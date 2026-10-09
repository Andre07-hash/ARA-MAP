"""Independent real-HTTP boundary probes. PYTHONPATH selects the reviewed tree."""
import json
import sys
import uuid
from urllib.parse import quote

backend, team = sys.argv[1:3]
if team == "a":
    from tests.test_columnas_maestra import ColumnasSqlite, ColumnasPostgres
    cls = ColumnasPostgres if backend == "postgres" else ColumnasSqlite
else:
    from tests.test_archivos_http import HTTPSQLite, HTTPPostgres
    cls = HTTPPostgres if backend == "postgres" else HTTPSQLite

cls.setUpClass()
test = cls(methodName="runTest")
test.setUp()
try:
    if team == "a":
        for label, name, extra in [
            ("nul_name", "Ficticio\x00nombre", {}),
            ("surrogate_name", "Ficticio\ud800", {}),
            ("nul_option", "Opcion ficticia", {"tipo": "opcion", "opciones": ["a\x00b"]}),
        ]:
            status, body = test.crear(test.b1, name, **extra)
            print(json.dumps({"backend": backend, "probe": label, "status": status,
                              "result": body}, ensure_ascii=True))
        col = test.columna(test.b1, "Fecha ficticia", "fecha")
        status, body = test.guardar(test.t1, {col["id"]: "2026-10-09\n"})
        print(json.dumps({"backend": backend, "probe": "date_trailing_newline",
                          "status": status, "stored": test.guardado(test.t1)}, ensure_ascii=True))
        col = test.columna(test.b1, "Texto ficticio")
        status, body = test.guardar(test.t1, {col["id"]: "Ficticio\ud800"})
        print(json.dumps({"backend": backend, "probe": "surrogate_value",
                          "status": status, "result": body}, ensure_ascii=True))
    else:
        routes = [
            f"/api/inventario/terrenos/{test.terreno}/archivos?limite={quote('²')}",
            f"/api/archivos/{uuid.uuid4()}/historial?limite={quote('²')}",
            f"/api/archivos/geometrias/{uuid.uuid4()}/contenido?desde={quote('²')}",
        ]
        for route in routes:
            status, body = test.j("GET", route)
            print(json.dumps({"backend": backend, "probe": route.split('?')[1],
                              "status": status, "result": body}, ensure_ascii=True))
finally:
    test.doCleanups()
    cls.tearDownClass()
