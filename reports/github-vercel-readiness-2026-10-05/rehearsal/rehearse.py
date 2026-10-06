#!/usr/bin/env python3
"""Fresh-checkout + schema 7 -> 8 migration + recovery rehearsal, all on
DISPOSABLE loopback Postgres and fictional data. Never touches production,
Vercel, .env.local or the default migrate/setup scripts.

    python3 rehearse.py --commit <sha> --pg-admin-url postgresql://aratest@127.0.0.1:55432/postgres \
        --python312 /path/to/python3.12 --out <evidence dir>

Backup-input mode (the real-data gate): add --backup <pg_dump file> and
--private-dir <directory OUTSIDE this repository>. The supplied backup is read
only (its sha256 is checked before and after), restored into a NEW database
on the loopback cluster, and used instead of the fictional seed; expected
counts and digests are derived from that restore. Every artifact that holds
data (restores, dumps, adapter logs) goes to --private-dir; --out then gets
only counts, ids, hashes and statuses, safe to commit for review.

Steps (each recorded in results.json):
  1. fresh clone of the commit from GitHub; HEAD must equal --commit
  2. a Vercel-like bundle: tracked files minus .vercelignore; no vendor/ copy
     of openpyxl, so dependencies come only from pyproject.toml
  3. clean Python 3.12 virtualenv with pyproject's [project] dependencies
  4. a production-shaped schema-7 workspace built by the frozen pre-change code
  5. pg_dump of it (the pre-migration backup)
  6. the candidate's cloud adapter against schema 7 before any migration
  7. scripts/esquema.py --url-env (twice) and --check
  8. legacy tables byte-identical, counts 3/104/2, in-database backup present
  9. fictional accounts through scripts/cuentas.py --url-env --password-stdin
 10. the bundle's api/index.py: anonymous policy, sign-in, bases, both saved
     maps, an import through openpyxl, an export
 11. recovery: pg_restore of the dump into a new database -> schema 7 and
     legacy tables identical to the original; the pre-change code reads it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
REPO_URL = "https://github.com/Andre07-hash/ARA-MAP.git"
LEGACY_TABLES = ("carpeta", "base", "terreno", "incidencia", "mapa", "mapa_capa",
                 "mapa_terreno", "formato_importacion", "importacion")
PG_BIN = Path("/usr/lib/postgresql/16/bin")
SAFE_ENV = {k: v for k, v in os.environ.items()
            if k not in ("DATABASE_URL", "ARA_MAP_DATABASE_URL", "ARA_MAP_TEST_DATABASE_URL")}

results: list[dict] = []


def record(step: str, ok: bool, detail: object = None) -> None:
    results.append({"step": step, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {step}" + (f"  {detail}" if detail is not None else ""), flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    kw.setdefault("env", SAFE_ENV)
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def with_db(admin_url: str, name: str) -> str:
    parts = urlsplit(admin_url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def legacy_digest(url: str) -> dict:
    import psycopg
    out = {}
    with psycopg.connect(url) as conn:
        for table in LEGACY_TABLES:
            cols = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'"
                " AND table_name = %s ORDER BY ordinal_position", (table,))]
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY 1, 2").fetchall()
            text = json.dumps([cols, [[str(v) for v in r] for r in rows]], ensure_ascii=False)
            out[table] = {"rows": len(rows), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    return out


def scalar(url: str, sql: str):  # noqa: ANN201
    import psycopg
    with psycopg.connect(url) as conn:
        return conn.execute(sql).fetchone()[0]


class Adapter:
    """The bundle's api/index.py under a stdlib HTTP server, as the tests do."""

    def __init__(self, python: str, bundle: Path, url: str, port: int) -> None:
        code = (
            "import importlib.util, sys; from http.server import ThreadingHTTPServer;"
            f"sys.path.insert(0, {str(bundle)!r});"
            f"spec = importlib.util.spec_from_file_location('vercel_entry', {str(bundle / 'api' / 'index.py')!r});"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
            "import openpyxl, server; print('openpyxl', openpyxl.__file__, flush=True);"
            f"ThreadingHTTPServer(('127.0.0.1', {port}), m.handler).serve_forever()"
        )
        env = {**SAFE_ENV, "DATABASE_URL": url}  # the variable Vercel provides
        self.log = open(bundle.parent / f"adapter-{port}.log", "w")  # noqa: SIM115
        self.proc = subprocess.Popen([python, "-c", code], cwd=bundle, env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        self.port = port
        for _ in range(80):
            try:
                self.call("GET", "/api/config")
                return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("adapter did not start")

    def call(self, method: str, path: str, body: object = None, headers: dict | None = None,
             raw: bytes | None = None) -> tuple[int, object, dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=60)
        hdrs = {"Host": "ara-preview.example", **(headers or {})}
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=hdrs)
        r = conn.getresponse()
        payload = r.read()
        conn.close()
        ctype = r.getheader("Content-Type") or ""
        parsed = json.loads(payload) if "json" in ctype else payload
        return r.status, parsed, dict(r.getheaders())

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.log.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", required=True)
    ap.add_argument("--pg-admin-url", required=True)
    ap.add_argument("--python312", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--backup", type=Path, help="pg_dump (custom or plain SQL) to restore instead of seeding")
    ap.add_argument("--private-dir", type=Path, help="required with --backup; outside the repository")
    args = ap.parse_args()
    private = None
    if args.backup:
        if not args.private_dir:
            raise SystemExit("--backup needs --private-dir (outside the repository) for data-bearing files")
        private = args.private_dir.resolve()
        inside = run(["git", "-C", str(private.parent if not private.exists() else private),
                      "rev-parse", "--show-toplevel"])
        if inside.returncode == 0:
            raise SystemExit("REFUSING: --private-dir is inside a Git working tree; real data must stay out of Git")
        private.mkdir(parents=True, exist_ok=False)
        backup_sha = hashlib.sha256(args.backup.read_bytes()).hexdigest()
    if urlsplit(args.pg_admin_url).hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("REFUSING: loopback disposable Postgres only")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.backup:
        record("backup-input mode: data-bearing files go only to the private directory", True,
               {"backup_sha256": backup_sha})
    work = out / "work"
    work.mkdir()
    stamp = uuid.uuid4().hex[:8]
    db_main, db_restore = f"ensayo_{stamp}", f"ensayo_restaurado_{stamp}"

    # 1. fresh clone
    clone = work / "clone"
    r = run(["git", "clone", "--quiet", REPO_URL, str(clone)])
    r2 = run(["git", "-C", str(clone), "checkout", "--quiet", args.commit])
    head = run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.strip()
    record("fresh clone at the reviewed commit", r.returncode == 0 and r2.returncode == 0 and head == args.commit,
           {"head": head})
    if head != args.commit:
        return finish(out)
    record("clean checkout has no local-only files",
           not any((clone / p).exists() for p in (".venv-dev", ".env.local", "datos", "api/data", ".cloud-access.txt")))

    # 2. Vercel-like bundle
    import pathspec
    spec = pathspec.PathSpec.from_lines("gitwildmatch", (clone / ".vercelignore").read_text().splitlines())
    tracked = run(["git", "-C", str(clone), "ls-files"]).stdout.splitlines()
    bundle = work / "bundle"
    kept = [f for f in tracked if not spec.match_file(f)]
    for f in kept:
        (bundle / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(clone / f, bundle / f)
    excluded_vendor = not (bundle / "vendor").exists()
    xlsx = [f for f in kept if f.endswith(".xlsx")]
    record("bundle excludes reports/tests/xlsx/root vendor; keeps web/ and api/",
           excluded_vendor and not xlsx and (bundle / "web" / "index.html").exists()
           and (bundle / "api" / "index.py").exists() and not any(f.startswith(("reports/", "tests/")) for f in kept),
           {"files": len(kept), "tracked": len(tracked)})
    vercel = json.loads((clone / "vercel.json").read_text())
    record("vercel.json keeps framework null, web/ output, api/index.py rewrite; Git deployments off",
           vercel.get("framework") is None and vercel.get("outputDirectory") == "web"
           and any(rw["destination"] == "/api/index.py" for rw in vercel.get("rewrites", []))
           and vercel.get("git", {}).get("deploymentEnabled") is False, vercel)
    missing_assets = []
    index = (bundle / "web" / "index.html").read_text()
    import re
    for ref in re.findall(r'(?:src|href)="([^"#:]+)"', index):
        if not (bundle / "web" / ref.lstrip("./")).exists():
            missing_assets.append(ref)
    record("every asset referenced by web/index.html is in the static output", not missing_assets, missing_assets)

    # 3. clean runtime from pyproject only
    import tomllib
    deps = tomllib.loads((clone / "pyproject.toml").read_text())["project"]["dependencies"]
    venv = work / "runtime"
    r = run([args.python312, "-m", "venv", str(venv)])
    py = str(venv / "bin" / "python")
    r2 = run([py, "-m", "pip", "install", "--quiet", *deps])
    ver = run([py, "-c", "import sys, openpyxl, psycopg; print(sys.version.split()[0], openpyxl.__version__, psycopg.__version__)"])
    record("clean Python 3.12 runtime installs pyproject dependencies", r.returncode == 0 and r2.returncode == 0
           and ver.returncode == 0, {"deps": deps, "versions": ver.stdout.strip(), "pip_stderr": r2.stderr[-400:]})

    # 4. the starting workspace: a restored real backup, or the fictional seed
    for name in (db_main, db_restore):
        run([str(PG_BIN / "createdb"), "-h", urlsplit(args.pg_admin_url).hostname,
             "-p", str(urlsplit(args.pg_admin_url).port), "-U", urlsplit(args.pg_admin_url).username, name])
    url = with_db(args.pg_admin_url, db_main)
    if args.backup:
        custom = run([str(PG_BIN / "pg_restore"), "-l", str(args.backup)]).returncode == 0
        r = (run([str(PG_BIN / "pg_restore"), "--no-owner", "--no-acl", "-d", url, str(args.backup)]) if custom
             else run(["psql", "-q", "-v", "ON_ERROR_STOP=0", "-d", url, "-f", str(args.backup)]))
        version = scalar(url, "SELECT value FROM workspace_metadata WHERE key = 'schema_version'")
        counts = {t: scalar(url, f"SELECT COUNT(*) FROM {t}") for t in ("base", "terreno", "mapa")}
        record("supplied backup restored into a new loopback database (fictional seed skipped)",
               counts["base"] is not None and str(version) in ("7", "8"),
               {"format": "custom" if custom else "plain", "schema_version": version, "counts": counts,
                "restore_errors": r.stderr.count("ERROR")})
    else:
        r = run([sys.executable, str(HERE / "build_v7_workspace.py"), "--url-env", "REHEARSAL_DATABASE_URL"],
                env={**SAFE_ENV, "REHEARSAL_DATABASE_URL": url})
        built = json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr[-800:]}
        counts = {t: scalar(url, f"SELECT COUNT(*) FROM {t}") for t in ("base", "terreno", "mapa")}
        record("schema-7 workspace built by the pre-change code: 3 bases / 104 terrains / 2 maps",
               built.get("schema_version") == 7 and counts == {"base": 3, "terreno": 104, "mapa": 2},
               {"built": built, "counts": counts})
    expected = expectations(url)
    before = legacy_digest(url)
    (out / "legacy_digest_before.json").write_text(json.dumps(before, indent=2))

    # 5. pre-migration backup
    dump = (private or out) / "pre_migration.dump"
    r = run([str(PG_BIN / "pg_dump"), "-Fc", "-f", str(dump), url])
    record("pre-migration pg_dump", r.returncode == 0 and dump.stat().st_size > 0,
           {"bytes": dump.stat().st_size if dump.exists() else 0, "stderr": r.stderr[-300:]})

    # 6. candidate against schema 7 before migration
    adapter = Adapter(py, bundle, url, 8441)
    try:
        st_cfg = adapter.call("GET", "/api/config")[0]
        st_login, body_login, _ = adapter.call("POST", "/api/login", {"username": "x", "password": "y" * 12})
        st_pub = adapter.call("GET", "/api/publico/terrenos")[0]
    finally:
        adapter.stop()
    record("UNMIGRATED schema 7: candidate cannot sign anyone in (expected; migration is required first)",
           st_login >= 500, {"config": st_cfg, "login": st_login, "login_body": body_login, "public_list": st_pub})
    record("UNMIGRATED schema 7: no exception text reaches the caller",
           isinstance(body_login, dict) and body_login.get("detalle", {}).get("code") in ("internal", None)
           and "team_" not in json.dumps(body_login), body_login)

    # 7. migration with the candidate's explicit-target command
    prior_backup_id = scalar(url, "SELECT COALESCE(MAX(id), 0) FROM workspace_backup")
    env_m = {**SAFE_ENV, "REHEARSAL_DATABASE_URL": url}
    chk0 = run([py, "scripts/esquema.py", "--url-env", "REHEARSAL_DATABASE_URL", "--check"], cwd=clone, env=env_m)
    m1 = run([py, "scripts/esquema.py", "--url-env", "REHEARSAL_DATABASE_URL"], cwd=clone, env=env_m)
    m2 = run([py, "scripts/esquema.py", "--url-env", "REHEARSAL_DATABASE_URL"], cwd=clone, env=env_m)
    chk = run([py, "scripts/esquema.py", "--url-env", "REHEARSAL_DATABASE_URL", "--check"], cwd=clone, env=env_m)
    noenv = run([py, "scripts/esquema.py", "--url-env", "NO_EXISTE_ESTA_VARIABLE"], cwd=clone)
    record("esquema.py: --check reports 7 (exit 1), upgrade twice, --check exit 0; refuses an unset target",
           chk0.returncode == 1 and m1.returncode == 0 and m2.returncode == 0 and chk.returncode == 0
           and noenv.returncode != 0,
           {"check_before": chk0.stdout.strip(), "run1": m1.stdout.strip() + m1.stderr[-300:],
            "run2": m2.stdout.strip(), "check_after": chk.stdout.strip(), "unset_target": noenv.stderr.strip()[-200:]})

    # 8. legacy content preserved
    after = legacy_digest(url)
    (out / "legacy_digest_after.json").write_text(json.dumps(after, indent=2))
    record("every legacy table byte-identical after migration", after == before,
           {t: after[t]["rows"] for t in after})
    import psycopg
    with psycopg.connect(url) as conn:
        # Only backups taken by this upgrade: a real workspace may already hold older ones.
        backups = conn.execute("SELECT id, payload FROM workspace_backup WHERE id > %s ORDER BY id",
                               (prior_backup_id,)).fetchall()
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    payload = json.loads(backups[0][1]) if backups else {}
    record("in-database backup taken by the upgrade holds every terrain, base and map",
           len(payload.get("terreno", [])) == expected["terrenos"] and len(payload.get("base", [])) == len(expected["bases"])
           and len(payload.get("mapa", [])) == len(expected["mapas"]),
           {"backups": len(backups), "tables_in_first": sorted(payload)})
    record("schema 8 tables now exist", {"team_user", "team_session", "inventory_terrain", "inventory_revision",
                                         "inventory_event", "inventory_operation_result"} <= tables)

    # 9. fictional accounts
    pw = {u: "ensayo-" + secrets.token_urlsafe(12) for u in ("ana.ensayo", "beto.ensayo")}
    acc = [run([py, "scripts/cuentas.py", "--url-env", "REHEARSAL_DATABASE_URL", "--password-stdin", "crear",
                u, f"{u.split('.')[0].capitalize()} Ensayo"], cwd=clone, env=env_m, input=pw[u] + "\n")
           for u in pw]
    record("fictional accounts provisioned with the operations command (password via stdin)",
           all(a.returncode == 0 for a in acc), [a.stdout.strip() + a.stderr.strip()[-200:] for a in acc])

    # 10. the bundle on schema 8
    adapter = Adapter(py, bundle, url, 8442)
    try:
        log_head = (bundle.parent / "adapter-8442.log").read_text()
        record("openpyxl resolves from the installed dependencies, not the repository's vendor copy",
               "site-packages" in log_head and "/vendor/" not in log_head, log_head.strip()[:200])
        st, body, _ = adapter.call("GET", "/api/config")
        # On this commit readOnly is true while signed out (Stage 2 changes that); only cloud matters here.
        record("anonymous /api/config answers with cloud:true", st == 200 and body.get("cloud") is True, body)
        st, body, _ = adapter.call("GET", "/api/session")
        record("anonymous /api/session", st == 200 and body == {"authenticated": False}, body)
        st_b = adapter.call("GET", "/api/bases")[0]
        st_m = adapter.call("GET", "/api/mapas")[0]
        st_p, body_p, _ = adapter.call("GET", "/api/publico/terrenos")
        record(f"CONTINUITY: anonymous visitors can no longer browse the {expected['terrenos']} legacy terrains"
               " (bases/maps 401; new public catalog empty)",
               st_b == 401 and st_m == 401 and st_p == 200 and body_p.get("total") == 0,
               {"bases": st_b, "mapas": st_m, "publico_total": body_p.get("total")})
        st, body, hdrs = adapter.call("POST", "/api/login", {"username": "ana.ensayo", "password": pw["ana.ensayo"]})
        cookie = hdrs.get("Set-Cookie", "")
        record("sign-in with a fictional account; Secure HttpOnly SameSite=Strict cookie",
               st == 200 and all(a in cookie for a in ("Secure", "HttpOnly", "SameSite=Strict")), body)
        jar = {"Cookie": cookie.split(";")[0]}
        st, body, _ = adapter.call("GET", "/api/bases", headers=jar)
        conteos = sorted(b.get("conteo") for b in body.get("bases", [])) if st == 200 else None
        record(f"signed in: the {len(expected['bases'])} migrated bases with all {expected['terrenos']} terrains",
               st == 200 and conteos == expected["bases"], conteos)
        st, body, _ = adapter.call("GET", "/api/mapas", headers=jar)
        mapas = body.get("mapas", []) if st == 200 else []
        snap = {}
        for m in mapas:
            s2, b2, _ = adapter.call("GET", f"/api/mapas/{m['id']}/terrenos", headers=jar)
            snap[str(m["id"])] = [s2, len(b2.get("terrenos", [])) if s2 == 200 else None]
        record(f"signed in: all {len(expected['mapas'])} saved maps reopen with their frozen terrains",
               snap == {k: [200, n] for k, n in expected["mapas"].items()}, snap)
        fixture = (clone / "tests" / "fixtures" / "base_terrenos_09_26.xlsx").read_bytes()
        st, prev, _ = adapter.call("POST", "/api/importar/vista-previa", headers={
            **jar, "Content-Type": "application/octet-stream", "X-Archivo": "fixture.xlsx"}, raw=fixture)
        ok_prev = st == 200 and "token" in prev
        st2, conf, _ = adapter.call("POST", "/api/importar/confirmar",
                                    {"token": prev.get("token"), "nombre": "Importación ensayo"} if ok_prev else {},
                                    headers=jar)
        record("an .xlsx import works on the deployed runtime (openpyxl from dependencies)",
               ok_prev and st2 == 200, {"preview": st, "confirm": st2,
                                        "terrenos": (conf.get("base") or {}).get("conteo") if st2 == 200 else conf})
        mid = next((m["id"] for m in mapas if m.get("tipo") == "comparacion"), mapas[0]["id"] if mapas else None)
        st, payload_x, hx = adapter.call("POST", "/api/exportar", {"mapa_id": mid, "nombre": "ensayo"}, headers=jar)
        record("export of the comparison map returns an .xlsx", st == 200 and isinstance(payload_x, bytes)
               and payload_x[:2] == b"PK", {"status": st, "bytes": len(payload_x) if isinstance(payload_x, bytes) else 0})
        st, body, _ = adapter.call("POST", "/api/inventario/terrenos", {"terreno": "Lote ensayo"},
                                   headers={**jar, "Idempotency-Key": f"ensayo-{stamp}"})
        record("signed in: a new inventory draft saves on the migrated workspace", st == 200,
               (body or {}).get("terreno", {}).get("publication_state") if st == 200 else body)
    finally:
        adapter.stop()

    # 11. recovery from the pre-migration dump
    url_r = with_db(args.pg_admin_url, db_restore)
    r = run([str(PG_BIN / "pg_restore"), "--no-owner", "-d", url_r, str(dump)])
    restored = legacy_digest(url_r)
    version = scalar(url_r, "SELECT value FROM workspace_metadata WHERE key = 'schema_version'")
    has_team = scalar(url_r, "SELECT to_regclass('public.team_user') IS NOT NULL")
    record("recovery: pg_restore of the pre-migration dump gives schema 7, identical legacy tables, no schema-8 tables",
           r.returncode == 0 and restored == before and str(version) == "7" and not has_team,
           {"schema_version": version, "stderr": r.stderr[-300:]})
    reader = run([sys.executable, "-c",
                  "import os,sys,json; sys.path.insert(0, os.environ['LEG']); import build_legacy_v7 as B;"
                  "mods = B.load_baseline(); os.environ['ARA_MAP_DATABASE_URL'] = os.environ['URL'];"
                  "from server import postgres; from server.repo import bases, mapas;"
                  "exec('with postgres.session() as c: print(json.dumps([len(bases.listing(c)), len(mapas.listing(c))]))')"],
                 env={**SAFE_ENV, "URL": url_r,
                      "LEG": str(HERE.parents[1] / "inventory-developer-handoff-2026-10-05" / "verification" / "legacy")})
    record("recovery: the pre-change (schema 7) code reads the restored workspace (rollback path)",
           reader.returncode == 0 and reader.stdout.strip() == json.dumps([len(expected["bases"]), len(expected["mapas"])]),
           reader.stdout.strip() or reader.stderr[-400:])
    if args.backup:
        record("the supplied backup file is unchanged", hashlib.sha256(args.backup.read_bytes()).hexdigest() == backup_sha)
    return finish(out, private)


def expectations(url: str) -> dict:
    """What the migrated app must show, derived from the starting database."""
    import psycopg
    with psycopg.connect(url) as conn:
        bases = sorted(r[0] for r in conn.execute(
            "SELECT COUNT(t.id) FROM base b LEFT JOIN terreno t ON t.base_id = b.id GROUP BY b.id"))
        mapas = {str(r[0]): r[1] for r in conn.execute(
            "SELECT m.id, COUNT(mt.mapa_id) FROM mapa m LEFT JOIN mapa_terreno mt ON mt.mapa_id = m.id GROUP BY m.id")}
        terrenos = conn.execute("SELECT COUNT(*) FROM terreno").fetchone()[0]
    return {"bases": bases, "mapas": mapas, "terrenos": terrenos}


def finish(out: Path, private: Path | None = None) -> int:
    fails = sum(r["result"] == "FAIL" for r in results)
    (out / "results.json").write_text(json.dumps(
        {"results": results, "pass": len(results) - fails, "fail": fails}, indent=2, ensure_ascii=False, default=str))
    for log in (out / "work").glob("adapter-*.log"):  # may name real records: private in backup mode
        shutil.move(str(log), (private or out) / log.name)
    shutil.rmtree(out / "work" / "runtime", ignore_errors=True)
    shutil.rmtree(out / "work" / "clone", ignore_errors=True)
    shutil.rmtree(out / "work" / "bundle", ignore_errors=True)
    print(f"\n{len(results) - fails} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
