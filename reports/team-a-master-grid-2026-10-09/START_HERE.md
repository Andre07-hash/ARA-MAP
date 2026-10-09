# Team A — packet 2A: editable table and work-base controls

An operator signs in and works in a table of the terrains of her work bases:
add a blank terrain, edit any cell, archive and restore. An administrator has
the master table, the unassigned records and any base, plus the bases, their
grants, their custom columns and transfers. Everything goes through the real
session and the accepted 1A routes; the new backend is the base-local custom
columns and one narrow account lookup.

- Instruction commit: `13840c0deaf7f78f79609126115d03769e27fd0a`,
  `reports/round-2-instructions-2026-10-09/TEAM_A.md`.
- **Base:** the round 2 checkpoint, PR #24, head
  `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` (accepted #22 + accepted #23;
  manifest `reports/round-2-baseline-2026-10-09/START_HERE.md`, CI green).
  Branch `claude/team-a/master-grid`; its draft PR targets
  `claude/integration/round-2-baseline`. The checkpoint was not changed after
  publication. #20, #22 and #23 are untouched.
- `origin/main`: `09452fd26d38319567dce28a89db100ea61c739a`, unchanged.
- **Schema stays 10.** No migration; no gap was found that needed one.
- No file of Team B was edited. The head commit and CI are in the PR.

## 1. What an employee sees

| Who | Entry point | Navigation | Views |
|---|---|---|---|
| Operator | `#/tabla` (default after sign-in) | Tabla · Catálogo público | Her granted, active bases; one at a time |
| Operator with no grant | `#/tabla` | same | «Todavía no tienes una base de trabajo», with *Volver a comprobar* |
| Administrator | `#/inventario` (unchanged) | Tabla maestra · Inventario · Bases · Mapas guardados · Catálogo público | Tabla maestra (all bases), Sin asignar, any base including archived ones |

- The administrators' default route is deliberately unchanged, so the legacy
  journeys are as they were; *Tabla maestra* is the first navigation item.
- An operator who follows an address into `#/inventario`, `#/bases`, `#/mapas`,
  `#/tabla/maestra` or a base she is not granted lands on `#/tabla`. The
  legacy lists are no longer requested for operators (they used to answer 403).
  The server remains the boundary: nothing was widened.
- No account creation, password or role console.

**Columns.** The fourteen core columns in spreadsheet order, with the 1A
mapping: Tipo de terreno, Nombre de terreno, Estado, Municipio, Superficie
(`superficie_m2`), HA (`superficie_ha`), Afectaciones % (`afectaciones_pct`),
Asking price, Asking $/m2, Comentarios (`notas_internas`), X (`lat`), Y (`lon`),
Archivos, KMZ. The global views add **Base**; a selected base adds its live
custom columns. Values are shown as stored and sent as typed: no currency is
assumed, nothing is converted or derived, X is latitude and Y longitude.
Publication fields are not in the table.

**Lists.** One bounded page from the accepted 1A endpoints: 50, 100 (default)
or 200 rows; search, the state / municipality / type filters, order, counts and
facets are the server's. Changing the view, a filter or the order starts again
at the first page (a cursor belongs to the query it came from); *Anterior* /
*Siguiente* replace the page, they do not accumulate rows. Filtering by a
custom column's value is out of scope. Located/unplaced is still XY-only.

## 2. Editing

- **Keyboard.** Every cell is a tab stop: Tab / Shift-Tab and the arrows move.
  Enter, F2, double click or typing opens the editor (typing replaces the
  value). In the editor Enter saves and keeps the focus on the cell, Tab saves
  and moves on, Escape cancels and returns the focus. Comentarios is a
  textarea: Shift+Enter is a line break. A choice column is a `<select>`, a
  date column a native date input.
- **Feedback.** A saving cell is marked «guardando» (`aria-busy`), a refused
  one `aria-invalid`; a polite status line announces *Guardando… / Guardado ·
  columna · versión N*, an alert line the errors. Unresolved cells are listed
  above the grid in *Cambios sin resolver* with their actions.
- **Versions.** Each save is a real `PATCH` with the row's `expected_version`.
  Saves of one row queue behind each other and each takes the version the
  previous one returned; rows do not wait for each other.
- **409.** The row is replaced by the authorized current row from the
  response; what the person typed stays in the tray beside the current value,
  with *Guardar el mío* (a new save at the new version) and *Descartar el mío*.
  Nothing is retried on its own.
- **No answer.** The cell becomes «sin confirmar». *Comprobar* reads the row
  and decides (`resolverIncierto`): saved (version moved by one and the value
  is ours), not saved (safe to send again), or changed by someone else (the
  conflict flow). The mutation is never replayed blindly.
- **Blank create.** *Agregar terreno* posts `{}` with a new `Idempotency-Key`
  that is kept until the outcome is known; *Reintentar* after an unanswered
  request sends the same key, so it cannot create a second terrain.
- **Invalid input** (not a number, an impossible date, too long) is not sent
  and not lost: it waits in the tray with *Corregir*. A server 422 is shown the
  same way with the server's message.
- **Read-only:** an archived base (banner, no *Agregar*, cells
  `aria-readonly`), an archived terrain (shown with *Incluir archivados*), and
  the application's read-only mode.

## 3. Custom columns (backend and UI)

Storage is schema 9's `inventory_column`, `inventory_revision.custom_json` and
`maestra_base_event`. New code: `server/columnas.py` (rules),
`server/repo/columnas.py`, `server/api/columnas.py`.

| Route | Capability | Check | Notes |
|---|---|---|---|
| `GET /api/maestra/bases/:bid/columnas` | `maestra.ver` | `require_base` | `?retiradas=1` adds retired ones (listed last) |
| `POST /api/maestra/bases/:bid/columnas` | `columnas.gestionar` | `reverificar_base(exclusivo)` | `{nombre, tipo, opciones?}` + `Idempotency-Key` |
| `PATCH /api/maestra/bases/:bid/columnas/:cid` | `columnas.gestionar` | same | `{expected_version, nombre?, opciones?, posicion?}` |
| `POST …/columnas/:cid/retirar`, `…/restaurar` | `columnas.gestionar` | same | `{expected_version}` |
| `GET /api/maestra/operadores` | `bases.gestionar` | role | `?q=&limit=`; see §4 |

60 routes: 6 anonymous, 54 private, each with a declared capability; the
existing registry tests walk the new ones. `:cid` is the bare UUID; everywhere
else the id is `custom:<uuid>`. Operators hold `columnas.gestionar` (accepted
in P2), so an operator manages the columns of a base she is granted.

**Definition contract (frozen for this packet)**

- `{id, base_id, nombre, tipo, opciones, orden, version, retirada, retired_at,
  created_at, updated_at}`.
- **Types** `texto`, `numero`, `opcion`, `fecha`. The type and the id never
  change; `tipo` in a PATCH is a 422. No attachment type; core columns are not
  rows and cannot be retired.
- **Name:** single-spaced, 1–100 characters; not one of the fourteen core
  labels (422); unique among the base's *live* columns comparing with case and
  Spanish accents folded (409 `nombre_duplicado`). A retired column frees its
  name and cannot be restored while another live column holds it.
- **Choices:** 1–100 distinct single-spaced strings of 1–100 characters. A
  PATCH sends the complete list, which must keep every existing choice in order
  before any new one: additions only. Removing, renaming or reordering is 409
  `opciones_solo_se_agregan` (deferred, as instructed).
- **At most 50 live columns per base** (409 `limite_columnas`, also on restore).
- **Order:** `posicion` is the 0-based place among live columns. Only the moved
  definition gets a new version and event; the others are renumbered without
  one. Retiring does not renumber: a restored column returns where it was.
- **Versions and audit:** every definition change is a compare-and-set on the
  column's own `version` and writes one `maestra_base_event` with `column_id`,
  that version, actor and time (`columna_crear`, `columna_cambiar`,
  `columna_retirar`, `columna_restaurar`). A stale version is 409 `conflict`
  with the current definition. A request that changes nothing writes nothing.
  **No terrain version, and no base version, moves** for any of it.
- **Create is idempotent:** the key is stored under
  `columna:<base>:<actor>` in `inventory_operation_result` with only the new
  id; same key and body returns the same definition, a different body is 409
  `idempotency_conflict`.
- **Existing definitions** (rows written before these rules, e.g. by tests or a
  future import) are served as stored: a longer name stays until renamed and
  must then meet the limit; `opciones_json` that is not a list of strings reads
  as no choices; the 50 limit only refuses new or restored columns.
- An archived base's definitions are readable by administrators and changeable
  by nobody (409 `base_archivada`). Out of scope is the base's 404 before any
  answer about the column, the body or the version; a column of another base
  is the same «La columna no existe» 404 as a missing one.

**Values** — `PATCH /api/inventario/terrenos/:id` accepts a sibling
`custom: {"custom:<uuid>": value}` beside `expected_version`, `changes` and
`confirm`. Core-only clients are unchanged.

- A key must be a live column of the terrain's **current** base. Unknown,
  retired and another base's ids get the same 422 («Columna desconocida o
  retirada.»), for administrators too. An unassigned terrain accepts none.
  Creating a terrain still takes core fields only.
- `texto`: a string, trimmed, at most 2,000 characters, no NUL; blank is null.
  `numero`: a JSON number, finite; booleans and numeric strings are refused; it
  is stored as a double, as core numbers are. `fecha`: `AAAA-MM-DD` naming a
  real calendar day, stored as that text, no time zone. `opcion`: exactly one of
  the column's choices. `null` clears; a key left out keeps what is stored.
- Core and custom changes of one request are one terrain version, one
  revision and one event, or none: a single bad value of either kind is a 422
  and nothing is written.
- The stored map is merged, never rebuilt from what the caller was shown:
  values of other bases and of retired columns are copied forward untouched
  (a cleared key is removed). An edit that touches no custom value copies
  `custom_json` byte for byte, as before.
- A stale `expected_version` is the 1A conflict with the current, caller-aware
  row. The PATCH has no idempotency key: its version is the guard, and the
  client resolves an unanswered save by reading the row (§2).

**History** is the accepted A2 shape, now with a real writer:

```json
{"changes": {"estado": {"before": null, "after": "Jalisco"},
             "custom:264c71a5-…": {"before": null, "after": "En pausa"}}}
```

Stable `custom:<uuid>` keys, scalar `before`/`after`, no nested map and no
label. The A2 projection is unchanged: a non-administrator sees a custom entry
only while that column is live in the terrain's current base.

**Locks.** A definition change takes the base row exclusively
(`reverificar_base(…, exclusivo=True)`); a cell save holds it shared through
`reverificar_terreno`, then reads the base's live columns. So a retirement and
a cell save in one base never interleave: whichever is second sees the first.
Transfers, grant changes and base archiving keep P2's order (user → session →
terrain → base).

Real requests and responses, fictional data:
[examples/columnas.json](examples/columnas.json) (regenerate with
`generar_ejemplos.py`).

## 4. Administration

All through the accepted routes, from *Bases y accesos* and the row's *⋯*.

- **Bases:** create, rename, archive, restore, each with the base's
  `expected_version`. After any error the list is reloaded, so a 409 shows the
  base as it is now.
- **Grants:** the dialog loads the current set and version and replaces the
  full set. On 409 it says so, reloads what the server holds and applies
  nothing of the stale selection. Inactive accounts can keep or lose a grant
  but cannot be newly checked.
- **Account lookup (new, narrow):** `GET /api/maestra/operadores?q=&limit=`,
  `bases.gestionar` only. Operators only (no administrators), `{id, login,
  display_name, active}` and nothing else, at most 200 per answer with the
  match count; `q` is a folded substring of login and name. It was needed
  because the access response lists current grantees, not who could be added.
- **Terrain archive / restore:** from the row's dialog, with confirmation; an
  operator's attempt on a published terrain shows the server's 403.
- **Transfer (administrators):** choose a destination; the real preview shows
  who will be able to open it and which columns stop showing (and whether this
  terrain holds a value in each); *Transferir* is disabled until the explicit
  checkbox. It sends the version of the row the person saw; a 409 refreshes
  the row and the preview and asks again.

**Leaving a scope.** On logout, expiry, another account, a lost grant, a
transfer out or a role change the table drops its rows, pending and unsaved
cells, queued saves, custom definitions, column headers, filter options and
file-slot mounts, and aborts its request. Each scope has a generation number;
a response for an older one is discarded, so an old request is never painted
under a newly selected account or base. If unsaved work was dropped the
message says so without quoting it. A session that expires with unsaved cells
keeps them behind the sign-in dialog; cancelling clears them; signing in as
someone else discards them.

## 5. Seams for 3A / 3B

`web/components/tabla/ranuraArchivos.js` is the host side of the adapter frozen
in INTERFACES.md:

```text
montarRanura({container, terrenoId, tipo, soloLectura, resumen, onCambio, onError})
  -> {container, update({soloLectura, resumen}), destroy()}
registrarWidgetDeArchivos(fabrica)      // 3B: same mount() contract
```

- Mounted in each `core:archivos` / `core:kmz` cell (`tipo` `pdf` / `kmz`) and
  in the row's detail dialog. A new mount per terrain; `destroy()` on page
  change, row repaint, scope loss and dialog close. After `destroy()` the
  wrapper drops `onCambio` / `onError`.
- `resumen` is `undefined` in 2A. The placeholder shows «No disponible aún»:
  no count, no control, nothing that reads as zero files.
- For 3A: fetch the 1B summaries for the page's ids and pass them as `resumen`;
  on `onCambio({terrenoId})` refresh that terrain's summary only. A file
  change must not touch the row's version or its unsaved cells: the mounts are
  outside the cell-state map by construction.

Other modules: `web/lib/tabla.js` (pure rules: columns, cell parsing, list
query, row queue, uncertain-save resolution), `web/components/tabla/Tabla.js`
(the grid and its state), `dialogos.js` (detail, transfer, columns, bases,
grants), `web/styles/tabla.css`. Shell wiring in `web/components/app.js`,
`web/lib/router.js`, `web/lib/api.js`.

## 6. Browser evidence

`tests/e2e/tabla-integrada.mjs`: a real Chrome (154) against the real local
server with real sessions and persistence; nothing mocked. Two cases let a
request reach the server and drop only its answer. Fictional accounts.
**13 journeys, all pass**: [evidencia/recorridos-navegador.log](evidencia/recorridos-navegador.log),
screenshots in [evidencia/capturas/](evidencia/capturas/).

```bash
python3 tests/e2e/tabla_servidor.py --puerto 8433     # terminal 1: disposable, fresh each run
cd tests/e2e && npm ci
ARA_URL=http://localhost:8433 node tabla-integrada.mjs ../../salida-capturas
```

| Journey | Screenshots |
|---|---|
| Administrator: role-aware navigation, 14 core columns + Base, create bases, grants, four custom columns; core and duplicate names refused | 01–03 |
| Operator: only her base, no legacy call; blank create; all 12 editable core cells and all 4 custom types by keyboard; values read back exact (X=lat, Y=lon, no currency, nothing derived); reload; second session | 04, 05 |
| Keyboard only: Tab, Shift-Tab, arrows, type-to-replace, Escape, Enter, F2, Tab-to-save, focus restored; invalid input kept; server 422 | 06 |
| Two users, one cell: conflict keeps both values; *Guardar el mío*; *Descartar el mío* on a custom cell | 07 |
| Lost response: checked, one PATCH only; lost blank create retried with the same key, one terrain | 08 |
| Archive / restore a terrain; archived row read-only; detail mount of the file slots | 09, 10 |
| Transfer: no-change, real preview (grantees, hidden columns with values), disabled until confirmed; the source operator's next save removes the row with no leak; back again with its values | 11, 12 |
| Custom columns: rename, add choice, reorder, retire (value hidden), history, restore (value back) | 13, 14 |
| Grants: concurrent change shown, not overwritten; grant loss clears rows, headers, filters and unsaved text; regrant | 15, 16 |
| No grant: useful empty state; administrators' addresses not reachable | 17 |
| Logout with a list in flight; next account on the same page; session revoked while saving | 18 |
| Archived base: read-only for the administrator, gone for the operator | 19 |
| Anonymous startup (three calls only) and the administrators' Inventario, Bases, Mapas, Catálogo | 20 |

Found by these journeys and fixed here: column headers and filter options of a
lost base stayed in the DOM; a search typed just before another control
changed was dropped; a dialog opened over another took the first one's
accessible name (`web/components/ui/dialog.js` now gives each its own title
id); and the legacy Inventario asked for 250 rows a page, which the accepted
1A maximum of 200 has refused since #22 (`PAGE_LIMIT` is now 200).

## 7. Measurement

`tests/e2e/tabla-medicion.mjs`, raw output in
[evidencia/medicion-navegador.json](evidencia/medicion-navegador.json). 25,000
synthetic terrains: 3,000 in one base granted to five operators, 1,000
unassigned, 21,000 over ten bases. Chrome 154, one developer Mac (Apple
silicon), server and SQLite on the same machine, loopback.

| Measure | Result | Local target |
|---|---|---|
| Operator, 3,000-record base: full app reload to 100 rows painted and a cell focused | median 102 ms, max 114 ms (5 runs) | 2,000 ms ✔ |
| Administrator, master table over 25,000: reload to 100 rows | median 183 ms, max 187 ms | 2,000 ms ✔ |
| Requests for that first page (operator) | 5: config, session, bases, columns, list | |
| List response, 100 rows | 173 kB JSON | |
| DOM at 100 rows / 200 rows | 100 rows, 1,400 cells, 4,357 nodes / 200 rows, 7,771 nodes | bounded ✔ |
| Key to two painted frames: open editor by typing / key inside editor / arrow move | median 33 / 30 / 29 ms, max 34 ms (the method itself waits two frames, about 16–33 ms) | 100 ms ✔ |
| Enter to «guardando» shown / to saved | median 4 ms / 23 ms, max 12 / 25 ms | 100 ms ✔ |
| Next / previous page, 3,000-record base, 60 changes | median 61 ms, max 80 ms | |
| Sort by name / search (includes the 300 ms typing pause) | 46 ms / 387 ms | |
| Master table next page (20) / switch base (24) | median 128 ms / 56 ms | |
| JS heap after forced GC: start → after 60 page changes → with 200 rows | 2.83 → 3.82 → 3.99 MB | |
| Same, administrator: start → after 20 pages and 24 base switches | 2.77 → 3.91 MB; DOM nodes 4,644 → 4,068 | |
| Five browsers, 50 edits of 50 different rows at once | 50 saved, 0 unresolved; median 49 ms, max 107 ms | |
| Five browsers, one cell, same version | 1 saved, 4 shown as conflicts, final version 2 | |

What this says and does not say:

- Both local targets are met with a wide margin on this machine. No miss to
  report.
- Rows do not accumulate: the row count equals the page size after 60 page
  changes and the DOM node count is flat. The heap is about 1 MB higher after
  repeated paging or base switching than at start. I did not run long enough
  to show that it plateaus; it is small and not growing with the DOM, but it
  is not proven to be zero growth.
- **SQL statement counts were not re-measured.** No list statement changed
  from 1A (7 per list). The new columns request is one SELECT after the scope
  check, and a cell save with custom values adds one SELECT of the base's
  live columns and one of the stored map.
- One machine, loopback, fictional data. Not a hosted measurement, not a
  capacity claim, and not Postgres in the browser (the Postgres evidence is the
  HTTP suite below).

## 8. Verification

`tests/test_columnas_maestra.py`, 13 tests on each database through the real
dispatcher with real sessions (the A-2 fixture).

| Required evidence | Tests |
|---|---|
| 1. Definition CRUD, idempotency, bounds, audit, scope | `test_definitions_are_created_listed_and_idempotent_per_actor_and_base`, `test_definition_input_is_bounded_and_the_type_is_fixed`, `test_rename_order_retire_and_restore_are_versioned_and_audited`, `test_definitions_follow_the_base_scope_and_an_archived_base_is_read_only` |
| 1. Custom PATCH validation, atomicity, audit, projection | `test_values_are_validated_by_type_and_saved_as_sent` (20 refused values, incl. Infinity, NaN, 10^400, impossible dates), `test_only_live_columns_of_the_current_base_accept_a_value`, `test_core_and_custom_changes_are_one_version_or_none` |
| 1. Real writes through transfer / back / retirement, on every surface | `test_written_values_and_history_follow_the_current_base`: values and history written by the PATCH; detail, list, search, 409 body, create replay and history checked for a source-only and a destination-only reader; hidden values stay stored through a destination edit; retire and restore; administrator audit whole; stored events never rewritten; every stored change is a scalar pair |
| 2. Both race orders | `test_a_cell_save_and_a_retirement_are_serialized_in_both_orders`, `…_and_a_transfer_…`, `…_and_a_grant_loss_or_base_archive_…`, `test_concurrent_definition_changes_and_grant_changes_do_not_overwrite` (two renames, two creates with one key, two grant replacements). The second request is shown not to complete while the first holds its write boundary; no partial revision; no hidden value in a refusal |
| 2. Preserved | A1, A2, A3 tests of `tests/test_registros_maestra.py` unchanged and passing; 1B independence in `tests/test_composicion_ronda2.py` |
| Account lookup | `test_the_operator_lookup_is_bounded_minimal_and_for_administrators` |
| 3. Browser journeys | §6 |
| 4. 25,000 / 3,000 / five sessions | §7 |
| Client rules | `tests/js/tabla.test.mjs` (8): columns, cell parsing, list query, row queue, uncertain save, routes by role |

Existing tests changed, each for a stated reason:

- `tests/js/sesion.test.mjs`, `tests/js/inventario.test.mjs`: the page size
  literal 250 → 200 (the `PAGE_LIMIT` repair in §6).
- `tests/test_registros_maestra.py:562`: `%`-format → f-string, the ruff
  finding recorded in the checkpoint manifest. No behaviour.

Results on the head named in the PR:

| Check | Result |
|---|---|
| `./verificar.sh` (macOS, SQLite) | 1,147 Python tests OK, 178 skipped (all need Postgres); complete suite on Python 3.9.6 OK; JavaScript 128/128 |
| Disposable local Postgres 16 (Python 3.12.15, psycopg 3.3.6) | 1,147 tests, 0 skipped, OK |
| `ruff check server/ tests/` (0.16.10), `mypy server/` (2.4.0) | clean; 52 source files |
| Browser journeys, real Chrome, SQLite server | 13/13 |
| GitHub Actions | in the PR |

Not run: coverage measurement; any hosted or Preview environment; the browser
journeys against a Postgres-backed server; the older `smoke.mjs` /
`inventario-integrado.mjs` suites (the legacy and public checks are journey 13);
signing in as a different account over an expired session with unsaved cells, and a role
change detected on revalidation (both are coded, neither has a journey); a screen reader (labels, roles and focus were checked through the accessibility
tree Playwright uses, not with assistive technology); mutation testing of the
new tests.

## 9. Decisions made here, for review

1. Administrators keep `#/inventario` as their default route; operators get
   `#/tabla`. One line to change if the master table should be the default.
2. Column names are unique per base among live columns, and may not reuse a
   core label.
3. Limits: name 100, text value 2,000, 100 choices of 100 characters, 50 live
   columns per base.
4. `posicion` moves one column and versions only that one.
5. Custom numbers are stored as doubles (7 is stored as 7.0), like core ones.
6. Unknown, retired and other-base column ids are one 422, for every role.
7. The account lookup is a new route, operators only, capped at 200.
8. A cell is saved on Enter, Tab and on leaving the editor (blur).
9. The table is one page at a time with previous/next, not infinite scroll.
10. Every cell is a tab stop, as the instruction's Tab / Shift-Tab asks; a
    roving-tabindex grid would be fewer stops if preferred later.

## 10. Limits and what is reserved

- **3A:** real attachment and location summaries in the row and the detail;
  KMZ-aware located/unplaced; mounting B's widgets and handlers; a map.
- **Not built:** filters on custom values; removing or renaming a choice;
  changing a column's type; bulk edit, paste or undo; saved views; editing
  `moneda`, availability, address or the public fields from the table (the
  existing Inventario editor still does that for administrators); a history of
  definition changes on screen (it is stored in `maestra_base_event`).
- History shows a custom change under its `custom:<uuid>` key, not the
  column's current label.
- A terrain created while a filter or order is active is shown first, marked
  «Nuevo», until the page reloads; it may not belong on that page.
- Narrow screens scroll the grid sideways; the layout was checked at 1440 px.
- Release notes to carry, beyond 1A's: none for the schema. The new routes
  need no data step.

Stop for supervisory review. Nothing was merged to a PR or to main, nothing
was deployed, and no real account or data was used. 3A was not started.
