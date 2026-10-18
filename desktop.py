import sys, traceback
from pathlib import Path
import webview
import server

def resource(name):
 base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
 return base/name

class Api:
 def open_path(self, path):
  try: return {'ok':True,'result':server.open_path(path)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def add_manual_root(self, group=None):
  """选目录时可以按住 Ctrl 或 Shift 一次选多个，全部加到当前标签下。"""
  try:
   start=''
   try:
    for g in server.groups():
     if g['id']==(group or 'download') and g['roots']:
      start=str(Path(g['roots'][0]).parent); break
   except Exception:
    start=''
   kw={'allow_multiple':True}
   if start: kw['directory']=start
   result=webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG,**kw)
   if not result: return {'ok':False,'cancelled':True}
   paths=[str(x) for x in (result if isinstance(result,(list,tuple)) else [result])]
   return {'ok':True,'result':server.add_manual_roots(paths,group)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def tokenize(self, query):
  try: return {'ok':True,'result':server.split_query_terms(query)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def natural_search(self, query):
  try: return {'ok':True,'result':server.natural_search(query)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def get_settings(self):
  try: return {'ok':True,'result':server.get_settings(False)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def save_settings(self, data):
  try: return {'ok':True,'result':server.save_settings(data)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def test_connection(self, data=None):
  try:
   data=data or {}
   return server.test_connection(data.get('baseUrl'),data.get('model'),data.get('apiKey'))
  except Exception as e: return {'ok':False,'error':str(e)}
 def enrich(self, paths, force=False):
  try: return server.enrich_items(paths, force)
  except Exception as e: return {'ok':False,'error':str(e)}
 def set_note(self, path, text):
  try: return {'ok':True,'result':server.save_note(path,text)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def add_group(self, name):
  try: return {'ok':True,'result':server.add_group(name)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def rename_group(self, group, name):
  try: return {'ok':True,'result':server.rename_group(group,name)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def app_version(self):
  try: return {'ok':True,'result':server.APP_VERSION}
  except Exception as e: return {'ok':False,'error':str(e)}
 def scan_status(self):
  try: return server.scan_status()
  except Exception as e: return {'ok':False,'error':str(e)}
 def scan(self, force=False):
  try: return server.scan(force)
  except Exception as e: return {'error':str(e)}
 def keep(self, paths):
  try: return {'ok':True,'result':server.save_keep(paths)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def recycle(self, paths):
  try: return {'ok':True,'result':server.recycle(paths)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def move(self, paths, destination):
  try: return {'ok':True,'result':server.move(paths,destination)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def unkeep(self, paths):
  try: return {'ok':True,'result':server.remove_keep(paths)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def pick_folder(self):
  try:
   result=webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
   if not result: return {'ok':False,'cancelled':True}
   path=result[0] if isinstance(result,(list,tuple)) else result
   return {'ok':True,'result':str(path)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def ignore(self, name, path=''):
  try: return {'ok':True,'result':server.add_ignore(name,path)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def unignore(self, name):
  try: return {'ok':True,'result':server.remove_ignore(name)}
  except Exception as e: return {'ok':False,'error':str(e)}
 def ignored_list(self):
  try: return {'ok':True,'result':server.load_ignore()}
  except Exception as e: return {'ok':False,'error':str(e)}

def fatal(text):
 try:
  import ctypes; ctypes.windll.user32.MessageBoxW(None,text,'下载包管家启动失败',0x10)
 except Exception: pass

if __name__=='__main__':
 try:
  url=resource('index.html').as_uri()
  webview.create_window('下载包管家 V'+server.APP_VERSION,url,js_api=Api(),width=1500,height=900,min_size=(900,600))
  webview.start(debug=False)
 except Exception:
  fatal(traceback.format_exc())
