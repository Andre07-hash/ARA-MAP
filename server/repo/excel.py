"""Data access for connected workbooks.

Transaction boundaries (see excel/servicio.py for the whole sequence):

* claim(): one short transaction that expires stale runs and inserts the new
  run as 'en_curso' with a lease and the source generation it starts from.
  The partial unique index allows one running refresh per source.
* activate()/finish_*(): one short transaction after the file was fetched and
  parsed outside any database session. Activation writes the version, its
  immutable row snapshot, the identity registry and the materialized base,
  then compare-and-sets excel_fuente.generacion and the run's ownership. If
  either check fails, everything rolls back and the caller records why.

Nothing here talks to Microsoft or holds a session open across a network call.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from .. import db
from ..excel.lectura import Configuracion, Fila, Lectura, Problema
from ..excel.proveedor import Metadatos
from ..protocols import DatabaseConnection
from ..validation import validate_record
from . import terrenos as repo_terrenos

LEASE_SEGUNDOS = 100.0  # under Vercel's 120 s function limit


class EnCursoError(Exception):
    """Another refresh of this source holds a valid lease."""

    def __init__(self, ejecucion: dict[str, Any]) -> None:
        super().__init__("en curso")
        self.ejecucion = ejecucion


class ConflictoError(Exception):
    """The source changed (generation/configuration/state) under this run."""


class SinPropiedadError(Exception):
    """This run no longer owns its lease (expired or marked interrupted)."""


class IdempotenciaConflictoError(Exception):
    """The same Idempotency-Key was used for a different request."""


def _now() -> str:
    return db.now()


# -- reads -----------------------------------------------------------------

def conectada(conn: DatabaseConnection, base_id: int) -> bool:
    """Whether this base is the live view of a workbook source (connected or
    disconnected-with-history). Its terrains are owned by the workbook."""
    return conn.execute("SELECT 1 FROM excel_fuente WHERE base_id = ?", (base_id,)).fetchone() is not None


def proteger_base(conn: DatabaseConnection, base_id: int) -> None:
    from ..errors import ApiError
    if conectada(conn, base_id):
        raise ApiError(
            "Esta base se actualiza desde un Excel conectado: cambia los datos en Excel y usa"
            " «Actualizar desde Excel». No se puede editar, completar ni eliminar desde aquí.",
            409, {"code": "fuente_conectada"})

def fuente(conn: DatabaseConnection, fuente_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM excel_fuente WHERE id = ?", (fuente_id,)).fetchone()
    return dict(row) if row else None


def fuente_por_base(conn: DatabaseConnection, base_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM excel_fuente WHERE base_id = ?", (base_id,)).fetchone()
    return dict(row) if row else None


def fuente_por_archivo(conn: DatabaseConnection, drive_id: str, item_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM excel_fuente WHERE drive_id = ? AND item_id = ?",
                       (drive_id, item_id)).fetchone()
    return dict(row) if row else None


def configuracion(conn: DatabaseConnection, configuracion_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM excel_configuracion WHERE id = ?", (configuracion_id,)).fetchone()
    return dict(row) if row else None


def como_configuracion(row: Mapping[str, Any]) -> Configuracion:
    return Configuracion(row["hoja"], row["columna_id"], row["moneda"], row["columna_moneda"],
                         row["version_lector"])


def version(conn: DatabaseConnection, version_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM excel_version WHERE id = ?", (version_id,)).fetchone()
    return dict(row) if row else None


def filas_de_version(conn: DatabaseConnection, version_id: str) -> list[dict[str, Any]]:
    """Reconstruct one retained version: every row it held, in sheet order."""
    rows = conn.execute(
        "SELECT i.id AS identidad_id, i.clave, vf.fila, vf.datos_json, vf.huella"
        " FROM excel_version_fila vf JOIN excel_identidad i ON i.id = vf.identidad_id"
        " WHERE vf.version_id = ? ORDER BY vf.fila", (version_id,)).fetchall()
    return [{"identidad_id": r["identidad_id"], "clave": r["clave"], "fila": r["fila"],
             "datos": json.loads(r["datos_json"]), "huella": r["huella"]} for r in rows]


def identidades(conn: DatabaseConnection, fuente_id: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM excel_identidad WHERE fuente_id = ? ORDER BY clave", (fuente_id,)).fetchall()]


# Every run names who started it (the audit trail employees see).
_EJECUCION_SQL = ("SELECT e.*, u.display_name AS iniciada_por_nombre FROM excel_ejecucion e"
                  " LEFT JOIN team_user u ON u.id = e.iniciada_por")


def ejecucion(conn: DatabaseConnection, ejecucion_id: str) -> dict[str, Any] | None:
    row = conn.execute(_EJECUCION_SQL + " WHERE e.id = ?", (ejecucion_id,)).fetchone()
    return ejecucion_dto(row) if row else None


def ejecucion_por_clave(conn: DatabaseConnection, fuente_id: str, clave: str) -> dict[str, Any] | None:
    row = conn.execute(_EJECUCION_SQL + " WHERE e.fuente_id = ? AND e.clave_idempotencia = ?",
                       (fuente_id, clave)).fetchone()
    return ejecucion_dto(row) if row else None


def ultima_ejecucion(conn: DatabaseConnection, fuente_id: str) -> dict[str, Any] | None:
    row = conn.execute(_EJECUCION_SQL + " WHERE e.fuente_id = ?"
                       " ORDER BY e.iniciada_epoch DESC, e.id DESC LIMIT 1", (fuente_id,)).fetchone()
    return ejecucion_dto(row) if row else None


def ejecucion_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "tipo": row["tipo"], "estado": row["estado"],
        "iniciada_por": {"id": row["iniciada_por"], "display_name": row["iniciada_por_nombre"]},
        "iniciada_en": row["iniciada_en"],
        "terminada_en": row["terminada_en"], "version_id": row["version_id"],
        "conteos": None if row["agregados"] is None else {
            "agregados": row["agregados"], "actualizados": row["actualizados"],
            "eliminados": row["eliminados"], "sin_cambio": row["sin_cambio"]},
        "error": None if not row["error_codigo"] else {
            "codigo": row["error_codigo"], "mensaje": row["error_mensaje"]},
        "problemas": json.loads(row["problemas_json"]) if row["problemas_json"] else [],
        "candidato": row["candidato_huella"],
    }


def cuenta(conn: DatabaseConnection, cuenta_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT c.*, u.display_name AS conectada_por_nombre,"
        " (SELECT 1 FROM excel_credencial k WHERE k.cuenta_id = c.id) AS tiene_credencial"
        " FROM excel_cuenta c JOIN team_user u ON u.id = c.conectada_por WHERE c.id = ?",
        (cuenta_id,)).fetchone()
    return dict(row) if row else None


def cuenta_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    """Non-secret account identity. requiere_reconexion when no credential
    exists -- true after any restore that did not carry credentials."""
    return {"id": row["id"], "proveedor": row["proveedor"], "tipo": row["tipo"],
            "nombre": row["nombre"], "correo": row["correo"],
            "conectada_por": {"id": row["conectada_por"], "display_name": row["conectada_por_nombre"]},
            "conectada_en": row["conectada_en"],
            "requiere_reconexion": not row["tiene_credencial"]}


def cuentas(conn: DatabaseConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.*, u.display_name AS conectada_por_nombre,"
        " (SELECT 1 FROM excel_credencial k WHERE k.cuenta_id = c.id) AS tiene_credencial"
        " FROM excel_cuenta c JOIN team_user u ON u.id = c.conectada_por ORDER BY c.conectada_en").fetchall()
    return [cuenta_dto(r) for r in rows]


def fuente_dto(conn: DatabaseConnection, fuente_id: str) -> dict[str, Any] | None:
    f = fuente(conn, fuente_id)
    if f is None:
        return None
    c = cuenta(conn, f["cuenta_id"])
    cfg = configuracion(conn, f["configuracion_id"])
    v = version(conn, f["version_activa_id"]) if f["version_activa_id"] else None
    ultimo_error = ejecucion(conn, f["ultimo_error_id"]) if f["ultimo_error_id"] else None
    ultima = ultima_ejecucion(conn, fuente_id)
    assert cfg is not None and c is not None
    return {
        "id": f["id"], "base_id": f["base_id"], "estado": f["estado"], "generacion": f["generacion"],
        "archivo": {"nombre": f["nombre_archivo"], "web_url": f["web_url"]},
        "cuenta": cuenta_dto(c),
        "configuracion": {"id": cfg["id"], "numero": cfg["numero"], "hoja": cfg["hoja"],
                          "columna_id": cfg["columna_id"], "moneda": cfg["moneda"],
                          "columna_moneda": cfg["columna_moneda"],
                          "version_lector": cfg["version_lector"]},
        "version_activa": None if v is None else {
            "id": v["id"], "numero": v["numero"], "filas": v["filas"], "activada_en": v["activada_en"],
            "modificado_en": v["modificado_en"], "modificado_por": v["modificado_por"],
            "configuracion_id": v["configuracion_id"]},
        "ultima_revision_en": f["ultima_revision_en"],
        "ultima_exitosa_en": f["ultima_exitosa_en"],
        "ultimo_error": None if ultimo_error is None else {
            "ejecucion_id": ultimo_error["id"], "en": ultimo_error["terminada_en"],
            **(ultimo_error["error"] or {"codigo": ultimo_error["estado"], "mensaje": None})},
        "ultima_ejecucion": ultima,
        "en_curso": bool(ultima and ultima["estado"] == "en_curso"),
        "creada_en": f["creada_en"], "desconectada_en": f["desconectada_en"],
    }


def fuentes(conn: DatabaseConnection) -> list[dict[str, Any]]:
    ids = [r["id"] for r in conn.execute("SELECT id FROM excel_fuente ORDER BY creada_en").fetchall()]
    return [d for d in (fuente_dto(conn, i) for i in ids) if d is not None]


# -- runs: claim, finish, expire ---------------------------------------------

def expirar(conn: DatabaseConnection, fuente_id: str | None = None) -> int:
    """Mark runs whose lease ran out as interrupted. Their old data stays."""
    ahora = time.time()
    sql = ("UPDATE excel_ejecucion SET estado = 'interrumpida', terminada_en = ?,"
           " error_codigo = 'interrumpida', error_mensaje = ?"
           " WHERE estado = 'en_curso' AND lease_hasta < ?")
    params: list[Any] = [_now(), "La actualización se interrumpió; los datos anteriores siguen activos.", ahora]
    if fuente_id:
        sql += " AND fuente_id = ?"
        params.append(fuente_id)
    return int(conn.execute(sql, tuple(params)).rowcount)


def reclamar(conn: DatabaseConnection, fuente_row: Mapping[str, Any], tipo: str, clave: str,
             huella: str, user_id: str, lease: float = LEASE_SEGUNDOS) -> dict[str, Any]:
    """Start a run (one short transaction). Replays and conflicts are the
    caller's job (ejecucion_por_clave first)."""
    with db.transaction(conn):
        expirar(conn, fuente_row["id"])
        actual = conn.execute(_EJECUCION_SQL + " WHERE e.fuente_id = ? AND e.estado = 'en_curso'",
                              (fuente_row["id"],)).fetchone()
        if actual is not None:
            raise EnCursoError(ejecucion_dto(actual))
        run_id = str(uuid.uuid4())
        ahora = time.time()
        conn.execute(
            "INSERT INTO excel_ejecucion (id, fuente_id, tipo, estado, clave_idempotencia,"
            " huella_solicitud, iniciada_por, iniciada_en, iniciada_epoch, lease_hasta,"
            " generacion_base, configuracion_id) VALUES (?, ?, ?, 'en_curso', ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, fuente_row["id"], tipo, clave, huella, user_id, _now(), ahora, ahora + lease,
             fuente_row["generacion"], fuente_row["configuracion_id"]))
    result = ejecucion(conn, run_id)
    assert result is not None
    return result


def _poseer(conn: DatabaseConnection, run_id: str) -> dict[str, Any]:
    """The run row, if this caller still owns it (running, lease valid)."""
    row = conn.execute("SELECT * FROM excel_ejecucion WHERE id = ? AND estado = 'en_curso'"
                       " AND lease_hasta >= ?", (run_id, time.time())).fetchone()
    if row is None:
        raise SinPropiedadError(run_id)
    return dict(row)


def terminar(conn: DatabaseConnection, run_id: str, estado: str, *, codigo: str | None = None,
             mensaje: str | None = None, problemas: Sequence[Problema] = (),
             candidato: str | None = None, revisado: bool = False) -> bool:
    """Record a non-activating outcome (error, review, conflict, no change).
    Only the owning run may write; returns False if it no longer owns it, in
    which case nothing is changed -- not even its own status."""
    with db.transaction(conn):
        cursor = conn.execute(
            "UPDATE excel_ejecucion SET estado = ?, terminada_en = ?, error_codigo = ?,"
            " error_mensaje = ?, problemas_json = ?, candidato_huella = ?"
            " WHERE id = ? AND estado = 'en_curso' AND lease_hasta >= ?",
            (estado, _now(), codigo, mensaje,
             json.dumps([p.dto() for p in problemas], ensure_ascii=False) if problemas else None,
             candidato, run_id, time.time()))
        if cursor.rowcount != 1:
            return False
        run = conn.execute("SELECT fuente_id FROM excel_ejecucion WHERE id = ?", (run_id,)).fetchone()
        campos = []
        params: list[Any] = []
        if estado in ("error", "conflicto"):
            campos.append("ultimo_error_id = ?")
            params.append(run_id)
        if revisado:  # the file was read: "last checked" advances
            campos.append("ultima_revision_en = ?")
            params.append(_now())
        if estado == "sin_cambios":
            campos += ["ultima_exitosa_en = ?", "ultimo_error_id = NULL"]
            params.append(_now())
        if campos:
            conn.execute(f"UPDATE excel_fuente SET {', '.join(campos)} WHERE id = ?",
                         (*params, run["fuente_id"]))
    return True


def interrumpir_propia(conn: DatabaseConnection, run_id: str, codigo: str, mensaje: str) -> None:
    """A run that lost its lease marks itself interrupted -- only if nobody
    else already settled it."""
    with db.transaction(conn):
        conn.execute("UPDATE excel_ejecucion SET estado = 'interrumpida', terminada_en = ?,"
                     " error_codigo = ?, error_mensaje = ? WHERE id = ? AND estado = 'en_curso'",
                     (_now(), codigo, mensaje, run_id))


# -- creation and configuration ------------------------------------------------

def crear_fuente(conn: DatabaseConnection, *, base_id: int, cuenta_id: str, drive_id: str,
                 item_id: str, nombre_archivo: str, web_url: str | None, config: Configuracion,
                 user_id: str) -> tuple[str, str]:
    """Insert source + configuration 1 (inside the caller's transaction)."""
    fuente_id = str(uuid.uuid4())
    configuracion_id = str(uuid.uuid4())
    ahora = _now()
    conn.execute(
        "INSERT INTO excel_fuente (id, base_id, cuenta_id, drive_id, item_id, nombre_archivo,"
        " web_url, configuracion_id, creada_por, creada_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fuente_id, base_id, cuenta_id, drive_id, item_id, nombre_archivo, web_url,
         configuracion_id, user_id, ahora))
    _insertar_configuracion(conn, fuente_id, configuracion_id, 1, config, drive_id, item_id, user_id)
    return fuente_id, configuracion_id


def _insertar_configuracion(conn: DatabaseConnection, fuente_id: str, configuracion_id: str,
                            numero: int, config: Configuracion, drive_id: str, item_id: str,
                            user_id: str) -> None:
    conn.execute(
        "INSERT INTO excel_configuracion (id, fuente_id, numero, hoja, columna_id, moneda,"
        " columna_moneda, version_lector, huella, creada_por, creada_en)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (configuracion_id, fuente_id, numero, config.hoja, config.columna_id, config.moneda,
         config.columna_moneda, config.version_lector, config.huella(drive_id, item_id), user_id, _now()))


def cambiar_configuracion(conn: DatabaseConnection, fuente_id: str, generacion: int,
                          config: Configuracion, user_id: str) -> str:
    """A reviewed mapping change: new configuration, generation bump. The
    next refresh re-evaluates the file under it even if the bytes did not
    change. A run in flight is fenced out by the generation change."""
    with db.transaction(conn):
        f = fuente(conn, fuente_id)
        if f is None or f["generacion"] != generacion:
            raise ConflictoError()
        numero = int(conn.execute("SELECT MAX(numero) AS n FROM excel_configuracion WHERE fuente_id = ?",
                                  (fuente_id,)).fetchone()["n"]) + 1
        configuracion_id = str(uuid.uuid4())
        _insertar_configuracion(conn, fuente_id, configuracion_id, numero, config,
                                f["drive_id"], f["item_id"], user_id)
        cursor = conn.execute("UPDATE excel_fuente SET configuracion_id = ?, generacion = generacion + 1"
                              " WHERE id = ? AND generacion = ?", (configuracion_id, fuente_id, generacion))
        if cursor.rowcount != 1:
            raise ConflictoError()
    return configuracion_id


def cambiar_estado(conn: DatabaseConnection, fuente_id: str, generacion: int, estado: str) -> None:
    """Disconnect (refresh disabled, base and history kept) or reconnect."""
    with db.transaction(conn):
        cursor = conn.execute(
            "UPDATE excel_fuente SET estado = ?, generacion = generacion + 1, desconectada_en = ?"
            " WHERE id = ? AND generacion = ?",
            (estado, _now() if estado == "desconectada" else None, fuente_id, generacion))
        if cursor.rowcount != 1:
            raise ConflictoError()


# -- activation -----------------------------------------------------------------

def activar(conn: DatabaseConnection, run_id: str, lectura: Lectura, meta: Metadatos, sha256: str,
            *, vacia_confirmada: bool = False) -> dict[str, int]:
    """Make this candidate the active version and the live base, atomically.

    Fenced: the run must still own its lease, and the source must still be at
    the generation and configuration the run started from. Any failure rolls
    back every write here (version, snapshot, identities, terrains)."""
    with db.transaction(conn):
        run = _poseer(conn, run_id)
        f = fuente(conn, run["fuente_id"])
        if (f is None or f["generacion"] != run["generacion_base"]
                or f["configuracion_id"] != run["configuracion_id"] or f["estado"] != "activa"):
            raise ConflictoError()
        numero = (conn.execute("SELECT MAX(numero) AS n FROM excel_version WHERE fuente_id = ?",
                               (f["id"],)).fetchone()["n"] or 0) + 1
        version_id = str(uuid.uuid4())
        ahora = _now()
        conn.execute(
            "INSERT INTO excel_version (id, fuente_id, numero, configuracion_id, ejecucion_id, etag,"
            " ctag, sha256, contenido_huella, tamano, modificado_en, modificado_por, filas,"
            " vacia_confirmada, activada_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (version_id, f["id"], numero, f["configuracion_id"], run_id, meta.etag, meta.ctag, sha256,
             lectura.contenido_huella, meta.tamano, meta.modificado_en, meta.modificado_por,
             len(lectura.filas), 1 if vacia_confirmada else 0, ahora))
        conteos = _materializar(conn, f, version_id, numero, lectura.filas)
        conn.execute("UPDATE base SET archivo_origen = ?, hoja = ? WHERE id = ?",
                     (meta.nombre, lectura.hoja, f["base_id"]))
        cursor = conn.execute(
            "UPDATE excel_fuente SET version_activa_id = ?, generacion = generacion + 1,"
            " nombre_archivo = ?, web_url = COALESCE(?, web_url), ultima_revision_en = ?,"
            " ultima_exitosa_en = ?, ultimo_error_id = NULL"
            " WHERE id = ? AND generacion = ? AND configuracion_id = ? AND estado = 'activa'",
            (version_id, meta.nombre, meta.web_url, ahora, ahora, f["id"], run["generacion_base"],
             run["configuracion_id"]))
        if cursor.rowcount != 1:
            raise ConflictoError()
        cursor = conn.execute(
            "UPDATE excel_ejecucion SET estado = 'ok', terminada_en = ?, version_id = ?,"
            " agregados = ?, actualizados = ?, eliminados = ?, sin_cambio = ?"
            " WHERE id = ? AND estado = 'en_curso' AND lease_hasta >= ?",
            (ahora, version_id, conteos["agregados"], conteos["actualizados"], conteos["eliminados"],
             conteos["sin_cambio"], run_id, time.time()))
        if cursor.rowcount != 1:
            raise SinPropiedadError(run_id)
    return conteos


def _materializar(conn: DatabaseConnection, f: Mapping[str, Any], version_id: str, numero: int,
                  filas: Sequence[Fila]) -> dict[str, int]:
    """Bring the live base to exactly these rows, keyed by stable ID, and
    write the immutable snapshot. Identities are never deleted."""
    activos: dict[str, dict[str, Any]] = {}
    if f["version_activa_id"]:
        for r in conn.execute(
                "SELECT i.id, i.clave, i.terreno_id, vf.huella FROM excel_version_fila vf"
                " JOIN excel_identidad i ON i.id = vf.identidad_id WHERE vf.version_id = ?",
                (f["version_activa_id"],)).fetchall():
            activos[r["clave"]] = dict(r)
    registro = {r["clave"]: dict(r) for r in conn.execute(
        "SELECT * FROM excel_identidad WHERE fuente_id = ?", (f["id"],)).fetchall()}
    conteos = {"agregados": 0, "actualizados": 0, "eliminados": 0, "sin_cambio": 0}
    vistos: set[str] = set()

    for orden, fila in enumerate(filas, start=1):
        vistos.add(fila.clave)
        identidad = registro.get(fila.clave)
        if identidad is None:
            identidad = {"id": str(uuid.uuid4()), "terreno_id": None}
            conn.execute(
                "INSERT INTO excel_identidad (id, fuente_id, clave, primera_version, ultima_version)"
                " VALUES (?, ?, ?, ?, ?)", (identidad["id"], f["id"], fila.clave, numero, numero))
        activo = activos.get(fila.clave)
        if activo is not None and identidad["terreno_id"] is not None:
            if activo["huella"] == fila.huella:
                conteos["sin_cambio"] += 1
            else:
                repo_terrenos.update_from_record(conn, identidad["terreno_id"], fila.record,
                                                 validate_record(fila.record))
                conteos["actualizados"] += 1
            terreno_id = identidad["terreno_id"]
        else:  # new, or a removed ID coming back: same logical identity
            (terreno_id,) = repo_terrenos.insert(conn, f["base_id"], [fila.record],
                                                 {fila.record.orden: validate_record(fila.record)})
            conteos["agregados"] += 1
        conn.execute("UPDATE terreno SET orden = ? WHERE id = ? AND orden <> ?", (orden, terreno_id, orden))
        conn.execute("UPDATE excel_identidad SET terreno_id = ?, ultima_version = ?,"
                     " eliminada_en_version = NULL WHERE id = ?", (terreno_id, numero, identidad["id"]))
        conn.execute(
            "INSERT INTO excel_version_fila (fuente_id, version_id, identidad_id, fila, datos_json, huella)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (f["id"], version_id, identidad["id"], fila.fila,
             json.dumps(fila.datos, ensure_ascii=False, sort_keys=True), fila.huella))

    for clave, activo in activos.items():
        if clave in vistos:
            continue
        terreno_id = registro[clave]["terreno_id"]
        conn.execute("UPDATE excel_identidad SET terreno_id = NULL, eliminada_en_version = ?"
                     " WHERE id = ?", (numero, activo["id"]))
        if terreno_id is not None:
            conn.execute("DELETE FROM terreno WHERE id = ?", (terreno_id,))
        conteos["eliminados"] += 1
    return conteos


def contenido_activo(conn: DatabaseConnection, fuente_id: str) -> tuple[str | None, str | None, int]:
    """(contenido_huella, configuracion_id, filas) of the active version."""
    row = conn.execute("SELECT v.contenido_huella, v.configuracion_id, v.filas FROM excel_fuente f"
                       " JOIN excel_version v ON v.id = f.version_activa_id WHERE f.id = ?",
                       (fuente_id,)).fetchone()
    return (row["contenido_huella"], row["configuracion_id"], row["filas"]) if row else (None, None, 0)
