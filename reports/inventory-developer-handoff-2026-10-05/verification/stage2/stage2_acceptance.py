#!/usr/bin/env python3
"""Stage 2 HTTP acceptance: PUB-01/02/03, CON-02, PRE-01, public catalog (VIEW-03 API,
§6 filters/facets/cursor), ID guessing, §5 anonymous route audit (BLOCKING), carry-forwards
(O-5 generic 500, O-7 login throttle per login+client, config.readOnly).

Independent of the developer's tests. Owns the server lifecycle like stage1_acceptance.py:
starts the candidate through stage2/serve_target2.py (stage1/serve_target.py + switchable
fault hooks) on 127.0.0.1:<port> against a NEW temporary SQLite file (local adapter) or the
verifier's disposable Postgres on 127.0.0.1:55433 (cloud adapter api/index.py).

  python stage2_acceptance.py --mode local --port 8433
  harness/pg_disposable_linux.sh -- python stage2_acceptance.py --mode cloud --port 8433

Evidence: verification/runs/<stamp>-stage2-<mode>/ (results.json, http.jsonl, server.log,
provision.log, route_table.json, public_responses.jsonl). Exit 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage1"))
import aralib as L  # noqa: E402
import leak_audit  # noqa: E402

INV = "/api/inventario/terrenos"
PUB = "/api/publico/terrenos"
PUBLIC_FIELDS = ("terreno", "estado", "municipio", "direccion", "superficie_m2", "superficie_ha",
                 "afectaciones_pct", "afectaciones_m2", "lat", "lon", "asking_price", "asking_m2",
                 "moneda", "price_on_request", "availability", "public_description")
UNIFORM_404 = {"error": "Terreno no encontrado.", "detalle": {"code": "not_found"}}
GENERIC_500_PREFIX = "Ocurrió un error inesperado"
PREVIEW_KEYS = {"id", "version", "revision_id", "preview", "terreno", "blockers", "warnings"}
CASES = ("SEED", "PRE-01", "PUB-01", "PUB-02", "PUB-03", "CON-02", "FILTERS", "PAGE-251", "GUESS",
         "LEAK", "O-5", "CONFIG", "O-7")
BLOCKER_CODES = {"coordinates": "location_invalid", "price": "price_required",
                 "availability": "availability_unknown", "price_conflict": "price_conflict",
                 "currency": "currency_required", "area": "area_required"}


# --------------------------------------------------------------------------- infrastructure

class Server2(L.Server):
    """aralib.Server, but launched through stage2/serve_target2.py with a fault control file."""

    def __init__(self, *a, fault_file: Path, **k) -> None:  # noqa: ANN002, ANN003
        super().__init__(*a, **k)
        self.fault_file = fault_file

    def start(self) -> None:
        cmd = [sys.executable, str(HERE / "serve_target2.py"), "--mode", self.mode,
               "--port", str(self.port), "--app-root", str(self.app_root),
               "--fault-file", str(self.fault_file)]
        if self.db:
            cmd += ["--db", str(L.assert_disposable_path(self.db))]
        env = L.safe_env(self.extra_env)
        if self.mode == "cloud":
            env["ARA_MAP_TEST_DATABASE_URL"] = os.environ["ARA_MAP_TEST_DATABASE_URL"]
        self._fh = self.log_path.open("a")
        self._fh.write(f"\n[verifier] start {time.strftime('%H:%M:%S')} extra_env={sorted(self.extra_env)}\n")
        self._fh.flush()
        self.proc = subprocess.Popen(cmd, env=env, stdout=self._fh, stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit(f"server exited early; see {self.log_path}")
            try:
                urllib.request.urlopen(self.url + "/api/session", timeout=1)
                return
            except urllib.error.HTTPError:
                return
            except OSError:
                time.sleep(0.2)
        raise SystemExit("server did not start")


class Ctx:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = L.VERIFY / "runs" / f"{self.stamp}-stage2-{args.mode}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="ara-verify-s2-"))
        self.users = L.users()
        # Two extra fictional accounts used only by the throttle probes (O-7).
        tag = uuid.uuid4().hex[:6]
        self.users += [
            {"tag": "T", "username": f"sntl-user-t-{tag}", "password": f"SNTL-PASS-T-{tag}-Fict!{uuid.uuid4().hex[:6]}",
             "display_name": f"Tere Throttle SNTL-ACTOR-T-{tag}", "provision": True},
            {"tag": "U", "username": f"sntl-user-u-{tag}", "password": f"SNTL-PASS-U-{tag}-Fict!{uuid.uuid4().hex[:6]}",
             "display_name": f"Ugo Throttle SNTL-ACTOR-U-{tag}", "provision": True},
        ]
        self.secrets = [u["password"] for u in self.users]
        self.ev = L.Evidence(self.run_dir / "http.jsonl", self.secrets)
        self.scanner = L.Scanner(self.secrets)
        self.master = L.records()
        self.pages = L.records("matching_251.json")
        self.db = L.assert_disposable_path(self.tmp / "ara.db") if args.mode == "local" else None
        self.fault_file = self.tmp / "faults.json"
        self.set_faults({})
        self.server = Server2(args.mode, args.port, self.db, self.run_dir / "server.log",
                              dict(L.contract_map().get("server_extra_env", {})),
                              app_root=args.app_root.resolve(), fault_file=self.fault_file)
        self.sess: dict[str, L.Session] = {}
        self.uid: dict[str, str] = {}
        self.id: dict[str, str] = {}            # fixture key -> inventory id
        self.model: dict[str, dict] = {}        # inventory id -> expected PublicTerrain (public now)
        self.public_log = (self.run_dir / "public_responses.jsonl").open("a")
        self.public_count = 0
        self.public_bad: list = []
        self.timings: dict[str, list[float]] = {"publish": [], "preview": [], "public_list": [],
                                                "public_detail": [], "lifecycle": []}

    def set_faults(self, control: dict) -> None:
        self.fault_file.write_text(json.dumps(control))

    def session(self, name: str) -> L.Session:
        return L.Session(self.server.url, name, self.ev)

    def user(self, tag: str) -> dict:
        return next(u for u in self.users if u["tag"] == tag)

    def ok(self, case: str, check: str, cond: bool, detail: object = None) -> bool:
        self.ev.result(case, check, "PASS" if cond else "FAIL", detail)
        return bool(cond)

    def warn(self, case: str, check: str, detail: object = None) -> None:
        self.ev.result(case, check, "WARN", detail)

    def info(self, case: str, check: str, detail: object = None) -> None:
        self.ev.result(case, check, "INFO", detail)

    def skip(self, case: str, check: str, detail: object = None) -> None:
        self.ev.result(case, check, "SKIP", detail)


def terr(r: L.Resp) -> dict:
    return (r.json or {}).get("terreno") or {}


def code(r: L.Resp) -> str | None:
    return ((r.json or {}).get("detalle") or {}).get("code")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c))


class DB:
    """Read-only (except throttle inspection) queries on the disposable database."""

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx

    def rows(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.ctx.db:
            conn = sqlite3.connect(self.ctx.db.as_uri() + "?mode=ro", uri=True)
            try:
                return [tuple(r) for r in conn.execute(sql, params).fetchall()]
            finally:
                conn.close()
        import psycopg
        with psycopg.connect(os.environ["ARA_MAP_TEST_DATABASE_URL"], autocommit=True) as conn:
            return [tuple(r) for r in conn.execute(sql.replace("?", "%s"), params).fetchall()]

    def events(self, tid: str) -> list[tuple]:
        return self.rows("SELECT version, action, actor_id, at, before_revision_id, after_revision_id"
                         " FROM inventory_event WHERE inventory_id = ? ORDER BY version", (tid,))

    def tables(self) -> list[str]:
        q = ("SELECT name FROM sqlite_master WHERE type='table'" if self.ctx.db else
             "SELECT table_name FROM information_schema.tables WHERE table_schema NOT IN"
             " ('pg_catalog','information_schema')")
        return [r[0] for r in self.rows(q)]


# --------------------------------------------------------------------------- API helpers

def get(ctx: Ctx, s: L.Session, tid: str) -> dict:
    return terr(s.get(f"{INV}/{tid}"))


def create(ctx: Ctx, s: L.Session, draft: dict, key: str) -> L.Resp:
    return s.post(INV, L.to_payload(draft), headers={"Idempotency-Key": key})


def save(ctx: Ctx, s: L.Session, tid: str, changes: dict, version: int | None = None) -> L.Resp:
    if version is None:
        version = get(ctx, s, tid).get("version")
    return s.patch(f"{INV}/{tid}", {"expected_version": version, "changes": L.to_payload(changes)})


def preview(ctx: Ctx, s: L.Session, tid: str, revision_id: str | None = None, extra: str = "") -> L.Resp:
    qs = f"?revision_id={revision_id}" if revision_id else ""
    if extra:
        qs += ("&" if qs else "?") + extra
    r = s.get(f"{INV}/{tid}/vista-publica{qs}")
    ctx.timings["preview"].append(r.ms)
    return r


def action(ctx: Ctx, s: L.Session, tid: str, verb: str, body: dict | None, **k) -> L.Resp:  # noqa: ANN003
    r = s.post(f"{INV}/{tid}/{verb}", body, **k)
    ctx.timings["publish" if verb == "publicar" else "lifecycle"].append(r.ms)
    return r


def publish_reviewed(ctx: Ctx, s: L.Session, tid: str, check: str | None = None) -> tuple[L.Resp, dict]:
    """Preview -> Publish {expected_version, revision_id} exactly as reviewed. Updates the model."""
    pv = preview(ctx, s, tid)
    body = pv.json or {}
    t0 = datetime.now(timezone.utc)
    r = action(ctx, s, tid, "publicar", {"expected_version": body.get("version"),
                                         "revision_id": body.get("revision_id")})
    t1 = datetime.now(timezone.utc)
    if r.status == 200:
        t = terr(r)
        if t.get("public_visible"):
            expected = dict(body.get("terreno") or {})
            expected["published_at"] = t.get("published_at")
            ctx.model[tid] = expected
        else:
            ctx.model.pop(tid, None)
    return r, {"preview": body, "t0": t0, "t1": t1}


def pub(ctx: Ctx, path: str, expect: int | tuple = 200, label: str = "") -> L.Resp:
    """Every anonymous public response passes through here: sentinel scan, exact keys,
    no-store, uniform 404."""
    anon = L.Session(ctx.server.url, "anon-public", ctx.ev)
    r = anon.get(path)
    ctx.timings["public_detail" if path.count("/") > 3 else "public_list"].append(r.ms)
    ctx.public_count += 1
    problems = []
    hits = ctx.scanner.hits(r.text_for_scan())
    if hits:
        problems.append({"sentinels": hits[:5]})
    if "no-store" not in (r.headers.get("Cache-Control") or ""):
        problems.append({"cache_control": r.headers.get("Cache-Control")})
    if any(c.lower().startswith(L.contract_map()["session_cookie"]) and "max-age=0" not in c.lower()
           for c in r.set_cookies):
        problems.append("sets a session cookie")
    body = r.json
    if r.status == 200 and isinstance(body, dict):
        items = body.get("terrenos") if "terrenos" in body else [body.get("terreno")]
        if "terrenos" in body and set(body) != L.LIST_ENVELOPE:
            problems.append({"envelope": sorted(body)})
        if "terreno" in body and set(body) != {"terreno"}:
            problems.append({"detail_envelope": sorted(body)})
        for t in items or []:
            if not isinstance(t, dict) or set(t) != L.PUBLIC_TERRAIN_KEYS:
                problems.append({"keys": sorted(set(t or {}) ^ L.PUBLIC_TERRAIN_KEYS)})
                break
            if t.get("availability") not in ("available", "negotiation") or not t.get("published_at"):
                problems.append({"ineligible": t.get("id"), "availability": t.get("availability")})
    if r.status == 404 and body != UNIFORM_404:
        problems.append({"non_uniform_404": body})
    if r.status >= 500 and GENERIC_500_PREFIX not in (body or {}).get("error", ""):
        problems.append({"non_generic_500": r.body[:200].decode("utf-8", "replace")})
    exp = expect if isinstance(expect, tuple) else (expect,)
    if r.status not in exp:
        problems.append({"status": r.status, "expected": exp})
    ctx.public_log.write(json.dumps({"path": path, "status": r.status, "problems": problems,
                                     "bytes": len(r.body)}, ensure_ascii=False) + "\n")
    if problems:
        ctx.public_bad.append({"path": path, "label": label, "problems": problems})
        ctx.ev.result("PUBLIC", f"public response clean: {path[:120]}", "FAIL", problems)
    return r


def all_public(ctx: Ctx, query: dict | list | None = None, limit: int = 250) -> tuple[list[dict], list[L.Resp]]:
    items, resps, cursor = [], [], None
    pairs = list(query.items()) if isinstance(query, dict) else list(query or [])
    for _ in range(50):
        q = pairs + [("limit", str(limit))] + ([("cursor", cursor)] if cursor else [])
        r = pub(ctx, f"{PUB}?{urlencode(q)}")
        resps.append(r)
        body = r.json or {}
        items += body.get("terrenos", [])
        cursor = body.get("next_cursor")
        if not cursor or r.status != 200:
            break
    return items, resps


def catalog_check(ctx: Ctx, case: str, label: str) -> bool:
    """The anonymous catalog equals the verifier's model exactly: membership, every public field,
    revision ids and published_at."""
    items, resps = all_public(ctx)
    got = {t["id"]: t for t in items}
    want = {k: v for k, v in ctx.model.items()}
    missing = sorted(set(want) - set(got))[:5]
    extra = sorted(set(got) - set(want))[:5]
    diffs = {}
    for tid in set(want) & set(got):
        w, g = want[tid], got[tid]
        if w is None:
            continue
        d = {k: (w.get(k), g.get(k)) for k in L.PUBLIC_TERRAIN_KEYS if w.get(k) != g.get(k)}
        if d:
            diffs[tid] = d
    totals = {(r.json or {}).get("total") for r in resps}
    return ctx.ok(case, f"catalog == model after {label} ({len(want)} records, all fields)",
                  not missing and not extra and not diffs and totals == {len(want)} and len(items) == len(got),
                  {"missing": missing, "extra": extra, "diffs": dict(list(diffs.items())[:3]),
                   "totals": sorted(t for t in totals if t is not None), "n": len(items)})


def unchanged(before: dict, after: dict) -> bool:
    keys = ("version", "draft_revision_id", "published_revision_id", "published_at", "archived_at",
            "publication_state", "draft")
    return all(before.get(k) == after.get(k) for k in keys)


# --------------------------------------------------------------------------- setup + seed

def setup(ctx: Ctx) -> None:
    if ctx.args.mode == "cloud":
        cmd = L.contract_map()["schema_cmd_cloud"]
        for _ in range(2):
            L.run_ops(cmd, None, ctx.run_dir / "provision.log")
        L.run_ops(cmd + ["--check"], None, ctx.run_dir / "provision.log")
        ctx.info("SETUP", "esquema.py applied twice and --check passed")
    ctx.server.start()
    for u in ctx.users:
        if u["provision"]:
            L.provision(u, ctx.db, ctx.run_dir / "provision.log")
    login_all(ctx)


def login_all(ctx: Ctx) -> None:
    for tag in "ABC":
        s = ctx.sess.get(tag) or ctx.session(tag)
        if (s.get("/api/session").json or {}).get("authenticated") is not True:
            r = s.login(ctx.user(tag)["username"], ctx.user(tag)["password"])
            if r.status != 200:
                raise SystemExit(f"login {tag} -> {r.status}")
        ctx.sess[tag] = s
        ctx.uid[tag] = (s.get("/api/session").json or {}).get("user", {}).get("id")


def case_seed(ctx: Ctx) -> None:
    """120 master + 251 pagination fixtures; 100 published (2 set to negotiation first), 10
    published then unpublished, 10 drafts, 251 published. PRE-01 is checked on every publish."""
    C = "SEED"
    S = ctx.sess
    refused = {}
    for i, (key, rec) in enumerate([*ctx.master.items(), *ctx.pages.items()]):
        r = create(ctx, S["ABC"[i % 3]], rec["draft"], f"s2-{key}-{ctx.stamp}")
        if r.status != 200:
            refused[key] = r.status
            continue
        ctx.id[key] = terr(r)["id"]
    ctx.ok(C, "all fixtures saved except M102 (|lat|>90) and M107 (price w/o currency, accepted O-1)",
           set(refused) == {"M102", "M107"}, refused)
    for key in ("M005", "M015"):
        r = save(ctx, S["B"], ctx.id[key], {"availability": "negotiation"})
        ctx.ok(C, f"{key} saved as negotiation before first publication", r.status == 200, r.status)
    pre = {"n": 0, "mismatch": [], "keys": [], "published_at": [], "revision": [], "preview_shape": []}
    publish_keys = [k for k, r in ctx.master.items() if r["intended_lifecycle"] in ("published", "unpublished")
                    and k in ctx.id] + list(ctx.pages)
    failures = {}
    for i, key in enumerate(publish_keys):
        tid = ctx.id[key]
        r, info = publish_reviewed(ctx, S["ABC"[(i + 1) % 3]], tid)
        if r.status != 200:
            failures[key] = (r.status, code(r), (r.json or {}).get("detalle"))
            continue
        pre["n"] += 1
        pv = info["preview"]
        t = terr(r)
        if set(pv) != PREVIEW_KEYS or pv.get("preview") is not True or pv.get("terreno", {}).get("published_at") is not None:
            pre["preview_shape"].append(key)
        if set(pv.get("terreno") or {}) != L.PUBLIC_TERRAIN_KEYS:
            pre["keys"].append(key)
        d = pub(ctx, f"{PUB}/{tid}", 200 if t.get("public_visible") else 404)
        if t.get("public_visible"):
            g = terr(d)
            biz = {k: (pv["terreno"].get(k), g.get(k)) for k in (*PUBLIC_FIELDS, "id")
                   if pv["terreno"].get(k) != g.get(k)}
            if biz:
                pre["mismatch"].append({key: biz})
            if not (g.get("revision_id") == pv.get("revision_id") == t.get("published_revision_id")
                    == t.get("draft_revision_id")):
                pre["revision"].append(key)
            try:
                at = datetime.fromisoformat(g.get("published_at"))
                lo = info["t0"].replace(microsecond=0) - timedelta(seconds=1)
                ok = lo <= at <= info["t1"] + timedelta(seconds=1) and g.get("published_at") == t.get("published_at")
            except (TypeError, ValueError):
                ok = False
            if not ok:
                pre["published_at"].append((key, g.get("published_at"), info["t0"].isoformat()))
            # fixture values (logical -> backend names) must be what is public
            fx = L.to_payload({**(ctx.master.get(key) or ctx.pages.get(key))["draft"]})
            if key in ("M005", "M015"):
                fx["availability"] = "negotiation"
            fdiff = {k: (fx.get(k), g.get(k)) for k in PUBLIC_FIELDS if fx.get(k) != g.get(k)}
            if fdiff:
                pre["mismatch"].append({key + "(fixture)": fdiff})
    ctx.ok(C, f"every intended publication succeeded ({len(publish_keys)})", not failures, failures)
    ctx.ok("PRE-01", f"preview envelope exact, preview:true, published_at null ({pre['n']} records)",
           not pre["preview_shape"], pre["preview_shape"][:5])
    ctx.ok("PRE-01", "preview terreno has exactly the PublicTerrain keys", not pre["keys"], pre["keys"][:5])
    ctx.ok("PRE-01", "preview business fields == public detail == fixture values (all published records)",
           not pre["mismatch"], pre["mismatch"][:3])
    ctx.ok("PRE-01", "revision_id: preview == public == published pointer == draft pointer",
           not pre["revision"], pre["revision"][:5])
    ctx.ok("PRE-01", "public published_at == commit time (within request window) == internal published_at",
           not pre["published_at"], pre["published_at"][:3])
    # 10 published-then-unpublished
    unpub = [k for k, r in ctx.master.items() if r["intended_lifecycle"] == "unpublished"]
    st = []
    for key in unpub:
        tid = ctx.id[key]
        t = get(ctx, S["C"], tid)
        r = action(ctx, S["C"], tid, "despublicar", {"expected_version": t["version"]})
        if r.status == 200:
            ctx.model.pop(tid, None)
        st.append((key, r.status, terr(r).get("publication_state")))
    ctx.ok(C, "10 published records unpublished (state 'unpublished')",
           all(s == 200 and p == "unpublished" for _, s, p in st), st)
    drafts = [get(ctx, S["A"], ctx.id[k]).get("publication_state") for k, r in ctx.master.items()
              if r["intended_lifecycle"] == "draft" and k in ctx.id]
    ctx.ok(C, "drafts remain 'draft'", set(drafts) == {"draft"}, drafts)
    ctx.info(C, "seeded", {"created": len(ctx.id), "public_model": len(ctx.model)})
    catalog_check(ctx, C, "seeding")
    # Positive controls: the detectors bite.
    internal = S["A"].get(f"{INV}/{ctx.id['M001']}")
    ctx.ok("CONTROL", "sentinel scanner finds the contact/notes sentinels in a signed-in internal detail",
           len(ctx.scanner.hits(internal.text_for_scan())) >= 2, ctx.scanner.hits(internal.text_for_scan())[:3])
    saved = dict(ctx.model)
    victim = next(iter(ctx.model))
    ctx.model.pop(victim)
    items = all_public(ctx)[0]
    ctx.ok("CONTROL", "catalog comparison detects a one-record discrepancy",
           victim in {t["id"] for t in items} and len(items) == len(saved))
    ctx.model = saved
    ctx.set_faults({"leak_control": True})
    try:
        n_bad = len(ctx.public_bad)
        pub(ctx, f"{PUB}/{ctx.id['M001']}", 200, "control")
        caught = ctx.public_bad[n_bad:]
        ctx.public_bad = ctx.public_bad[:n_bad]
        ctx.ev.results = [r for r in ctx.ev.results
                          if not (r["case"] == "PUBLIC" and r["status"] == "FAIL" and ctx.id["M001"] in r["check"])]
    finally:
        ctx.set_faults({})
    ctx.ok("CONTROL", "deliberate wrapper-injected contacto leak in public detail is caught (keys + sentinel)",
           bool(caught) and any("sentinels" in p for c in caught for p in c["problems"] if isinstance(p, dict))
           and any("keys" in p for c in caught for p in c["problems"] if isinstance(p, dict)), caught)
    ctx.ok("CONTROL", "control switched off again: same detail is clean",
           set(terr(pub(ctx, f"{PUB}/{ctx.id['M001']}"))) == L.PUBLIC_TERRAIN_KEYS)


# --------------------------------------------------------------------------- PRE-01 (negative + warnings)

def case_pre01(ctx: Ctx) -> None:
    C = "PRE-01"
    A, B = ctx.sess["A"], ctx.sess["B"]
    tid = ctx.id["M030"]
    t = get(ctx, A, tid)
    ok = preview(ctx, A, tid, t["draft_revision_id"])
    ctx.ok(C, "preview with the current saved revision_id -> 200", ok.status == 200
           and (ok.json or {}).get("revision_id") == t["draft_revision_id"], ok.status)
    anon = ctx.session("anon-preview")
    r = anon.get(f"{INV}/{tid}/vista-publica")
    ctx.ok(C, "preview cannot be fetched anonymously (401, no payload)", r.status == 401
           and not ctx.scanner.hits(r.text_for_scan()) and "terreno" not in (r.json or {}), r.status)
    old_rev = t["draft_revision_id"]
    s = save(ctx, B, tid, {"public_description": "Descripción revisada PRE01"})
    stale = preview(ctx, A, tid, old_rev)
    ctx.ok(C, "stale revision_id -> 409 revision_changed with current_version", stale.status == 409
           and code(stale) == "revision_changed"
           and (stale.json or {}).get("detalle", {}).get("current_version") == terr(s).get("version"),
           (stale.status, code(stale)))
    other = preview(ctx, A, tid, get(ctx, A, ctx.id["M031"])["draft_revision_id"])
    ctx.ok(C, "another record's revision_id -> 404", other.status == 404, other.status)
    rnd = preview(ctx, A, tid, str(uuid.uuid4()))
    ctx.ok(C, "random revision_id -> 404", rnd.status == 404, rnd.status)
    for extra in ("campos=contacto", "include_private=1", "version=1"):
        r = preview(ctx, A, tid, None, extra)
        ctx.ok(C, f"unknown preview query key ({extra}) -> 422", r.status == 422, r.status)
    r = A.get(f"{INV}/{uuid.uuid4()}/vista-publica")
    ctx.ok(C, "preview of a nonexistent record -> 404", r.status == 404, r.status)
    # private data never in the preview body (signed-in, but preview = visitor appearance)
    hits = {}
    for key in ("M001", "M020", "M023", "M030", "M101", "M110", "M118"):
        p = preview(ctx, A, ctx.id[key])
        h = ctx.scanner.hits(json.dumps(p.json, ensure_ascii=False))
        if h:
            hits[key] = h[:3]
    ctx.ok(C, "preview bodies carry no contact/notes/extra/actor sentinel", not hits, hits)
    # warnings: unconfirmed facts, price inconsistency, never fabricated confirmations
    w040 = [w.get("code") for w in (preview(ctx, A, ctx.id["M040"]).json or {}).get("warnings", [])]
    ctx.ok(C, "M040 total/unit inconsistency shown as a preview warning", "PRECIO_INCONSISTENTE" in w040, w040)
    g040 = terr(pub(ctx, f"{PUB}/{ctx.id['M040']}"))
    fx = ctx.master["M040"]["draft"]
    ctx.ok(C, "M040 published with its source amounts (no recalculation)",
           g040.get("asking_price") == fx["asking_price"] and g040.get("asking_m2") == fx["asking_m2"],
           (g040.get("asking_price"), g040.get("asking_m2")))
    w001 = [w.get("code") for w in (preview(ctx, A, ctx.id["M001"]).json or {}).get("warnings", [])]
    ctx.ok(C, "never-confirmed price and availability are preview warnings",
           {"price_unconfirmed", "availability_unconfirmed"} <= set(w001), w001)
    conf = get(ctx, A, ctx.id["M001"]).get("confirmations")
    ctx.ok(C, "publication does not fabricate confirmation dates", conf == {"price": None, "availability": None}, conf)
    # HTML-like and formula-like literals stay literal in preview and public
    lit = {}
    for key in ("M020", "M021", "M022", "M023", "M024", "M025", "M026"):
        p = (preview(ctx, A, ctx.id[key]).json or {}).get("terreno", {})
        g = terr(pub(ctx, f"{PUB}/{ctx.id[key]}"))
        if not (p.get("terreno") == g.get("terreno") == ctx.master[key]["draft"]["terreno"]):
            lit[key] = (p.get("terreno"), g.get("terreno"))
    ctx.ok(C, "HTML-like / formula-like names are literal in preview and public", not lit, lit)
    # cents and currency explicit
    g30, g31, g32 = (terr(pub(ctx, f"{PUB}/{ctx.id[k]}")) for k in ("M030", "M031", "M032"))
    ctx.ok(C, "USD 122.50/m2, MXN 3456.78/m2 and per-m2-only price keep cents and currency",
           (g30.get("asking_m2"), g30.get("moneda")) == (122.5, "USD")
           and (g31.get("asking_m2"), g31.get("moneda")) == (3456.78, "MXN")
           and g32.get("asking_price") is None and g32.get("asking_m2") == 85.25,
           [(g.get("asking_price"), g.get("asking_m2"), g.get("moneda")) for g in (g30, g31, g32)])
    g34 = terr(pub(ctx, f"{PUB}/{ctx.id['M034']}"))
    ctx.ok(C, "price-on-request public record: flag true, no amounts, no guessed currency",
           g34.get("price_on_request") is True and g34.get("asking_price") is None
           and g34.get("asking_m2") is None and g34.get("moneda") is None, g34)
    # history publish event 'at' == published_at for a sample
    db = DB(ctx)
    bad = []
    for key in ("M001", "M030", "M034", "P001", "P251"):
        tid2 = ctx.id[key]
        ev = [e for e in db.events(tid2) if e[1] == "publish"]
        if not ev or ev[-1][3] != get(ctx, A, tid2).get("published_at"):
            bad.append((key, ev[-1][3] if ev else None, get(ctx, A, tid2).get("published_at")))
    ctx.ok(C, "published_at == the stored publish event time (sample)", not bad, bad)


# --------------------------------------------------------------------------- PUB-01

def case_pub01(ctx: Ctx) -> None:
    C = "PUB-01"
    A, B, Cc = ctx.sess["A"], ctx.sess["B"], ctx.sess["C"]
    db = DB(ctx)
    draft = dict(ctx.master["M001"]["draft"], terreno="Lote Publicación Uno PUB01",
                 internal_notes="Nota privada SNTL-NOTE-PUB01-a1b2c3")
    ctx.scanner.known.add("SNTL-NOTE-PUB01-a1b2c3")
    tid = terr(create(ctx, A, draft, f"pub01-{ctx.stamp}"))["id"]
    n0 = (pub(ctx, PUB + "?limit=1").json or {}).get("total")
    ctx.ok(C, "new draft invisible anonymously: detail 404, absent from list and search",
           pub(ctx, f"{PUB}/{tid}", 404).status == 404
           and (pub(ctx, f"{PUB}?q={quote('Publicación Uno PUB01')}").json or {}).get("total") == 0, n0)
    r, info = publish_reviewed(ctx, B, tid)
    revA = info["preview"].get("revision_id")
    ctx.ok(C, "B publishes A's draft (equal powers)", r.status == 200 and terr(r).get("publication_state") == "published",
           r.status)
    ctx.ok(C, "list total +1 immediately after commit", (pub(ctx, PUB + "?limit=1").json or {}).get("total") == n0 + 1)
    pubA = terr(pub(ctx, f"{PUB}/{tid}"))
    # C saves revision B: public fields + private note
    t = get(ctx, Cc, tid)
    ch = {"terreno": "Lote Publicación Uno Revisado", "direccion": "Calle Revisión B 123",
          "asking_price": 1234567.89, "internal_notes": "Otra nota SNTL-NOTE-PUB01-d4e5f6"}
    ctx.scanner.known.add("SNTL-NOTE-PUB01-d4e5f6")
    rb = save(ctx, Cc, tid, ch, t["version"])
    tb = terr(rb)
    revB = tb.get("draft_revision_id")
    g = terr(pub(ctx, f"{PUB}/{tid}"))
    ctx.ok(C, "after saving B, public detail is still revision A (every field)", g == pubA and g.get("revision_id") == revA,
           {k: (pubA.get(k), g.get(k)) for k in pubA if pubA.get(k) != g.get(k)})
    li = [x for x in (pub(ctx, f"{PUB}?q={quote('Publicación Uno')}").json or {}).get("terrenos", []) if x["id"] == tid]
    ctx.ok(C, "public list item is revision A", li == [pubA], li)
    ctx.ok(C, "public search for B's new name finds nothing",
           (pub(ctx, f"{PUB}?q={quote('Uno Revisado')}").json or {}).get("total") == 0)
    pend = tb.get("pending_changes") or {}
    ctx.ok(C, "editor sees B pending: has_pending_changes and exact pending_changes",
           tb.get("has_pending_changes") is True and set(pend) == {"terreno", "direccion", "asking_price"}
           and pend["asking_price"] == {"published": pubA["asking_price"], "draft": 1234567.89}
           and pend["terreno"]["published"] == pubA["terreno"], pend)
    ctx.ok(C, "published pointer still A, draft pointer B",
           tb.get("published_revision_id") == revA and revB != revA, (tb.get("published_revision_id"), revA))
    ids_true = {x["id"] for x in internal_all(ctx, A, [("has_pending_changes", "true")])}
    ids_false = {x["id"] for x in internal_all(ctx, A, [("has_pending_changes", "false")])}
    ctx.ok(C, "internal filter has_pending_changes=true includes it, =false excludes it",
           tid in ids_true and tid not in ids_false, None)
    # private-only edit on a published record: nothing pending
    tid3 = ctx.id["M003"]
    before = terr(pub(ctx, f"{PUB}/{tid3}"))
    r3 = save(ctx, B, tid3, {"internal_notes": "Solo nota privada", "contacts": "Contacto nuevo privado"})
    t3 = terr(r3)
    ctx.ok(C, "private-only edit: version +1, has_pending_changes false, pending_changes {}",
           r3.status == 200 and t3.get("has_pending_changes") is False and t3.get("pending_changes") == {},
           (r3.status, t3.get("has_pending_changes"), t3.get("pending_changes")))
    ctx.ok(C, "private-only edit leaves the public record identical", terr(pub(ctx, f"{PUB}/{tid3}")) == before)
    # cannot publish another terrain's revision
    other_rev = get(ctx, A, ctx.id["M002"])["draft_revision_id"]
    tnow = get(ctx, A, tid)
    rx = action(ctx, A, tid, "publicar", {"expected_version": tnow["version"], "revision_id": other_rev})
    ctx.ok(C, "publish naming another terrain's revision -> 409 revision_changed, nothing changes",
           rx.status == 409 and code(rx) == "revision_changed" and unchanged(tnow, get(ctx, A, tid)), (rx.status, code(rx)))
    rr = action(ctx, A, tid, "publicar", {"expected_version": tnow["version"], "revision_id": str(uuid.uuid4())})
    ctx.ok(C, "publish naming a random revision -> 409 revision_changed", rr.status == 409 and code(rr) == "revision_changed",
           (rr.status, code(rr)))
    for extra in ({"changes": {"terreno": "Implícito"}}, {"actor_id": ctx.uid["C"]}, {"published_at": "2000-01-01"}):
        re_ = action(ctx, A, tid, "publicar", {"expected_version": tnow["version"], "revision_id": revB, **extra})
        ctx.ok(C, f"publish with extra key {list(extra)} -> 422 (no implicit save / spoof)",
               re_.status == 422 and code(re_) == "validation_failed" and unchanged(tnow, get(ctx, A, tid)), re_.status)
    rxo = action(ctx, A, tid, "publicar", {"expected_version": tnow["version"], "revision_id": revB},
                 origin="https://evil.example")
    ctx.ok(C, "cross-origin publish rejected (403), nothing changes", rxo.status == 403 and unchanged(tnow, get(ctx, A, tid)),
           rxo.status)
    # A publishes B
    rp, info = publish_reviewed(ctx, A, tid)
    gB = terr(pub(ctx, f"{PUB}/{tid}"))
    ctx.ok(C, "publish B: public shows revision B atomically (fields, revision_id, published_at)",
           rp.status == 200 and gB.get("revision_id") == revB and gB.get("terreno") == ch["terreno"]
           and gB.get("asking_price") == ch["asking_price"] and gB.get("published_at") == terr(rp).get("published_at")
           and gB.get("published_at") >= pubA.get("published_at"), (rp.status, gB.get("revision_id")))
    ctx.ok(C, "after publishing B nothing is pending", terr(rp).get("has_pending_changes") is False
           and terr(rp).get("pending_changes") == {})
    evs = [e for e in db.events(tid) if e[1] == "publish"]
    ctx.ok(C, "history: two publish events, actors from the sessions (B then A), revisions A then B",
           [(e[2], e[5]) for e in evs] == [(ctx.uid["B"], revA), (ctx.uid["A"], revB)],
           [(e[2], e[5]) for e in evs])
    cross = db.rows("SELECT COUNT(*) FROM inventory_terrain t JOIN inventory_revision r"
                    " ON r.id = t.published_revision_id WHERE r.inventory_id <> t.id")[0][0]
    ctx.ok(C, "database: no terrain's published pointer names another terrain's revision", cross == 0, cross)
    pubtables = [t for t in db.tables() if "publica" in t.lower() or "publication" in t.lower()]
    ctx.info(C, "separate publication tables present", pubtables or "none (projection from published revision)")
    ex = ctx.session("anon-export").post("/api/exportar", {"base_id": 1})
    ctx.ok(C, "exports remain private (anonymous /api/exportar -> 401)", ex.status == 401, ex.status)
    catalog_check(ctx, C, "PUB-01")


def internal_all(ctx: Ctx, s: L.Session, query: list) -> list[dict]:
    out, cursor = [], None
    for _ in range(50):
        q = query + [("limit", "250")] + ([("cursor", cursor)] if cursor else [])
        body = s.get(f"{INV}?{urlencode(q)}").json or {}
        out += body.get("terrenos", [])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return out


# --------------------------------------------------------------------------- PUB-02

def case_pub02(ctx: Ctx) -> None:
    C = "PUB-02"
    A = ctx.sess["A"]
    db = DB(ctx)
    targets = {k: {BLOCKER_CODES[b] for b in ctx.master[k]["expected_blockers"]}
               for k in ("M101", "M103", "M104", "M105", "M106", "M108", "M109", "M110")}
    # constructed: currency_required (price, then currency removed) and name_required
    t = terr(create(ctx, A, dict(ctx.master["M002"]["draft"], terreno="Moneda faltante PUB02"), f"pub02c-{ctx.stamp}"))
    r = save(ctx, A, t["id"], {"moneda": None})
    ctx.ok(C, "removing the currency of a priced draft saves (drafts may be incomplete)", r.status == 200, r.status)
    ctx.id["CUR"] = t["id"]
    targets["CUR"] = {"currency_required"}
    t = terr(create(ctx, A, dict(ctx.master["M003"]["draft"], terreno=None), f"pub02n-{ctx.stamp}"))
    ctx.id["NAME"] = t["id"]
    targets["NAME"] = {"name_required"}
    # price on request + amounts (M106 covers price_conflict); make one more from a priced record
    t = terr(create(ctx, A, dict(ctx.master["M004"]["draft"], price_on_request=True), f"pub02p-{ctx.stamp}"))
    ctx.id["POR+AMT"] = t["id"]
    targets["POR+AMT"] = {"price_conflict"}
    for key, want in targets.items():
        tid = ctx.id[key]
        before = get(ctx, A, tid)
        h0 = len(db.events(tid))
        pv = preview(ctx, A, tid).json or {}
        pcodes = {b.get("code") for b in pv.get("blockers", [])}
        r = action(ctx, A, tid, "publicar", {"expected_version": pv.get("version"), "revision_id": pv.get("revision_id")})
        det = (r.json or {}).get("detalle") or {}
        rcodes = {b.get("code") for b in det.get("blockers", [])}
        fields_ok = all(isinstance(b.get("field"), str) and b.get("message") for b in det.get("blockers", []))
        ctx.ok(C, f"{key}: preview blockers ⊇ {sorted(want)}; publish -> 422 publication_blocked with the same blockers",
               want <= pcodes and r.status == 422 and code(r) == "publication_blocked" and rcodes == pcodes and fields_ok,
               {"preview": sorted(pcodes), "status": r.status, "publish": sorted(rcodes)})
        ctx.ok(C, f"{key}: draft retained, nothing changed, no history, still not public",
               unchanged(before, get(ctx, A, tid)) and len(db.events(tid)) == h0
               and pub(ctx, f"{PUB}/{tid}", 404).status == 404, None)
    # price on request without amounts or currency publishes (M008 etc. in seed): explicit check
    t = terr(create(ctx, A, dict(ctx.master["M001"]["draft"], terreno="Precio a consultar PUB02", asking_price=None,
                                 asking_m2=None, moneda=None, price_on_request=True), f"pub02por-{ctx.stamp}"))
    r, _ = publish_reviewed(ctx, A, t["id"])
    g = terr(pub(ctx, f"{PUB}/{t['id']}"))
    ctx.ok(C, "price_on_request without amounts/currency publishes; public shows the flag, no amounts",
           r.status == 200 and g.get("price_on_request") is True and g.get("moneda") is None
           and g.get("asking_price") is None, (r.status, code(r)))
    # bad bodies (validation_failed, no change)
    tid = ctx.id["M050"]
    base = get(ctx, A, tid)
    v, rev = base["version"], base["draft_revision_id"]
    bodies = [("publicar", {}), ("publicar", {"expected_version": str(v), "revision_id": rev}),
              ("publicar", {"expected_version": v}), ("publicar", {"expected_version": v, "revision_id": ""}),
              ("publicar", {"expected_version": v, "revision_id": rev, "x": 1}),
              ("publicar", {"expected_version": 0, "revision_id": rev}),
              ("publicar", {"expected_version": True, "revision_id": rev}),
              ("despublicar", {"expected_version": v, "revision_id": rev}), ("despublicar", {}),
              ("archivar", {"expected_version": v, "motivo": "x"}), ("archivar", {"expected_version": None}),
              ("restaurar", {"expected_version": v, "republicar": True}), ("restaurar", {"expected_version": 1.5})]
    for verb, body in bodies:
        r = action(ctx, A, tid, verb, body)
        ctx.ok(C, f"{verb} {json.dumps(body)[:70]} -> 422 validation_failed, unchanged",
               r.status == 422 and code(r) == "validation_failed" and unchanged(base, get(ctx, A, tid)), (r.status, code(r)))
    for raw in (b"no es json", b"[1,2]", b'{"expected_version":'):
        r = A.request("POST", f"{INV}/{tid}/publicar", raw=raw, headers={"Content-Type": "application/json"})
        ctx.ok(C, f"malformed body {raw[:15]!r} -> 4xx, unchanged", 400 <= r.status < 500
               and unchanged(base, get(ctx, A, tid)), r.status)
    for verb in ("publicar", "despublicar", "archivar", "restaurar"):
        body = {"expected_version": 1, **({"revision_id": rev} if verb == "publicar" else {})}
        r1 = action(ctx, A, str(uuid.uuid4()), verb, body)
        r2 = action(ctx, A, "no-es-uuid", verb, body)
        ctx.ok(C, f"{verb} on unknown/malformed id -> 404", r1.status == 404 and r2.status == 404
               and code(r1) == "not_found", (r1.status, r2.status))
        an = ctx.session("anon-life").post(f"{INV}/{tid}/{verb}", body)
        ctx.ok(C, f"{verb} anonymous -> 401, unchanged", an.status == 401 and unchanged(base, get(ctx, A, tid)), an.status)
    catalog_check(ctx, C, "PUB-02")


# --------------------------------------------------------------------------- PUB-03

def case_pub03(ctx: Ctx) -> None:
    C = "PUB-03"
    A, B, Cc = ctx.sess["A"], ctx.sess["B"], ctx.sess["C"]

    def total() -> int:
        return (pub(ctx, PUB + "?limit=1").json or {}).get("total")

    def visible(tid: str) -> bool:
        """True only if BOTH detail and list show it; False only if NEITHER does; None if they disagree."""
        d = pub(ctx, f"{PUB}/{tid}", (200, 404)).status == 200
        in_list = any(x["id"] == tid for x in all_public(ctx)[0])
        return d if d == in_list else None

    def act(s: L.Session, tid: str, verb: str) -> L.Resp:
        r = action(ctx, s, tid, verb, {"expected_version": get(ctx, s, tid)["version"]})
        if r.status == 200 and not terr(r).get("public_visible"):
            ctx.model.pop(tid, None)
        return r

    # unpublish
    tid = ctx.id["M050"]
    n = total()
    r = act(A, tid, "despublicar")
    t = terr(r)
    ctx.ok(C, "unpublish: 200, state unpublished, public_visible false, pointer null",
           r.status == 200 and t.get("publication_state") == "unpublished" and t.get("public_visible") is False
           and t.get("published_revision_id") is None, (r.status, t.get("publication_state")))
    ctx.ok(C, "unpublish withdraws at commit: detail 404, absent from list, total -1",
           pub(ctx, f"{PUB}/{tid}", 404).status == 404 and visible(tid) is False and total() == n - 1)
    r = act(A, tid, "despublicar")
    ctx.ok(C, "unpublish again -> 409 invalid_state", r.status == 409 and code(r) == "invalid_state", (r.status, code(r)))
    r, _ = publish_reviewed(ctx, B, tid)
    ctx.ok(C, "explicit republish of the same saved revision makes it public again",
           r.status == 200 and visible(tid) is True and total() == n, r.status)
    # archive / restore
    r = act(Cc, tid, "archivar")
    t = terr(r)
    ctx.ok(C, "archive a published record: 200, state archived, withdrawn at commit",
           r.status == 200 and t.get("publication_state") == "archived" and t.get("archived_at")
           and pub(ctx, f"{PUB}/{tid}", 404).status == 404 and visible(tid) is False, (r.status, t.get("publication_state")))
    ctx.ok(C, "archived is hidden internally by default, shown with include_archived=true",
           tid not in {x["id"] for x in internal_all(ctx, A, [])}
           and tid in {x["id"] for x in internal_all(ctx, A, [("include_archived", "true")])})
    for verb in ("archivar", "despublicar"):
        r = act(A, tid, verb)
        ctx.ok(C, f"{verb} while archived -> 409 invalid_state", r.status == 409 and code(r) == "invalid_state",
               (r.status, code(r)))
    tv = get(ctx, A, tid)
    r = action(ctx, A, tid, "publicar", {"expected_version": tv["version"], "revision_id": tv["draft_revision_id"]})
    ctx.ok(C, "publish while archived -> 409 invalid_state, unchanged", r.status == 409 and code(r) == "invalid_state"
           and unchanged(tv, get(ctx, A, tid)), (r.status, code(r)))
    r = act(B, tid, "restaurar")
    t = terr(r)
    ctx.ok(C, "restore: 200, state unpublished (was published), NOT republished",
           r.status == 200 and t.get("publication_state") == "unpublished" and t.get("published_revision_id") is None
           and t.get("public_visible") is False and pub(ctx, f"{PUB}/{tid}", 404).status == 404 and visible(tid) is False,
           (r.status, t.get("publication_state"), t.get("published_revision_id")))
    r = act(B, tid, "restaurar")
    ctx.ok(C, "restore when not archived -> 409 invalid_state", r.status == 409 and code(r) == "invalid_state",
           (r.status, code(r)))
    r, _ = publish_reviewed(ctx, A, tid)
    ctx.ok(C, "after restore, an explicit publish is required and works", r.status == 200 and visible(tid) is True, r.status)
    # draft archive/restore
    dt = ctx.id["M101"]
    r1 = act(A, dt, "archivar")
    r2 = act(A, dt, "restaurar")
    ctx.ok(C, "archive+restore a never-published draft -> state draft, not public",
           r1.status == 200 and r2.status == 200 and terr(r2).get("publication_state") == "draft"
           and pub(ctx, f"{PUB}/{dt}", 404).status == 404, (r1.status, r2.status, terr(r2).get("publication_state")))
    r = act(A, dt, "despublicar")
    ctx.ok(C, "unpublish a draft -> 409 invalid_state", r.status == 409 and code(r) == "invalid_state", (r.status, code(r)))
    # sold / withdrawn
    for key, avail in (("M060", "sold"), ("M061", "withdrawn")):
        tid = ctx.id[key]
        before = terr(pub(ctx, f"{PUB}/{tid}"))
        r = save(ctx, A, tid, {"availability": avail})
        t = terr(r)
        ctx.ok(C, f"{key}: saving {avail} alone does not change the public record",
               terr(pub(ctx, f"{PUB}/{tid}")) == before and visible(tid) is True, None)
        ctx.ok(C, f"{key}: pending availability change is conspicuous (pending_changes.availability)",
               t.get("has_pending_changes") is True
               and t.get("pending_changes", {}).get("availability") == {"published": "available", "draft": avail},
               t.get("pending_changes"))
        w = [x.get("code") for x in (preview(ctx, B, tid).json or {}).get("warnings", [])]
        ctx.ok(C, f"{key}: preview warns leaves_catalog", "leaves_catalog" in w, w)
        n = total()
        r, _ = publish_reviewed(ctx, B, tid)
        t = terr(r)
        ctx.ok(C, f"{key}: publishing {avail} -> 200, state published, public_visible false",
               r.status == 200 and t.get("publication_state") == "published" and t.get("public_visible") is False,
               (r.status, t.get("publication_state"), t.get("public_visible")))
        ctx.ok(C, f"{key}: {avail} leaves public list and direct detail (404) at commit; total -1",
               pub(ctx, f"{PUB}/{tid}", 404).status == 404 and visible(tid) is False and total() == n - 1)
        ids_pv = {x["id"] for x in internal_all(ctx, A, [("public_visible", "false"), ("publication_state", "published")])}
        ctx.ok(C, f"{key}: internal filter public_visible=false&publication_state=published finds it", tid in ids_pv)
        hist = [e[1] for e in DB(ctx).events(tid)]
        ctx.ok(C, f"{key}: internal history retained (create..publish..update..publish)",
               hist[0] == "create" and hist.count("publish") == 2, hist)
        ctx.id[f"{avail.upper()}"] = tid
    # sold back to available
    tid = ctx.id["M060"]
    save(ctx, A, tid, {"availability": "available"})
    r, _ = publish_reviewed(ctx, A, tid)
    ctx.ok(C, "sold -> available republished returns to the catalog", r.status == 200 and visible(tid) is True, r.status)
    save(ctx, A, tid, {"availability": "sold"})
    publish_reviewed(ctx, A, tid)  # leave M060 sold for the ID-guessing case
    # negotiation visible + labelled
    g = terr(pub(ctx, f"{PUB}/{ctx.id['M005']}"))
    ctx.ok(C, "negotiation remains public with availability 'negotiation'", g.get("availability") == "negotiation", g)
    neg = {x["id"] for x in all_public(ctx)[0] if x["availability"] == "negotiation"}
    want_neg = {k for k, v in ctx.model.items() if v and v["availability"] == "negotiation"}
    ctx.ok(C, "the catalog lists exactly the negotiation records of the model (M005, M015 + 25 P fixtures)",
           neg == want_neg and {ctx.id["M005"], ctx.id["M015"]} <= neg and len(neg) == 27, len(neg))
    # never-published sold draft
    t = terr(create(ctx, A, dict(ctx.master["M007"]["draft"], terreno="Vendido sin publicar", availability="sold"),
                    f"pub03sold-{ctx.stamp}"))
    r, _ = publish_reviewed(ctx, A, t["id"])
    ctx.info(C, "publishing a never-published sold draft", (r.status, terr(r).get("publication_state"),
                                                            terr(r).get("public_visible")))
    ctx.ok(C, "a never-published sold record never appears publicly", pub(ctx, f"{PUB}/{t['id']}", 404).status == 404)
    ctx.id["SOLD-NEVER"] = t["id"]
    # Cache-Control on internal + lifecycle
    cc = {
        "preview": preview(ctx, A, ctx.id["M001"]).headers.get("Cache-Control"),
        "internal detail": A.get(f"{INV}/{ctx.id['M001']}").headers.get("Cache-Control"),
        "lifecycle 409": act(A, ctx.id["M001"], "restaurar").headers.get("Cache-Control"),
    }
    ctx.ok(C, "Cache-Control no-store on preview/internal/lifecycle responses",
           all("no-store" in (v or "") for v in cc.values()), cc)
    catalog_check(ctx, C, "PUB-03")


# --------------------------------------------------------------------------- CON-02

def race(fns: list) -> list[L.Resp]:
    barrier, out = threading.Barrier(len(fns)), [None] * len(fns)

    def run(i: int, fn) -> None:  # noqa: ANN001
        barrier.wait()
        out[i] = fn()
    th = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(fns)]
    [t.start() for t in th]
    [t.join() for t in th]
    return out


def contiguous(db: DB, tid: str, version: int) -> bool:
    return [e[0] for e in db.events(tid)] == list(range(1, version + 1))


def case_con02(ctx: Ctx) -> None:
    C = "CON-02"
    A, B, Cc = ctx.sess["A"], ctx.sess["B"], ctx.sess["C"]
    db = DB(ctx)
    tid = ctx.id["M070"]
    before_pub = terr(pub(ctx, f"{PUB}/{tid}"))
    pv = preview(ctx, A, tid).json or {}
    N, R = pv["version"], pv["revision_id"]
    h0 = len(db.events(tid))
    rb = save(ctx, B, tid, {"asking_price": 777777.77})
    r = action(ctx, A, tid, "publicar", {"expected_version": N, "revision_id": R})
    det = (r.json or {}).get("detalle") or {}
    ctx.ok(C, "A publishes reviewed {N,R} after B saved -> 409 conflict with current_version and terreno",
           r.status == 409 and det.get("code") == "conflict" and det.get("current_version") == N + 1
           and (det.get("terreno") or {}).get("version") == N + 1, (r.status, det.get("code"), det.get("current_version")))
    ctx.ok(C, "unseen change not published; public unchanged; only B's save in history",
           terr(pub(ctx, f"{PUB}/{tid}")) == before_pub and len(db.events(tid)) == h0 + 1 and rb.status == 200)
    r = action(ctx, A, tid, "publicar", {"expected_version": N + 1, "revision_id": R})
    ctx.ok(C, "fresh version but stale revision {N+1,R} -> 409 revision_changed, unchanged",
           r.status == 409 and code(r) == "revision_changed" and terr(pub(ctx, f"{PUB}/{tid}")) == before_pub,
           (r.status, code(r)))
    r, info = publish_reviewed(ctx, A, tid)
    R2, N2 = info["preview"]["revision_id"], info["preview"]["version"]
    ctx.ok(C, "re-review then publish -> B's change public", r.status == 200
           and terr(pub(ctx, f"{PUB}/{tid}")).get("asking_price") == 777777.77, r.status)
    h1 = len(db.events(tid))
    r1 = action(ctx, A, tid, "publicar", {"expected_version": N2, "revision_id": R2})
    r2 = action(ctx, A, tid, "publicar", {"expected_version": N2 + 1, "revision_id": R2})
    ctx.ok(C, "retrying the successful publish: old version -> 409 conflict; current version -> 409 invalid_state;"
           " no double-apply", r1.status == 409 and code(r1) == "conflict" and r2.status == 409
           and code(r2) == "invalid_state" and len(db.events(tid)) == h1, (r1.status, code(r1), r2.status, code(r2)))
    # every action under version checks (stale and future versions)
    for verb in ("despublicar", "archivar", "restaurar", "publicar"):  # each valid from the previous state
        cur = get(ctx, A, tid)
        h = len(db.events(tid))
        for bad in (cur["version"] - 1, cur["version"] + 3):
            body = {"expected_version": bad, **({"revision_id": cur["draft_revision_id"]} if verb == "publicar" else {})}
            r = action(ctx, B, tid, verb, body)
            ctx.ok(C, f"{verb} with expected_version {'stale' if bad < cur['version'] else 'future'} -> 409 conflict,"
                   " no partial change", r.status == 409 and code(r) == "conflict" and unchanged(cur, get(ctx, A, tid))
                   and len(db.events(tid)) == h, (r.status, code(r)))
        body = {"expected_version": cur["version"], **({"revision_id": cur["draft_revision_id"]} if verb == "publicar" else {})}
        r = action(ctx, B, tid, verb, body)
        ctx.ok(C, f"{verb} with the current version -> 200 and version +1", r.status == 200
               and terr(r).get("version") == cur["version"] + 1, (r.status, code(r)))
        if r.status == 200:
            if terr(r).get("public_visible"):
                ctx.model[tid] = dict(preview(ctx, A, tid).json["terreno"], published_at=terr(r)["published_at"])
            else:
                ctx.model.pop(tid, None)
        rr = action(ctx, B, tid, verb, body)
        ctx.ok(C, f"{verb} retried with its old version -> 409, not applied twice", rr.status == 409
               and get(ctx, A, tid)["version"] == cur["version"] + 1, rr.status)
    ctx.ok(C, "M070 event versions contiguous 1..version", contiguous(db, tid, get(ctx, A, tid)["version"]))
    # races
    trials = ctx.args.race_trials
    outcomes = {"publish_vs_save": [], "publish_vs_publish": [], "publish_vs_unpublish_vs_archive": []}
    reserved = {f"M{n:03d}" for n in (*range(1, 9), 15, 18, *range(20, 43), 50, 60, 61, 70, 80, 90, 99)}
    keys = [k for k, r in ctx.master.items() if r["intended_lifecycle"] == "published" and k not in reserved][:3 * trials]
    bad = []
    for i in range(trials):
        tid = ctx.id[keys[i]]
        save(ctx, Cc, tid, {"public_description": f"Carrera {i}"})
        pv = preview(ctx, A, tid).json
        N, R = pv["version"], pv["revision_id"]
        rp, rs = race([lambda: action(ctx, A, tid, "publicar", {"expected_version": N, "revision_id": R}),
                       lambda: B.patch(f"{INV}/{tid}", {"expected_version": N, "changes": {"direccion": f"Gana B {i}"}})])
        t = get(ctx, A, tid)
        g = pub(ctx, f"{PUB}/{tid}")
        st = (rp.status, rs.status)
        if st == (200, 409):
            ok = t["published_revision_id"] == R and terr(g).get("revision_id") == R \
                and terr(g).get("public_description") == f"Carrera {i}" and t["draft"]["direccion"] != f"Gana B {i}"
            ctx.model[tid] = dict(pv["terreno"], published_at=t["published_at"])
        elif st == (409, 200):
            ok = t["published_revision_id"] != R and terr(g).get("public_description") != f"Carrera {i}" \
                and t["draft"]["direccion"] == f"Gana B {i}" and code(rp) == "conflict"
        else:
            ok = False
        ok = ok and t["version"] == N + 1 and contiguous(db, tid, t["version"])
        outcomes["publish_vs_save"].append(st)
        if not ok:
            bad.append(("pvs", keys[i], st))
    for i in range(trials):
        tid = ctx.id[keys[trials + i]]
        save(ctx, Cc, tid, {"public_description": f"Doble {i}"})
        pv = preview(ctx, A, tid).json
        N, R = pv["version"], pv["revision_id"]
        n_pub = sum(1 for e in db.events(tid) if e[1] == "publish")
        out = race([lambda s=s: action(ctx, s, tid, "publicar", {"expected_version": N, "revision_id": R}) for s in (A, B, Cc)])
        st = sorted(r.status for r in out)
        t = get(ctx, A, tid)
        ok = st == [200, 409, 409] and sum(1 for e in db.events(tid) if e[1] == "publish") == n_pub + 1 \
            and t["version"] == N + 1 and t["published_revision_id"] == R and contiguous(db, tid, t["version"])
        ctx.model[tid] = dict(pv["terreno"], published_at=t["published_at"])
        outcomes["publish_vs_publish"].append(st)
        if not ok:
            bad.append(("pvp", keys[trials + i], st))
    for i in range(trials):
        tid = ctx.id[keys[2 * trials + i]]
        save(ctx, Cc, tid, {"public_description": f"Triple {i}"})
        pv = preview(ctx, A, tid).json
        N, R = pv["version"], pv["revision_id"]
        out = race([lambda: action(ctx, A, tid, "publicar", {"expected_version": N, "revision_id": R}),
                    lambda: action(ctx, B, tid, "despublicar", {"expected_version": N}),
                    lambda: action(ctx, Cc, tid, "archivar", {"expected_version": N})])
        st = [r.status for r in out]
        t = get(ctx, A, tid)
        g = pub(ctx, f"{PUB}/{tid}", (200, 404))
        win = ["publicar", "despublicar", "archivar"][st.index(200)] if st.count(200) == 1 else None
        expect_state = {"publicar": "published", "despublicar": "unpublished", "archivar": "archived"}.get(win)
        ok = sorted(st) == [200, 409, 409] and t["publication_state"] == expect_state and t["version"] == N + 1 \
            and ((g.status == 200 and terr(g).get("revision_id") == R) if win == "publicar" else g.status == 404) \
            and contiguous(db, tid, t["version"]) and db.events(tid)[-1][1] == {"publicar": "publish",
                                                                                  "despublicar": "unpublish",
                                                                                  "archivar": "archive"}.get(win)
        if win == "publicar":
            ctx.model[tid] = dict(pv["terreno"], published_at=t["published_at"])
        else:
            ctx.model.pop(tid, None)
        outcomes["publish_vs_unpublish_vs_archive"].append((win, st))
        if not ok:
            bad.append(("pua", keys[2 * trials + i], st, win))
    ctx.ok(C, f"races ({trials} trials each): exactly one winner, losers 409, coherent pointer/public/history",
           not bad, bad)
    ctx.info(C, "race outcomes", outcomes)
    if ctx.args.mode == "cloud":
        ctx.info(C, "limitation O-4/§9.5", "Postgres workspace advisory lock serializes requests: these races prove"
                 " compare-and-set, not overlapping transactions")
    catalog_check(ctx, C, "CON-02")


# --------------------------------------------------------------------------- FILTERS (§6, published fields only)

def model_match(t: dict, q: list[tuple[str, str]]) -> bool:
    d: dict[str, list[str]] = {}
    for k, v in q:
        d.setdefault(k, []).append(v)
    one = {k: v[-1] for k, v in d.items()}
    if d.get("estado") and t["estado"] not in d["estado"]:
        return False
    if d.get("municipio") and t["municipio"] not in d["municipio"]:
        return False
    a = t["superficie_m2"]
    if "area_min_m2" in one and (a is None or a < float(one["area_min_m2"])):
        return False
    if "area_max_m2" in one and (a is None or a > float(one["area_max_m2"])):
        return False
    mon = one.get("moneda")
    if mon and t["moneda"] != mon:
        return False
    if "price_min" in one or "price_max" in one:
        amt = t["asking_price" if one.get("price_basis", "total") == "total" else "asking_m2"]
        if amt is None:
            return False
        if "price_min" in one and amt < float(one["price_min"]):
            return False
        if "price_max" in one and amt > float(one["price_max"]):
            return False
    if one.get("q"):
        hay = fold(" ".join(str(t.get(n) or "") for n in ("terreno", "municipio", "estado", "direccion")))
        if fold(one["q"]) not in hay:
            return False
    return True


def case_filters(ctx: Ctx) -> None:
    C = "FILTERS"
    A = ctx.sess["A"]
    # draft-only values must not influence public filters/facets/search
    tid = ctx.id["M080"]
    pubv = terr(pub(ctx, f"{PUB}/{tid}"))
    new_m = "USD" if pubv["moneda"] == "MXN" else "MXN"
    r = save(ctx, A, tid, {"estado": "Tlaxcala Borrador", "municipio": "Municipio Borrador",
                           "terreno": "Nombre Borrador Único", "superficie_m2": 987654321.0,
                           "asking_price": 1.0, "moneda": new_m, "direccion": "Dirección Borrador"})
    ctx.ok(C, "M080 draft saved with different public fields (published revision unchanged)", r.status == 200, r.status)
    items = all_public(ctx)[0]
    body = pub(ctx, PUB + "?limit=1").json or {}
    ctx.ok(C, "draft-only estado/municipio absent from public facets",
           "Tlaxcala Borrador" not in body.get("facets", {}).get("estados", [])
           and "Municipio Borrador" not in body.get("facets", {}).get("municipios", []), body.get("facets"))
    checks = {
        "estado=draft value": ([("estado", "Tlaxcala Borrador")], False),
        "municipio=draft value": ([("municipio", "Municipio Borrador")], False),
        "q=draft name": ([("q", "Borrador Único")], False),
        "q=draft address": ([("q", "Dirección Borrador")], False),
        "area_min=draft area": ([("area_min_m2", "987654000")], False),
        f"moneda={new_m} price<=1 (draft)": ([("moneda", new_m), ("price_max", "1")], False),
        "estado=published value": ([("estado", pubv["estado"])], True),
        "q=published name": ([("q", pubv["terreno"])], True),
        f"moneda={pubv['moneda']} (published)": ([("moneda", pubv["moneda"])], True),
    }
    for label, (q, expect) in checks.items():
        got = any(x["id"] == tid for x in all_public(ctx, q)[0])
        ctx.ok(C, f"public filter on {label}: M080 {'included' if expect else 'excluded'}", got == expect, got)
    internal = any(x["id"] == tid for x in internal_all(ctx, A, [("estado", "Tlaxcala Borrador")]))
    ctx.info(C, "internal list filters on draft fields (estado=Tlaxcala Borrador finds M080)", internal)
    # model-based query matrix
    model = [v for v in ctx.model.values() if v]
    queries = [
        [], [("estado", "Querétaro")], [("estado", "Querétaro"), ("estado", "Jalisco")],
        [("estado", "Querétaro"), ("estado", "Jalisco"), ("municipio", "El Marqués")],
        [("q", "queretaro")], [("q", "ÑANDÚ")], [("q", "nandu")], [("q", "Ávila")], [("q", "avila camacho")],
        [("area_min_m2", "50000")], [("area_max_m2", "20000")], [("area_min_m2", "20000"), ("area_max_m2", "60000")],
        [("moneda", "USD")], [("moneda", "MXN")],
        [("moneda", "USD"), ("price_min", "1000000"), ("price_max", "20000000")],
        [("moneda", "MXN"), ("price_max", "100000000")],
        [("moneda", "USD"), ("price_basis", "per_m2"), ("price_min", "100"), ("price_max", "300")],
        [("moneda", "MXN"), ("price_basis", "per_m2"), ("price_min", "3000")],
        [("moneda", "USD"), ("price_basis", "per_m2"), ("price_max", "100")],
        [("estado", "Nuevo León"), ("moneda", "USD"), ("q", "lote")],
        [("estado", "Estado Inexistente")],
    ]
    bad = []
    for q in queries:
        items, resps = all_public(ctx, q)
        want = sorted(t["id"] for t in model if model_match(t, q))
        got = [t["id"] for t in items]
        if got != want or {(r.json or {}).get("total") for r in resps} != {len(want)}:
            bad.append({"q": q, "want": len(want), "got": len(got), "missing": sorted(set(want) - set(got))[:3],
                        "extra": sorted(set(got) - set(want))[:3]})
    ctx.ok(C, f"{len(queries)} filter combinations == verifier model over published values (membership, order, total)",
           not bad, bad[:4])
    # mixed currency
    usd = all_public(ctx, [("moneda", "USD")])[0]
    mxn = all_public(ctx, [("moneda", "MXN")])[0]
    por = [t for t in model if t["moneda"] is None]
    ctx.ok(C, "moneda=USD returns only USD, moneda=MXN only MXN; null-currency records in neither",
           all(t["moneda"] == "USD" for t in usd) and all(t["moneda"] == "MXN" for t in mxn)
           and not ({t["id"] for t in por} & {t["id"] for t in usd + mxn}) and len(por) > 0,
           {"usd": len(usd), "mxn": len(mxn), "null": len(por)})
    pr = all_public(ctx, [("moneda", "USD"), ("price_basis", "per_m2"), ("price_min", "0")])[0]
    ctx.ok(C, "USD per-m2 price filter excludes records with no per-m2 amount and other currencies",
           all(t["moneda"] == "USD" and t["asking_m2"] is not None for t in pr), len(pr))
    # facets
    fac = (pub(ctx, PUB + "?limit=1").json or {}).get("facets") or {}
    want_e = sorted({t["estado"] for t in model if t["estado"]}, key=fold)
    want_c = sorted({t["moneda"] for t in model if t["moneda"]})
    ctx.ok(C, "facets.estados complete over the published candidate set (not one page)",
           sorted(fac.get("estados", []), key=fold) == want_e, {"got": len(fac.get("estados", [])), "want": len(want_e)})
    ctx.ok(C, "facets.monedas == published currencies", sorted(fac.get("monedas", [])) == want_c, fac.get("monedas"))
    fq = (pub(ctx, f"{PUB}?limit=1&estado={quote('Querétaro')}&estado=Jalisco").json or {}).get("facets") or {}
    want_m = sorted({t["municipio"] for t in model if t["estado"] in ("Querétaro", "Jalisco") and t["municipio"]}, key=fold)
    ctx.ok(C, "facets.municipios narrowed to the selected estados", sorted(fq.get("municipios", []), key=fold) == want_m
           and sorted(fq.get("estados", []), key=fold) == want_e, {"got": fq.get("municipios"), "want": want_m})
    # 422s: invalid filters and private/unknown selectors
    bad422 = {}
    invalid = ["price_min=1", "price_max=5&price_basis=total", "moneda=EUR", "moneda=usd", "price_basis=m2&moneda=USD",
               "limit=0", "limit=251", "limit=abc", "limit=-1", "area_min_m2=abc", "area_min_m2=NaN",
               "area_max_m2=Infinity"]
    private = ["campos=contacto", "contacto=x", "contacts=x", "notas_internas=x", "internal_notes=x",
               "include_archived=true", "include_private=1", "publication_state=draft", "availability=sold",
               "attention=true", "public_visible=false", "has_pending_changes=true", "draft=1", "extra=1",
               "extra_json=1", "source_extra=1", "created_by=x", "updated_by=x", "fields=contacto", "select=*",
               "sort=asking_price", "order=desc", "expand=draft", "revision_id=x", "id=x", "q=a&debug=1"]
    for qs in invalid + private:
        r = pub(ctx, f"{PUB}?{qs}", 422)
        if r.status != 422 or code(r) != "validation_failed":
            bad422[qs] = (r.status, code(r))
    ctx.ok(C, f"{len(invalid)} invalid filters and {len(private)} private/unknown selectors -> 422 validation_failed",
           not bad422, bad422)
    neg_filters = {qs: pub(ctx, f"{PUB}?{qs}", (200, 422)).status for qs in ("price_min=-5&moneda=USD", "area_min_m2=-1")}
    ctx.info(C, "negative lower bounds (contract silent; harmless, equivalent to no bound)", neg_filters)
    ok = pub(ctx, f"{PUB}?limit=250")
    ctx.ok(C, "limit=250 accepted", ok.status == 200 and len((ok.json or {}).get("terrenos", [])) == min(250, len(model)))
    d = pub(ctx, PUB)
    ctx.ok(C, "default page size 100", len((d.json or {}).get("terrenos", [])) == min(100, len(model)))
    end = pub(ctx, f"{PUB}?cursor=ffffffff-ffff-ffff-ffff-ffffffffffff")
    ctx.ok(C, "cursor past the end -> empty page, next_cursor null, total unchanged",
           (end.json or {}).get("terrenos") == [] and (end.json or {}).get("next_cursor") is None
           and (end.json or {}).get("total") == len(model), end.json and {k: end.json[k] for k in ("total", "next_cursor")})
    pv_ids = {x["id"] for x in internal_all(ctx, A, [("public_visible", "true")])}
    ctx.ok(C, "internal filter public_visible=true == the public catalog's id set",
           pv_ids == {k for k, v in ctx.model.items() if v}, len(pv_ids))
    for bad in ("public_visible=yes", "has_pending_changes=2", "publication_state=borrador"):
        r = A.get(f"{INV}?{bad}")
        ctx.ok(C, f"internal list {bad} -> 422", r.status == 422, r.status)
    catalog_check(ctx, C, "FILTERS")


def case_page251(ctx: Ctx) -> None:
    C = "PAGE-251"
    pq = L.load_json(L.FIXTURES / "manifest.json")["canonical_cases"]["pagination_query"]
    q = [("estado", pq["estado"]), ("municipio", pq["municipio"]), ("q", pq["q"])]
    want = sorted(ctx.id[k] for k in ctx.pages)
    for limit, pages in ((100, [100, 100, 51]), (250, [250, 1])):
        items, resps = all_public(ctx, q, limit)
        ids = [t["id"] for t in items]
        facets = {json.dumps((r.json or {}).get("facets"), sort_keys=True) for r in resps}
        ctx.ok(C, f"limit={limit}: pages {pages}, 251 distinct ids == published P set, ascending, totals 251",
               [len((r.json or {}).get("terrenos", [])) for r in resps] == pages and ids == want
               and len(set(ids)) == 251 and {(r.json or {}).get("total") for r in resps} == {251}
               and (resps[-1].json or {}).get("next_cursor") is None,
               {"pages": [len((r.json or {}).get("terrenos", [])) for r in resps], "n": len(ids)})
        ctx.ok(C, f"limit={limit}: facets identical on every page", len(facets) == 1)
        cur = [(r.json or {}).get("next_cursor") for r in resps[:-1]]
        ctx.ok(C, f"limit={limit}: cursor == last id of the page", cur == [(r.json or {})["terrenos"][-1]["id"]
                                                                           for r in resps[:-1]], cur)
    # default limit, no explicit limit parameter
    r = pub(ctx, f"{PUB}?{urlencode(q)}")
    ctx.ok(C, "no limit parameter -> 100 items + cursor", len((r.json or {}).get("terrenos", [])) == 100
           and (r.json or {}).get("next_cursor"))
    # whole catalog > 250
    items, resps = all_public(ctx)
    ctx.ok(C, f"whole catalog ({len(items)} > 250) assembles across pages without duplicates",
           len(items) == len({t['id'] for t in items}) == len(ctx.model) and len(resps) >= 2, len(items))


# --------------------------------------------------------------------------- GUESS (uniform 404)

def nonpublic_ids(ctx: Ctx) -> dict[str, str]:
    A = ctx.sess["A"]
    out = {"draft M101": ctx.id["M101"], "draft M110": ctx.id["M110"], "unpublished M111": ctx.id["M111"],
           "unpublished M050?": None, "sold M060": ctx.id["M060"], "withdrawn M061": ctx.id["M061"],
           "never-published sold": ctx.id["SOLD-NEVER"], "random": str(uuid.uuid4())}
    if "ARCHIVED" not in ctx.id:  # deterministic: archive a published record
        tid = ctx.id["M099"]
        r = action(ctx, A, tid, "archivar", {"expected_version": get(ctx, A, tid)["version"]})
        if r.status == 200:
            ctx.model.pop(tid, None)
            ctx.id["ARCHIVED"] = tid
    out["archived"] = ctx.id.get("ARCHIVED")
    out.pop("unpublished M050?")
    return {k: v for k, v in out.items() if v}


def case_guess(ctx: Ctx) -> None:
    C = "GUESS"
    ids = nonpublic_ids(ctx)
    ctx.ok(C, "probe set covers draft, unpublished, archived, sold, withdrawn and random ids",
           {"archived", "sold M060", "withdrawn M061", "unpublished M111", "draft M101", "random"} <= set(ids), sorted(ids))
    bodies, heads = set(), set()
    for label, tid in ids.items():
        for variant in (tid, tid.upper(), tid.replace("-", ""), "{" + tid + "}", f"urn:uuid:{tid}"):
            r = pub(ctx, f"{PUB}/{quote(variant, safe='')}", 404, label)
            bodies.add(r.body)
            heads.add(tuple(sorted((k, v) for k, v in r.headers.items() if k.lower() not in ("date",))))
    for bad in ("abc", "1", "0", "null", "undefined", "-1", "%00", "..%2f..%2fbases", "x" * 300,
                str(uuid.uuid4()) + "x", "'%20OR%201=1--", "%E2%80%AE"):
        r = pub(ctx, f"{PUB}/{bad}", 404, "malformed")
        bodies.add(r.body)
        heads.add(tuple(sorted((k, v) for k, v in r.headers.items() if k.lower() not in ("date",))))
    ctx.ok(C, "every nonpublic/malformed id -> byte-identical uniform 404 body", len(bodies) == 1
           and json.loads(next(iter(bodies))) == UNIFORM_404, [b[:120] for b in bodies][:3])
    ctx.ok(C, "404 headers identical across those ids (except Date)", len(heads) == 1, len(heads))
    pid = next(k for k, v in ctx.model.items() if v)
    ctx.info(C, "published id alternate spellings (UUID normalization)",
             {v: pub(ctx, f"{PUB}/{quote(v, safe='')}", (200, 404)).status for v in (pid.upper(), pid.replace("-", ""))})
    r = pub(ctx, f"{PUB}/{pid}?campos=contacto", 422)
    ctx.ok(C, "public detail with a query selector -> 422", r.status == 422, r.status)
    r = pub(ctx, f"{PUB}/{ids['random']}?x=1", 422)
    ctx.info(C, "nonexistent id with query selector", r.status)


# --------------------------------------------------------------------------- LEAK (§5, blocking)

def case_leak(ctx: Ctx) -> None:
    C = "LEAK"
    ids = list(nonpublic_ids(ctx).values())
    # leak_audit probes /api/publico/terrenos/:id with these and expects 404: use non-public ids only.
    original = leak_audit.ids_for

    def ids_for(base, ev, users, manifest):  # noqa: ANN001, ANN202
        got = original(base, ev, users, manifest)
        return {"legacy": got["legacy"], "inventory": ids}
    leak_audit.ids_for = ids_for
    try:
        table = leak_audit.run(ctx.server.url, ctx.ev, ctx.scanner, [u for u in ctx.users if u["tag"] in "ABCX"],
                               None, ctx.args.app_root.resolve())
    finally:
        leak_audit.ids_for = original
    routes = leak_audit.registry(ctx.args.app_root.resolve())
    ctx.info(C, "final route registry", [f"{m} {p}" for m, p in routes])
    s2 = {("GET", "/api/inventario/terrenos/:id/vista-publica"), ("POST", "/api/inventario/terrenos/:id/publicar"),
          ("POST", "/api/inventario/terrenos/:id/despublicar"), ("POST", "/api/inventario/terrenos/:id/archivar"),
          ("POST", "/api/inventario/terrenos/:id/restaurar")}
    ctx.ok(C, "all Stage 2 routes present in the registry and audited", s2 <= set(routes), sorted(s2 - set(routes)))
    nonpub = [r for r in table if (r["method"], r["pattern"]) not in leak_audit.PUBLIC and r["pattern"] not in ("<shell>",)]
    ctx.ok(C, f"BLOCKING: every non-allowlisted anonymous probe got its expected status (401 except method/route edge"
           f" cases) and zero sentinels ({len(table)} probes)",
           all((r["anon_status"] == r["expected"] if isinstance(r["expected"], int) else r["anon_status"] in r["expected"])
               and not r["sentinel_hits"] for r in nonpub),
           [r for r in nonpub if r["sentinel_hits"]][:3])
    # published ids on every non-public inventory route + valid lifecycle bodies, anonymously
    anon = ctx.session("anon-published")
    A = ctx.sess["A"]
    pids = [k for k, v in ctx.model.items() if v][:5]
    rows = []
    for tid in pids:
        before = get(ctx, A, tid)
        for m, p in routes:
            if ":id" not in p or not p.startswith("/api/inventario"):
                continue
            body = None
            if m == "POST":
                body = {"expected_version": before["version"]}
                if p.endswith("publicar") and not p.endswith("despublicar"):
                    body["revision_id"] = before["draft_revision_id"]
            if m == "PATCH":
                body = {"expected_version": before["version"], "changes": {"terreno": "anon"}}
            r = anon.request(m, p.replace(":id", tid), body=body)
            rows.append((m, p, r.status, ctx.scanner.hits(r.text_for_scan())))
        after = get(ctx, A, tid)
        rows.append(("state", tid, unchanged(before, after), []))
    ctx.ok(C, "BLOCKING: published ids on every internal inventory route anonymously -> 401, no payload, no change",
           all((r[2] == 401 if r[0] != "state" else r[2]) and not r[3] for r in rows),
           [r for r in rows if (r[0] != "state" and r[2] != 401) or r[3] or (r[0] == "state" and not r[2])][:5])
    # Non-GET methods and path variants on the public routes (only GET is allowlisted, §3/§9.2).
    pid = pids[0]
    odd = {}
    for m in ("POST", "PATCH", "DELETE", "PUT"):
        for path in (PUB, f"{PUB}/{pid}"):
            r = anon.request(m, path, body={})
            odd[f"{m} {path[:40]}"] = (r.status, bool(ctx.scanner.hits(r.text_for_scan())))
    # PUT has no do_PUT in the stdlib handler -> 501 before any dispatch (same as Stage 1's accepted
    # HEAD/OPTIONS/PUT rule for /api/bases): no payload either way.
    ctx.ok(C, "BLOCKING: POST/PATCH/DELETE on public routes anonymously -> 401 (PUT -> stdlib 501), no payload",
           all((st == 401 or (k.startswith("PUT") and st == 501)) and not h for k, (st, h) in odd.items()), odd)
    variants = {}
    for path in (f"{PUB}/", f"{PUB}/{pid}/", f"{PUB}/{pid}/historial", f"{PUB}/{pid}/vista-publica",
                 f"{PUB}/{ids[0]}/", "/api/publico/terrenos.json", "/api/publico/terrenos%2F" + ids[0]):
        r = anon.get(path)
        variants[path.replace(pid, "<pub>").replace(ids[0], "<nonpub>")] = (r.status, bool(ctx.scanner.hits(r.text_for_scan())),
                                                                              sorted((r.json or {}).keys()) if isinstance(r.json, dict) else None)
    ctx.ok(C, "public path variants: no sentinel, nonpublic id never 200, unknown sub-paths 401",
           not any(h for _, h, _ in variants.values())
           and variants[f"{PUB}/<nonpub>/"][0] == 404
           and variants[f"{PUB}/<pub>/historial"][0] == 401 and variants[f"{PUB}/<pub>/vista-publica"][0] == 401,
           variants)
    hits = sum(len(r["sentinel_hits"]) for r in table)
    ctx.ok(C, "BLOCKING: total sentinel hits across the §5 audit == 0", hits == 0, hits)
    # after logout, private ids give nothing on public routes and the session is dead
    lo = ctx.session("A-logout")
    lo.login(ctx.user("A")["username"], ctx.user("A")["password"])
    lo.post("/api/logout")
    r = lo.get(f"{INV}/{pids[0]}/vista-publica")
    ctx.ok(C, "after logout preview -> 401", r.status == 401, r.status)


# --------------------------------------------------------------------------- O-5 generic 500

def case_o5(ctx: Ctx) -> None:
    C = "O-5"
    A = ctx.sess["A"]
    db = DB(ctx)
    tid = ctx.id["M090"]
    save(ctx, A, tid, {"public_description": "Cambio que fallará al publicar"})
    before = get(ctx, A, tid)
    before_pub = terr(pub(ctx, f"{PUB}/{tid}"))
    h0 = len(db.events(tid))
    ctx.set_faults({"event_ids": [tid]})
    ctx.info(C, "patched (verifier wrapper process only, §9.4)",
             "server.repo.inventario._event raises RuntimeError for inventory_id M090; "
             "server.repo.inventario.public_records raises when switched on; (SEED control only:"
             " public_get adds contacto). Candidate files untouched.")
    results = {}
    try:
        pv = preview(ctx, A, tid).json
        calls = {
            "publicar": lambda: action(ctx, A, tid, "publicar", {"expected_version": pv["version"], "revision_id": pv["revision_id"]}),
            "despublicar": lambda: action(ctx, A, tid, "despublicar", {"expected_version": before["version"]}),
            "archivar": lambda: action(ctx, A, tid, "archivar", {"expected_version": before["version"]}),
            "PATCH": lambda: save(ctx, A, tid, {"direccion": "nunca"}, before["version"]),
        }
        for name, fn in calls.items():
            r = fn()
            body = r.json or {}
            text = r.body.decode("utf-8", "replace")
            results[name] = r.status
            ctx.ok(C, f"{name} failing mid-transaction -> 500 with exactly the generic body",
                   r.status == 500 and body == {"error": body.get("error"), "detalle": {"code": "internal"}}
                   and body.get("error", "").startswith(GENERIC_500_PREFIX), (r.status, text[:200]))
            ctx.ok(C, f"{name}: no exception text, path, table name or traceback in the response",
                   not any(w in text for w in ("SNTL-FAULTEXC", "/srv/secret", "inventory_event", "Traceback",
                                               "RuntimeError", "verifier fault")), text[:200])
            ctx.ok(C, f"{name}: atomic rollback (version, pointers, archive, draft, history, public)",
                   unchanged(before, get(ctx, A, tid)) and len(db.events(tid)) == h0
                   and terr(pub(ctx, f"{PUB}/{tid}")) == before_pub, None)
        ctx.set_faults({"public_records": True})
        r = pub(ctx, PUB, 500, "fault")
        ctx.ok(C, "anonymous public list failure -> generic 500, no exception text",
               r.status == 500 and (r.json or {}).get("detalle") == {"code": "internal"}
               and "SNTL-FAULTEXC" not in r.body.decode("utf-8", "replace"), (r.status, r.body[:200]))
    finally:
        ctx.set_faults({})
    log = (ctx.run_dir / "server.log").read_text(errors="replace")
    ctx.ok(C, "exception text is logged server-side", "SNTL-FAULTEXC-S2" in log and "Traceback" in log)
    r, _ = publish_reviewed(ctx, A, tid)
    ctx.ok(C, "after the fault is removed the same publish succeeds with the same version", r.status == 200
           and terr(r).get("version") == before["version"] + 1, r.status)
    catalog_check(ctx, C, "fault injection")


# --------------------------------------------------------------------------- config.readOnly

def case_config(ctx: Ctx) -> None:
    C = "CONFIG"

    def ro() -> tuple:
        a = ctx.session("anon-cfg").get("/api/config").json or {}
        s = ctx.sess["A"].get("/api/config").json or {}
        return a.get("readOnly"), s.get("readOnly")
    ctx.ok(C, "readOnly false for anonymous and signed-in without ARA_MAP_READ_ONLY", ro() == (False, False), ro())
    ctx.server.extra_env["ARA_MAP_READ_ONLY"] = "1"
    ctx.server.restart()
    login_all(ctx)
    got = ro()
    ctx.ok(C, "readOnly true for both with ARA_MAP_READ_ONLY=1", got == (True, True), got)
    ctx.server.extra_env.pop("ARA_MAP_READ_ONLY")
    ctx.server.restart()
    login_all(ctx)
    ctx.ok(C, "readOnly false again after removing the variable", ro() == (False, False), ro())
    catalog_check(ctx, C, "restart")


# --------------------------------------------------------------------------- O-7 throttle

def raw_login(ctx: Ctx, username: str, password: str, source: str = "127.0.0.1", xff: str | None = None) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", ctx.args.port, timeout=30, source_address=(source, 0))
    body = json.dumps({"username": username, "password": password}).encode()
    h = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{ctx.args.port}",
         "Host": f"127.0.0.1:{ctx.args.port}"}
    if xff is not None:
        h["X-Forwarded-For"] = xff
    conn.request("POST", "/api/login", body=body, headers=h)
    r = conn.getresponse()
    r.read()
    conn.close()
    ctx.ev.log({"session": "throttle", "method": "POST", "path": "/api/login", "source": source, "xff": xff,
                "username": username, "status": r.status})
    return r.status


def case_o7(ctx: Ctx) -> None:
    C = "O-7"
    T, U = ctx.user("T"), ctx.user("U")
    db = DB(ctx)
    if ctx.args.mode == "local":
        def at(n: int) -> dict:
            return {"source": f"127.0.0.{n}"}
        ctx.info(C, "client identity", "local adapter: socket address; distinct loopback sources 127.0.0.2..9")
    else:
        def at(n: int) -> dict:
            return {"xff": f"203.0.113.{n}"}
        ctx.info(C, "client identity", "cloud adapter: first X-Forwarded-For entry (all requests from 127.0.0.1)")
    s = [raw_login(ctx, T["username"], "wrong-password-x", **at(2)) for _ in range(5)]
    six = raw_login(ctx, T["username"], T["password"], **at(2))
    ctx.ok(C, "5 failures for (T, client-2) -> correct password from client-2 is 429", s == [401] * 5 and six == 429,
           (s, six))
    other = raw_login(ctx, T["username"], T["password"], **at(3))
    ctx.ok(C, "the same login from another client is not locked out (200)", other == 200, other)
    ok_u = raw_login(ctx, U["username"], U["password"], **at(2))
    ctx.ok(C, "another login from the throttled client is not locked by T's 5 failures", ok_u == 200, ok_u)
    ctx.server.restart()
    login_all(ctx)
    ctx.ok(C, "throttle survives a server restart (stored in the shared database)",
           raw_login(ctx, T["username"], T["password"], **at(2)) == 429)
    # per-client cap across logins
    spray = [raw_login(ctx, f"nadie-{i}-{uuid.uuid4().hex[:4]}", "x" * 12, **at(4)) for i in range(20)]
    after = raw_login(ctx, U["username"], U["password"], **at(4))
    ctx.ok(C, "20 failures from one client across logins -> that client is paused (429 even for a valid login)",
           spray == [401] * 20 and after == 429, (spray[-3:], after))
    ctx.ok(C, "a different client can still sign in U", raw_login(ctx, U["username"], U["password"], **at(5)) == 200)
    if ctx.args.mode == "local":
        xs = [raw_login(ctx, U["username"], "wrong-password-y", source="127.0.0.6", xff=f"198.51.100.{i}") for i in range(5)]
        x6 = raw_login(ctx, U["username"], U["password"], source="127.0.0.6", xff="198.51.100.99")
        ctx.ok(C, "local adapter ignores X-Forwarded-For (rotating it does not escape the socket-address key)",
               xs == [401] * 5 and x6 == 429, (xs, x6))
    else:
        f = [raw_login(ctx, U["username"], "wrong-password-y", xff=f"203.0.113.7, 10.0.0.{i}") for i in range(5)]
        f6 = raw_login(ctx, U["username"], U["password"], xff="203.0.113.7")
        ctx.ok(C, "only the FIRST X-Forwarded-For entry identifies the client", f == [401] * 5 and f6 == 429, (f, f6))
        g = [raw_login(ctx, U["username"], "wrong-password-z", xff=f"no-es-ip-{i}") for i in range(5)]
        g6 = raw_login(ctx, U["username"], U["password"], xff="otro-valor-no-ip")
        ctx.ok(C, "non-IP X-Forwarded-For values are ignored (they share the socket-address key)",
               g == [401] * 5 and g6 == 429, (g, g6))
        g7 = raw_login(ctx, U["username"], U["password"], xff="198.51.100.1")
        ctx.ok(C, "a real IP X-Forwarded-For is a distinct client", g7 == 200, g7)
        ctx.info(C, "deployment note", "the cloud adapter trusts the first X-Forwarded-For entry; on Vercel the edge"
                 " overwrites it. Behind another proxy a client could rotate it to evade the per-client cap (developer"
                 " docstring says so). Not verifiable locally.")
    raw = db.rows("SELECT login, client FROM team_login_failure")
    leaked = [r for r in raw if any(ip in (r[1] or "") for ip in ("127.0.0.", "203.0.113.", "198.51.100."))]
    ctx.ok(C, "client addresses are not stored in clear in team_login_failure", not leaked and raw, len(raw))
    ctx.info(C, "design note", "no global per-login cap: failures for one login from many clients are bounded only"
             " per client (accepted O-7 trade-off: a stranger cannot lock out a known account)")


# --------------------------------------------------------------------------- main

def p(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("local", "cloud"), default="local")
    ap.add_argument("--port", type=int, default=8433)
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--race-trials", type=int, default=8)
    ap.add_argument("--keep-db", action="store_true")
    ap.add_argument("--app-root", type=Path, default=L.WORKSPACE)
    args = ap.parse_args()
    if args.mode == "cloud" and not os.environ.get("ARA_MAP_TEST_DATABASE_URL"):
        raise SystemExit("cloud mode: run under harness/pg_disposable_linux.sh")
    ctx = Ctx(args)
    print(f"[run] {ctx.run_dir}  db={ctx.db or 'postgres:55433'}", flush=True)
    wanted = [c for c in CASES if c in args.cases.split(",")]
    fns = {"SEED": case_seed, "PRE-01": case_pre01, "PUB-01": case_pub01, "PUB-02": case_pub02, "PUB-03": case_pub03,
           "CON-02": case_con02, "FILTERS": case_filters, "PAGE-251": case_page251, "GUESS": case_guess,
           "LEAK": case_leak, "O-5": case_o5, "CONFIG": case_config, "O-7": case_o7}
    summary = {}
    try:
        setup(ctx)
        if "SEED" not in wanted:
            wanted.insert(0, "SEED")
        for c in wanted:
            print(f"== {c}", flush=True)
            try:
                fns[c](ctx)
            except Exception as exc:  # noqa: BLE001
                import traceback
                ctx.ev.result(c, "case crashed", "FAIL", repr(exc) + " " + traceback.format_exc()[-800:])
        ctx.ok("PUBLIC", f"every anonymous public response clean: exact keys, eligible only, no-store, uniform 404,"
               f" zero sentinels ({ctx.public_count} responses)", not ctx.public_bad, ctx.public_bad[:3])
        log = (ctx.run_dir / "server.log").read_text(errors="replace")
        ctx.ok("ID-02", "no password in server/provisioning logs",
               not any(u["password"] in log + (ctx.run_dir / "provision.log").read_text(errors="replace")
                       for u in ctx.users))
    finally:
        ctx.server.stop()
        ctx.public_log.close()
        summary = {
            "mode": args.mode, "port": args.port, "db": str(ctx.db) if ctx.db else "postgres 127.0.0.1:55433",
            "fixture_hash": L.load_json(L.FIXTURES / "manifest.json")["fixture_hash_sha256"],
            "python": sys.version.split()[0], "race_trials": args.race_trials,
            "public_responses_scanned": ctx.public_count,
            "timings_ms": {k: {"n": len(v), "p50": p(v, .5), "p95": p(v, .95),
                               "mean": round(statistics.mean(v), 1) if v else None} for k, v in ctx.timings.items()},
            "counts": {s: sum(1 for r in ctx.ev.results if r["status"] == s)
                       for s in ("PASS", "FAIL", "WARN", "SKIP", "INFO")},
            "results": ctx.ev.results,
        }
        (ctx.run_dir / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        print(json.dumps(summary["counts"]), "->", ctx.run_dir / "results.json")
        if args.keep_db:
            print(f"[kept] {ctx.tmp}")
        else:
            shutil.rmtree(ctx.tmp, ignore_errors=True)
    return 1 if summary["counts"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
