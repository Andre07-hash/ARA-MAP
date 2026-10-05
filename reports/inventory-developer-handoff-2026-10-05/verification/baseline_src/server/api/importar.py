"""Import and append endpoints.

The browser posts the file's raw bytes with the filename in a header, which
avoids multipart parsing entirely -- the `cgi` module was removed in Python 3.13
and a local single-user app has no need for it.

Excel workbooks (.xlsx, .xlsm) and CSV files (.csv) share everything after the
read: the same records, validation, staging, confirmation and append. A CSV is
parsed once, at preview, with the number convention the user chose; the token
holds that result, so confirming never re-reads the file with other settings.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import unquote

from .. import db
from ..csv_importer import read_csv_bytes
from ..csv_numbers import DECIMAL_MODES, DOT
from ..errors import WorkbookError
from ..importer import COLUMN_ALIASES, ImportResult, read_workbook
from ..matching import Disposition, classify
from ..normalize import fold
from ..repo import bases as repo_bases
from ..repo import carpetas as repo_carpetas
from ..repo import formatos as repo_formatos
from ..repo import terrenos as repo_terrenos
from ..router import Request
from ..staging import staging
from ..validation import summarize, validate_all
from ..web_util import ApiError, parse_json, require
from .carpetas import NO_EXISTE, destination, folder_errors

Respuesta = dict[str, Any]

MAX_UPLOAD = 25 * 1024 * 1024


EXCEL_SUFFIXES = (".xlsx", ".xlsm")
CSV_SUFFIX = ".csv"
UNSUPPORTED = (
    "Formato no admitido. Selecciona un archivo .xlsx, .xlsm o .csv. "
    "Si usas Numbers, expórtalo a Excel o CSV UTF-8."
)


class Upload(NamedTuple):
    nombre: str
    resultado: ImportResult
    formato: str                # "xlsx", "xlsm" or "csv"
    csv_decimal: str | None     # the number convention a CSV was read with


def _read_upload(request: Request) -> Upload:
    if not request.body:
        raise ApiError("No se recibió ningún archivo.")
    if len(request.body) > MAX_UPLOAD:
        raise ApiError("El archivo supera el límite de 25 MB.", 413)

    nombre = unquote(request.headers.get("X-Archivo", "") or "base.xlsx")
    suffix = Path(nombre).suffix.lower()

    if suffix == CSV_SUFFIX:
        decimal = request.q("csv_decimal") or DOT
        if decimal not in DECIMAL_MODES:
            raise ApiError("Formato de números no válido: usa csv_decimal=dot o csv_decimal=comma.")
        try:
            return Upload(nombre, read_csv_bytes(request.body, decimal_mode=decimal), "csv", decimal)
        except WorkbookError as exc:
            raise ApiError(str(exc)) from exc

    if suffix not in EXCEL_SUFFIXES:
        raise ApiError(UNSUPPORTED)

    # openpyxl needs a real path, so the upload lands in a temp file we delete.
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
        handle.write(request.body)
        temp_path = Path(handle.name)

    try:
        return Upload(nombre, read_workbook(temp_path), suffix[1:], None)
    except WorkbookError as exc:
        raise ApiError(str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _duplicate_aliases(resultado: ImportResult) -> list[str]:
    """Columns that name a field an earlier column already took.

    They are kept as extra data, but saying so plainly beats listing them as
    "unrecognized" when the user can see they are a known name.
    """
    return [c for c in resultado.columnas_no_reconocidas if fold(c) in COLUMN_ALIASES]


def _muestra(resultado: ImportResult, incidencias: dict[int, Any], limite: int = 200) -> list[dict[str, Any]]:
    """The findings list shown in the preview, errors first."""
    filas: list[dict[str, Any]] = []
    for record in resultado.records:
        found = incidencias.get(record.orden, ())
        if not found:
            continue
        filas.append({
            "fila": record.fila,
            "terreno": record.terreno,
            "incidencias": [
                {"codigo": f.codigo, "severidad": f.severidad, "mensaje": f.mensaje}
                for f in found
            ],
        })
    filas.sort(key=lambda f: 0 if any(i["severidad"] == "error" for i in f["incidencias"]) else 1)
    return filas[:limite]


def preview(request: Request) -> Respuesta:
    """Parse and validate a workbook without writing anything."""
    nombre_archivo, resultado, formato, csv_decimal = _read_upload(request)
    if not resultado.records:
        raise ApiError(
            "El CSV no contiene ningún terreno con nombre." if formato == "csv"
            else "La hoja no contiene ningún terreno con nombre."
        )

    incidencias = validate_all(resultado.records)
    pending = staging.put(
        nombre_archivo, Path(nombre_archivo).stem, resultado, incidencias
    )

    payload = {
        "token": pending.token,
        "archivo": nombre_archivo,
        "nombre_sugerido": pending.nombre_sugerido,
        "hoja": resultado.hoja,
        "formato": formato,
        "conteo": len(resultado.records),
        "ubicados": resultado.ubicados,
        "sin_ubicacion": resultado.sin_ubicacion,
        "sin_coordenadas": resultado.sin_coordenadas,
        "ubicacion_invalida": resultado.ubicacion_invalida,
        "filas_con_datos": resultado.filas_con_datos,
        "rechazadas": [
            {"fila": r.fila, "motivo": r.motivo, "resumen": r.resumen}
            for r in resultado.rechazadas
        ],
        "resumen": summarize(incidencias),
        "hallazgos": _muestra(resultado, incidencias),
        "columnas_no_reconocidas": list(resultado.columnas_no_reconocidas),
        "columnas_faltantes": list(resultado.columnas_faltantes),
        "columnas_duplicadas": _duplicate_aliases(resultado),
    }
    if csv_decimal is not None:
        payload["csv_decimal"] = csv_decimal

    base_id = request.q("base_id")
    if base_id:
        payload["clasificacion"] = _clasificar(int(base_id), resultado)
    return payload


def _clasificar(base_id: int, resultado: ImportResult) -> dict[str, Any]:
    """Work out what an append would do, without doing it."""
    with db.session() as conn:
        if repo_bases.get(conn, base_id) is None:
            raise ApiError("La base indicada no existe.", 404)
        existentes = repo_terrenos.dedupe_rows(conn, base_id)

    decisiones = classify(resultado.records, existentes)
    detalle = []
    for decision in decisiones:
        if decision.disposition is Disposition.NUEVA:
            continue
        record = resultado.records[decision.incoming_index]
        diferencias = [
            {"campo": d.campo, "etiqueta": d.etiqueta,
             "anterior": d.anterior, "nuevo": d.nuevo}
            for d in decision.diferencias
        ]
        detalle.append({
            "indice": decision.incoming_index,
            "fila": record.fila,
            "terreno": record.terreno,
            "disposicion": decision.disposition.value,
            "motivo": decision.reason,
            "terreno_id": decision.existing_id,
            "diferencias": diferencias,
            # Filling a field that was empty is a correction, not a disputed
            # edit, so that case defaults to accepting the new value.
            "solo_completa": bool(diferencias)
                             and all(d["anterior"] in (None, "") for d in diferencias),
        })

    return {
        "nuevas": sum(1 for d in decisiones if d.disposition is Disposition.NUEVA),
        "duplicadas": sum(1 for d in decisiones if d.disposition is Disposition.DUPLICADA),
        "conflictos": sum(1 for d in decisiones if d.disposition is Disposition.CONFLICTO),
        "detalle": detalle,
    }


log = logging.getLogger("ara.importar")


def _vigente(pending: Any) -> None:
    """Claim the preview's draft for this confirmation, before any write.

    A single compare-and-set on the draft revision: if a correction produced a
    newer preview first, this confirmation is refused; if this claim wins, any
    later correction is refused. The two can never both succeed.

    The draft must exist. A preview whose draft is gone -- because another
    revision of it was already imported, or it expired or was evicted -- is
    stale, never a licence to write. Legacy previews (no assistant draft)
    return early and keep their original behaviour.
    """
    from ..asistente.borradores import RevisionObsoleta, borradores
    meta = pending.meta or {}
    if not meta.get("borrador"):
        return
    try:
        reclamado = borradores.reclamar(meta["borrador"], meta.get("revision", -1))
    except RevisionObsoleta:
        raise ApiError("La vista previa fue reemplazada por una más reciente. "
                       "Confirma la versión que tienes en pantalla.", 409) from None
    if not reclamado:
        raise ApiError("Esta vista previa ya no es válida: se importó otra versión o expiró. "
                       "Vuelve a seleccionar el archivo.", 410)


@contextmanager
def _confirmacion(pending: Any) -> Iterator[None]:
    """From the claim to the end of a commit.

    The draft is closed afterwards -- on success or failure -- and only once
    the caller's business-data session has exited: closing it opens its own
    session, which in the cloud takes the workspace lock that session held.
    Errors keep their type and message; an ApiError raised after the claim is
    marked so the dialog knows this preview is spent and must be reselected.
    """
    _vigente(pending)
    asistente = bool((pending.meta or {}).get("borrador"))
    try:
        yield
    except ApiError as exc:
        if asistente:
            exc.detalle = {**(exc.detalle or {}), "vista_previa_consumida": True}
        raise
    finally:
        _cerrar_borrador(pending)


def _registrar(conn: Any, pending: Any, base_id: int, tipo: str, recordar: bool) -> dict[str, Any] | None:
    """Record where the rows came from and, if asked, remember the format.

    Runs inside the commit's transaction: a failed import remembers nothing.
    """
    meta = pending.meta or {}
    if not meta.get("plan"):
        return None
    formato_id, formato_version = None, None
    usado = meta.get("formato_usado") or {}
    recordado = None
    if recordar and meta.get("recordar"):
        datos = meta["recordar"]
        formato_id, formato_version, accion = repo_formatos.recordar(
            conn, datos["nombre"], datos["firma"], datos["config"], datos["plan_version"])
        recordado = {"id": formato_id, "version": formato_version, "accion": accion}
    elif usado:
        formato_id, formato_version = usado.get("id"), usado.get("version")
    repo_formatos.registrar_importacion(
        conn, base_id=base_id, tipo=tipo, archivo=meta.get("archivo"), sha256=meta.get("sha256"),
        hoja=meta.get("hoja"), fila_encabezado=meta.get("fila_encabezado"), plan=meta["plan"],
        formato_id=formato_id, formato_version=formato_version)
    return recordado


def _cerrar_borrador(pending: Any) -> None:
    """Delete a claimed draft. Never masks the outcome of the import: if the
    deletion itself fails, the draft stays claimed (so no stale request can
    use it) until it expires, and only the failure's type is logged."""
    from ..asistente.borradores import borradores
    token = (pending.meta or {}).get("borrador")
    if not token:
        return
    try:
        borradores.borrar(token)
    except Exception as exc:  # noqa: BLE001 - cleanup must not replace the real result
        log.error("no se pudo cerrar el borrador de importación: %s", type(exc).__name__)


def confirm(request: Request) -> Respuesta:
    """Write a previously previewed import into a new base."""
    data = parse_json(request.body)
    (token,) = require(data, "token")
    carpeta_id = destination(data, required=False)

    # Checked before the single-use token is spent, so a folder that has
    # vanished can simply be swapped for another without re-reading the file.
    with db.session() as conn, folder_errors():
        repo_carpetas.require_folder(conn, "bases", carpeta_id)

    recordar = data.get("recordar_formato", True) is not False
    # Validated before the single-use token is spent, so a bad name does not
    # use up the preview.
    nombre_pedido = data.get("nombre")
    if nombre_pedido is not None and not isinstance(nombre_pedido, str):
        raise ApiError("El nombre de la base debe ser texto.")
    if isinstance(nombre_pedido, str) and nombre_pedido and not nombre_pedido.strip():
        raise ApiError("El nombre de la base no puede estar vacío.")

    pending = staging.take(token)
    if pending is None:
        raise ApiError("La vista previa expiró. Vuelve a seleccionar el archivo.", 410)

    with _confirmacion(pending):
        nombre = ((nombre_pedido or "").strip() or pending.nombre_sugerido).strip()
        if not nombre:
            raise ApiError("El nombre de la base no puede estar vacío.")
        db.backup()
        with db.session() as conn:
            conn.execute("BEGIN")
            try:
                # Checked again inside the transaction that creates the base:
                # the folder could have been deleted in the moment since.
                try:
                    repo_carpetas.require_folder(conn, "bases", carpeta_id)
                except repo_carpetas.CarpetaNoExisteError:
                    raise ApiError(
                        f"{NO_EXISTE} No se importó nada; vuelve a seleccionar el archivo.", 404
                    ) from None
                base_id = repo_bases.create(
                    conn,
                    repo_bases.unique_name(conn, nombre),
                    pending.archivo,
                    pending.resultado.hoja,
                    data.get("notas"),
                    carpeta_id=carpeta_id,
                )
                repo_terrenos.insert(
                    conn, base_id, pending.resultado.records, pending.incidencias
                )
                recordado = _registrar(conn, pending, base_id, "nueva", recordar)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            respuesta = {"base": repo_bases.get(conn, base_id)}
    if recordado:
        respuesta["formato"] = recordado
    return respuesta


def append(request: Request) -> Respuesta:
    """Add the new rows of a previewed workbook to an existing base."""
    data = parse_json(request.body)
    (token,) = require(data, "token")
    base_id = request.param("id")
    recordar = data.get("recordar_formato", True) is not False
    # Per-row choices for conflicts, keyed by the incoming row index. Parsed
    # before the single-use token is spent, so malformed input does not use it.
    try:
        resoluciones = {int(k): v for k, v in (data.get("resoluciones") or {}).items()}
    except (TypeError, ValueError, AttributeError):
        raise ApiError("Las decisiones sobre conflictos no son válidas.") from None

    pending = staging.take(token)
    if pending is None:
        raise ApiError("La vista previa expiró. Vuelve a seleccionar el archivo.", 410)

    with _confirmacion(pending):
        db.backup()
        with db.session() as conn:
            if repo_bases.get(conn, base_id) is None:
                raise ApiError("La base indicada no existe.", 404)

            decisiones = classify(
                pending.resultado.records, repo_terrenos.dedupe_rows(conn, base_id)
            )
            nuevos, actualizados, omitidos = [], 0, 0

            conn.execute("BEGIN")
            try:
                for decision in decisiones:
                    record = pending.resultado.records[decision.incoming_index]
                    findings = pending.incidencias.get(record.orden, ())
                    eleccion = resoluciones.get(decision.incoming_index)

                    if decision.disposition is Disposition.NUEVA:
                        nuevos.append(record)
                    elif eleccion == "actualizar" and decision.existing_id:
                        repo_terrenos.update_from_record(
                            conn, decision.existing_id, record, findings
                        )
                        actualizados += 1
                    else:
                        omitidos += 1

                if nuevos:
                    repo_terrenos.insert(conn, base_id, nuevos, pending.incidencias)
                recordado = _registrar(conn, pending, base_id, "agregar", recordar)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

            respuesta = {
                "base": repo_bases.get(conn, base_id),
                "agregados": len(nuevos),
                "actualizados": actualizados,
                "omitidos": omitidos,
            }
    if recordado:
        respuesta["formato"] = recordado
    return respuesta
