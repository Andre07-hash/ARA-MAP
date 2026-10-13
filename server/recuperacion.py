"""Read-only verifier and exporter of attachment bytes, for backup and restore.

The database knows which final objects must exist (key, size, SHA-256); the
byte store (server.almacen) holds them. This module compares the two and can
copy the verified bytes to a local directory. It never deletes or modifies
anything in the store or the database: it only calls `leer`, `tamano_de` and
`listar`, and only runs SELECTs on a connection switched to read-only. The
only thing it writes is the export directory the operator names.

The manifest (the contract between whoever snapshots the database and this
verifier) is one JSON object:

    {
      "formato": "ara-map.manifiesto-archivos",   exact text
      "version": 1,                               exact integer
      "creado_en": "2026-10-12T18:00:00+00:00",   ISO-8601, UTC, when it was built
      "finales": [                                one per referenced final object
        {
          "clave": "final/<id>/<nonce>",          archivo_version.clave_final; unique
          "tamano": 12345,                        exact bytes (archivo_version.tamano)
          "sha256": "<64 lowercase hex>",         archivo_version.sha256
          "version_id": "<uuid>",                 archivo_version.id
          "archivo_id": "<uuid>",                 archivo.id
          "inventory_id": "<uuid>",               the terrain
          "tipo": "pdf" | "kmz",                  archivo.tipo; picks the read limit
          "estado": "disponible",                 archivo_version.estado
          "numero": 1,                            version number within the attachment
          "actual": true,                         it is the attachment's current version
          "retirado": false,                      its attachment was retired
          "geometrias": 0,                        geometria rows parsed from this version
          "eventos": 2                            archivo_evento rows naming this version
        }
      ],
      "pendientes": [                             uploads never finalized (staging only)
        {
          "version_id": "<uuid>", "archivo_id": "<uuid>", "inventory_id": "<uuid>",
          "tipo": "pdf" | "kmz", "numero": 2,
          "clave_temporal": "temporal/<id>",
          "tamano_declarado": 12345, "sha256_declarado": "<64 hex>",
          "iniciado_en": "<ISO-8601>",
          "subida_vence_en": "<ISO-8601>",        original deadlines, unchanged
          "completar_antes_de": "<ISO-8601>"
        }
      ]
    }

`finales` holds every archivo_version row with a clave_final, including
superseded versions and versions of retired attachments: history keeps them.
`pendientes` are not errors; after a restore they must be cancelled or
restarted, because their staging bytes are not part of a backup. The verifier
requires `formato`, `version`, `creado_en`, both lists, and in each final
`clave`, `tamano`, `sha256`, `tipo`, `version_id` and `archivo_id`; it ignores
keys it does not know. Original file names are never in a manifest.

An export directory holds `manifiesto.json` and each object at the path of its
key (`final/<id>/<nonce>`).

Restore drill: `--restauracion --cargar-exportacion CARPETA` loads an export
into the (empty, disposable) target store named by --almacen-local or
--almacen-entorno, re-hashing every local copy first and creating each final
key create-only, then verifies the target against the manifest. That is the
one mode that writes, and only to the target store.

Exit codes of the command (scripts/verificar_archivos.py): 0 every referenced
object verified; 1 integrity problems (or the store could not be listed);
2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import secrets
import sys
import tempfile
from collections.abc import Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from . import db
from .almacen import (
    FINAL,
    Almacen,
    AlmacenError,
    AlmacenLocal,
    ClaveInvalidaError,
    ColisionError,
    LimiteExcedidoError,
    Metadato,
    ObjetoAusenteError,
    partes_de_clave,
)
from .archivos import KMZ_MAX, PDF_MAX
from .protocols import DatabaseConnection
from .repo import recuperacion as repo

FORMATO = "ara-map.manifiesto-archivos"
VERSION = 1
PRESUPUESTO = 700_000_000          # decimal bytes the operator plans to retain
NOMBRE_MANIFIESTO = "manifiesto.json"
LIMITES = {"pdf": PDF_MAX, "kmz": KMZ_MAX}
ESTADOS = ("ok", "ausente", "tamano_distinto", "sha_distinto", "ilegible")

SALIDA_OK = 0
SALIDA_INTEGRIDAD = 1
SALIDA_USO = 2

_SHA256 = re.compile(r"[0-9a-f]{64}")
_BLOQUE_LOCAL = 64 * 1024


class ManifiestoInvalidoError(ValueError):
    """The manifest is not the documented format."""


class UsoError(Exception):
    """A usage or configuration problem; its message is shown to the operator."""


# ------------------------------------------------------------------ manifest

def _entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def validar_manifiesto(dato: object) -> dict[str, Any]:
    """The manifest itself once it is known to follow the documented format."""
    if not isinstance(dato, dict) or dato.get("formato") != FORMATO:
        raise ManifiestoInvalidoError("No es un manifiesto de archivos de ARA Map.")
    if dato.get("version") != VERSION:
        raise ManifiestoInvalidoError(f"Versión de manifiesto no admitida; se espera {VERSION}.")
    finales, pendientes = dato.get("finales"), dato.get("pendientes")
    if not isinstance(dato.get("creado_en"), str) or not isinstance(finales, list) \
            or not isinstance(pendientes, list):
        raise ManifiestoInvalidoError("Al manifiesto le faltan campos obligatorios.")
    vistas: set[str] = set()
    for n, entrada in enumerate(finales):
        if not isinstance(entrada, dict):
            raise ManifiestoInvalidoError(f"La entrada final {n} no es un objeto.")
        clave = entrada.get("clave")
        try:
            partes_de_clave(clave, FINAL)
        except ClaveInvalidaError:
            raise ManifiestoInvalidoError(f"La entrada final {n} no tiene una clave válida.") \
                from None
        sha = entrada.get("sha256")
        if not _entero(entrada.get("tamano")) or not isinstance(sha, str) \
                or not _SHA256.fullmatch(sha) or entrada.get("tipo") not in LIMITES \
                or not isinstance(entrada.get("version_id"), str) \
                or not isinstance(entrada.get("archivo_id"), str):
            raise ManifiestoInvalidoError(f"La entrada final {n} está incompleta o mal formada.")
        if clave in vistas:
            raise ManifiestoInvalidoError(f"La entrada final {n} repite una clave.")
        vistas.add(str(clave))
    for n, pendiente in enumerate(pendientes):
        if not isinstance(pendiente, dict) or not isinstance(pendiente.get("version_id"), str):
            raise ManifiestoInvalidoError(f"La entrada pendiente {n} está mal formada.")
    return dato


def construir_manifiesto(conn: DatabaseConnection) -> dict[str, Any]:
    """The manifest of everything this database references, from SELECTs only."""
    finales = repo.finales(conn)
    for entrada in finales:
        entrada["actual"] = bool(entrada["actual"])
        entrada["retirado"] = bool(entrada["retirado"])
    return validar_manifiesto({
        "formato": FORMATO,
        "version": VERSION,
        "creado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finales": finales,
        "pendientes": repo.pendientes(conn),
    })


def cargar_manifiesto(ruta: Path) -> dict[str, Any]:
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return validar_manifiesto(json.load(archivo))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ManifiestoInvalidoError("No se pudo leer el manifiesto como JSON.") from None


@contextmanager
def base_solo_lectura(sqlite: Path | None) -> Iterator[DatabaseConnection]:
    """A connection that cannot write: a SQLite file, or Postgres when None.

    Postgres is the one db.session() already targets (ARA_MAP_DATABASE_URL).
    SQLite goes through the application's own read-only mode, which neither
    migrates nor creates the file.
    """
    if sqlite is None:
        with db.session() as conn:
            repo.solo_lectura(conn)
            yield conn
        return
    if not sqlite.is_file():
        raise UsoError("El archivo SQLite no existe.")
    # ponytail: the app's read-only mode opens the file as immutable, which
    # skips the write-ahead log. A database in use would be read stale, so it
    # is refused; verify a stopped app or a backup copy. Upgrade path: a
    # mode=ro (not immutable) connection helper in server/db.py.
    wal = Path(str(sqlite) + "-wal")
    if wal.is_file() and wal.stat().st_size:
        raise UsoError("La base SQLite está en uso o no se cerró limpia; usa una copia"
                       " de respaldo o detén la aplicación.")
    previo = os.environ.get("ARA_MAP_READ_ONLY")
    os.environ["ARA_MAP_READ_ONLY"] = "1"
    try:
        local = db.connect(sqlite)
    finally:
        if previo is None:
            del os.environ["ARA_MAP_READ_ONLY"]
        else:
            os.environ["ARA_MAP_READ_ONLY"] = previo
    try:
        repo.solo_lectura(local)
        yield local
    finally:
        local.close()


# -------------------------------------------------------------------- verify

class _FalloError(Exception):
    """A store read ended in one of the reported states."""

    def __init__(self, estado: str) -> None:
        super().__init__(estado)
        self.estado = estado


def _bloques(almacen: Almacen, clave: str, limite: int) -> Generator[bytes, None, None]:
    """The object's chunks; any store failure becomes a reported state."""
    try:
        with almacen.leer(clave, limite) as lectura:
            yield from lectura
    except ObjetoAusenteError:
        raise _FalloError("ausente") from None
    except LimiteExcedidoError:
        raise _FalloError("tamano_distinto") from None
    except (AlmacenError, OSError):
        raise _FalloError("ilegible") from None


def _leer_verificando(almacen: Almacen, entrada: Mapping[str, Any],
                      salida: BinaryIO | None = None) -> tuple[str, int]:
    """Stream one final object, checking size and SHA-256.

    Returns its state and the bytes read from the store. The read is bounded
    by the manifest's size and the application's maximum for the type.
    """
    tamano = int(entrada["tamano"])
    limite = max(1, min(tamano, LIMITES[entrada["tipo"]]))
    resumen = hashlib.sha256()
    leidos = 0
    bloques = _bloques(almacen, entrada["clave"], limite)
    try:
        for bloque in bloques:
            leidos += len(bloque)
            if leidos > tamano:
                return "tamano_distinto", leidos
            resumen.update(bloque)
            if salida is not None:
                salida.write(bloque)
    except _FalloError as fallo:
        return fallo.estado, leidos
    finally:
        bloques.close()
    if leidos != tamano:
        return "tamano_distinto", leidos
    return ("ok" if resumen.hexdigest() == entrada["sha256"] else "sha_distinto"), leidos


def _presente(almacen: Almacen, entrada: Mapping[str, Any]) -> str:
    """The state of an object judged by its metadata alone (no bytes read)."""
    try:
        tamano = almacen.tamano_de(entrada["clave"])
    except (AlmacenError, OSError):
        return "ilegible"
    if tamano is None:
        return "ausente"
    return "ok" if tamano == entrada["tamano"] else "tamano_distinto"


def _listar(almacen: Almacen, prefijo: str) -> list[Metadato] | None:
    try:
        return list(almacen.listar(prefijo))
    except (AlmacenError, OSError):
        return None


# -------------------------------------------------------------------- export

def _copia_local(ruta: Path, entrada: Mapping[str, Any]) -> bool | None:
    """Whether the exported copy matches the manifest; None when there is none."""
    if not os.path.lexists(ruta):
        return None
    if ruta.is_symlink() or not ruta.is_file() or ruta.stat().st_size != entrada["tamano"]:
        return False
    resumen = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(_BLOQUE_LOCAL), b""):
            resumen.update(bloque)
    return bool(resumen.hexdigest() == entrada["sha256"])


def _exportar(almacen: Almacen, entrada: Mapping[str, Any],
              destino: Path) -> tuple[str, int, bool | None]:
    """Bring one object into the export directory.

    Returns its state, the bytes read from the store and what the previous
    local copy was (see _copia_local). A matching local copy is trusted after
    re-hashing it, and the store is only asked for the object's size.
    """
    ruta = destino.joinpath(*partes_de_clave(entrada["clave"], FINAL))
    local = _copia_local(ruta, entrada)
    if local:
        return _presente(almacen, entrada), 0, local
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if destino.resolve() not in ruta.parent.resolve().parents:
        raise UsoError("La carpeta de exportación contiene enlaces que salen de ella.")
    descriptor, parcial = tempfile.mkstemp(prefix=".parcial-", dir=ruta.parent)
    try:
        with os.fdopen(descriptor, "wb") as salida:
            estado, leidos = _leer_verificando(almacen, entrada, salida)
            if estado == "ok":
                salida.flush()
                os.fsync(salida.fileno())
        if estado == "ok":
            os.replace(parcial, ruta)       # verified bytes appear atomically
    finally:
        with suppress(FileNotFoundError):
            os.unlink(parcial)
    return estado, leidos, local


def _guardar_manifiesto(manifiesto: Mapping[str, Any], destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    descriptor, parcial = tempfile.mkstemp(prefix=".parcial-", dir=destino)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
            json.dump(manifiesto, salida, ensure_ascii=False, indent=2)
        os.replace(parcial, destino / NOMBRE_MANIFIESTO)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(parcial)


# ---------------------------------------------------------------- restore load

def cargar_exportacion(exportacion: Path, manifiesto: Mapping[str, Any],
                       almacen: Almacen) -> dict[str, Any]:
    """Load an export's verified copies into a restore target store.

    Every local copy is re-hashed against the manifest first; a bad or
    missing copy is reported and not loaded. Final keys are created through
    the store's create-only `copiar` from a scratch staging key: an object
    already at the key is never replaced. If it holds the manifest's exact
    bytes it counts as present; otherwise it is reported as a conflict for
    the operator. Only this call's own scratch staging keys are deleted.
    """
    manifiesto = validar_manifiesto(manifiesto)
    cargados = presentes = 0
    problemas: list[dict[str, Any]] = []
    for entrada in manifiesto["finales"]:
        clave = entrada["clave"]
        ruta = exportacion.joinpath(*partes_de_clave(clave, FINAL))
        if not _copia_local(ruta, entrada):
            problemas.append({"clave": clave, "estado": "copia_local_invalida"})
            continue
        if _leer_verificando(almacen, entrada)[0] == "ok":
            presentes += 1
            continue
        limite = max(1, int(entrada["tamano"]))
        temporal = "temporal/restaurar-" + secrets.token_hex(16)
        try:
            with open(ruta, "rb") as archivo:
                almacen.guardar_temporal(
                    temporal, iter(lambda: archivo.read(_BLOQUE_LOCAL), b""), limite)
            almacen.copiar(temporal, clave, limite)
            cargados += 1
        except ColisionError:
            problemas.append({"clave": clave, "estado": "conflicto_en_destino"})
        except (AlmacenError, OSError) as exc:
            problemas.append({"clave": clave, "estado": getattr(exc, "codigo", "ilegible")})
        finally:
            with suppress(AlmacenError, OSError):
                almacen.borrar(temporal)
    return {"cargados": cargados, "ya_presentes": presentes, "problemas": problemas}


# -------------------------------------------------------------------- report

def verificar(manifiesto: Mapping[str, Any], almacen: Almacen, *,
              presupuesto: int = PRESUPUESTO,
              exportar_a: Path | None = None) -> dict[str, Any]:
    """Check every referenced final object of a manifest against a store.

    One object's failure never stops the run. With `exportar_a`, verified
    objects and the manifest are also written under that directory.
    """
    manifiesto = validar_manifiesto(manifiesto)
    if exportar_a is not None:
        _guardar_manifiesto(manifiesto, exportar_a)
    conteos = dict.fromkeys(ESTADOS, 0)
    problemas: list[dict[str, Any]] = []
    corruptas: list[dict[str, Any]] = []
    leidos_total = reutilizadas = 0
    for entrada in manifiesto["finales"]:
        if exportar_a is None:
            estado, leidos = _leer_verificando(almacen, entrada)
        else:
            estado, leidos, local = _exportar(almacen, entrada, exportar_a)
            reutilizadas += local is True
            if local is False:
                corruptas.append({"clave": entrada["clave"], "reemplazada": estado == "ok"})
        leidos_total += leidos
        conteos[estado] += 1
        if estado != "ok":
            problemas.append({"clave": entrada["clave"], "estado": estado,
                              "version_id": entrada["version_id"],
                              "archivo_id": entrada["archivo_id"], "tipo": entrada["tipo"]})

    referidas = {entrada["clave"] for entrada in manifiesto["finales"]}
    finales, temporales = _listar(almacen, "final/"), _listar(almacen, "temporal/")
    sobrantes: list[dict[str, Any]] = [{"clave": m.clave, "tamano": m.tamano}
                                       for m in finales or () if m.clave not in referidas]
    staging: list[dict[str, Any]] = [{"clave": m.clave, "tamano": m.tamano}
                                     for m in temporales or ()]
    en_staging = {m["clave"] for m in staging}
    pendientes = [{**p, "staging_presente":
                   None if temporales is None else p.get("clave_temporal") in en_staging}
                  for p in manifiesto["pendientes"]]

    referenciados = sum(entrada["tamano"] for entrada in manifiesto["finales"])
    no_referenciados = sum(m["tamano"] for m in sobrantes)
    en_temporal = sum(m["tamano"] for m in staging)
    retenidos = referenciados + no_referenciados + en_temporal
    listado_completo = finales is not None and temporales is not None
    reporte: dict[str, Any] = {
        "modo": "verificacion",
        "manifiesto_creado_en": manifiesto["creado_en"],
        "correcto": not problemas and listado_completo,
        "conteos": conteos,
        "problemas": problemas,
        "listado_completo": listado_completo,
        "no_referenciados": sorted(sobrantes, key=lambda m: m["clave"]),
        "staging": sorted(staging, key=lambda m: m["clave"]),
        "pendientes": pendientes,
        "bytes": {
            "referenciados": referenciados,
            "no_referenciados": no_referenciados,
            "staging": en_temporal,
            "retenidos": retenidos,
            "presupuesto": presupuesto,
            "excede_presupuesto": retenidos > presupuesto,
            "leidos_del_almacen": leidos_total,
        },
    }
    if exportar_a is not None:
        reporte["exportacion"] = {"copias_locales_reutilizadas": reutilizadas,
                                  "copias_locales_corruptas": corruptas}
    return reporte


def verificar_restauracion(manifiesto: Mapping[str, Any], almacen: Almacen, *,
                           presupuesto: int = PRESUPUESTO) -> dict[str, Any]:
    """The same verification, of a restored store against its restored data."""
    return {**verificar(manifiesto, almacen, presupuesto=presupuesto), "modo": "restauracion"}


_ETIQUETAS = {"ok": "correctos", "ausente": "ausentes", "tamano_distinto": "tamaño distinto",
              "sha_distinto": "SHA-256 distinto", "ilegible": "ilegibles"}


def resumen(reporte: Mapping[str, Any]) -> str:
    """The report as Spanish text for the operator."""
    restauracion = reporte["modo"] == "restauracion"
    b = reporte["bytes"]
    lineas = [
        "Verificación de restauración" if restauracion else "Verificación de archivos adjuntos",
        f"Manifiesto creado: {reporte['manifiesto_creado_en']}",
        "Resultado: " + ("CORRECTO" if reporte["correcto"] else "CON PROBLEMAS"),
        "  " + " · ".join(f"{_ETIQUETAS[e]}: {reporte['conteos'][e]}" for e in ESTADOS),
    ]
    lineas += [f"  {_ETIQUETAS[p['estado']]}: {p['clave']} ({p['tipo']}, versión {p['version_id']})"
               for p in reporte["problemas"]]
    if not reporte["listado_completo"]:
        lineas.append("  No se pudo listar el almacén: sobrantes y temporales incompletos.")
    lineas.append(f"Objetos finales sin referencia: {len(reporte['no_referenciados'])}"
                  f" ({b['no_referenciados']} bytes)")
    lineas += [f"  {m['clave']} ({m['tamano']} bytes)" for m in reporte["no_referenciados"]]
    lineas.append(f"Objetos temporales: {len(reporte['staging'])} ({b['staging']} bytes)")
    lineas.append(f"Subidas pendientes: {len(reporte['pendientes'])}"
                  + (" (no son error; tras restaurar hay que cancelarlas o reiniciarlas)"
                     if reporte["pendientes"] else ""))
    for p in reporte["pendientes"]:
        temporal = {True: "con temporal", False: "sin temporal",
                    None: "temporal sin comprobar"}[p["staging_presente"]]
        lineas.append(f"  versión {p['version_id']} ({p.get('tipo')}), completar antes de"
                      f" {p.get('completar_antes_de')}, {temporal}")
    lineas.append(f"Bytes referenciados: {b['referenciados']}; retenidos en total:"
                  f" {b['retenidos']} de un presupuesto de {b['presupuesto']}"
                  + (" (EXCEDE el presupuesto)" if b["excede_presupuesto"] else " (dentro)"))
    lineas.append(f"Bytes leídos del almacén: {b['leidos_del_almacen']}")
    carga = reporte.get("carga")
    if carga is not None:
        lineas.append(f"Carga en el destino: {carga['cargados']} cargados,"
                      f" {carga['ya_presentes']} ya presentes, {len(carga['problemas'])} con problemas")
        lineas += [f"  {p['estado']}: {p['clave']}" for p in carga["problemas"]]
    exportacion = reporte.get("exportacion")
    if exportacion is not None:
        lineas.append(f"Exportación: {exportacion['copias_locales_reutilizadas']} copias locales"
                      f" reutilizadas, {len(exportacion['copias_locales_corruptas'])} corruptas")
        lineas += [f"  copia local corrupta: {c['clave']}"
                   + (" (reemplazada)" if c["reemplazada"] else " (NO reemplazada)")
                   for c in exportacion["copias_locales_corruptas"]]
    return "\n".join(lineas)


# ----------------------------------------------------------------------- CLI

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verifica (sin modificar nada) que el almacén tenga los archivos adjuntos"
                    " que la base de datos referencia, y opcionalmente los exporta.",
        epilog="Códigos de salida: 0 todo verificado; 1 problemas de integridad;"
               " 2 error de uso o de configuración.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--sqlite", metavar="RUTA", help="base SQLite (se abre sólo lectura)")
    origen.add_argument("--url-env", metavar="VARIABLE",
                        help="variable de entorno con la URL de Postgres (nunca la URL misma)")
    origen.add_argument("--manifiesto", metavar="ARCHIVO",
                        help="manifiesto JSON generado antes, en lugar de una base")
    almacen = parser.add_mutually_exclusive_group(required=True)
    almacen.add_argument("--almacen-local", metavar="CARPETA",
                         help="almacén de archivos en una carpeta local")
    almacen.add_argument("--almacen-entorno", action="store_true",
                         help="almacén remoto configurado con variables de entorno")
    parser.add_argument("--exportar", metavar="CARPETA",
                        help="copia ahí cada objeto verificado y el manifiesto (incremental)")
    parser.add_argument("--restauracion", action="store_true",
                        help="el almacén es el destino de una restauración")
    parser.add_argument("--cargar-exportacion", metavar="CARPETA",
                        help="con --restauracion: antes de verificar, carga en el almacén"
                             " destino las copias verificadas de esa exportación (nunca"
                             " reemplaza un objeto existente)")
    parser.add_argument("--presupuesto", metavar="BYTES", type=int, default=PRESUPUESTO,
                        help=f"bytes que se planea retener (por omisión {PRESUPUESTO})")
    parser.add_argument("--json", action="store_true", help="reporte en JSON")
    return parser


def _manifiesto_de(args: argparse.Namespace) -> dict[str, Any]:
    if args.manifiesto:
        return cargar_manifiesto(Path(args.manifiesto))
    if args.url_env:
        url = os.environ.get(args.url_env)
        if not url:
            raise UsoError(f"{args.url_env} no está definida; no se usa ningún destino"
                           " por omisión.")
        os.environ["ARA_MAP_DATABASE_URL"] = url
        sqlite = None
    else:
        sqlite = Path(args.sqlite).expanduser().resolve()
    try:
        with base_solo_lectura(sqlite) as conn:
            return construir_manifiesto(conn)
    except (UsoError, ManifiestoInvalidoError):
        raise
    except Exception as exc:        # never echo a driver message: it may carry the URL
        raise UsoError("No se pudo leer la base de datos"
                       f" ({type(exc).__name__}); ¿está en el esquema actual?") from None


def _almacen_de(args: argparse.Namespace) -> Almacen:
    if args.almacen_local:
        try:
            return AlmacenLocal(Path(args.almacen_local).expanduser())
        except AlmacenError as exc:
            raise UsoError(str(exc)) from None
    try:
        modulo = importlib.import_module("server.almacen_supabase")
    except ImportError:
        raise UsoError("Esta versión no incluye el almacén remoto"
                       " (server.almacen_supabase).") from None
    fabrica = modulo.fabrica_desde_entorno(os.environ)
    if fabrica is None:
        raise UsoError("El almacén remoto no está configurado en las variables de entorno.")
    try:
        almacen: Almacen = fabrica()         # the factory, not the store, came back
    except AlmacenError as exc:              # e.g. the SDK is not installed
        raise UsoError(f"No se pudo preparar el almacén remoto ({exc.codigo}).") from None
    return almacen


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.restauracion and args.exportar:
        parser.error("--restauracion no se combina con --exportar")
    if args.cargar_exportacion and not args.restauracion:
        parser.error("--cargar-exportacion requiere --restauracion")
    if args.presupuesto < 0:
        parser.error("--presupuesto no puede ser negativo")
    try:
        manifiesto = _manifiesto_de(args)
        almacen = _almacen_de(args)
        if args.restauracion:
            carga = None
            if args.cargar_exportacion:
                carga = cargar_exportacion(Path(args.cargar_exportacion).expanduser(),
                                           manifiesto, almacen)
            reporte = verificar_restauracion(manifiesto, almacen, presupuesto=args.presupuesto)
            if carga is not None:
                reporte["carga"] = carga
                reporte["correcto"] = reporte["correcto"] and not carga["problemas"]
        else:
            reporte = verificar(
                manifiesto, almacen, presupuesto=args.presupuesto,
                exportar_a=Path(args.exportar).expanduser() if args.exportar else None)
    except (UsoError, ManifiestoInvalidoError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return SALIDA_USO
    except OSError as exc:          # the export directory: full disk, permissions
        print(f"Error al escribir la exportación ({type(exc).__name__}).", file=sys.stderr)
        return SALIDA_USO
    print(json.dumps(reporte, ensure_ascii=False, indent=2) if args.json else resumen(reporte))
    return SALIDA_OK if reporte["correcto"] else SALIDA_INTEGRIDAD
