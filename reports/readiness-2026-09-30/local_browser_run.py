"""Run existing full browser suite against disposable local storage only."""
import os, sys, subprocess, tempfile, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
for k in list(os.environ):
    if k.startswith('ARA_MAP_IA_') or k in ('DATABASE_URL','ARA_MAP_DATABASE_URL','ARA_MAP_TEST_DATABASE_URL'):
        os.environ.pop(k,None)
os.environ['ARA_MAP_IA_PROVEEDOR']=''
os.environ['ARA_MAP_READ_ONLY']='0'
evidence=Path(__file__).parent/'evidence'
with tempfile.TemporaryDirectory(prefix='ara-readiness-') as tmp:
    os.environ['ARA_MAP_DB']=str(Path(tmp)/'test.db')
    from server import db
    db.connect().close()
    from server.app import Handler,ThreadingHTTPServer
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
    print('Disposable test server port',srv.server_address[1],flush=True)
    try:
        env=dict(os.environ,ARA_URL=f'http://127.0.0.1:{srv.server_address[1]}',E2E_SHOTS=str(evidence),E2E_LAYOUT_SHOTS=str(evidence))
        result=subprocess.run(['node','tests/e2e/smoke.mjs'],cwd=ROOT,env=env,timeout=360)
    finally:
        srv.shutdown();srv.server_close();t.join(timeout=5)
print('Temporary server stopped; disposable database removed.',flush=True)
sys.exit(result.returncode)
