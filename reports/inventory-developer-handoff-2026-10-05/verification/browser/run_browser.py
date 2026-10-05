#!/usr/bin/env python3
"""Stage 1 integrated browser pass: disposable server + seed, then stage1_browser.mjs.

Starts the candidate's local adapter on 127.0.0.1:8433 over a NEW temp copy of the
fictional legacy v7 workspace, provisions the three fictional users, seeds the
120 master fixtures (A/B/C round-robin) and the 251 matching fixtures through the
real API, then runs the Node/playwright-core script and stops the server.

  .venv-dev/bin/python3 verification/browser/run_browser.py
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage1"))
import aralib as L  # noqa: E402

PORT = 8433


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = L.VERIFY / "runs" / f"{stamp}-browser"
    run_dir.mkdir(parents=True)
    tmp = Path(tempfile.mkdtemp(prefix="ara-verify-browser-"))
    db = L.assert_disposable_path(tmp / "ara.db")
    src = tmp / "legacy_src.db"
    subprocess.run([sys.executable, str(L.VERIFY / "legacy" / "build_legacy_v7.py"), "--out", str(src)],
                   check=True, env=L.safe_env(), stdout=subprocess.DEVNULL)
    shutil.copy(str(src) + ".manifest.json", run_dir / "legacy.manifest.json")
    a, b = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True), sqlite3.connect(db)
    a.backup(b)
    a.close()
    b.close()

    users = L.users()
    ev = L.Evidence(run_dir / "seed_http.jsonl", [u["password"] for u in users])
    server = L.Server("local", PORT, db, run_dir / "server.log")
    server.start()
    code = 1
    try:
        for u in users:
            if u["provision"]:
                L.provision(u, db, run_dir / "provision.log")
        sess = {}
        for u in users[:3]:
            s = L.Session(server.url, f"seed-{u['tag']}", ev)
            assert s.login(u["username"], u["password"]).status == 200
            sess[u["tag"]] = s
        ids, rejected = {}, {}
        recs = list(L.records().values()) + list(L.records("matching_251.json").values())
        t0 = time.perf_counter()
        for i, rec in enumerate(recs):
            s = sess["ABC"[i % 3]]
            r = s.post("/api/inventario/terrenos", L.to_payload(rec["draft"]),
                       headers={"Idempotency-Key": f"browser-seed-{rec['key']}-{uuid.uuid4()}"})
            if r.status == 200:
                ids[rec["key"]] = r.json["terreno"]["id"]
            else:
                rejected[rec["key"]] = r.status
        seed_s = round(time.perf_counter() - t0, 1)
        total = sess["A"].get("/api/inventario/terrenos?limit=1").json["total"]
        seed = {"url": server.url, "ids": ids, "rejected_at_save": rejected, "total": total,
                "users_file": str(L.FIXTURES / "users.json"), "legacy_manifest": str(run_dir / "legacy.manifest.json"),
                "seed_seconds": seed_s, "fixture_hash": L.load_json(L.FIXTURES / "manifest.json")["fixture_hash_sha256"]}
        (run_dir / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=1))
        for s in sess.values():
            s.post("/api/logout")
        print(f"[seed] {len(ids)} created, rejected {rejected}, total {total}, {seed_s}s", flush=True)
        node = subprocess.run(
            ["node", str(HERE / "stage1_browser.mjs")],
            env={**L.safe_env(), "SEED": str(run_dir / "seed.json"), "OUT": str(run_dir)},
            cwd=HERE, timeout=1800)
        code = node.returncode
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"[browser] exit {code} -> {run_dir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
