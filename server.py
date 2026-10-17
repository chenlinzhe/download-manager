import base64, ctypes, json, os, re, shutil, subprocess, threading, time, urllib.parse
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

APP=Path(__file__).resolve().parent; CACHE={}; LOCK=threading.Lock()
if getattr(__import__('sys'),'frozen',False):
 APP=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'DownloadPackageManager'
 APP.mkdir(parents=True,exist_ok=True)
LABELS_FILE=APP/'user_labels.json'
SETTINGS_FILE=APP/'settings.json'; AI_CACHE_FILE=APP/'ai_descriptions.json'; INVENTORY_FILE=APP/'inventory.json'; COLLECTION_CACHE_FILE=APP/'collection_classifications.json'; MANUAL_ROOTS_FILE=APP/'manual_roots.json'; SNAPSHOT_FILE=APP/'inventory_snapshot.json'; COLLECTION_FAIL_FILE=APP/'collection_failures.json'; SCAN_TTL_DAYS=7
APP_VERSION='1.1'
AI_FAIL_TTL=1800
SCAN_LOCK=threading.Lock()
PROGRESS={'phase':'','done':0,'total':0,'at':0.0}
def set_progress(phase,done=0,total=0):
 PROGRESS.update(phase=phase,done=done,total=total,at=time.time())
def scan_status(): return dict(PROGRESS)
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

def _llm_error(e):
 """把 AI 调用异常翻译成用户能直接看懂的一句话。"""
 import urllib.error
 if isinstance(e,urllib.error.HTTPError):
  try: body=e.read().decode('utf-8','ignore')
  except Exception: body=''
  text=body
  try:
   parsed=json.loads(body); text=str((parsed.get('error') or {}).get('message') or body)
  except Exception: pass
  if e.code==401: return 'DeepSeek 认为 API Key 无效或已失效（HTTP 401）：请打开「模型设置」重新填写 Key，再点「测试连接」确认'
  if e.code==402: return 'DeepSeek 账户余额不足（HTTP 402），请充值后再试'
  if e.code==403: return 'DeepSeek 拒绝访问（HTTP 403）：'+text[:120]
  if e.code==404: return 'DeepSeek 接口地址或模型不存在（HTTP 404）：'+text[:120]
  if e.code==429: return 'DeepSeek 触发限流（HTTP 429），请稍后再试'
  if e.code>=500: return 'DeepSeek 服务暂时不可用（HTTP %d），请稍后再试'%e.code
  return 'DeepSeek 返回错误（HTTP %d）：%s'%(e.code,text[:150])
 if isinstance(e,(urllib.error.URLError,TimeoutError,OSError)):
  return '连不上 DeepSeek：%s（请检查网络或代理后重试）'%str(getattr(e,'reason',e))[:140]
 return 'AI 调用失败：'+str(e)[:150]

_VEC={'fp':None,'idf':None,'docs':None}
def _search_text(item):
 return ' '.join([item.get('name',''),item.get('displayName',''),item.get('path',''),item.get('kind',''),(item.get('aiDescription') or {}).get('summary',''),item.get('recommendation','')]).lower()
_STOP=set('的了着是在有和与及或也都就才又再还只但并而这那此其某个吗呢吧啊呀哦嗯哈嗦啦喰么之对从向给被把让到于为以用想找要搜查看请帮哪什该我你他她它咱侩种')
_STOP|={'一个','一下','一种','一些','一类','一款','这个','那个','这些','那些','哪个','哪些','这种','那种','哪种','这么','那么','这样','那样','一点','有些','东西','里面','我们','你们','他们','她们','它们','咱们','自己','可以','想要','需要','应该','看看','点儿','有点儿','如何','为什么'}
_STOP|={'a','an','the','of','for','is','are','it','to','and','or','this','that','these','those','want','find','get','with','my','me','one','we','you','they'}
def _tok(text):
 import jieba, re
 text=(text or '').lower()
 toks=[]
 for seg in jieba.lcut(text):
  seg=seg.strip()
  if not seg: continue
  if re.fullmatch(r'[\u4e00-\u9fff]+',seg):
   toks.append(seg)
  else:
   for w in re.findall(r'[a-z0-9]+',seg):
    if w: toks.append(w)
 kept=[t for t in toks if t not in _STOP]
 return kept if kept else toks
def _tfidf(toks,idf):
 n=len(toks) or 1; c={}
 for t in toks: c[t]=c.get(t,0)+1
 return {t:(f/n)*idf[t] for t,f in c.items() if t in idf}
def _cos(a,b):
 if not a or not b: return 0.0
 if len(a)>len(b): a,b=b,a
 dot=sum(fa*b.get(t,0.0) for t,fa in a.items())
 na=sum(f*f for f in a.values())**0.5
 nb=sum(f*f for f in b.values())**0.5
 return dot/(na*nb+1e-9) if (na and nb) else 0.0
def _vector_index(items):
 import math
 try:
  from collections import Counter
 except Exception: pass
 texts=[_search_text(x) for x in items]
 fp=str(hash(tuple(texts)))
 if _VEC['fp']==fp: return _VEC['idf'],_VEC['docs']
 N=len(texts); df={}
 docs=[]
 for t in texts:
  toks=_tok(t); docs.append(toks)
  for term in set(toks): df[term]=df.get(term,0)+1
 idf={t:math.log((N+1)/(d+1))+1 for t,d in df.items()}
 vecs=[_tfidf(docs[i],idf) for i in range(N)]
 _VEC.update(fp=fp,idf=idf,docs=vecs)
 return idf,vecs
def _vector_recall(query,items,topk=30):
 try:
  idf,vecs=_vector_index(items)
  qv=_tfidf(_tok(query or ''),idf)
  scored=[(_cos(qv,vecs[i]),items[i]['path']) for i in range(len(vecs))]
  scored.sort(key=lambda x:x[0],reverse=True)
  return [p for s,p in scored[:topk] if s>0], scored
 except Exception:
  return [], []

def split_query_terms(query):
 return _tok(query)
def natural_search(query):
 import urllib.request, urllib.error
 cfg=get_settings(True); key=cfg.get('apiKey','')
 if not key: raise ValueError('尚未配置 DeepSeek API Key')
 with LOCK: items=list(CACHE.get('items',[]))
 texts=[_search_text(x) for x in items]
 terms=split_query_terms(query)
 base=(cfg.get('baseUrl') or 'https://api.deepseek.com').strip().rstrip('/')
 model=cfg.get('model') or 'deepseek-v4-flash'
 def call_llm(prompt):
  body=json.dumps({'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0,'response_format':{'type':'json_object'}}).encode()
  req=urllib.request.Request(base+'/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  try: raw=urllib.request.urlopen(req,timeout=30).read().decode('utf-8')
  except Exception as e: raise RuntimeError(_llm_error(e))
  content=json.loads(raw)['choices'][0]['message']['content'].strip()
  m=re.search(r'\{.*\}',content,re.S)
  if not m: raise ValueError('模型没有返回可解析的搜索条件')
  return json.loads(m.group(0))
 # A) 本地切词模糊召回
 local_paths=[items[i]['path'] for i in range(len(items)) if any(t in texts[i] for t in terms)]
 # B) 向量召回（查询→向量→cosine）
 def score_lex(i):
  name=items[i].get('name','').lower()
  return 2*sum(1 for t in terms if t in texts[i]) + sum(1 for t in terms if t in name)
 vec_paths=[]
 try:
  vec_paths,_= _vector_recall(query, items, 30)
 except Exception: pass
 # 候选：词法打分 top30 与向量 top30 取并
 lex_rank=sorted(range(len(items)), key=score_lex, reverse=True)
 cand=[]
 for i in lex_rank[:30]:
  if score_lex(i)>0:
   cand.append(i)
 cand_set=set(cand)
 if vec_paths:
  pmap={items[i]['path']:i for i in range(len(items))}
  for p in vec_paths:
   i=pmap.get(p)
   if i is not None and i not in cand_set:
    cand_set.add(i); cand.append(i)
 cand=[i for i in cand if i<len(items)]
 llm_paths=set(); parsed={}
 if cand:
  lines=[]
  for n,i in enumerate(cand):
   info=(items[i].get('aiDescription') or {}).get('summary','')
   lines.append('%d. %s｜%s' % (n, items[i].get('name',''), info))
  prompt=('是一款“下载包管家”应用，要从本机缓存的下载包里找出用户关心的那类。\n'
    '用户查询：'+str(query)+'\n'
    '已从缓存召回候选（编号. 包名｜说明）：\n'+'\n'.join(lines)+'\n'
    '请只返回严格 JSON：{"relevant":[候选编号数组],"extra_terms":[能继续扩大召回的相关中英文词、常见产品名数组]}。'
    'relevant 从上面的候选编号里挑与用户意图相关的；extra_terms 没有就返回空数组。')
  parsed=call_llm(prompt)
  if isinstance(parsed.get('relevant'),list):
   for idx in parsed['relevant']:
    try:
     i=cand[int(idx)]
     if 0<=i<len(items): llm_paths.add(items[i]['path'])
    except (ValueError,IndexError,TypeError): pass
  if isinstance(parsed.get('paths'),list):
   for ppp in parsed['paths']:
    if ppp: llm_paths.add(str(ppp))
  extra=[str(x) for x in (parsed.get('extra_terms') or []) if str(x).strip() and str(x).lower() not in _STOP]
 else:
  prompt=('理解用户想找哪类下载包，并扩展相关的中文/英文词、常见产品名。只返回严格JSON。字段：'
    'terms为可选同义词数组（任意一个命中即可）、recommendations数组、kinds数组、minSizeMB、maxSizeMB、minAgeDays、maxAgeDays、suspicious、mediaDirectory。'
    '用户查询：'+str(query))
  parsed=call_llm(prompt)
  extra=[str(x) for x in (parsed.get('terms') or []) if str(x).strip() and str(x).lower() not in _STOP]
 all_terms=terms+extra
 for i in range(len(items)):
  if any(t in texts[i] for t in all_terms): llm_paths.add(items[i]['path'])
 # 并集 = 切词模糊 ∪ 向量召回 ∪ LLM(相关候选+扩词)
 result=set(local_paths)|set(vec_paths)|llm_paths
 return {'paths':sorted(result),'criteria':parsed,'terms':all_terms,'candidates':len(cand),'vec':len(vec_paths)}

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

def _dpapi(raw, protect=True):
 from ctypes import wintypes
 class BLOB(ctypes.Structure):
  _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_char))]
 raw=raw if isinstance(raw,bytes) else str(raw).encode('utf-8')
 if not raw: return b''
 buf=ctypes.create_string_buffer(raw,len(raw))
 src=BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char))); dst=BLOB()
 fn=ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
 if not fn(ctypes.byref(src),None,None,None,None,0,ctypes.byref(dst)): raise RuntimeError('系统加密接口调用失败')
 try: return ctypes.string_at(dst.pbData,dst.cbData)
 finally: ctypes.windll.kernel32.LocalFree(dst.pbData)

def protect_key(key):
 try: return _dpapi(str(key),True).hex()
 except Exception: return ''

def unprotect_key(token):
 try: return _dpapi(bytes.fromhex(str(token or '')),False).decode('utf-8')
 except Exception: return ''

def get_settings(reveal=False):
 cfg={'baseUrl':'https://api.deepseek.com','model':'deepseek-v4-flash','autoSearch':True,'destination':''}
 cfg.update(load_json_file(SETTINGS_FILE,{}))
 key=unprotect_key(cfg.get('apiKeyEnc')) or str(cfg.get('apiKey') or '')
 if not reveal:
  cfg['apiKeyMasked']=('••••'+key[-4:]) if key else ''; cfg['apiKey']=''
  return cfg
 cfg['apiKey']=key; return cfg

def save_settings(data):
 old=get_settings(True); key=str(data.get('apiKey','')).strip()
 if data.get('clearApiKey'): old['apiKey']=''
 elif key: old['apiKey']=key
 old['baseUrl']=str(data.get('baseUrl') or old['baseUrl']).strip().rstrip('/')
 old['model']=str(data.get('model') or old['model']).strip()
 old['autoSearch']=bool(data.get('autoSearch',old.get('autoSearch',True)))
 old['destination']=str(data.get('destination') or old.get('destination') or '').strip()
 plain=old.pop('apiKey','') or ''
 old.pop('apiKeyMasked',None); old.pop('apiKeyEnc',None)
 if plain: old['apiKeyEnc']=protect_key(plain)
 save_json_file(SETTINGS_FILE,old); return get_settings(False)

def test_connection(baseUrl=None, model=None, apiKey=None):
 import urllib.request, urllib.error, time
 cfg=get_settings(True)
 base=str(baseUrl or cfg.get('baseUrl') or 'https://api.deepseek.com').strip().rstrip('/')
 model=str(model or cfg.get('model','')).strip()
 key=str(apiKey or '').strip() or cfg.get('apiKey','')
 if not key: return {'ok':False,'error':'尚未配置 DeepSeek API Key，请先填写并保存'}
 def chat_check():
  body=json.dumps({'model':model,'messages':[{'role':'user','content':'回复ok'}],'max_tokens':4}).encode()
  req=urllib.request.Request(base+'/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  return urllib.request.urlopen(req,timeout=15)
 t0=time.time()
 try:
  req=urllib.request.Request(base+'/models',headers={'Authorization':'Bearer '+key})
  resp=urllib.request.urlopen(req,timeout=15)
  data=json.loads(resp.read().decode('utf-8'))
  ms=[m.get('id') for m in data.get('data',[]) if isinstance(m,dict)]
  latency=int((time.time()-t0)*1000)
  model_ok=(model in ms) if ms else True
  return {'ok':True,'latencyMs':latency,'endpoint':base,'model':model,'availableModels':ms,'modelOk':model_ok}
 except urllib.error.HTTPError as e:
  code=e.code; msg=e.read().decode('utf-8','ignore')[:300]
  if code==401: return {'ok':False,'error':'DeepSeek 认为 API Key 无效或已失效（HTTP 401）：请打开「模型设置」重新填写 Key 后重试','endpoint':base}
  if code==404:
   try:
    t0=time.time(); chat_check(); latency=int((time.time()-t0)*1000)
    return {'ok':True,'latencyMs':latency,'endpoint':base,'model':model,'via':'chat/completions','modelOk':True}
   except urllib.error.HTTPError as e2:
    return {'ok':False,'error':'HTTP %s：%s'%(e2.code,e2.read().decode('utf-8','ignore')[:300]),'endpoint':base}
   except Exception as e2:
    return {'ok':False,'error':str(e2),'endpoint':base}
  return {'ok':False,'error':'HTTP %s：%s'%(code,msg),'endpoint':base}
 except Exception as e:
  return {'ok':False,'error':str(e),'endpoint':base}

def item_fingerprint(item): return '|'.join([item['name'].lower(),str(item['size']),item['modified']])

def deepseek_description(item):
 import urllib.request
 cfg=get_settings(True); key=cfg.get('apiKey','')
 if not key: raise ValueError('尚未配置 DeepSeek API Key，请打开「模型设置」填写。')
 prompt=('根据下载包名判断这是什么。只返回严格JSON：{\"summary\":\"10至15个中文字的简短描述\"}。必须给出最可能判断，不能回答无法确认或复述文件名。包名：%s')%item['name']
 body=json.dumps({'model':cfg['model'],'messages':[{'role':'user','content':prompt}],'temperature':0.1,'response_format':{'type':'json_object'}}).encode()
 req=urllib.request.Request(cfg['baseUrl']+'/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 try: response=json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
 except Exception as e: raise RuntimeError(_llm_error(e))
 try:
  content=response['choices'][0]['message']['content'].strip().strip(chr(96)).replace('json\n','',1)
  return json.loads(content)
 except (KeyError,IndexError,ValueError) as e: raise RuntimeError('DeepSeek 返回内容无法解析：'+str(e)[:120])

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
 try: response=json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
 except Exception as e: raise RuntimeError(_llm_error(e))
 try:
  content=response['choices'][0]['message']['content'].strip().strip(chr(96)).replace('json\n','',1)
  result=json.loads(content)
 except (KeyError,IndexError,ValueError) as e: raise RuntimeError('DeepSeek 返回内容无法解析：'+str(e)[:120])
 return {'isCollection':bool(result.get('isCollection')),'reason':str(result.get('reason',''))[:30]}

def collection_prejudge(p):
 """本地零成本预判，避免为显然不是集合的目录花掉 AI 调用。"""
 try: kids=list(p.iterdir())
 except OSError: return {'isCollection':False,'reason':'目录不可读'}
 if len(kids)<2: return {'isCollection':False,'reason':'子项不足，不展开'}
 packs=[k for k in kids if k.is_file() and k.suffix.lower() in PACK]
 if len(packs)>=2 and len(packs)/len(kids)>=0.6: return {'isCollection':True,'reason':'多个独立安装包'}
 install={'.dll','.lib','.pdb','.so','.dat','.pak'}
 if any(k.is_file() and k.suffix.lower() in install for k in kids): return {'isCollection':False,'reason':'安装目录内容'}
 return None

def classify_first_level(children):
 cache=load_json_file(COLLECTION_CACHE_FILE,{}); fails=load_json_file(COLLECTION_FAIL_FILE,{})
 now=time.time(); folders=[p for p in children if p.is_dir()]; results={}; pending=[]
 for p in folders:
  hint=collection_prejudge(p)
  if hint is not None: results[str(p)]=hint; continue
  sig=collection_signature(p)
  if sig in cache: results[str(p)]=cache[sig]; continue
  if now-fails.get(sig,0)<AI_FAIL_TTL:
   results[str(p)]={'isCollection':False,'reason':'AI 暂不可用，先不展开'}; continue
  pending.append((p,sig))
 failed=False
 if pending:
  from concurrent.futures import ThreadPoolExecutor,as_completed
  done=0; set_progress('AI 判断集合目录',0,len(pending))
  with ThreadPoolExecutor(max_workers=min(10,len(pending) or 1)) as pool:
   futures={pool.submit(classify_collection,p):(p,sig) for p,sig in pending}
   for future in as_completed(futures):
    p,sig=futures[future]; done+=1; set_progress('AI 判断集合目录',done,len(pending))
    try:
     value=future.result(); results[str(p)]=value
     # Do not persist transient API/key failures as a permanent decision.
     if not value.get('reason','').startswith(('未配置','目录不可读')): cache[sig]=value
    except Exception as e:
     results[str(p)]={'isCollection':False,'reason':'AI判断失败，暂不展开：'+str(e)[:80]}
     fails[sig]=now; failed=True
  save_json_file(COLLECTION_CACHE_FILE,cache)
  if failed: save_json_file(COLLECTION_FAIL_FILE,fails)
 return results

def load_labels():
 try:
  data=json.loads(LABELS_FILE.read_text(encoding='utf-8'))
  return data if isinstance(data,dict) else {}
 except (OSError,json.JSONDecodeError): return {}

def save_keep(paths):
 labels=load_labels(); now=datetime.now().isoformat(timespec='seconds'); marked=[]; base=roots()
 for x in paths:
  p=Path(x)
  if not allowed(p,base) or not p.exists(): continue
  labels[str(p.resolve()).lower()]={'label':'keep','markedAt':now,'path':str(p)}; marked.append(str(p.resolve()))
 if marked:
  tmp=LABELS_FILE.with_suffix('.tmp')
  tmp.write_text(json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,LABELS_FILE)
 return marked

def scan(force=False):
 if SCAN_LOCK.acquire(blocking=False):
  try: return _scan_impl(force)
  finally: set_progress(''); SCAN_LOCK.release()
 with LOCK: cached=dict(CACHE) if CACHE.get('items') else None
 if cached:
  cached.pop('at',None); return cached
 SCAN_LOCK.acquire()
 try:
  snap=load_json_file(SNAPSHOT_FILE,None)
  if isinstance(snap,dict) and isinstance(snap.get('items'),list): return snap
  return _scan_impl(False)
 finally: set_progress(''); SCAN_LOCK.release()

def _scan_impl(force=False):
 if not force:
  snap=load_json_file(SNAPSHOT_FILE,None)
  if isinstance(snap,dict) and isinstance(snap.get('items'),list) and snap.get('generatedAt'):
   try: age=(datetime.now()-datetime.fromisoformat(snap['generatedAt'])).total_seconds()
   except (ValueError,TypeError): age=-1
   if 0<=age<SCAN_TTL_DAYS*86400:
    data={'generatedAt':snap['generatedAt'],'items':snap['items'],'roots':snap.get('roots',[]),'errors':snap.get('errors',[])}
    with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
    return data
 set_progress('枚举扫描目录'); rr=roots(); out=[]; errors=[]; labels=load_labels(); ai_cache=load_json_file(AI_CACHE_FILE,{}); old_inventory=set(load_json_file(INVENTORY_FILE,[])); baseline=not INVENTORY_FILE.exists()
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
 for ri,root in enumerate(rr,1):
  set_progress('统计目录内容',ri,len(rr))
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
 set_progress('保存扫描结果')
 save_json_file(INVENTORY_FILE,[item_fingerprint(x) for x in out])
 data={'generatedAt':datetime.now().isoformat(timespec='seconds'),'items':out,'roots':[str(x) for x in rr],'errors':errors,'version':APP_VERSION}
 save_json_file(SNAPSHOT_FILE,data)
 with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
 return data

def allowed(p,root_list=None):
 try:
  resolved=p.resolve()
  for root in (root_list if root_list is not None else roots()):
   try:
    rel=resolved.relative_to(root.resolve())
    if len(rel.parts) in (1,2): return True
   except (ValueError,OSError): pass
  return False
 except OSError: return False

def recycle(paths):
 base=roots()
 safe=[str(Path(x).resolve()) for x in paths if allowed(Path(x),base) and Path(x).exists()]
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
 d.mkdir(parents=True,exist_ok=True); done=[]; failed=[]; base=roots()
 for x in paths:
  p=Path(x)
  try:
   if not allowed(p,base) or not p.exists(): failed.append({'path':str(p),'error':'不在扫描范围内或已不存在'}); continue
   target=d/p.name
   if target.exists(): failed.append({'path':str(p),'error':'目标已存在，跳过'}); continue
   shutil.move(str(p),str(target)); done.append({'from':str(p),'to':str(target)})
  except OSError as e: failed.append({'path':str(p),'error':str(e)})
 return {'done':done,'failed':failed}

class H(SimpleHTTPRequestHandler):
 def translate_path(self,path):
  rel=urllib.parse.urlparse(path).path.lstrip('/') or 'index.html'
  try: target=(APP/rel).resolve(); target.relative_to(APP.resolve())
  except (ValueError,OSError): return str(APP/'index.html')
  return str(target)
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
