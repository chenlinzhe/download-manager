import base64, ctypes, json, os, re, shutil, subprocess, tarfile, threading, time, urllib.parse, uuid, zipfile
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

APP=Path(__file__).resolve().parent; CACHE={}; LOCK=threading.Lock()
if getattr(__import__('sys'),'frozen',False):
 APP=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'DownloadPackageManager'
 APP.mkdir(parents=True,exist_ok=True)
LABELS_FILE=APP/'user_labels.json'
SETTINGS_FILE=APP/'settings.json'; AI_CACHE_FILE=APP/'ai_descriptions.json'; INVENTORY_FILE=APP/'inventory.json'; COLLECTION_CACHE_FILE=APP/'collection_classifications.json'; MANUAL_ROOTS_FILE=APP/'manual_roots.json'; SNAPSHOT_FILE=APP/'inventory_snapshot.json'; COLLECTION_FAIL_FILE=APP/'collection_failures.json'; NOTES_FILE=APP/'user_notes.json'; IGNORE_FILE=APP/'ignore.json'; SCAN_TTL_DAYS=7
GROUPS_FILE=APP/'resource_groups.json'
AI_HIDDEN_FILE=APP/'ai_hidden.json'
MODELS_FILE=APP/'models.json'
APP_VERSION='3.3'
ENV_KEY_NAME='DEEPSEEK_API_KEY'
DEFAULT_MODEL='deepseek-flash'
MODEL_ALIASES={'deepseek-v4-flash':'deepseek-flash','deepseek-v4':'deepseek-flash'}  # 只纠正本应用自己用过的失效模型名
AI_FAIL_TTL=1800
SCAN_LOCK=threading.Lock()
PROGRESS={'phase':'','done':0,'total':0,'at':0.0}
def set_progress(phase,done=0,total=0):
 PROGRESS.update(phase=phase,done=done,total=total,at=time.time())
def scan_status(): return dict(PROGRESS)
def scan_ai_enabled():
 """扫描时是否让 AI 判断「一级目录是不是多个包的集合」。默认关闭：扫描纯本地、不联网、不花钱。"""
 try: return bool(load_json_file(SETTINGS_FILE,{}).get('scanAI'))
 except Exception: return False
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

def load_groups():
 """读取用户自建的资源标签：每个标签一个名字 + 一组目录。"""
 data=load_json_file(GROUPS_FILE,[])
 if not isinstance(data,list): return []
 out=[]
 for g in data:
  if not isinstance(g,dict): continue
  gid=' '.join(str(g.get('id') or '').split())
  name=' '.join(str(g.get('name') or '').split())[:24]
  if not gid or not name or gid=='download': continue
  rs=[]; seen=set()
  for raw in g.get('roots') or []:
   try: p=Path(raw)
   except (OSError,ValueError): continue
   key=str(p).lower()
   if key in seen: continue
   seen.add(key); rs.append(str(p))
  out.append({'id':gid,'name':name,'roots':rs})
 return out

def save_groups(rows):
 data=[{'id':g['id'],'name':g['name'],'roots':[str(x) for x in g.get('roots') or []]} for g in rows if g.get('id') and g.get('id')!='download']
 save_json_file(GROUPS_FILE,data)
 return data

def groups():
 """资源标签清单：第一项固定是内置的「下载包」（自动发现的下载目录 + 手工加的目录），其后是用户自建的标签。"""
 auto=[str(x) for x in roots()]
 out=[{'id':'download','name':'下载包','roots':auto,'builtin':True}]
 for g in load_groups():
  rs=[]
  for raw in g['roots']:
   try: p=Path(raw)
   except (OSError,ValueError): continue
   if p.is_dir(): rs.append(str(p))
  out.append({'id':g['id'],'name':g['name'],'roots':rs,'builtin':False})
 return out

def group_list():
 """标签清单 + 上次扫描结果里的条目数。给界面启动时先画标签条用，不触发扫描。"""
 counts={}
 snap=load_json_file(SNAPSHOT_FILE,None)
 rows=snap.get('items') if isinstance(snap,dict) and isinstance(snap.get('items'),list) else []
 for item in rows:
  if isinstance(item,dict):
   gid=str(item.get('group') or 'download'); counts[gid]=counts.get(gid,0)+1
 out=[]
 for g in groups():
  out.append({'id':g['id'],'name':g['name'],'roots':g['roots'],
              'count':counts.get(g['id'],0),'builtin':g.get('builtin',False)})
 return out

def all_roots():
 out=[]
 for g in groups():
  for raw in g['roots']:
   try: out.append(Path(raw))
   except (OSError,ValueError): pass
 return out

def add_group(name):
 """新建一个用户自定义的资源标签（例如「我的项目」）。"""
 text=' '.join(str(name or '').split())[:24]
 if not text: raise ValueError('标签名不能为空')
 for g in groups():
  if g['name'].lower()==text.lower(): raise ValueError('已经有叫「'+text+'」的标签了')
 data=load_groups()
 gid='g'+str(int(time.time()*1000))
 used={g['id'] for g in data}
 n=2
 while gid in used:
  gid='g'+str(int(time.time()*1000))+'-'+str(n); n+=1
 data.append({'id':gid,'name':text,'roots':[]})
 save_groups(data)
 return {'id':gid,'name':text,'roots':[]}

def rename_group(gid,name):
 """给用户自建的资源标签改名；内置的「下载包」不许改名。"""
 key=' '.join(str(gid or '').split())
 if not key: raise ValueError('缺少标签')
 if key=='download': raise ValueError('内置标签「下载包」不用改名')
 text=' '.join(str(name or '').split())[:24]
 if not text: raise ValueError('标签名不能为空')
 data=load_groups(); target=None
 for g in data:
  if g['id']==key: target=g
  elif g['name'].lower()==text.lower(): raise ValueError('已经有叫「'+text+'」的标签了')
 if target is None: raise ValueError('找不到这个标签')
 target['name']=text
 save_groups(data)
 return {'id':key,'name':text,'roots':target['roots']}

def add_manual_roots(paths,group=None):
 """一次把多个目录加进同一个资源标签：重复的自动跳过，坏路径单独报错，其余照常加进去。"""
 gid=' '.join(str(group or '').split()) or 'download'
 rows=load_groups(); target=None
 for g in rows:
  if g['id']==gid: target=g
 if gid!='download' and target is None: raise ValueError('找不到这个标签：'+gid)
 gname='下载包'
 if target is not None: gname=target['name']
 owner={}
 for g in groups():
  for raw in g['roots']:
   try: owner.setdefault(str(Path(raw)).lower(),g['name'])
   except (OSError,ValueError): pass
 mine=[]
 if gid=='download':
  for raw in load_json_file(MANUAL_ROOTS_FILE,[]):
   try: mine.append(str(Path(raw).resolve()))
   except (OSError,ValueError): pass
 else:
  mine=list(target['roots'])
 added=[]; skipped=[]; failed=[]; seen=set()
 for raw in paths or []:
  try: p=Path(str(raw)).resolve()
  except (OSError,ValueError):
   failed.append({'path':str(raw),'error':'路径无效'}); continue
  key=str(p).lower()
  if not p.is_dir():
   failed.append({'path':str(p),'error':'不是有效目录'}); continue
  if key in seen:
   skipped.append({'path':str(p),'reason':'同一个目录选了两次'}); continue
  other=owner.get(key)
  if other:
   skipped.append({'path':str(p),'reason':('已经在这个标签里了' if other==gname else '已经在「'+other+'」里了')}); continue
  seen.add(key); added.append(str(p))
 if added:
  if gid=='download':
   out=list(mine); low={x.lower() for x in out}
   for x in added:
    if x.lower() not in low: low.add(x.lower()); out.append(x)
   save_json_file(MANUAL_ROOTS_FILE,out)
  else:
   target['roots'].extend(added); save_groups(rows)
 return {'group':gid,'groupName':gname,'added':added,'skipped':skipped,'failed':failed}

def add_manual_root(path,group=None):
 """把目录加到某个资源标签下；默认加到内置的「下载包」。"""
 r=add_manual_roots([path],group)
 if r['failed']:
  err=r['failed'][0].get('error') or '添加失败'
  raise ValueError('所选路径不是有效目录' if err=='不是有效目录' else err)
 if r['added']: return r['added'][0]
 if r['skipped']: return r['skipped'][0]['path']
 try: return str(Path(str(path)).resolve())
 except (OSError,ValueError): return str(path)

def open_path(path):
 p=Path(path)
 if not p.exists(): raise FileNotFoundError('项目已不存在：'+str(p))
 if p.is_dir(): os.startfile(str(p))
 else: subprocess.Popen(['explorer.exe','/select,',str(p)])
 return str(p)

def _llm_error(e, key='', model='', label='DeepSeek'):
 """把 AI 调用异常翻译成用户能直接看懂的一句话。"""
 import urllib.error
 label=str(label or '').strip() or 'DeepSeek'
 if isinstance(e,urllib.error.HTTPError):
  try: body=e.read().decode('utf-8','ignore')
  except Exception: body=''
  text=body
  try:
   parsed=json.loads(body); text=str((parsed.get('error') or {}).get('message') or body)
  except Exception: pass
  if e.code==401:
   who=('，本次发送的 Key 尾号 '+key_tail(key)+'、共 %d 位'%len(key)) if key else ''
   fmt=key_format_problem(key)
   hint=(fmt+'。请到服务商控制台重新复制 Key（DeepSeek 的形如 sk- 开头共 35 位）后填入「模型设置」') if fmt else '请打开「设置 → 模型设置」重新填写 Key，再点「测试连通」确认'
   return label+' 认为 API Key 无效或已失效（HTTP 401）'+who+'：'+hint
  if e.code==402: return label+' 账户余额不足（HTTP 402），请充值后再试'
  if e.code==403: return label+' 拒绝访问（HTTP 403）：'+text[:120]
  if e.code==404: return label+' 接口地址或模型不存在（HTTP 404）：%s（当前用的模型：%s，请到「模型设置」点「测试连通」确认地址与型号）'%(text[:120],model or '未设置')
  if e.code==429: return label+' 触发限流（HTTP 429），请稍后再试'
  if e.code>=500: return label+' 服务暂时不可用（HTTP %d），请稍后再试'%e.code
  return label+' 返回错误（HTTP %d）：%s'%(e.code,text[:150])
 if isinstance(e,(urllib.error.URLError,TimeoutError,OSError)):
  return '连不上 %s：%s（请检查网络、代理或接口地址后重试）'%(label,str(getattr(e,'reason',e))[:140])
 return 'AI 调用失败：'+str(e)[:150]

_VEC={'fp':None,'idf':None,'docs':None}
def _search_text(item):
 # V2.8：你动过这一格（改写 / 删掉 AI 那句）之后，AI 原话就不再算这一格的内容，搜索也不该再命中它
 summary='' if item.get('aiHidden') else (item.get('aiDescription') or {}).get('summary','')
 return ' '.join([item.get('name',''),item.get('displayName',''),item.get('path',''),item.get('kind',''),summary,item.get('recommendation',''),item.get('note') or '']).lower()
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
 profile=default_model_profile()
 if not model_api_key(profile)[0]: raise ValueError('尚未配置 DeepSeek API Key')
 with LOCK: items=list(CACHE.get('items',[]))
 items=_with_notes({'items':items}).get('items',items)   # 带上 note / aiHidden：你删掉 AI 那句的格子不该再按 AI 原话搜到
 texts=[_search_text(x) for x in items]
 terms=split_query_terms(query)
 def call_llm(prompt):
  out=llm_call([{'role':'user','content':prompt}],profile,timeout=30,temperature=0,json_mode=True)
  content=str(out.get('text') or '').strip()
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
   info='' if items[i].get('aiHidden') else (items[i].get('aiDescription') or {}).get('summary','')
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

# 统计大小 / 文件数时跳过的目录（依赖、缓存、版本库）。这些不是下载内容本身，
# 但动辄几十万个文件，走进去会让扫描慢上几分钟，所以只算一个目录、不进去数。
WALK_SKIP=frozenset('''node_modules __pycache__ .git .svn .hg .venv venv .tox .mypy_cache
.pytest_cache site-packages .next .nuxt .cache .gradle .m2 .pnpm-store .yarn .parcel-cache
.turbo .svelte-kit .angular bower_components jspm_packages .eggs .bundle .cargo .npm .nuget'''.split())
HINT_RE=re.compile(r'crack|keygen|注册机|破解|无限试用|激活工具|serial',re.I)

def summary(p):
 """统计一个条目的大小、文件数、目录数与最新时间。用 os.scandir（比 os.walk+Path.stat 快
 一个数量级），并跳过依赖/缓存目录；跳过目录仍计入目录数，只是不进去逐个文件数。"""
 size=files=dirs=err=0; newest=0.0; hints=[]
 try: st=os.stat(p)
 except OSError: raise
 if not os.path.isdir(p):
  return st.st_size,1,0,st.st_mtime,[],0
 stack=[p]
 while stack:
  base=stack.pop()
  try: it=os.scandir(base)
  except OSError: err+=1; continue
  with it:
   for e in it:
    try:
     if e.is_dir(follow_symlinks=False):
      dirs+=1
      if e.name.lower() in WALK_SKIP: continue
      stack.append(e.path); continue
     s=e.stat(follow_symlinks=False)
    except OSError: err+=1; continue
    size+=s.st_size; files+=1
    if s.st_mtime>newest: newest=s.st_mtime
    if len(hints)<6 and HINT_RE.search(e.name): hints.append(e.name)
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

def key_tail(key):
 """Key 尾号，用于在界面和报错里指认具体用的是哪一把 Key（不泄露完整 Key）。"""
 k=str(key or '')
 return k[-4:] if len(k)>=4 else ('' if not k else k)

def key_format_problem(key):
 """检查 Key 像不像 DeepSeek Key；正常返回空串，异常返回中文说明。"""
 import re as _re
 k=str(key or '').strip()
 if not k: return ''
 if _re.fullmatch(r'sk-[0-9A-Za-z]{32}',k): return ''
 if _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',k):
  return '这串内容是一个 UUID（通用唯一标识符），不是 DeepSeek API Key，多半是粘贴错了或被浏览器自动填充覆盖'
 if not k.startswith('sk-'):
  return '这串内容不以 sk- 开头，不是 DeepSeek API Key 的格式'
 return '长度是 %d 位，而 DeepSeek Key 通常是 sk- 开头共 35 位'%len(k)

def env_api_key():
 """读本机环境变量里的 Key（推荐存放位置：不落盘、不进 Git）。"""
 return str(os.environ.get(ENV_KEY_NAME) or '').strip()

def set_user_env_key(value):
 """把 Key 写进当前用户的 Windows 环境变量（HKCU\Environment）并同步当前进程。"""
 import winreg
 val=str(value or '').strip()
 try:
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as h:
   if val: winreg.SetValueEx(h,ENV_KEY_NAME,0,winreg.REG_SZ,val)
   else:
    try: winreg.DeleteValue(h,ENV_KEY_NAME)
    except FileNotFoundError: pass
 except OSError:
  return False
 if val: os.environ[ENV_KEY_NAME]=val
 else: os.environ.pop(ENV_KEY_NAME,None)
 try:  # 广播设置变更，让新开的进程/资源管理器也能读到
  res=ctypes.c_ulong()
  ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x001A,0,ctypes.c_wchar_p('Environment'),0x0002,3000,ctypes.byref(res))
 except Exception: pass
 return True

def clear_user_env_key(): return set_user_env_key('')

# ---------- V3.0：文字模型中心（多模型配置；模型列表与「当前默认」分开存，只用稳定 ID 关联） ----------
MODEL_LIST_VERSION=1
DEFAULT_PROFILE_ID='m_default'
CLIENT_TYPES=[
 {'id':'openai-chat','name':'OpenAI Chat','path':'/chat/completions','hint':'最通用：DeepSeek、通义千问、Kimi、硅基流动等 OpenAI 兼容接口都选这个'},
 {'id':'openai-responses','name':'OpenAI Responses','path':'/responses','hint':'OpenAI 新版 Responses 接口（input / output_text）'},
 {'id':'anthropic-messages','name':'Anthropic Messages','path':'/messages','hint':'Claude 官方接口，用 x-api-key 与 anthropic-version 鉴权'},
]
CLIENT_TYPE_IDS=[t['id'] for t in CLIENT_TYPES]
MODEL_CATALOG=[
 {'id':'deepseek','name':'DeepSeek','baseUrl':'https://api.deepseek.com','clientType':'openai-chat',
  'models':[{'id':'deepseek-flash','name':'DeepSeek Flash（快、便宜）'},{'id':'deepseek-chat','name':'DeepSeek Chat'}]},
 {'id':'openai','name':'OpenAI','baseUrl':'https://api.openai.com/v1','clientType':'openai-chat',
  'models':[{'id':'gpt-4o-mini','name':'GPT-4o mini'},{'id':'gpt-4o','name':'GPT-4o'}]},
 {'id':'anthropic','name':'Anthropic（Claude）','baseUrl':'https://api.anthropic.com/v1','clientType':'anthropic-messages',
  'models':[{'id':'claude-sonnet-4-5','name':'Claude Sonnet 4.5'},{'id':'claude-haiku-4-5','name':'Claude Haiku 4.5'}]},
 {'id':'moonshot','name':'月之暗面 Kimi','baseUrl':'https://api.moonshot.cn/v1','clientType':'openai-chat',
  'models':[{'id':'kimi-k2-0905-preview','name':'Kimi K2'},{'id':'moonshot-v1-8k','name':'Moonshot v1 8K'}]},
 {'id':'zhipu','name':'智谱 GLM','baseUrl':'https://open.bigmodel.cn/api/paas/v4','clientType':'openai-chat',
  'models':[{'id':'glm-4-flash','name':'GLM-4 Flash'},{'id':'glm-4-plus','name':'GLM-4 Plus'}]},
 {'id':'qwen','name':'阿里通义千问','baseUrl':'https://dashscope.aliyuncs.com/compatible-mode/v1','clientType':'openai-chat',
  'models':[{'id':'qwen-plus','name':'Qwen Plus'},{'id':'qwen-turbo','name':'Qwen Turbo'}]},
 {'id':'siliconflow','name':'硅基流动','baseUrl':'https://api.siliconflow.cn/v1','clientType':'openai-chat',
  'models':[{'id':'Qwen/Qwen3-8B','name':'Qwen3 8B'}]},
 {'id':'openrouter','name':'OpenRouter（一个 Key 用很多家模型）','baseUrl':'https://openrouter.ai/api/v1','clientType':'openai-chat',
  'models':[{'id':'openrouter/auto','name':'Auto（自动挑一个可用模型）'},
            {'id':'deepseek/deepseek-chat','name':'DeepSeek Chat（走 OpenRouter）'}]},
 {'id':'ollama','name':'本地 Ollama','baseUrl':'http://127.0.0.1:11434/v1','clientType':'openai-chat',
  'models':[{'id':'qwen2.5:7b','name':'Qwen2.5 7B（本机）'}]},
 {'id':'custom','name':'自定义（OpenAI 兼容）','baseUrl':'','clientType':'openai-chat','models':[]},
]
_BASE_HINTS=[('openrouter','openrouter'),('deepseek','deepseek'),('openai.com','openai'),('anthropic','anthropic'),('moonshot','moonshot'),('bigmodel','zhipu'),('dashscope','qwen'),('siliconflow','siliconflow'),('11434','ollama')]

def _now_iso(): return datetime.now().isoformat(timespec='seconds')
def _new_model_id(): return 'm_'+uuid.uuid4().hex[:10]
def _catalog_provider(provider_id):
 for p in MODEL_CATALOG:
  if p['id']==provider_id: return p
 return None
def _provider_of_base(base):
 low=str(base or '').lower()
 for key,pid in _BASE_HINTS:
  if key in low: return pid
 return 'custom'

def _normalize_profile(raw):
 """把一个模型配置补齐成完整快照：**只填空值**，绝不覆盖用户已经填过/改过的型号、名称、地址、接口类型。"""
 raw=dict(raw or {})
 pid=str(raw.get('id') or '').strip() or _new_model_id()
 base=str(raw.get('baseUrl') or '').strip().rstrip('/')
 provider_id=str(raw.get('providerId') or '').strip() or _provider_of_base(base)
 preset=_catalog_provider(provider_id)
 if preset is None:
  provider_id='custom'; preset=_catalog_provider('custom')
 preset=preset or {}
 model=str(raw.get('model') or '').strip()
 if not model:
  models=preset.get('models') or []
  model=str(models[0]['id']) if models else ''
 if provider_id=='deepseek': model=MODEL_ALIASES.get(model,model)  # 只纠正本应用自己用过的失效 DeepSeek 型号名
 if not base: base=str(preset.get('baseUrl') or '').strip().rstrip('/')
 client=str(raw.get('clientType') or '').strip()
 if client not in CLIENT_TYPE_IDS: client=str(preset.get('clientType') or 'openai-chat')
 if client not in CLIENT_TYPE_IDS: client='openai-chat'
 name=str(raw.get('name') or '').strip()
 if not name: name=((str(preset.get('name') or '未命名服务商')+' · '+model) if model else str(preset.get('name') or '未命名模型'))
 profile={'id':pid,'providerId':provider_id,'providerName':str(raw.get('providerName') or preset.get('name') or provider_id).strip(),
  'name':name,'baseUrl':base,'model':model,'clientType':client,
  'createdAt':str(raw.get('createdAt') or '') or _now_iso(),'updatedAt':str(raw.get('updatedAt') or '') or _now_iso()}
 enc=str(raw.get('apiKeyEnc') or '').strip()
 if enc: profile['apiKeyEnc']=enc
 return profile

def _legacy_profile():
 """老版本只在一个 settings.json 里放 baseUrl/model：把它派生成一个默认模型（只在内存里，不写盘）。"""
 cfg=load_json_file(SETTINGS_FILE,{})
 base=str(cfg.get('baseUrl') or 'https://api.deepseek.com').strip() or 'https://api.deepseek.com'
 return {'id':DEFAULT_PROFILE_ID,'providerId':_provider_of_base(base),'name':'默认模型',
  'baseUrl':base,'model':str(cfg.get('model') or DEFAULT_MODEL),
  'clientType':str(cfg.get('clientType') or 'openai-chat')}

def load_models():
 """读模型配置。列表与「当前默认模型」分开存，只用稳定 ID 关联；models.json 不存在时按老配置派生（不写盘）。"""
 raw=load_json_file(MODELS_FILE,None)
 if isinstance(raw,dict) and isinstance(raw.get('profiles'),list):
  profiles=[]
  for item in raw['profiles']:
   if isinstance(item,dict) and str(item.get('id') or '').strip(): profiles.append(_normalize_profile(item))
  if not profiles: profiles=[_normalize_profile(_legacy_profile())]
  default_id=str(raw.get('defaultId') or '').strip()
  if not any(p['id']==default_id for p in profiles): default_id=profiles[0]['id']
  return {'version':MODEL_LIST_VERSION,'defaultId':default_id,'profiles':profiles,'source':'file'}
 return {'version':MODEL_LIST_VERSION,'defaultId':DEFAULT_PROFILE_ID,'profiles':[_normalize_profile(_legacy_profile())],'source':'legacy'}

def default_model_profile():
 data=load_models()
 for p in data['profiles']:
  if p['id']==data['defaultId']: return p
 return data['profiles'][0] if data['profiles'] else _normalize_profile(_legacy_profile())

def model_api_key(profile):
 """这个模型该用哪把 Key：先用它自己存的；默认模型没有自己的 Key 时回退本机环境变量 / settings.json 的 DPAPI 备份。"""
 profile=dict(profile or {})
 own=unprotect_key(profile.get('apiKeyEnc')) or str(profile.get('apiKey') or '').strip()
 if own: return own,'profile'
 if str(profile.get('id') or '')==DEFAULT_PROFILE_ID:
  env=env_api_key()
  if env: return env,'env'
  legacy=load_json_file(SETTINGS_FILE,{})
  file_key=unprotect_key(legacy.get('apiKeyEnc')) or str(legacy.get('apiKey') or '')
  if file_key: return file_key,'file'
 return '',''

def _preset_suggestions(profiles):
 """还没配过的服务商：按预置给一张空卡片，用户只需要粘一把 Key（地址、型号已经填好）。
   这些卡片只在内存里生成，不是 models.json 的内容，也不写盘；保存之后对应服务商的卡片自动消失。"""
 covered=set(str(p.get('providerId') or '') for p in (profiles or []))
 out=[]
 for prov in MODEL_CATALOG:
  if prov['id'] in covered: continue
  models=prov.get('models') or []
  if not models: continue  # 「自定义」没有预置型号：想用就点「添加模型」自己填
  model=str(models[0]['id'])
  out.append({'id':'','preset':True,'providerId':prov['id'],'providerName':prov['name'],
   'name':str(prov['name'])+' · '+model,'baseUrl':str(prov.get('baseUrl') or ''),'model':model,
   'clientType':str(prov.get('clientType') or 'openai-chat'),
   'hasKey':False,'keyMasked':'','keyTail':'','keySource':'','configured':False,
   'isDefault':False,'canDelete':False})
 return out

def _public_profile(profile, default_id):
 key,source=model_api_key(profile)
 return {'id':profile['id'],'preset':False,'providerId':profile['providerId'],'providerName':profile['providerName'],
  'name':profile['name'],'baseUrl':profile['baseUrl'],'model':profile['model'],'clientType':profile['clientType'],
  'hasKey':bool(key),'keyMasked':('••••'+key_tail(key)) if key else '','keyTail':key_tail(key) if key else '',
  'keySource':source,'configured':bool(profile.get('baseUrl') and profile.get('model') and key),
  'isDefault':profile['id']==default_id,'canDelete':profile['id']!=default_id}

def models_state():
 data=load_models()
 default_id=data['defaultId']
 profiles=[_public_profile(p,default_id) for p in data['profiles']]
 suggested=_preset_suggestions(data['profiles'])
 default=profiles[0] if profiles else None
 for p in profiles:
  if p['isDefault']: default=p; break
 return {'profiles':profiles,'suggested':suggested,'defaultId':default['id'] if default else '','count':len(profiles),
  'savedCount':len(profiles),'suggestedCount':len(suggested),
  'migrated':data.get('source')!='file',
  'default':({'id':default['id'],'name':default['name'],'providerName':default['providerName'],'model':default['model'],
   'baseUrl':default['baseUrl'],'clientType':default['clientType'],'configured':default['configured'],'hasKey':default['hasKey'],
   'keyMasked':default['keyMasked']} if default else None)}

def model_catalog():
 """前端唯一的数据源：预置服务商 + 型号 + 三种接口类型。"""
 return {'providers':[{'id':p['id'],'name':p['name'],'baseUrl':p['baseUrl'],'clientType':p['clientType'],
   'models':[{'id':m['id'],'name':m['name']} for m in p['models']]} for p in MODEL_CATALOG],
  'clientTypes':[{'id':t['id'],'name':t['name'],'path':t['path'],'hint':t['hint']} for t in CLIENT_TYPES],
  'defaultProviderId':'deepseek'}

def _write_models(state):
 payload={'version':MODEL_LIST_VERSION,'defaultId':str(state.get('defaultId') or ''),
  'profiles':[dict(p) for p in (state.get('profiles') or [])]}
 for p in payload['profiles']:
  p.pop('apiKey',None); p.pop('apiKeyMasked',None); p.pop('apiKeyTail',None)  # 明文 Key 永不落盘
 if not payload['defaultId'] and payload['profiles']: payload['defaultId']=payload['profiles'][0]['id']
 save_json_file(MODELS_FILE,payload)
 return payload

def _require_user_save(payload):
 if str((payload or {}).get('intent') or '')!='user-confirmed':
  raise RuntimeError('模型配置只能由用户点击「保存」或「设置为默认」后写入（程序不能自己改模型配置）')

def save_model_profile(payload):
 """保存一个模型：只改这一个模型；makeDefault 时在同一次写入里「存最新字段 + 换默认」。"""
 data=dict(payload or {})
 _require_user_save(data)
 state=load_models()
 pid=str(data.get('id') or '').strip()
 existing=None
 for p in state['profiles']:
  if p['id']==pid: existing=p; break
 merged=dict(existing or {})
 merged['id']=pid or _new_model_id()
 for field in ('providerId','providerName','name','baseUrl','model','clientType'):
  if data.get(field) is not None: merged[field]=data.get(field)
 if existing: merged['createdAt']=existing.get('createdAt') or _now_iso()
 profile=_normalize_profile(merged)
 prev_enc=str((existing or {}).get('apiKeyEnc') or '')
 key=str(data.get('apiKey') or '').strip()
 if data.get('clearApiKey'): profile.pop('apiKeyEnc',None)
 elif key: profile['apiKeyEnc']=protect_key(key) or prev_enc
 elif prev_enc: profile['apiKeyEnc']=prev_enc
 if not str(profile.get('apiKeyEnc') or '').strip(): profile.pop('apiKeyEnc',None)
 profile['updatedAt']=_now_iso()
 if existing is None: state['profiles'].append(profile)
 else:
  for idx,p in enumerate(state['profiles']):
   if p['id']==profile['id']: state['profiles'][idx]=profile; break
 if data.get('makeDefault'): state['defaultId']=profile['id']
 _write_models(state)
 return models_state()

def delete_model_profile(payload):
 """删除一个模型；如果删的是当前默认，默认自动移交给剩下的第一个（不会把默认指向不存在的 ID）。"""
 data=dict(payload or {})
 _require_user_save(data)
 pid=str(data.get('id') or '').strip()
 state=load_models()
 rest=[p for p in state['profiles'] if p['id']!=pid]
 if len(rest)==len(state['profiles']): raise ValueError('要删除的模型不存在（可能已经被删掉了）')
 if not rest: raise ValueError('至少要保留一个模型，不能全删；如果想换，先添加一个再删')
 if state.get('defaultId')==pid: state['defaultId']=rest[0]['id']
 state['profiles']=rest
 _write_models(state)
 return models_state()

def _mirror_default_profile(base_url='', model=''):
 """settings.json 那份老配置被显式保存时，镜像进默认模型，避免两份配置各说各话。"""
 if not Path(MODELS_FILE).exists(): return
 state=load_models()
 if state.get('source')!='file': return
 for p in state['profiles']:
  if p['id']!=state['defaultId']: continue
  changed=False
  if base_url and p['baseUrl']!=base_url: p['baseUrl']=base_url; changed=True
  if model and p['model']!=model: p['model']=model; changed=True
  if changed:
   p['updatedAt']=_now_iso(); _write_models(state)
  return

def llm_endpoint(base_url, client_type='openai-chat'):
 """按接口类型拼出真正的请求地址。"""
 base=str(base_url or '').strip().rstrip('/')
 if not base: raise ValueError('还没填接口地址（Base URL）')
 ct=client_type if client_type in CLIENT_TYPE_IDS else 'openai-chat'
 if ct=='anthropic-messages': return base+'/messages'
 if ct=='openai-responses': return base+'/responses'
 return base+'/chat/completions'

def llm_request_spec(profile, messages, key='', temperature=None, max_tokens=None, json_mode=False):
 """接口适配层：同一份 messages 按三种接口类型翻译成各自的 url / headers / body。"""
 profile=dict(profile or {})
 ct=str(profile.get('clientType') or 'openai-chat')
 if ct not in CLIENT_TYPE_IDS: ct='openai-chat'
 model=str(profile.get('model') or '').strip()
 if not model: raise ValueError('还没填模型型号')
 msg=[dict(m) for m in (messages or [])]
 spec={'url':llm_endpoint(profile.get('baseUrl'),ct),'clientType':ct,'model':model,
  'headers':{'Content-Type':'application/json'},'body':{'model':model}}
 headers=spec['headers']; body=spec['body']
 if ct=='anthropic-messages':
  headers['x-api-key']=key; headers['anthropic-version']='2023-06-01'
  systems=[str(m.get('content') or '') for m in msg if m.get('role')=='system']
  body['messages']=[m for m in msg if m.get('role')!='system']
  if any(systems): body['system']='\n\n'.join(x for x in systems if x)
  body['max_tokens']=int(max_tokens or 512)
  if temperature is not None: body['temperature']=float(temperature)
 elif ct=='openai-responses':
  headers['Authorization']='Bearer '+key
  body['input']=msg
  if max_tokens: body['max_output_tokens']=int(max_tokens)
  if temperature is not None: body['temperature']=float(temperature)
  if json_mode: body['text']={'format':{'type':'json_object'}}
 else:
  headers['Authorization']='Bearer '+key
  body['messages']=msg
  if max_tokens: body['max_tokens']=int(max_tokens)
  if temperature is not None: body['temperature']=float(temperature)
  if json_mode: body['response_format']={'type':'json_object'}
 return spec

def _text_pieces(value):
 out=[]
 if isinstance(value,str): out.append(value)
 elif isinstance(value,list):
  for x in value: out.extend(_text_pieces(x))
 elif isinstance(value,dict):
  for k in ('text','content','value'):
   if k in value: out.extend(_text_pieces(value[k]))
 return out

def llm_extract_text(raw):
 """三种接口的返回长得都不一样，统一抠出模型说的话。"""
 data=raw if isinstance(raw,dict) else {}
 out=[]
 if isinstance(data.get('output_text'),str): out.append(data['output_text'])
 for ch in data.get('choices') or []:
  if isinstance(ch,dict):
   msg=ch.get('message') or ch.get('delta') or {}
   if isinstance(msg,dict): out.extend(_text_pieces(msg.get('content')))
 for item in data.get('output') or []:
  if isinstance(item,dict): out.extend(_text_pieces(item.get('content')))
 for item in data.get('content') or []:
  out.extend(_text_pieces(item))
 text=''.join(x for x in out if x).strip()
 if text: return text
 alt=[]  # 有些推理模型只给 reasoning_content
 for ch in data.get('choices') or []:
  if isinstance(ch,dict):
   msg=ch.get('message') or {}
   if isinstance(msg,dict): alt.append(str(msg.get('reasoning_content') or ''))
 return ''.join(alt).strip()

def llm_call(messages, profile=None, key='', timeout=30, temperature=None, max_tokens=None, json_mode=False):
 """所有文字模型请求唯一入口：统一适配、统一超时、统一错误结构。"""
 prof=dict(profile or {}) or default_model_profile()
 label=str(prof.get('providerName') or '文字模型').strip() or '文字模型'
 model=str(prof.get('model') or DEFAULT_MODEL)
 if not key: key,_source=model_api_key(prof)
 if not key: raise RuntimeError('还没有可用的 API Key：请打开「设置 → 模型设置」给「%s」填好 Key 并保存'%label)
 spec=llm_request_spec(prof,messages,key,temperature,max_tokens,json_mode)
 import urllib.request
 req=urllib.request.Request(spec['url'],data=json.dumps(spec['body']).encode('utf-8'),headers=spec['headers'])
 t0=time.time()
 try: raw=urllib.request.urlopen(req,timeout=timeout).read().decode('utf-8','replace')
 except Exception as e: raise RuntimeError(_llm_error(e,key,model,label=label))
 try: data=json.loads(raw)
 except ValueError: raise RuntimeError('%s 返回的内容不是 JSON：%s'%(label,str(raw)[:160]))
 return {'text':llm_extract_text(data),'raw':data,'model':str(data.get('model') or model),
  'latencyMs':int((time.time()-t0)*1000),'usage':data.get('usage') or {},
  'clientType':spec['clientType'],'endpoint':spec['url'],'providerName':label}

def verify_model_profile(payload):
 """测试连通：只用界面上的草稿字段，不写盘、不改默认；Key 留空时用这个模型已保存的 Key。"""
 data=dict(payload or {})
 pid=str(data.get('id') or '').strip()
 base=str(data.get('baseUrl') or '').strip().rstrip('/')
 model=str(data.get('model') or '').strip()
 ct=str(data.get('clientType') or 'openai-chat')
 if ct not in CLIENT_TYPE_IDS: ct='openai-chat'
 label=str(data.get('providerName') or '文字模型')
 key=str(data.get('apiKey') or '').strip(); source='draft' if key else ''
 if not key:
  for p in load_models()['profiles']:
   if p['id']==pid: key,source=model_api_key(p); break
 info={'model':model,'clientType':ct,'providerName':label,'keySource':source or 'none','keyTail':key_tail(key)}
 if not base: return dict(info,ok=False,error='还没填接口地址（Base URL）')
 if not model: return dict(info,ok=False,error='还没填模型型号')
 if not key: return dict(info,ok=False,error='还没有可用的 API Key：请填一个再点「测试连通」（也可以先「保存」再测）')
 profile={'id':pid,'providerName':label,'baseUrl':base,'model':model,'clientType':ct}
 t0=time.time()
 try:
  out=llm_call([{'role':'user','content':'只回复两个字：可以'}],profile,key=key,timeout=20,max_tokens=16)
  result={'ok':True,'latencyMs':out['latencyMs'],'reply':str(out.get('text') or '')[:60],'endpoint':out['endpoint']}
 except Exception as e:
  result={'ok':False,'error':str(e),'latencyMs':int((time.time()-t0)*1000)}
 result.update(info)
 if not result.get('endpoint'): result['endpoint']=llm_endpoint(base,ct)
 return result
def get_settings(reveal=False):
 cfg={'baseUrl':'https://api.deepseek.com','model':DEFAULT_MODEL,'autoAnalyze':False,'scanAI':False,'hideNotice':False,'destination':''}
 cfg.update(load_json_file(SETTINGS_FILE,{}))
 cfg.pop('autoSearch',None)  # 旧版的「自动 AI 分析」开关已废弃，现由 autoAnalyze 控制（默认关闭，不再每次启动都跑分析）
 cfg['model']=MODEL_ALIASES.get(str(cfg.get('model') or '').strip().strip(),str(cfg.get('model') or '').strip() or DEFAULT_MODEL)
 file_key=unprotect_key(cfg.get('apiKeyEnc')) or str(cfg.get('apiKey') or '')
 env_key=env_api_key()
 key=env_key or file_key
 profile=default_model_profile()  # V3.0：用哪个模型由「默认模型」决定，老的 settings.json 仍煶兼容读写
 if profile:
  cfg['baseUrl']=profile.get('baseUrl') or cfg['baseUrl']
  cfg['model']=profile.get('model') or cfg['model']
  cfg['clientType']=profile.get('clientType') or 'openai-chat'
  cfg['modelProfileId']=profile.get('id') or ''
  cfg['modelProfileName']=profile.get('name') or ''
  if not key: key=model_api_key(profile)[0]
 cfg['keyName']=ENV_KEY_NAME
 cfg['keySource']='env' if env_key else ('file' if file_key else ('profile' if key else ''))
 cfg['keyTail']=key_tail(key)
 cfg['keyFormatProblem']=key_format_problem(key)
 cfg['keyBackup']=bool(file_key)  # 本机是否留有 DPAPI 加密的备份（环境变量被改坏/清掉时能恢复）
 cfg['apiKeyBackupMasked']=('••••'+key_tail(file_key)) if file_key else ''
 if not reveal:
  cfg['apiKeyMasked']=('••••'+cfg['keyTail']) if key else ''; cfg['apiKey']=''
  return cfg
 cfg['apiKey']=key; return cfg

_DERIVED=('apiKey','apiKeyMasked','apiKeyEnc','keyName','keySource','keyTail','keyFormatProblem','keyStoredIn','keyWarning','keyBackup','apiKeyBackupMasked','clientType','modelProfileId','modelProfileName')

def save_settings(data):
 """保存设置。API Key 写进本机环境变量，同时在配置文件里留一份只有本机当前用户能解密的备份（DPAPI）。"""
 old=get_settings(True); key=str(data.get('apiKey','')).strip()
 prev_enc=str(load_json_file(SETTINGS_FILE,{}).get('apiKeyEnc') or '')
 existing=str(old.get('apiKey') or '')
 stored=old.get('keySource') or ''
 if data.get('clearApiKey'):
  clear_user_env_key(); stored=''
 elif key:
  stored='env' if set_user_env_key(key) else 'file'
 elif existing and stored=='file':
  stored='env' if set_user_env_key(existing) else 'file'  # 老版本存在文件里的 Key，顺手迁移进环境变量
 old['baseUrl']=str(data.get('baseUrl') or old['baseUrl']).strip().rstrip('/')
 old['model']=str(data.get('model') or old['model']).strip()
 old.pop('autoSearch',None)
 old['autoAnalyze']=bool(data.get('autoAnalyze',old.get('autoAnalyze',False)))
 old['scanAI']=bool(data.get('scanAI',old.get('scanAI',False)))
 old['destination']=str(data.get('destination') or old.get('destination') or '').strip()
 old['hideNotice']=bool(data.get('hideNotice',old.get('hideNotice',False)))  # 顶部提示条：用户点过 ✕ 就不再自动显示
 for name in _DERIVED: old.pop(name,None)
 backup=''  # 加密备份：只有本机当前用户能解开，明文永远不落盘
 if data.get('clearApiKey'): backup=''
 elif key: backup=protect_key(key) or prev_enc
 elif existing and stored=='file': backup=prev_enc
 if backup: old['apiKeyEnc']=backup
 else: old.pop('apiKeyEnc',None)
 if data.get('baseUrl') or data.get('model'): _mirror_default_profile(old.get('baseUrl') or '',old.get('model') or '')
 save_json_file(SETTINGS_FILE,old); out=get_settings(False)
 out['keyStoredIn']=stored
 out['keyWarning']=key_format_problem(key) if key else ''
 return out

def restore_key_backup():
 """把配置文件里的 DPAPI 备份重新写回用户环境变量：环境变量被清掉或被写坏时用这个兜底。"""
 raw=load_json_file(SETTINGS_FILE,{})
 key=unprotect_key(raw.get('apiKeyEnc')) or str(raw.get('apiKey') or '')
 if not key: raise ValueError('本机没有可用的 Key 备份，请重新填写一次 Key 并保存')
 if not set_user_env_key(key): raise RuntimeError('写不进用户环境变量（可能被权限或安全软件拦住），请手动填写 Key')
 return get_settings(False)
def test_connection(baseUrl=None, model=None, apiKey=None):
 import urllib.request, urllib.error, time
 cfg=get_settings(True)
 base=str(baseUrl or cfg.get('baseUrl') or 'https://api.deepseek.com').strip().rstrip('/')
 model=str(model or cfg.get('model','')).strip()
 key=str(apiKey or '').strip() or cfg.get('apiKey','')
 if not key: return {'ok':False,'error':'尚未配置 DeepSeek API Key，请先填写并保存'}
 tail=key_tail(key)
 probe={'keyTail':tail,'keyLength':len(key),'keySource':('input' if str(apiKey or '').strip() else (cfg.get('keySource') or ''))}
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
  out={'ok':True,'latencyMs':latency,'endpoint':base,'model':model,'availableModels':ms,'modelOk':model_ok}; out.update(probe); return out
 except urllib.error.HTTPError as e:
  code=e.code; msg=e.read().decode('utf-8','ignore')[:300]
  if code==401:
   fmt=key_format_problem(key)
   msg='DeepSeek 拒绝了这个 Key（HTTP 401）。本次发送的 Key 尾号 %s、共 %d 位'%(tail,len(key))
   msg+=(('，而且'+fmt+'。请到 DeepSeek 控制台重新复制 Key（形如 sk- 开头共 35 位）后填入并保存。') if fmt else '。请打开「模型设置」重新填写 Key 后重试。')
   out={'ok':False,'error':msg,'endpoint':base}; out.update(probe); return out
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

# ---------- V2.3：功能知识库（功能说明全文直传 LLM；总共一万多 token，不建向量库，装机不用多带任何东西） ----------
RES_DIR=Path(getattr(__import__('sys'),'_MEIPASS',Path(__file__).resolve().parent))
KB_LOCK=threading.Lock(); KB_CACHE={'key':'','data':None}
KB_SYSTEM=('你是「下载包管家」这款 Windows 小工具的使用帮助助手。下面【资料】里是这个软件的全部功能说明与 README。'
 '回答时只用资料里写明的事实，不要编造资料里没有的功能、不要让用户去装别的东西；资料里没写的就直接说「功能说明里没写」，'
 '并提示用户到「设置 → 功能说明」自己翻一下。回答用简体中文，先给结论，再给不超过 6 条要点；'
 '凡涉及点哪里，写成「设置 → 模型设置 → 保存」这种路径形式。不要输出 Markdown 标题、不要贴大段代码。')
def kb_guide_html(raw):
 """从 index.html 里取出 data-pane="guide" 那一整段（按 div 嵌套计数，不硬啃正则）。"""
 m=re.search(r'<div class="pane" data-pane="guide"',raw)
 if not m: return ''
 depth=1
 for t in re.finditer(r'<div\b|</div>',raw[m.start():]):
  depth += 1 if t.group(0)=='<div' else -1
  if depth==0: return raw[m.start():m.start()+t.end()]
 return raw[m.start():]
def kb_plain(h):
 """HTML → 纯文本：去标签、还原实体、压掉多余空白。"""
 import html as _html
 h=re.sub(r'<(script|style)\b.*?</\1>',' ',h,flags=re.S)
 h=re.sub(r'<br\s*/?>','\n',h)
 h=re.sub(r'</(p|li|h1|h2|h3|h4|div|tr)>','\n',h)
 h=re.sub(r'<[^>]+>','',h)
 h=_html.unescape(h)
 h=re.sub(r'[ \t\u00a0]+',' ',h)
 h=re.sub(r'\n{3,}','\n\n',h)
 return h.strip()
def kb_tokens(text):
 """粗略估算 token：中日韩字符按 1 个算，其它字符 1.8 个算 1 个（按 cl100k 实测校准，只用于界面展示）。"""
 cjk=sum(1 for ch in text if u'\u3400'<=ch<=u'\u9fff')
 return cjk+int((len(text)-cjk)/1.8)+1
def kb_text(refresh=False):
 """拼出知识库全文：应用内「功能说明」+ README。两个文件本来就随程序打包，不用另装、不用建索引。"""
 paths=[RES_DIR/'index.html',RES_DIR/'README.md']
 stamp='|'.join(('%s:%s'%(p.name,p.stat().st_mtime)) if p.exists() else (p.name+':-') for p in paths)
 with KB_LOCK:
  if not refresh and KB_CACHE['data'] is not None and KB_CACHE['key']==stamp: return KB_CACHE['data']
  parts=[]; sources=[]
  if paths[0].exists():
   try:
    body=kb_plain(kb_guide_html(paths[0].read_text(encoding='utf-8',errors='ignore')))
    if body: parts.append(u'【应用内「功能说明」全文】\n'+body); sources.append('index.html')
   except OSError: pass
  if paths[1].exists():
   try:
    body=paths[1].read_text(encoding='utf-8',errors='ignore').strip()
    if body: parts.append(u'【README】\n'+body); sources.append('README.md')
   except OSError: pass
  text=u'\n\n'.join(parts)
  data={'text':text,'chars':len(text),'tokens':kb_tokens(text),'sources':sources,'version':APP_VERSION}
  KB_CACHE['key']=stamp; KB_CACHE['data']=data
  return data
def ask_help(question):
 """功能问答：知识库全文放 system（固定前缀，好命中缓存），用户的问题单独发。"""
 import urllib.request, urllib.error
 q=str(question or '').strip()
 if not q: raise ValueError('请先输入想问的问题')
 q=q[:600]
 profile=default_model_profile()
 if not model_api_key(profile)[0]: raise ValueError(u'尚未配置 DeepSeek API Key，请到「设置 → 模型设置」填好并保存后再问')
 kb=kb_text()
 if not kb['text']: raise ValueError(u'没读到功能说明内容（打包时漏了 index.html / README.md）')
 messages=[{'role':'system','content':KB_SYSTEM+u'\n\n【资料】\n'+kb['text']},{'role':'user','content':q}]
 t0=time.time()
 out=llm_call(messages,profile,timeout=60,temperature=0.2,max_tokens=900)
 answer=str(out.get('text') or '').strip()
 usage=out.get('usage') or {}
 if not answer: raise RuntimeError(u'%s 这次没给出回答，请再问一次'%(profile.get('providerName') or u'模型'))
 return {'answer':answer,'question':q,'model':out.get('model') or profile.get('model'),'latencyMs':out.get('latencyMs') or int((time.time()-t0)*1000),
  'usage':{'prompt':usage.get('prompt_tokens',usage.get('input_tokens')),'completion':usage.get('completion_tokens',usage.get('output_tokens')),
   'cached':(usage.get('prompt_tokens_details') or {}).get('cached_tokens') or usage.get('cache_read_input_tokens')},
  'kb':{'chars':kb['chars'],'tokens':kb['tokens'],'sources':kb['sources'],'version':kb['version']}}

def item_fingerprint(item): return '|'.join([item['name'].lower(),str(item['size']),item['modified']])

ARCHIVE_KINDS={'.zip','.whl','.crx','.jar','.tar','.gz','.tgz','.bz2','.xz','.7z','.rar','.iso'}
def archive_entry_list(path,limit=24):
 """只读压缩包里的文件清单：不解压、不写磁盘，读不到就返回空列表。"""
 if not path: return []
 p=Path(path)
 try:
  if not p.is_file(): return []
 except OSError: return []
 suffix=p.suffix.lower(); names=[]
 try:
  if suffix in ('.zip','.whl','.crx','.jar') or zipfile.is_zipfile(str(p)):
   with zipfile.ZipFile(str(p)) as z:
    for info in z.infolist():
     if info.is_dir(): continue
     names.append(info.filename)
     if len(names)>=limit: break
  elif suffix in ('.tar','.gz','.tgz','.bz2','.xz'):
   with tarfile.open(str(p)) as t:
    for m in t:
     if not m.isfile(): continue
     names.append(m.name)
     if len(names)>=limit: break
  elif suffix in ARCHIVE_KINDS:
   # rar / 7z / iso：交给 Windows 自带的 tar（bsdtar 能读这几类压缩包的清单）
   flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
   out=subprocess.run(['tar','-tf',str(p)],capture_output=True,timeout=30,creationflags=flags)
   for line in (out.stdout or b'').decode('utf-8','replace').splitlines():
    line=line.strip()
    if not line or line.endswith('/') or line.endswith('\\'): continue
    names.append(line)
    if len(names)>=limit: break
 except Exception:
  return []
 cleaned=[]
 for n in names:
  n=str(n).replace('\\','/').strip()
  if not n: continue
  cleaned.append(n if len(n)<=60 else n[:57]+u'\u2026')
 return cleaned

def dir_entry_list(path,limit=60,depth=3):
 """只读目录里的内容清单（含子目录，最多 depth 层），留给「重做分析」时深挖用；读不到就返回空列表。"""
 if not path: return []
 p=Path(path)
 try:
  if not p.is_dir(): return []
 except OSError: return []
 names=[]
 def walk(d,prefix,level):
  if len(names)>=limit or level>depth: return
  try: entries=sorted(list(os.scandir(str(d))),key=lambda e:(not e.is_dir(follow_symlinks=False),e.name.lower()))
  except OSError: return
  for e in entries:
   if len(names)>=limit: return
   try: isdir=e.is_dir(follow_symlinks=False)
   except OSError: isdir=False
   names.append(prefix+e.name+(u'/' if isdir else u''))
   if isdir: walk(Path(e.path),prefix+e.name+u'/',level+1)
 walk(p,u'',1)
 return [n if len(n)<=60 else n[:57]+u'\u2026' for n in names]

def description_prompt(item,deep=False):
 prompt=('根据下载包名判断这是什么。只返回严格JSON：{"summary":"10至15个中文字的简短描述"}。'
         '必须给出最可能判断，不能回答无法确认或复述文件名。包名：%s')%item.get('name','')
 inside=archive_entry_list(item.get('path'),80 if deep else 24)
 if inside: prompt+='；压缩包里主要有这些文件：'+'、'.join(inside)
 elif deep:
  sub=dir_entry_list(item.get('path'),60)
  if sub: prompt+='；这个包里（含子目录）主要有：'+'、'.join(sub)
 if deep:
  # 用户已经标注过还是要求重做＝对上一次的说明不满意，让他往深里看子目录和内部结构
  prompt+=('；这一项用户看过并标注过，但对你这次的说明不满意，请你重新判断、往深处看：'
           '结合上面列出的子目录和文件清单、名称里的版本号与关键字，讲清它究竟是什么、做什么用、'
           '值得注意什么（安装包 / 驱动 / 数据集 / 源码 / 运行库等），10至20个中文字以内，不要复述文件名。')
 return prompt

def deepseek_description(item,deep=False):
 profile=default_model_profile()
 if not model_api_key(profile)[0]: raise ValueError('尚未配置 DeepSeek API Key，请打开「模型设置」填写。')
 prompt=description_prompt(item,deep)
 out=llm_call([{'role':'user','content':prompt}],profile,timeout=30,temperature=0.1,json_mode=True)
 try:
  content=str(out.get('text') or '').strip().strip(chr(96)).replace('json\n','',1)
  return json.loads(content)
 except ValueError as e: raise RuntimeError('%s 返回内容无法解析：%s'%(profile.get('providerName') or '模型',str(e)[:120]))

def enrich_items(paths, force=False, deep=False):
 wanted=set(paths); cache=load_json_file(AI_CACHE_FILE,{}); notes=load_notes(); hidden=load_ai_hidden(); skipped=0
 # Reuse the most recent scan. The old implementation rescanned every drive for
 # every package, which made the UI appear stuck.
 with LOCK: cached_items=list(CACHE.get('items',[]))
 data={'items':cached_items} if cached_items else scan()
 targets=[item for item in data['items'] if item['path'] in wanted]
 results={}; errors={}; pending=[]; fresh=[]
 for item in targets:
  fp=item_fingerprint(item)
  # V2.8：你动过这一格（写过自己的话，或把 AI 那句删干净）＝以你的为准，批量分析直接跳过，
  # 不花额度也不覆盖你的话；deep（单独确认过的重做）和 force（按住 Shift）是你明确要求，照做。
  if not force and not deep and (str(notes.get(item['path']) or '').strip() or item['path'] in hidden):
   skipped+=1; continue
  # force / deep：你明确要求重做，忽略缓存再问一遍 AI
  if fp in cache and not force and not deep: results[item['path']]=cache[fp]
  else: pending.append(item)
 model_name=default_model_profile().get('model') or DEFAULT_MODEL
 def ask(item):
  desc=deepseek_description(item,deep)
  desc={'summary':str(desc.get('summary','')).strip()[:30],
        'searchedAt':datetime.now().isoformat(timespec='seconds'),
        'model':model_name}
  return item,desc
 from concurrent.futures import ThreadPoolExecutor,as_completed
 # DeepSeek requests run concurrently, with an explicit maximum of 10.
 with ThreadPoolExecutor(max_workers=min(10,len(pending) or 1)) as pool:
  futures={pool.submit(ask,item):item for item in pending}
  for future in as_completed(futures):
   item=futures[future]
   try:
    _,desc=future.result(); cache[item_fingerprint(item)]=desc; results[item['path']]=desc
    fresh.append(item['path'])
   except Exception as e: errors[item['path']]=str(e)
 if pending: save_json_file(AI_CACHE_FILE,cache)
 if fresh:  # 重做成功：把你动过的记录去掉，新说明加到格子下面，你写的话一个字不动
  rest=load_ai_hidden()
  for path in fresh: rest.pop(path,None)
  save_ai_hidden(rest)
 return {'ok':not errors,'result':results,'errors':errors,'skipped':skipped,'deep':bool(deep),'fresh':fresh}

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
 profile=default_model_profile()
 if not model_api_key(profile)[0]: return {'isCollection':False,'reason':'未配置AI，保守地视为完整包'}
 prompt=('判断这个下载目录下的一级文件夹，是一个完整软件/资料包，还是用户用于归类多个相互独立下载包的集合目录。'
         '只有当其直接子项明显是多个可各自独立整理、移动或删除的下载包时才判为集合；安装目录中的exe、dll、资源目录不是集合。'
         '只返回严格JSON：{"isCollection":true或false,"reason":"15字内理由"}。'
         '目录名：%s；直接子项：%s')%(p.name,'、'.join(sample))
 out=llm_call([{'role':'user','content':prompt}],profile,timeout=30,temperature=0,json_mode=True)
 try:
  content=str(out.get('text') or '').strip().strip(chr(96)).replace('json\n','',1)
  result=json.loads(content)
 except ValueError as e: raise RuntimeError('%s 返回内容无法解析：%s'%(profile.get('providerName') or '模型',str(e)[:120]))
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
 """判断一级目录是不是「多个相互独立下载包的集合」。
 默认纯本地：先用零成本的 collection_prejudge，再用以前缓存下来的 AI 结论，都不产生新请求。
 只有设置里打开「扫描时用 AI 判断」才真的联网问 DeepSeek。"""
 cache=load_json_file(COLLECTION_CACHE_FILE,{}); fails=load_json_file(COLLECTION_FAIL_FILE,{}); use_ai=scan_ai_enabled()
 now=time.time(); folders=[p for p in children if p.is_dir()]; results={}; pending=[]
 for p in folders:
  hint=collection_prejudge(p)
  if hint is not None: results[str(p)]=hint; continue
  sig=collection_signature(p)
  if sig in cache: results[str(p)]=cache[sig]; continue
  if not use_ai:
   results[str(p)]={'isCollection':False,'reason':'没做 AI 判断，先当成一个整体','pending':True}; continue
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

def load_notes():
 try:
  data=json.loads(NOTES_FILE.read_text(encoding='utf-8'))
  return data if isinstance(data,dict) else {}
 except (OSError,json.JSONDecodeError): return {}

def load_ai_hidden():
 """你动过的那几格（改写或删掉 AI 说明）：记在名单里，AI 那句不再显示，重新扫描 / 批量分析也不会写回来。"""
 try:
  data=json.loads(AI_HIDDEN_FILE.read_text(encoding='utf-8'))
  return data if isinstance(data,dict) else {}
 except (OSError,json.JSONDecodeError): return {}

def save_ai_hidden(hidden):
 hidden=hidden if isinstance(hidden,dict) else {}
 tmp=AI_HIDDEN_FILE.with_suffix('.tmp')
 tmp.parent.mkdir(parents=True,exist_ok=True)
 tmp.write_text(json.dumps(hidden,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,AI_HIDDEN_FILE)
 return hidden

def fold_note(text):
 """把用户写的说明收成存下来的样子：换行保留（格子按多行原样显示），行内多余空白收成一个空格。"""
 raw=str(text or '').replace('\r\n','\n').replace('\r','\n')
 lines=[' '.join(line.split()) for line in raw.split('\n')]
 while lines and not lines[0]: lines.pop(0)
 while lines and not lines[-1]: lines.pop()
 return '\n'.join(lines)[:400]

def save_note(path, text, hide_ai=False):
 """保存你改过 / 补过的说明（按包路径存，最多 400 字，可以多行）。
 V2.8：只要你动过这一格，AI 那句就不算数了（记进 ai_hidden.json）——
 改写过＝这一格全是你的话；全删干净（hide_ai=True）＝连 AI 那句一起删掉、格子空着。
 这两种情况默认都不会再被批量 AI 分析写回；想让它再说一遍就单独分析这一项（或按住 Shift 点「AI 分析」），
 成功后会加回「AI：…」这一行，你写的一个字都不动。只有在你只留「AI：…」那一行时才恢复 AI。"""
 notes=load_notes(); hidden=load_ai_hidden(); key=str(path or '')
 if not key: raise ValueError('缺少包路径')
 note=fold_note(text)
 if note:
  # 你改写过这一格：AI 那句不再算数，这一格从此全是你的（也默认不再被 AI 分析）
  notes[key]=note; hidden[key]=datetime.now().isoformat(timespec='seconds')
 elif hide_ai:
  notes.pop(key,None); hidden[key]=datetime.now().isoformat(timespec='seconds')
 else:
  notes.pop(key,None); hidden.pop(key,None)
 tmp=NOTES_FILE.with_suffix('.tmp')
 tmp.parent.mkdir(parents=True,exist_ok=True)
 tmp.write_text(json.dumps(notes,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,NOTES_FILE)
 save_ai_hidden(hidden)
 return {'path':key,'note':note,'aiHidden':key in hidden}

def _with_notes(data):
 if not isinstance(data,dict) or not isinstance(data.get('items'),list): return data
 notes=load_notes(); hidden=load_ai_hidden()
 for item in data['items']:
  if isinstance(item,dict):
   item['note']=notes.get(str(item.get('path')),'')
   item['aiHidden']=str(item.get('path')) in hidden
 return data

def ai_skip_list():
 """V2.9：设置 → 忽略名单 →「AI 分析」标签要看的名单。
 被批量 AI 分析跳过的那几格有两种来源：你改写成了自己的话（user_notes.json 里有你的字），
 或者你把 AI 那句删干净了（ai_hidden.json 里有记录）。这里把它们一起列出来，
 方便你想让 AI 再说一遍时逐个点「让 AI 重新分析」。"""
 notes=load_notes(); hidden=load_ai_hidden(); names={}
 snap=load_json_file(SNAPSHOT_FILE,None)
 if isinstance(snap,dict) and isinstance(snap.get('items'),list):
  for item in snap['items']:
   if isinstance(item,dict):
    n=' '.join(str(item.get('displayName') or item.get('name') or '').split())
    if n: names[str(item.get('path') or '')]=n
 out=[]
 for raw in set(notes)|set(hidden):
  key=str(raw or '')
  if not key: continue
  note=str(notes.get(key) or '')
  name=names.get(key) or (re.split(r'[\\/]',key.rstrip('\\/'))[-1] or key)
  out.append({'path':key,'name':name,'note':note[:400],'hidden':key in hidden,
              'when':str(hidden.get(key) or ''),'reason':'改写' if note else '删除'})
 out.sort(key=lambda r:(0 if r['reason']=='改写' else 1,r['name'].lower()))
 return out

def load_ignore():
 """读取忽略名单。按项目名称忽略（同时记录路径，便于在界面上展示）。"""
 data=load_json_file(IGNORE_FILE,{})
 names=data.get('names') if isinstance(data,dict) else None
 if not isinstance(names,list): return []
 out=[]
 for r in names:
  if isinstance(r,dict):
   name=' '.join(str(r.get('name') or '').split())
   if name: out.append({'name':name,'path':str(r.get('path') or ''),'addedAt':str(r.get('addedAt') or '')})
  elif isinstance(r,str) and r.strip(): out.append({'name':r.strip(),'path':'','addedAt':''})
 return out

def save_ignore(records):
 recs=[]
 for r in records or []:
  raw=(r or {}).get('name') if isinstance(r,dict) else r
  name=' '.join(str(raw or '').split())
  if not name: continue
  recs.append({'name':name,
               'path':str(r.get('path') or '') if isinstance(r,dict) else '',
               'addedAt':str(r.get('addedAt') or '') if isinstance(r,dict) else ''})
 tmp=IGNORE_FILE.with_suffix('.tmp')
 tmp.parent.mkdir(parents=True,exist_ok=True)
 tmp.write_text(json.dumps({'names':recs},ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,IGNORE_FILE)
 return recs

def add_ignore(name, path=''):
 """把一个项目名称加入忽略名单；以后扫描会自动跳过同名项目。"""
 name=' '.join(str(name or '').split())
 if not name: raise ValueError('缺少项目名称')
 recs=[r for r in load_ignore() if r['name'].lower()!=name.lower()]
 recs.append({'name':name,'path':str(path or ''),'addedAt':datetime.now().isoformat(timespec='seconds')})
 save_ignore(recs)
 return {'name':name,'total':len(recs)}

def remove_ignore(name):
 target=' '.join(str(name or '').split()).lower()
 recs=load_ignore(); kept=[r for r in recs if r['name'].lower()!=target]
 if len(kept)==len(recs): return {'name':name,'removed':False,'total':len(recs)}
 save_ignore(kept)
 return {'name':name,'removed':True,'total':len(kept)}

def ignore_sets():
 """返回 (忽略的名称集合, 忽略的路径集合)，都转小写便于比较。"""
 names=set(); paths=set()
 for r in load_ignore():
  n=str(r.get('name') or '').strip().lower()
  if n: names.add(n)
  p=str(r.get('path') or '').strip().lower()
  if p: paths.add(p)
 return names, paths

def is_ignored(p, names=None, paths=None):
 """这个项目是否在忽略名单里（按名称或路径）。"""
 if names is None or paths is None: names,paths=ignore_sets()
 if not names and not paths: return False
 try:
  if p.name.strip().lower() in names: return True
 except (AttributeError,OSError): return False
 try: return str(p).strip().lower() in paths
 except OSError: return False

def _drop_ignored(data):
 """把忽略名单里的项目从结果中过滤掉（含沿用的旧快照）。"""
 if not isinstance(data,dict) or not isinstance(data.get('items'),list): return data
 names,paths=ignore_sets()
 if not names and not paths: return data
 kept=[]
 for item in data['items']:
  if isinstance(item,dict):
   name=str(item.get('name') or '').strip().lower()
   if name and name in names: continue
   if str(item.get('path') or '').strip().lower() in paths: continue
  kept.append(item)
 if len(kept)!=len(data['items']): data['items']=kept
 return data

def _finalize(data):
 """扫描结果统一出口：附加资源标签 + 备注 + 过滤忽略名单。"""
 return _with_groups(_drop_ignored(_with_notes(data)))

def _with_groups(data):
 """在扫描结果上附加资源标签清单（每个标签带目录与项目数），并给每个条目补上所属标签。"""
 if not isinstance(data,dict): return data
 rows=data.get('items') if isinstance(data.get('items'),list) else []
 counts={}
 for item in rows:
  if not isinstance(item,dict): continue
  gid=str(item.get('group') or 'download')
  counts[gid]=counts.get(gid,0)+1
 names={}; summary=[]
 for g in groups():
  names[g['id']]=g['name']
  summary.append({'id':g['id'],'name':g['name'],'roots':g['roots'],
                  'count':counts.get(g['id'],0),'builtin':g.get('builtin',False)})
 for item in rows:
  if not isinstance(item,dict): continue
  gid=str(item.get('group') or 'download')
  item['group']=gid
  item['groupName']=names.get(gid,'')
 data['groups']=summary
 return data

def _manual_keep_fields(manual):
 """「标为保留」在条目上体现出来的字段（扫描与单条重算共用）。"""
 when=(manual or {}).get('markedAt') or '此前'
 return {'recommendation':'保留（手工）','score':100,'manualKeep':True,
         'reasons':['你在 '+when+' 手工标记为保留；重新扫描不会覆盖']}

def _patch_cached_items(fields_list):
 """把重算后的字段同步进内存缓存与快照，避免旧快照把新结果又盖回去。"""
 if not fields_list: return
 by_path={str(x.get('path') or '').lower():x for x in fields_list if x}
 def merge(it,f):
  # 取消保留时新字段里没有 manualKeep，必须显式删掉旧值
  if not f.get('manualKeep'): it.pop('manualKeep',None)
  it.update(f)
 with LOCK:
  for it in CACHE.get('items') or []:
   f=by_path.get(str(it.get('path') or '').lower())
   if f: merge(it,f)
 snap=load_json_file(SNAPSHOT_FILE,None)
 if isinstance(snap,dict) and isinstance(snap.get('items'),list):
  changed=False
  for it in snap['items']:
   f=by_path.get(str(it.get('path') or '').lower())
   if f: merge(it,f); changed=True
  if changed: save_json_file(SNAPSHOT_FILE,snap)

def reanalyze(path):
 """按当前磁盘状态重算单个项目的建议（取消保留后立刻刷新，不必全盘重扫）。"""
 p=Path(path)
 if not allowed(p): raise ValueError('不在扫描范围内')
 if not p.exists(): raise ValueError('项目已不存在，可能已被移动或删除')
 size,files,dirs,newest,hints,errs=summary(p); newest=newest or p.stat().st_mtime
 fields=analyze(p,size,files,newest,hints)
 manual=load_labels().get(str(p.resolve()).lower())
 if manual and manual.get('label')=='keep': fields.update(_manual_keep_fields(manual))
 fields.update(path=str(p),size=size,files=files,dirs=dirs,readErrors=errs,
               modified=datetime.fromtimestamp(newest).isoformat(timespec='seconds'))
 return fields

def remove_keep(paths):
 """取消手工「标为保留」，并立刻重算这些项目的建议。"""
 labels=load_labels(); removed=[]
 for x in paths:
  p=Path(x)
  try: key=str(p.resolve()).lower()
  except OSError: continue
  if labels.pop(key,None) is not None: removed.append(str(p.resolve()))
 if not removed: return {'removed':[],'refreshed':[]}
 tmp=LABELS_FILE.with_suffix('.tmp')
 tmp.parent.mkdir(parents=True,exist_ok=True)
 tmp.write_text(json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,LABELS_FILE)
 refreshed=[]
 for x in removed:
  try: refreshed.append(reanalyze(x))
  except (OSError,ValueError): pass
 _patch_cached_items(refreshed)
 return {'removed':removed,'refreshed':refreshed}

def save_keep(paths):
 labels=load_labels(); now=datetime.now().isoformat(timespec='seconds'); marked=[]; base=all_roots()
 for x in paths:
  p=Path(x)
  if not allowed(p,base) or not p.exists(): continue
  labels[str(p.resolve()).lower()]={'label':'keep','markedAt':now,'path':str(p)}; marked.append(str(p.resolve()))
 if marked:
  tmp=LABELS_FILE.with_suffix('.tmp')
  tmp.write_text(json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,LABELS_FILE)
  refreshed=[]
  for x in marked:
   fields=dict(_manual_keep_fields(labels.get(x.lower())))
   fields['path']=x; refreshed.append(fields)
  _patch_cached_items(refreshed)
 return marked

def roots_signature(gs=None):
 """资源标签 + 目录清单的指纹。清单一变，旧的扫描结果就不能再复用。"""
 rows=gs if gs is not None else groups()
 out=[]
 for g in rows:
  roots=sorted(str(r).replace('/','\\').rstrip('\\').lower() for r in (g.get('roots') or []))
  out.append([str(g.get('id') or ''),str(g.get('name') or ''),roots])
 return out

def snapshot_is_current(snap):
 if not isinstance(snap,dict) or not isinstance(snap.get('items'),list): return False
 return snap.get('rootSig')==roots_signature()

def scan(force=False):
 if SCAN_LOCK.acquire(blocking=False):
  try: return _scan_impl(force)
  finally: set_progress(''); SCAN_LOCK.release()
 # 上一次扫描还在跑：等它结束再决定，绝不把内存里的旧结果当成「刚扫描的结果」返回。
 set_progress('等待上一次扫描结束',0,0)
 SCAN_LOCK.acquire()
 try:
  snap=load_json_file(SNAPSHOT_FILE,None)
  if not force and snapshot_is_current(snap):
   data={'generatedAt':snap.get('generatedAt'),'items':snap['items'],'roots':snap.get('roots',[]),
         'errors':snap.get('errors',[]),'rootSig':snap.get('rootSig')}
   with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
   return _finalize(dict(data,reused=True))
  return _scan_impl(force)
 finally: set_progress(''); SCAN_LOCK.release()

def _scan_impl(force=False):
 gs=groups(); sig=roots_signature(gs)
 if not force:
  snap=load_json_file(SNAPSHOT_FILE,None)
  if isinstance(snap,dict) and isinstance(snap.get('items'),list) and snap.get('generatedAt'):
   try: age=(datetime.now()-datetime.fromisoformat(snap['generatedAt'])).total_seconds()
   except (ValueError,TypeError): age=-1
   if 0<=age<SCAN_TTL_DAYS*86400 and snap.get('rootSig')==sig:
    data={'generatedAt':snap['generatedAt'],'items':snap['items'],'roots':snap.get('roots',[]),'errors':snap.get('errors',[]),'rootSig':sig}
    with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
    return _finalize(dict(data,reused=True))
 set_progress('枚举扫描目录'); rr=[]; out=[]; errors=[]; labels=load_labels(); ai_cache=load_json_file(AI_CACHE_FILE,{}); old_inventory=set(load_json_file(INVENTORY_FILE,[])); baseline=not INVENTORY_FILE.exists(); seen_roots=set()
 for group_rows in gs:
  for raw in group_rows['roots']:
   try: rp=Path(raw)
   except (OSError,ValueError): continue
   key=str(rp).lower()
   if key in seen_roots: continue
   seen_roots.add(key); rr.append((group_rows,rp))
 def add_item(p,root,collection=None,collection_reason='',media_kind='',grp=None):
  try:
   size,files,dirs,newest,hints,errs=summary(p); newest=newest or p.stat().st_mtime
   item={'id':str(p),'name':p.name,'path':str(p),'parentPath':str(p.parent),'root':str(root),'group':(grp or {}).get('id','download'),'groupName':(grp or {}).get('name','下载包'),'size':size,'files':files,'dirs':dirs,'modified':datetime.fromtimestamp(newest).isoformat(timespec='seconds'),'readErrors':errs,**analyze(p,size,files,newest,hints)}
   if media_kind:
    item.update(kind=media_kind+'目录',recommendation='建议保留',score=max(85,item['score']),mediaDirectory=True)
    item['reasons']=['目录内主要是'+media_kind+'，不拆成下载包；请按个人媒体资料处理']
   if collection:
    item['collection']=collection; item['displayName']=collection+' / '+p.name
    item['reasons']=['来自集合目录“'+collection+'”（'+collection_reason+'）']+item['reasons']
   manual=labels.get(str(p.resolve()).lower())
   if manual and manual.get('label')=='keep': item.update(_manual_keep_fields(manual))
   fp=item_fingerprint(item); item['fingerprint']=fp; item['aiDescription']=({'summary':media_kind,'model':'本地媒体识别'} if media_kind else ai_cache.get(fp)); item['isNew']=False if baseline else fp not in old_inventory
   out.append(item); return item
  except OSError as e: errors.append(str(e))
 for ri,(grp,root) in enumerate(rr,1):
  set_progress('统计目录内容 · '+os.path.basename(str(root))[:20],ri,len(rr))
  try: children=list(root.iterdir())
  except OSError as e: errors.append(str(e)); continue
  ign_names,ign_paths=ignore_sets()
  if ign_names or ign_paths: children=[p for p in children if not is_ignored(p,ign_names,ign_paths)]
  media_kinds={str(p):media_directory_kind(p) for p in children if p.is_dir()}
  decisions=classify_first_level([p for p in children if not media_kinds.get(str(p))])
  for p in children:
   # Standalone media files are personal content, not downloadable packages.
   if p.is_file() and media_file_kind(p): continue
   media_kind=media_kinds.get(str(p),'')
   if media_kind:
    add_item(p,root,media_kind=media_kind,grp=grp); continue
   decision=decisions.get(str(p),{})
   if p.is_dir() and decision.get('isCollection'):
    try: members=list(p.iterdir())
    except OSError as e: errors.append(str(e)); add_item(p,root,grp=grp); continue
    if ign_names or ign_paths: members=[m for m in members if not is_ignored(m,ign_names,ign_paths)]
    for member in members:
     if member.is_file() and media_file_kind(member): continue
     member_media=media_directory_kind(member) if member.is_dir() else ''
     add_item(member,root,p.name,decision.get('reason','多个下载包的集合'),member_media,grp)
   else:
    one=add_item(p,root,grp=grp)
    if one and decision.get('pending'): one['collectionPending']=True
 set_progress('保存扫描结果')
 save_json_file(INVENTORY_FILE,[item_fingerprint(x) for x in out])
 data={'generatedAt':datetime.now().isoformat(timespec='seconds'),'items':out,'roots':[str(p) for _,p in rr],'errors':errors,'rootSig':sig,'version':APP_VERSION}
 save_json_file(SNAPSHOT_FILE,data)
 with LOCK: CACHE.clear(); CACHE.update(data,at=time.time())
 return _finalize(dict(data,reused=False))

def allowed(p,root_list=None):
 try:
  resolved=p.resolve()
  for root in (root_list if root_list is not None else all_roots()):
   try:
    rel=resolved.relative_to(root.resolve())
    if len(rel.parts) in (1,2): return True
   except (ValueError,OSError): pass
  return False
 except OSError: return False

def recycle(paths):
 base=all_roots()
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
 d.mkdir(parents=True,exist_ok=True); done=[]; failed=[]; base=all_roots()
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
  if u.path=='/api/groups':
   try: return self.sendj({'ok':True,'result':group_list()})
   except Exception as e: return self.sendj({'ok':False,'error':str(e)},500)
  if u.path=='/api/scan':
   force=urllib.parse.parse_qs(u.query).get('force',['0'])[0]=='1'
   try:
    with LOCK: fresh=CACHE and time.time()-CACHE.get('at',0)<300 and CACHE.get('rootSig')==roots_signature()
    if fresh and not force:
     with LOCK: return self.sendj({k:v for k,v in CACHE.items() if k!='at'})
    return self.sendj(scan(force))
   except Exception as e: return self.sendj({'error':str(e)},500)
  return super().do_GET()
 def do_POST(self):
  try:
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
   if self.path=='/api/add_group': return self.sendj({'ok':True,'result':add_group(data.get('name',''))})
   if self.path=='/api/rename_group': return self.sendj({'ok':True,'result':rename_group(data.get('id',''),data.get('name',''))})
   paths=data.get('paths',[])
   if not isinstance(paths,list) or len(paths)>500: raise ValueError('选择列表无效')
   result=move(paths,data.get('destination','')) if self.path=='/api/move' else recycle(paths) if self.path=='/api/recycle' else save_keep(paths) if self.path=='/api/keep' else None
   if result is None: return self.sendj({'error':'Not found'},404)
   return self.sendj({'ok':True,'result':result})
  except Exception as e: return self.sendj({'ok':False,'error':str(e)},400)
 def log_message(self,fmt,*args): print('[web]',fmt%args)

if __name__=='__main__':
 print('下载包管家：http://127.0.0.1:8766'); ThreadingHTTPServer(('127.0.0.1',8766),H).serve_forever()
