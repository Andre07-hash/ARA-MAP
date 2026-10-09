"""Independent 1A compatibility/privacy/cursor probes on disposable fixtures.

PYTHONPATH=/path/to/pr22 python reproduce.py sqlite|postgres
Postgres needs ARA_MAP_TEST_DATABASE_URL for an explicitly disposable database.
"""
import base64
import hashlib
import json
import sys
import uuid

from server import db
from tests.test_registros_maestra import RegistrosPostgres, RegistrosSqlite


def old_idempotency(t):
    fields = {"terreno": "Legacy fictional record"}
    key = "legacy-supervisor-fixture"
    before = t.cuenta("inventory_terrain")
    first = t.call("POST", "/api/inventario/terrenos", fields, "ada", {"Idempotency-Key": key})
    tid = first[1]["terreno"]["id"]
    legacy_hash = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    # Reconstruct the accepted pre-1A storage shape and normalized body hash.
    with db.escritura() as conn:
        conn.execute("UPDATE inventory_operation_result SET operation = 'create', request_hash = ?,"
                     " result_json = ? WHERE idempotency_key = ?",
                     (legacy_hash, json.dumps({"terreno": {"id": tid}}), key))
    replay = t.call("POST", "/api/inventario/terrenos", fields, "ada", {"Idempotency-Key": key})
    return {"first_status": first[0], "same_actor_same_body_retry": replay,
            "record_count_delta": t.cuenta("inventory_terrain") - before}


def hidden_history(t):
    source_id = t.columna(t.b1, "Private source column")
    destination_id = t.columna(t.b2, "Visible destination column")
    secret = "SOURCE-ONLY-FICTIONAL-VALUE"
    details = {"changes": {source_id: {"before": None, "after": secret},
                           "custom_json": {"before": {}, "after": {source_id: secret}},
                           "terreno": {"before": "Before", "after": "After"}}}
    with db.escritura() as conn:
        conn.execute("UPDATE inventory_revision SET custom_json = ? WHERE inventory_id = ?",
                     (json.dumps({source_id: secret, destination_id: "DESTINATION"}), t.t1))
        # Valid stored audit details. These are not emitted by current core-only writers;
        # 1A explicitly requires projection of embedded custom-history values.
        conn.execute("UPDATE inventory_event SET details_json = ? WHERE inventory_id = ? AND version = 1",
                     (json.dumps(details), t.t1))
    t.ok(t.accion(t.t1, "transferir", "ada", base_id=t.b2))
    t.otorgar(t.b1, "olga")  # Omar now has destination access only.
    detail = t.ver(t.t1, "omar")
    history = t.ver(t.t1, "omar", "/historial")
    return {"detail_status": detail[0], "detail_has_hidden_value": secret in json.dumps(detail),
            "history_status": history[0], "history_has_hidden_value": secret in json.dumps(history),
            "history": history[1]}


def malformed_cursors(t):
    results = []
    for sort, value in (("asking_price", "not-a-number"), ("asking_price", 10**1000),
                        ("terreno", 5), ("terreno", float("nan"))):
        cursor = base64.urlsafe_b64encode(json.dumps([sort, value, str(uuid.uuid4())]).encode()).decode()
        try:
            response = t.lista(t.b1, f"sort={sort}&cursor={cursor}")
            results.append({"sort": sort, "value_type": type(value).__name__, "status": response[0],
                            "error": response[1].get("error"), "detail": response[1].get("detalle")})
        except Exception as exc:
            results.append({"sort": sort, "value_type": type(value).__name__, "exception": type(exc).__name__})
    return results


if __name__ == "__main__":
    backend = sys.argv[1]
    if backend not in ("sqlite", "postgres"):
        raise SystemExit("Choose sqlite or postgres with a disposable test database")
    cls = RegistrosPostgres if backend == "postgres" else RegistrosSqlite
    if backend == "postgres":
        cls.setUpClass()
    try:
        for probe in (old_idempotency, hidden_history, malformed_cursors):
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
