"""Authorized attachment lifecycle over the accepted database and byte store.

This is a domain service, not an HTTP handler.  It accepts a real
``auth.Sesion`` and keeps storage and KMZ parsing outside write transactions.
Every transaction that mutates attachment state revalidates the session and
terrain scope before taking attachment locks or writing a row.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Union, cast

from . import auth, db
from .almacen import Almacen, AlmacenError, LimiteExcedidoError, ObjetoAusenteError
from .errors import ApiError
from .kmz import procesar_kmz
from .protocols import DatabaseConnection
from .repo import archivos as repo

PDF_MAX = 25 * 1024 * 1024
KMZ_MAX = 20 * 1024 * 1024
UPLOAD_SECONDS = 15 * 60
COMPLETE_SECONDS = 60 * 60
LEASE_SECONDS = 180
PENDING_MAX = 5
HISTORY_DEFAULT = 50
HISTORY_MAX = 100
ANALYZER = "server.kmz/v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

Clock = Callable[[], Union[datetime, str]]
Processor = Callable[[bytes, object], dict[str, Any]]


def _error(code: str, message: str, status: int = 400,
           **detail: Any) -> ApiError:
    return ApiError(message, status, {"code": code, **detail})


def _not_found() -> ApiError:
    return _error("not_found", "El archivo no existe.", 404)


def _conflict(code: str, message: str, **detail: Any) -> ApiError:
    return _error(code, message, 409, **detail)


def _now(clock: Clock | None) -> str:
    value: datetime | str = clock() if clock else datetime.now(timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TypeError("reloj must return datetime or ISO text")
    if parsed.tzinfo is None:
        raise ValueError("reloj must return a timezone-aware value")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _after(now: str, seconds: int) -> str:
    return (datetime.fromisoformat(now) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _request(session: auth.Sesion) -> Any:
    return SimpleNamespace(sesion=session)


def _valid_session(session: object) -> auth.Sesion:
    if not isinstance(session, auth.Sesion):
        raise auth.no_autenticado()
    return session


def _authorize_read(session: auth.Sesion, terrain_id: str, capability: str,
                    database: Path | str | None) -> auth.Alcance:
    with db.session(database) as conn:
        return auth.require_terreno(_request(session), terrain_id, capability, conn)


def _resource_version(version_id: str, database: Path | str | None) -> dict[str, Any]:
    with db.session(database) as conn:
        resource = repo.resource_for_version(conn, version_id)
    if resource is None:
        raise _not_found()
    return resource


def _resource_attachment(attachment_id: str,
                         database: Path | str | None) -> dict[str, Any]:
    with db.session(database) as conn:
        resource = repo.resource_for_attachment(conn, attachment_id)
    if resource is None:
        raise _not_found()
    return resource


def _hash_payload(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _key(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise _error("idempotencia_invalida", "La clave de idempotencia no es válida.")
    return value


def _operation(conn: DatabaseConnection, operation: str, key: str,
               request_hash: str) -> dict[str, Any] | None:
    saved = repo.operation_result(conn, operation, key)
    if saved is None:
        return None
    if saved["request_hash"] != request_hash:
        raise _conflict("idempotencia_conflictiva",
                        "La clave de idempotencia ya se usó con otros datos.")
    return cast(dict[str, Any], saved["result"])


def _safe_name(value: object) -> str:
    if not isinstance(value, str):
        raise _error("nombre_invalido", "El nombre del archivo no es válido.")
    name = value.strip()
    if (not name or len(name) > 255 or name in (".", "..") or "/" in name
            or "\\" in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise _error("nombre_invalido", "El nombre del archivo no es válido.")
    return name


def _size(value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise _error("tamano_invalido", "El tamaño declarado no es válido.",
                     limite=maximum)
    return value


def _digest(value: object) -> str:
    digest = str(value or "").lower()
    if not _SHA256.fullmatch(digest):
        raise _error("sha256_invalido", "El SHA-256 declarado no es válido.")
    return digest


def _kind(value: object) -> tuple[str, int]:
    if value == "pdf":
        return "pdf", PDF_MAX
    if value == "kmz":
        return "kmz", KMZ_MAX
    raise _error("tipo_invalido", "El tipo debe ser pdf o kmz.")


def _hook(hooks: object | None, name: str, *args: Any) -> None:
    callback = getattr(hooks, name, None)
    if callback is not None:
        callback(*args)


def iniciar(sesion: auth.Sesion, terreno_id: str, *, tipo: str,
            nombre_original: str, tamano_declarado: int,
            sha256_declarado: str, idempotency_key: str,
            bd: Path | str | None = None, reloj: Clock | None = None) -> dict[str, Any]:
    """Authorize an upload and create its immutable pending version."""
    _valid_session(sesion)
    kind, maximum = _kind(tipo)
    name = _safe_name(nombre_original)
    size = _size(tamano_declarado, maximum)
    digest = _digest(sha256_declarado)
    key = _key(idempotency_key)
    now = _now(reloj)
    payload = {"tipo": kind, "nombre_original": name, "tamano_declarado": size,
               "sha256_declarado": digest}
    request_hash = _hash_payload(payload)
    _authorize_read(sesion, terreno_id, "archivos.subir", bd)
    operation = f"archivos.iniciar:{sesion.user_id}:{terreno_id}"
    with db.escritura(bd) as conn:
        scope = auth.reverificar_terreno(conn, sesion, terreno_id, "archivos.subir")
        replay = _operation(conn, operation, key, request_hash)
        if replay is not None:
            return replay
        if repo.effective_pending_count(conn, sesion.user_id, now) >= PENDING_MAX:
            raise _conflict("limite_pendientes",
                            "Ya hay demasiadas subidas pendientes para esta cuenta.",
                            limite=PENDING_MAX)
        attachment_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        result = repo.start_upload(
            conn, terrain_id=terreno_id, kind=kind, attachment_id=attachment_id,
            version_id=version_id, temporary_key=f"temporal/{uuid.uuid4().hex}",
            original_name=name, declared_size=size, declared_sha256=digest,
            upload_expires_at=_after(now, UPLOAD_SECONDS),
            complete_before=_after(now, COMPLETE_SECONDS), now=now,
            actor=scope.actor, base_id=scope.base_id)
        repo.save_operation_result(conn, operation, key, request_hash,
                                   sesion.user_id, now, result)
        return result


def escribir_temporal(sesion: auth.Sesion, version_id: str,
                      bloques: Iterable[bytes | bytearray | memoryview],
                      almacen: Almacen, *, bd: Path | str | None = None,
                      reloj: Clock | None = None) -> dict[str, Any]:
    """Stream bytes into replaceable staging before its 15-minute deadline."""
    _valid_session(sesion)
    now = _now(reloj)
    resource = _resource_version(version_id, bd)
    _authorize_read(sesion, str(resource["inventory_id"]), "archivos.subir", bd)
    if resource["iniciado_por"] != sesion.user_id:
        raise _not_found()
    if resource["estado"] != "subiendo":
        raise _conflict("subida_no_pendiente", "La subida ya no está pendiente.")
    if resource["subida_vence_en"] <= now:
        raise _conflict("subida_expirada", "El plazo para subir contenido terminó.")
    maximum = PDF_MAX if resource["archivo_tipo"] == "pdf" else KMZ_MAX
    try:
        written = almacen.guardar_temporal(str(resource["clave_temporal"]), bloques, maximum)
    except LimiteExcedidoError as exc:
        raise _error("tamano_excedido", "El archivo supera el tamaño permitido.",
                     413, limite=maximum) from exc
    except AlmacenError as exc:
        raise _error("almacen_no_disponible", "No fue posible guardar el archivo.", 503,
                     reintentar=True) from exc
    except (TypeError, ValueError) as exc:
        raise _error("bloque_invalido", "Los bloques de la subida no son válidos.") from exc
    current = _resource_version(version_id, bd)
    _authorize_read(sesion, str(current["inventory_id"]), "archivos.subir", bd)
    if (current["iniciado_por"] != sesion.user_id or current["estado"] != "subiendo"
            or current["subida_vence_en"] <= _now(reloj)):
        raise _conflict("subida_no_pendiente",
                        "La subida cambió mientras se guardaba el contenido.")
    return {"version_id": version_id, "bytes_recibidos": written,
            "estado": "subiendo"}


def _acquire_completion(sesion: auth.Sesion, version_id: str,
                        database: Path | str | None, now: str,
                        work_id: str) -> dict[str, Any]:
    with db.escritura(database) as conn:
        resource = repo.resource_for_version(conn, version_id)
        if resource is None:
            raise _not_found()
        scope = auth.reverificar_terreno(conn, sesion, str(resource["inventory_id"]),
                                         "archivos.subir")
        resource = repo.resource_for_version(conn, version_id, lock=True)
        assert resource is not None
        if resource["iniciado_por"] != sesion.user_id:
            raise _not_found()
        if resource["estado"] in ("disponible", "fallido"):
            return {"replay": repo.completion_result(conn, version_id)}
        if resource["estado"] != "subiendo":
            raise _conflict("subida_no_pendiente", "La subida ya no puede completarse.")
        if resource["completar_antes_de"] <= now:
            repo.expire_pending(conn, resource=resource, now=now, actor=scope.actor,
                                base_id=scope.base_id)
            return {"expired": True}
        leased = repo.lease(conn, version_id=version_id, work_id=work_id,
                            actor_id=sesion.user_id, operation="completar", started_at=now,
                            expires_at=_after(now, LEASE_SECONDS), now=now)
        if not leased["acquired"]:
            raise _conflict("procesamiento_en_curso",
                            "El archivo ya se está procesando.", reintentar=True,
                            reintentar_despues_de=leased["expires_at"])
        return {"resource": resource}


def _release_lease(sesion: auth.Sesion, version_id: str, terrain_id: str,
                   work_id: str, database: Path | str | None) -> None:
    try:
        with db.escritura(database) as conn:
            auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
            current = repo.resource_for_version(conn, version_id, lock=True)
            if current is not None:
                repo.release_lease(conn, version_id, work_id)
    except Exception:
        # A lost scope must not mutate the resource. The short lease expires.
        return


def _verify_final(almacen: Almacen, final_key: str, maximum: int,
                  kind: str) -> tuple[int, str, str, bytes | None]:
    digest = hashlib.sha256()
    total = 0
    prefix = bytearray()
    kmz = bytearray() if kind == "kmz" else None
    with almacen.leer(final_key, maximum) as reading:
        for chunk in reading:
            total += len(chunk)
            digest.update(chunk)
            if len(prefix) < 8:
                prefix.extend(chunk[:8 - len(prefix)])
            if kmz is not None:
                kmz.extend(chunk)
    if kind == "pdf":
        if not bytes(prefix).startswith(b"%PDF-"):
            raise _error("firma_invalida", "El contenido no es un PDF válido.")
        detected = "application/pdf"
    else:
        if not bytes(prefix).startswith(b"PK\x03\x04"):
            raise _error("firma_invalida", "El contenido no es un KMZ válido.")
        detected = "application/vnd.google-earth.kmz"
    return total, digest.hexdigest(), detected, bytes(kmz) if kmz is not None else None


def _attempt(result: Mapping[str, Any], selection: Sequence[int] | None = None
             ) -> tuple[dict[str, Any], dict[str, Any] | None]:
    outcome = str(result.get("estado"))
    if outcome not in ("listo", "requiere_seleccion", "rechazado", "error_interno"):
        outcome = "error_interno"
        result = {"estado": outcome, "error": {"codigo": "RESULTADO_INVALIDO",
                  "mensaje": "El analizador devolvió un resultado no válido."}}
    detail = {k: v for k, v in result.items() if k != "geometria"}
    attempt_id = str(uuid.uuid4())
    attempt = {"id": attempt_id, "selection": list(selection) if selection is not None
               else result.get("seleccion"), "outcome": outcome, "detail": detail,
               "analyzer": ANALYZER}
    source = result.get("geometria")
    if outcome != "listo" or not isinstance(source, Mapping):
        return attempt, None
    geojson = json.dumps(source["geojson"], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    encoded = geojson.encode("utf-8")
    geometry = {"id": str(uuid.uuid4()), "geojson": geojson,
                "bbox": list(source["bbox"]),
                "point": list(source["punto_interior"]["coordinates"]),
                "parts": source["partes"], "holes": source["huecos"],
                "vertices": source["vertices"], "area": source.get("area_aproximada_m2"),
                "usable": bool((result.get("ubicacion") or {}).get("utilizable")),
                "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
    return attempt, geometry


def _delete_if_unreferenced(key: str, almacen: Almacen,
                            database: Path | str | None) -> bool:
    try:
        with db.session(database) as conn:
            referenced = repo.final_key_referenced(conn, key)
    except Exception:
        return False
    if referenced:
        return False
    try:
        return almacen.borrar(key)
    except AlmacenError:
        return False


def completar(sesion: auth.Sesion, version_id: str, almacen: Almacen, *,
              bd: Path | str | None = None, reloj: Clock | None = None,
              procesador: Processor = procesar_kmz,
              ganchos: object | None = None) -> dict[str, Any]:
    """Finalize, verify and optionally parse one pending upload."""
    _valid_session(sesion)
    resource = _resource_version(version_id, bd)
    _authorize_read(sesion, str(resource["inventory_id"]), "archivos.subir", bd)
    if resource["iniciado_por"] != sesion.user_id:
        raise _not_found()
    work_id = str(uuid.uuid4())
    acquired = _acquire_completion(sesion, version_id, bd, _now(reloj), work_id)
    if "expired" in acquired:
        raise _conflict("subida_expirada", "El plazo para completar la subida terminó.")
    if "replay" in acquired:
        result = cast(dict[str, Any], acquired["replay"])
        result["replay"] = True
        return result
    resource = acquired["resource"]
    terrain_id = str(resource["inventory_id"])
    _hook(ganchos, "despues_lease", version_id)
    maximum = PDF_MAX if resource["archivo_tipo"] == "pdf" else KMZ_MAX
    final_key = f"final/{version_id.replace('-', '')[:64]}/{uuid.uuid4().hex}"
    copied = False
    verification: ApiError | None
    try:
        almacen.copiar(str(resource["clave_temporal"]), final_key, maximum)
        copied = True
        _hook(ganchos, "despues_copia", version_id)
        actual, digest, detected, body = _verify_final(
            almacen, final_key, maximum, str(resource["archivo_tipo"]))
    except ObjetoAusenteError as exc:
        _release_lease(sesion, version_id, terrain_id, work_id, bd)
        if copied:
            raise _error("almacen_no_disponible", "El archivo final desapareció.", 503,
                         reintentar=True) from exc
        raise _conflict("contenido_temporal_ausente",
                        "No se encontró el contenido temporal; vuelve a subirlo.") from exc
    except LimiteExcedidoError:
        verification = _error("tamano_excedido", "El archivo supera el tamaño permitido.",
                              413, limite=maximum)
        actual = -1
        digest = ""
        detected = ""
        body = None
    except ApiError as exc:
        verification = exc
    except AlmacenError as exc:
        _release_lease(sesion, version_id, terrain_id, work_id, bd)
        if copied:
            _delete_if_unreferenced(final_key, almacen, bd)
        raise _error("almacen_no_disponible", "No fue posible verificar el archivo.", 503,
                     reintentar=True) from exc
    else:
        verification = None
        if actual != int(resource["tamano_declarado"]):
            verification = _error("tamano_no_coincide",
                                  "El tamaño recibido no coincide con el declarado.")
        elif digest != resource["sha256_declarado"]:
            verification = _error("sha256_no_coincide",
                                  "El SHA-256 recibido no coincide con el declarado.")

    if verification is not None:
        try:
            now = _now(reloj)
            with db.escritura(bd) as conn:
                scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
                current = repo.resource_for_version(conn, version_id, lock=True)
                if current is None or not repo.lease_owned(conn, version_id, work_id, now):
                    raise _conflict("lease_perdido", "El turno de procesamiento terminó.")
                result = repo.finish_failed(conn, resource=current, work_id=work_id,
                                            error_code=verification.detalle["code"],
                                            error_message=verification.mensaje, now=now,
                                            actor=scope.actor, base_id=scope.base_id)
        except Exception:
            if copied:
                _delete_if_unreferenced(final_key, almacen, bd)
            raise
        if copied:
            _delete_if_unreferenced(final_key, almacen, bd)
        result["replay"] = False
        return result

    attempt = geometry = None
    if resource["archivo_tipo"] == "kmz":
        assert body is not None
        try:
            parsed = procesador(body, None)
        except MemoryError:
            raise
        except Exception:
            parsed = {"estado": "error_interno", "error": {
                "codigo": "ANALIZADOR_FALLO",
                "mensaje": "No fue posible analizar el KMZ."}}
        attempt, geometry = _attempt(parsed)
        _hook(ganchos, "despues_parseo", version_id)
    _hook(ganchos, "antes_commit", version_id)
    try:
        now = _now(reloj)
        with db.escritura(bd) as conn:
            scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
            current = repo.resource_for_version(conn, version_id, lock=True)
            if (current is None or current["estado"] != "subiendo"
                    or not repo.lease_owned(conn, version_id, work_id, now)):
                raise _conflict("lease_perdido", "El turno de procesamiento terminó.")
            result = repo.finish_available(
                conn, resource=current, work_id=work_id, final_key=final_key,
                actual_size=actual, sha256=digest, detected_type=detected, now=now,
                actor=scope.actor, base_id=scope.base_id, attempt=attempt,
                geometry=geometry)
    except Exception:
        _delete_if_unreferenced(final_key, almacen, bd)
        raise
    _hook(ganchos, "despues_commit", version_id)
    cleanup_pending = False
    try:
        almacen.borrar(str(resource["clave_temporal"]))
    except AlmacenError:
        cleanup_pending = True
    result["replay"] = False
    result["limpieza_pendiente"] = cleanup_pending
    return result


def cancelar(sesion: auth.Sesion, version_id: str, almacen: Almacen | None = None, *,
             bd: Path | str | None = None, reloj: Clock | None = None) -> dict[str, Any]:
    _valid_session(sesion)
    resource = _resource_version(version_id, bd)
    _authorize_read(sesion, str(resource["inventory_id"]), "archivos.subir", bd)
    now = _now(reloj)
    with db.escritura(bd) as conn:
        current = repo.resource_for_version(conn, version_id)
        if current is None:
            raise _not_found()
        scope = auth.reverificar_terreno(conn, sesion, str(current["inventory_id"]),
                                         "archivos.subir")
        current = repo.resource_for_version(conn, version_id, lock=True)
        assert current is not None
        if current["iniciado_por"] != sesion.user_id and scope.rol != "admin":
            raise _not_found()
        if not repo.cancel_pending(conn, resource=current, now=now, actor=scope.actor,
                                   base_id=scope.base_id):
            raise _conflict("subida_no_pendiente", "La subida ya no está pendiente.")
        result: dict[str, Any] = {"version_id": version_id, "estado": "cancelado"}
        temporary_key = str(current["clave_temporal"])
    cleanup_pending = False
    if almacen is not None:
        try:
            almacen.borrar(temporary_key)
        except AlmacenError:
            cleanup_pending = True
    result["limpieza_pendiente"] = cleanup_pending
    return result


def reprocesar(sesion: auth.Sesion, version_id: str, almacen: Almacen, *,
               seleccion: Sequence[int] | None = None, idempotency_key: str,
               bd: Path | str | None = None, reloj: Clock | None = None,
               procesador: Processor = procesar_kmz,
               ganchos: object | None = None) -> dict[str, Any]:
    _valid_session(sesion)
    key = _key(idempotency_key)
    normalized = list(seleccion) if seleccion is not None else None
    request_hash = _hash_payload({"seleccion": normalized})
    resource = _resource_version(version_id, bd)
    terrain_id = str(resource["inventory_id"])
    _authorize_read(sesion, terrain_id, "archivos.subir", bd)
    operation = f"archivos.procesar:{sesion.user_id}:{version_id}"
    work_id = str(uuid.uuid4())
    now = _now(reloj)
    with db.escritura(bd) as conn:
        scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
        current = repo.resource_for_version(conn, version_id, lock=True)
        if current is None:
            raise _not_found()
        replay = _operation(conn, operation, key, request_hash)
        if replay is not None:
            replay["replay"] = True
            return replay
        if current["archivo_tipo"] != "kmz" or current["estado"] != "disponible":
            raise _conflict("version_no_procesable", "La versión no se puede procesar.")
        leased = repo.lease(conn, version_id=version_id, work_id=work_id,
                            actor_id=sesion.user_id, operation="procesar", started_at=now,
                            expires_at=_after(now, LEASE_SECONDS), now=now)
        if not leased["acquired"]:
            raise _conflict("procesamiento_en_curso", "El archivo ya se está procesando.",
                            reintentar=True, reintentar_despues_de=leased["expires_at"])
        final_key = str(current["clave_final"])
    _hook(ganchos, "despues_lease", version_id)
    try:
        actual, digest, _, body = _verify_final(almacen, final_key, KMZ_MAX, "kmz")
        assert body is not None
    except AlmacenError as exc:
        _release_lease(sesion, version_id, terrain_id, work_id, bd)
        raise _error("almacen_no_disponible", "No fue posible leer el archivo.", 503,
                     reintentar=True) from exc
    except ApiError:
        _release_lease(sesion, version_id, terrain_id, work_id, bd)
        raise
    if actual != resource["tamano"] or digest != resource["sha256"]:
        _release_lease(sesion, version_id, terrain_id, work_id, bd)
        raise _error("objeto_final_inconsistente",
                     "El archivo final no coincide con la versión registrada.", 503,
                     reintentar=True)
    try:
        parsed = procesador(body, normalized)
        attempt, geometry = _attempt(parsed, normalized)
        _hook(ganchos, "despues_parseo", version_id)
    except MemoryError:
        raise
    except Exception:
        attempt, geometry = _attempt({"estado": "error_interno", "error": {
            "codigo": "ANALIZADOR_FALLO", "mensaje": "No fue posible analizar el KMZ."}},
            normalized)
    now = _now(reloj)
    with db.escritura(bd) as conn:
        scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
        current = repo.resource_for_version(conn, version_id, lock=True)
        if current is None or current["estado"] != "disponible":
            raise _conflict("version_no_procesable", "La versión ya no se puede procesar.")
        attempt_dto = repo.insert_processing_attempt(
            conn, resource=current, work_id=work_id,
            origin="seleccion" if normalized is not None else "reintento",
            attempt=attempt, geometry=geometry, now=now, actor=scope.actor,
            base_id=scope.base_id)
        result = {"version_id": version_id, "intento": attempt_dto,
                  "geometria_id": geometry["id"] if geometry else None,
                  "archivo": repo.attachment_dto(current), "replay": False}
        repo.save_operation_result(conn, operation, key, request_hash,
                                   sesion.user_id, now, result)
        return result


def activar(sesion: auth.Sesion, archivo_id: str, *, version_id: str,
            expected_revision: int, idempotency_key: str,
            geometria_id: str | None = None, bd: Path | str | None = None,
            reloj: Clock | None = None) -> dict[str, Any]:
    _valid_session(sesion)
    key = _key(idempotency_key)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise _error("revision_invalida", "La revisión esperada no es válida.")
    payload = {"version_id": version_id, "geometria_id": geometria_id,
               "expected_revision": expected_revision}
    request_hash = _hash_payload(payload)
    attachment = _resource_attachment(archivo_id, bd)
    terrain_id = str(attachment["inventory_id"])
    _authorize_read(sesion, terrain_id, "archivos.subir", bd)
    operation = f"archivos.activar:{sesion.user_id}:{archivo_id}"
    now = _now(reloj)
    with db.escritura(bd) as conn:
        scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.subir")
        current = repo.resource_for_attachment(conn, archivo_id, lock=True)
        if current is None:
            raise _not_found()
        replay = _operation(conn, operation, key, request_hash)
        if replay is not None:
            replay["replay"] = True
            return replay
        work_id = str(uuid.uuid4())
        leased = repo.lease(conn, version_id=version_id, work_id=work_id,
                            actor_id=sesion.user_id, operation="activar", started_at=now,
                            expires_at=_after(now, LEASE_SECONDS), now=now)
        if not leased["acquired"]:
            raise _conflict("procesamiento_en_curso", "La versión está en uso.",
                            reintentar=True, reintentar_despues_de=leased["expires_at"])
        try:
            updated = repo.activate(conn, attachment=current, version_id=version_id,
                                    geometry_id=geometria_id,
                                    expected_revision=expected_revision, now=now,
                                    actor=scope.actor, base_id=scope.base_id)
        except repo.ConflictError as exc:
            raise _conflict("revision_conflictiva",
                            "La decisión cambió; vuelve a cargar el archivo.") from exc
        except ValueError as exc:
            raise _conflict("version_no_activable",
                            "La versión o geometría no se puede activar.") from exc
        if not repo.release_lease(conn, version_id, work_id):
            raise _conflict("lease_perdido", "El turno de activación terminó.")
        result = {"archivo": updated, "replay": False}
        repo.save_operation_result(conn, operation, key, request_hash,
                                   sesion.user_id, now, result)
        return result


def retirar(sesion: auth.Sesion, archivo_id: str, *, expected_revision: int,
            idempotency_key: str, almacen: Almacen | None = None,
            bd: Path | str | None = None, reloj: Clock | None = None) -> dict[str, Any]:
    _valid_session(sesion)
    key = _key(idempotency_key)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise _error("revision_invalida", "La revisión esperada no es válida.")
    request_hash = _hash_payload({"expected_revision": expected_revision})
    attachment = _resource_attachment(archivo_id, bd)
    terrain_id = str(attachment["inventory_id"])
    _authorize_read(sesion, terrain_id, "archivos.retirar", bd)
    operation = f"archivos.retirar:{sesion.user_id}:{archivo_id}"
    now = _now(reloj)
    with db.escritura(bd) as conn:
        scope = auth.reverificar_terreno(conn, sesion, terrain_id, "archivos.retirar")
        current = repo.resource_for_attachment(conn, archivo_id, lock=True)
        if current is None:
            raise _not_found()
        replay = _operation(conn, operation, key, request_hash)
        if replay is not None:
            replay["replay"] = True
            return replay
        try:
            updated, temporary_keys = repo.retire(
                conn, attachment=current, expected_revision=expected_revision, now=now,
                actor=scope.actor, base_id=scope.base_id)
        except repo.ConflictError as exc:
            raise _conflict("revision_conflictiva",
                            "La decisión cambió; vuelve a cargar el archivo.") from exc
        result = {"archivo": updated, "replay": False, "limpieza_pendiente": False}
        repo.save_operation_result(conn, operation, key, request_hash,
                                   sesion.user_id, now, result)
    if almacen is not None:
        for temporary_key in temporary_keys:
            try:
                almacen.borrar(temporary_key)
            except AlmacenError:
                result["limpieza_pendiente"] = True
    return result


def listar(sesion: auth.Sesion, terreno_id: str, *, bd: Path | str | None = None,
           reloj: Clock | None = None) -> list[dict[str, Any]]:
    _valid_session(sesion)
    _authorize_read(sesion, terreno_id, "archivos.ver", bd)
    with db.session(bd) as conn:
        auth.require_terreno(_request(sesion), terreno_id, "archivos.ver", conn)
        return repo.list_for_terrain(conn, terreno_id, sesion.user_id, _now(reloj))


def historial(sesion: auth.Sesion, archivo_id: str, *, cursor: str | None = None,
              limite: int = HISTORY_DEFAULT,
              bd: Path | str | None = None) -> dict[str, Any]:
    _valid_session(sesion)
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= HISTORY_MAX:
        raise _error("limite_invalido", f"El límite debe estar entre 1 y {HISTORY_MAX}.")
    attachment = _resource_attachment(archivo_id, bd)
    terrain_id = str(attachment["inventory_id"])
    _authorize_read(sesion, terrain_id, "archivos.ver", bd)
    parsed = None
    if cursor is not None:
        try:
            at, event_id = cursor.split("|", 1)
            datetime.fromisoformat(at)
            uuid.UUID(event_id)
            parsed = (at, event_id)
        except (ValueError, AttributeError):
            raise _error("cursor_invalido", "El cursor no es válido.") from None
    with db.session(bd) as conn:
        auth.require_terreno(_request(sesion), terrain_id, "archivos.ver", conn)
        events, following = repo.history(conn, archivo_id, parsed, limite)
        return {"eventos": events, "cursor_siguiente": following}


def resumenes_de_archivos(conn: DatabaseConnection, inventory_ids: Sequence[str],
                          sesion: auth.Sesion, *,
                          reloj: Clock | None = None) -> dict[str, Any]:
    """Reserved bounded batch hook for a later terrain-list handler."""
    _valid_session(sesion)
    authorized: list[str] = []
    unavailable: list[str] = []
    seen: set[str] = set()
    for terrain_id in inventory_ids:
        if terrain_id in seen:
            continue
        seen.add(terrain_id)
        try:
            auth.require_terreno(_request(sesion), terrain_id, "archivos.ver", conn)
        except ApiError as exc:
            if exc.status == 404:
                unavailable.append(terrain_id)
                continue
            raise
        authorized.append(terrain_id)
    return {"resultados": repo.summaries(conn, authorized, sesion.user_id, _now(reloj)),
            "no_disponibles": unavailable}
