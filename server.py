import json, os, re, shutil, subprocess, threading, time, urllib.parse
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

APP=Path(__file__).resolve().parent; CACHE={}; LOCK=threading.Lock()
if getattr(__import__('sys'),'frozen',False):
 APP=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'DownloadPackageManager'
 APP.mkdir(parents=True,exist_ok=True)
LABELS_FILE=APP/'user_labels.json'
SETTINGS_FILE=APP/'settings.json'; AI_CACHE_FILE=APP/'ai_descriptions.json'; INVENTORY_FILE=APP/'inventory.json'; COLLECTION_CACHE_FILE=APP/'collection_classifications.json'; MANUAL_ROOTS_FILE=APP/'manual_roots.json'; SNAPSHOT_FILE=APP/'inventory_snapshot.json'; SCAN_TTL_DAYS=7
NAMES={'down','download','downloads','downloda'}
def download_dir(name):
 low=name.lower()
 return low in NAMES or 'down' in low or '下载' in name
PACK={'.zip','.rar','.7z','.tar','.gz','.tgz','.iso','.whl','.crx','.exe','.msi','.msix','.msixbundle'}
DOC={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.txt'}
IMAGE={'.jpg','.jpeg','.png','.gif','.webp','.bmp','.tif','.tiff','.heic','.raw','.svg'}
VIDEO={'.mp4','.mkv','.avi','.mov','.wmv','.flv','.webm','.m4v','.ts','.mts','.3gp'}
AUDIO={'.mp3','.wav','.flac','.aac','.m4a','.ogg','.wma','.ape','.opus'}
MEDIA=IMAGE|VIDEO|AUDIO

def roots():
 out=[]
 for c in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
  d=Path(c+chr(58)+chr(92))
  try:
   if d.exists(): out += [p for p in d.iterdir() if p.is_dir() and download_dir(p.name)]
  except OSError: pass
 for raw in load_json_file(MANUAL_ROOTS_FILE,[]):
  try:
   p=Path(raw)
   if p.is_dir(): out.append(p)
  except OSError: pass
 return sorted(set(out),key=lambda p:str(p).lower())

def add_manual_root(path):
 p=Path(path).resolve()
 if not p.is_dir(): raise ValueError('所选路径不是有效目录')
 values=load_json_file(MANUAL_ROOTS_FILE,[])
 normalized={str(Path(x).resolve()).lower():x for x in values}
 normalized[str(p).lower()]=str(p)
 save_json_file(MANUAL_ROOTS_FILE,list(normalized.values()))
 return str(p)

def open_path(path):
 p=Path(path)
 if not p.exists(): raise FileNotFoundError('项目已不存在：'+str(p))
 if p.is_dir(): os.startfile(str(p))
 else: subprocess.Popen(['explorer.exe','/select,',str(p)])
 return str(p)

def natural_search(query):
 import urllib.request
 cfg=get_settings(True); key=cfg.get('apiKey','')
 if not key: raise ValueError('尚未配置 DeepSeek API Key')
 prompt=('理解用户想找哪类下载包，并扩展相关的中文/英文词、常见产品名。只返回严格JSON。字段：'
  'terms为可选同义词数组（任意一个命中即可，例如数据库应扩展为database、mysql、postgresql、sql server、oracle、redis、mongodb、navicat）；'
  'recommendations数组、kinds数组、minSizeMB、maxSizeMB、minAgeDays、maxAgeDays、suspicious、mediaDirectory。'
  '不要把“我要、找、查、帮我”等口语放进terms。用户查询：'+str(query))
 body=json.dumps({'model':cfg['model'],'messages':[{'role':'user','content':prompt}],
  'temperature':0,'response_format':{'type':'json_object'}}).encode()
 req=urllib.request.Request(cfg['baseUrl']+'/chat/completions',data=body,
  headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 response=json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
 content=response['choices'][0]['message']['content'].strip(); match=re.search(r'\{.*\}',content,re.S)
 if not match: raise ValueError('模型没有返回可解析的搜索条件')
 criteria=json.loads(match.group(0)); matches=[]
 with LOCK: items=list(CACHE.get('items',[]))
 terms=[str(x).lower() for x in criteria.get('terms',[]) if str(x).strip()]
 active=lambda k: k in criteria and criteria[k] not in (None,'',[])
 has_structured=any(active(k) for k in ('recommendations','kinds','minSizeMB','maxSizeMB','minAgeDays','maxAgeDays','suspicious','mediaDirectory'))
 for item in items:
  text=' '.join([item.get('name',''),item.get('displayName',''),item.get('path',''),item.get('kind',''),
   (item.get('aiDescription') or {}).get('summary',''),item.get('recommendation','')]).lower()
  term_match=any(t in text for t in terms) if terms else False
  structured_match=has_structured
  if criteria.get('recommendations') and item.get('recommendation') not in criteria['recommendations']: structured_match=False
  if criteria.get('kinds') and not any(str(k) in item.get('kind','') for k in criteria['kinds']): structured_match=False
  mb=item.get('size',0)/1048576; age=item.get('ageDays',0)
  if active('minSizeMB') and mb<float(criteria['minSizeMB']): structured_match=False
  if active('maxSizeMB') and mb>float(criteria['maxSizeMB']): structured_match=False
  if active('minAgeDays') and age<float(criteria['minAgeDays']): structured_match=False
  if active('maxAgeDays') and age>float(criteria['maxAgeDays']): structured_match=False
  if active('suspicious') and bool(item.get('suspicious'))!=bool(criteria['suspicious']): structured_match=False
  if active('mediaDirectory') and bool(item.get('mediaDirectory'))!=bool(criteria['mediaDirectory']): structured_match=False
  # LLM semantic result is the union of synonym hits and structured filter hits.
  if term_match or structured_match: matches.append(item['path'])
 return {'paths':matches,'criteria':criteria,'terms':terms}

def media_file_kind(p):
 ext=p.suffix.lower()
 return '图片' if ext in IMAGE else ('视频' if ext in VIDEO else ('音乐' if ext in AUDIO else ''))

def media_directory_kind(p):
 """Classify a directory when media is at least 60% of sampled files."""
 counts={'图片':0,'视频':0,'音乐':0}; total=0
 try:
  for base,ds,fs in os.walk(p,onerror=lambda e:None):
   for name in fs:
    total+=1; kind=media_file_kind(Path(name))
    if kind: counts[kind]+=1
    if total>=300: break
   if total>=300: break
 except OSError: return ''
 media=sum(counts.values())
 if total<2 or media/total<0.60: return ''
 kind=max(counts,key=counts.get)
 # Require the leading kind to dominate all files; otherwise use generic media.
 return kind if counts[kind]/total>=0.50 else ''

def summary(p):
 size=files=dirs=err=0; newest=0; hints=[]
 if p.is_file():
  s=p.stat(); return s.st_size,1,0,s.st_mtime,[],0
 for base,ds,fs in os.walk(p,onerror=lambda e:None):
  dirs+=len(ds)
  for n in fs:
   if re.search(r'crack|keygen|注册机|破解|无限试用|激活工具|serial',n,re.I): hints.append(n)
   try:
    s=(Path(base)/n).stat(); size+=s.st_size; files+=1; newest=max(newest,s.st_mtime)
   except OSError: err+=1
 return size,files,dirs,newest,hints[:6],err

def analyze(p,size,files,newest,hints):
 low=p.name.lower(); ext=p.suffix.lower(); age=max(0,int((time.time()-newest)/86400)); reasons=[]; score=55
 kind='文件夹'
 if ext in PACK: kind='安装/压缩包'
 elif ext in DOC: kind='文档'
 elif ext in MEDIA: kind='媒体'
 elif p.is_file(): kind=(ext[1:].upper()+' 文件') if ext else '文件'
 public=bool(re.search(r'python|node|jdk|git[-_ ]|docker|ubuntu|cuda|redis|mysql|chrome|driver|torch|esp-idf|freeglut|mujoco|nvm|telegram|tsetup|win32disk|clash|openai',low))
 commercial=bool(re.search(r'navicat|xftp|pycharm|vmware|adobe|迅捷pdf|1password',low))
 if files==0 and p.is_dir(): score=2; reasons=['空目录，无需保留']
 else:
  if kind=='安装/压缩包': score+=8
  if age>1095: score-=35; reasons.append('超过 3 年，兼容性与安全更新价值低')
  elif age>730: score-=22; reasons.append('超过 2 年，建议优先核对新版')
  elif age>365: score-=8; reasons.append('已有一年以上，可能存在新版')
  else: score+=10; reasons.append('文件较新')
  if public: score-=8; reasons.append('公开软件/开源组件，通常可从官网重下')
  if size>2*1024**3: score-=8; reasons.append('占用空间很大')
  if kind in ('媒体','文档'): score+=18; reasons.append('可能是个人资料，不能按普通安装包判断')
  if hints: score-=18; reasons.append('检测到疑似破解/激活文件，存在安全与授权风险')
 score=max(0,min(100,score)); rec='不用保住' if score<38 else ('待确认' if score<65 else '建议保留')
 redown='方便（建议官网）' if public else ('不确定/可能无法重下' if kind in ('媒体','文档') else ('可重下，但可能需账户/授权' if commercial else '不确定'))
 if hints: reg='发现：'+'；'.join(hints[:3])+'。不建议运行来源不明的注册机/破解文件；请改用正版授权或官方免费版。'
 elif commercial: reg='商业软件，通常需要账户、订阅或许可证；未发现随包注册机。'
 elif public: reg='通常无需注册码（开源、免费或官方公共组件）；仍应核验官方下载来源。'
 else: reg='仅凭文件名无法确认；未发现明显注册机/破解文件。'
 return {'kind':kind,'ageDays':age,'score':score,'recommendation':rec,'reasons':reasons,'redownload':redown,'registration':reg,'suspicious':bool(hints)}

def load_json_file(file, default):
 try: return json.loads(file.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError): return default

def save_json_file(file, value):
 file.parent.mkdir(parents=True,exist_ok=True); tmp=file.with_suffix(file.suffix+'.tmp')
 tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,file)

def get_settings(reveal=False):
 cfg={'apiKey':'','baseUrl':'https://api.deepseek.com','model':'deepseek-v4-flash','autoSearch':True}
 cfg.update(load_json_file(SETTINGS_FILE,{}))
 if not reveal:
  key=cfg.get('apiKey',''); cfg['apiKeyMasked']=('••••'+key[-4:]) if key else ''; cfg['apiKey']=''
 return cfg

def save_settings(data):
 old=get_settings(True); key=str(data.get('apiKey','')).strip()
 if key: old['apiKey']=key
 old['baseUrl']=str(data.get('baseUrl') or old['baseUrl']).strip().rstrip('/')
 old['model']=str(data.get('model') or old['model']).strip(); old['autoSearch']=bool(data.get('autoSearch',True))
 save_json_file(SETTINGS_FILE,old); return get_settings(False)

def item_fingerprint(item): return '|'.join([item['name'].lower(),str(item['size']),item['modified']])

def web_search_snippets(query):
 import urllib.request
 url='https://www.google.com/search?q='+urllib.parse.quote(query)
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 try:
  html=urllib.request.urlopen(req,timeout=12).read().decode('utf-8','ignore')
  html=re.sub(r'<script.*?</script>|<style.*?</style>',' ',html,flags=re.I|re.S)
  return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html))[:6000]
 except Exception as e: return '联网搜索失败：'+str(e)

def deepseek_description(item):
 import urllib.request
 cfg=get_settings(True); key=cfg.get('apiKey','')
 if not key: raise ValueError('尚未配置 DeepSeek API Key，请打开“软件设置”填写。')
 prompt=('根据下载包名判断这是什么。只返回严格JSON：{\"summary\":\"10至15个中文字的简短描述\"}。必须给出最可能判断，不能回答无法确认或复述文件名。包名：%s')%item['name']
 body=json.dumps({'model':cfg['model'],'messages':[{'role':'user','content':prompt}],'temperature':0.1,'response_format':{'type':'json_object'}}).encode()
 req=urllib.request.Request(cfg['baseUrl']+'/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 response=json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
 content=response['choices'][0]['message']['content'].strip().strip(chr(96)).replace('json\n','',1)
 return json.loads(content)

def enrich_items(paths):
 wanted=set(paths); cache=load_json_file(AI_CACHE_FILE,{})
 # Reuse the most recent scan. The old implementation rescanned every drive for
 # every package, which made the UI appear stuck.
 with LOCK: cached_items=list(CACHE.get('items',[]))
 data={'items':cached_items} if cached_items else scan()
 targets=[item for item in data['items'] if item['path'] in wanted]
 results={}; errors={}; pending=[]
 for item in targets:
  fp=item_fingerprint(item)
  if fp in cache: results[item['path']]=cache[fp]
  else: pending.append(item)
 def ask(item):
  desc=deepseek_description(item)
  desc={'summary':str(desc.get('summary','')).strip()[:30],
        'searchedAt':datetime.now().isoformat(timespec='seconds'),
        'model':get_settings(True)['model']}
  return item,desc
 from concurrent.futures import ThreadPoolExecutor,as_completed
 # DeepSeek requests run concurrently, with an explicit maximum of 10.
 with ThreadPoolExecutor(max_workers=min(10,len(pending) or 1)) as pool:
  futures={pool.submit(ask,item):item for item in pending}
  for future in as_completed(futures):
   item=futures[future]
   try:
    _,desc=future.result(); cache[item_fingerprint(item)]=desc; results[item['path']]=desc
   except Exception as e: errors[item['path']]=str(e)
 if pending: save_json_file(AI_CACHE_FILE,cache)
 return {'ok':not errors,'result':results,'errors':errors}

def collection_signature(p):
 try:
  children=sorted(p.iterdir(),key=lambda x:x.name.lower())
  parts=[]
  for x in children[:40]:
   try: parts.append(x.name+'|'+('d' if x.is_dir() else 'f')+'|'+str(x.stat().st_size if x.is_file() else 0))
   except OSError: parts.append(x.name)
  return str(p.resolve()).lower()+'||'+'||'.join(parts)
 except OSError: return str(p).lower()

def classify_collection(p):
 """Return whether a first-level folder is a collection of separate downloads."""
 try: children=sorted(p.iterdir(),key=lambda x:x.name.lower())
 except OSError: return {'isCollection':False,'reason':'目录不可读'}
 sample=[x.name+('（目录）' if x.is_dir() else '') for x in children[:40]]
 if len(children)<2: return {'isCollection':False,'reason':'子项不足，不展开'}
 import urllib.request
 cfg=get_settings(True); key=cfg.get('apiKey','')
 if not key: return {'isCollection':False,'reason':'未配置AI，保守地视为完整包'}
 prompt=('判断这个下载目录下的一级文件夹，是一个完整软件/资料包，还是用户用于归类多个相互独立下载包的集合目录。'
         '只有当其直接子项明显是多个可各自独立整理、移动或删除的下载包时才判为集合；安装目录中的exe、dll、资源目录不是集合。'
         '只返回严格JSON：{"isCollection":true或false,"reason":"15字内理由"}。'
         '目录名：%s；直接子项：%s')%(p.name,'、'.join(sample))
 body=json.dumps({'model':cfg['model'],'messages':[{'role':'user','content':prompt}],
                  'temperature':0,'response_format':{'type':'json_object'}}).encode()
 req=urllib.request.Request(cfg['baseUrl']+'/chat/completions',data=body,
  headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 response=json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
 content=response['choices'][0]['message']['content'].strip().strip(chr(96)).replace('json\n','',1)
 result=json.loads(content)
 return {'isCollection':bool(result.get('isCollection')),'reason':str(result.get('reason',''))[:30]}

def classify_first_level(children):
 cache=load_json_file(COLLECTION_CACHE_FILE,{})
 folders=[p for p in children if p.is_dir()]; results={}; pending=[]
 for p in folders:
  sig=collection_signature(p)
  if sig in cache: results[str(p)]=cache[sig]
  else: pending.append((p,sig))
 from concurrent.futures import ThreadPoolExecutor,as_completed
 with ThreadPoolExecutor(max_workers=min(10,len(pending) or 1)) as pool:
  futures={pool.submit(classify_collection,p):(p,sig) for p,sig in pending}
  for future in as_completed(futures):
   p,sig=futures[future]
   try:
    value=future.result(); results[str(p)]=value
    # Do not persist transient API/key failures as a permanent decision.
    if not value.get('reason','').startswith(('未配置','目录不可读')): cache[sig]=value
   except Exception as e: results[str(p)]={'isCollection':False,'reason':'AI判断失败，暂不展开：'+str(e)[:80]}
 if pending: save_json_file(COLLECTION_CACHE_FILE,cache)
 return results

def load_labels():
 try:
  data=json.loads(LABELS_FILE.read_text(encoding='utf-8'))
  return data if isinstance(data,dict) else {}
 except (OSError,json.JSONDecodeError): return {}

def save_keep(paths):
 labels=load_labels(); now=datetime.now().isoformat(timespec='seconds')
 for x in paths:
  p=Path(x)
  if not allowed(p) or not p.exists(): continue
  labels[str(p.resolve()).lower()]={'label':'keep','markedAt':now,'path':str(p)}
 tmp=LABELS_FILE.with_suffix('.tmp')
 tmp.write_text(json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,LABELS_FILE)
 return [v['path'] for v in labels.values() if v.get('label')=='keep']

def scan(force=False):
 if not force:
  snap=load_json_file(SNAPSHOT_FILE,None)
  if isinstance(snap,dict) and isinstance(snap.get('items'),list) and snap.get('generatedAt'):
   try: age=(datetime.now()-datetime.fromisoformat(snap['generatedAt'])).total_seconds()
   except (ValueError,TypeError): age=-1
   if 0<=age<SCAN_TTL_DAYS*86400:
    data={'generatedAt':snap['generatedAt'],'items':snap['items'],'roots':snap.get('roots',[]),'errors':snap.get('errors',[])}
    with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
    return data
 rr=roots(); out=[]; errors=[]; labels=load_labels(); ai_cache=load_json_file(AI_CACHE_FILE,{}); old_inventory=load_json_file(INVENTORY_FILE,[]); baseline=not INVENTORY_FILE.exists()
 def add_item(p,root,collection=None,collection_reason='',media_kind=''):
  try:
   size,files,dirs,newest,hints,errs=summary(p); newest=newest or p.stat().st_mtime
   item={'id':str(p),'name':p.name,'path':str(p),'parentPath':str(p.parent),'root':str(root),'size':size,'files':files,'dirs':dirs,'modified':datetime.fromtimestamp(newest).isoformat(timespec='seconds'),'readErrors':errs,**analyze(p,size,files,newest,hints)}
   if media_kind:
    item.update(kind=media_kind+'目录',recommendation='建议保留',score=max(85,item['score']),mediaDirectory=True)
    item['reasons']=['目录内主要是'+media_kind+'，不拆成下载包；请按个人媒体资料处理']
   if collection:
    item['collection']=collection; item['displayName']=collection+' / '+p.name
    item['reasons']=['来自集合目录“'+collection+'”（'+collection_reason+'）']+item['reasons']
   manual=labels.get(str(p.resolve()).lower())
   if manual and manual.get('label')=='keep':
    item.update(recommendation='保留（手工）',score=100,manualKeep=True)
    item['reasons']=['你在 '+manual.get('markedAt','此前')+' 手工标记为保留；重新扫描不会覆盖']
   fp=item_fingerprint(item); item['fingerprint']=fp; item['aiDescription']=({'summary':media_kind,'model':'本地媒体识别'} if media_kind else ai_cache.get(fp)); item['isNew']=False if baseline else fp not in old_inventory
   out.append(item)
  except OSError as e: errors.append(str(e))
 for root in rr:
  try: children=list(root.iterdir())
  except OSError as e: errors.append(str(e)); continue
  media_kinds={str(p):media_directory_kind(p) for p in children if p.is_dir()}
  decisions=classify_first_level([p for p in children if not media_kinds.get(str(p))])
  for p in children:
   # Standalone media files are personal content, not downloadable packages.
   if p.is_file() and media_file_kind(p): continue
   media_kind=media_kinds.get(str(p),'')
   if media_kind:
    add_item(p,root,media_kind=media_kind); continue
   decision=decisions.get(str(p),{})
   if p.is_dir() and decision.get('isCollection'):
    try: members=list(p.iterdir())
    except OSError as e: errors.append(str(e)); add_item(p,root); continue
    for member in members:
     if member.is_file() and media_file_kind(member): continue
     member_media=media_directory_kind(member) if member.is_dir() else ''
     add_item(member,root,p.name,decision.get('reason','多个下载包的集合'),member_media)
   else: add_item(p,root)
 save_json_file(INVENTORY_FILE,[item_fingerprint(x) for x in out])
 data={'generatedAt':datetime.now().isoformat(timespec='seconds'),'items':out,'roots':[str(x) for x in rr],'errors':errors}
 save_json_file(SNAPSHOT_FILE,data)
 with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
 return data

def allowed(p):
 try:
  resolved=p.resolve()
  for root in roots():
   try:
    rel=resolved.relative_to(root.resolve())
    if len(rel.parts) in (1,2): return True
   except (ValueError,OSError): pass
  return False
 except OSError: return False


def recycle(paths):
 safe=[str(Path(x).resolve()) for x in paths if allowed(Path(x)) and Path(x).exists()]
 if not safe: return []
 # Native Windows Shell API: FO_DELETE with FOF_ALLOWUNDO sends items to Recycle Bin.
 import ctypes
 from ctypes import wintypes
 class SHFILEOPSTRUCTW(ctypes.Structure):
  _fields_=[('hwnd',wintypes.HWND),('wFunc',wintypes.UINT),('pFrom',wintypes.LPCWSTR),
   ('pTo',wintypes.LPCWSTR),('fFlags',wintypes.WORD),('fAnyOperationsAborted',wintypes.BOOL),
   ('hNameMappings',ctypes.c_void_p),('lpszProgressTitle',wintypes.LPCWSTR)]
 source=chr(0).join(safe)+chr(0)+chr(0)
 op=SHFILEOPSTRUCTW(None,3,source,None,0x40|0x10|0x04|0x400,False,None,None)
 code=ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
 if code or op.fAnyOperationsAborted: raise RuntimeError('移入回收站失败，Windows 返回代码：%s'%code)
 return safe

def move(paths,dest):
 d=Path(dest)
 if not d.is_absolute(): raise ValueError('目标目录必须是绝对路径')
 d.mkdir(parents=True,exist_ok=True); done=[]
 for x in paths:
  p=Path(x)
  if not allowed(p) or not p.exists(): continue
  target=d/p.name
  if target.exists(): raise FileExistsError('目标已存在：'+str(target))
  shutil.move(str(p),str(target)); done.append({'from':str(p),'to':str(target)})
 return done

class H(SimpleHTTPRequestHandler):
 def translate_path(self,path): return str(APP/(urllib.parse.urlparse(path).path.lstrip('/') or 'index.html'))
 def sendj(self,o,status=200):
  b=json.dumps(o,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  u=urllib.parse.urlparse(self.path)
  if u.path=='/api/scan':
   force=urllib.parse.parse_qs(u.query).get('force',['0'])[0]=='1'
   try:
    with LOCK: fresh=CACHE and time.time()-CACHE.get('at',0)<300
    if fresh and not force:
     with LOCK: return self.sendj({k:v for k,v in CACHE.items() if k!='at'})
    return self.sendj(scan(force))
   except Exception as e: return self.sendj({'error':str(e)},500)
  return super().do_GET()
 def do_POST(self):
  try:
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}'); paths=data.get('paths',[])
   if not isinstance(paths,list) or len(paths)>500: raise ValueError('选择列表无效')
   result=move(paths,data.get('destination','')) if self.path=='/api/move' else recycle(paths) if self.path=='/api/recycle' else save_keep(paths) if self.path=='/api/keep' else None
   if result is None: return self.sendj({'error':'Not found'},404)
   return self.sendj({'ok':True,'result':result})
  except Exception as e: return self.sendj({'ok':False,'error':str(e)},400)
 def log_message(self,fmt,*args): print('[web]',fmt%args)

if __name__=='__main__':
 print('下载包管家：http://127.0.0.1:8766'); ThreadingHTTPServer(('127.0.0.1',8766),H).serve_forever()
