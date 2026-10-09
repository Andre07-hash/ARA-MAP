"""Independent probes; run against an archive of the reviewed PR, not production.

Usage: PYTHONPATH=/path/to/pr23 python reproduce_lifecycle.py [sqlite|postgres]
Postgres requires ARA_MAP_TEST_DATABASE_URL pointing to a disposable UTF-8 DB.
"""
import json
import sys
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from server import archivos, db
from server.almacen import FalloAlmacenError
from server.errors import ApiError
from tests.test_archivos import (
    AttachmentLifecyclePostgres, AttachmentLifecycleSQLite, PDF, kmz,
)


def outcome(call):
    try:
        return {"returned": call()}
    except ApiError as exc:
        return {"status": exc.status, "message": exc.mensaje, "detail": exc.detalle}
    except Exception as exc:
        return {"exception": type(exc).__name__}


def absence(t):
    hidden = t.start(PDF, terrain=t.other_terrain)
    return {
        "missing": outcome(lambda: archivos.completar(
            t.sessions["olga"], str(uuid.uuid4()), t.store, bd=t.database, reloj=t.clock)),
        "out_of_scope": outcome(lambda: t.complete(hidden, user="olga")),
    }


def foreign_activation(t):
    own = t.upload(PDF, user="olga")
    t.complete(own, user="olga")
    hidden = t.upload(PDF, terrain=t.other_terrain)
    def activate(version):
        return archivos.activar(t.sessions["olga"], own["archivo_id"],
            version_id=version, expected_revision=2, idempotency_key=str(uuid.uuid4()),
            bd=t.database, reloj=t.clock)
    t.clock.advance(900)
    observed = {}
    def probe(_):
        observed["foreign_live_lease"] = outcome(lambda: activate(hidden["version_id"]))
        observed["missing_version"] = outcome(lambda: activate(str(uuid.uuid4())))
    t.complete(hidden, ganchos=SimpleNamespace(despues_lease=probe))
    observed["foreign_available"] = outcome(lambda: activate(hidden["version_id"]))
    return observed


def pending_privacy(t):
    pending = t.start(PDF, name="private-pending-fixture.pdf")
    before = archivos.historial(t.sessions["olga"], pending["archivo_id"], bd=t.database)
    t.clock.advance(3600)
    with db.session(t.database) as conn:
        after = archivos.resumenes_de_archivos(conn, [t.terrain], t.sessions["olga"], reloj=t.clock)
    return {"history_discloses_name": "private-pending-fixture.pdf" in json.dumps(before),
            "history": before,
            "expired_summary_discloses_name": "private-pending-fixture.pdf" in json.dumps(after)}


def stale_clock(t):
    pending = t.upload(PDF)
    original = db.escritura
    calls = 0
    @contextmanager
    def delayed(path=None):
        nonlocal calls
        calls += 1
        with original(path) as conn:
            if calls == 2:
                # Deterministic clock advance while acquiring the final boundary.
                t.clock.advance(2)
            yield conn
    with patch.object(db, "escritura", delayed):
        result = outcome(lambda: t.complete(pending, ganchos=SimpleNamespace(
            antes_commit=lambda _: t.clock.advance(178))))
    return {"clock_at_return": t.clock().isoformat(), "result": result}


def expired_processing(t):
    pending = t.upload(kmz("ambiguo_tres_lotes"), "kmz")
    t.complete(pending)
    return outcome(lambda: archivos.reprocesar(t.sessions["ana"], pending["version_id"],
        t.store, seleccion=[0], idempotency_key="expired-processing", bd=t.database,
        reloj=t.clock, ganchos=SimpleNamespace(despues_parseo=lambda _: t.clock.advance(180))))


def unbounded_list(t):
    for i in range(105):
        p = t.start(PDF, key=str(i))
        archivos.cancelar(t.sessions["ana"], p["version_id"], bd=t.database, reloj=t.clock)
    return {"attachments_returned": len(archivos.listar(
        t.sessions["ana"], t.terrain, bd=t.database, reloj=t.clock))}


def retired_summary(t):
    active = t.upload(PDF, name="still-active.pdf")
    t.complete(active)
    for i in range(5):
        t.clock.advance(1)
        p = t.upload(PDF, name=f"retired-{i}.pdf")
        t.complete(p)
        archivos.retirar(t.sessions["ana"], p["archivo_id"], expected_revision=2,
            idempotency_key=str(i), bd=t.database, reloj=t.clock)
    with db.session(t.database) as conn:
        summary = archivos.resumenes_de_archivos(conn, [t.terrain], t.sessions["ana"], reloj=t.clock)
    data = summary["resultados"][t.terrain]
    return {"pdf_total": data["pdf_total"], "recent_retired": [r["retirado"] for r in data["pdf_recientes"]],
            "active_in_recent": any(r["id"] == active["archivo_id"] for r in data["pdf_recientes"])}


def cleanup(t):
    bad = t.upload(b"not-pdf")
    with patch.object(t.store, "borrar", side_effect=FalloAlmacenError()):
        result = t.complete(bad)
    return {"result": result, "final_objects_remaining": len(list(t.store.listar("final/")))}


if __name__ == "__main__":
    backend = sys.argv[1] if len(sys.argv) > 1 else "sqlite"
    cls = AttachmentLifecyclePostgres if backend == "postgres" else AttachmentLifecycleSQLite
    if backend == "postgres":
        cls.setUpClass()
    try:
        for probe in (absence, foreign_activation, pending_privacy, stale_clock,
                      expired_processing, unbounded_list, retired_summary, cleanup):
            fixture = cls()
            fixture.setUp()
            try:
                print(json.dumps({"backend": backend, "probe": probe.__name__,
                                  "observed": probe(fixture)}, ensure_ascii=False))
            finally:
                fixture.doCleanups()
    finally:
        if backend == "postgres":
            cls.tearDownClass()
