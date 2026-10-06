#!/usr/bin/env python3
"""Stage 2 wrapper around stage1/serve_target.py with switchable verifier fault injection.

INTEGRATION_DECISIONS §9.4: the verifier may patch calls INSIDE ITS OWN WRAPPER
PROCESS to force failures. No candidate file is modified. Exactly two patches,
both only active while the JSON control file named by --fault-file says so
(re-read on every call, so the test can switch them without a restart):

  1. server.repo.inventario._event  -> raises RuntimeError when the event's
     inventory_id is listed in control["event_ids"]. _event is the history insert
     that every lifecycle action performs AFTER its compare-and-set and pointer
     update, inside the same transaction, so a raise must roll all of it back.
  2. server.repo.inventario.public_records -> raises RuntimeError when
     control["public_records"] is true (anonymous 500 path).
  3. server.repo.inventario.public_get -> POSITIVE CONTROL ONLY: when control["leak_control"]
     is true, adds the record's private `contacto` to the public detail, to prove the
     verifier's public-response checks catch a leak. Switched off for every real check.

The exception text deliberately contains a sentinel-shaped marker and a fake
file path; neither may appear in any HTTP response (O-5).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage1"))
import serve_target  # noqa: E402

FAULT_TEXT = "SNTL-FAULTEXC-S2-abc123 /srv/secret/path/inventory_event.py relation inventory_event"


def _control(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def install(fault_file: Path) -> None:
    from server.repo import inventario as repo_inv
    original_event = repo_inv._event
    original_public = repo_inv.public_records

    def event(conn, inventory_id, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if inventory_id in _control(fault_file).get("event_ids", []):
            raise RuntimeError(f"verifier fault: {FAULT_TEXT}")
        return original_event(conn, inventory_id, *args, **kwargs)

    def public_records(conn):  # noqa: ANN001, ANN202
        if _control(fault_file).get("public_records"):
            raise RuntimeError(f"verifier fault: {FAULT_TEXT}")
        return original_public(conn)

    original_public_get = repo_inv.public_get

    def public_get(conn, inventory_id):  # noqa: ANN001, ANN202
        found = original_public_get(conn, inventory_id)
        if found is not None and _control(fault_file).get("leak_control"):
            internal = repo_inv.get(conn, inventory_id)  # POSITIVE CONTROL ONLY: deliberately leak contacto
            found = {**found, "contacto": internal["draft"]["contacto"]}
        return found

    repo_inv._event = event
    repo_inv.public_records = public_records
    repo_inv.public_get = public_get
    print(f"[serve_target2] fault hooks installed (control file {fault_file}): "
          "server.repo.inventario._event, .public_records, .public_get", flush=True)


def main() -> int:
    argv = sys.argv[1:]
    fault_file = None
    if "--fault-file" in argv:
        i = argv.index("--fault-file")
        fault_file = Path(argv[i + 1])
        del argv[i:i + 2]
    if fault_file:
        # serve_target imports the candidate inside main(); patch right after import by
        # wrapping its install_fault hook point: we pre-import the module tree here.
        original_main = serve_target.main

        import http.server as hs
        original_init = hs.ThreadingHTTPServer.__init__

        def init(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
            install(fault_file)  # candidate modules are imported by now (handler resolved)
            hs.ThreadingHTTPServer.__init__ = original_init
            original_init(self, *a, **k)

        hs.ThreadingHTTPServer.__init__ = init
        sys.argv = [sys.argv[0], *argv]
        return original_main()
    sys.argv = [sys.argv[0], *argv]
    return serve_target.main()


if __name__ == "__main__":
    sys.exit(main())
