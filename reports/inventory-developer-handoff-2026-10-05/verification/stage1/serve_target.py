#!/usr/bin/env python3
"""Run the candidate's HTTP handler on 127.0.0.1 against a DISPOSABLE database.

  --mode local : server.app.Handler (the loopback adapter) with ARA_MAP_DB=--db
  --mode cloud : api/index.py `handler` (the deployment adapter) with
                 ARA_MAP_DATABASE_URL taken from ARA_MAP_TEST_DATABASE_URL, which
                 must point at the verifier's own cluster on 127.0.0.1:55433.

Refuses: non-temporary or workspace data paths, any other Postgres target,
inherited DATABASE_URL / ARA_MAP_DATABASE_URL, ARA_MAP_PUBLIC_EDIT unless
--allow-public-edit-env (used only to prove that variable no longer opens anything).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aralib import assert_disposable_path  # noqa: E402

PG_PORT = 55433


def install_fault(marker: str) -> None:
    """THE ONLY PATCH: wrap server.repo.inventario._event (the history insert, which runs
    after the terrain/revision/pointer writes and before the idempotency result update)
    so it raises when the event details contain `marker`. In this process only; no file
    of the candidate is modified."""
    import json
    from server.repo import inventario as repo_inv
    original = repo_inv._event

    def faulty(conn, inventory_id, version, action, actor, ahora, before, after, details):  # noqa: ANN001, ANN202
        if marker in json.dumps(details, ensure_ascii=False):
            raise RuntimeError("verifier fault injection before inventory_event insert")
        return original(conn, inventory_id, version, action, actor, ahora, before, after, details)

    repo_inv._event = faulty
    print(f"[serve_target] FAULT INJECTION active: server.repo.inventario._event raises on {marker!r}",
          flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("local", "cloud"), required=True)
    ap.add_argument("--port", type=int, default=8433)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--app-root", type=Path, required=True)
    ap.add_argument("--allow-public-edit-env", action="store_true")
    ap.add_argument("--fault-marker", help="verifier fault injection (INTEGRATION_DECISIONS §9.4)")
    args = ap.parse_args()

    for var in ("DATABASE_URL", "ARA_MAP_DATABASE_URL"):
        if os.environ.pop(var, None):
            print(f"[serve_target] dropped inherited {var}", flush=True)
    if os.environ.get("ARA_MAP_PUBLIC_EDIT") and not args.allow_public_edit_env:
        raise SystemExit("ARA_MAP_PUBLIC_EDIT set without --allow-public-edit-env")

    if args.mode == "local":
        os.environ.pop("ARA_MAP_TEST_DATABASE_URL", None)
        if not args.db:
            raise SystemExit("--db required in local mode")
        os.environ["ARA_MAP_DB"] = str(assert_disposable_path(args.db))
    else:
        url = os.environ.pop("ARA_MAP_TEST_DATABASE_URL", "")
        parts = urlsplit(url)
        if parts.hostname not in ("127.0.0.1", "localhost") or parts.port != PG_PORT:
            raise SystemExit("cloud mode needs ARA_MAP_TEST_DATABASE_URL on 127.0.0.1:55433")
        os.environ["ARA_MAP_DATABASE_URL"] = url
        os.environ.pop("ARA_MAP_DB", None)

    root = args.app_root.resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    if args.mode == "local":
        from server import db
        from server.app import Handler
        db.connect().close()  # create/migrate before the first request, like serve()
        handler = Handler
    else:
        spec = importlib.util.spec_from_file_location("cloud_adapter", root / "api" / "index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = module.handler
        if os.environ.get("ARA_MAP_DATABASE_URL") != url:
            raise SystemExit("cloud adapter changed ARA_MAP_DATABASE_URL; refusing")

    if args.fault_marker:
        install_fault(args.fault_marker)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"[serve_target] mode={args.mode} http://127.0.0.1:{args.port} root={root}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
