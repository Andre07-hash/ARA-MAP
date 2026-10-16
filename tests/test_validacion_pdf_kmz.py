"""Issue #51: regressions the PDF/KMZ validation found missing from the suites.

Each check goes over real loopback HTTP through the one production Handler,
reusing the fixtures of tests/test_archivos_http.py (cookie sessions, the
in-memory store, the controlled clock), on SQLite and on a disposable
Postgres schema. Only the checks defined here are loaded: the inherited
2B matrix keeps running from its own module.

- Valid files exactly at the 25 MiB (PDF) and 20 MiB (KMZ) limits complete
  and download with the same bytes; one byte over is refused and saves nothing.
- An upload that expires (content deadline and completion deadline, exactly
  at equality) never takes away an earlier saved PDF or the active boundary.
- Deleting a terrain's only PDF leaves the terrain, answers the old download
  link with the real 404 and drops the PDF from the listing.
- Two completions of one version racing on real threads (a double click)
  give one fresh result and one replay or "busy" answer, never two saves.
"""

from __future__ import annotations

import hashlib
import io
import random
import threading
import unittest
import zipfile

from server import app as app_module
from server import archivos
from tests import test_archivos_http as base
from tests.test_archivos_http import PDF, kmz

MiB = 1024 * 1024


def pdf_de(tamano: int, semilla: int = 51) -> bytes:
    """A fictional PDF of exactly `tamano` bytes (PDF signature, random filler)."""
    cabeza = b"%PDF-1.4\n% ficticio\n"
    cola = b"\n%%EOF\n"
    return cabeza + random.Random(semilla).randbytes(tamano - len(cabeza) - len(cola)) + cola


def kmz_de(tamano: int, semilla: int = 51) -> bytes:
    """A fictional KMZ of exactly `tamano` bytes: one valid polygon plus a stored filler member."""
    kml = (base.FIXTURES / "kmz" / "poligono_simple.kml").read_bytes()

    def armar(relleno: int) -> bytes:
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w") as zf:
            zf.writestr(zipfile.ZipInfo("doc.kml", date_time=(2026, 10, 15, 0, 0, 0)), kml,
                        compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr(zipfile.ZipInfo("files/relleno.bin", date_time=(2026, 10, 15, 0, 0, 0)),
                        random.Random(semilla).randbytes(relleno), compress_type=zipfile.ZIP_STORED)
        return salida.getvalue()
    datos = armar(1 + tamano - len(armar(1)))
    assert len(datos) == tamano
    return datos


class Validacion:
    """Mixed into the 2B HTTP fixture; see load_tests for what runs."""

    def descarga_identica(self, version_id: str, esperado: bytes) -> None:
        s, h, cuerpo = self.bajar(f"/api/archivos/versiones/{version_id}/descarga")
        self.assertEqual(s, 200)
        self.assertEqual(len(cuerpo), len(esperado))
        self.assertEqual(hashlib.sha256(cuerpo).hexdigest(), hashlib.sha256(esperado).hexdigest())
        self.assertEqual(h["X-Archivo-Sha256"], hashlib.sha256(esperado).hexdigest())

    def listado(self) -> list[dict]:
        s, r = self.j("GET", f"/api/inventario/terrenos/{self.terreno}/archivos")
        self.assertEqual(s, 200, r)
        return r["archivos"]

    def test_valid_files_at_the_limit_complete_and_one_byte_over_saves_nothing(self):
        self.assertEqual((archivos.PDF_MAX, archivos.KMZ_MAX), (25 * MiB, 20 * MiB))
        self.assertGreaterEqual(app_module.MAX_BODY, archivos.PDF_MAX)
        pdf = pdf_de(archivos.PDF_MAX)
        inicio, r = self.archivo_completo(pdf, "pdf", login="olga", nombre="Límite ñ (25 MiB).pdf")
        self.assertEqual((r["version"]["estado"], r["version"]["tamano"]), ("disponible", archivos.PDF_MAX))
        self.descarga_identica(inicio["version_id"], pdf)
        datos = kmz_de(archivos.KMZ_MAX)
        inicio_kmz, r = self.archivo_completo(datos, "kmz", login="olga")
        self.assertEqual((r["version"]["estado"], r["intento"]["resultado"], r["aplicada"]),
                         ("disponible", "listo", True))
        self.descarga_identica(inicio_kmz["version_id"], datos)
        guardados = {a["id"]: a["version_actual_id"] for a in self.listado()}
        # One byte over the KMZ limit in the body: 413, nothing staged, nothing saved.
        s, mas = self.iniciar(b"x", "kmz", login="olga", tamano=1)
        s, err = self.subir(mas["version_id"], datos + b"\0", login="olga")
        self.assertEqual((s, err["detalle"]["code"]), (413, "tamano_excedido"))
        s, err = self.completar(mas["version_id"], login="olga")
        self.assertEqual((s, err["detalle"]["code"]), (409, "contenido_temporal_ausente"))
        self.assertEqual(list(self.store.listar("temporal/")), [])
        # Declared one byte over either limit: refused before any version exists.
        for tipo, maximo in (("pdf", archivos.PDF_MAX), ("kmz", archivos.KMZ_MAX)):
            s, err = self.iniciar(b"x", tipo, login="olga", tamano=maximo + 1)
            self.assertEqual((s, err["detalle"]["code"]), (400, "tamano_invalido"))
        # The KMZ start appended a pending version to the one KMZ attachment;
        # its current (saved) version and the PDF's are unchanged.
        self.assertEqual({a["id"]: a["version_actual_id"] for a in self.listado()}, guardados)
        self.descarga_identica(inicio["version_id"], pdf)
        self.descarga_identica(inicio_kmz["version_id"], datos)

    def test_an_expired_upload_never_takes_away_the_saved_pdf_or_the_active_boundary(self):
        guardado, _ = self.archivo_completo(PDF, login="olga", nombre="Guardado.pdf")
        contorno, r = self.archivo_completo(kmz("poligono_simple"), "kmz", login="olga")
        activa = r["archivo"]["geometria_activa_id"]
        nuevo = PDF + b"% reemplazo ficticio\n"
        # Content deadline: one second before it the PUT is accepted, at equality it is not.
        s, sin_contenido = self.iniciar(nuevo, login="olga")
        s, con_contenido = self.iniciar(nuevo + b"%", login="olga")
        s, kmz_tarde = self.iniciar(kmz("forma_u"), "kmz", login="olga")
        self.reloj.avanzar(archivos.UPLOAD_SECONDS - 1)
        s, r = self.subir(con_contenido["version_id"], nuevo + b"%", login="olga")
        self.assertEqual(s, 200, r)
        s, r = self.subir(kmz_tarde["version_id"], kmz("forma_u"), login="olga")
        self.assertEqual(s, 200, r)
        self.reloj.avanzar(1)
        s, r = self.subir(sin_contenido["version_id"], nuevo, login="olga")
        self.assertEqual((s, r["detalle"]["code"]), (409, "subida_expirada"))
        # Completion deadline at equality: both pending uploads expire.
        self.reloj.avanzar(archivos.COMPLETE_SECONDS - archivos.UPLOAD_SECONDS)
        for pendiente in (con_contenido, kmz_tarde, sin_contenido):
            s, r = self.completar(pendiente["version_id"], login="olga")
            self.assertEqual((s, r["detalle"]["code"]), (409, "subida_expirada"))
        self.descarga_identica(guardado["version_id"], PDF)
        estados = {a["id"]: (a["ultima_version"] or {}).get("estado") for a in self.listado()}
        self.assertEqual(estados[guardado["archivo_id"]], "disponible")
        self.assertEqual(estados[con_contenido["archivo_id"]], "expirado")
        self.assertEqual(estados[sin_contenido["archivo_id"]], "expirado")
        s, meta = self.j("POST", "/api/archivos/geometrias/metadatos", login="olga",
                         datos={"ids": [activa]})
        self.assertTrue(meta["geometrias"][activa]["activa"])
        with base.db.session() as conn:
            fila = conn.execute("SELECT geometria_activa_id FROM archivo WHERE id = ?",
                                (contorno["archivo_id"],)).fetchone()
        self.assertEqual(fila["geometria_activa_id"], activa)

    def test_deleting_the_only_pdf_keeps_the_terrain_and_the_old_link_is_a_real_404(self):
        inicio, r = self.archivo_completo(PDF, login="olga")
        s, borrado = self.j("POST", f"/api/archivos/{inicio['archivo_id']}/borrar", login="olga",
                            datos={"expected_revision": r["archivo"]["revision"]})
        self.assertEqual((s, borrado["borrado"]), (200, True))
        for login in ("olga", "ana"):
            s, _h, cuerpo = self.bajar(f"/api/archivos/versiones/{inicio['version_id']}/descarga", login)
            self.assertEqual((s, base.json.loads(cuerpo)["detalle"]["code"]), (404, "not_found"))
        self.assertEqual(self.listado(), [])
        self.assertEqual(len(self.filas("inventory_terrain", "id = ?", (self.terreno,))), 1)
        sesion = self._sesion("olga")       # not nested: a Postgres session holds a lock
        with base.db.session() as conn:
            resumen = archivos.resumenes_de_archivos(conn, [self.terreno], sesion)
        self.assertEqual(resumen["resultados"][self.terreno],
                         {"pdf_total": 0, "pdf_recientes": [], "kmz": None})

    def _sesion(self, login: str):
        with base.db.session() as conn:
            return base.auth.sesion_de_token(conn, self.tokens[login])

    def test_a_double_click_on_completion_saves_once(self):
        for vuelta in range(3):               # the race is repeated, not retried until green
            with self.subTest(vuelta=vuelta):
                contenido = PDF + f"% vuelta {vuelta}\n".encode()
                s, inicio = self.iniciar(contenido, login="olga")
                self.subir(inicio["version_id"], contenido, login="olga")
                barrera = threading.Barrier(2)
                respuestas: list = []

                def completar(barrera=barrera, respuestas=respuestas, vid=inicio["version_id"]) -> None:
                    barrera.wait()
                    respuestas.append(self.completar(vid, login="olga"))
                hilos = [threading.Thread(target=completar) for _ in range(2)]
                for h in hilos:
                    h.start()
                for h in hilos:
                    h.join()
                frescas = [r for s, r in respuestas if s == 200 and r["replay"] is False]
                self.assertEqual(len(frescas), 1, respuestas)
                for s, r in respuestas:
                    if not (s == 200 and r["replay"] is False):
                        self.assertTrue((s == 200 and r["replay"] is True)
                                        or (s, r["detalle"]["code"]) == (409, "procesamiento_en_curso"), r)
                s, r = self.completar(inicio["version_id"], login="olga")
                self.assertEqual((s, r["replay"], r["version"]["estado"]), (200, True, "disponible"))
                self.assertEqual(len(self.filas("archivo_version", "archivo_id = ?",
                                                (inicio["archivo_id"],))), 1)
                self.assertEqual(len(list(self.store.listar(f"final/{inicio['version_id'].replace('-', '')}/"))), 1)
                self.descarga_identica(inicio["version_id"], contenido)


class ValidacionSQLite(Validacion, base.HTTPSQLite):
    pass


class ValidacionPostgres(Validacion, base.HTTPPostgres):
    pass


def load_tests(loader: unittest.TestLoader, _tests: unittest.TestSuite, _pattern: str | None
               ) -> unittest.TestSuite:
    """Only this module's checks; the inherited 2B matrix runs from its own module."""
    propios = sorted(n for n in vars(Validacion) if n.startswith("test_"))
    suite = unittest.TestSuite()
    for clase in (ValidacionSQLite, ValidacionPostgres):
        suite.addTests(clase(nombre) for nombre in propios)
    return suite


if __name__ == "__main__":
    unittest.main()
