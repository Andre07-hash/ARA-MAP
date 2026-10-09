"""Review probe; requires an explicitly disposable ARA_MAP_TEST_DATABASE_URL."""
import contextlib, io, json, os, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, sys.argv[1])
if not os.environ.get('ARA_MAP_TEST_DATABASE_URL'):
    raise SystemExit('Disposable test database required')
import psycopg
from server import postgres
from tests.test_roles_y_bases import RolesPostgres
RolesPostgres.setUpClass()
case = RolesPostgres('test_each_caller_lists_only_the_bases_it_may_open')
try:
    case.setUp()
    before = case.cuenta('maestra_base')
    with psycopg.connect(case.conninfo) as holder:
        holder.execute('SELECT pg_advisory_xact_lock(hashtext(current_schema()), %s)', (postgres.LOCK_ID,))
        req = urllib.request.Request(
            f'http://127.0.0.1:{case.httpd.server_address[1]}/api/maestra/bases',
            method='POST', data=json.dumps({'nombre': 'Review lock probe'}).encode(),
            headers={'Content-Type': 'application/json', 'Cookie': case.cookies['ada']})
        start = time.monotonic()
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                with urllib.request.urlopen(req, timeout=40) as response:
                    outcome = {'http_status': response.status, 'body': json.loads(response.read())}
            except urllib.error.HTTPError as exc:
                outcome = {'http_status': exc.code, 'body': json.loads(exc.read())}
            except Exception as exc:
                outcome = {'exception': type(exc).__name__}
        outcome['elapsed_seconds'] = round(time.monotonic()-start, 2)
        holder.rollback()
    outcome['base_count_unchanged'] = before == case.cuenta('maestra_base')
    outcome['retry_status'] = case.call('POST', '/api/maestra/bases', {'nombre':'Review lock probe'})[0]
    print(json.dumps(outcome))
    assert outcome['http_status'] == 503
    assert outcome['body']['detalle']['code'] == 'ocupado'
    assert outcome['base_count_unchanged'] and outcome['retry_status'] == 200
finally:
    case.doCleanups()
    RolesPostgres.tearDownClass()
