"""Write examples/columnas.json from real requests against a temporary SQLite
database with the test fixture's fictional accounts.

    python3 reports/team-a-master-grid-2026-10-09/generar_ejemplos.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.test_roles_y_bases import Escenario  # noqa: E402

SALIDA = Path(__file__).parent / "examples" / "columnas.json"


class Ejemplos(Escenario, unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._entorno = patch.dict(os.environ, {"ARA_MAP_DB": str(Path(self._dir.name) / "e.db")})
        self._entorno.start()
        os.environ.pop("ARA_MAP_DATABASE_URL", None)
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(self._entorno.stop)
        self.levantar()

    def test_escribir(self):
        ejemplos = []

        def pedir(titulo, method, path, body=None, user="olga", headers=None):
            status, respuesta = self.call(method, path, body, user, headers)
            ejemplos.append({"titulo": titulo, "quien": user,
                             "peticion": {"metodo": method, "ruta": path, "encabezados": headers or {},
                                          "cuerpo": body},
                             "respuesta": {"estado": status, "cuerpo": respuesta}})
            return respuesta

        base = f"/api/maestra/bases/{self.b1}"
        nota = pedir("Crear una columna de texto", "POST", f"{base}/columnas",
                     {"nombre": "Nota de visita", "tipo": "texto"},
                     headers={"Idempotency-Key": "clave-ficticia-0001"})["columna"]
        etapa = pedir("Crear una columna de opción", "POST", f"{base}/columnas",
                      {"nombre": "Etapa", "tipo": "opcion", "opciones": ["En curso", "Cerrado"]},
                      headers={"Idempotency-Key": "clave-ficticia-0002"})["columna"]
        cid = etapa["id"].split(":")[1]
        pedir("Renombrar, agregar una opción y mover al primer lugar", "PATCH", f"{base}/columnas/{cid}",
              {"expected_version": 1, "nombre": "Etapa comercial",
               "opciones": ["En curso", "Cerrado", "En pausa"], "posicion": 0})
        pedir("Versión vieja: conflicto con la definición actual", "PATCH", f"{base}/columnas/{cid}",
              {"expected_version": 1, "nombre": "Tarde"}, user="ada")
        pedir("Quitar una opción no se ofrece", "PATCH", f"{base}/columnas/{cid}",
              {"expected_version": 2, "opciones": ["En curso"]})
        pedir("Listar las columnas de la base", "GET", f"{base}/columnas")
        terreno = f"/api/inventario/terrenos/{self.t1}"
        pedir("Guardar celdas básicas y personalizadas en una sola versión", "PATCH", terreno,
              {"expected_version": 1, "changes": {"estado": "Jalisco"},
               "custom": {nota["id"]: "Junto al río", etapa["id"]: "En pausa"}})
        pedir("Un valor que la columna no admite: nada se guarda", "PATCH", terreno,
              {"expected_version": 2, "changes": {"municipio": "Zapopan"}, "custom": {etapa["id"]: "Otra"}})
        pedir("Retirar una columna", "POST", f"{base}/columnas/{nota['id'].split(':')[1]}/retirar",
              {"expected_version": 1})
        pedir("Columna retirada, desconocida o de otra base: una sola respuesta", "PATCH", terreno,
              {"expected_version": 2, "custom": {nota["id"]: "tarde"}})
        pedir("Historial para una operadora: sólo columnas vivas de la base actual", "GET",
              f"{terreno}/historial")
        pedir("Historial para una administradora: completo", "GET", f"{terreno}/historial", user="ada")
        pedir("Cuentas que pueden recibir acceso (sólo administradores)", "GET",
              "/api/maestra/operadores?q=ol&limit=5", user="ada")
        pedir("La misma consulta por una operadora", "GET", "/api/maestra/operadores")
        SALIDA.parent.mkdir(exist_ok=True)
        SALIDA.write_text(json.dumps(ejemplos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
