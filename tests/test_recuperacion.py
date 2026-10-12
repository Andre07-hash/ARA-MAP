"""The read-only attachment verifier/exporter, and a synthetic restore drill."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server import db, recuperacion
from server.almacen import AlmacenEnMemoria, AlmacenLocal
from tests import test_archivos

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
RAIZ = Path(__file__).resolve().parents[1]
TABLAS = ("archivo", "archivo_version", "archivo_intento", "geometria", "archivo_evento")


def poner(almacen, clave: str, datos: bytes) -> None:
    """Test-only: put these bytes at a final key through the store's own contract."""
    temporal = "temporal/" + uuid.uuid4().hex
    almacen.guardar_temporal(temporal, [datos[i:i + 65536] for i in range(0, len(datos), 65536)],
                             max(1, len(datos)))
    almacen.borrar(clave)
    almacen.copiar(temporal, clave, max(1, len(datos)))
    almacen.borrar(temporal)


def cargar_exportacion(origen: Path, destino) -> None:
    """Test-only restore step: load an export directory into a target store."""
    for ruta in sorted((origen / "final").glob("*/*")):
        poner(destino, f"final/{ruta.parent.name}/{ruta.name}", ruta.read_bytes())


def entrada(clave: str, datos: bytes, tipo: str = "pdf") -> dict:
    return {"clave": clave, "tamano": len(datos), "sha256": hashlib.sha256(datos).hexdigest(),
            "tipo": tipo, "version_id": "v-" + clave[-1], "archivo_id": "a-" + clave[-1]}


def manifiesto(*finales: dict, pendientes: tuple = ()) -> dict:
    return {"formato": recuperacion.FORMATO, "version": recuperacion.VERSION,
            "creado_en": "2026-10-12T00:00:00+00:00", "finales": list(finales),
            "pendientes": list(pendientes)}


class SoloLectura:
    """A store that fails the test if anything tries to change it."""

    def __init__(self, almacen) -> None:
        self._almacen = almacen
        self.lecturas: list[tuple[str, int]] = []

    def leer(self, clave, limite, *args):
        self.lecturas.append((clave, limite))
        return self._almacen.leer(clave, limite, *args)

    def tamano_de(self, clave):
        return self._almacen.tamano_de(clave)

    def listar(self, prefijo):
        return self._almacen.listar(prefijo)

    def guardar_temporal(self, *_args):
        raise AssertionError("the verifier wrote to the store")

    def copiar(self, *_args):
        raise AssertionError("the verifier copied inside the store")

    def borrar(self, *_args):
        raise AssertionError("the verifier deleted from the store")


def ejecutar(argumentos: list[str]) -> tuple[int, str, str]:
    salida, errores = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
        try:
            codigo = recuperacion.main(argumentos)
        except SystemExit as exc:       # argparse
            codigo = int(exc.code or 0)
    return codigo, salida.getvalue(), errores.getvalue()


class _Datos(test_archivos.LifecycleChecks):
    """The lifecycle suite's fixture builder, used as a helper (not a TestCase)."""

    def __init__(self, preparar) -> None:
        self.prepare_database = lambda: preparar(self)


class RecoveryChecks:
    """One synthetic source: a KMZ with three versions (history and geometry),
    a PDF, and one upload that was started but never sent (no staging)."""

    def setUp(self) -> None:
        self.datos = _Datos(self.preparar)
        self.datos.setUp()
        self.almacen = self.datos.store
        for n, nombre in enumerate(("poligono_simple", "multiparte", "poligono_con_hueco")):
            self.datos.complete(self.datos.upload(test_archivos.kmz(nombre), "kmz", key=f"kmz-{n}"))
        self.datos.complete(self.datos.upload(test_archivos.PDF))
        self.pendiente = self.datos.start(test_archivos.PDF, key="pendiente")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.carpeta = Path(self.temp.name)

    def ruta_sqlite(self) -> Path | None:
        return self.datos.database

    def construir(self) -> dict:
        with recuperacion.base_solo_lectura(self.ruta_sqlite()) as conn:
            return recuperacion.construir_manifiesto(conn)

    def filas(self) -> dict:
        return {tabla: sorted(self.datos.rows(tabla), key=lambda fila: fila["id"])
                for tabla in TABLAS}

    def test_manifest_covers_every_version_geometry_and_the_pending_upload(self):
        m = self.construir()
        versiones = self.datos.rows("archivo_version")
        disponibles = [v for v in versiones if v["estado"] == "disponible"]
        self.assertEqual(len(disponibles), 4)
        self.assertEqual({(e["clave"], e["tamano"], e["sha256"], e["version_id"])
                          for e in m["finales"]},
                         {(v["clave_final"], v["tamano"], v["sha256"], v["id"])
                          for v in disponibles})
        kmz = [e for e in m["finales"] if e["tipo"] == "kmz"]
        self.assertEqual(sorted(e["numero"] for e in kmz), [1, 2, 3])
        self.assertEqual(len({e["archivo_id"] for e in kmz}), 1)
        self.assertEqual([e["actual"] for e in sorted(kmz, key=lambda e: e["numero"])],
                         [False, False, True])
        self.assertTrue(all(e["geometrias"] == 1 and e["eventos"] >= 1 for e in kmz))
        fila = next(v for v in versiones if v["estado"] == "subiendo")
        self.assertEqual(len(m["pendientes"]), 1)
        self.assertEqual(m["pendientes"][0]["version_id"], self.pendiente["version_id"])
        for campo in ("clave_temporal", "subida_vence_en", "completar_antes_de"):
            self.assertEqual(m["pendientes"][0][campo], fila[campo])
        self.assertNotIn("ficticio", json.dumps(m))      # no original file names
        archivo = self.carpeta / "m.json"
        archivo.write_text(json.dumps(m), encoding="utf-8")
        self.assertEqual(recuperacion.cargar_manifiesto(archivo), m)

    def test_nothing_is_written_to_the_database_or_the_store(self):
        antes = self.filas()
        sqlite = self.ruta_sqlite()
        # The whole directory: the database file and SQLite's side files.
        def en_disco():
            return {p.name: p.read_bytes() for p in sqlite.parent.iterdir()} if sqlite else None
        contenido = en_disco()
        with recuperacion.base_solo_lectura(sqlite) as conn:
            m = recuperacion.construir_manifiesto(conn)
            with self.assertRaises(Exception) as escrito:
                conn.execute("DELETE FROM archivo_evento")
            self.assertRegex(str(escrito.exception).lower(), "read.?only")
        vigilado = SoloLectura(self.almacen)
        self.assertTrue(recuperacion.verificar(m, vigilado)["correcto"])
        self.assertTrue(recuperacion.verificar(m, vigilado,
                                               exportar_a=self.carpeta / "e")["correcto"])
        self.assertTrue(recuperacion.verificar_restauracion(m, vigilado)["correcto"])
        # Every read was bounded by the object's own size and the type's maximum.
        tamanos = {e["clave"]: (e["tamano"], recuperacion.LIMITES[e["tipo"]])
                   for e in m["finales"]}
        self.assertEqual(len(vigilado.lecturas), 12)
        for clave, limite in vigilado.lecturas:
            self.assertEqual(limite, tamanos[clave][0])
            self.assertLessEqual(limite, tamanos[clave][1])
        self.assertEqual(self.filas(), antes)
        self.assertEqual(en_disco(), contenido)

    def test_command_reads_the_database_and_never_prints_the_url(self):
        modulo = SimpleNamespace(fabrica_desde_entorno=lambda entorno: self.almacen)
        with patch.dict(sys.modules, {"server.almacen_supabase": modulo}):
            codigo, salida, errores = ejecutar(self.origen() + ["--almacen-entorno", "--json"])
            self.assertEqual((codigo, errores), (0, ""))
            reporte = json.loads(salida)
            self.assertEqual(reporte["conteos"]["ok"], 4)
            self.assertEqual(len(reporte["pendientes"]), 1)
            self.almacen.perder(self.datos.rows("archivo_version", "numero = 2")[0]["clave_final"])
            codigo, salida, errores = ejecutar(self.origen() + ["--almacen-entorno"])
        self.assertEqual(codigo, 1)
        self.assertIn("CON PROBLEMAS", salida)
        self.assertIn("ausentes: 1", salida)
        self.assertNotIn("://", salida + errores)

    def test_restore_drill(self):
        exportado = self.carpeta / "exportacion"
        origen = recuperacion.verificar(self.construir(), SoloLectura(self.almacen),
                                        exportar_a=exportado)
        self.assertTrue(origen["correcto"])
        self.assertEqual(origen["bytes"]["leidos_del_almacen"], origen["bytes"]["referenciados"])

        raiz = self.carpeta / "destino"
        raiz.mkdir()
        destino = AlmacenLocal(raiz)
        self.addCleanup(destino.close)
        cargar_exportacion(exportado, destino)

        # The restored database and the manifest saved with the export agree.
        del_respaldo = recuperacion.cargar_manifiesto(exportado / recuperacion.NOMBRE_MANIFIESTO)
        for m in (self.construir(), del_respaldo):
            reporte = recuperacion.verificar_restauracion(m, destino)
            self.assertTrue(reporte["correcto"])
            self.assertEqual(reporte["modo"], "restauracion")
            self.assertEqual(reporte["conteos"]["ok"], 4)
            self.assertEqual((reporte["no_referenciados"], reporte["staging"]), ([], []))
            # The pending upload is listed with its deadline, and is not an error.
            self.assertEqual([(p["version_id"], p["staging_presente"])
                              for p in reporte["pendientes"]],
                             [(self.pendiente["version_id"], False)])
            self.assertTrue(reporte["pendientes"][0]["completar_antes_de"])
        texto = recuperacion.resumen(reporte)
        self.assertIn("Verificación de restauración", texto)
        self.assertIn("cancelarlas o reiniciarlas", texto)
        self.assertIn(self.pendiente["version_id"], texto)

        kmz = sorted((e for e in del_respaldo["finales"] if e["tipo"] == "kmz"),
                     key=lambda e: e["numero"])
        perdido, alterado = kmz[0], kmz[2]
        self.assertTrue(destino.borrar(perdido["clave"]))
        poner(destino, alterado["clave"], b"x" * alterado["tamano"])
        reporte = recuperacion.verificar_restauracion(del_respaldo, destino)
        self.assertFalse(reporte["correcto"])
        self.assertEqual(reporte["conteos"], {"ok": 2, "ausente": 1, "tamano_distinto": 0,
                                              "sha_distinto": 1, "ilegible": 0})
        self.assertEqual(
            sorted((p["estado"], p["clave"], p["version_id"]) for p in reporte["problemas"]),
            sorted([("ausente", perdido["clave"], perdido["version_id"]),
                    ("sha_distinto", alterado["clave"], alterado["version_id"])]))
        self.assertEqual(len(reporte["pendientes"]), 1)


class RecuperacionSQLite(RecoveryChecks, unittest.TestCase):
    def preparar(self, datos) -> None:
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        datos.database = Path(carpeta.name) / "attachments.db"

    def origen(self) -> list[str]:
        return ["--sqlite", str(self.datos.database)]

    def test_database_in_use_or_missing_is_refused_not_created(self):
        with db.session(self.datos.database) as abierta:
            abierta.execute("CREATE TABLE en_uso (x)")
            with self.assertRaises(recuperacion.UsoError), \
                    recuperacion.base_solo_lectura(self.datos.database):
                pass
        ausente = self.carpeta / "no-existe.db"
        self.assertEqual(ejecutar(["--sqlite", str(ausente), "--almacen-local",
                                   str(self.carpeta)])[0], 2)
        self.assertFalse(ausente.exists())


@unittest.skipUnless(URL, "No Postgres test connection configured")
class RecuperacionPostgres(RecoveryChecks, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_archivos.AttachmentLifecyclePostgres.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls) -> None:
        test_archivos.AttachmentLifecyclePostgres.tearDownClass.__func__(cls)

    def preparar(self, datos) -> None:
        test_archivos.AttachmentLifecyclePostgres.prepare_database(datos)

    def origen(self) -> list[str]:
        return ["--url-env", "ARA_MAP_DATABASE_URL"]


class VerificacionChecks(unittest.TestCase):
    """The verifier against hand-built stores and manifests: no database."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.carpeta = Path(self.temp.name)
        self.almacen = AlmacenEnMemoria()
        self.datos = {f"final/v{n}/n{n}": bytes([65 + n]) * (70_000 + n) for n in range(4)}
        for clave, datos in self.datos.items():
            poner(self.almacen, clave, datos)
        self.claves = list(self.datos)
        self.manifiesto = manifiesto(*(entrada(c, d) for c, d in self.datos.items()))
        self.total = sum(len(d) for d in self.datos.values())

    def test_each_problem_is_reported_and_one_failure_does_not_stop_the_run(self):
        a, b, c, d = self.claves
        self.almacen.inyectar_falla("leer", tras_bloques=1)      # the first read (`a`) breaks
        poner(self.almacen, b, b"z" * len(self.datos[b]))
        poner(self.almacen, c, self.datos[c] + b"!")
        self.almacen.perder(d)
        poner(self.almacen, "final/huerfano/x", b"12345")
        self.almacen.guardar_temporal("temporal/suelto", [b"123"], 10)
        reporte = recuperacion.verificar(self.manifiesto, SoloLectura(self.almacen), presupuesto=1)
        estados = {p["clave"]: p["estado"] for p in reporte["problemas"]}
        self.assertEqual(estados, {a: "ilegible", b: "sha_distinto", c: "tamano_distinto",
                                   d: "ausente"})
        self.assertEqual(reporte["conteos"]["ok"], 0)
        self.assertFalse(reporte["correcto"])
        self.assertEqual(reporte["no_referenciados"], [{"clave": "final/huerfano/x", "tamano": 5}])
        self.assertEqual(reporte["staging"], [{"clave": "temporal/suelto", "tamano": 3}])
        self.assertEqual(reporte["bytes"]["referenciados"], self.total)
        self.assertEqual(reporte["bytes"]["retenidos"], self.total + 8)
        self.assertTrue(reporte["bytes"]["excede_presupuesto"])
        self.assertIn("EXCEDE", recuperacion.resumen(reporte))
        reporte = recuperacion.verificar(self.manifiesto, self.almacen)
        self.assertEqual(reporte["conteos"]["ok"], 1)            # `a` reads fine again
        self.assertFalse(reporte["bytes"]["excede_presupuesto"])

    def test_listing_failure_keeps_the_verdicts_and_is_not_a_clean_result(self):
        class SinListado(SoloLectura):
            def listar(self, prefijo):
                raise OSError("listing is down")

        reporte = recuperacion.verificar(self.manifiesto, SinListado(self.almacen))
        self.assertEqual(reporte["conteos"]["ok"], 4)
        self.assertFalse(reporte["listado_completo"])
        self.assertFalse(reporte["correcto"])

    def test_export_is_incremental_and_repairs_a_corrupt_local_copy(self):
        destino = self.carpeta / "exportacion"
        primero = recuperacion.verificar(self.manifiesto, self.almacen, exportar_a=destino)
        self.assertTrue(primero["correcto"])
        self.assertEqual(primero["bytes"]["leidos_del_almacen"], self.total)
        archivos = sorted(str(p.relative_to(destino)) for p in destino.rglob("*") if p.is_file())
        self.assertEqual(archivos, sorted(self.claves + [recuperacion.NOMBRE_MANIFIESTO]))
        for clave, datos in self.datos.items():
            self.assertEqual((destino / clave).read_bytes(), datos)

        vigilado = SoloLectura(self.almacen)
        segundo = recuperacion.verificar(self.manifiesto, vigilado, exportar_a=destino)
        self.assertTrue(segundo["correcto"])
        self.assertEqual((vigilado.lecturas, segundo["bytes"]["leidos_del_almacen"]), ([], 0))
        self.assertEqual(segundo["exportacion"], {"copias_locales_reutilizadas": 4,
                                                  "copias_locales_corruptas": []})

        a, b, c, _d = self.claves
        (destino / a).write_bytes(b"y" * len(self.datos[a]))     # corrupt, same size
        (destino / b).unlink()                                   # never exported
        self.almacen.perder(c)                  # lost at the source after it was exported
        tercero = recuperacion.verificar(self.manifiesto, self.almacen, exportar_a=destino)
        self.assertEqual(tercero["bytes"]["leidos_del_almacen"],
                         len(self.datos[a]) + len(self.datos[b]))
        self.assertEqual(tercero["exportacion"]["copias_locales_corruptas"],
                         [{"clave": a, "reemplazada": True}])
        self.assertEqual([(p["clave"], p["estado"]) for p in tercero["problemas"]],
                         [(c, "ausente")])
        self.assertEqual((destino / a).read_bytes(), self.datos[a])
        self.assertEqual((destino / b).read_bytes(), self.datos[b])

    def test_unverified_bytes_never_reach_the_export_directory(self):
        a = self.claves[0]
        poner(self.almacen, a, b"q" * len(self.datos[a]))
        destino = self.carpeta / "exportacion"
        reporte = recuperacion.verificar(self.manifiesto, self.almacen, exportar_a=destino)
        self.assertEqual([(p["clave"], p["estado"]) for p in reporte["problemas"]],
                         [(a, "sha_distinto")])
        self.assertEqual(sorted(p.name for p in (destino / a).parent.iterdir()), [])

    def test_malformed_manifests_are_rejected(self):
        bueno = entrada("final/v0/n0", b"abc")
        casos = [
            [], {**manifiesto(), "formato": "otro"}, {**manifiesto(), "version": 2},
            {k: v for k, v in manifiesto().items() if k != "pendientes"},
            manifiesto({**bueno, "clave": "final/../n0"}),
            manifiesto({**bueno, "clave": "temporal/v0"}),
            manifiesto({**bueno, "tamano": -1}), manifiesto({**bueno, "tamano": True}),
            manifiesto({**bueno, "sha256": "ABC"}), manifiesto({**bueno, "tipo": "exe"}),
            manifiesto(bueno, bueno), manifiesto(pendientes=("x",)),
        ]
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(recuperacion.ManifiestoInvalidoError):
                recuperacion.validar_manifiesto(caso)
        with self.assertRaises(recuperacion.ManifiestoInvalidoError):
            recuperacion.cargar_manifiesto(self.carpeta / "no-existe.json")

    def test_command_line_exit_codes_and_store_selection(self):
        raiz = self.carpeta / "almacen"
        raiz.mkdir()
        with AlmacenLocal(raiz) as local:
            for clave, datos in self.datos.items():
                poner(local, clave, datos)
        archivo = self.carpeta / "m.json"
        archivo.write_text(json.dumps(self.manifiesto), encoding="utf-8")
        base = ["--manifiesto", str(archivo)]
        local_ok = base + ["--almacen-local", str(raiz)]

        codigo, salida, _ = ejecutar(local_ok + ["--restauracion"])
        self.assertEqual(codigo, 0)
        self.assertIn("Verificación de restauración", salida)
        self.assertIn("CORRECTO", salida)
        exportado = self.carpeta / "exportado"
        codigo, salida, _ = ejecutar(local_ok + ["--exportar", str(exportado), "--json",
                                                 "--presupuesto", "10"])
        self.assertEqual(codigo, 0)                      # the budget is a report, not a gate
        self.assertTrue(json.loads(salida)["bytes"]["excede_presupuesto"])
        self.assertTrue((exportado / self.claves[0]).is_file())

        (raiz / self.claves[0]).unlink()
        self.assertEqual(ejecutar(local_ok)[0], 1)

        for argumentos in (
            base + ["--almacen-local", str(self.carpeta / "no-existe")],
            ["--manifiesto", str(self.carpeta / "no-existe.json"), "--almacen-local", str(raiz)],
            ["--url-env", "ARA_MAP_VARIABLE_QUE_NO_EXISTE", "--almacen-local", str(raiz)],
            local_ok + ["--restauracion", "--exportar", str(exportado)],
            base, base + ["--almacen-entorno"],          # the remote module is not in this tree
        ):
            with self.subTest(argumentos=argumentos):
                codigo, salida, errores = ejecutar(argumentos)
                self.assertEqual((codigo, salida), (2, ""))
                self.assertTrue(errores)
        sin_configurar = SimpleNamespace(fabrica_desde_entorno=lambda entorno: None)
        with patch.dict(sys.modules, {"server.almacen_supabase": sin_configurar}):
            codigo, _, errores = ejecutar(base + ["--almacen-entorno"])
        self.assertEqual(codigo, 2)
        self.assertIn("no está configurado", errores)

    def test_script_help_runs_with_the_standard_library_only(self):
        hecho = subprocess.run(
            [sys.executable, "-S", str(RAIZ / "scripts" / "verificar_archivos.py"), "--help"],
            capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(hecho.returncode, 0, hecho.stderr)
        self.assertIn("--almacen-entorno", hecho.stdout)


if __name__ == "__main__":
    unittest.main()
