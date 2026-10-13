"""Actual completion-boundary-first races and paged-list probes on disposable data.

PYTHONPATH=/path/to/pr23 python reproduce_lifecycle_edges.py sqlite|postgres
Postgres requires ARA_MAP_TEST_DATABASE_URL for an explicitly disposable UTF-8 DB.
"""
from __future__ import annotations

import json
import sys
import threading
from unittest.mock import patch

from server import archivos, auth, db
from server.errors import ApiError
from server.repo import archivos as repo
from tests.test_archivos import AttachmentLifecyclePostgres, AttachmentLifecycleSQLite, PDF


def boundary_first(t, change):
    pending = t.upload(PDF, user="olga")
    entered, release, trying, changed = (threading.Event() for _ in range(4))
    results = {}
    original = repo.finish_available

    def held_finish(*args, **kwargs):
        # Actual completion has reauthorized and acquired its final write boundary.
        entered.set()
        if not release.wait(10):
            raise AssertionError("supervisor barrier timed out")
        return original(*args, **kwargs)

    def finish():
        try:
            results["completion"] = t.complete(pending, user="olga")
        except BaseException as exc:
            results["completion_error"] = type(exc).__name__

    def mutate():
        try:
            trying.set()
            with db.escritura(t.database) as conn:
                auth.reverificar(conn, t.sessions["ana"], "maestra.global")
                if change == "grant":
                    conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                                 (t.base, t.users["olga"]["id"]))
                elif change == "transfer":
                    conn.execute("UPDATE inventory_terrain SET base_id = NULL WHERE id = ?", (t.terrain,))
                elif change == "terrain_archive":
                    conn.execute("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?", (db.now(), t.terrain))
                elif change == "base_archive":
                    conn.execute("UPDATE maestra_base SET archived_at = ? WHERE id = ?", (db.now(), t.base))
                elif change == "deactivate":
                    conn.execute("UPDATE team_user SET active = 0 WHERE id = ?", (t.users["olga"]["id"],))
                elif change in ("role", "credential"):
                    extra = "rol = 'admin', " if change == "role" else ""
                    conn.execute("UPDATE team_user SET " + extra + "credential_revision = credential_revision + 1 WHERE id = ?",
                                 (t.users["olga"]["id"],))
                else:
                    conn.execute("UPDATE team_session SET revoked_at = ? WHERE token_hash = ?",
                                 (db.now(), t.sessions["olga"].referencia))
            changed.set()
        except BaseException as exc:
            results["mutation_error"] = type(exc).__name__

    with patch.object(repo, "finish_available", held_finish):
        writer = threading.Thread(target=finish)
        writer.start()
        assert entered.wait(10)
        administrator = threading.Thread(target=mutate)
        administrator.start()
        assert trying.wait(10)
        blocked = not changed.wait(0.15)
        release.set()
        writer.join(10)
        administrator.join(10)
    assert not writer.is_alive() and not administrator.is_alive()
    assert "completion_error" not in results and "mutation_error" not in results, results
    rows_before = len(t.rows("archivo_evento"))
    try:
        t.complete(pending, user="olga")
        replay = "unexpected_success"
    except ApiError as exc:
        replay = exc.detalle["code"]
    result = {"change": change, "mutation_waited": blocked, "mutation_committed": changed.is_set(),
              "completion_state": results["completion"]["version"]["estado"],
              "next_replay": replay, "audit_unchanged_on_denial": rows_before == len(t.rows("archivo_evento"))}
    assert blocked and changed.is_set() and result["completion_state"] == "disponible"
    assert replay != "unexpected_success" and result["audit_unchanged_on_denial"]
    return result


def pages(t):
    ids = []
    for i in range(105):
        started = t.start(PDF, key=str(i))
        ids.append(started["archivo_id"])
        archivos.cancelar(t.sessions["ana"], started["version_id"], bd=t.database, reloj=t.clock)
    sizes, seen, cursor = [], [], None
    while True:
        page = archivos.listar(t.sessions["ana"], t.terrain, cursor=cursor, bd=t.database, reloj=t.clock)
        sizes.append(len(page["archivos"]))
        seen.extend(row["id"] for row in page["archivos"])
        cursor = page["cursor_siguiente"]
        if cursor is None:
            break
    assert sizes == [50, 50, 5] and sorted(seen) == sorted(ids) and len(set(seen)) == 105
    return {"sizes": sizes, "unique": len(set(seen))}


if __name__ == "__main__":
    backend = sys.argv[1]
    assert backend in ("sqlite", "postgres")
    cls = AttachmentLifecyclePostgres if backend == "postgres" else AttachmentLifecycleSQLite
    if backend == "postgres":
        cls.setUpClass()
    try:
        cases = ["grant", "transfer", "terrain_archive", "base_archive", "deactivate", "role", "credential", "logout", "pages"]
        for case in cases:
            t = cls()
            t.setUp()
            try:
                observed = pages(t) if case == "pages" else boundary_first(t, case)
                print(json.dumps({"backend": backend, "case": case, "observed": observed}))
            finally:
                t.doCleanups()
    finally:
        if backend == "postgres":
            cls.tearDownClass()
