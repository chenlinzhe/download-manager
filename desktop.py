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
 def add_manual_root(self):
  try:
   result=webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
   if not result: return {'ok':False,'cancelled':True}
   path=result[0] if isinstance(result,(list,tuple)) else result
   return {'ok':True,'result':server.add_manual_root(path)}
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
 def enrich(self, paths):
  try: return server.enrich_items(paths)
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

def fatal(text):
 try:
  import ctypes; ctypes.windll.user32.MessageBoxW(None,text,'下载包管家启动失败',0x10)
 except Exception: pass

if __name__=='__main__':
 try:
  url=resource('index.html').as_uri()
  webview.create_window('下载包管家',url,js_api=Api(),width=1500,height=900,min_size=(900,600))
  webview.start(debug=False)
 except Exception:
  fatal(traceback.format_exc())
