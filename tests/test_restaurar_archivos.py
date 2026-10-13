"""scripts/restaurar_archivos.py: an exported backup into a fresh store, never overwriting."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from server import recuperacion
from server.almacen import AlmacenEnMemoria, AlmacenLocal

spec = importlib.util.spec_from_file_location(
    "restaurar_archivos", Path(__file__).parents[1] / "scripts" / "restaurar_archivos.py")
restaurar_archivos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restaurar_archivos)

PDF = b"%PDF-1.7\n" + bytes(range(256)) * 9000   # larger than one transfer block
KMZ = b"PK\x03\x04 contorno ficticio"


class Restaurar(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.carpeta = Path(self._dir.name) / "exportado"
        self.finales = []
        for contenido, tipo in ((PDF, "pdf"), (KMZ, "kmz")):
            clave = f"final/{uuid.uuid4().hex}/{uuid.uuid4().hex}"
            ruta = self.carpeta / clave
            ruta.parent.mkdir(parents=True)
            ruta.write_bytes(contenido)
            self.finales.append({"clave": clave, "tamano": len(contenido), "tipo": tipo,
                                 "sha256": hashlib.sha256(contenido).hexdigest(),
                                 "version_id": str(uuid.uuid4()), "archivo_id": str(uuid.uuid4())})
        (self.carpeta / recuperacion.NOMBRE_MANIFIESTO).write_text(json.dumps({
            "formato": recuperacion.FORMATO, "version": recuperacion.VERSION,
            "creado_en": "2026-10-12T18:00:00+00:00", "finales": self.finales, "pendientes": []}))
        self.manifiesto = recuperacion.cargar_manifiesto(self.carpeta / recuperacion.NOMBRE_MANIFIESTO)
        self.almacen = AlmacenEnMemoria()

    def claves(self):
        return [e["clave"] for e in self.finales]

    def bytes_de(self, clave):
        with self.almacen.leer(clave, 30 * 1024 * 1024) as lectura:
            return b"".join(lectura)

    def test_every_object_lands_at_its_key_and_the_verifier_accepts_the_store(self):
        resultado = restaurar_archivos.restaurar(self.carpeta, self.almacen)
        self.assertEqual(resultado, {"subidos": self.claves(), "ya_estaban": [], "fallidos": []})
        self.assertEqual([self.bytes_de(c) for c in self.claves()], [PDF, KMZ])
        self.assertEqual(list(self.almacen.listar("temporal/")), [])  # no staging left behind
        self.assertTrue(recuperacion.verificar_restauracion(self.manifiesto, self.almacen)["correcto"])

    def test_a_second_run_changes_nothing(self):
        restaurar_archivos.restaurar(self.carpeta, self.almacen)
        resultado = restaurar_archivos.restaurar(self.carpeta, self.almacen)
        self.assertEqual(resultado, {"subidos": [], "ya_estaban": self.claves(), "fallidos": []})

    def test_a_missing_or_altered_file_stops_everything_before_any_upload(self):
        (self.carpeta / self.finales[1]["clave"]).write_bytes(KMZ + b"!")
        resultado = restaurar_archivos.restaurar(self.carpeta, self.almacen)
        self.assertEqual(resultado, {"subidos": [], "ya_estaban": [], "fallidos": [self.finales[1]["clave"]]})
        self.assertEqual(list(self.almacen.listar("final/")), [])
        (self.carpeta / self.finales[1]["clave"]).unlink()
        self.assertEqual(restaurar_archivos.restaurar(self.carpeta, self.almacen)["fallidos"],
                         [self.finales[1]["clave"]])

    def test_an_existing_different_object_is_reported_and_never_overwritten(self):
        clave = self.finales[1]["clave"]
        self.almacen.guardar_temporal("temporal/ajeno", [b"otro contenido, otro tamano"], 1000)
        self.almacen.copiar("temporal/ajeno", clave, 1000)
        resultado = restaurar_archivos.restaurar(self.carpeta, self.almacen)
        self.assertEqual((resultado["subidos"], resultado["fallidos"]), ([self.finales[0]["clave"]], [clave]))
        self.assertEqual(self.bytes_de(clave), b"otro contenido, otro tamano")

    def test_the_command_restores_into_a_local_store_and_reports(self):
        destino = Path(self._dir.name) / "almacen-nuevo"
        self.assertEqual(restaurar_archivos.main([str(self.carpeta), "--almacen-local", str(destino)]), 0)
        with AlmacenLocal(destino) as nuevo:
            self.assertTrue(recuperacion.verificar_restauracion(self.manifiesto, nuevo)["correcto"])
        (self.carpeta / recuperacion.NOMBRE_MANIFIESTO).write_text("{")
        self.assertEqual(restaurar_archivos.main([str(self.carpeta), "--almacen-local", str(destino)]), 2)


if __name__ == "__main__":
    unittest.main()
