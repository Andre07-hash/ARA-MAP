"""Run the rewritten L2 privacy test against deliberately leaky projections.

    PYTHONPATH=<tree> python3 mutaciones_privacidad.py sqlite|postgres

Each mutation patches the real read path (server.repo.archivos) for the
duration of one run of
``test_l2_pending_privacy_is_one_rule_on_every_read_surface``. Every mutation
must make the test fail; the unmutated control must pass. Synthetic data;
Postgres needs ARA_MAP_TEST_DATABASE_URL pointing at a disposable database.
Prints one JSON line per run.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

from server.repo import archivos as repo
from tests.test_archivos import AttachmentLifecyclePostgres, AttachmentLifecycleSQLite

_private_event = repo._private_event
_projected = repo.projected_version
_pending_view = repo.pending_view
_list = repo.list_for_terrain


def event_with_details(row, state):
    return _private_event(row, state) | {"details": json.loads(row["details_json"] or "{}")}


def event_with_actor(row, state):
    return _private_event(row, state) | {"actor": {"id": row["actor_id"],
                                                   "display_name": row["actor_name"]}}


def projection_with_size(version, lease_live, actor_id, now):
    dto = _projected(version, lease_live, actor_id, now)
    if dto.get("propia") is False:
        dto["tamano_declarado"] = int(version["tamano_declarado"])
    return dto


def projection_with_name(version, lease_live, actor_id, now):
    dto = _projected(version, lease_live, actor_id, now)
    if dto.get("propia") is False:
        dto["nombre_original"] = version["nombre_original"]
    return dto


def no_privacy(version, lease_live, actor_id, now):
    state, _private = _pending_view(version, lease_live, actor_id, now)
    return state, False


def list_with_item_size(conn, *args, **kwargs):
    items, cursor = _list(conn, *args, **kwargs)
    for item in items:
        row = conn.execute("SELECT tamano_declarado FROM archivo_version WHERE archivo_id = ?"
                           " ORDER BY numero DESC", (item["id"],)).fetchone()
        item["bytes_pendientes"] = str(row["tamano_declarado"])
    return items, cursor


MUTATIONS = {
    "control (no mutation)": [],
    "history keeps the private details": [("_private_event", event_with_details)],
    "history keeps the uploader": [("_private_event", event_with_actor)],
    "listing projection adds the byte count": [("projected_version", projection_with_size)],
    "listing projection adds the file name": [("projected_version", projection_with_name)],
    "privacy rule removed everywhere": [("pending_view", no_privacy)],
    "listing item carries the byte count as text": [("list_for_terrain", list_with_item_size)],
}


def main(backend: str) -> None:
    cls = AttachmentLifecyclePostgres if backend == "postgres" else AttachmentLifecycleSQLite
    name = "test_l2_pending_privacy_is_one_rule_on_every_read_surface"
    cls.setUpClass()
    try:
        for label, patches in MUTATIONS.items():
            case = cls(name)
            case.setUp()
            try:
                active = [patch.object(repo, attr, fake) for attr, fake in patches]
                for p in active:
                    p.start()
                try:
                    getattr(case, name)()
                    result, reason = "pass", ""
                except AssertionError as exc:
                    result, reason = "fail", str(exc).splitlines()[0][:240]
                finally:
                    for p in active:
                        p.stop()
            finally:
                case.doCleanups()
            print(json.dumps({"backend": backend, "mutation": label, "result": result,
                              "first_line": reason}, ensure_ascii=True), flush=True)
    finally:
        cls.tearDownClass()


if __name__ == "__main__":
    main(sys.argv[1])
