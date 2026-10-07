"""Byte storage core: one behavioural contract run against both backends.

Every test uses a temporary root or the in-memory fake, with synthetic bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import tracemalloc
import unittest
from array import array
from collections.abc import Iterator
from unittest import mock

from server import almacen
from server.almacen import (
    MAX_BLOQUE,
    AlmacenEnMemoria,
    AlmacenLocal,
    ClaveInvalidaError,
    ColisionError,
    FalloAlmacenError,
    LimiteExcedidoError,
    ObjetoAusenteError,
)

KB = 1024
MB = 1024 * KB
RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLAVES_INVALIDAS = [
    "", "temporal", "temporal/", "/temporal/a", "temporal//a", "temporal/../a",
    "temporal/a/b", "temporal/A", "temporal/.parcial-a", "temporal/a b", "temporal/a\n",
    "temporal/-a", "temporal/" + "a" * 101, "temporal/á", "otro/a", "final", "final/a",
    "final/a/", "final/a/b/c", "final/../a", "./temporal/a", "temporal\\a", None, b"temporal/a",
]


def trozos(datos: bytes, tamano: int) -> Iterator[bytes]:
    for i in range(0, len(datos), tamano):
        yield datos[i:i + tamano]


def contenido(almacen_: almacen.Almacen, clave: str, limite: int = 64 * MB) -> bytes:
    with almacen_.leer(clave, limite) as lectura:
        return b"".join(lectura)


class Contrato:
    """Behaviour both backends must share. Subclasses provide `crear` and `abierta`."""

    def crear(self) -> almacen.Almacen:
        raise NotImplementedError

    def abierta(self, lectura: almacen.Lectura) -> bool:
        raise NotImplementedError

    def setUp(self) -> None:
        self.a = self.crear()

    # -- staging writes

    def test_empty_object(self) -> None:
        self.assertEqual(self.a.guardar_temporal("temporal/v1", [], 10), 0)
        self.assertEqual(self.a.tamano_de("temporal/v1"), 0)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"")
        self.assertEqual(self.a.guardar_temporal("temporal/v2", [b"", b""], 1), 0)

    def test_arbitrary_binary_bytes_round_trip(self) -> None:
        datos = bytes(range(256)) * 1000 + b"\x00\xff\r\n%PDF-\x00PK\x03\x04"
        for tamano in (1, 7, 4096, MAX_BLOQUE):
            with self.subTest(tamano=tamano):
                escritos = self.a.guardar_temporal("temporal/v1", trozos(datos, tamano), len(datos))
                self.assertEqual(escritos, len(datos))
                self.assertEqual(contenido(self.a, "temporal/v1"), datos)

    def test_accepts_bytearray_and_memoryview_chunks(self) -> None:
        self.a.guardar_temporal("temporal/v1", [bytearray(b"ab"), memoryview(b"cd")], 4)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"abcd")

    def test_exact_limit_and_one_byte_over(self) -> None:
        self.assertEqual(self.a.guardar_temporal("temporal/v1", [b"x" * 100], 100), 100)
        with self.assertRaises(LimiteExcedidoError) as ctx:
            self.a.guardar_temporal("temporal/v2", [b"x" * 50, b"x" * 51], 100)
        self.assertEqual(ctx.exception.limite, 100)
        self.assertIsNone(self.a.tamano_de("temporal/v2"))

    def test_replacement_exposes_the_new_complete_object(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"primero"], 100)
        self.a.guardar_temporal("temporal/v1", [b"segundo", b" completo"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"segundo completo")

    def test_failed_replacement_keeps_the_previous_object(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"original"], 100)

        def interrumpido() -> Iterator[bytes]:
            yield b"parcial"
            raise RuntimeError("cliente desconectado")

        with self.assertRaises(RuntimeError):
            self.a.guardar_temporal("temporal/v1", interrumpido(), 100)
        with self.assertRaises(LimiteExcedidoError):
            self.a.guardar_temporal("temporal/v1", [b"z" * 60, b"z" * 60], 100)
        with self.assertRaises(TypeError):
            self.a.guardar_temporal("temporal/v1", [b"ok", "texto"], 100)   # type: ignore[list-item]
        with self.assertRaises(ValueError):
            self.a.guardar_temporal("temporal/v1", [b"z" * (MAX_BLOQUE + 1)], 10 * MB)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"original")
        self.assertEqual(self.a.tamano_de("temporal/v1"), 8)

    def test_oversized_chunks_are_rejected_before_copying(self) -> None:
        # S1 review (S2): the byte size is checked before any copy is made.
        # Buffers are allocated before measuring, so only the store's own
        # allocations count.
        grande = bytearray(32 * MB)
        tipado = array("I", [7]) * (MAX_BLOQUE // 4 + 1)          # 262,145 elements
        dos_d = memoryview(bytearray(2 * MAX_BLOQUE)).cast("B", shape=[2, MAX_BLOQUE])
        casos = {
            "bytearray": grande,
            "memoryview": memoryview(grande),
            "typed view": memoryview(tipado),
            "2-D view": dos_d,
            "bytes": bytes(MAX_BLOQUE + 1),
        }
        self.assertLessEqual(len(memoryview(tipado)), MAX_BLOQUE)
        self.assertGreater(memoryview(tipado).nbytes, MAX_BLOQUE)
        self.assertEqual(len(dos_d), 2)
        self.a.guardar_temporal("temporal/v1", [b"previo"], 100)
        for nombre, bloque in casos.items():
            with self.subTest(nombre):
                tracemalloc.start()
                try:
                    with self.assertRaises(ValueError):
                        self.a.guardar_temporal("temporal/v1", [b"ok", bloque], 64 * MB)
                    _, pico = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertLess(pico, 256 * KB, f"{nombre}: peak {pico} bytes")
                self.assertEqual(contenido(self.a, "temporal/v1"), b"previo")

    def test_typed_and_multidimensional_views_round_trip(self) -> None:
        tipado = array("H", range(1000))
        self.a.guardar_temporal("temporal/v1", [memoryview(tipado)], 2000)
        self.assertEqual(contenido(self.a, "temporal/v1"), tipado.tobytes())
        rejilla = memoryview(bytearray(b"abcdef")).cast("B", shape=[2, 3])
        salteado = memoryview(b"abcdef")[::2]
        self.a.guardar_temporal("temporal/v2", [rejilla, salteado], 9)
        self.assertEqual(contenido(self.a, "temporal/v2"), b"abcdeface")
        justo = memoryview(array("I", [1]) * (MAX_BLOQUE // 4))      # nbytes == MAX_BLOQUE
        self.assertEqual(self.a.guardar_temporal("temporal/v3", [justo], MAX_BLOQUE), MAX_BLOQUE)

    def test_chunks_must_be_an_iterable_of_bytes(self) -> None:
        for malo in (b"abc", bytearray(b"abc"), "abc"):
            with self.subTest(malo=malo), self.assertRaises(TypeError):
                self.a.guardar_temporal("temporal/v1", malo, 10)  # type: ignore[arg-type]
        self.assertIsNone(self.a.tamano_de("temporal/v1"))

    def test_limit_must_be_a_positive_int(self) -> None:
        for limite in (0, -1, True, 1.5, None, "10"):
            with self.subTest(limite=limite):
                with self.assertRaises(ValueError):
                    self.a.guardar_temporal("temporal/v1", [b""], limite)  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    self.a.leer("temporal/v1", limite)  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    self.a.copiar("temporal/v1", "final/v1/n1", limite)  # type: ignore[arg-type]

    # -- keys

    def test_invalid_keys_are_rejected_by_every_operation(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        for clave in CLAVES_INVALIDAS:
            with self.subTest(clave=clave):
                for operacion in (
                    lambda c: self.a.guardar_temporal(c, [b"x"], 10),
                    lambda c: self.a.copiar(c, "final/v1/n1", 10),
                    lambda c: self.a.copiar("temporal/v1", c, 10),
                    lambda c: self.a.leer(c, 10),
                    lambda c: self.a.tamano_de(c),
                    lambda c: self.a.borrar(c),
                ):
                    with self.assertRaises(ClaveInvalidaError):
                        operacion(clave)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))

    def test_namespaces_are_enforced(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        with self.assertRaises(ClaveInvalidaError):
            self.a.guardar_temporal("final/v1/n1", [b"x"], 10)
        with self.assertRaises(ClaveInvalidaError):
            self.a.copiar("temporal/v1", "temporal/v2", 10)
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        with self.assertRaises(ClaveInvalidaError):
            self.a.copiar("final/v1/n1", "final/v1/n2", 10)

    def test_error_messages_carry_no_key_or_path(self) -> None:
        errores: list[almacen.AlmacenError] = []
        for accion in (lambda: self.a.leer("temporal/secreto1", 10),
                       lambda: self.a.leer("../etc/passwd", 10)):
            try:
                accion()
            except almacen.AlmacenError as exc:
                errores.append(exc)
        self.assertEqual([type(e) for e in errores], [ObjetoAusenteError, ClaveInvalidaError])
        for exc in errores:
            self.assertNotIn("secreto1", str(exc))
            self.assertNotIn("/", str(exc))

    # -- absent objects

    def test_absent_objects(self) -> None:
        self.assertIsNone(self.a.tamano_de("temporal/nada"))
        self.assertIsNone(self.a.tamano_de("final/nada/n1"))
        with self.assertRaises(ObjetoAusenteError):
            self.a.leer("final/nada/n1", 10)
        with self.assertRaises(ObjetoAusenteError):
            self.a.copiar("temporal/nada", "final/nada/n1", 10)
        self.assertFalse(self.a.borrar("temporal/nada"))
        self.assertIsNone(self.a.tamano_de("final/nada/n1"))

    # -- reads

    def test_read_limit_is_checked_before_any_byte(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"y" * 100], 100)
        self.assertEqual(len(contenido(self.a, "temporal/v1", limite=100)), 100)
        with self.assertRaises(LimiteExcedidoError):
            self.a.leer("temporal/v1", 99)

    def test_read_streams_in_bounded_chunks(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"q" * 10_000], 10_000)
        with self.a.leer("temporal/v1", 10_000, bloque=4096) as lectura:
            self.assertEqual(lectura.tamano, 10_000)
            tamanos = [len(b) for b in lectura]
        self.assertTrue(all(t <= 4096 for t in tamanos))
        self.assertEqual(sum(tamanos), 10_000)
        for bloque in (0, MAX_BLOQUE + 1, True):
            with self.subTest(bloque=bloque), self.assertRaises(ValueError):
                self.a.leer("temporal/v1", 10_000, bloque=bloque)

    def test_early_close_releases_the_reader(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"r" * 50_000], 50_000)
        lectura = self.a.leer("temporal/v1", 50_000, bloque=1000)
        self.assertEqual(len(next(lectura)), 1000)
        self.assertTrue(self.abierta(lectura))
        lectura.close()
        self.assertFalse(self.abierta(lectura))
        self.assertEqual(list(lectura), [])
        with self.a.leer("temporal/v1", 50_000, bloque=1000) as otra:
            next(otra)
        self.assertFalse(self.abierta(otra))
        agotada = self.a.leer("temporal/v1", 50_000)
        list(agotada)
        self.assertFalse(self.abierta(agotada))

    # -- copy to final

    def test_final_bytes_survive_later_staging_writes(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"evidencia original"], 100)
        self.assertEqual(self.a.copiar("temporal/v1", "final/v1/n1", 100), 18)
        self.a.guardar_temporal("temporal/v1", [b"escritura posterior con credencial"], 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"evidencia original")
        self.assertTrue(self.a.borrar("temporal/v1"))
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"evidencia original")

    def test_verify_after_copy_reads_the_final_object(self) -> None:
        datos = os.urandom(300_000)
        self.a.guardar_temporal("temporal/v1", trozos(datos, 65_536), len(datos))
        self.a.copiar("temporal/v1", "final/v1/n1", len(datos))
        h = hashlib.sha256()
        total = 0
        with self.a.leer("final/v1/n1", len(datos)) as lectura:
            for bloque in lectura:
                h.update(bloque)
                total += len(bloque)
        self.assertEqual((total, h.hexdigest()), (len(datos), hashlib.sha256(datos).hexdigest()))

    def test_existing_final_key_is_never_overwritten(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"ganador"], 100)
        self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.a.guardar_temporal("temporal/v1", [b"intruso"], 100)
        with self.assertRaises(ColisionError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"ganador")

    def test_two_nonces_may_both_succeed(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"uno"], 100)
        self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.a.guardar_temporal("temporal/v1", [b"dos"], 100)
        self.a.copiar("temporal/v1", "final/v1/n2", 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"uno")
        self.assertEqual(contenido(self.a, "final/v1/n2"), b"dos")

    def test_copy_limit(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"c" * 101], 200)
        with self.assertRaises(LimiteExcedidoError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        self.assertEqual(self.a.copiar("temporal/v1", "final/v1/n1", 101), 101)

    def test_concurrent_copies_to_one_destination_have_one_winner(self) -> None:
        participantes = 8
        for i in range(participantes):
            self.a.guardar_temporal(f"temporal/c{i}", [bytes([65 + i]) * 200_000], MB)
        barrera = threading.Barrier(participantes)
        resultados: dict[int, str] = {}

        def copiar(i: int) -> None:
            barrera.wait()
            try:
                self.a.copiar(f"temporal/c{i}", "final/v1/compartido", MB)
                resultados[i] = "ok"
            except ColisionError:
                resultados[i] = "colision"

        hilos = [threading.Thread(target=copiar, args=(i,)) for i in range(participantes)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        ganadores = [i for i, r in resultados.items() if r == "ok"]
        self.assertEqual(len(ganadores), 1, resultados)
        self.assertEqual(sorted(resultados.values()).count("colision"), participantes - 1)
        self.assertEqual(contenido(self.a, "final/v1/compartido"),
                         bytes([65 + ganadores[0]]) * 200_000)

    def test_staging_replacement_racing_copies_gives_whole_snapshots(self) -> None:
        tamano = 256 * KB
        versiones = (b"A" * tamano, b"B" * tamano)
        self.a.guardar_temporal("temporal/v1", trozos(versiones[0], 64 * KB), tamano)
        alto = threading.Event()

        def escritor() -> None:
            i = 0
            while not alto.is_set():
                i += 1
                self.a.guardar_temporal("temporal/v1", trozos(versiones[i % 2], 64 * KB), tamano)

        hilo = threading.Thread(target=escritor)
        hilo.start()
        try:
            for n in range(25):
                self.a.copiar("temporal/v1", f"final/v1/n{n}", tamano)
                with self.subTest(n=n):
                    self.assertIn(contenido(self.a, f"final/v1/n{n}"), versiones)
        finally:
            alto.set()
            hilo.join()

    # -- delete and list

    def test_delete_is_exact_and_idempotent(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"t"], 10)
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.a.copiar("temporal/v1", "final/v1/n2", 10)
        self.assertTrue(self.a.borrar("final/v1/n1"))
        self.assertFalse(self.a.borrar("final/v1/n1"))
        self.assertEqual(self.a.tamano_de("final/v1/n2"), 1)
        self.assertEqual(self.a.tamano_de("temporal/v1"), 1)
        for prefijo in ("final/v1", "final/v1/", "final/", "temporal/"):
            with self.subTest(prefijo=prefijo), self.assertRaises(ClaveInvalidaError):
                self.a.borrar(prefijo)

    def test_listing(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"12345"], 10)
        self.a.guardar_temporal("temporal/v2", [], 10)
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.a.copiar("temporal/v1", "final/v2/n1", 10)
        iterador = self.a.listar("final/")
        self.assertIs(iter(iterador), iterador)
        self.assertEqual(sorted(m.clave for m in iterador), ["final/v1/n1", "final/v2/n1"])
        temporales = {m.clave: m.tamano for m in self.a.listar("temporal/")}
        self.assertEqual(temporales, {"temporal/v1": 5, "temporal/v2": 0})
        self.assertEqual([m.clave for m in self.a.listar("final/v2/")], ["final/v2/n1"])
        self.assertEqual(list(self.a.listar("final/nada/")), [])
        metadato = next(self.a.listar("final/v1/"))
        self.assertGreater(metadato.modificado, 0)
        self.assertEqual(self.a.tamano_de("temporal/v1"), 5)     # listing removes nothing

    def test_listing_prefixes_are_explicit(self) -> None:
        for prefijo in ("", "/", "temporal", "final", "final/v1", "final/v1/n1/", "temporal/v1/",
                        "../", "otro/", "final/V1/", "final//", None):
            with self.subTest(prefijo=prefijo), self.assertRaises(ClaveInvalidaError):
                self.a.listar(prefijo)  # type: ignore[arg-type]

    def test_listing_an_empty_store(self) -> None:
        self.assertEqual(list(self.a.listar("temporal/")), [])
        self.assertEqual(list(self.a.listar("final/")), [])


class ContratoLocal(Contrato, unittest.TestCase):
    def crear(self) -> almacen.Almacen:
        self.raiz = tempfile.mkdtemp(prefix="ara-almacen-")
        self.addCleanup(shutil.rmtree, self.raiz, True)
        local = AlmacenLocal(self.raiz)
        self.addCleanup(local.close)
        return local

    def abierta(self, lectura: almacen.Lectura) -> bool:
        return lectura._fd is not None


class ContratoEnMemoria(Contrato, unittest.TestCase):
    def crear(self) -> almacen.Almacen:
        return AlmacenEnMemoria()

    def abierta(self, lectura: almacen.Lectura) -> bool:
        return not lectura.cerrada


class AlmacenLocalSeguridad(unittest.TestCase):
    """Containment, partial files and faults specific to the filesystem backend."""

    def setUp(self) -> None:
        self.base = tempfile.mkdtemp(prefix="ara-almacen-")
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = os.path.join(self.base, "raiz")
        self.fuera = os.path.join(self.base, "fuera")
        os.mkdir(self.raiz)
        os.mkdir(self.fuera)
        self.secreto = os.path.join(self.fuera, "secreto")
        with open(self.secreto, "wb") as f:
            f.write(b"no debe leerse")
        self.a = AlmacenLocal(self.raiz)
        self.addCleanup(self.a.close)

    def ruta(self, *partes: str) -> str:
        return os.path.join(self.raiz, *partes)

    def parciales(self) -> list[str]:
        encontrados = []
        for actual, _, archivos in os.walk(self.raiz):
            encontrados += [os.path.join(actual, a) for a in archivos if a.startswith(".parcial-")]
        return encontrados

    def test_constructing_creates_nothing_and_needs_an_existing_root(self) -> None:
        self.assertEqual(os.listdir(self.raiz), [])
        with self.assertRaises(FalloAlmacenError) as ctx:
            AlmacenLocal(os.path.join(self.base, "no-existe"))
        self.assertNotIn(self.base, str(ctx.exception))
        archivo = os.path.join(self.base, "archivo")
        open(archivo, "wb").close()
        with self.assertRaises(FalloAlmacenError):
            AlmacenLocal(archivo)

    def test_closed_store_refuses_work(self) -> None:
        local = AlmacenLocal(self.raiz)
        local.close()
        local.close()
        with self.assertRaises(FalloAlmacenError):
            local.tamano_de("temporal/v1")

    def test_objects_are_files_under_the_injected_root(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"abc"], 10)
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        with open(self.ruta("final", "v1", "n1"), "rb") as f:
            self.assertEqual(f.read(), b"abc")
        self.assertEqual(sorted(os.listdir(self.raiz)), ["final", "temporal"])

    def test_symlinked_namespace_directory_is_refused(self) -> None:
        os.symlink(self.fuera, self.ruta("temporal"))
        with self.assertRaises(FalloAlmacenError):
            self.a.guardar_temporal("temporal/secreto", [b"x"], 10)
        with self.assertRaises(FalloAlmacenError):
            self.a.leer("temporal/secreto", 100)
        with self.assertRaises(FalloAlmacenError):
            self.a.tamano_de("temporal/secreto")
        with self.assertRaises(FalloAlmacenError):
            self.a.borrar("temporal/secreto")
        with self.assertRaises(FalloAlmacenError):
            list(self.a.listar("temporal/"))
        self.assertEqual(os.listdir(self.fuera), ["secreto"])
        with open(self.secreto, "rb") as f:
            self.assertEqual(f.read(), b"no debe leerse")

    def test_symlinked_object_is_refused(self) -> None:
        os.mkdir(self.ruta("temporal"))
        os.symlink(self.secreto, self.ruta("temporal", "v1"))
        with self.assertRaises(FalloAlmacenError):
            self.a.leer("temporal/v1", 100)
        with self.assertRaises(FalloAlmacenError):
            self.a.tamano_de("temporal/v1")
        with self.assertRaises(FalloAlmacenError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        self.assertEqual(list(self.a.listar("temporal/")), [])
        # Replacing or deleting acts on the link itself, never on its target.
        self.a.guardar_temporal("temporal/v1", [b"propio"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"propio")
        os.unlink(self.ruta("temporal", "v1"))
        os.symlink(self.secreto, self.ruta("temporal", "v1"))
        self.assertTrue(self.a.borrar("temporal/v1"))
        with open(self.secreto, "rb") as f:
            self.assertEqual(f.read(), b"no debe leerse")

    def test_symlinked_final_directory_is_refused(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        os.mkdir(self.ruta("final"))
        os.symlink(self.fuera, self.ruta("final", "v1"))
        with self.assertRaises(FalloAlmacenError):
            self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.assertEqual(os.listdir(self.fuera), ["secreto"])
        self.assertEqual(list(self.a.listar("final/")), [])
        with self.assertRaises(FalloAlmacenError):
            list(self.a.listar("final/v1/"))

    def test_directory_planted_at_a_key(self) -> None:
        os.makedirs(self.ruta("temporal", "v1"))
        with self.assertRaises(FalloAlmacenError):
            self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        with self.assertRaises(FalloAlmacenError):
            self.a.leer("temporal/v1", 10)
        with self.assertRaises(FalloAlmacenError):
            self.a.tamano_de("temporal/v1")
        with self.assertRaises(FalloAlmacenError):
            self.a.borrar("temporal/v1")
        self.assertEqual(self.parciales(), [])

    def test_foreign_entries_are_not_listed(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        for nombre in (".parcial-abc", "LEEME", "con espacio", "a.b"):
            with open(self.ruta("temporal", nombre), "wb") as f:
                f.write(b"ajeno")
        self.assertEqual([m.clave for m in self.a.listar("temporal/")], ["temporal/v1"])

    def en_subproceso(self, acciones: str) -> dict[str, str]:
        """Run `acciones` against this root in a child with a deadline.

        A regression that blocks (S1) then fails this test instead of
        hanging the suite. `acciones` is a dict literal of name -> lambda.
        """
        codigo = (
            "import json, sys\n"
            "from server.almacen import AlmacenLocal, AlmacenError\n"
            "a = AlmacenLocal(sys.argv[1])\n"
            f"acciones = {acciones}\n"
            "salida = {}\n"
            "for nombre, accion in acciones.items():\n"
            "    try:\n"
            "        accion()\n"
            "        salida[nombre] = 'ok'\n"
            "    except AlmacenError as exc:\n"
            "        salida[nombre] = type(exc).__name__\n"
            "print(json.dumps(salida))\n"
        )
        try:
            hijo = subprocess.run([sys.executable, "-c", codigo, self.raiz], cwd=RAIZ_REPO,
                                  capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            self.fail("a storage call blocked on a non-regular entry; child terminated")
        self.assertEqual(hijo.returncode, 0, hijo.stderr)
        resultado: dict[str, str] = json.loads(hijo.stdout)
        return resultado

    def test_fifo_at_a_key_fails_promptly(self) -> None:
        # S1 review (S1): opening a FIFO must not wait for a writer.
        os.makedirs(self.ruta("temporal"))
        os.makedirs(self.ruta("final", "v1"))
        os.mkfifo(self.ruta("temporal", "fifo"))
        os.mkfifo(self.ruta("final", "v1", "fifo"))
        resultado = self.en_subproceso(
            "{'leer': lambda: a.leer('temporal/fifo', 1024),"
            " 'copiar': lambda: a.copiar('temporal/fifo', 'final/v1/n1', 1024),"
            " 'leer_final': lambda: a.leer('final/v1/fifo', 1024),"
            " 'tamano_de': lambda: a.tamano_de('temporal/fifo')}")
        self.assertEqual(resultado, dict.fromkeys(
            ("leer", "copiar", "leer_final", "tamano_de"), "FalloAlmacenError"))
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.ruta("temporal", "fifo")).st_mode))
        self.assertFalse(os.path.lexists(self.ruta("final", "v1", "n1")))
        self.assertEqual(self.parciales(), [])
        self.assertEqual(list(self.a.listar("temporal/")), [])

    def test_fifo_where_a_directory_belongs_fails_promptly(self) -> None:
        os.mkfifo(self.ruta("temporal"))
        os.makedirs(self.ruta("final"))
        os.mkfifo(self.ruta("final", "v1"))
        resultado = self.en_subproceso(
            "{'leer': lambda: a.leer('temporal/x', 1024),"
            " 'guardar': lambda: a.guardar_temporal('temporal/x', [b'x'], 10),"
            " 'tamano_de': lambda: a.tamano_de('final/v1/n1'),"
            " 'listar': lambda: list(a.listar('final/v1/'))}")
        self.assertEqual(resultado, dict.fromkeys(
            ("leer", "guardar", "tamano_de", "listar"), "FalloAlmacenError"))

    def test_regular_objects_are_read_in_blocking_mode(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"z" * 1000], 1000)
        with self.a.leer("temporal/v1", 1000) as lectura:
            self.assertTrue(os.get_blocking(lectura._fd))
            self.assertEqual(sum(len(b) for b in lectura), 1000)

    def test_failures_leave_no_partial_files(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"base"], 10)
        with self.assertRaises(ValueError):
            self.a.guardar_temporal("temporal/v1", [memoryview(bytearray(2 * MAX_BLOQUE))], 10)

        def roto() -> Iterator[bytes]:
            yield b"ab"
            raise RuntimeError("corte")

        with self.assertRaises(RuntimeError):
            self.a.guardar_temporal("temporal/v1", roto(), 10)
        with self.assertRaises(LimiteExcedidoError):
            self.a.guardar_temporal("temporal/v1", [b"x" * 11], 10)
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        with self.assertRaises(ColisionError):
            self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.assertEqual(self.parciales(), [])
        self.assertEqual(contenido(self.a, "temporal/v1"), b"base")

    def test_collision_found_only_at_link_time_cleans_up(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"segundo"], 100)
        enlace_real = os.link

        def otro_gana_primero(*args: object, **kwargs: object) -> None:
            with open(self.ruta("final", "v1", "n1"), "xb") as f:
                f.write(b"primero")
            enlace_real(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch("server.almacen.os.link", side_effect=otro_gana_primero), \
                self.assertRaises(ColisionError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"primero")
        self.assertEqual(self.parciales(), [])

    def test_write_fault_keeps_previous_object(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"previo"], 100)
        with mock.patch("server.almacen.os.fsync", side_effect=OSError(5, "E/S")), \
                self.assertRaises(FalloAlmacenError) as ctx:
            self.a.guardar_temporal("temporal/v1", [b"nuevo"], 100)
        self.assertNotIn(self.raiz, str(ctx.exception))
        self.assertEqual(contenido(self.a, "temporal/v1"), b"previo")
        self.assertEqual(self.parciales(), [])

    def test_copy_fault_leaves_no_destination(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"z" * 200_000], MB)
        lectura_real = os.read
        llamadas = {"n": 0}

        def falla_a_la_segunda(fd: int, n: int) -> bytes:
            llamadas["n"] += 1
            if llamadas["n"] == 2:
                raise OSError(5, "E/S")
            return lectura_real(fd, n)

        with mock.patch("server.almacen.os.read", side_effect=falla_a_la_segunda), \
                self.assertRaises(FalloAlmacenError):
            self.a.copiar("temporal/v1", "final/v1/n1", MB)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        self.assertEqual(self.parciales(), [])
        self.assertEqual(self.a.copiar("temporal/v1", "final/v1/n1", MB), 200_000)

    def test_read_fault_closes_the_reader(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"z" * 10_000], 10_000)
        lectura = self.a.leer("temporal/v1", 10_000, bloque=1000)
        next(lectura)
        with mock.patch("server.almacen.os.read", side_effect=OSError(5, "E/S")), \
                self.assertRaises(FalloAlmacenError):
            next(lectura)
        self.assertIsNone(lectura._fd)

    def test_in_place_change_during_read_is_not_success(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"z" * 10_000], 10_000)
        lectura = self.a.leer("temporal/v1", 10_000, bloque=1000)
        next(lectura)
        os.truncate(self.ruta("temporal", "v1"), 5000)     # not something this module does
        with self.assertRaises(FalloAlmacenError):
            list(lectura)

    def test_large_objects_stream_with_bounded_memory(self) -> None:
        tamano = 48 * MB
        bloque = b"\xa5" * MB

        def flujo() -> Iterator[bytes]:
            for _ in range(tamano // MB):
                yield bloque

        tracemalloc.start()
        try:
            self.a.guardar_temporal("temporal/grande", flujo(), tamano)
            self.a.copiar("temporal/grande", "final/grande/n1", tamano)
            total = 0
            with self.a.leer("final/grande/n1", tamano) as lectura:
                for parte in lectura:
                    total += len(parte)
            _, pico = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(total, tamano)
        self.assertLess(pico, 8 * MB, f"peak {pico} bytes")


class AlmacenEnMemoriaFallas(unittest.TestCase):
    """Deterministic fault injection, which exists only on the fake."""

    def setUp(self) -> None:
        self.a = AlmacenEnMemoria()
        self.a.guardar_temporal("temporal/v1", [b"previo"], 100)

    def test_write_fault_after_some_chunks_keeps_previous(self) -> None:
        self.a.inyectar_falla("guardar_temporal", tras_bloques=2)
        consumidos = []

        def flujo() -> Iterator[bytes]:
            for b in (b"a", b"b", b"c", b"d"):
                consumidos.append(b)
                yield b

        with self.assertRaises(FalloAlmacenError):
            self.a.guardar_temporal("temporal/v1", flujo(), 100)
        self.assertEqual(consumidos, [b"a", b"b", b"c"])
        self.assertEqual(contenido(self.a, "temporal/v1"), b"previo")
        self.a.guardar_temporal("temporal/v1", [b"luego"], 100)       # one-shot
        self.assertEqual(contenido(self.a, "temporal/v1"), b"luego")

    def test_write_fault_with_fewer_chunks_still_fails(self) -> None:
        self.a.inyectar_falla("guardar_temporal", tras_bloques=5)
        with self.assertRaises(FalloAlmacenError):
            self.a.guardar_temporal("temporal/v1", [b"x"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"previo")

    def test_copy_fault_writes_nothing(self) -> None:
        self.a.inyectar_falla("copiar")
        with self.assertRaises(FalloAlmacenError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        self.assertEqual(self.a.copiar("temporal/v1", "final/v1/n1", 100), 6)

    def test_read_fault_after_some_chunks(self) -> None:
        self.a.inyectar_falla("leer", tras_bloques=1)
        lectura = self.a.leer("temporal/v1", 100, bloque=2)
        self.assertEqual(next(lectura), b"pr")
        with self.assertRaises(FalloAlmacenError):
            next(lectura)
        self.assertTrue(lectura.cerrada)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"previo")

    def test_lost_object(self) -> None:
        self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.a.perder("final/v1/n1")
        with self.assertRaises(ObjetoAusenteError):
            self.a.leer("final/v1/n1", 100)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        with self.assertRaises(ClaveInvalidaError):
            self.a.perder("../x")

    def test_unknown_fault_and_no_production_bypass(self) -> None:
        with self.assertRaises(ValueError):
            self.a.inyectar_falla("borrar")
        for nombre in ("inyectar_falla", "perder"):
            self.assertFalse(hasattr(AlmacenLocal, nombre))


if __name__ == "__main__":
    unittest.main()
