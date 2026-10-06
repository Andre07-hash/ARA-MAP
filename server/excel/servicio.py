"""Connecting a workbook and refreshing it.

Sequence of every refresh (no database session is open during network I/O,
so the Postgres workspace lock is never held while Microsoft answers):

  1. session A, short transaction: idempotency lookup, expire stale runs,
     claim a run ('en_curso', lease, source generation, configuration).
  2. no session: fetch ONE coherent provider revision and parse it.
  3. session B, short transaction: decide -- no change / review (empty
     candidate) / data errors / activate -- and record the outcome. Activation
     is fenced on the run's lease and the source generation.

The request itself does all three (bounded synchronous design). If the process
dies between 1 and 3, the run's lease expires; the old version stays active,
the next read or claim marks the run 'interrumpida', and a new refresh may
start. Nothing completes unattended after a lost process.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from .. import db
from ..repo import bases as repo_bases
from ..repo import excel as repo
from ..repo import inventario as repo_inventario
from .lectura import MAX_BYTES, Configuracion, LecturaError, Problema, leer
from .proveedor import Proveedor, ProveedorError, version_coherente

log = logging.getLogger(__name__)

FabricaProveedor = Callable[[Mapping[str, Any]], Proveedor]
"""Builds the provider for a file identity: {cuenta_id, drive_id, item_id}."""


class DatosInvalidosError(Exception):
    def __init__(self, problemas: list[Problema]) -> None:
        super().__init__("datos inválidos")
        self.problemas = problemas


class YaConectadaError(Exception):
    def __init__(self, fuente_id: str) -> None:
        super().__init__(fuente_id)
        self.fuente_id = fuente_id


class NoActivaError(Exception):
    """The source is disconnected (or missing)."""


def huella(datos: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _leer(proveedor: Proveedor, config: Configuracion) -> tuple[Any, bytes, Any]:
    meta, contenido = version_coherente(proveedor, MAX_BYTES)
    return meta, contenido, leer(contenido, config)


# -- connect ----------------------------------------------------------------------

def conectar(*, fabrica: FabricaProveedor, cuenta_id: str, drive_id: str, item_id: str,
             config: Configuracion, nombre: str, carpeta_id: int | None, actor: Mapping[str, Any],
             clave: str) -> dict[str, Any]:
    """Validate the workbook under its configuration, then create the base,
    the source, configuration 1 and version 1 in ONE transaction. A retry with
    the same Idempotency-Key returns the original result; a different request
    under that key is a conflict. Nothing is created when the data is invalid."""
    solicitud = huella({"op": "conectar", "cuenta": cuenta_id, "drive": drive_id, "item": item_id,
                        "hoja": config.hoja, "id": config.columna_id, "moneda": config.moneda,
                        "columna_moneda": config.columna_moneda, "nombre": nombre, "carpeta": carpeta_id})
    with db.session() as conn:
        previo = _resultado_previo(conn, clave, solicitud)
        if previo is not None:
            return previo
        existente = repo.fuente_por_archivo(conn, drive_id, item_id)
        if existente is not None:
            raise YaConectadaError(existente["id"])
        if repo.cuenta(conn, cuenta_id) is None:
            raise ProveedorError("reconectar", "Esa cuenta de Microsoft no está conectada.")

    meta, contenido, lectura = _leer(fabrica({"cuenta_id": cuenta_id, "drive_id": drive_id,
                                              "item_id": item_id}), config)
    if lectura.problemas:
        raise DatosInvalidosError(list(lectura.problemas))
    if not lectura.filas:
        raise DatosInvalidosError([Problema("vacio", "La hoja no tiene ningún terreno.")])

    sha = hashlib.sha256(contenido).hexdigest()
    try:
        with db.session() as conn, db.transaction(conn):
            # The key row is the first write: a concurrent retry waits, then collides.
            conn.execute(
                "INSERT INTO inventory_operation_result (operation, idempotency_key, request_hash,"
                " result_json, actor_id, created_at) VALUES ('excel_conectar', ?, ?, '{}', ?, ?)",
                (clave, solicitud, actor["id"], db.now()))
            base_id = repo_bases.create(conn, repo_bases.unique_name(conn, nombre), meta.nombre,
                                        config.hoja, carpeta_id=carpeta_id)
            fuente_id, _ = repo.crear_fuente(
                conn, base_id=base_id, cuenta_id=cuenta_id, drive_id=drive_id, item_id=item_id,
                nombre_archivo=meta.nombre, web_url=meta.web_url, config=config, user_id=actor["id"])
            f = repo.fuente(conn, fuente_id)
            assert f is not None
            run = repo.reclamar(conn, f, "conexion", clave, solicitud, actor["id"])
            repo.activar(conn, run["id"], lectura, meta, sha)
            resultado = {"fuente": repo.fuente_dto(conn, fuente_id), "ejecucion": repo.ejecucion(conn, run["id"])}
            conn.execute("UPDATE inventory_operation_result SET result_json = ?"
                         " WHERE operation = 'excel_conectar' AND idempotency_key = ?",
                         (json.dumps(resultado, ensure_ascii=False), clave))
            return resultado
    except Exception as exc:
        if not repo_inventario._unique_violation(exc):
            raise
    # Lost a race with an identical retry (or the same file was connected
    # concurrently): answer from what was committed.
    with db.session() as conn:
        previo = _resultado_previo(conn, clave, solicitud)
        if previo is not None:
            return previo
        existente = repo.fuente_por_archivo(conn, drive_id, item_id)
    if existente is not None:
        raise YaConectadaError(existente["id"])
    raise RuntimeError("conexión interrumpida sin resultado registrado")


def _resultado_previo(conn: Any, clave: str, solicitud: str) -> dict[str, Any] | None:
    previo = repo_inventario.stored_result(conn, "excel_conectar", clave)
    if previo is None:
        return None
    if previo["request_hash"] != solicitud:
        raise repo.IdempotenciaConflictoError()
    resultado: dict[str, Any] = previo["result"]
    return {**resultado, "repeticion": True}


# -- refresh ------------------------------------------------------------------------

def actualizar(*, fabrica: FabricaProveedor, fuente_id: str, actor: Mapping[str, Any], clave: str,
               confirmar_vacio: str | None = None) -> dict[str, Any]:
    """One refresh, start to recorded outcome. Returns {ejecucion, fuente}."""
    solicitud = huella({"op": "actualizar", "fuente": fuente_id, "confirmar_vacio": confirmar_vacio})
    with db.session() as conn:
        previa = conn.execute("SELECT id, huella_solicitud FROM excel_ejecucion"
                              " WHERE fuente_id = ? AND clave_idempotencia = ?",
                              (fuente_id, clave)).fetchone()
        if previa is not None:
            if previa["huella_solicitud"] != solicitud:
                raise repo.IdempotenciaConflictoError()
            repo.expirar(conn, fuente_id)
            return {"ejecucion": repo.ejecucion(conn, previa["id"]),
                    "fuente": repo.fuente_dto(conn, fuente_id), "repeticion": True}
        f = repo.fuente(conn, fuente_id)
        if f is None or f["estado"] != "activa":
            raise NoActivaError()
        run = repo.reclamar(conn, f, "actualizacion", clave, solicitud, actor["id"])
        cfg_row = repo.configuracion(conn, f["configuracion_id"])
        assert cfg_row is not None
        config = repo.como_configuracion(cfg_row)
        cfg_huella = cfg_row["huella"]

    run_id = run["id"]
    try:
        _ejecutar(fabrica, f, run_id, config, cfg_huella, confirmar_vacio)
    except Exception:  # noqa: BLE001 - recorded, never leaves a run hanging
        log.exception("Excel refresh failed unexpectedly")
        with db.session() as conn:
            repo.terminar(conn, run_id, "error", codigo="interno",
                          mensaje="Ocurrió un error inesperado; los datos anteriores siguen activos.")
    with db.session() as conn:
        return {"ejecucion": repo.ejecucion(conn, run_id), "fuente": repo.fuente_dto(conn, fuente_id)}


def _ejecutar(fabrica: FabricaProveedor, f: Mapping[str, Any], run_id: str, config: Configuracion,
              cfg_huella: str, confirmar_vacio: str | None) -> None:
    try:
        meta, contenido, lectura = _leer(fabrica(f), config)
    except ProveedorError as exc:
        with db.session() as conn:
            repo.terminar(conn, run_id, "conflicto" if exc.codigo == "archivo_cambiando" else "error",
                          codigo=exc.codigo, mensaje=exc.mensaje)
        return
    except LecturaError as exc:
        with db.session() as conn:
            repo.terminar(conn, run_id, "error", codigo=exc.codigo, mensaje=exc.mensaje, revisado=True)
        return

    if lectura.problemas:
        with db.session() as conn:
            repo.terminar(conn, run_id, "error", codigo="datos_invalidos",
                          mensaje="El libro tiene filas que no se pueden usar; nada cambió.",
                          problemas=lectura.problemas, revisado=True)
        return

    sha = hashlib.sha256(contenido).hexdigest()
    with db.session() as conn:
        try:
            huella_activa, cfg_activa, filas_activas = repo.contenido_activo(conn, f["id"])
            if cfg_activa == f["configuracion_id"] and huella_activa == lectura.contenido_huella:
                repo.terminar(conn, run_id, "sin_cambios", revisado=True)
                return
            if not lectura.filas and filas_activas > 0:
                candidato = huella({"sha": sha, "configuracion": cfg_huella, "contenido": lectura.contenido_huella})
                if confirmar_vacio != candidato:
                    repo.terminar(conn, run_id, "revision", codigo="vacio", candidato=candidato,
                                  mensaje="La hoja quedó sin terrenos. Confirma si de verdad quieres vaciar"
                                          " la base; mientras tanto se conservan los datos anteriores.",
                                  revisado=True)
                    return
                repo.activar(conn, run_id, lectura, meta, sha, vacia_confirmada=True)
                return
            repo.activar(conn, run_id, lectura, meta, sha)
        except repo.ConflictoError:
            repo.terminar(conn, run_id, "conflicto", codigo="conflicto",
                          mensaje="La fuente cambió durante la actualización (otra actualización o un cambio"
                                  " de configuración). Vuelve a intentarlo.")
        except repo.SinPropiedadError:
            repo.interrumpir_propia(conn, run_id, "interrumpida",
                                    "La actualización tardó demasiado y se descartó; los datos anteriores"
                                    " siguen activos.")


# -- configuration and lifecycle --------------------------------------------------

def configurar(*, fabrica: FabricaProveedor, fuente_id: str, generacion: int, config: Configuracion,
               actor: Mapping[str, Any]) -> dict[str, Any]:
    """A reviewed mapping change. The new configuration must read the current
    file without structural errors before it is stored."""
    with db.session() as conn:
        f = repo.fuente(conn, fuente_id)
        if f is None:
            raise NoActivaError()
    _, _, lectura = _leer(fabrica(f), config)  # LecturaError propagates: nothing stored
    with db.session() as conn:
        repo.cambiar_configuracion(conn, fuente_id, generacion, config, actor["id"])
        return {"fuente": repo.fuente_dto(conn, fuente_id),
                "vista_previa": {"filas": len(lectura.filas),
                                 "problemas": [p.dto() for p in lectura.problemas[:50]]}}
