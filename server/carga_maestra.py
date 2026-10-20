"""Load read spreadsheet rows into one work base of the master table.

Shared by scripts/cargar_maestra.py and the table's «Importar Excel»
(server/api/maestra.py). Every row passes the same field validation as a row
typed in the table; a row already in the base (same name + state +
municipality + area, the domain identity) or repeated in the file is skipped
and reported, never duplicated and never updated. Each terrain is created by
the master table's own repository function, so it gets its revision, its
"create" history event and its idempotency row exactly like one created in the
app. The caller runs it in one write transaction and writes nothing while any
row is invalid: all or nothing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from . import inventario
from .importer import ImportResult, TerrainRecord
from .matching import Disposition, classify, dedupe_key
from .normalize import fold
from .protocols import DatabaseConnection
from .repo import inventario as repo

# Master-table fields the shared reader keeps as extra columns, by their header.
DE_EXTRA = {"tipo de terreno": "tipo_terreno", "comentarios": "notas_internas"}


def no_cargadas(leido: ImportResult) -> list[str]:
    """The file's columns the master table has no field for."""
    return [c for c in leido.columnas_no_reconocidas if fold(c) not in DE_EXTRA]


def _crudos(record: TerrainRecord) -> dict[str, Any]:
    crudos = {n: getattr(record, n) for n in inventario.EDITABLE if hasattr(record, n)}
    for etiqueta, valor in record.extra.items():
        campo = DE_EXTRA.get(fold(etiqueta))
        if campo and crudos.get(campo) is None:
            crudos[campo] = valor
    return {n: v for n, v in crudos.items() if v is not None}


def validar(records: Sequence[TerrainRecord]) -> tuple[list[dict[str, Any]], list[str]]:
    """Each row's clean fields, and every invalid value as "línea N (name): field: why"."""
    filas: list[dict[str, Any]] = []
    errores: list[str] = []
    for record in records:
        campos, malos = inventario.clean_changes(_crudos(record))
        errores.extend(f"línea {record.fila} ({record.terreno}): {campo}: {mensaje}"
                       for campo, mensaje in malos.items())
        filas.append(campos)
    return filas, errores


def cargar(conn: DatabaseConnection, base_id: str, records: Sequence[TerrainRecord],
           filas: Sequence[Mapping[str, Any]], actor: Mapping[str, Any], *,
           simular: bool) -> tuple[int, list[str]]:
    """Create the new rows (none when simulating). Returns how many are new and
    one line per skipped duplicate."""
    nuevas = 0
    omitidas: list[str] = []
    for decision in classify(records, existentes(conn, base_id)):
        record = records[decision.incoming_index]
        if decision.disposition is not Disposition.NUEVA:
            donde = (f"terreno {decision.existing_id}" if decision.existing_id
                     else "otra línea de este archivo")
            omitidas.append(f"línea {record.fila} ({record.terreno}): ya existe en {donde}"
                            + (f" · {decision.reason}" if decision.reason else ""))
            continue
        nuevas += 1
        if not simular:
            campos = dict(filas[decision.incoming_index])
            pedido = hashlib.sha256(json.dumps(
                {"base": base_id, "campos": campos}, sort_keys=True,
                ensure_ascii=False).encode("utf-8")).hexdigest()
            repo.crear(conn, campos, actor, f"carga-{uuid.uuid4()}", pedido, base_id)
    return nuevas, omitidas


def existentes(conn: DatabaseConnection, base_id: str) -> list[dict[str, Any]]:
    """Every terrain of the base, shaped for classify()."""
    consulta = inventario.parse_query(
        {"limit": [str(inventario.MAX_LIST_LIMIT)]}, inventario.SCOPED_QUERY)
    todos: list[dict[str, Any]] = []
    while True:
        pagina, _, cursor, _ = repo.listar(conn, consulta, base_id)
        todos.extend(
            {**t["draft"], "id": t["id"], "clave_dedupe": dedupe_key(
                t["draft"]["terreno"] or "", t["draft"]["estado"], t["draft"]["municipio"])}
            for t in pagina)
        if cursor is None:
            return todos
        consulta = {**consulta, "cursor": cursor}
