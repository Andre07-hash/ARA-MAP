"""Browser evidence on an ephemeral port and disposable SQLite, without AI."""
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from review_regressions import two_sheets
os.environ['ARA_MAP_IA_PROVEEDOR'] = ''
os.environ['ARA_MAP_READ_ONLY'] = '0'
with tempfile.TemporaryDirectory(prefix='ara-review-fixes-') as tmp:
    os.environ['ARA_MAP_DB'] = str(Path(tmp) / 'test.db')
    workbook = Path(tmp) / 'two-sheets.xlsx'
    workbook.write_bytes(two_sheets())
    from server import db
    db.connect().close()
    from server.app import Handler, ThreadingHTTPServer
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ, ARA_URL=f'http://127.0.0.1:{server.server_address[1]}',
                   ARA_REVIEW_WORKBOOK=str(workbook))
        result = subprocess.run(['node', str(Path(__file__).with_name('browser.mjs'))],
                                env=env, cwd=ROOT, timeout=120)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
print('Temporary server stopped; temporary database and workbook removed.')
sys.exit(result.returncode)
