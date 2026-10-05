"""Disposable PostgreSQL integration verification, Unix socket only."""
import os, subprocess, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=Path('/opt/homebrew/opt/postgresql@17/bin')
env=dict(os.environ)
for k in list(env):
    if k.startswith('ARA_MAP_IA_') or k in ('DATABASE_URL','ARA_MAP_DATABASE_URL','ARA_MAP_TEST_DATABASE_URL'):
        env.pop(k,None)
with tempfile.TemporaryDirectory(prefix='ara-ready-pg-',dir='/tmp') as tmp:
    data=Path(tmp)/'cluster'
    subprocess.run([str(BIN/'initdb'),'-D',str(data),'-U','ara_review','--auth=trust','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL,env=env)
    started=False
    try:
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-l',str(Path(tmp)/'postgres.log'),'-o',f"-k {tmp} -h ''",'-w','start'],check=True,env=env)
        started=True
        env['ARA_MAP_TEST_DATABASE_URL']=f'dbname=postgres user=ara_review host={tmp}'
        subprocess.run([str(BIN/'postgres'),'--version'],check=True)
        r=subprocess.run([sys.executable,'-m','unittest','tests.test_postgres','tests.test_postgres_aceptacion','-v'],cwd=ROOT,env=env,timeout=180)
    finally:
        if started:subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,env=env)
print('Temporary PostgreSQL cluster stopped and removed; no production connection used.')
sys.exit(r.returncode)
