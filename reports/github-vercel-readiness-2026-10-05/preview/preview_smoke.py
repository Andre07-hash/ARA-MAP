#!/usr/bin/env python3
"""Smoke-test a REAL Vercel Preview deployment of ARA Map, with fictional data.

Run on a machine that can reach the deployment (the supervisor's Mac), from a
checkout of the repository:

    export ARA_PREVIEW_PASSWORD=...          # a FICTIONAL Preview account; never on argv
    export VERCEL_AUTOMATION_BYPASS_SECRET=... # only if Deployment Protection is on
    python3 reports/github-vercel-readiness-2026-10-05/preview/preview_smoke.py \
        --url https://<preview>.vercel.app --commit <sha> --user <fictional login> \
        --out reports/github-vercel-readiness-2026-10-05/preview/run-<sha7>

It refuses the production alias and anything that is not *.vercel.app. It
creates a fictional base (from tests/fixtures), a saved map and an inventory
draft, all named "Ensayo Preview <stamp>", and leaves them for inspection
unless --cleanup is given. results.json contains statuses, counts and hashes
only: no cookie, password or secret.

Checks: served by Vercel; static files byte-identical to <commit>; anonymous
policy; sign-in; bases and map data; .xlsx import (openpyxl on Vercel); saved
map; .xlsx export; persistence across a second, independent session; logout
revocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_HOSTS = {"ara-map-ivory.vercel.app"}
results: list[dict] = []


def record(step: str, ok: bool, detail: object = None) -> None:
    results.append({"step": step, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {step}" + (f"  {detail}" if detail is not None else ""), flush=True)


class Client:
    def __init__(self, base: str, bypass: str | None) -> None:
        self.base = base.rstrip("/")
        self.bypass = bypass
        self.cookie: str | None = None

    def call(self, method: str, path: str, body: object = None, raw: bytes | None = None,
             headers: dict | None = None) -> tuple[int, object, dict]:
        hdrs = {"Accept": "application/json", "Origin": self.base, **(headers or {})}
        if self.bypass:
            hdrs["x-vercel-protection-bypass"] = self.bypass
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                status, payload, h = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, payload, h = e.code, e.read(), dict(e.headers)
        ctype = h.get("Content-Type", "")
        parsed = json.loads(payload) if "json" in ctype and payload else payload
        return status, parsed, h

    def login(self, user: str, password: str) -> tuple[int, dict]:
        status, body, h = self.call("POST", "/api/login", {"username": user, "password": password})
        if status == 200:
            self.cookie = h.get("Set-Cookie", "").split(";")[0]
        return status, h


def git_file(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
                          capture_output=True, check=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password-env", default="ARA_PREVIEW_PASSWORD")
    ap.add_argument("--bypass-env", default="VERCEL_AUTOMATION_BYPASS_SECRET")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--selftest-loopback", action="store_true",
                    help="developer self-test against a local cloud adapter on 127.0.0.1 only")
    args = ap.parse_args()

    host = urlsplit(args.url).hostname or ""
    if args.selftest_loopback:
        if host != "127.0.0.1":
            raise SystemExit("REFUSING: --selftest-loopback is for 127.0.0.1 only")
    elif host in PRODUCTION_HOSTS or not host.endswith(".vercel.app") or urlsplit(args.url).scheme != "https":
        raise SystemExit("REFUSING: give an https://<preview>.vercel.app URL, never the production alias")
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Set {args.password_env} (fictional Preview account) in the environment")
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", args.commit],
                            capture_output=True, text=True, check=True).stdout.strip()
    args.out.mkdir(parents=True, exist_ok=False)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    a = Client(args.url, os.environ.get(args.bypass_env))

    # Served by Vercel, from this commit.
    status, index, h = a.call("GET", "/")
    record("served by Vercel", status == 200 and "x-vercel-id" in {k.lower() for k in h},
           {"status": status, "x-vercel-id": h.get("x-vercel-id") or h.get("X-Vercel-Id")})
    same = {}
    for path in ("web/index.html", "web/components/app.js", "web/lib/api.js", "web/styles/global.css"):
        served = a.call("GET", "/" + path.removeprefix("web/"))[1]
        served = served if isinstance(served, bytes) else json.dumps(served).encode()
        same[path] = hashlib.sha256(served).hexdigest() == hashlib.sha256(git_file(commit, path)).hexdigest()
    record(f"static files are byte-identical to {commit[:7]}", all(same.values()), same)

    # Anonymous policy.
    status, cfg, h = a.call("GET", "/api/config")
    record("anonymous /api/config (cloud, no-store)", status == 200 and cfg.get("cloud") is True
           and h.get("Cache-Control", h.get("cache-control")) == "no-store", cfg)
    record("anonymous /api/session", a.call("GET", "/api/session")[1] == {"authenticated": False})
    record("anonymous legacy data is private", a.call("GET", "/api/bases")[0] == 401)

    # Sign-in.
    status, h = a.login(args.user, password)
    cookie_attrs = h.get("Set-Cookie", "")
    record("sign-in with the fictional account; Secure HttpOnly SameSite=Strict",
           status == 200 and all(x in cookie_attrs for x in ("Secure", "HttpOnly", "SameSite=Strict")),
           {"status": status})
    if status != 200:
        return finish(args.out)

    # Import (openpyxl on Vercel), map data, saved map, export.
    fixture = (ROOT / "tests" / "fixtures" / "base_terrenos_09_26.xlsx").read_bytes()
    status, prev, _ = a.call("POST", "/api/importar/vista-previa", raw=fixture, headers={
        "Content-Type": "application/octet-stream", "X-Archivo": "ensayo.xlsx"})
    nombre = f"Ensayo Preview {stamp}"
    status2, conf, _ = a.call("POST", "/api/importar/confirmar",
                              {"token": prev.get("token"), "nombre": nombre} if status == 200 else {})
    base = conf.get("base", {}) if status2 == 200 else {}
    record("an .xlsx import works on Vercel", status == 200 and status2 == 200 and base.get("conteo", 0) > 0,
           {"preview": status, "confirm": status2, "terrenos": base.get("conteo")})
    status, ter, _ = a.call("GET", f"/api/bases/{base.get('id')}/terrenos")
    terrenos = ter.get("terrenos", []) if status == 200 else []
    record("map data for the imported base", status == 200 and len(terrenos) == base.get("conteo"),
           {"terrenos": len(terrenos), "ubicados": sum(1 for t in terrenos if t.get("ubicado"))})
    status, m, _ = a.call("POST", "/api/mapas", {
        "nombre": f"{nombre} mapa", "tipo": "simple", "capas": [{"base_id": base.get("id"), "color": "#2a78d6"}],
        "config": {"basemap": "claro", "modoColor": "precio"}})
    mapa = m.get("mapa", {}) if status == 200 else {}
    record("a saved map is created", status == 200 and bool(mapa.get("id")), {"status": status})
    status, xlsx, h = a.call("POST", "/api/exportar", {"mapa_id": mapa.get("id"), "nombre": "ensayo"})
    record("export returns an .xlsx", status == 200 and isinstance(xlsx, bytes) and xlsx[:2] == b"PK",
           {"status": status, "bytes": len(xlsx) if isinstance(xlsx, bytes) else None})
    status, d, _ = a.call("POST", "/api/inventario/terrenos", {"terreno": f"{nombre} borrador", "moneda": "USD",
                                                                "asking_m2": 122.5},
                          headers={"Idempotency-Key": f"preview-smoke-{stamp}"})
    draft = d.get("terreno", {}) if status == 200 else {}
    record("an inventory draft saves", status == 200 and draft.get("version") == 1, {"status": status})

    # Persistence: a second, independent session (another function invocation).
    b = Client(args.url, os.environ.get(args.bypass_env))
    b.login(args.user, password)
    bases_b = b.call("GET", "/api/bases")[1].get("bases", [])
    mapas_b = b.call("GET", "/api/mapas")[1].get("mapas", [])
    st, dd, _ = b.call("GET", f"/api/inventario/terrenos/{draft.get('id')}")
    record("persistence: a second session sees the base, the map and the draft (122.5 USD kept)",
           any(x.get("id") == base.get("id") for x in bases_b) and any(x.get("id") == mapa.get("id") for x in mapas_b)
           and st == 200 and dd["terreno"]["draft"]["asking_m2"] == 122.5,
           {"bases": len(bases_b), "mapas": len(mapas_b), "draft": st})

    if args.cleanup:
        for path in (f"/api/mapas/{mapa.get('id')}", f"/api/bases/{base.get('id')}"):
            a.call("DELETE", path)
    # Logout revokes the session on the server.
    a.call("POST", "/api/logout")  # the client keeps sending the old cookie
    record("logout revokes the session", a.call("GET", "/api/bases")[0] == 401)
    b.call("POST", "/api/logout")
    return finish(args.out, {"url_host": host, "commit": commit})


def finish(out: Path, meta: dict | None = None) -> int:
    fails = sum(r["result"] == "FAIL" for r in results)
    (out / "results.json").write_text(json.dumps({**(meta or {}), "results": results,
                                                   "pass": len(results) - fails, "fail": fails},
                                                  indent=2, ensure_ascii=False))
    print(f"\n{len(results) - fails} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
