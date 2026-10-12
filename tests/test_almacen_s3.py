"""The private S3 store (server/almacen_s3.py) and its credential handoff.

Two groups:

- Without any SDK (always run): configuration is pure and validated, the
  factory never imports the SDK or touches the network, a missing SDK is
  "not configured", and the OIDC ContextVar handoff sets and resets.
- With boto3 and moto installed (an isolated development environment; skipped
  otherwise): the Almacen contract against a local moto S3/STS server, pinned
  composition, create-only finals, a write that lands but loses its reply,
  the error mapping, STS web identity with the request's token, refresh under
  concurrency and near expiry, and one forced refresh after an
  expired-credentials answer.

moto models create-only writes, versioning and STS web identity; it does NOT
enforce or store SHA-256 checksums and is not AWS. Real-provider and Vercel
OIDC behavior remain hosted acceptance gates.
"""

from __future__ import annotations

import builtins
import importlib.util
import logging
import os
import socket
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from server import almacen_s3
from server.almacen import (
    AlmacenNoConfiguradoError,
    ColisionError,
    FalloAlmacenError,
    LimiteExcedidoError,
    ObjetoAusenteError,
    ResultadoInciertoError,
)

TIENE_SDK = all(importlib.util.find_spec(m) is not None for m in ("boto3", "moto"))
BUCKET = "ara-archivos-prueba"
SIN_VERSIONES = "ara-archivos-sin-versiones"
REGION = "us-east-1"
ROL = "arn:aws:iam::123456789012:role/ara-map-preview"
TOKEN = "token-oidc-ficticio-uno"
SECRETO = "valor-secreto-ficticio"


def entorno(**extra: str) -> dict[str, str]:
    base = {almacen_s3.VARIABLE_BUCKET: BUCKET, almacen_s3.VARIABLE_REGION: REGION,
            almacen_s3.VARIABLE_ROL: ROL}
    base.update(extra)
    return base


class SinSDK(unittest.TestCase):
    """Pure configuration, lazy SDK, ContextVar handoff."""

    def test_nothing_configured_is_none_and_valid_settings_build_a_pure_factory(self):
        self.assertIsNone(almacen_s3.fabrica_desde_entorno({}))
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network")), \
                patch.dict("sys.modules", {"boto3": None}):
            fabrica = almacen_s3.fabrica_desde_entorno(entorno())
            self.assertTrue(callable(fabrica))
            # Without the SDK the store is "not configured", never an import error.
            with self.assertRaises(AlmacenNoConfiguradoError):
                fabrica()

    def test_invalid_settings_defer_a_safe_error_and_never_log_values(self):
        malos = {
            "bucket": {almacen_s3.VARIABLE_BUCKET: "Mayusculas_No"},
            "region": {almacen_s3.VARIABLE_REGION: "marte"},
            "role": {almacen_s3.VARIABLE_ROL: "arn:aws:iam::1:role/x"},
            "no-role": {almacen_s3.VARIABLE_ROL: ""},
            "remote-endpoint": {almacen_s3.VARIABLE_ENDPOINT: "https://s3.example.com"},
            "endpoint-on-vercel": {almacen_s3.VARIABLE_ENDPOINT: "http://127.0.0.1:9000",
                                   "VERCEL": "1"},
            "endpoint-with-path": {almacen_s3.VARIABLE_ENDPOINT: "http://localhost:9000/x"},
            "partial": {almacen_s3.VARIABLE_REGION: "", almacen_s3.VARIABLE_ROL: ""},
        }
        for nombre, cambio in malos.items():
            with self.subTest(caso=nombre), self.assertLogs("ara_map.archivos.s3", "ERROR") as log:
                fabrica = almacen_s3.fabrica_desde_entorno({**entorno(), **cambio})
                with self.assertRaises(AlmacenNoConfiguradoError):
                    fabrica()
                texto = " ".join(log.output)
                for valor in cambio.values():
                    if valor and valor != "1":
                        self.assertNotIn(valor, texto)
        # A loopback test endpoint without a role is accepted (isolated tests only).
        ok = almacen_s3.leer_configuracion({almacen_s3.VARIABLE_BUCKET: BUCKET,
                                            almacen_s3.VARIABLE_REGION: REGION,
                                            almacen_s3.VARIABLE_ENDPOINT: "http://127.0.0.1:9000"})
        self.assertEqual((ok.rol, ok.endpoint), (None, "http://127.0.0.1:9000"))

    def test_the_oidc_handoff_sets_and_resets_per_context(self):
        self.assertIsNone(almacen_s3._TOKEN_OIDC.get())
        marca = almacen_s3.fijar_token_oidc(TOKEN)
        try:
            self.assertEqual(almacen_s3._TOKEN_OIDC.get(), TOKEN)
            interior = almacen_s3.fijar_token_oidc("   ")
            self.assertIsNone(almacen_s3._TOKEN_OIDC.get())
            almacen_s3.restablecer_token_oidc(interior)
            self.assertEqual(almacen_s3._TOKEN_OIDC.get(), TOKEN)
            visto = []
            hilo = threading.Thread(target=lambda: visto.append(almacen_s3._TOKEN_OIDC.get()))
            hilo.start()
            hilo.join()
            self.assertEqual(visto, [None])          # a new thread does not inherit it
        finally:
            almacen_s3.restablecer_token_oidc(marca)
        self.assertIsNone(almacen_s3._TOKEN_OIDC.get())

    def test_importing_the_module_does_not_import_the_sdk(self):
        guardia = builtins.__import__

        def sin_sdk(nombre, *args, **kwargs):
            if nombre.split(".")[0] in ("boto3", "botocore"):
                raise AssertionError("the SDK was imported")
            return guardia(nombre, *args, **kwargs)
        import importlib
        with patch.object(builtins, "__import__", sin_sdk):
            importlib.reload(almacen_s3)
            almacen_s3.fabrica_desde_entorno(entorno())
        importlib.reload(almacen_s3)


@unittest.skipUnless(TIENE_SDK, "boto3 and moto are not installed (isolated dev environment only)")
class ConMoto(unittest.TestCase):
    """The contract against a local moto S3/STS server."""

    @classmethod
    def setUpClass(cls) -> None:
        from moto.server import ThreadedMotoServer
        cls.credenciales = patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "prueba", "AWS_SECRET_ACCESS_KEY": SECRETO,
            "AWS_DEFAULT_REGION": REGION})
        cls.credenciales.start()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        cls.servidor = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
        cls.servidor.start()
        host, puerto = cls.servidor.get_host_and_port()
        cls.endpoint = f"http://127.0.0.1:{puerto}"
        import boto3
        cls.crudo = boto3.client("s3", endpoint_url=cls.endpoint, region_name=REGION)
        cls.crudo.create_bucket(Bucket=BUCKET)
        cls.crudo.put_bucket_versioning(Bucket=BUCKET,
                                        VersioningConfiguration={"Status": "Enabled"})
        cls.crudo.create_bucket(Bucket=SIN_VERSIONES)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.servidor.stop()
        cls.credenciales.stop()

    def almacen(self, bucket: str = BUCKET, rol: str | None = None, **kwargs):
        config = almacen_s3.Configuracion(bucket, REGION, rol, self.endpoint)
        return almacen_s3.AlmacenS3(config, **kwargs)

    def setUp(self) -> None:
        self.s3 = self.almacen()
        self.id = uuid.uuid4().hex

    # -- the Almacen contract --------------------------------------------------------

    def test_contract_round_trip(self):
        t, f = f"temporal/{self.id}", f"final/{self.id}/n1"
        self.assertIsNone(self.s3.tamano_de(t))
        self.assertEqual(self.s3.guardar_temporal(t, [b"ab", bytearray(b"cd"), memoryview(b"e")], 10), 5)
        self.assertEqual(self.s3.tamano_de(t), 5)
        self.assertEqual(self.s3.copiar(t, f, 10), 5)
        with self.s3.leer(f, 10, bloque=2) as lectura:
            self.assertEqual((lectura.tamano, b"".join(lectura)), (5, b"abcde"))
        with self.assertRaises(LimiteExcedidoError):
            self.s3.leer(f, 4)
        with self.assertRaises(LimiteExcedidoError):
            self.s3.guardar_temporal(t, [b"x" * 11], 10)
        self.assertEqual(self.s3.tamano_de(t), 5)                       # the previous object stays
        claves = {m.clave for m in self.s3.listar(f"final/{self.id}/")}
        self.assertEqual(claves, {f})
        self.assertIn(t, {m.clave for m in self.s3.listar("temporal/")})
        self.assertTrue(self.s3.borrar(t))
        self.assertFalse(self.s3.borrar(t))
        with self.assertRaises(ObjetoAusenteError):
            self.s3.leer(t, 10)

    def test_compose_is_ordered_create_only_and_names_missing_sources(self):
        a, b = f"temporal/{self.id}-00", f"temporal/{self.id}-01"
        self.s3.guardar_temporal(a, [b"uno-"], 100)
        self.s3.guardar_temporal(b, [b"dos"], 100)
        destino = f"final/{self.id}/n1"
        self.assertEqual(self.s3.componer([a, b], destino, 100), 7)
        with self.assertRaises(ColisionError):
            self.s3.componer([b], destino, 100)
        self.assertEqual(b"".join(self.s3.leer(destino, 100)), b"uno-dos")
        with self.assertRaises(ObjetoAusenteError) as falta:
            self.s3.componer([a, f"temporal/{self.id}-07"], f"final/{self.id}/n2", 100)
        self.assertEqual(falta.exception.claves, (f"temporal/{self.id}-07",))
        with self.assertRaises(LimiteExcedidoError):
            self.s3.componer([a, b], f"final/{self.id}/n3", 6)
        self.assertIsNone(self.s3.tamano_de(f"final/{self.id}/n2"))
        self.assertIsNone(self.s3.tamano_de(f"final/{self.id}/n3"))

    def _restage_before_first_read(self, almacen, clave):
        real = almacen._llamar

        def llamar(operacion, segura, escritura, **argumentos):
            if operacion == "get_object" and argumentos.get("Key") == clave and not llamar.hecho:
                llamar.hecho = True
                self.crudo.put_object(Bucket=almacen._config.bucket, Key=clave, Body=b"TARDE")
            return real(operacion, segura, escritura, **argumentos)
        llamar.hecho = False
        return patch.object(almacen, "_llamar", llamar)

    def test_compose_reads_the_pinned_version_of_each_source(self):
        a = f"temporal/{self.id}-00"
        self.s3.guardar_temporal(a, [b"pin"], 100)
        with self._restage_before_first_read(self.s3, a):
            self.s3.componer([a], f"final/{self.id}/n1", 100)
        self.assertEqual(b"".join(self.s3.leer(f"final/{self.id}/n1", 100)), b"pin")

    def test_without_versioning_a_replaced_source_aborts_before_writing(self):
        s3 = self.almacen(SIN_VERSIONES)
        a = f"temporal/{self.id}-00"
        s3.guardar_temporal(a, [b"pin"], 100)
        with self._restage_before_first_read(s3, a), self.assertRaises(FalloAlmacenError) as fallo:
            s3.componer([a], f"final/{self.id}/n1", 100)
        self.assertNotIsInstance(fallo.exception, ResultadoInciertoError)
        self.assertIsNone(s3.tamano_de(f"final/{self.id}/n1"))

    def test_a_final_write_that_lands_but_loses_its_reply_is_uncertain(self):
        from botocore.exceptions import ReadTimeoutError
        a = f"temporal/{self.id}-00"
        self.s3.guardar_temporal(a, [b"datos"], 100)
        cliente = self.s3._cliente
        real = cliente.put_object

        def aterriza_y_pierde(**argumentos):
            real(**argumentos)
            raise ReadTimeoutError(endpoint_url=self.endpoint)
        with patch.object(cliente, "put_object", side_effect=aterriza_y_pierde), \
                self.assertRaises(ResultadoInciertoError):
            self.s3.componer([a], f"final/{self.id}/n1", 100)
        self.assertEqual(self.s3.tamano_de(f"final/{self.id}/n1"), 5)    # it did land

    def test_error_mapping(self):
        from botocore.stub import Stubber
        casos = [
            ("head_object", "AccessDenied", 403, lambda: self.s3.tamano_de("temporal/x"),
             FalloAlmacenError, False),
            ("get_object", "SlowDown", 503, lambda: self.s3.leer("temporal/x", 10),
             FalloAlmacenError, True),
            ("put_object", "InternalError", 500,
             lambda: self.s3.guardar_temporal("temporal/x", [b"1"], 10), ResultadoInciertoError, True),
            ("put_object", "InvalidArgument", 400,
             lambda: self.s3.guardar_temporal("temporal/x", [b"1"], 10), FalloAlmacenError, False),
        ]
        for operacion, codigo, estado, llamada, clase, reintentar in casos:
            with self.subTest(codigo=codigo), Stubber(self.s3._cliente) as stub, \
                    self.assertLogs("ara_map.archivos.s3") as log:
                for _ in range(3):
                    stub.add_client_error(operacion, service_error_code=codigo,
                                          http_status_code=estado)
                with self.assertRaises(clase) as fallo:
                    llamada()
                self.assertEqual(fallo.exception.reintentar, reintentar)
                self.assertNotIn(BUCKET, " ".join(log.output))
        cerrado = almacen_s3.AlmacenS3(almacen_s3.Configuracion(BUCKET, REGION, None,
                                                                "http://127.0.0.1:9"))
        with self.assertRaises(FalloAlmacenError) as fallo:
            cerrado.guardar_temporal("temporal/x", [b"1"], 10)     # never sent: not uncertain
        self.assertNotIsInstance(fallo.exception, ResultadoInciertoError)
        self.assertTrue(fallo.exception.reintentar)

    def test_expired_credentials_force_one_refresh_and_one_retry_of_a_safe_call(self):
        from botocore.stub import Stubber
        self.s3.guardar_temporal(f"temporal/{self.id}", [b"abc"], 10)
        antes = self.s3._generacion
        with Stubber(self.s3._cliente) as stub:
            stub.add_client_error("head_object", service_error_code="ExpiredToken",
                                  http_status_code=400)
            self.assertEqual(self.s3.tamano_de(f"temporal/{self.id}"), 3)   # retried on a new client
        self.assertEqual(self.s3._generacion, antes + 1)
        self.s3.guardar_temporal(f"temporal/{self.id}-00", [b"abc"], 10)
        real = self.s3._llamar

        def put_caducado(operacion, segura, escritura, **argumentos):
            if operacion == "put_object" and argumentos.get("IfNoneMatch") == "*":
                with Stubber(self.s3._cliente) as stub:
                    stub.add_client_error("put_object", service_error_code="ExpiredToken",
                                          http_status_code=400)
                    return real(operacion, segura, escritura, **argumentos)
            return real(operacion, segura, escritura, **argumentos)
        with patch.object(self.s3, "_llamar", put_caducado), \
                self.assertRaises(FalloAlmacenError) as fallo:
            self.s3.componer([f"temporal/{self.id}-00"], f"final/{self.id}/n1", 10)
        # The final write is not retried by the adapter; it was refused, so not uncertain.
        self.assertNotIsInstance(fallo.exception, ResultadoInciertoError)
        self.assertIsNone(self.s3.tamano_de(f"final/{self.id}/n1"))

    # -- credentials ---------------------------------------------------------------------

    def test_web_identity_uses_the_request_token_and_needs_one(self):
        sin_claves = {k: "" for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")}
        with patch.dict(os.environ, sin_claves):
            s3 = self.almacen(rol=ROL)
            with self.assertRaises(AlmacenNoConfiguradoError):
                s3.tamano_de("temporal/x")                       # no token in this context
            marca = almacen_s3.fijar_token_oidc(TOKEN)
            try:
                s3.guardar_temporal(f"temporal/{self.id}", [b"rol"], 10)
                self.assertEqual(s3.tamano_de(f"temporal/{self.id}"), 3)
            finally:
                almacen_s3.restablecer_token_oidc(marca)

    def _sts_falso(self, vence_en: timedelta, demora: float = 0.0, error=None):
        llamadas = []

        class Falso:
            def assume_role_with_web_identity(self, **argumentos):
                llamadas.append(argumentos["WebIdentityToken"])
                time.sleep(demora)
                if error is not None:
                    raise error
                return {"Credentials": {
                    "AccessKeyId": "ASIAFICTICIA", "SecretAccessKey": SECRETO,
                    "SessionToken": "sesion-ficticia",
                    "Expiration": datetime.now(timezone.utc) + vence_en}}
        return llamadas, (lambda: Falso())

    def test_simultaneous_first_use_and_warm_reuse(self):
        llamadas, fabrica = self._sts_falso(timedelta(hours=1), demora=0.2)
        s3 = self.almacen(rol=ROL, _sts=fabrica)
        self.assertEqual(llamadas, [])                           # construction exchanged nothing
        errores = []

        def peticion(n):
            marca = almacen_s3.fijar_token_oidc(f"token-{n}")
            try:
                s3.tamano_de(f"temporal/{self.id}")
            except Exception as exc:                             # noqa: BLE001
                errores.append(exc)
            finally:
                almacen_s3.restablecer_token_oidc(marca)
        hilos = [threading.Thread(target=peticion, args=(n,)) for n in range(16)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(errores, [])
        self.assertEqual(len(llamadas), 1, llamadas)             # measured with botocore 1.43.112
        for n in range(5):
            peticion(100 + n)
        self.assertEqual(len(llamadas), 1)                       # warm instance: reused

    def test_near_expiry_refreshes_with_the_current_request_token(self):
        llamadas, fabrica = self._sts_falso(timedelta(minutes=12))
        s3 = self.almacen(rol=ROL, _sts=fabrica)
        marca = almacen_s3.fijar_token_oidc("token-A")
        try:
            s3.tamano_de(f"temporal/{self.id}")
        finally:
            almacen_s3.restablecer_token_oidc(marca)
        self.assertEqual(llamadas, ["token-A"])
        import botocore.credentials as bc
        despues = datetime.now(timezone.utc) + timedelta(minutes=5)   # 7 min left: mandatory
        with patch.object(bc, "_local_now", lambda: despues):
            marca = almacen_s3.fijar_token_oidc("token-B")
            try:
                s3.tamano_de(f"temporal/{self.id}")
            finally:
                almacen_s3.restablecer_token_oidc(marca)
        self.assertEqual(llamadas, ["token-A", "token-B"])

    def test_sts_failures_are_classified(self):
        from botocore.exceptions import ClientError, ConnectTimeoutError

        def cliente(codigo, estado=400):
            return ClientError({"Error": {"Code": codigo, "Message": SECRETO},
                                "ResponseMetadata": {"HTTPStatusCode": estado}},
                               "AssumeRoleWithWebIdentity")
        for error, reintentar in ((cliente("AccessDenied", 403), False),
                                  (cliente("InvalidIdentityToken"), False),
                                  (cliente("ExpiredTokenException"), True),
                                  (cliente("IDPCommunicationError"), True),
                                  (cliente("Throttling"), True),
                                  (ConnectTimeoutError(endpoint_url="http://sts"), True)):
            with self.subTest(error=type(error).__name__), \
                    self.assertLogs("ara_map.archivos.s3") as log:
                _, fabrica = self._sts_falso(timedelta(hours=1), error=error)
                s3 = self.almacen(rol=ROL, _sts=fabrica)
                marca = almacen_s3.fijar_token_oidc(TOKEN)
                try:
                    with self.assertRaises(FalloAlmacenError) as fallo:
                        s3.tamano_de("temporal/x")
                finally:
                    almacen_s3.restablecer_token_oidc(marca)
                self.assertEqual(fallo.exception.reintentar, reintentar)
                texto = " ".join(log.output)
                self.assertNotIn(TOKEN, texto)
                self.assertNotIn(SECRETO, texto)

    def test_an_expired_credentials_answer_exchanges_again_with_the_current_token(self):
        from botocore.stub import Stubber
        llamadas, fabrica = self._sts_falso(timedelta(hours=1))
        s3 = self.almacen(rol=ROL, _sts=fabrica)
        marca = almacen_s3.fijar_token_oidc("token-A")
        try:
            s3.tamano_de(f"temporal/{self.id}")
        finally:
            almacen_s3.restablecer_token_oidc(marca)
        marca = almacen_s3.fijar_token_oidc("token-B")
        try:
            with Stubber(s3._cliente) as stub:
                stub.add_client_error("head_object", service_error_code="ExpiredToken",
                                      http_status_code=400)
                s3.tamano_de(f"temporal/{self.id}")
        finally:
            almacen_s3.restablecer_token_oidc(marca)
        self.assertEqual(llamadas, ["token-A", "token-B"])


if __name__ == "__main__":
    unittest.main()
