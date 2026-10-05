import os,subprocess,tempfile,threading,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
for k in list(os.environ):
    if k.startswith('ARA_MAP_IA_') or k in ('DATABASE_URL','ARA_MAP_DATABASE_URL','ARA_MAP_TEST_DATABASE_URL'):os.environ.pop(k,None)
os.environ['ARA_MAP_IA_PROVEEDOR']='';os.environ['ARA_MAP_READ_ONLY']='0'
with tempfile.TemporaryDirectory(prefix='ara-maptest-browser-') as tmp:
    os.environ['ARA_MAP_DB']=str(Path(tmp)/'test.db')
    from server import db
    db.connect().close()
    from server.app import Handler,ThreadingHTTPServer
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        env=dict(os.environ,ARA_URL=f'http://127.0.0.1:{server.server_address[1]}')
        result=subprocess.run(['node',str(Path(__file__).with_name('browser.mjs'))],env=env,cwd=ROOT,timeout=150)
        print('browser_exit',result.returncode)
    finally:
        server.shutdown();server.server_close();t.join(timeout=5)
print('Temporary browser server stopped; database deleted.')
