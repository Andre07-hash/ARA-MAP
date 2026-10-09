# Team A — packet 1A, part 2: scoped terrain-record backend

Backend only. An operator can create, list, edit, archive and restore terrain
records inside a granted work base; an administrator has the master table over
every base, bounded and filtered in SQL, and can move a record between bases.
**No screen uses it yet**: the table and the base/grant/transfer controls are
packet 2A, file handlers 2B, mounting files and layouts 3A.

- Instruction commit: `f3fd0f05c0ba9f28bd8b3e7321f374368027e784`,
  `reports/round-1-instructions-2026-10-08/TEAM_A.md`.
- `origin/main`: `09452fd26d38319567dce28a89db100ea61c739a`, unchanged.
- **Base:** the round 1 checkpoint, PR #20, head
  `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb` (manifest:
  `reports/round-1-baseline-2026-10-08/START_HERE.md`). Branch
  `claude/team-a/master-record-backend`; its draft PR targets
  `claude/integration/round-1-baseline`. The checkpoint branch was not changed.
- **Schema stays 10.** No migration was needed.
- The head commit and CI evidence are in the PR.

## 1. API matrix

Record routes after this packet. New ones in bold.

| Route | Capability | Scope check | Notes |
|---|---|---|---|
| `GET /api/inventario/terrenos` | `maestra.global` | — (administrators) | Master table. Now SQL; adds `base`, `tipo_terreno`, `sort` |
| `POST /api/inventario/terrenos` | `maestra.global` | — | Creates an unassigned record |
| **`GET /api/maestra/bases/:bid/terrenos`** | `maestra.ver` | `require_base` | One base's list |
| **`POST /api/maestra/bases/:bid/terrenos`** | `maestra.editar` | `reverificar_base` in the write transaction | Blank or populated create |
| `GET /api/inventario/terrenos/:id` | `maestra.ver` | `require_terreno` | Adds `base_id`, `custom`, `draft.tipo_terreno` |
| `PATCH /api/inventario/terrenos/:id` | `maestra.editar` | `reverificar_terreno(exclusivo)` | `tipo_terreno` editable; currency no longer required with an amount |
| `GET /api/inventario/terrenos/:id/historial` | `maestra.ver` | `require_terreno` | Base details of a transfer only for administrators |
| **`POST /api/inventario/terrenos/:id/archivar`** | `maestra.archivar` | `reverificar_terreno(exclusivo)` | `{expected_version}` |
| **`POST /api/inventario/terrenos/:id/restaurar`** | `maestra.archivar` | same | `{expected_version}` |
| **`GET /api/inventario/terrenos/:id/transferir?base_id=…`** | `bases.gestionar` | `require_terreno` | Preview, read-only |
| **`POST /api/inventario/terrenos/:id/transferir`** | `bases.gestionar` | `reverificar_terreno(exclusivo)` + destination lock | `{expected_version, base_id}` |

54 routes in the registry: 6 anonymous, 48 private, each with a declared
capability. The route-registry tests from A-2 walk the new ones too.

Statuses are A-2's: 401, 403 `forbidden`, 404 `not_found` (missing and out of
scope, byte-identical), 409, 422 `validation_failed`, 503 `ocupado`. New 409
codes: `terreno_no_archivado`; new 403 code: `requiere_admin`. Authorization is
resolved before any answer about the body, the query or the version: an
out-of-scope caller gets the same 404 for a valid and an invalid request.

Fictional request and response examples:
[examples/registros.json](examples/registros.json).

## 2. The record

One `inventory_terrain` row per terrain, identified by its UUID; zero or one
`base_id`. Nothing is ever copied to move or share it.

Core columns → stored fields. All optional; missing stays NULL.

| Column | Field | Rule when present |
|---|---|---|
| Tipo de terreno | `tipo_terreno` | **New in this packet as an editable field.** Free text, single-spaced, at most **100** characters |
| Nombre de terreno | `terreno` | text ≤ 200 |
| Estado, Municipio | `estado`, `municipio` | text ≤ 100 |
| Superficie, HA | `superficie_m2`, `superficie_ha` | finite, ≥ 0; neither derived from the other |
| Afectaciones % | `afectaciones_pct` | finite, ≥ 0 |
| Asking price, Asking $/m2 | `asking_price`, `asking_m2` | finite, ≥ 0; neither derived |
| Comentarios | `notas_internas` | private text ≤ 10,000 |
| X, Y | `lat`, `lon` | −90…90, −180…180; never swapped |
| Archivos, KMZ | attachment resources | not fields of the record; sending `archivos`/`kmz` is a 422 |

The other existing fields (`direccion`, `afectaciones_m2`, `moneda`,
`price_on_request`, `availability`, `public_description`, `contacto`) are
unchanged.

- **A blank record is `{}`.** `POST …/bases/:bid/terrenos` with an empty body
  and an `Idempotency-Key` creates a record whose business fields are all NULL
  (`price_on_request` false and `availability` `unknown`, as before).
- **An amount no longer needs a currency to be saved.** `moneda` stays NULL
  (unknown) until someone states it; it is never assumed to be MXN. The
  publication gate still requires it (`currency_required`), and price filters
  still need one explicit currency. `inventario.check_merged`, which held only
  that rule, is removed.
- Nothing is converted, derived or deduplicated. Validation of values that
  are sent, and the existing warnings, are unchanged.
- The record DTO adds `base_id` and `custom`. Revision fields, provenance
  (`source_extra`), confirmation stamps and published pointers are untouched;
  every new revision carries `extra_json` and `custom_json` forward and records
  the terrain's base at that moment.

**`custom`** holds the values of the terrain's **current** base's unretired
custom columns, keyed `custom:<column id>`, for every reader including
administrators. Values kept from another base, or of a retired column, stay
stored in `custom_json` and are not shown. No route writes custom values yet
(2A); tests seed them.

## 3. Creating, and idempotency

Body: the flat field map, as the existing create. The owner is the path's base;
the actor is the session. `base_id`, `actor_id`, `rol`, `id`, `version` and the
like in the body are 422, and nothing in headers or the query string changes
either.

`Idempotency-Key` (8–200 printable characters) is required.

- **A key belongs to one account creating in one place.** It is stored under
  `create:<base id or "global">:<actor id>` in the existing
  `inventory_operation_result` table. The same key from another account, or for
  another base, is a different key: it creates that caller's own record and can
  never return someone else's.
- The hash covers the destination base and the cleaned fields. Same key, same
  request: the same record, one terrain and one event however many times and
  however concurrently. Same key, different request: 409
  `idempotency_conflict`.
- **Only the id is stored**, `{"id": "…"}`, never a response. A replay
  re-authorizes the caller for the record *as it is now* and serializes it
  fresh. If it was moved out of the caller's scope, or the caller lost the
  grant, the replay is the ordinary 404 and creates nothing.
- Keys stored by earlier code (operation `create`, whole response stored) are
  still honoured on the unscoped route, for the account that wrote them only.

## 4. Lists

`{terrenos, total, next_cursor, facets}`, for the master table and for a base.

| Parameter | Master | Base | Meaning |
|---|---|---|---|
| `q` | ✔ | ✔ | Folded substring over name, municipality, state, address |
| `estado`, `municipio`, `tipo_terreno`, `availability` | ✔ | ✔ | Exact, repeatable |
| `area_min_m2`, `area_max_m2` | ✔ | ✔ | Records with no area are left out |
| `moneda`, `price_min`, `price_max`, `price_basis` | ✔ | ✔ | One explicit currency; unknown and other currencies left out |
| `publication_state`, `include_archived`, `attention` | ✔ | ✔ | As before |
| `base` | ✔ | 422 | Base ids and/or `sin_asignar`, repeatable |
| `sort` | ✔ | ✔ | `id` (default), `terreno`, `estado`, `municipio`, `tipo_terreno`, `superficie_m2`, `asking_price`, `updated_at`; `-` in front for descending |
| `limit` | ✔ | ✔ | Default 100, **maximum 200** (was 250). History keeps 250 |
| `cursor` | ✔ | ✔ | Opaque; from `next_cursor` |

- **Everything is SQL over one set of predicates**: scope, filters, search,
  order, the count and the facets. Identifiers come from fixed allowlists; every
  client value is a bound parameter. A list costs **7 statements** whatever the
  page size: count, page, four facets, one for the page's custom columns. The
  page query joins what a record needs; there is no per-row query.
- **Facets** (`estados`, `municipios`, `monedas`, **`tipos`**) are computed over
  what the caller is looking at before business filters: the scope, the `base`
  filter and whether archived records are in view. This is the existing,
  intentional behaviour: choosing a state does not remove the other states from
  the options. `municipios` narrows to the chosen states.
- **Folding.** Search and text sorts compare text with ASCII case and Spanish
  diacritics removed (`Á→a`, `Ñ→n`, `Ü→u`, …), from one table used by both
  databases: a function registered on each SQLite connection, `translate()` with
  `COLLATE "C"` on Postgres. The result does not depend on the server's locale.
  It is not full Unicode folding: other characters compare as written. Facet
  lists are sorted with the same key.
- **Order.** Missing values come last in both directions. Equal keys are
  ordered by id. Tested to give the same sequence on both databases.
- **Cursor.** For `sort=id` it is the last id, as before. For other sorts it is
  an encoded `[sort, last key, last id]`. A cursor is a position, not authority:
  it is ANDed onto the scoped query, so a cursor from another list, or a forged
  one, selects rows of the caller's own scope or nothing. A cursor for another
  sort is 422. **It is not a snapshot:** a record edited or created between two
  pages may appear twice or not at all.
- No geometry, file credential or attachment summary is in a list; `ubicacion`
  is not returned. Location filters remain X/Y-only until 3A.

### One filter is not SQL

`attention` ("needs a look") is decided by the publication gate and the
validation warnings, which are Python rules, not a column. When that filter is
used, the query still applies scope and every other filter in SQL, then reads
the remaining rows one at a time to evaluate it; only the page is built. On
25,000 records that is about a second (§6). The interface does not use this
filter today. Making it SQL needs a stored flag on the revision, which is a
schema change; it is listed as a follow-up rather than done here.

## 5. Archive, restore, transfer, history

**Archive / restore** (`maestra.archivar`, `{expected_version}`): sets or
clears `archived_at`, increments the version, adds one event (`archive`,
`restore`). Same id, same revision, same files and layout. An archived terrain
is readable in scope, absent from lists unless asked for, and refuses ordinary
edits (409 `terreno_archivado`). Archiving twice or restoring an active terrain
is 409. In an archived base both are 409 `base_archivada`: restoring a terrain
cannot reopen its base. **A published terrain** (a published revision pointer
is set) can be archived or restored only by an administrator; an operator gets
403 `requiere_admin`, because either would change what the public sees. There
is still no publish route.

**Transfer** (`bases.gestionar`, administrators): one transaction changes the
owner, writes a revision recording the new base, increments the version and
adds one `transfer` event with the old and new base. Earlier revisions are not
rewritten.

- `base_id` is an active base, or `null` for none. A destination that does not
  exist is 422; an archived one is 409 `base_archivada`. A terrain that is
  archived, or whose source base is archived, must be restored first (409):
  a transfer is not a way around an archive. Moving to the base it is already
  in changes nothing.
- Files, the active layout, their versions and all history stay on the same
  terrain id. Attachment rows are byte-identical before and after (tested with a
  seeded, activated KMZ graph).
- Source-only operators lose the record on their next request; a stale edit
  they had open gets 404, not a conflict. Destination operators get the record
  and its core history.
- **Locks.** User → session → terrain (`FOR UPDATE`) → source base → destination
  base (`FOR SHARE`). Archiving either base, or revoking a grant, takes that base
  exclusively and therefore waits for an open transfer, and the reverse. A
  writer that locks a single base cannot form a cycle with this; a future
  operation that locks two bases must take them in id order.

**Preview**, `GET …/transferir?base_id=<id|sin_asignar>`: `{terreno: {id,
version}, origen, destino, sin_cambio, acceso: [{id, login, display_name,
active}], columnas_que_se_ocultan: [{id, nombre, con_valor}]}`. `acceso` is who
can open the destination (administrators always can and are not listed).
`columnas_que_se_ocultan` are the source base's columns, with whether this
terrain holds a value. It reads only; the transfer re-checks version and
permissions on its own.

**History.** Events carry core-field changes, which travel with the terrain.
For a non-administrator, an event shows `changes` and `confirmed` only: a
transfer appears as an event, its bases do not. Administrators see everything
recorded. There are no custom-value changes in history yet, because nothing
edits them; when 2A adds that, the same projection must filter them to the
reader's current-base columns.

## 6. Measurement

`medir.py` in this folder; raw output and query plans in `evidencia/`. 25,000
synthetic records: one 3,000-record base, ten bases sharing 21,000, 1,000
unassigned; five operators granted the large base. Requests go through the real
dispatcher with real sessions on the loopback interface; each list is called
five times. One developer Mac, databases on the same machine.

**SQLite, temporary file, Python 3.9.6**

| Operation | Matching | Rows | Response | SQL statements | Median ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|
| Master table, default page (100) | 25,000 | 100 | 163 kB | 7 | 82 | 83 |
| Master table, 200 rows | 25,000 | 200 | 323 kB | 7 | 86 | 87 |
| Master table, state + type filter | 625 | 100 | 161 kB | 7 | 94 | 94 |
| Master table, price range in USD | 1,411 | 100 | 156 kB | 7 | 92 | 93 |
| Master table, search 'nandu 12' | 220 | 100 | 162 kB | 7 | 185 | 188 |
| Master table, one base + unassigned | 3,100 | 100 | 160 kB | 7 | 39 | 39 |
| Master table, sorted by name | 25,000 | 100 | 161 kB | 7 | 141 | 142 |
| Master table, sorted by area, descending | 25,000 | 100 | 160 kB | 7 | 106 | 107 |
| Master table, attention=false (the one Python-side filter) | 0 | 0 | 1 kB | 6 | 1250 | 1251 |
| 3,000-record base, operator, default page | 3,000 | 100 | 161 kB | 7 | 19 | 20 |
| 3,000-record base, operator, 200 rows sorted by name | 3,000 | 200 | 322 kB | 7 | 27 | 27 |
| 3,000-record base, operator, search | 880 | 100 | 162 kB | 7 | 30 | 30 |
| 3,000-record base, operator, state filter | 375 | 100 | 161 kB | 7 | 18 | 18 |
| Master table, pages 1-10 of 200 by cursor, sorted by name | 25,000 | 200 | 322 kB | 7 | 183 | 185 |

Five sessions, 100 edits of 100 different records: 100 accepted, 0 other outcomes; median 33 ms, max 78 ms. Five sessions, one record, same version: responses [200, 409, 409, 409, 409]; the record ends at version 2 with 2 revisions and 2 events.

**PostgreSQL 16, disposable local schema, Python 3.12, after ANALYZE**

| Operation | Matching | Rows | Response | SQL statements | Median ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|
| Master table, default page (100) | 25,000 | 100 | 161 kB | 7 | 57 | 60 |
| Master table, 200 rows | 25,000 | 200 | 321 kB | 7 | 59 | 59 |
| Master table, state + type filter | 625 | 100 | 161 kB | 7 | 59 | 59 |
| Master table, price range in USD | 1,411 | 100 | 156 kB | 7 | 57 | 64 |
| Master table, search 'nandu 12' | 220 | 100 | 162 kB | 7 | 488 | 490 |
| Master table, one base + unassigned | 3,100 | 100 | 161 kB | 7 | 34 | 35 |
| Master table, sorted by name | 25,000 | 100 | 161 kB | 7 | 187 | 188 |
| Master table, sorted by area, descending | 25,000 | 100 | 160 kB | 7 | 99 | 99 |
| Master table, attention=false (the one Python-side filter) | 0 | 0 | 1 kB | 6 | 824 | 827 |
| 3,000-record base, operator, default page | 3,000 | 100 | 162 kB | 7 | 31 | 34 |
| 3,000-record base, operator, 200 rows sorted by name | 3,000 | 200 | 322 kB | 7 | 65 | 66 |
| 3,000-record base, operator, search | 880 | 100 | 160 kB | 7 | 467 | 468 |
| 3,000-record base, operator, state filter | 375 | 100 | 161 kB | 7 | 32 | 33 |
| Master table, pages 1-10 of 200 by cursor, sorted by name | 25,000 | 200 | 322 kB | 7 | 472 | 477 |

Five sessions, 100 edits of 100 different records: 100 accepted, 0 other outcomes; median 27 ms, max 32 ms. Five sessions, one record, same version: responses [200, 409, 409, 409, 409]; the record ends at version 2 with 2 revisions and 2 events.

What the numbers say, and do not say:

- Every list is 7 statements (6 when the attention filter replaces the count),
  independent of the page and of the inventory size. A 100-row page is about
  160 kB of JSON; 200 rows about 320 kB.
- **Plans.** A base's list enters through `idx_inventory_terrain_base` and joins
  the draft revision by primary key. The master table scans `inventory_terrain`
  and joins by primary key; with the default order it walks the primary key and
  stops at the limit. Filters on revision columns (state, type, price, area) are
  evaluated on that scan: there is no index on them, and at this size none was
  needed. Full plans are in the JSON.
- **Postgres needs statistics.** Measured immediately after the bulk load, with
  no `ANALYZE`, two master-table filters took 2.5 s and 5.6 s because the planner
  chose nested loops over tables it believed empty. After `ANALYZE` the same
  requests take about 60 ms. A database in service is analyzed by autovacuum; a
  bulk import or a restore should be followed by `ANALYZE`. Recorded as a release
  note.
- **Search and text sort are the slow operations**: about 0.5 s on Postgres and
  0.2 s on SQLite over 25,000 records, because every row's text is folded. This
  also applies inside a 3,000-record base on Postgres, where the planner folds
  before it narrows to the base. It is bounded and correct; the fix, if wanted,
  is a stored folded column or an expression index, which is a schema change.
- The attention filter costs about a second on the full inventory (§4).
- This is a backend measurement on one machine with fictional data. It is not a
  capacity claim for the product, a hosted measurement, or a browser one.

## 7. Verification

`tests/test_registros_maestra.py`: 23 tests on SQLite, 22 on Postgres, through
the real dispatcher with real sessions, on the A-2 fixture (two administrators;
operators with one, two and no grants; two active bases and an archived one;
assigned, unassigned and archived terrains).

| Acceptance item | Tests |
|---|---|
| 1. Blank create where authorized and nowhere else; optional values round-trip | `test_a_blank_record_is_created_where_authorized_and_nowhere_else`, `test_every_core_value_is_optional_and_round_trips`, `test_the_body_cannot_choose_the_owner_actor_or_role` |
| 2. Idempotency scope and replay; simultaneous edits | `test_a_repeated_key_returns_the_same_record_to_its_owner_only`, `test_a_replay_is_reauthorized_against_the_record_as_it_is_now`, `test_simultaneous_requests_with_one_key_create_one_record`, `test_five_sessions_editing_one_cell_give_one_version_and_four_conflicts` |
| 3. Archive, restore, transfer; both race orders; retained files; custom redaction | `test_archiving_is_reversible_and_changes_only_the_archive_state`, `test_archive_and_restore_are_refused_out_of_scope_or_in_an_archived_base`, `test_an_operator_cannot_change_what_the_public_sees_by_archiving`, `test_a_transfer_moves_the_one_record_with_its_files_and_history`, `test_custom_values_follow_the_base_that_defines_them`, `test_transfers_are_validated_and_administrators_only`, `test_a_transfer_and_an_edit_never_both_win_on_one_version`, `test_a_transfer_and_a_change_to_its_destination_are_serialized` |
| 4. Inaccessible rows in no total, facet, history, cursor or error; order parity; injection | `test_a_base_list_holds_only_that_base_in_rows_totals_and_facets`, `test_the_master_table_filters_by_base_type_and_unassigned`, `test_order_missing_values_case_and_accents_are_the_same_on_both_databases`, `test_query_values_are_values_and_identifiers_are_allowlisted`, `test_the_attention_filter_partitions_the_list`, `test_a_page_costs_the_same_number_of_queries_whatever_its_size` (SQLite), folding parity tests on each backend |
| 5. 25,000 / 3,000 / five sessions | §6, `medir.py` |
| 6. Existing behaviour preserved | `test_public_output_and_operator_limits_are_unchanged`, and the whole existing suite |

Race tests hold the first request inside its write transaction, after its
authorization and before its write, and start the second: the second has not
completed 0.4 s later, the first commits, the second then completes. On SQLite
the wait is the single writer; on Postgres through the dispatcher it is the
workspace advisory lock (row-lock behaviour of the P2 helpers was shown in
A-2's `RowLocksPostgres` and is unchanged).

Existing tests changed, each for a change this packet orders:

- `tests/test_inventario.py`: the list maximum is 200; an amount without a
  currency now saves (moved from the rejection list to a positive check);
  `tipo_terreno` length is validated; **a key reused by another account now
  creates that account's own record** instead of returning the first one.
- `tests/test_inventario_postgres.py`: the same idempotency change.
- `tests/test_schema_v9.py`, `tests/test_roles_y_bases.py`: `tipo_terreno`,
  `base_id` and `custom` are now part of the record; the tests assert what stays
  closed instead (no client writes a base, role or custom map; a stored value no
  current column defines is shown to nobody).

Results on the head named in the PR:

| Check | Result |
|---|---|
| `./verificar.sh` (macOS, SQLite) | 1,032 Python tests OK, 121 skipped (all need Postgres); complete suite on Python 3.9.6 OK; JavaScript 120/120 |
| Disposable local Postgres 16 (Python 3.12, psycopg 3) | 1,032 tests, 0 skipped, OK |
| `ruff check server/ tests/`, `mypy server/` | clean; 47 source files |
| GitHub Actions | in the PR |

Not run: browser tests, any hosted or Preview environment, coverage.

## 8. Decisions made here, for review

1. `tipo_terreno`: at most 100 characters, single-spaced, free text.
2. Idempotency keys are scoped through the `operation` value of the existing
   table, and only the record id is stored. No migration.
3. A replay whose record left the caller's scope answers 404, not the old body.
4. `custom` shows current-base, unretired columns to everyone, administrators
   included; nothing else of `custom_json` is exposed.
5. Non-administrators do not see which bases a transfer went between.
6. Transfers out of an archived base, or of an archived terrain, are refused.
7. A published terrain is archived or restored by administrators only.
8. The transfer preview is `GET` on the transfer path with `base_id`, using
   `sin_asignar` for "no base" (the router drops empty query values).
9. Search and sort fold ASCII case and Spanish diacritics from one explicit
   table instead of full Unicode normalization, so both databases agree whatever
   their locale. Before, folding was Python's NFKD over the loaded inventory.
10. The `attention` filter stays exact and is evaluated in Python (§4).
11. Facets keep their existing "before business filters" meaning and gain `tipos`.

## 9. Reserved for later packets

- **2A:** the grid and navigation; custom-column definitions and editing of
  custom values (and their history projection); base, grant and transfer
  controls using the preview; exposing a base list for the master table's base
  filter labels.
- **3A:** attachment and location summaries in the record DTO; KMZ-aware
  located/unplaced filters; mounting B's widgets and handlers.
- **Schema, when wanted:** a stored attention flag; a stored folded search
  column or expression index.
- **Release notes to carry:** run `ANALYZE` after a bulk load or restore on
  Postgres; the list maximum changed from 250 to 200; idempotency keys are now
  per account and per base.
- The current interface still calls the previous contract and is not usable by
  operators; unchanged by this packet.

Stop for supervisory review. Nothing was merged or deployed; no real account or
data was used.
