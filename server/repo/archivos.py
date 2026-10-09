"""SQL repository for the attachment lifecycle.

The service in :mod:`server.archivos` owns orchestration, authorization and
storage.  This module owns every attachment SQL statement.  Callers enter
through ``db.escritura()`` and re-authorize before using a mutating function.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .. import db
from ..protocols import DatabaseConnection


class ConflictError(Exception):
    """A compare-and-set or immutable-state precondition failed."""


class IdempotencyConflictError(Exception):
    """The same scoped key was used with a different normalized payload."""


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def terrain_exists(conn: DatabaseConnection, terrain_id: str) -> bool:
    return conn.execute("SELECT 1 FROM inventory_terrain WHERE id = ?", (terrain_id,)).fetchone() is not None


def resource_for_version(conn: DatabaseConnection, version_id: str, *, lock: bool = False) -> dict[str, Any] | None:
    suffix = db.bloqueo(conn, exclusivo=True) if lock else ""
    return _dict(conn.execute(
        """
        SELECT v.*, a.columna_id, a.tipo AS archivo_tipo, a.revision AS archivo_revision,
               a.version_actual_id, a.geometria_activa_id, a.retirado_en,
               a.retirado_motivo, a.actualizado_en, a.actualizado_por
        FROM archivo_version v JOIN archivo a ON a.id = v.archivo_id
        WHERE v.id = ?
        """ + suffix, (version_id,)).fetchone())


def resource_for_attachment(conn: DatabaseConnection, attachment_id: str,
                            *, lock: bool = False) -> dict[str, Any] | None:
    suffix = db.bloqueo(conn, exclusivo=True) if lock else ""
    return _dict(conn.execute("SELECT * FROM archivo WHERE id = ?" + suffix,
                              (attachment_id,)).fetchone())


def operation_result(conn: DatabaseConnection, operation: str, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT request_hash, result_json, actor_id FROM inventory_operation_result"
        " WHERE operation = ? AND idempotency_key = ?", (operation, key)).fetchone()
    if row is None:
        return None
    return {"request_hash": row["request_hash"], "result": json.loads(row["result_json"]),
            "actor_id": row["actor_id"]}


def save_operation_result(conn: DatabaseConnection, operation: str, key: str,
                          request_hash: str, actor_id: str, now: str,
                          result: Mapping[str, Any]) -> None:
    conn.execute(
        "INSERT INTO inventory_operation_result (operation, idempotency_key, request_hash,"
        " result_json, actor_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (operation, key, request_hash, _json(result), actor_id, now))


def effective_pending_count(conn: DatabaseConnection, actor_id: str, now: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM archivo_version v
        WHERE v.iniciado_por = ? AND v.estado = 'subiendo'
          AND (v.completar_antes_de > ? OR EXISTS (
            SELECT 1 FROM archivo_trabajo t
            WHERE t.archivo_version_id = v.id AND t.vence_en > ?
          ))
        """, (actor_id, now, now)).fetchone()
    return int(row["n"])


def start_upload(conn: DatabaseConnection, *, terrain_id: str, kind: str,
                 attachment_id: str, version_id: str, temporary_key: str,
                 original_name: str, declared_size: int, declared_sha256: str,
                 upload_expires_at: str, complete_before: str, now: str,
                 actor: Mapping[str, str], base_id: str | None) -> dict[str, Any]:
    """Create a PDF attachment or append a version to the one live KMZ."""
    column = "core:kmz" if kind == "kmz" else "core:archivos"
    attachment = None
    if kind == "kmz":
        attachment = conn.execute(
            "SELECT * FROM archivo WHERE inventory_id = ? AND columna_id = 'core:kmz'"
            " AND retirado_en IS NULL" + db.bloqueo(conn, exclusivo=True),
            (terrain_id,)).fetchone()
    if attachment is None:
        conn.execute(
            "INSERT INTO archivo (id, inventory_id, columna_id, tipo, revision, creado_en,"
            " creado_por, actualizado_en, actualizado_por) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (attachment_id, terrain_id, column, kind, now, actor["id"], now, actor["id"]))
        revision = 1
        number = 1
    else:
        attachment_id = attachment["id"]
        revision = int(attachment["revision"])
        row = conn.execute("SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM archivo_version"
                           " WHERE archivo_id = ?", (attachment_id,)).fetchone()
        number = int(row["n"])
    conn.execute(
        """
        INSERT INTO archivo_version (
          id, archivo_id, inventory_id, numero, estado, revision_base,
          nombre_original, tamano_declarado, sha256_declarado, clave_temporal,
          subida_vence_en, completar_antes_de, iniciado_en, iniciado_por
        ) VALUES (?, ?, ?, ?, 'subiendo', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (version_id, attachment_id, terrain_id, number, revision, original_name,
                declared_size, declared_sha256, temporary_key, upload_expires_at,
                complete_before, now, actor["id"]))
    _event(conn, attachment_id=attachment_id, terrain_id=terrain_id, action="subida_iniciada",
           now=now, actor=actor, base_id=base_id, version_id=version_id,
           details={"tipo": kind, "numero": number, "nombre": original_name,
                    "tamano_declarado": declared_size})
    return {"archivo_id": attachment_id, "version_id": version_id, "tipo": kind,
            "numero": number, "estado": "subiendo", "revision_base": revision,
            "nombre_original": original_name, "tamano_declarado": declared_size,
            "sha256_declarado": declared_sha256, "subida_vence_en": upload_expires_at,
            "completar_antes_de": complete_before}


def lease(conn: DatabaseConnection, *, version_id: str, work_id: str, actor_id: str,
          operation: str, started_at: str, expires_at: str, now: str) -> dict[str, Any]:
    current = conn.execute("SELECT * FROM archivo_trabajo WHERE archivo_version_id = ?"
                           + db.bloqueo(conn, exclusivo=True), (version_id,)).fetchone()
    if current is not None and current["vence_en"] > now:
        return {"acquired": False, "expires_at": current["vence_en"],
                "operation": current["operacion"]}
    if current is None:
        conn.execute(
            "INSERT INTO archivo_trabajo (archivo_version_id, trabajo_id, actor_id, operacion,"
            " inicio, vence_en) VALUES (?, ?, ?, ?, ?, ?)",
            (version_id, work_id, actor_id, operation, started_at, expires_at))
    else:
        conn.execute(
            "UPDATE archivo_trabajo SET trabajo_id = ?, actor_id = ?, operacion = ?, inicio = ?,"
            " vence_en = ? WHERE archivo_version_id = ?",
            (work_id, actor_id, operation, started_at, expires_at, version_id))
    return {"acquired": True, "expires_at": expires_at}


def lease_owned(conn: DatabaseConnection, version_id: str, work_id: str, now: str) -> bool:
    row = conn.execute("SELECT 1 FROM archivo_trabajo WHERE archivo_version_id = ?"
                       " AND trabajo_id = ? AND vence_en > ?",
                       (version_id, work_id, now)).fetchone()
    return row is not None


def release_lease(conn: DatabaseConnection, version_id: str, work_id: str) -> bool:
    changed = conn.execute("DELETE FROM archivo_trabajo WHERE archivo_version_id = ?"
                           " AND trabajo_id = ?", (version_id, work_id)).rowcount
    return bool(changed == 1)


def final_key_referenced(conn: DatabaseConnection, key: str) -> bool:
    return conn.execute("SELECT 1 FROM archivo_version WHERE clave_final = ? LIMIT 1",
                        (key,)).fetchone() is not None


def completion_attempt(conn: DatabaseConnection, version_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM archivo_intento WHERE archivo_version_id = ? AND origen = 'completar'",
        (version_id,)).fetchone()
    return attempt_dto(row) if row else None


def attempt_dto(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "numero": int(row["numero"]), "origen": row["origen"],
            "seleccion": json.loads(row["seleccion_json"]) if row["seleccion_json"] else None,
            "resultado": row["resultado"], "resultado_detalle": json.loads(row["resultado_json"]),
            "geometria_id": row["geometria_id"], "creado_en": row["creado_en"],
            "creado_por": row["creado_por"]}


def insert_attempt(conn: DatabaseConnection, *, attempt_id: str, version_id: str,
                   origin: str, selection: Sequence[int] | None, outcome: str,
                   detail: Mapping[str, Any], analyzer: str, geometry_id: str | None,
                   now: str, actor_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM archivo_intento"
                       " WHERE archivo_version_id = ?", (version_id,)).fetchone()
    number = int(row["n"])
    conn.execute(
        "INSERT INTO archivo_intento (id, archivo_version_id, numero, origen, seleccion_json,"
        " resultado, resultado_json, analizador, geometria_id, creado_en, creado_por)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (attempt_id, version_id, number, origin,
         _json(list(selection)) if selection is not None else None, outcome, _json(detail),
         analyzer, geometry_id, now, actor_id))
    return {"id": attempt_id, "numero": number, "origen": origin,
            "seleccion": list(selection) if selection is not None else None,
            "resultado": outcome, "resultado_detalle": dict(detail),
            "geometria_id": geometry_id, "creado_en": now, "creado_por": actor_id}


def insert_geometry(conn: DatabaseConnection, *, geometry_id: str, attachment_id: str,
                    version_id: str, terrain_id: str, attempt_id: str,
                    geojson_text: str, bbox: Sequence[float], point: Sequence[float],
                    parts: int, holes: int, vertices: int, area: float | None,
                    usable: bool, byte_count: int, sha256: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO geometria (
          id, archivo_id, archivo_version_id, inventory_id, intento_id, geojson,
          bbox_oeste, bbox_sur, bbox_este, bbox_norte, punto_lon, punto_lat,
          partes, huecos, vertices, area_aproximada_m2, utilizable,
          bytes_geojson, sha256_geojson, creado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (geometry_id, attachment_id, version_id, terrain_id, attempt_id, geojson_text,
                bbox[0], bbox[1], bbox[2], bbox[3], point[0], point[1], parts, holes,
                vertices, area, 1 if usable else 0, byte_count, sha256, now))


def finish_available(conn: DatabaseConnection, *, resource: Mapping[str, Any], work_id: str,
                     final_key: str, actual_size: int, sha256: str, detected_type: str,
                     now: str, actor: Mapping[str, str], base_id: str | None,
                     attempt: Mapping[str, Any] | None,
                     geometry: Mapping[str, Any] | None) -> dict[str, Any]:
    """Commit terminal bytes, optional attempt/geometry and conditional decision."""
    version_id = str(resource["id"])
    attachment_id = str(resource["archivo_id"])
    terrain_id = str(resource["inventory_id"])
    if attempt is not None:
        insert_attempt(conn, attempt_id=str(attempt["id"]), version_id=version_id,
                       origin="completar", selection=attempt.get("selection"),
                       outcome=str(attempt["outcome"]), detail=attempt["detail"],
                       analyzer=str(attempt["analyzer"]),
                       geometry_id=str(geometry["id"]) if geometry is not None else None,
                       now=now, actor_id=actor["id"])
        if geometry is not None:
            insert_geometry(conn, geometry_id=str(geometry["id"]), attachment_id=attachment_id,
                            version_id=version_id, terrain_id=terrain_id,
                            attempt_id=str(attempt["id"]), geojson_text=str(geometry["geojson"]),
                            bbox=geometry["bbox"], point=geometry["point"],
                            parts=int(geometry["parts"]), holes=int(geometry["holes"]),
                            vertices=int(geometry["vertices"]), area=geometry.get("area"),
                            usable=bool(geometry["usable"]), byte_count=int(geometry["bytes"]),
                            sha256=str(geometry["sha256"]), now=now)

    attachment = resource_for_attachment(conn, attachment_id, lock=True)
    if attachment is None:
        raise ConflictError()
    applicable = attachment["retirado_en"] is None and int(attachment["revision"]) == int(resource["revision_base"])
    geometry_applicable = geometry is not None and bool(geometry["usable"])
    applies = applicable and (resource["archivo_tipo"] == "pdf" or geometry_applicable)
    reason = None if applies or applicable else ("retirado" if attachment["retirado_en"] else "superada")
    changed = conn.execute(
        """
        UPDATE archivo_version SET estado = 'disponible', tamano = ?, sha256 = ?,
          tipo_detectado = ?, clave_final = ?, error_codigo = NULL, error_mensaje = NULL,
          aplicada = ?, motivo_no_aplicada = ?, finalizado_en = ?, finalizado_por = ?,
          terminado_en = ?, terminado_por = ?
        WHERE id = ? AND estado = 'subiendo'
        """, (actual_size, sha256, detected_type, final_key, 1 if applies else 0, reason,
                now, actor["id"], now, actor["id"], version_id)).rowcount
    if changed != 1 or not release_lease(conn, version_id, work_id):
        raise ConflictError()

    _event(conn, attachment_id=attachment_id, terrain_id=terrain_id,
           action="version_disponible", now=now, actor=actor, base_id=base_id,
           version_id=version_id, attempt_id=str(attempt["id"]) if attempt else None,
           geometry_id=str(geometry["id"]) if geometry else None,
           details={"aplicada": applies, "motivo_no_aplicada": reason})
    if attempt is not None:
        _event(conn, attachment_id=attachment_id, terrain_id=terrain_id,
               action="procesado", now=now, actor=actor, base_id=base_id,
               version_id=version_id, attempt_id=str(attempt["id"]),
               geometry_id=str(geometry["id"]) if geometry else None,
               details={"resultado": attempt["outcome"]})
    if applies:
        new_revision = int(attachment["revision"]) + 1
        geometry_id = str(geometry["id"]) if geometry else None
        changed_attachment = conn.execute(
            "UPDATE archivo SET revision = ?, version_actual_id = ?, geometria_activa_id = ?,"
            " actualizado_en = ?, actualizado_por = ? WHERE id = ? AND revision = ?"
            " AND retirado_en IS NULL",
            (new_revision, version_id, geometry_id, now, actor["id"], attachment_id,
             attachment["revision"])).rowcount
        if changed_attachment != 1:
            raise ConflictError()
        _event(conn, attachment_id=attachment_id, terrain_id=terrain_id,
               action="capa_activada" if geometry else "version_actual_cambiada",
               now=now, actor=actor, base_id=base_id, version_id=version_id,
               attempt_id=str(attempt["id"]) if attempt else None,
               geometry_id=geometry_id, revision=new_revision,
               details={"version_anterior_id": attachment["version_actual_id"],
                        "geometria_anterior_id": attachment["geometria_activa_id"]})
    elif reason is not None:
        _event(conn, attachment_id=attachment_id, terrain_id=terrain_id,
               action="decision_superada", now=now, actor=actor, base_id=base_id,
               version_id=version_id, attempt_id=str(attempt["id"]) if attempt else None,
               geometry_id=str(geometry["id"]) if geometry else None,
               details={"motivo": reason})
    return completion_result(conn, version_id)


def finish_failed(conn: DatabaseConnection, *, resource: Mapping[str, Any], work_id: str,
                  error_code: str, error_message: str, now: str,
                  actor: Mapping[str, str], base_id: str | None) -> dict[str, Any]:
    changed = conn.execute(
        "UPDATE archivo_version SET estado = 'fallido', error_codigo = ?, error_mensaje = ?,"
        " aplicada = 0, motivo_no_aplicada = NULL, finalizado_en = ?, finalizado_por = ?,"
        " terminado_en = ?, terminado_por = ? WHERE id = ? AND estado = 'subiendo'",
        (error_code, error_message, now, actor["id"], now, actor["id"], resource["id"])).rowcount
    if changed != 1 or not release_lease(conn, str(resource["id"]), work_id):
        raise ConflictError()
    _event(conn, attachment_id=str(resource["archivo_id"]), terrain_id=str(resource["inventory_id"]),
           action="version_fallida", now=now, actor=actor, base_id=base_id,
           version_id=str(resource["id"]), details={"codigo": error_code})
    return completion_result(conn, str(resource["id"]))


def completion_result(conn: DatabaseConnection, version_id: str) -> dict[str, Any]:
    resource = resource_for_version(conn, version_id)
    if resource is None:
        raise LookupError(version_id)
    attempt = completion_attempt(conn, version_id)
    return {"version": version_dto(resource, own_pending=True), "intento": attempt,
            "aplicada": bool(resource["aplicada"]) if resource["aplicada"] is not None else None,
            "motivo_no_aplicada": resource["motivo_no_aplicada"],
            "archivo": attachment_dto(resource)}


def expire_pending(conn: DatabaseConnection, *, resource: Mapping[str, Any], now: str,
                   actor: Mapping[str, str], base_id: str | None) -> None:
    changed = conn.execute(
        "UPDATE archivo_version SET estado = 'expirado', terminado_en = ?, terminado_por = ?"
        " WHERE id = ? AND estado = 'subiendo' AND completar_antes_de <= ?"
        " AND NOT EXISTS (SELECT 1 FROM archivo_trabajo WHERE archivo_version_id = ?"
        " AND vence_en > ?)",
        (now, actor["id"], resource["id"], now, resource["id"], now)).rowcount
    if changed:
        _event(conn, attachment_id=str(resource["archivo_id"]),
               terrain_id=str(resource["inventory_id"]), action="subida_expirada", now=now,
               actor=actor, base_id=base_id, version_id=str(resource["id"]))


def cancel_pending(conn: DatabaseConnection, *, resource: Mapping[str, Any], now: str,
                   actor: Mapping[str, str], base_id: str | None) -> bool:
    changed = conn.execute(
        "UPDATE archivo_version SET estado = 'cancelado', terminado_en = ?, terminado_por = ?"
        " WHERE id = ? AND estado = 'subiendo'", (now, actor["id"], resource["id"])).rowcount
    if not changed:
        return False
    conn.execute("DELETE FROM archivo_trabajo WHERE archivo_version_id = ?", (resource["id"],))
    _event(conn, attachment_id=str(resource["archivo_id"]), terrain_id=str(resource["inventory_id"]),
           action="subida_cancelada", now=now, actor=actor, base_id=base_id,
           version_id=str(resource["id"]))
    return True


def retire(conn: DatabaseConnection, *, attachment: Mapping[str, Any], expected_revision: int,
           now: str, actor: Mapping[str, str], base_id: str | None) -> tuple[dict[str, Any], list[str]]:
    if attachment["retirado_en"] is not None or int(attachment["revision"]) != expected_revision:
        raise ConflictError()
    pending = conn.execute("SELECT id, clave_temporal FROM archivo_version"
                           " WHERE archivo_id = ? AND estado = 'subiendo'",
                           (attachment["id"],)).fetchall()
    for row in pending:
        conn.execute("UPDATE archivo_version SET estado = 'cancelado', terminado_en = ?,"
                     " terminado_por = ? WHERE id = ? AND estado = 'subiendo'",
                     (now, actor["id"], row["id"]))
        conn.execute("DELETE FROM archivo_trabajo WHERE archivo_version_id = ?", (row["id"],))
        _event(conn, attachment_id=str(attachment["id"]), terrain_id=str(attachment["inventory_id"]),
               action="subida_cancelada", now=now, actor=actor, base_id=base_id,
               version_id=str(row["id"]), details={"motivo": "retirado"})
    revision = expected_revision + 1
    changed = conn.execute(
        "UPDATE archivo SET revision = ?, version_actual_id = NULL, geometria_activa_id = NULL,"
        " retirado_en = ?, retirado_por = ?, retirado_motivo = 'usuario', actualizado_en = ?,"
        " actualizado_por = ? WHERE id = ? AND revision = ? AND retirado_en IS NULL",
        (revision, now, actor["id"], now, actor["id"], attachment["id"], expected_revision)).rowcount
    if changed != 1:
        raise ConflictError()
    _event(conn, attachment_id=str(attachment["id"]), terrain_id=str(attachment["inventory_id"]),
           action="retirado", now=now, actor=actor, base_id=base_id, revision=revision,
           details={"version_anterior_id": attachment["version_actual_id"],
                    "geometria_anterior_id": attachment["geometria_activa_id"]})
    current = resource_for_attachment(conn, str(attachment["id"]))
    assert current is not None
    return attachment_dto(current), [str(r["clave_temporal"]) for r in pending]


def geometry_for_activation(conn: DatabaseConnection, attachment_id: str, version_id: str,
                            geometry_id: str) -> dict[str, Any] | None:
    return _dict(conn.execute(
        """
        SELECT g.*, i.resultado AS intento_resultado
        FROM geometria g JOIN archivo_intento i ON i.id = g.intento_id
        WHERE g.id = ? AND g.archivo_id = ? AND g.archivo_version_id = ?
        """, (geometry_id, attachment_id, version_id)).fetchone())


def activate(conn: DatabaseConnection, *, attachment: Mapping[str, Any], version_id: str,
             geometry_id: str | None, expected_revision: int, now: str,
             actor: Mapping[str, str], base_id: str | None) -> dict[str, Any]:
    if attachment["retirado_en"] is not None or int(attachment["revision"]) != expected_revision:
        raise ConflictError()
    version = conn.execute("SELECT * FROM archivo_version WHERE id = ? AND archivo_id = ?",
                           (version_id, attachment["id"])).fetchone()
    if version is None or version["estado"] != "disponible":
        raise ValueError("version")
    geometry = None
    if attachment["tipo"] == "kmz":
        if geometry_id is None:
            raise ValueError("geometry")
        geometry = geometry_for_activation(conn, str(attachment["id"]), version_id, geometry_id)
        if geometry is None or geometry["intento_resultado"] != "listo" or not geometry["utilizable"]:
            raise ValueError("geometry")
    elif geometry_id is not None:
        raise ValueError("geometry")
    revision = expected_revision + 1
    changed = conn.execute(
        "UPDATE archivo SET revision = ?, version_actual_id = ?, geometria_activa_id = ?,"
        " actualizado_en = ?, actualizado_por = ? WHERE id = ? AND revision = ?"
        " AND retirado_en IS NULL",
        (revision, version_id, geometry_id, now, actor["id"], attachment["id"],
         expected_revision)).rowcount
    if changed != 1:
        raise ConflictError()
    _event(conn, attachment_id=str(attachment["id"]), terrain_id=str(attachment["inventory_id"]),
           action="capa_activada" if geometry_id else "version_actual_cambiada", now=now,
           actor=actor, base_id=base_id, version_id=version_id,
           attempt_id=str(geometry["intento_id"]) if geometry else None,
           geometry_id=geometry_id, revision=revision,
           details={"version_anterior_id": attachment["version_actual_id"],
                    "geometria_anterior_id": attachment["geometria_activa_id"]})
    current = resource_for_attachment(conn, str(attachment["id"]))
    assert current is not None
    return attachment_dto(current)


def insert_processing_attempt(conn: DatabaseConnection, *, resource: Mapping[str, Any],
                              work_id: str, origin: str, attempt: Mapping[str, Any],
                              geometry: Mapping[str, Any] | None, now: str,
                              actor: Mapping[str, str], base_id: str | None) -> dict[str, Any]:
    if not lease_owned(conn, str(resource["id"]), work_id, now):
        raise ConflictError()
    dto = insert_attempt(conn, attempt_id=str(attempt["id"]), version_id=str(resource["id"]),
                         origin=origin, selection=attempt.get("selection"),
                         outcome=str(attempt["outcome"]), detail=attempt["detail"],
                         analyzer=str(attempt["analyzer"]),
                         geometry_id=str(geometry["id"]) if geometry else None,
                         now=now, actor_id=actor["id"])
    if geometry:
        insert_geometry(conn, geometry_id=str(geometry["id"]),
                        attachment_id=str(resource["archivo_id"]), version_id=str(resource["id"]),
                        terrain_id=str(resource["inventory_id"]), attempt_id=str(attempt["id"]),
                        geojson_text=str(geometry["geojson"]), bbox=geometry["bbox"],
                        point=geometry["point"], parts=int(geometry["parts"]),
                        holes=int(geometry["holes"]), vertices=int(geometry["vertices"]),
                        area=geometry.get("area"), usable=bool(geometry["usable"]),
                        byte_count=int(geometry["bytes"]), sha256=str(geometry["sha256"]), now=now)
    if not release_lease(conn, str(resource["id"]), work_id):
        raise ConflictError()
    _event(conn, attachment_id=str(resource["archivo_id"]), terrain_id=str(resource["inventory_id"]),
           action="procesado", now=now, actor=actor, base_id=base_id,
           version_id=str(resource["id"]), attempt_id=str(attempt["id"]),
           geometry_id=str(geometry["id"]) if geometry else None,
           details={"resultado": attempt["outcome"], "origen": origin})
    return dto


def versions_for_attachment(conn: DatabaseConnection, attachment_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM archivo_version WHERE archivo_id = ?"
                        " ORDER BY numero DESC LIMIT ?", (attachment_id, limit)).fetchall()
    return [version_dto(r, own_pending=True) for r in rows]


def list_for_terrain(conn: DatabaseConnection, terrain_id: str, actor_id: str,
                     now: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM archivo WHERE inventory_id = ?"
                        " ORDER BY creado_en DESC, id DESC", (terrain_id,)).fetchall()
    result = []
    for row in rows:
        item = attachment_dto(row)
        latest = conn.execute("SELECT * FROM archivo_version WHERE archivo_id = ?"
                              " ORDER BY numero DESC LIMIT 1", (row["id"],)).fetchone()
        item["ultima_version"] = projected_version(conn, latest, actor_id, now) if latest else None
        result.append(item)
    return result


def summaries(conn: DatabaseConnection, terrain_ids: Sequence[str], actor_id: str,
              now: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for terrain_id in terrain_ids:
        pdf_rows = conn.execute(
            "SELECT a.*, v.id AS v_id, v.numero AS v_numero, v.estado AS v_estado,"
            " v.nombre_original, v.tamano, v.tamano_declarado, v.completar_antes_de,"
            " v.iniciado_por FROM archivo a LEFT JOIN archivo_version v"
            " ON v.id = (SELECT vv.id FROM archivo_version vv WHERE vv.archivo_id = a.id"
            " ORDER BY vv.numero DESC LIMIT 1) WHERE a.inventory_id = ?"
            " AND a.tipo = 'pdf' ORDER BY a.creado_en DESC, a.id DESC LIMIT 5",
            (terrain_id,)).fetchall()
        kmz = conn.execute(
            "SELECT a.*, v.id AS v_id, v.numero AS v_numero, v.estado AS v_estado,"
            " v.nombre_original, v.tamano, v.tamano_declarado, v.completar_antes_de,"
            " v.iniciado_por FROM archivo a LEFT JOIN archivo_version v"
            " ON v.id = (SELECT vv.id FROM archivo_version vv WHERE vv.archivo_id = a.id"
            " ORDER BY vv.numero DESC LIMIT 1) WHERE a.inventory_id = ? AND a.tipo = 'kmz'"
            " AND a.retirado_en IS NULL LIMIT 1", (terrain_id,)).fetchone()
        output[terrain_id] = {
            "pdf_total": int(conn.execute("SELECT COUNT(*) AS n FROM archivo WHERE inventory_id = ?"
                                          " AND tipo = 'pdf' AND retirado_en IS NULL",
                                          (terrain_id,)).fetchone()["n"]),
            "pdf_recientes": [_summary_row(conn, r, actor_id, now) for r in pdf_rows],
            "kmz": _summary_row(conn, kmz, actor_id, now) if kmz else None,
        }
    return output


def _summary_row(conn: DatabaseConnection, row: Any, actor_id: str, now: str) -> dict[str, Any]:
    state = row["v_estado"]
    if state == "subiendo" and row["completar_antes_de"] <= now:
        live = conn.execute("SELECT 1 FROM archivo_trabajo WHERE archivo_version_id = ?"
                            " AND vence_en > ?", (row["v_id"], now)).fetchone()
        if live is None:
            state = "expirado"
    own = row["iniciado_por"] == actor_id
    if state == "subiendo" and not own:
        private_version = {"estado": "subiendo", "propia": False}
        return {"id": row["id"], "tipo": row["tipo"], "revision": row["revision"],
                "retirado": row["retirado_en"] is not None,
                "version_actual_id": row["version_actual_id"],
                "geometria_activa_id": row["geometria_activa_id"],
                "ultima_version": private_version}
    version: dict[str, Any] | None = None
    if row["v_id"]:
        version = {"id": row["v_id"], "numero": row["v_numero"], "estado": state,
                   "nombre_original": row["nombre_original"]}
        if own or state != "subiendo":
            version["tamano"] = row["tamano"]
            version["tamano_declarado"] = row["tamano_declarado"]
        if state == "subiendo":
            version["propia"] = own
    return {"id": row["id"], "tipo": row["tipo"], "revision": row["revision"],
            "retirado": row["retirado_en"] is not None,
            "version_actual_id": row["version_actual_id"],
            "geometria_activa_id": row["geometria_activa_id"], "ultima_version": version}


def history(conn: DatabaseConnection, attachment_id: str, cursor: tuple[str, str] | None,
            limit: int) -> tuple[list[dict[str, Any]], str | None]:
    where = "archivo_id = ?"
    params: list[Any] = [attachment_id]
    if cursor:
        where += " AND (at < ? OR (at = ? AND id < ?))"
        params.extend((cursor[0], cursor[0], cursor[1]))
    params.append(limit + 1)
    rows = conn.execute(
        "SELECT * FROM archivo_evento WHERE " + where + " ORDER BY at DESC, id DESC LIMIT ?",
        tuple(params)).fetchall()
    events = [event_dto(r) for r in rows[:limit]]
    next_cursor = None
    if len(rows) > limit and events:
        next_cursor = f"{events[-1]['at']}|{events[-1]['id']}"
    return events, next_cursor


def projected_version(conn: DatabaseConnection, row: Any, actor_id: str, now: str) -> dict[str, Any]:
    if row is None:
        raise LookupError
    own = row["iniciado_por"] == actor_id
    if row["estado"] == "subiendo" and not own:
        return {"estado": "subiendo", "propia": False}
    dto = version_dto(row, own_pending=own)
    if row["estado"] == "subiendo" and row["completar_antes_de"] <= now:
        live = conn.execute("SELECT 1 FROM archivo_trabajo WHERE archivo_version_id = ?"
                            " AND vence_en > ?", (row["id"], now)).fetchone()
        if live is None:
            dto["estado"] = "expirado"
    return dto


def attachment_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(row.keys())
    joined = "archivo_id" in keys and "archivo_tipo" in keys
    return {"id": row["archivo_id"] if joined else row["id"],
            "inventory_id": row["inventory_id"], "columna_id": row["columna_id"],
            "tipo": row["archivo_tipo"] if joined else row["tipo"],
            "revision": int(row["archivo_revision"] if joined else row["revision"]),
            "version_actual_id": row["version_actual_id"],
            "geometria_activa_id": row["geometria_activa_id"],
            "retirado_en": row["retirado_en"], "retirado_motivo": row["retirado_motivo"]}


def version_dto(row: Mapping[str, Any], *, own_pending: bool) -> dict[str, Any]:
    dto = {"id": row["id"], "archivo_id": row["archivo_id"], "inventory_id": row["inventory_id"],
           "numero": int(row["numero"]), "estado": row["estado"],
           "revision_base": int(row["revision_base"]), "nombre_original": row["nombre_original"],
           "tamano_declarado": int(row["tamano_declarado"]), "tamano": row["tamano"],
           "sha256": row["sha256"], "tipo_detectado": row["tipo_detectado"],
           "error": ({"codigo": row["error_codigo"], "mensaje": row["error_mensaje"]}
                     if row["error_codigo"] else None), "aplicada": (bool(row["aplicada"])
                     if row["aplicada"] is not None else None),
           "motivo_no_aplicada": row["motivo_no_aplicada"], "iniciado_en": row["iniciado_en"],
           "finalizado_en": row["finalizado_en"], "terminado_en": row["terminado_en"]}
    if row["estado"] == "subiendo" and own_pending:
        dto.update({"subida_vence_en": row["subida_vence_en"],
                    "completar_antes_de": row["completar_antes_de"]})
    return dto


def event_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "accion": row["accion"], "revision": row["revision"],
            "archivo_version_id": row["archivo_version_id"], "intento_id": row["intento_id"],
            "geometria_id": row["geometria_id"], "base_id": row["base_id"],
            "actor": {"id": row["actor_id"], "display_name": row["actor_name"]},
            "at": row["at"], "details": json.loads(row["details_json"] or "{}")}


def _event(conn: DatabaseConnection, *, attachment_id: str, terrain_id: str, action: str,
           now: str, actor: Mapping[str, str], base_id: str | None,
           version_id: str | None = None, attempt_id: str | None = None,
           geometry_id: str | None = None, revision: int | None = None,
           details: Mapping[str, Any] | None = None) -> None:
    import uuid
    conn.execute(
        """
        INSERT INTO archivo_evento (
          id, archivo_id, inventory_id, archivo_version_id, intento_id, geometria_id,
          accion, revision, base_id, actor_id, actor_name, at, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), attachment_id, terrain_id, version_id, attempt_id, geometry_id,
                action, revision, base_id, actor["id"], actor["display_name"], now,
                _json(details) if details else None))
