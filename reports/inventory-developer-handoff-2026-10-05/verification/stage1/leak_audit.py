#!/usr/bin/env python3
"""ACCEPTANCE_MATRIX §5 anonymous leakage audit, over HTTP, against a loopback server.

* Enumerates the candidate's FINAL route registry (imports server.app in a
  sandboxed subprocess) instead of trusting a developer's list, and adds
  legacy, unknown and path-normalization probes.
* Every anonymous request outside the exact public allowlist must be 401 with
  no internal payload. Every anonymous response (JSON, HTML, headers, cookies,
  unzipped xlsx) is scanned: zero sentinel hits required.
* Allowlisted routes are checked for their exact shapes (PublicTerrain keys).
* Writes route_table.json (method, path, anon status, expected, hits, auth status).

Standalone (server already running, seeded):
  python3 leak_audit.py --url http://127.0.0.1:8433 [--legacy-manifest X.db.manifest.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aralib as L  # noqa: E402

PUBLIC = {("GET", "/api/config"), ("GET", "/api/session"), ("POST", "/api/login"),
          ("POST", "/api/logout"), ("GET", "/api/publico/terrenos"), ("GET", "/api/publico/terrenos/:id")}
KNOWN_LEGACY = [
    ("GET", "/api/bases"), ("GET", "/api/bases/:id"), ("GET", "/api/bases/:id/terrenos"),
    ("GET", "/api/mapas"), ("GET", "/api/mapas/:id"), ("GET", "/api/mapas/:id/terrenos"),
    ("GET", "/api/carpetas"), ("GET", "/api/formatos"), ("POST", "/api/exportar"),
    ("POST", "/api/importar/vista-previa"), ("POST", "/api/importar/confirmar"),
    ("POST", "/api/importar/analizar"), ("POST", "/api/importar/preparar"),
    ("GET", "/api/inventario/terrenos"), ("GET", "/api/inventario/terrenos/:id"),
    ("GET", "/api/inventario/terrenos/:id/historial"), ("GET", "/api/inventario/terrenos/:id/vista-publica"),
]
UNKNOWN = ["/api/nope", "/api/bases/1/secreto", "/api/inventario", "/api/inventario/terrenos/x/y/z",
           "/api/BASES", "/api//bases", "/api/bases/", "/api/./bases", "/api/bases%2F1",
           "/api/publico/terrenos/../../bases", "/api/publico/terrenos/..%2f..%2fbases",
           "/api/publico/../bases", "/api/config/../bases", "/api/session/../mapas/1/terrenos",
           "/api/bases?x=/api/config", "/api/publico/terrenosX", "/api/publico", "/api/exportar/"]
INV_TRICKS = ["/api/inventario/terrenos/", "/api/INVENTARIO/terrenos", "/api/inventario/terrenos;x=1",
              "/api/inventario//terrenos", "/api/inventario/terrenos%2f", "/api/inventario/terrenos?cursor=../..",
              "/api/inventario/terrenos/%2e%2e/%2e%2e/bases",
              "/api/inventario/terrenos?limit=250&campos=contacto"]
# Authority-form tricks: urlparse reads "//api/..." as host "api", so these may fall to the static
# shell. Acceptable only as non-JSON with zero sentinels.
# Likewise "/./api/..." and "/api%2f..." are not /api/ paths to the server and get the app shell.
SHELL_OK = ["//api/inventario/terrenos", "//api/bases/1/terrenos", "/./api/inventario/terrenos",
            "/api%2finventario%2fterrenos", "/./api/bases/1/terrenos"]
# Segment-encoded ids that the router (like any client) treats as one :id of the public detail route.
PUBLIC_DETAIL_SHAPED = {"/api/publico/terrenos/..%2f..%2fbases"}
EXTRA_GETS = ["/api/carpetas?tipo=bases", "/api/carpetas?tipo=mapas", "/api/bases/1/terrenos?ids=1",
              "/api/mapas/2/terrenos?capa=1", "/api/inventario/terrenos?limit=250&include_archived=true"]
EXPORT_BODIES = [{}, {"base_id": 1}, {"base_id": 1, "ids": []}, {"base_id": 1, "ids": [1, 2, 3]},
                 {"mapa_id": 1}, {"mapa_id": 2}, {"mapa_id": 3, "nombre": "x"}, {"base_id": "1"},
                 {"base_id": 2, "ids": list(range(1, 40))}]


def registry(app_root: Path = L.WORKSPACE) -> list[tuple[str, str]]:
    """(method, pattern) from the candidate's live router, imported in isolation."""
    code = ("import json, server.app as a; "
            "print(json.dumps([[r.method, r.pattern.pattern] for r in a.router._routes]))")
    with tempfile.TemporaryDirectory() as tmp:
        env = L.safe_env({"ARA_MAP_DB": str(Path(tmp) / "never.db")})
        out = subprocess.run([sys.executable, "-c", code], cwd=app_root, env=env,
                             capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise SystemExit(f"cannot enumerate router: {out.stderr[-500:]}")
    import re
    routes = []
    for method, rx in json.loads(out.stdout.strip().splitlines()[-1]):
        path = re.sub(r"\(\?P<(\w+)>[^)]*\)", r":\1", rx.strip("^$"))
        routes.append((method, path))
    return routes


def fill(pattern: str, ids: dict) -> list[str]:
    if ":" not in pattern:
        return [pattern]
    inv = pattern.startswith("/api/inventario") or pattern.startswith("/api/publico")
    values = ids["inventory"] if inv else ids["legacy"]
    out = []
    for v in values:
        path = "/".join(str(v) if seg.startswith(":") else seg for seg in pattern.split("/"))
        out.append(path)
    return out


def ids_for(base: str, ev: L.Evidence, users: list[dict], legacy_manifest: Path | None) -> dict:
    legacy = [1, 2, 3, 4, 999999]
    if legacy_manifest and legacy_manifest.exists():
        m = L.load_json(legacy_manifest)["ids"]
        legacy = sorted({*m["bases"].values(), *m["mapas"].values(), *m["carpetas"].values(), 999999})
    inv = [str(uuid.uuid4())]
    a = next(u for u in users if u["tag"] == "A")
    s = L.Session(base, "audit-A", ev)
    if s.login(a["username"], a["password"]).status == 200:
        cursor, seen = None, []
        while True:
            q = "/api/inventario/terrenos?limit=250&include_archived=true" + (f"&cursor={cursor}" if cursor else "")
            body = s.get(q).json or {}
            seen += [t.get("id") for t in body.get("terrenos", [])]
            cursor = body.get("next_cursor")
            if not cursor or len(seen) > 5000:
                break
        inv += [i for i in seen if i][:25]
        s.post("/api/logout")
    return {"legacy": legacy, "inventory": inv}


def run(base: str, ev: L.Evidence, scanner: L.Scanner, users: list[dict], manifest: Path | None,
        app_root: Path = L.WORKSPACE) -> list[dict]:
    C = "LEAK"
    ids = ids_for(base, ev, users, manifest)
    ev.result(C, "probe ids", "INFO", {"legacy": ids["legacy"], "inventory": len(ids["inventory"])})
    routes = registry(app_root)
    ev.result(C, "final registry enumerated", "INFO", len(routes))
    probes = sorted(set(routes) | set(KNOWN_LEGACY))
    anon = L.Session(base, "anon-audit", ev)
    table: list[dict] = []

    def probe(method: str, pattern: str, path: str, body: object = None, expect: object = 401) -> L.Resp:
        r = anon.request(method, path, body=body if body is not None else ({} if method != "GET" else None))
        hits = scanner.hits(r.text_for_scan())
        ok_status = r.status == expect if isinstance(expect, int) else r.status in expect
        row = {"method": method, "pattern": pattern, "path": path, "body": body, "anon_status": r.status,
               "expected": expect, "sentinel_hits": hits, "content_type": r.headers.get("Content-Type"),
               "cache_control": r.headers.get("Cache-Control")}
        table.append(row)
        tag = "[S1-blocking] " if "inventario" in path.lower() else ""
        row["stage1_blocking"] = bool(tag)
        ev.result(C, f"{tag}{method} {path}", "PASS" if ok_status and not hits else "FAIL",
                  None if ok_status and not hits else {"status": r.status, "hits": hits[:5]})
        return r

    anon.cookies.clear()
    # Reads first, destructive methods last: a broken boundary must not erase
    # the evidence the later read probes are looking for.
    jobs: list[tuple] = []
    for method, pattern in probes:
        if (method, pattern) in PUBLIC:
            continue
        for path in fill(pattern, ids):
            jobs.append((method, pattern, path, None, 401))
            if method == "GET":  # same path, other methods: never a bypass
                jobs += [(other, pattern, path, None, (401, 405)) for other in ("POST", "PATCH", "DELETE")]
    jobs += [("GET", path.split("?")[0], path, None, 401) for path in EXTRA_GETS]
    jobs += [("POST", "/api/exportar", "/api/exportar", b, 401) for b in EXPORT_BODIES]
    jobs.append(("GET", "/api/exportar", "/api/exportar", None, (401, 405)))
    jobs += [("GET", "<unknown>", path, None, (401, 404) if path in PUBLIC_DETAIL_SHAPED else 401)
             for path in UNKNOWN]
    jobs += [(m, "/api/bases", "/api/bases", None, (401, 405, 501)) for m in ("HEAD", "OPTIONS", "PUT")]
    jobs += [("GET", "<inv-trick>", path, None, 401) for path in INV_TRICKS]
    jobs += [("GET", "<shell>", path, None, (200, 401, 404)) for path in SHELL_OK]
    phase = {"GET": 0, "HEAD": 1, "OPTIONS": 1, "POST": 2, "PATCH": 3, "PUT": 3, "DELETE": 4}
    for method, pattern, path, body, expect in sorted(jobs, key=lambda j: phase[j[0]]):
        r = probe(method, pattern, path, body, expect)
        if pattern == "<shell>":
            is_json = "json" in (r.headers.get("Content-Type") or "")
            ev.result(C, f"{path} never yields API JSON anonymously", "FAIL" if r.status == 200 and is_json
                      else "PASS", {"status": r.status, "type": r.headers.get("Content-Type")})

    # Allowlist shapes.
    cfg = probe("GET", "/api/config", "/api/config", expect=200)
    ev.result(C, "config has no secret-looking keys", "PASS" if not any(
        w in json.dumps(cfg.json or {}).lower() for w in ("password", "secret", "database", "postgres")) else "FAIL",
        cfg.json)
    ses = probe("GET", "/api/session", "/api/session", expect=200)
    ev.result(C, "anonymous session is exactly {authenticated:false}",
              "PASS" if ses.json == {"authenticated": False} else "FAIL", ses.json)
    probe("POST", "/api/login", "/api/login", {"username": "nadie", "password": "x"}, expect=401)
    probe("POST", "/api/logout", "/api/logout", expect=(200, 204))
    lst = probe("GET", "/api/publico/terrenos", "/api/publico/terrenos", expect=(200, 404))
    if lst.status == 404:
        ev.result(C, "public catalog list", "SKIP", "route absent: Stage 2")
    else:
        body = lst.json or {}
        bad = [sorted(set(t) ^ L.PUBLIC_TERRAIN_KEYS) for t in body.get("terrenos", []) if set(t) != L.PUBLIC_TERRAIN_KEYS]
        ev.result(C, "public list envelope + exact PublicTerrain keys",
                  "PASS" if set(body) == L.LIST_ENVELOPE and not bad else "FAIL", {"envelope": sorted(body), "bad": bad[:3]})
        ev.result(C, "public list Cache-Control no-store",
                  "PASS" if "no-store" in (lst.headers.get("Cache-Control") or "") else "FAIL",
                  lst.headers.get("Cache-Control"))
        sel = probe("GET", "/api/publico/terrenos", "/api/publico/terrenos?campos=contacto&include_private=1",
                    expect=(200, 422))
        if sel.status != 422:
            ev.result(C, "public list rejects private-field selectors with 422", "WARN",
                      f"{sel.status}: Stage 1 placeholder; required by Stage 2 (INTEGRATION §6)")
    bodies = set()
    for tid in ids["inventory"]:
        r = probe("GET", "/api/publico/terrenos/:id", f"/api/publico/terrenos/{tid}", expect=404)
        bodies.add(r.body)
    ev.result(C, "non-public detail 404 bodies indistinguishable (draft vs nonexistent)",
              "PASS" if len(bodies) <= 1 else "FAIL", len(bodies))

    # Static app shell and assets.
    web = app_root / "web"
    for f in ["/", "/index.html", *("/" + str(p.relative_to(web)) for p in sorted(web.rglob("*"))
                                     if p.is_file() and p.suffix in (".html", ".js", ".css", ".json"))][:200]:
        r = anon.request("GET", f)
        hits = scanner.hits(r.text_for_scan())
        if hits or r.status >= 500:
            ev.result(C, f"static {f}", "FAIL", {"status": r.status, "hits": hits[:5]})
    ev.result(C, "static assets scanned", "INFO", "zero hits unless FAIL rows above")

    # Authenticated behaviour of the same legacy surfaces (should still work for the team).
    a = next(u for u in users if u["tag"] == "A")
    s = L.Session(base, "audit-A-auth", ev)
    if s.login(a["username"], a["password"]).status == 200:
        for row in table:
            if row["method"] == "GET" and row["pattern"] not in ("<unknown>",) and "/api/" in row["path"]:
                row["auth_status"] = s.get(row["path"]).status
        unk = s.get("/api/nope")
        ev.result(C, "signed-in unknown /api route -> 404 (§9.2)", "PASS" if unk.status == 404 else "FAIL",
                  unk.status)
        if manifest:
            exp = s.post("/api/exportar", {"base_id": ids["legacy"][0]})
            ev.result(C, "signed-in legacy export still works", "PASS" if exp.status == 200
                      and exp.body[:2] == b"PK" else "FAIL", exp.status)
        s.post("/api/logout")
        after = s.get("/api/bases")
        ev.result(C, "after logout the same client gets 401 on legacy reads",
                  "PASS" if after.status == 401 else "FAIL", after.status)
    (ev.path.parent / "route_table.json").write_text(json.dumps(table, ensure_ascii=False, indent=1, default=str))
    total_hits = sum(len(r["sentinel_hits"]) for r in table)
    ev.result(C, "sentinel hits across all anonymous responses == 0", "PASS" if total_hits == 0 else "FAIL",
              total_hits)
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8433")
    ap.add_argument("--legacy-manifest", type=Path, help="legacy manifest listing ids/sentinels")
    ap.add_argument("--out", type=Path, default=L.VERIFY / "runs" / "leak-standalone")
    ap.add_argument("--app-root", type=Path, default=L.WORKSPACE, help="source tree whose router is enumerated")
    args = ap.parse_args()
    base = L.require_loopback(args.url)
    users = L.users()
    ev = L.Evidence(args.out / "http.jsonl", [u["password"] for u in users])
    scanner = L.Scanner([u["password"] for u in users])
    if args.legacy_manifest:
        scanner.known.update(L.load_json(args.legacy_manifest)["sentinels"])
    run(base, ev, scanner, users, args.legacy_manifest, args.app_root.resolve())
    fails = [r for r in ev.results if r["status"] == "FAIL"]
    (args.out / "results.json").write_text(json.dumps(ev.results, ensure_ascii=False, indent=1, default=str))
    print(f"{len(fails)} FAIL -> {args.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
