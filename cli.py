# -*- coding: utf-8 -*-
"""下载包管家 CLI：给 GPT / dsh 这类外部工具读数据用的命令行入口。

源码用法：python cli.py status
EXE 用法：「下载包管家智能搜索版-v22.exe」--cli list --out out.json
只做本地扫描与关键词匹配，不会替你调用 DeepSeek（不花钱）。
"""
import argparse, io, json, os, re, sys, time
from datetime import datetime
from pathlib import Path
import server

OUT_ENCODING='utf-8'

def human(n):
 try: n=float(n or 0)
 except (TypeError,ValueError): n=0.0
 for unit in ('B','KB','MB','GB','TB'):
  if n<1024 or unit=='TB':
   return (('%.0f ' if unit=='B' else '%.1f ')%n)+unit
  n/=1024.0
 return '0 B'

def snapshot():
 snap=server.load_json_file(server.SNAPSHOT_FILE,None)
 return snap if isinstance(snap,dict) and isinstance(snap.get('items'),list) else None

def read_items(refresh=False):
 """读条目。默认只读上次扫描结果（秒回、不扫描）；--refresh 才真正重新扫描（纯本地）。"""
 if refresh or not snapshot():
  data=server.scan(bool(refresh))
  return data.get('items') or [],data
 snap=snapshot()
 data={'generatedAt':snap.get('generatedAt'),'items':snap['items'],'roots':snap.get('roots',[]),
       'errors':snap.get('errors',[]),'rootSig':snap.get('rootSig'),'reused':True}
 with server.LOCK: server.CACHE.clear(); server.CACHE.update(data,at=time.time())
 return server._finalize(data).get('items') or [],data

def slim(item,fields=None):
 ai=item.get('aiDescription') or {}
 out={'name':item.get('name',''),'path':item.get('path',''),'size':item.get('size') or 0,
      'sizeHuman':human(item.get('size')),'files':item.get('files'),'modified':item.get('modified',''),
      'recommendation':item.get('recommendation',''),'score':item.get('score'),'kind':item.get('kind',''),
      'group':item.get('group','download'),'groupName':item.get('groupName',''),
      'aiSummary':ai.get('summary',''),'aiSearchedAt':ai.get('searchedAt',''),'note':item.get('note') or '',
      'manualKeep':bool(item.get('manualKeep')),'isNew':bool(item.get('isNew')),
      'reasons':item.get('reasons') or []}
 if item.get('collection'):
  out['collection']=item['collection']; out['displayName']=item.get('displayName','')
 if fields:
  wanted=[f.strip() for f in fields.split(',') if f.strip()]
  out={k:v for k,v in out.items() if k in wanted}
 return out

def terms_of(query):
 """本地切词，不联网；jieba 缺失时退回正则。"""
 try: return server.split_query_terms(query)
 except Exception:
  toks=re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]+',(query or '').lower())
  return [t for t in toks if t]

def sort_items(items,key,reverse):
 if not key: return items
 if key=='name': f=lambda x:str(x.get('name') or '').lower()
 elif key=='size': f=lambda x:x.get('size') or 0
 elif key=='score': f=lambda x:x.get('score') or 0
 elif key=='modified': f=lambda x:str(x.get('modified') or '')
 else: f=lambda x:str(x.get('recommendation') or '')
 return sorted(items,key=f,reverse=reverse)

def cmd_status(args):
 snap=snapshot(); cfg=server.get_settings(False); gs=server.group_list()
 rows=snap['items'] if snap else []
 age=None; current=False
 if snap and snap.get('generatedAt'):
  try: age=int((datetime.now()-datetime.fromisoformat(snap['generatedAt'])).total_seconds())
  except (ValueError,TypeError): age=None
  current=snap.get('rootSig')==server.roots_signature()
 return {'ok':True,'command':'status','version':server.APP_VERSION,'dataDir':str(server.APP),
         'snapshot':{'exists':bool(snap),'generatedAt':(snap or {}).get('generatedAt',''),
                     'ageSeconds':age,'count':len(rows),
                     'sizeHuman':human(sum((x.get('size') or 0) for x in rows)),
                     'reusable':bool(snap) and age is not None and 0<=age<server.SCAN_TTL_DAYS*86400 and current},
         'progress':server.scan_status(),
         'groups':[{'id':g['id'],'name':g['name'],'roots':len(g.get('roots') or []),'count':g.get('count',0)} for g in gs],
         'settings':{'baseUrl':cfg.get('baseUrl',''),'model':cfg.get('model',''),
                     'aiConfigured':bool(cfg.get('apiKeyMasked')),'scanAI':bool(cfg.get('scanAI')),
                     'autoAnalyze':bool(cfg.get('autoAnalyze')),'hideNotice':bool(cfg.get('hideNotice')),
                     'destination':cfg.get('destination','')}}

def cmd_groups(args):
 gs=server.group_list()
 return {'ok':True,'command':'groups','count':len(gs),
         'groups':[{'id':g['id'],'name':g['name'],'builtin':bool(g.get('builtin')),'count':g.get('count',0),
                    'roots':g.get('roots') or []} for g in gs]}

def cmd_scan(args):
 data=server.scan(bool(args.force)); rows=data.get('items') or []
 return {'ok':True,'command':'scan','force':bool(args.force),'reused':bool(data.get('reused')),
         'generatedAt':data.get('generatedAt',''),'count':len(rows),
         'size':sum((x.get('size') or 0) for x in rows),
         'sizeHuman':human(sum((x.get('size') or 0) for x in rows)),
         'errors':data.get('errors') or [],
         'groups':[{'id':g['id'],'name':g['name'],'count':g.get('count',0)} for g in (data.get('groups') or [])]}

def cmd_list(args):
 items,_=read_items(args.refresh)
 if args.group: items=[x for x in items if str(x.get('group') or 'download')==args.group]
 if args.recommendation: items=[x for x in items if x.get('recommendation')==args.recommendation]
 if args.query:
  q=args.query.strip().lower()
  items=[x for x in items if q in server._search_text(x)]
 total=len(items)
 if args.sort: items=sort_items(items,args.sort,args.order=='desc')
 rows=items[args.offset:(args.offset+args.limit) if args.limit else None]
 return {'ok':True,'command':'list','total':total,'offset':args.offset,'count':len(rows),
         'items':[slim(x,args.fields) for x in rows]}

def cmd_search(args):
 items,_=read_items(args.refresh)
 if args.group: items=[x for x in items if str(x.get('group') or 'download')==args.group]
 terms=terms_of(args.query); low=args.query.strip().lower()
 scored=[]
 for x in items:
  text=server._search_text(x); name=str(x.get('name') or '').lower()
  hits=sum(1 for t in terms if t and t in text)
  score=2*hits+sum(1 for t in terms if t and t in name)+(3 if low and low in text else 0)
  if score>0: scored.append((score,x))
 scored.sort(key=lambda p:-p[0])
 rows=[dict(slim(x),matchScore=s) for s,x in scored[:args.limit]]
 return {'ok':True,'command':'search','query':args.query,'terms':terms,'total':len(scored),
         'count':len(rows),'items':rows}

def cmd_describe(args):
 items,_=read_items(args.refresh)
 raw=str(args.path or '').strip()
 want=raw.lower().replace('/','\\').rstrip('\\')
 hit=None
 for x in items:
  p=str(x.get('path') or '').lower().replace('/','\\').rstrip('\\')
  if p==want: hit=x; break
  if not hit and p.endswith(want): hit=x
 if not hit:  # 再退一步：按名字或路径包含匹配（外部工具常常只给个名字片段）
  cands=[x for x in items if want and (want in str(x.get('name') or '').lower() or want in str(x.get('path') or '').lower().replace('/','\\'))]
  if len(cands)==1: hit=cands[0]
  elif len(cands)>1:
   return {'ok':False,'command':'describe','error':'匹配到多条，请给更完整的路径：'+raw,
    'candidates':[{'name':x.get('name'),'path':x.get('path')} for x in cands[:10]]}
 if not hit: return {'ok':False,'command':'describe','error':'没找到这个条目：'+raw}
 out=dict(hit); out['sizeHuman']=human(hit.get('size'))
 return {'ok':True,'command':'describe','item':out}

def build_parser():
 common=argparse.ArgumentParser(add_help=False)
 common.add_argument('--out',default=argparse.SUPPRESS,help='把 JSON 写到这个文件（窗口版 EXE 推荐）')
 common.add_argument('--pretty',action='store_true',default=argparse.SUPPRESS,help='输出多行缩进 JSON')
 p=argparse.ArgumentParser(prog='下载包管家 CLI',description='读取下载包管家的本机数据（只读文件信息，不联网、不调用 AI）')
 p.add_argument('--out',default='',help='把 JSON 写到这个文件（窗口版 EXE 推荐）')
 p.add_argument('--pretty',action='store_true',help='输出多行缩进 JSON')
 p.add_argument('--version',action='store_true',help='显示版本号')
 sub=p.add_subparsers(dest='command')
 sub.add_parser('status',parents=[common],help='版本、上次扫描时间、是否配置了 Key、标签概览')
 sub.add_parser('groups',parents=[common],help='资源标签与目录、条目数')
 sp=sub.add_parser('scan',parents=[common],help='跑一次纯本地扫描')
 sp.add_argument('--force',action='store_true',help='忽略缓存，强制重新扫描（慢，约几秒到几十秒）')
 sp=sub.add_parser('list',parents=[common],help='列出条目')
 sp.add_argument('--group',default='',help='只看某个标签（标签 id，见 groups）')
 sp.add_argument('--query',default='',help='按关键词过滤（本地包含匹配）')
 sp.add_argument('--recommendation',default='',help='按建议过滤：建议保留 / 待确认 / 不用保住 / 保留（手工）')
 sp.add_argument('--sort',default='',choices=['','name','size','score','modified','recommendation'],help='排序字段')
 sp.add_argument('--order',default='desc',choices=['asc','desc'],help='排序方向，默认 desc')
 sp.add_argument('--limit',type=int,default=0,help='最多返回多少条，0 表示全部')
 sp.add_argument('--offset',type=int,default=0,help='跳过前多少条')
 sp.add_argument('--fields',default='',help='只保留这些字段，逗号分隔，例如 name,sizeHuman,recommendation')
 sp.add_argument('--refresh',action='store_true',help='先重新扫描再列（默认只读上次扫描结果）')
 sp=sub.add_parser('search',parents=[common],help='一句话本地检索引擎（关键词，不联网）')
 sp.add_argument('query',help='想找什么，例如「CUDA 安装包」')
 sp.add_argument('--limit',type=int,default=20,help='最多返回多少条，默认 20')
 sp.add_argument('--group',default='',help='只在这个标签里搜')
 sp.add_argument('--refresh',action='store_true',help='先重新扫描再搜')
 sp=sub.add_parser('describe',parents=[common],help='看单个条目的完整信息（按路径或路径结尾匹配）')
 sp.add_argument('path',help='条目路径，或路径结尾，例如 WeChat')
 sp.add_argument('--refresh',action='store_true',help='先重新扫描再查')
 return p

def emit(obj,out,pretty):
 text=json.dumps(obj,ensure_ascii=False,indent=2 if pretty else None)
 if out:
  target=Path(out).expanduser()
  if target.parent and not target.parent.exists(): target.parent.mkdir(parents=True,exist_ok=True)
  with io.open(target,'w',encoding=OUT_ENCODING,newline='\n') as f: f.write(text+'\n')
  return
 try: sys.stdout.write(text+'\n')
 except Exception:
  # 窗口版 EXE 没有控制台：退回到固定文件，别把数据丢掉
  fallback=Path.cwd()/'dpm-cli-output.json'
  with io.open(fallback,'w',encoding=OUT_ENCODING,newline='\n') as f: f.write(text+'\n')

def ensure_stdio():
 """窗口版 EXE 没有 stdout：尽量挂上父进程的控制台，挂不上就算了（这时用 --out）。"""
 if sys.stdout is not None and sys.stderr is not None: return True
 try:
  import ctypes
  if not ctypes.windll.kernel32.AttachConsole(-1): return False
  sys.stdout=io.open('CONOUT$','w',encoding=OUT_ENCODING,buffering=1,closefd=False)
  sys.stderr=io.open('CONOUT$','w',encoding=OUT_ENCODING,buffering=1,closefd=False)
  return True
 except Exception: return False

def main(argv=None):
 argv=list(sys.argv[1:] if argv is None else argv)
 ensure_stdio()
 parser=build_parser(); args=parser.parse_args(argv)
 if args.version:
  emit({'ok':True,'version':server.APP_VERSION},getattr(args,'out',''),getattr(args,'pretty',False)); return 0
 if not args.command:
  parser.print_help(); return 0
 handler={'status':cmd_status,'groups':cmd_groups,'scan':cmd_scan,'list':cmd_list,'search':cmd_search,'describe':cmd_describe}[args.command]
 try: obj=handler(args)
 except Exception as e: obj={'ok':False,'command':args.command,'error':str(e)}
 emit(obj,getattr(args,'out',''),getattr(args,'pretty',False))
 return 0 if obj.get('ok') else 1

if __name__=='__main__':
 sys.exit(main())