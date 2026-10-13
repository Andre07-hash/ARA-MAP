"""Supabase Storage adapter: the shared store contract plus provider faults.

No network and no account: the provider is a deterministic in-memory fake.
It runs behind two doors:

- always, behind a minimal stand-in for the SDK surface the adapter uses, so
  the suite needs nothing installed (Python 3.9, CI);
- when `storage3` is importable, behind the REAL SDK over an httpx mock
  transport, which proves the adapter calls methods the SDK actually has and
  that the SDK's requests and error parsing give the mapped results.

Neither proves what Supabase itself does: duplicate-upload answers, atomic
replacement, read-after-overwrite freshness, 20/25 MiB transfers and quota
errors remain for the hosted gate.
"""

from __future__ import annotations

import email
import importlib.util
import json
import logging
import subprocess
import sys
import threading
import unittest
from typing import Any

from server import almacen, almacen_supabase
from server.almacen import (
    AlmacenNoConfiguradoError,
    ColisionError,
    FalloAlmacenError,
    LimiteExcedidoError,
    ObjetoAusenteError,
    ResultadoInciertoError,
)
from server.almacen_supabase import (
    ENV_BUCKET,
    ENV_KEY,
    ENV_URL,
    AlmacenSupabase,
    fabrica_desde_entorno,
)
from tests import test_almacen
from tests.test_almacen import RAIZ_REPO, contenido

BUCKET = "archivos-prueba"
URL = "https://proyecto-ficticio.supabase.co"
CLAVE = "clave-ficticia-de-servicio"     # synthetic; never a real credential
CABECERAS = {"apiKey": CLAVE, "Authorization": f"Bearer {CLAVE}"}
HAY_SDK = importlib.util.find_spec("storage3") is not None

Respuesta = tuple[int, Any]              # HTTP status, JSON-able body or bytes


class CorteError(Exception):
    """A transport failure: no answer arrived."""


class ProveedorFalso:
    """The provider's observable behaviour, as the adapter's tests assume it.

    Errors are answered the way Supabase Storage has answered them: HTTP 400
    with the real status inside the JSON body, so mapping by the HTTP status
    line alone would fail these tests.
    """

    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}
        self.candado = threading.Lock()
        self.fallas: dict[str, list[Any]] = {}
        self.llamadas: list[tuple[str, str]] = []
        self.vistas: list[dict[str, str]] = []      # headers of every request

    # -- fault injection

    def fallar(self, operacion: str, falla: Any) -> None:
        """Next `operacion`: answer `falla` (a Respuesta), or cut the line.

        "corte" drops the request; "corte_despues" applies it and then drops
        the answer, as a lost provider response would.
        """
        self.fallas.setdefault(operacion, []).append(falla)

    def _falla(self, operacion: str) -> Any:
        cola = self.fallas.get(operacion)
        return cola.pop(0) if cola else None

    @staticmethod
    def _error(status: int, codigo: str, mensaje: str) -> Respuesta:
        return 400, {"statusCode": str(status), "error": codigo, "message": mensaje}

    def _comprobar(self, bucket: str, cabeceras: Any) -> Respuesta | None:
        self.vistas.append({k.lower(): v for k, v in dict(cabeceras).items()})
        if dict(self.vistas[-1]).get("authorization") != f"Bearer {CLAVE}":
            return self._error(403, "Unauthorized", "Invalid JWT")
        if bucket != BUCKET:
            return self._error(404, "Bucket not found", "Bucket not found")
        return None

    # -- operations

    def subir(self, bucket: str, clave: str, datos: bytes, cabeceras: Any) -> Respuesta:
        self.llamadas.append(("subir", clave))
        falla = self._falla("subir")
        if falla == "corte":
            raise CorteError()
        if isinstance(falla, tuple):
            return falla
        negado = self._comprobar(bucket, cabeceras)
        if negado:
            return negado
        reemplazar = dict(self.vistas[-1]).get("x-upsert") == "true"
        with self.candado:
            if clave in self.objetos and not reemplazar:
                return self._error(409, "Duplicate", "The resource already exists")
            self.objetos[clave] = datos
        if falla == "corte_despues":
            raise CorteError()
        return 200, {"Key": f"{bucket}/{clave}", "Id": "id-ficticio"}

    def bajar(self, bucket: str, clave: str, cabeceras: Any) -> Respuesta:
        self.llamadas.append(("bajar", clave))
        falla = self._falla("bajar")
        if falla == "corte":
            raise CorteError()
        if isinstance(falla, tuple):
            return falla
        negado = self._comprobar(bucket, cabeceras)
        if negado:
            return negado
        with self.candado:
            if clave not in self.objetos:
                return self._error(404, "not_found", "Object not found")
            return 200, self.objetos[clave]

    def info(self, bucket: str, clave: str, cabeceras: Any) -> Respuesta:
        self.llamadas.append(("info", clave))
        falla = self._falla("info")
        if falla == "corte":
            raise CorteError()
        if isinstance(falla, tuple):
            return falla
        negado = self._comprobar(bucket, cabeceras)
        if negado:
            return negado
        with self.candado:
            if clave not in self.objetos:
                return self._error(404, "not_found", "Object not found")
            return 200, {"name": clave, "size": len(self.objetos[clave]),
                         "metadata": {"mimetype": "application/octet-stream"}}

    def quitar(self, bucket: str, claves: list[str], cabeceras: Any) -> Respuesta:
        self.llamadas.append(("quitar", ",".join(claves)))
        falla = self._falla("quitar")
        if falla == "corte":
            raise CorteError()
        if isinstance(falla, tuple):
            return falla
        negado = self._comprobar(bucket, cabeceras)
        if negado:
            return negado
        with self.candado:
            return 200, [{"name": c} for c in claves if self.objetos.pop(c, None) is not None]

    def listar(self, bucket: str, cuerpo: dict[str, Any], cabeceras: Any) -> Respuesta:
        carpeta = str(cuerpo.get("prefix", "")).strip("/")
        self.llamadas.append(("listar", f"{carpeta}@{cuerpo.get('offset')}"))
        falla = self._falla("listar")
        if falla == "corte":
            raise CorteError()
        if isinstance(falla, tuple):
            return falla
        negado = self._comprobar(bucket, cabeceras)
        if negado:
            return negado
        entradas: dict[str, dict[str, Any]] = {}
        with self.candado:
            for clave, datos in self.objetos.items():
                if not clave.startswith(carpeta + "/"):
                    continue
                nombre, _, resto = clave[len(carpeta) + 1:].partition("/")
                if resto:       # a folder, as the provider reports one
                    entradas[nombre] = {"name": nombre, "id": None, "metadata": None}
                else:
                    entradas[nombre] = {
                        "name": nombre, "id": "id-" + nombre,
                        "updated_at": "2026-10-12T18:00:00.000Z",
                        "metadata": {"size": len(datos), "mimetype": "application/octet-stream"}}
        orden = [entradas[n] for n in sorted(entradas)]
        desde, limite = int(cuerpo.get("offset", 0)), int(cuerpo.get("limit", 100))
        return 200, orden[desde:desde + limite]


# ---- door 1: a stand-in for the SDK surface (always available)

class ApiSimuladaError(Exception):
    """Same shape as storage3.exceptions.StorageApiError."""

    def __init__(self, message: str, code: str, status: Any) -> None:
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


class _RespuestaMinima:
    def __init__(self, status: int, cuerpo: Any) -> None:
        self.status_code = status
        self._datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
        self.headers = {"content-length": str(len(self._datos))}

    def iter_bytes(self, tamano: int) -> Any:
        for i in range(0, len(self._datos), tamano):
            yield self._datos[i:i + tamano]

    def __enter__(self) -> _RespuestaMinima:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _SesionMinima:
    def __init__(self, proveedor: ProveedorFalso) -> None:
        self._p = proveedor
        self.cerrada = False

    def stream(self, metodo: str, url: str, headers: dict[str, str]) -> _RespuestaMinima:
        assert metodo == "GET"
        bucket, _, clave = url.split("/storage/v1/object/", 1)[1].partition("/")
        return _RespuestaMinima(*self._p.bajar(bucket, clave, headers))

    def close(self) -> None:
        self.cerrada = True


class _BucketMinimo:
    def __init__(self, proveedor: ProveedorFalso, bucket: str) -> None:
        self._p, self._b = proveedor, bucket

    @staticmethod
    def _json(respuesta: Respuesta) -> Any:
        status, cuerpo = respuesta
        if status != 200:     # what the SDK's _request does with an error body
            raise ApiSimuladaError(cuerpo["message"], cuerpo["error"], cuerpo["statusCode"])
        return cuerpo

    def upload(self, path: str, file: Any, file_options: dict[str, str]) -> Any:
        cabeceras = {**CABECERAS, "x-upsert": file_options["upsert"]}
        return self._json(self._p.subir(self._b, path, file.read(), cabeceras))

    def info(self, path: str) -> Any:
        return self._json(self._p.info(self._b, path, CABECERAS))

    def remove(self, paths: list[str]) -> Any:
        return self._json(self._p.quitar(self._b, paths, CABECERAS))

    def list(self, path: str, options: dict[str, Any]) -> Any:
        return self._json(self._p.listar(self._b, {**options, "prefix": path}, CABECERAS))


class ClienteMinimo:
    def __init__(self, proveedor: ProveedorFalso) -> None:
        self._p = proveedor
        self.session = _SesionMinima(proveedor)

    def from_(self, bucket: str) -> _BucketMinimo:
        return _BucketMinimo(self._p, bucket)


def almacen_minimo(proveedor: ProveedorFalso, bucket: str = BUCKET) -> AlmacenSupabase:
    return AlmacenSupabase(ClienteMinimo(proveedor), bucket, URL + "/storage/v1", CABECERAS)


# ---- door 2: the real SDK over an httpx mock transport

def transporte_http(proveedor: ProveedorFalso) -> Any:
    import httpx

    def atender(peticion: Any) -> Any:
        ruta = peticion.url.path
        assert ruta.startswith("/storage/v1/object/"), ruta
        partes = ruta[len("/storage/v1/object/"):].split("/")
        cabeceras = peticion.headers
        try:
            if peticion.method == "POST" and partes[0] == "list":
                status, cuerpo = proveedor.listar(partes[1], json.loads(peticion.read()), cabeceras)
            elif peticion.method == "GET" and partes[0] == "info":
                status, cuerpo = proveedor.info(partes[1], "/".join(partes[2:]), cabeceras)
            elif peticion.method == "DELETE":
                claves = json.loads(peticion.read())["prefixes"]
                status, cuerpo = proveedor.quitar(partes[0], claves, cabeceras)
            elif peticion.method == "POST":
                mensaje = email.message_from_bytes(
                    b"Content-Type: " + cabeceras["content-type"].encode() + b"\r\n\r\n"
                    + peticion.read())
                archivo = next(p for p in mensaje.walk() if p.get_param(
                    "name", header="content-disposition") == "file")
                datos = archivo.get_payload(decode=True) or b""
                status, cuerpo = proveedor.subir(partes[0], "/".join(partes[1:]), datos, cabeceras)
            elif peticion.method == "GET":
                status, cuerpo = proveedor.bajar(partes[0], "/".join(partes[1:]), cabeceras)
            else:
                raise AssertionError(f"unexpected request {peticion.method} {ruta}")
        except CorteError:
            raise httpx.ConnectError("corte simulado", request=peticion) from None
        if isinstance(cuerpo, bytes):
            return httpx.Response(status, content=cuerpo)
        return httpx.Response(status, json=cuerpo)

    return httpx.MockTransport(atender)


def almacen_sdk(proveedor: ProveedorFalso, bucket: str = BUCKET) -> AlmacenSupabase:
    return almacen_supabase._construir(URL + "/storage/v1", CLAVE, bucket,
                                       transporte=transporte_http(proveedor))


# ---------------------------------------------------------------- the contract

class _Puerta:
    """Builds the store under test; subclasses choose the door."""

    def construir(self, proveedor: ProveedorFalso, bucket: str = BUCKET) -> AlmacenSupabase:
        raise NotImplementedError

    def crear(self) -> almacen.Almacen:
        self.p = ProveedorFalso()
        tienda = self.construir(self.p)
        self.addCleanup(tienda.close)          # type: ignore[attr-defined]
        return tienda

    def abierta(self, lectura: almacen.Lectura) -> bool:
        return not lectura.cerrada             # type: ignore[attr-defined]


class _Minima(_Puerta):
    def construir(self, proveedor: ProveedorFalso, bucket: str = BUCKET) -> AlmacenSupabase:
        return almacen_minimo(proveedor, bucket)


class _ConSdk(_Puerta):
    def construir(self, proveedor: ProveedorFalso, bucket: str = BUCKET) -> AlmacenSupabase:
        return almacen_sdk(proveedor, bucket)


class ContratoSupabase(_Minima, test_almacen.Contrato, unittest.TestCase):
    pass


@unittest.skipUnless(HAY_SDK, "storage3 is not installed")
class ContratoSupabaseConSdk(_ConSdk, test_almacen.Contrato, unittest.TestCase):
    pass


# ------------------------------------------------------------ provider behaviour

class Proveedor:
    """Faults and provider-specific behaviour, through either door."""

    a: AlmacenSupabase
    p: ProveedorFalso

    def setUp(self) -> None:
        self.a = self.crear()                  # type: ignore[attr-defined]
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)   # type: ignore[attr-defined]

    def test_final_upload_never_upserts_and_staging_always_does(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        self.assertEqual(self.p.vistas[-1]["x-upsert"], "true")
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.assertEqual(self.p.vistas[-1]["x-upsert"], "false")
        # No existence probe precedes the create-only upload.
        self.assertEqual([op for op, _ in self.p.llamadas], ["subir", "bajar", "subir"])

    def test_collision_is_recognized_from_the_error_body_only(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        # A plain 400 that is not a duplicate must not become a collision.
        self.p.fallar("subir", (400, {"statusCode": "400", "error": "InvalidRequest",
                                      "message": "The resource already exists"}))
        with self.assertRaises(FalloAlmacenError) as ctx:
            self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.assertNotIsInstance(ctx.exception, (ColisionError, ResultadoInciertoError))
        self.assertFalse(ctx.exception.reintentar)
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))
        # An HTTP 409 with the newer body is one too.
        self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.p.fallar("subir", (409, {"statusCode": "409", "error": "Duplicate",
                                      "message": "The resource already exists"}))
        with self.assertRaises(ColisionError):
            self.a.copiar("temporal/v1", "final/v1/n2", 10)

    def test_lost_answer_of_a_final_write_is_uncertain_not_failed(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"bytes finales"], 100)
        self.p.fallar("subir", "corte_despues")
        with self.assertRaises(ResultadoInciertoError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"bytes finales")   # it WAS stored
        # Retrying the same nonce cannot overwrite: it reports the collision.
        with self.assertRaises(ColisionError):
            self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.p.fallar("subir", "corte")
        with self.assertRaises(ResultadoInciertoError):     # indistinguishable from outside
            self.a.copiar("temporal/v1", "final/v1/n2", 100)
        self.assertIsNone(self.a.tamano_de("final/v1/n2"))

    def test_gateway_error_on_a_write_is_uncertain(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        self.p.fallar("subir", (504, {"statusCode": "504", "error": "GatewayTimeout",
                                      "message": "upstream timed out"}))
        with self.assertRaises(ResultadoInciertoError) as ctx:
            self.a.copiar("temporal/v1", "final/v1/n1", 10)
        self.assertTrue(ctx.exception.reintentar)
        self.assertEqual(ctx.exception.proveedor, "504/GatewayTimeout")

    def test_failed_staging_upload_keeps_the_previous_object(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"anterior"], 100)
        self.p.fallar("subir", "corte")
        with self.assertRaises(ResultadoInciertoError):
            self.a.guardar_temporal("temporal/v1", [b"nuevo"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"anterior")
        self.p.fallar("subir", (429, {"statusCode": "429", "error": "TooManyRequests",
                                      "message": "slow down"}))
        with self.assertRaises(FalloAlmacenError) as ctx:
            self.a.guardar_temporal("temporal/v1", [b"nuevo"], 100)
        self.assertNotIsInstance(ctx.exception, ResultadoInciertoError)   # refused, not stored
        self.assertTrue(ctx.exception.reintentar)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"anterior")

    def test_input_failure_sends_nothing_to_the_provider(self) -> None:
        with self.assertRaises(LimiteExcedidoError):
            self.a.guardar_temporal("temporal/v1", [b"x" * 6, b"x" * 6], 10)
        self.assertEqual(self.p.llamadas, [])

    def test_overwrite_then_immediate_read_and_copy_see_the_new_bytes(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"primero"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"primero")
        self.a.guardar_temporal("temporal/v1", [b"segundo"], 100)
        self.assertEqual(contenido(self.a, "temporal/v1"), b"segundo")
        self.a.copiar("temporal/v1", "final/v1/n1", 100)
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"segundo")
        lecturas = [v for (op, _), v in zip(self.p.llamadas, self.p.vistas) if op == "bajar"]
        self.assertTrue(lecturas)
        for vista in lecturas:      # authenticated and uncached, never a public URL
            self.assertEqual(vista["authorization"], f"Bearer {CLAVE}")
            self.assertEqual(vista["cache-control"], "no-cache")

    def test_access_denied_is_a_nonretryable_storage_failure(self) -> None:
        negado = (400, {"statusCode": "403", "error": "Unauthorized", "message": "Invalid JWT"})
        for operacion, accion in (
            ("subir", lambda: self.a.guardar_temporal("temporal/v1", [b"x"], 10)),
            ("bajar", lambda: self.a.leer("temporal/v1", 10)),
            ("info", lambda: self.a.tamano_de("temporal/v1")),
            ("quitar", lambda: self.a.borrar("temporal/v1")),
            ("listar", lambda: list(self.a.listar("temporal/"))),
        ):
            with self.subTest(operacion):
                self.p.fallar(operacion, negado)
                with self.assertRaises(FalloAlmacenError) as ctx:
                    accion()
                self.assertNotIsInstance(ctx.exception, ResultadoInciertoError)
                self.assertFalse(ctx.exception.reintentar)
                self.assertEqual(ctx.exception.proveedor, "403/Unauthorized")

    def test_outages_are_retryable_and_never_look_like_absence(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"x"], 10)
        caido = (503, {"statusCode": "503", "error": "ServiceUnavailable", "message": "paused"})
        for falla in (caido, "corte", (500, b"<html>no json</html>")):
            for operacion, accion in (
                ("bajar", lambda: self.a.leer("temporal/v1", 10)),
                ("bajar", lambda: self.a.copiar("temporal/v1", "final/v1/n1", 10)),
                ("info", lambda: self.a.tamano_de("temporal/v1")),
                ("quitar", lambda: self.a.borrar("temporal/v1")),
                ("listar", lambda: list(self.a.listar("temporal/"))),
            ):
                with self.subTest(operacion=operacion, falla=str(falla)[:20]):
                    self.p.fallar(operacion, falla)
                    with self.assertRaises(FalloAlmacenError) as ctx:
                        accion()
                    self.assertTrue(ctx.exception.reintentar)
        self.assertEqual(self.a.tamano_de("temporal/v1"), 1)        # nothing was lost
        self.assertIsNone(self.a.tamano_de("final/v1/n1"))

    def test_a_missing_bucket_is_a_failure_not_an_absent_object(self) -> None:
        otra = self.construir(self.p, "bucket-inexistente")     # type: ignore[attr-defined]
        self.addCleanup(otra.close)                             # type: ignore[attr-defined]
        with self.assertRaises(FalloAlmacenError) as ctx:
            otra.tamano_de("final/v1/n1")
        self.assertFalse(ctx.exception.reintentar)
        with self.assertRaises(FalloAlmacenError):
            otra.leer("final/v1/n1", 10)
        with self.assertRaises(FalloAlmacenError):
            otra.guardar_temporal("temporal/v1", [b"x"], 10)

    def test_quota_style_rejection_keeps_existing_objects(self) -> None:
        self.a.guardar_temporal("temporal/v1", [b"aceptado"], 100)
        self.a.copiar("temporal/v1", "final/v1/n1", 100)
        lleno = (400, {"statusCode": "413", "error": "Payload too large",
                       "message": "The object exceeded the maximum allowed size"})
        self.p.fallar("subir", lleno)
        with self.assertRaises(FalloAlmacenError) as ctx:
            self.a.guardar_temporal("temporal/v1", [b"otro"], 100)
        self.assertFalse(ctx.exception.reintentar)
        self.assertEqual(ctx.exception.proveedor, "413/Payload too large")
        self.assertEqual(contenido(self.a, "temporal/v1"), b"aceptado")
        self.assertEqual(contenido(self.a, "final/v1/n1"), b"aceptado")

    def test_read_is_bounded_even_when_the_provider_misreports(self) -> None:
        self.p.objetos["temporal/v1"] = b"z" * 5000
        with self.assertRaises(LimiteExcedidoError):
            self.a.leer("temporal/v1", 4999)
        with self.assertRaises(LimiteExcedidoError):
            self.a.copiar("temporal/v1", "final/v1/n1", 4999)
        self.assertNotIn("final/v1/n1", self.p.objetos)

    def test_listing_is_lazy_and_paginated(self) -> None:
        for i in range(250):
            self.p.objetos[f"temporal/v{i:03d}"] = b"x" * i
        self.p.objetos["temporal/No-Valido"] = b"ajeno"      # not written by the app
        self.p.llamadas.clear()
        iterador = self.a.listar("temporal/")
        self.assertEqual(self.p.llamadas, [])                # nothing until consumed
        primero = next(iterador)
        self.assertEqual(self.p.llamadas, [("listar", "temporal@0")])
        resto = list(iterador)
        self.assertEqual(len(resto) + 1, 250)
        self.assertEqual(primero.tamano + sum(m.tamano for m in resto), sum(range(250)))
        self.assertEqual([c for _, c in self.p.llamadas],
                         ["temporal@0", "temporal@100", "temporal@200"])
        self.p.objetos["final/v1/n1"] = b"a"
        self.p.objetos["final/v2/n1"] = b"bb"
        self.assertEqual(sorted((m.clave, m.tamano) for m in self.a.listar("final/")),
                         [("final/v1/n1", 1), ("final/v2/n1", 2)])

    def test_delete_names_exactly_one_key(self) -> None:
        self.p.objetos.update({"final/v1/n1": b"a", "final/v1/n10": b"b", "final/v1/n": b"c"})
        self.assertTrue(self.a.borrar("final/v1/n1"))
        self.assertEqual(sorted(self.p.objetos), ["final/v1/n", "final/v1/n10"])
        self.assertEqual(self.p.llamadas[-1], ("quitar", "final/v1/n1"))

    def test_errors_and_logs_carry_no_key_url_or_credential(self) -> None:
        logging.disable(logging.NOTSET)
        self.p.fallar("bajar", (400, {"statusCode": "500", "error": "Internal",
                                      "message": f"token {CLAVE} at {URL}/temporal/secreto1"}))
        with self.assertLogs("server.almacen_supabase", "WARNING") as registro, \
                self.assertRaises(FalloAlmacenError) as ctx:
            self.a.leer("temporal/secreto1", 10)
        texto = " ".join(registro.output) + str(ctx.exception) + str(ctx.exception.proveedor)
        for secreto in (CLAVE, "secreto1", "supabase.co", "Bearer"):
            self.assertNotIn(secreto, texto)


class ProveedorSupabase(_Minima, Proveedor, unittest.TestCase):
    pass


@unittest.skipUnless(HAY_SDK, "storage3 is not installed")
class ProveedorSupabaseConSdk(_ConSdk, Proveedor, unittest.TestCase):
    def test_the_session_does_not_follow_redirects(self) -> None:
        self.assertFalse(self.a._cliente.session.follow_redirects)

    def test_closing_the_store_closes_the_session(self) -> None:
        tienda = almacen_sdk(ProveedorFalso())
        tienda.close()
        self.assertTrue(tienda._cliente.session.is_closed)


# -------------------------------------------------------------------- factory

class Fabrica(unittest.TestCase):
    COMPLETO = {ENV_URL: URL, ENV_KEY: CLAVE, ENV_BUCKET: BUCKET}

    def test_unconfigured_gives_none(self) -> None:
        self.assertIsNone(fabrica_desde_entorno({}))
        self.assertIsNone(fabrica_desde_entorno({ENV_URL: " ", ENV_KEY: "", ENV_BUCKET: ""}))

    def test_incomplete_or_malformed_gives_none_and_names_only_variables(self) -> None:
        casos: list[dict[str, str]] = [
            {**self.COMPLETO, ENV_KEY: ""},
            {**self.COMPLETO, ENV_BUCKET: ""},
            {ENV_KEY: CLAVE},
            {**self.COMPLETO, ENV_URL: "http://proyecto-ficticio.supabase.co"},   # clear text
            {**self.COMPLETO, ENV_URL: "https://usuario:secreto@host.example"},
            {**self.COMPLETO, ENV_URL: "https://host.example/otra/ruta"},
            {**self.COMPLETO, ENV_URL: "https://host.example/?x=1"},
            {**self.COMPLETO, ENV_URL: "host.example"},
            {**self.COMPLETO, ENV_URL: "https://host.example:puerto"},
            {**self.COMPLETO, ENV_BUCKET: "Con Espacios"},
            {**self.COMPLETO, ENV_BUCKET: "a/b"},
            {**self.COMPLETO, ENV_KEY: "con espacio"},
        ]
        for entorno in casos:
            with self.subTest(entorno=sorted(entorno)), \
                    self.assertLogs("server.almacen_supabase", "WARNING") as registro:
                self.assertIsNone(fabrica_desde_entorno(entorno))
            texto = " ".join(registro.output)
            self.assertIn("ARA_MAP_ARCHIVOS_SUPABASE_", texto)
            for valor in (CLAVE, "secreto", "host.example"):
                self.assertNotIn(valor, texto)

    def test_accepted_url_forms(self) -> None:
        for url in (URL, URL + "/", URL + "/storage/v1", URL + "/storage/v1/",
                    "http://127.0.0.1:54321", "http://localhost:54321/storage/v1"):
            with self.subTest(url=url):
                self.assertIsNotNone(fabrica_desde_entorno({**self.COMPLETO, ENV_URL: url}))

    def test_building_the_factory_imports_no_sdk_and_opens_nothing(self) -> None:
        # A fresh interpreter where importing the SDK or opening a socket fails.
        programa = (
            "import socket, sys\n"
            "class Prohibido:\n"
            "    def find_spec(self, nombre, *a, **k):\n"
            "        if nombre.split('.')[0] in ('storage3', 'httpx', 'supabase'):\n"
            "            raise AssertionError('imported ' + nombre)\n"
            "sys.meta_path.insert(0, Prohibido())\n"
            "def sin_red(*a, **k): raise AssertionError('network')\n"
            "socket.socket.connect = sin_red\n"
            "socket.getaddrinfo = sin_red\n"
            "from server.almacen_supabase import fabrica_desde_entorno\n"
            f"f = fabrica_desde_entorno({self.COMPLETO!r})\n"
            "assert callable(f)\n"
            "print('ok')\n")
        hecho = subprocess.run([sys.executable, "-c", programa], cwd=RAIZ_REPO,
                               capture_output=True, text=True, timeout=60)
        self.assertEqual((hecho.returncode, hecho.stdout.strip()), (0, "ok"), hecho.stderr)

    def test_missing_sdk_is_reported_as_not_configured_on_first_use(self) -> None:
        programa = (
            "import sys\n"
            "class SinSdk:\n"
            "    def find_spec(self, nombre, *a, **k):\n"
            "        if nombre.split('.')[0] == 'storage3':\n"
            "            raise ImportError('no sdk')\n"
            "sys.meta_path.insert(0, SinSdk())\n"
            "from server.almacen import AlmacenNoConfiguradoError\n"
            "from server.almacen_supabase import fabrica_desde_entorno\n"
            f"f = fabrica_desde_entorno({self.COMPLETO!r})\n"
            "try:\n"
            "    f()\n"
            "except AlmacenNoConfiguradoError as exc:\n"
            "    print(exc.codigo)\n")
        hecho = subprocess.run([sys.executable, "-c", programa], cwd=RAIZ_REPO,
                               capture_output=True, text=True, timeout=60)
        self.assertEqual((hecho.returncode, hecho.stdout.strip()),
                         (0, "almacen_no_configurado"), hecho.stderr)

    @unittest.skipUnless(HAY_SDK, "storage3 is not installed")
    def test_the_factory_builds_a_store_without_any_request(self) -> None:
        fabrica = fabrica_desde_entorno(self.COMPLETO)
        assert fabrica is not None
        tienda = fabrica()
        self.addCleanup(tienda.close)       # type: ignore[attr-defined]
        self.assertIsInstance(tienda, AlmacenSupabase)
        self.assertIsNot(fabrica(), tienda)

    def test_error_types_are_importable_without_the_adapter(self) -> None:
        self.assertTrue(issubclass(ResultadoInciertoError, FalloAlmacenError))
        self.assertFalse(issubclass(AlmacenNoConfiguradoError, FalloAlmacenError))
        self.assertFalse(issubclass(ObjetoAusenteError, FalloAlmacenError))


if __name__ == "__main__":
    unittest.main()
