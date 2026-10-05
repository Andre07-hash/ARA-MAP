#!/usr/bin/env python3
"""Stage 1 HTTP acceptance: ID-01, ID-02, INV-01, INV-02, INV-03, CON-01 (+ §5 LEAK).

Owns the server lifecycle: starts the candidate via serve_target.py on
127.0.0.1:<port> against a NEW temporary database (optionally a copy of a
legacy v7 workspace), provisions the three fictional users through the
backend's operations command (contract_map.json), runs the cases, writes
evidence to verification/runs/<stamp>-<mode>/ and exits 1 on any FAIL.

  python3 stage1_acceptance.py --mode local --port 8433 [--legacy]
  harness/pg_disposable.sh -- python3 stage1_acceptance.py --mode cloud --port 8433

Never targets anything but loopback; never touches the default local data.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
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
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aralib as L  # noqa: E402

INV = "/api/inventario/terrenos"
CASES = ("INV-01", "ID-01", "INV-02", "INV-03", "FAULT", "CON-01", "ID-02", "LEAK")
ROLE_KEYS = {"role", "roles", "rol", "is_admin", "admin", "permissions", "permisos", "is_staff"}
HASH_MARKERS = ("scrypt$", "$argon2", "pbkdf2", "password_hash", "$2b$", "\"salt\"")


# --------------------------------------------------------------------------- helpers

class Ctx:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = L.VERIFY / "runs" / f"{self.stamp}-{args.mode}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="ara-verify-"))
        self.users = L.users()
        self.secrets = [u["password"] for u in self.users]
        self.ev = L.Evidence(self.run_dir / "http.jsonl", self.secrets)
        self.scanner = L.Scanner(self.secrets)
        self.master = L.records()
        self.db = None
        if args.mode == "local":
            self.db = L.assert_disposable_path(self.tmp / "ara.db")
        self.legacy_manifest: Path | None = None
        if args.legacy:
            self.legacy_manifest = self.run_dir / "legacy.manifest.json"
            builder = [sys.executable, str(L.VERIFY / "legacy" / "build_legacy_v7.py")]
            if self.db:
                src_db = self.tmp / "legacy_src.db"
                subprocess.run(builder + ["--out", str(src_db)], check=True, env=L.safe_env())
                shutil.copy(str(src_db) + ".manifest.json", self.legacy_manifest)
                src = sqlite3.connect(src_db.as_uri() + "?mode=ro", uri=True)
                dst = sqlite3.connect(self.db)
                src.backup(dst)
                src.close()
                dst.close()
            else:
                subprocess.run(builder + ["--pg-url-env", "ARA_MAP_TEST_DATABASE_URL", "--manifest",
                                          str(self.legacy_manifest)], check=True)
        self.legacy_pw = "legacy-shared-" + uuid.uuid4().hex
        env = {**L.contract_map().get("server_extra_env", {}),
               L.contract_map()["legacy_edit_password_env"]: self.legacy_pw}
        self.server = L.Server(args.mode, args.port, self.db, self.run_dir / "server.log", env,
                               app_root=args.app_root.resolve(), public_edit_env=args.public_edit_env)
        self.sess: dict[str, L.Session] = {}
        self.uid: dict[str, str] = {}
        self.created: dict[str, str] = {}   # fixture key -> inventory id
        self.timings: dict[str, list[float]] = {"create": [], "patch": [], "get": []}
        self.all_bodies: list[str] = []

    def session(self, name: str) -> L.Session:
        return L.Session(self.server.url, name, self.ev)

    def user(self, tag: str) -> dict:
        return next(u for u in self.users if u["tag"] == tag)

    def ok(self, case: str, check: str, cond: bool, detail: object = None) -> bool:
        self.ev.result(case, check, "PASS" if cond else "FAIL", detail)
        return cond

    def track(self, r: L.Resp) -> L.Resp:
        self.all_bodies.append(r.body.decode("utf-8", "replace"))  # body only: Set-Cookie legitimately has the token
        return r


def terr(r: L.Resp) -> dict:
    body = r.json or {}
    return body.get("terreno") or {}


def create(ctx: Ctx, s: L.Session, draft: dict, key: str | None, extra: dict | None = None) -> L.Resp:
    payload = L.to_payload(draft)
    wrapper = L.contract_map().get("create_body_wrapper")
    body = {wrapper: payload} if wrapper else payload
    body.update(extra or {})
    headers = {"Idempotency-Key": key} if key is not None else {}
    r = ctx.track(s.post(INV, body, headers=headers))
    ctx.timings["create"].append(r.ms)
    return r


def get(ctx: Ctx, s: L.Session, tid: str) -> L.Resp:
    r = ctx.track(s.get(f"{INV}/{tid}"))
    ctx.timings["get"].append(r.ms)
    return r


def patch(ctx: Ctx, s: L.Session, tid: str, version: object, changes: dict, extra: dict | None = None) -> L.Resp:
    body = {"expected_version": version, "changes": L.to_payload(changes)} if version is not None \
        else {"changes": L.to_payload(changes)}
    body.update(extra or {})
    r = ctx.track(s.patch(f"{INV}/{tid}", body))
    ctx.timings["patch"].append(r.ms)
    return r


def history(ctx: Ctx, s: L.Session, tid: str) -> list:
    r = ctx.track(s.get(f"{INV}/{tid}/historial"))
    body = r.json or {}
    if isinstance(body, list):
        return body
    for k in ("eventos", "events", "historial", "history", "items"):
        if isinstance(body.get(k), list):
            return body[k]
    return []


def actor_ids(event: object, known: set[str]) -> set[str]:
    """Every known user id that appears anywhere under an actor/user-ish key of an event."""
    found: set[str] = set()

    def walk(o: object, actorish: bool) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, actorish or any(t in k.lower() for t in ("actor", "user", "usuario", "by")))
        elif isinstance(o, list):
            for v in o:
                walk(v, actorish)
        elif actorish and isinstance(o, str) and o in known:
            found.add(o)
    walk(event, False)
    return found


def keys_recursive(o: object) -> set[str]:
    if isinstance(o, dict):
        return set(o) | set().union(*(keys_recursive(v) for v in o.values())) if o else set()
    if isinstance(o, list):
        return set().union(*(keys_recursive(v) for v in o)) if o else set()
    return set()


def list_total(ctx: Ctx, s: L.Session) -> int | None:
    r = ctx.track(s.get(f"{INV}?limit=1&include_archived=true"))
    return (r.json or {}).get("total") if r.status == 200 else None


class Store:
    """Row counts of inventory/team tables in the disposable database (read-only)."""

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx

    def _conn(self, write: bool = False):  # noqa: ANN202
        if self.ctx.db:
            uri = self.ctx.db.as_uri() + ("" if write else "?mode=ro")
            return sqlite3.connect(uri, uri=True), "sqlite"
        import psycopg  # cloud mode only: the verifier's own cluster
        return psycopg.connect(os.environ["ARA_MAP_TEST_DATABASE_URL"], autocommit=True), "pg"

    def tables(self) -> list[str]:
        conn, kind = self._conn()
        try:
            q = ("SELECT name FROM sqlite_master WHERE type='table'" if kind == "sqlite" else
                 "SELECT table_schema||'.'||table_name FROM information_schema.tables"
                 " WHERE table_schema NOT IN ('pg_catalog','information_schema')")
            return [r[0] for r in conn.execute(q).fetchall()]
        finally:
            conn.close()

    def counts(self) -> dict[str, int]:
        names = [t for t in self.tables() if any(p in t.split(".")[-1] for p in ("inventory", "team", "idempot"))]
        conn, _ = self._conn()
        try:
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in names}
        finally:
            conn.close()

    def expire_sessions_of(self, user_id: str) -> str:
        """Set every session of one user to expired. Returns what was done (evidence)."""
        conn, kind = self._conn(write=True)
        try:
            for t in self.tables():
                if "session" not in t.split(".")[-1]:
                    continue
                if kind == "sqlite":
                    cols = [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({t})")]
                else:
                    schema, name = t.split(".")
                    cols = [tuple(r) for r in conn.execute(
                        "SELECT column_name, data_type FROM information_schema.columns"
                        " WHERE table_schema=%s AND table_name=%s", (schema, name)).fetchall()]
                exp = [c for c, _ in cols if "expir" in c.lower()]
                usr = [c for c, _ in cols if "user" in c.lower()]
                if not exp or not usr:
                    continue
                ph = "?" if kind == "sqlite" else "%s"
                sample = conn.execute(f"SELECT {exp[0]} FROM {t} LIMIT 1").fetchone()
                past = 1 if sample and isinstance(sample[0], (int, float)) else "2000-01-01T00:00:00+00:00"
                n = conn.execute(f"UPDATE {t} SET {exp[0]} = {ph} WHERE {usr[0]} = {ph}", (past, user_id))
                if kind == "sqlite":
                    conn.commit()
                return f"{t}.{exp[0]} := {past!r} for {usr[0]}=user ({n.rowcount} rows)"
            return ""
        finally:
            conn.close()


def legacy_cookie(password: str) -> str:
    """A cookie the PRE-CHANGE shared-password scheme (server/cloud_auth.py) would accept."""
    value = f"{int(time.time()) + 3600}.{uuid.uuid4().hex}"
    sig = hmac.new(password.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"


# --------------------------------------------------------------------------- setup

def legacy_preserved(ctx: Ctx, when: str = "after candidate's schema upgrade") -> None:
    """Early MIG-02 signal: the upgrade on start must leave every legacy table byte-identical."""
    sys.path.insert(0, str(L.VERIFY / "legacy"))
    import build_legacy_v7 as B
    want = L.load_json(ctx.legacy_manifest)["digest"]
    got = B.digest(ctx.db) if ctx.db else B.digest(pg_url=os.environ["ARA_MAP_TEST_DATABASE_URL"])
    diff = {t: (want[t], got.get(t)) for t in B.LEGACY_TABLES if want[t] != got.get(t)}
    ctx.ok("MIG-02(pre)", f"legacy tables identical {when}", not diff, diff or None)
    ctx.ev.result("MIG-02(pre)", "schema user_version", "INFO", (want["_user_version"], got["_user_version"]))


def log_scan(ctx: Ctx) -> None:
    """ID-02: no credentials or session tokens in server/provisioning logs."""
    text = "".join(f.read_text(errors="replace") for f in (ctx.run_dir / "server.log", ctx.run_dir / "provision.log")
                   if f.exists())
    tokens = [v for s in ctx.sess.values() for v in s.cookies.values() if v]
    found = [u["tag"] for u in ctx.users if u["password"] in text] + ["token" for t in tokens if t in text]
    ctx.ok("ID-02", "no password or live session token in server/provisioning logs", not found, found)


def setup(ctx: Ctx) -> None:
    if ctx.args.mode == "cloud":  # explicit-target schema command; ordinary requests never migrate
        cmd = L.contract_map()["schema_cmd_cloud"]
        for _ in range(2):  # second run proves it is repeat-safe
            L.run_ops(cmd, None, ctx.run_dir / "provision.log")
        L.run_ops(cmd + ["--check"], None, ctx.run_dir / "provision.log")
        ctx.ev.result("SETUP", "esquema.py applied twice and --check passed", "INFO")
    ctx.server.start()
    if ctx.legacy_manifest:
        legacy_preserved(ctx)
        ctx.scanner.known.update(L.load_json(ctx.legacy_manifest)["sentinels"])
    for u in ctx.users:
        if u["provision"]:
            L.provision(u, ctx.db, ctx.run_dir / "provision.log")
    for tag in "ABC":
        s = ctx.session(tag)
        u = ctx.user(tag)
        r = ctx.track(s.login(u["username"], u["password"]))
        if r.status != 200:
            raise SystemExit(f"login {tag} -> {r.status}; cannot continue")
        me = ctx.track(s.get("/api/session")).json or {}
        ctx.sess[tag], ctx.uid[tag] = s, (me.get("user") or {}).get("id")


# --------------------------------------------------------------------------- cases

def case_inv01(ctx: Ctx) -> None:
    """Round-trip all 120 master fixtures (A/B/C round-robin), cross-user edit, restart."""
    C = "INV-01"
    mismatches, rejected = {}, {}
    for i, (key, rec) in enumerate(ctx.master.items()):
        s = ctx.sess["ABC"[i % 3]]
        r = create(ctx, s, rec["draft"], f"inv01-{key}-{ctx.stamp}")
        if r.status not in (200, 201):
            rejected[key] = (r.status, (r.json or {}).get("detalle"))
            continue
        t = terr(r)
        ctx.created[key] = t.get("id")
        back = L.from_payload(t.get("draft") or {})
        sent = {k: v for k, v in rec["draft"].items()
                if k not in L.contract_map()["private_field_names"] or L.contract_map()["private_field_names"][k]}
        diff = {k: (v, back.get(k)) for k, v in sent.items() if back.get(k) != v}
        if diff:
            mismatches[key] = diff
    # BACKEND_RESPONSE deviation 5: a typed price needs a currency on save (M107 only).
    deviation = {k for k, (st, det) in rejected.items()
                 if k == "M107" and st == 422 and "moneda" in ((det or {}).get("fields") or {})}
    # M102 stores X/Y swapped: lat -100.39 is outside ±90, i.e. impossible, so §9.1 requires 422.
    impossible = {k for k, (st, det) in rejected.items()
                  if k == "M102" and st == 422 and "lat" in ((det or {}).get("fields") or {})}
    ctx.ok(C, "M102 (swapped X/Y => |lat|>90) refused at save with a lat field error (§9.1)",
           impossible == {"M102"}, rejected.get("M102") or "saved")
    ctx.ok(C, "every other fixture saves as a draft, incl. outside-Mexico/missing coordinates (§9.1)",
           not (set(rejected) - deviation - impossible),
           {k: rejected[k] for k in sorted(set(rejected) - deviation - impossible)})
    if deviation:
        ctx.ev.result(C, "M107 price without currency refused at save", "WARN",
                      "BACKEND_RESPONSE deviation 5 (pending supervisor confirmation); not counted as defect")
    ctx.ok(C, "round-trip values identical (accents, cents, literals, nulls, private fields)",
           not mismatches, mismatches or None)
    ctx.ok(C, "every create returned a distinct string id",
           len(set(ctx.created.values())) == len(ctx.created) and all(isinstance(v, str) for v in ctx.created.values()))
    states = {terr(get(ctx, ctx.sess["A"], ctx.created[k])).get("publication_state") for k in list(ctx.created)[:5]}
    ctx.ok(C, "new records are drafts", states == {"draft"}, states)

    # A creates, B corrects name/location, C reads on a fresh request.
    tid = ctx.created["M004"]
    v = terr(get(ctx, ctx.sess["B"], tid)).get("version")
    fix = {"terreno": "Lote Ávila Camacho M004 (corregido)", "lat": 20.6012, "lon": -100.3911}
    r = patch(ctx, ctx.sess["B"], tid, v, fix)
    ctx.ok(C, "B edits A's draft without import", r.status == 200, r.status)
    t = terr(get(ctx, ctx.sess["C"], tid))
    ctx.ok(C, "C sees B's saved values with the same stable id",
           t.get("id") == tid and all((t.get("draft") or {}).get(k) == v for k, v in fix.items()), t.get("draft"))
    before = {k: terr(get(ctx, ctx.sess["A"], ctx.created[k])) for k in ("M004", "M030", "M110") if k in ctx.created}
    ctx.server.restart()
    s = ctx.sess["C"]
    r = get(ctx, s, tid)
    if r.status == 401:
        ctx.ev.result(C, "session survives restart", "INFO", "401 after restart; re-login")
        for tag in "ABC":
            ctx.track(ctx.sess[tag].login(ctx.user(tag)["username"], ctx.user(tag)["password"]))
    after = {k: terr(get(ctx, ctx.sess["A"], ctx.created[k])) for k in before}
    ctx.ok(C, "records, versions and drafts identical after server restart", after == before,
           {k: (before[k].get("version"), after[k].get("version")) for k in before})
    ctx.ev.result(C, "source lineage on rename", "SKIP", "Stage 3 (adoption/provenance)")


def case_id01(ctx: Ctx) -> None:
    C = "ID-01"
    known = set(ctx.uid.values())
    ctx.ok(C, "three distinct user ids", len(known) == 3 and None not in known, ctx.uid)
    for tag in "ABC":
        me = ctx.track(ctx.sess[tag].get("/api/session")).json or {}
        ctx.ok(C, f"{tag}: /api/session has id+display_name and no role keys",
               me.get("authenticated") is True and set(me.get("user") or {}) == {"id", "display_name"}
               and not (keys_recursive(me) & ROLE_KEYS), me.keys())
    # Each user creates one record, spoofing another user's id in the body.
    recs = {}
    for tag, key, spoof in (("A", "M111", "B"), ("B", "M112", "C"), ("C", "M113", "A")):
        bogus = {f: ctx.uid[spoof] for f in ("actor_id", "created_by", "updated_by", "user_id")}
        r = create(ctx, ctx.sess[tag], ctx.master[key]["draft"], f"id01-{key}-{ctx.stamp}", bogus)
        if r.status == 422:
            ctx.ev.result(C, f"{tag}: spoofed actor fields rejected (422)", "PASS")
            r = create(ctx, ctx.sess[tag], ctx.master[key]["draft"], f"id01b-{key}-{ctx.stamp}")
        ctx.ok(C, f"{tag} creates {key}", r.status in (200, 201), r.status)
        recs[tag] = terr(r).get("id")
    expected: dict[str, list[str]] = {tag: [ctx.uid[tag]] for tag in "ABC"}
    for owner, tid in recs.items():
        for editor in "ABC":
            if editor == owner:
                continue
            s = ctx.sess[editor]
            ok_read = get(ctx, s, tid).status == 200
            v = terr(get(ctx, s, tid)).get("version")
            r = patch(ctx, s, tid, v, {"direccion": f"Editado por {editor}"},
                      {"actor_id": ctx.uid[owner], "updated_by": ctx.uid[owner]})
            if r.status == 422:
                r = patch(ctx, s, tid, v, {"direccion": f"Editado por {editor}"})
            ctx.ok(C, f"{editor} reads+edits {owner}'s record", ok_read and r.status == 200, r.status)
            if r.status == 200:
                expected[owner].append(ctx.uid[editor])
            # Server-controlled fields cannot be set through changes.
            v2 = terr(get(ctx, s, tid)).get("version")
            for bad in ({"actor_id": ctx.uid[owner]}, {"version": 999}, {"id": str(uuid.uuid4())},
                        {"published_revision_id": str(uuid.uuid4())}):
                r = ctx.track(s.patch(f"{INV}/{tid}", {"expected_version": v2, "changes": bad}))
                after = terr(get(ctx, s, tid))
                ctx.ok(C, f"changes {list(bad)} rejected without effect",
                       r.status == 422 and after.get("version") == v2 and after.get("id") == tid, r.status)
    for owner, tid in recs.items():
        events = history(ctx, ctx.sess["A"], tid)
        seen = sorted(a for e in events for a in actor_ids(e, known))
        ctx.ok(C, f"history of {owner}'s record attributes each event to the session user",
               seen == sorted(expected[owner]), {"expected": sorted(expected[owner]), "seen": seen,
                                                 "events": len(events)})
    total = {tag: list_total(ctx, ctx.sess[tag]) for tag in "ABC"}
    ctx.ok(C, "all three users see the same inventory total", len(set(total.values())) == 1, total)
    for action in ("archivar", "restaurar", "publicar", "despublicar"):
        tid = recs["A"]
        v = terr(get(ctx, ctx.sess["B"], tid)).get("version")
        r = ctx.track(ctx.sess["B"].post(f"{INV}/{tid}/{action}", {"expected_version": v}))
        if r.status in (404, 405):
            ctx.ev.result(C, f"cross-user {action}", "SKIP", f"route absent ({r.status}); later stage")
        else:
            ctx.ev.result(C, f"cross-user {action} (B on A's record)", "INFO", r.status)


def case_inv02(ctx: Ctx) -> None:
    C = "INV-02"
    st = Store(ctx)
    tid = ctx.created.get("M030")
    s = ctx.sess["B"]
    t0 = terr(get(ctx, s, tid))
    h0 = len(history(ctx, s, tid))
    r = patch(ctx, s, tid, t0.get("version"), {"asking_m2": 123.75, "moneda": "USD"})
    t1 = terr(r)
    events = history(ctx, s, tid)
    newest = json.dumps(events, ensure_ascii=False)
    ctx.ok(C, "valid edit adds one history entry", len(events) == h0 + 1, (h0, len(events)))
    ctx.ok(C, "history holds previous and new value, actor and time",
           "122.5" in newest and "123.75" in newest and ctx.uid["B"] in newest
           and any(k in newest for k in ("2026-", "T")), None)
    ctx.ok(C, "version +1 and new draft_revision_id",
           t1.get("version") == t0.get("version") + 1 and t1.get("draft_revision_id") != t0.get("draft_revision_id"),
           (t0.get("version"), t1.get("version")))
    base = terr(get(ctx, s, tid))
    c0, h1 = st.counts(), len(history(ctx, s, tid))
    for bad in ({"superficie_m2": "abc"}, {"moneda": "EUR"}, {"lat": "NaN"}, {"asking_price": "Infinity"},
                {"availability": "vendido-quizá"}, {"campo_inventado": 1}, {"price_on_request": "sí"},
                {"lat": 95.0}, {"lat": -90.5}, {"lon": 200.0}, {"superficie_m2": -5},
                {"extra": {"x": 1}}, {"contacto": "x" * 2001}):
        r = ctx.track(s.patch(f"{INV}/{tid}", {"expected_version": base.get("version"), "changes": bad}))
        now = terr(get(ctx, s, tid))
        ctx.ok(C, f"invalid {bad} -> 422, record untouched",
               r.status == 422 and now.get("version") == base.get("version")
               and now.get("draft") == base.get("draft"), r.status)
        if r.status == 422:
            det = (r.json or {}).get("detalle")
            ctx.ok(C, f"  422 carries {{error,detalle.code}} for {list(bad)}",
                   isinstance((r.json or {}).get("error"), str) and isinstance(det, dict) and "code" in det, det)
    ctx.ok(C, "rejected edits add no history", len(history(ctx, s, tid)) == h1)
    t103 = terr(get(ctx, s, ctx.created["M103"])) if "M103" in ctx.created else {}
    ctx.ok(C, "outside-Mexico pair saved and flagged location_invalid blocker (§9.1)",
           any(a.get("code") == "location_invalid" and a.get("kind") == "blocker" for a in t103.get("attention", [])),
           [a.get("code") for a in t103.get("attention", [])])
    ctx.ok(C, "rejected edits add no rows in inventory/team tables", st.counts() == c0, (c0, st.counts()))
    tmin = terr(get(ctx, s, ctx.created["M110"])) if "M110" in ctx.created else {}
    d = L.from_payload(tmin.get("draft") or {})
    nulls = ("estado", "municipio", "direccion", "superficie_m2", "lat", "lon", "asking_price", "asking_m2", "moneda")
    ctx.ok(C, "unknown values stay null (not 0/false/'')", tmin and all(d.get(k) is None for k in nulls),
           {k: d.get(k) for k in nulls})
    ctx.ok(C, "unknown availability stays 'unknown'", d.get("availability") == "unknown", d.get("availability"))
    ctx.ev.result(C, "rolled-back transaction leaves no partial write", "INFO", "see FAULT case (verifier fault injection)")


def case_inv03(ctx: Ctx) -> None:
    C = "INV-03"
    s, st = ctx.sess["A"], Store(ctx)
    draft = dict(ctx.master["M114"]["draft"], terreno="Idempotencia M114")
    n0 = list_total(ctx, s)
    for hdr in (None, ""):
        r = create(ctx, s, draft, hdr)
        ctx.ok(C, f"create with Idempotency-Key={hdr!r} refused", r.status in (400, 409, 422, 428), r.status)
    ctx.ok(C, "no record created without a key", list_total(ctx, s) == n0)
    key = f"inv03-{uuid.uuid4()}"
    r1 = create(ctx, s, draft, key)
    r2 = create(ctx, s, draft, key)
    t1, t2 = terr(r1), terr(r2)
    ctx.ok(C, "same key + same body -> original result",
           r1.status in (200, 201) and r2.status in (200, 201) and t1.get("id") == t2.get("id")
           and t1.get("draft_revision_id") == t2.get("draft_revision_id"), (r1.status, r2.status))
    ctx.server.restart()
    if (ctx.track(s.get("/api/session")).json or {}).get("authenticated") is not True:
        ctx.track(s.login(ctx.user("A")["username"], ctx.user("A")["password"]))
    r3 = create(ctx, s, draft, key)
    ctx.ok(C, "same key + same body after restart -> original id", terr(r3).get("id") == t1.get("id"), r3.status)
    r4 = create(ctx, s, dict(draft, terreno="Idempotencia distinta"), key)
    ctx.ok(C, "same key + different body -> 409", r4.status == 409, r4.status)
    ctx.ok(C, "exactly one record added so far", list_total(ctx, s) == (n0 or 0) + 1, (n0, list_total(ctx, s)))
    # Same key fired concurrently from separate sessions/connections.
    key2, barrier, out = f"inv03-race-{uuid.uuid4()}", threading.Barrier(5), []
    racers = [ctx.session(f"A-race{i}") for i in range(5)]
    for rs in racers:
        rs.cookies = dict(s.cookies)

    def fire(rs: L.Session) -> None:
        barrier.wait()
        out.append(create(ctx, rs, dict(draft, terreno="Carrera idempotente"), key2))
    threads = [threading.Thread(target=fire, args=(rs,)) for rs in racers]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = {terr(r).get("id") for r in out if r.status in (200, 201)}
    ctx.ok(C, "concurrent same-key creates yield one record", len(ids) == 1 and list_total(ctx, s) == (n0 or 0) + 2,
           {"statuses": sorted(r.status for r in out), "ids": len(ids)})
    rb = create(ctx, ctx.sess["B"], draft, key)
    ctx.ev.result(C, "same key reused by another user", "INFO", (rb.status, terr(rb).get("id") == t1.get("id")))
    rk = create(ctx, s, draft, f"inv03-other-{uuid.uuid4()}")
    ctx.ev.result(C, "new key + identical body (duplicate review is DUP-01, Stage 3)", "INFO",
                  (rk.status, (rk.json or {}).get("detalle")))
    ctx.ev.result(C, "store counts after INV-03", "INFO", st.counts())
    ctx.ev.result(C, "durable result committed with business write", "INFO", "see FAULT case (verifier fault injection)")


def relogin_all(ctx: Ctx) -> None:
    for tag in "ABC":
        if (ctx.track(ctx.sess[tag].get("/api/session")).json or {}).get("authenticated") is not True:
            ctx.track(ctx.sess[tag].login(ctx.user(tag)["username"], ctx.user(tag)["password"]))


def case_fault(ctx: Ctx) -> None:
    """INV-02/INV-03 rollback under verifier fault injection (serve_target.install_fault)."""
    C = "FAULT"
    marker = f"FAULT-INJECT-{uuid.uuid4().hex[:8]}"
    ctx.server.fault_marker = marker
    ctx.server.restart()
    relogin_all(ctx)
    ctx.ev.result(C, "patched", "INFO", "server.repo.inventario._event raises when event details contain "
                  f"{marker!r}; nothing else patched; candidate files untouched")
    s, st = ctx.sess["A"], Store(ctx)
    try:
        n0, c0 = list_total(ctx, s), st.counts()
        key = f"fault-{uuid.uuid4()}"
        draft = dict(ctx.master["M118"]["draft"], terreno=f"Lote {marker}")
        r = create(ctx, s, draft, key)
        ctx.ok(C, "create failing mid-transaction returns 5xx", r.status >= 500, r.status)
        ctx.ok(C, "failed create leaves no rows (terrain, revision, event, idempotency result)",
               st.counts() == c0 and list_total(ctx, s) == n0, (c0, st.counts()))
        r2 = create(ctx, s, dict(ctx.master["M118"]["draft"], terreno="Lote tras fallo"), key)
        ctx.ok(C, "same key is free afterwards (no orphan idempotency row): new body succeeds once",
               r2.status == 200 and list_total(ctx, s) == (n0 or 0) + 1, r2.status)
        tid = terr(r2).get("id")
        t0, h0, c1 = terr(get(ctx, s, tid)), len(history(ctx, s, tid)), st.counts()
        r3 = patch(ctx, s, tid, t0.get("version"), {"direccion": f"Calle {marker}"})
        t1 = terr(get(ctx, s, tid))
        ctx.ok(C, "save failing mid-transaction returns 5xx", r3.status >= 500, r3.status)
        ctx.ok(C, "failed save: version, draft pointer, history and row counts unchanged",
               t1.get("version") == t0.get("version") and t1.get("draft_revision_id") == t0.get("draft_revision_id")
               and len(history(ctx, s, tid)) == h0 and st.counts() == c1, (t0.get("version"), t1.get("version")))
        r4 = patch(ctx, s, tid, t0.get("version"), {"direccion": "Calle sin fallo"})
        ctx.ok(C, "a normal save with the same expected_version then succeeds (no stale claim)",
               r4.status == 200 and terr(r4).get("version") == t0.get("version") + 1, r4.status)
        ctx.ok(C, "5xx bodies carry no sentinel", not any(ctx.scanner.hits(x.body.decode("utf-8", "replace"))
                                                        for x in (r, r3)))
    finally:
        ctx.server.fault_marker = None
        ctx.server.restart()
        relogin_all(ctx)


def case_con01(ctx: Ctx) -> None:
    C = "CON-01"
    A, B, Cc = ctx.sess["A"], ctx.sess["B"], ctx.sess["C"]
    for label, a_change, b_change in (
        ("same field", {"direccion": "Versión de A"}, {"direccion": "Versión de B"}),
        ("different fields", {"superficie_m2": 15000.0}, {"municipio": "Querétaro"}),
        ("private note vs public field", {"internal_notes": "Nota de A SNTL-NOTE-CON01-000000"},
         {"terreno": "Nombre de B"}),
    ):
        tid = ctx.created["M115"]
        ta, tb = terr(get(ctx, A, tid)), terr(get(ctx, B, tid))
        n = ta.get("version")
        h0 = len(history(ctx, A, tid))
        ra = patch(ctx, A, tid, n, a_change)
        rb = patch(ctx, B, tid, tb.get("version"), b_change)
        now = terr(get(ctx, Cc, tid))
        ctx.ok(C, f"{label}: A saves N->N+1", ra.status == 200 and terr(ra).get("version") == n + 1, ra.status)
        ctx.ok(C, f"{label}: stale B -> 409 conflict", rb.status == 409
               and ((rb.json or {}).get("detalle") or {}).get("code") == "conflict", (rb.status, rb.json))
        d = L.from_payload(now.get("draft") or {})
        ctx.ok(C, f"{label}: no partial write from B, A's value kept",
               now.get("version") == n + 1 and all(d.get(k) == v for k, v in a_change.items())
               and not any(d.get(k) == v for k, v in b_change.items()), now.get("version"))
        ctx.ok(C, f"{label}: history +1 only", len(history(ctx, A, tid)) == h0 + 1)
        rb2 = patch(ctx, B, tid, terr(get(ctx, B, tid)).get("version"), b_change)
        ctx.ok(C, f"{label}: B reloads and deliberately saves", rb2.status == 200
               and terr(rb2).get("version") == n + 2, rb2.status)
    tid = ctx.created["M115"]
    t = terr(get(ctx, A, tid))
    ctx.ok(C, "version is an integer counter distinct from revision ids",
           isinstance(t.get("version"), int) and isinstance(t.get("draft_revision_id"), str)
           and str(t.get("version")) != t.get("draft_revision_id"), (t.get("version"), t.get("draft_revision_id")))
    for bad in (t["version"] + 5, None, "1"):
        r = patch(ctx, A, tid, bad, {"direccion": "nunca"})
        ctx.ok(C, f"expected_version={bad!r} refused", r.status in (409, 422)
               and terr(get(ctx, A, tid)).get("version") == t["version"], r.status)
    # Barrier race: three sessions, same expected version.
    n = terr(get(ctx, A, tid)).get("version")
    barrier, out = threading.Barrier(3), {}

    def fire(tag: str) -> None:
        barrier.wait()
        out[tag] = patch(ctx, ctx.sess[tag], tid, n, {"direccion": f"Carrera {tag}"})
    threads = [threading.Thread(target=fire, args=(tag,)) for tag in "ABC"]
    [th.start() for th in threads]
    [th.join() for th in threads]
    wins = [tag for tag, r in out.items() if r.status == 200]
    final = terr(get(ctx, A, tid))
    ctx.ok(C, "3-way race: exactly one 200, others 409, winner's value persisted",
           len(wins) == 1 and sorted(r.status for r in out.values()) == [200, 409, 409]
           and (final.get("draft") or {}).get("direccion") == f"Carrera {wins[0]}" and final.get("version") == n + 1,
           {t: r.status for t, r in out.items()})


def case_id02(ctx: Ctx) -> None:
    C = "ID-02"
    A, uA, X = ctx.sess["A"], ctx.user("A"), ctx.user("X")
    anon = ctx.session("anon-id02")
    bad_pw = ctx.track(anon.login(uA["username"], uA["password"] + "x"))
    no_user = ctx.track(anon.login(X["username"], X["password"]))
    ctx.ok(C, "wrong password -> 401", bad_pw.status == 401, bad_pw.status)
    ctx.ok(C, "unknown user -> 401, same message as wrong password (no enumeration)",
           no_user.status == 401 and (bad_pw.json or {}).get("error") == (no_user.json or {}).get("error"),
           ((bad_pw.json or {}).get("error"), (no_user.json or {}).get("error")))
    ctx.ok(C, "failed logins set no session cookie", not anon.cookies, list(anon.cookies))
    # Cookie attributes of a fresh login.
    fresh = ctx.session("A-fresh")
    r = ctx.track(fresh.login(uA["username"], uA["password"]))
    sc = " ".join(r.set_cookies)
    ctx.ok(C, "session cookie HttpOnly + SameSite", "httponly" in sc.lower() and "samesite" in sc.lower(), sc.split("=")[0])
    ctx.ev.result(C, "Secure attribute on loopback cookie", "INFO",
                  "present" if "secure" in sc.lower() else "absent (loopback test policy; production must assert Secure)")
    token = next(iter(fresh.cookies.values()), "")
    cname = next(iter(fresh.cookies), "")
    ctx.ok(C, "session cookie name as documented", cname == L.contract_map().get("session_cookie"), cname)
    # Forged / tampered / legacy shared-password cookies.
    for label, value in (("random", uuid.uuid4().hex * 2), ("tampered", token[:-1] + ("A" if token[-1:] != "A" else "B"))):
        f = ctx.session(f"forged-{label}")
        f.cookies = {cname: value}
        ctx.ok(C, f"{label} session cookie -> anonymous + 401 internal",
               (ctx.track(f.get("/api/session")).json or {}).get("authenticated") is False
               and ctx.track(f.get(INV)).status == 401)
    lg = ctx.session("legacy-cookie")
    lg.cookies = {"ara_editor": legacy_cookie(ctx.legacy_pw)}
    probes = [lg.get(INV), lg.get("/api/bases"), lg.post("/api/carpetas", {"tipo": "bases", "nombre": "x"}),
              create(ctx, lg, ctx.master["M116"]["draft"], f"legacy-{uuid.uuid4()}")]
    ctx.ok(C, "pre-change shared-password cookie grants nothing", all(p.status == 401 for p in probes),
           [p.status for p in probes])
    # Cross-origin mutations with a valid session.
    tid = ctx.created["M116"]
    v = terr(get(ctx, A, tid)).get("version")
    n0 = list_total(ctx, A)
    for origin in ("https://evil.example", "null", "http://127.0.0.1.evil.example"):
        rp = ctx.track(A.request("PATCH", f"{INV}/{tid}", {"expected_version": v, "changes": {"direccion": "x"}},
                                 origin=origin))
        rc = ctx.track(A.request("POST", INV, L.to_payload(ctx.master["M117"]["draft"]),
                                 headers={"Idempotency-Key": str(uuid.uuid4())}, origin=origin))
        ctx.ok(C, f"Origin {origin}: PATCH/POST rejected", rp.status in (401, 403) and rc.status in (401, 403),
               (rp.status, rc.status))
    lx = ctx.session("login-xorigin")
    rl = ctx.track(lx.request("POST", "/api/login", {"username": uA["username"], "password": uA["password"]},
                              origin="https://evil.example"))
    ctx.ok(C, "cross-origin login rejected, no cookie", rl.status in (401, 403) and not lx.cookies, rl.status)
    ctx.ok(C, "no write happened via cross-origin", terr(get(ctx, A, tid)).get("version") == v
           and list_total(ctx, A) == n0)
    # No open signup (anonymous and signed-in), then X still cannot sign in.
    statuses = {}
    for path in L.contract_map()["signup_probe_paths"]:
        body = {"username": X["username"], "password": X["password"], "display_name": X["display_name"]}
        statuses[path] = (ctx.track(anon.post(path, body)).status, ctx.track(A.post(path, body)).status)
    ctx.ok(C, "no signup endpoint accepts a new account", not any(200 <= s < 300 for p in statuses.values() for s in p),
           statuses)
    ctx.ok(C, "unprovisioned identity still cannot sign in",
           ctx.track(ctx.session("X").login(X["username"], X["password"])).status == 401)
    # Logout revokes server-side; a copied cookie is dead; logout idempotent.
    c1, c2 = ctx.session("C-1"), ctx.session("C-2")
    for s in (c1, c2):
        ctx.track(s.login(ctx.user("C")["username"], ctx.user("C")["password"]))
    copied = ctx.session("C-1-copy")
    copied.cookies = dict(c1.cookies)
    out = ctx.track(c1.post("/api/logout"))
    ctx.ok(C, "logout clears cookie", out.status in (200, 204) and not c1.cookies, out.set_cookies and "cleared")
    ctx.ok(C, "copied cookie after logout -> 401 internal read and write",
           ctx.track(copied.get(INV)).status == 401
           and patch(ctx, copied, tid, terr(get(ctx, A, tid)).get("version"), {"direccion": "zombie"}).status == 401)
    ctx.ev.result(C, "other session of same user after logout", "INFO", ctx.track(c2.get(INV)).status)
    again = ctx.track(ctx.session("anon-logout").post("/api/logout"))
    ctx.ok(C, "anonymous logout is idempotent (2xx)", 200 <= again.status < 300, again.status)
    # Expired session (disposable DB manipulation).
    try:
        done = Store(ctx).expire_sessions_of(ctx.uid["C"])
    except Exception as exc:  # noqa: BLE001 - reported as SKIP with reason
        done = f"error: {exc}"
    if done and not done.startswith("error"):
        ctx.ok(C, "expired session -> 401", ctx.track(c2.get(INV)).status == 401, done)
    else:
        ctx.ev.result(C, "expired session -> 401", "SKIP", done or "no session/expiry columns found")
    # Credential/session material never in bodies; no role fields anywhere.
    blob = "\n".join(ctx.all_bodies)
    leaks = [m for m in HASH_MARKERS if m in blob] + [f"password:{u['tag']}" for u in ctx.users if u["password"] in blob]
    tok = [n for n, s in ctx.sess.items() for v in s.cookies.values() if v and v in blob]
    ctx.ok(C, "no password, hash material or session token in any response body", not leaks and not tok,
           {"markers": leaks, "tokens_of": tok})
    cfg = ctx.track(anon.get("/api/config"))
    ctx.ok(C, "public config carries no secrets", not any(w in cfg.body.decode().lower()
           for w in ("password", "postgres", "database_url", "secret", "sntl-")), cfg.json)


def credential_changes(ctx: Ctx) -> None:
    """ID-02: password reset and deactivation (operations command) end existing sessions."""
    C = "ID-02"
    base = (L.contract_map()["provision_cmd"]["local" if ctx.db else "cloud"])[:4]
    log = ctx.run_dir / "provision.log"
    uB, uC = ctx.user("B"), ctx.user("C")
    b1 = ctx.session("B-reset")
    ctx.track(b1.login(uB["username"], uB["password"]))
    new_pw = uB["password"] + "-nuevo"
    ctx.secrets.append(new_pw)
    L.run_ops(base + ["--password-stdin", "restablecer", "{username}"], ctx.db, log, new_pw + "\n",
              username=uB["username"])
    ctx.ok(C, "password reset ends the user's existing session", ctx.track(b1.get(INV)).status == 401)
    ctx.ok(C, "old password refused after reset",
           ctx.track(ctx.session("B-old").login(uB["username"], uB["password"])).status == 401)
    ctx.ok(C, "new password accepted after reset",
           ctx.track(ctx.session("B-new").login(uB["username"], new_pw)).status == 200)
    c1 = ctx.session("C-deact")
    ctx.track(c1.login(uC["username"], uC["password"]))
    L.run_ops(base + ["desactivar", "{username}"], ctx.db, log, username=uC["username"])
    ctx.ok(C, "deactivation ends the user's existing session", ctx.track(c1.get(INV)).status == 401)
    r = ctx.track(ctx.session("C-after").login(uC["username"], uC["password"]))
    ctx.ok(C, "deactivated user cannot sign in (generic 401)", r.status == 401, r.status)
    acao = [json.loads(line).get("resp_headers", {}).get("Access-Control-Allow-Origin")
            for line in (ctx.run_dir / "http.jsonl").read_text().splitlines() if '"resp_headers"' in line]
    ctx.ok(C, "no response grants cross-origin reads (Access-Control-Allow-Origin absent)",
           not any(acao), sorted({a for a in acao if a}))


def rate_limit_probe(ctx: Ctx) -> None:
    C = "ID-02"
    X = ctx.user("X")
    s = ctx.session("bruteforce")
    statuses = [ctx.track(s.login(X["username"], f"wrong-{i}")).status for i in range(25)]
    ctx.ok(C, "repeated failed logins never succeed; throttled or uniformly 401",
           all(st in (401, 429) for st in statuses), statuses)
    ctx.ev.result(C, "throttle engaged", "INFO", f"429 seen: {429 in statuses}")
    r = ctx.track(ctx.session("A-after-bf").login(ctx.user("A")["username"], ctx.user("A")["password"]))
    ctx.ev.result(C, "other user can still sign in from same address after X's failures", "INFO", r.status)


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
    ap.add_argument("--legacy", action="store_true", help="start from a fictional schema-v7 workspace")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--keep-db", action="store_true", help="keep the temporary database for inspection")
    ap.add_argument("--app-root", type=Path, default=L.WORKSPACE, help="candidate source tree")
    ap.add_argument("--public-edit-env", action="store_true", help="run the server with ARA_MAP_PUBLIC_EDIT=1")
    args = ap.parse_args()
    if args.mode == "cloud" and not os.environ.get("ARA_MAP_TEST_DATABASE_URL"):
        raise SystemExit("cloud mode: run under harness/pg_disposable.sh")
    ctx = Ctx(args)
    print(f"[run] {ctx.run_dir}  db={ctx.db or 'postgres:55433'}", flush=True)
    wanted = [c for c in CASES if c in args.cases.split(",")]
    try:
        setup(ctx)
        fns = {"INV-01": case_inv01, "ID-01": case_id01, "INV-02": case_inv02, "INV-03": case_inv03,
               "FAULT": case_fault,
               "CON-01": case_con01, "ID-02": case_id02}
        for c in wanted:
            if c in fns:
                if c != "INV-01" and not ctx.created and "INV-01" not in wanted:
                    case_inv01(ctx)  # later cases need the seeded records
                print(f"== {c}", flush=True)
                try:
                    fns[c](ctx)
                except Exception as exc:  # noqa: BLE001 - recorded as a failure, run continues
                    ctx.ev.result(c, "case crashed", "FAIL", repr(exc))
        if "LEAK" in wanted:
            import leak_audit
            print("== LEAK", flush=True)
            leak_audit.run(ctx.server.url, ctx.ev, ctx.scanner, ctx.users, ctx.legacy_manifest,
                           args.app_root.resolve())
        if "ID-02" in wanted:
            credential_changes(ctx)
            rate_limit_probe(ctx)
            log_scan(ctx)
        if ctx.legacy_manifest:
            legacy_preserved(ctx, "at end of run (after anonymous mutation/delete probes)")
    finally:
        ctx.server.stop()
        summary = {
            "mode": args.mode, "port": args.port, "public_edit_env": args.public_edit_env, "db": str(ctx.db) if ctx.db else "postgres 127.0.0.1:55433",
            "legacy": bool(args.legacy),
            "fixture_hash": L.load_json(L.FIXTURES / "manifest.json")["fixture_hash_sha256"],
            "contract_map_sha256": hashlib.sha256(L.CONTRACT_MAP.read_bytes()).hexdigest(),
            "python": sys.version.split()[0],
            "timings_ms": {k: {"n": len(v), "p50": p(v, .5), "p95": p(v, .95),
                               "mean": round(statistics.mean(v), 1) if v else None}
                           for k, v in ctx.timings.items()},
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
