# Team A preparation report — master table, roles and integration

Team A · first assignment (preparation) · October 7, 2026

| Item | Value |
|---|---|
| Instruction commit | `bbd640dec00c055b43454f61b35861c38063b550` on `codex/supervisor-completion-brief` (PR #5, open). Read with `git show <sha>:<path>`; the checkout was not switched. |
| Later instruction commits also read | Branch tip `c755429ef4ea160f460d93d5803352ffcd457453`: Team B preparation review, B-1 packet and B-1 acceptance. They state that Team A's assignment is unchanged; this report follows them where they constrain the shared contract. |
| Documents read | `GITHUB_HANDOFF.md`, `MASTER_PLAN.md`, `TWO_TEAM_DELIVERY_PLAN.md`, `TEAM_A_START_HERE.md`; Team B's `REPORT.md` at PR #8 head `e93649c4`; baseline `AGENTS.md` and `CLAUDE.md` |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`. No application code is changed by this report. |
| Branch / PR | `claude/team-a/preparation` · draft PR against `main` |
| Status | Preparation only. The experiment is **disposable** and uses **fictional** values. Nothing here is hosted, Postgres or real-data evidence. |

---

## 1. Baseline and state of open work

**Recommended baseline: `origin/main` at `09452fd2`**, the same commit Team B used. It already contains the inventory, individual accounts and schema 8.

| Open work | Head | Relevance to Team A |
|---|---|---|
| PR #4 `codex/fix-vercel-inventory-api` (draft) | `077b4e0f` | **Prerequisite for hosted verification, not for local work.** On Vercel the `:path*` rewrite adds a `path` query parameter, and `inventario.parse_query` rejects unknown parameters, so the hosted inventory list fails. The master table uses that same list route. The fix is 14 lines in `api/index.py` plus a regression test. It also changes `vercel.json` to enable branch previews, which is a separate decision. Recommendation: land the `api/index.py` fix and its test before the first hosted check of the grid; decide the `vercel.json` line on its own. |
| PR #6 `claude/excel-onedrive-refresh` (draft, parked) | `9d452790`; reviewed implementation `415eb2640a42d99687fcef7a68ac3575ce8a651e` | **Preserved, not merged.** Merge base with main is `5cbf6718`. It edits `server/db.py` (+187), `server/app.py`, `server/auth.py`, `server/postgres.py`, `web/components/app.js` and sets `SCHEMA_VERSION = 9`. Team A's work will touch the same shared files, so that branch will need a rebase and a new schema number when Excel resumes. Nothing is taken from it. |
| PR #8, PR #9 (Team B) | `e93649c4`, `efc36281` | Reports and a standalone parser. No shared file is touched. No conflict with this plan. |

**Schema number.** Main is at 8. Team A takes **9** for its first migration, from main's own history. PR #6's claim on 9 is a reconciliation item for whoever resumes Excel; no number is reserved or skipped for it.

### What the existing inventory already provides

Checked by reading the code and by `experiment/baseline_probe.py` (output in `experiment/baseline_probe.txt`):

| Need in the master plan | Baseline today | Evidence |
|---|---|---|
| Stable internal ID | `inventory_terrain.id` is a UUID assigned by the server | Probe 1 |
| Create with every business field blank | Works: `POST /api/inventario/terrenos` with `{}` validates and saves; name stays `NULL` | Probe 1 |
| Partial entry (only X, only a price…) | Works; half a coordinate pair saves | Probe 3 |
| Type validation that does not destroy the record | Per-field errors, HTTP 422 with a `fields` map; nothing is saved on error | Probe 3 |
| Lost-update protection | Compare-and-set on `version`; stale write raises a conflict and returns the latest record | Probe 4 |
| History with author | Append-only `inventory_event`, one per version, with before/after per field | Probe 4 |
| Retry-safe creation | `Idempotency-Key`, stored in the same transaction | `server/repo/inventario.py` `create` |
| Individual accounts and revocable sessions | `team_user`, `team_session`; deny-by-default dispatcher | `server/auth.py`, `server/app.py` `_dispatch` |
| Roles | **None.** `team_user` has no role column; every account has identical powers | Probe 5 |
| Tipo de terreno, Comentarios | **No such fields**; both are rejected as unknown | Probe 3 |
| Create a base without importing a file | **Not possible.** A `base` row is only created by an import | `repo.bases.create` is called only from the import handlers; there is no `POST /api/bases` |
| Custom columns | **None** | — |
| Editable grid | **None.** `TerrainTable.js` is read-only; editing is a separate full-page form (`TerrainEditor.js`) | — |

**Conclusion: extend the inventory into the master record. Do not create a second terrain store.** The missing pieces are one field, work bases that can be created empty, per-base custom columns, roles with per-person access, and the grid.

### Reusable code

| Code | Reuse |
|---|---|
| `server/repo/inventario.py` (create, update, `_claim`, history) | As is. Custom values ride in the immutable revision, so history and conflicts cover them with no new mechanism. |
| `server/inventario.py` `clean_changes`, `_clean_value`, `_number` | As is for core fields; one rule removed (§2.3). |
| `server/auth.py` sessions, password hashing, throttle | As is; role and capabilities are added. |
| `scripts/cuentas.py` | Extended with a role argument and a `rol` subcommand. |
| `web/lib/inventario.js`: `CAMPOS`, `leerNumero`, `textoDeValor`, `cambiosDelFormulario`, `analizarConflicto`, `crearIntento`, `reunirPaginas` | As is. `analizarConflicto` already tells whether another person's save touched the same fields; the grid uses it to retry non-overlapping edits. |
| `web/components/inventory/datasets.js` (`cargar`, `reemplazarRegistro`) | As is: loads every page of a query and replaces one record after a save. |
| `web/components/inventory/TerrainHistory.js`, `web/components/ui/dialog.js`, `toast.js` | As is, from the detail panel. |
| `web/components/terrain/TerrainTable.js` | Not extended: it serves saved maps and comparisons. The grid is a new component. |

---

## 2. Proposed master-record contract

Fictional examples: `examples/02-columnas.json`, `03-registro.json`, `04-editar-celda.json`.

### 2.1 Identity and work bases

The master record **is** an `inventory_terrain` row. Its ID is the existing UUID. Existing IDs, revisions and events are kept unchanged. The legacy importer's identity (name + state + municipality + area) is not applied to master records.

**New owner requirement (§3.1): records are grouped into editable work bases**, for example "Base Ejemplo". A work base is created empty, with no file upload, and terrains are then added in the grid. This is new: today a base exists only as the result of importing a spreadsheet.

```
maestra_base
  id          TEXT PK (uuid)
  nombre      TEXT NOT NULL
  creado_en/por, actualizado_en/por
  archivado_en/por              reversible; nothing is deleted

inventory_terrain.base_id   TEXT NULL → maestra_base(id)
```

A terrain belongs to at most one work base. `base_id NULL` means "not assigned": visible to administrators only. Records that exist before the migration stay unassigned; none is moved or invented. An administrator can move a record between bases; that is a versioned, audited change like any other.

Work bases are a different thing from the legacy `base` table (imported spreadsheets, integer IDs, frozen into saved maps). The legacy table is not touched. The interface must name the two differently (decision D8).

**This departs from MASTER_PLAN §4**, which describes one master table with filtered bases derived from it. See §3.1 and decision D0.

### 2.2 Core columns

Stable column IDs use the prefix `core:`; custom columns use `custom:<uuid>`. Team B's proposed `core:archivos` and `core:kmz` are accepted as written.

| Core column | Column ID | Stored in | Change |
|---|---|---|---|
| Tipo de terreno | `core:tipo_terreno` | `inventory_revision.tipo_terreno` | **New** nullable text column |
| Nombre de terreno | `core:terreno` | `terreno` | — |
| Estado | `core:estado` | `estado` | — |
| Municipio | `core:municipio` | `municipio` | — |
| Superficie | `core:superficie` | `superficie_m2` | — |
| HA | `core:ha` | `superficie_ha` | — |
| Afectaciones % | `core:afectaciones` | `afectaciones_pct` | — (stored as a fraction, entered and shown as a percentage, as the editor does today) |
| Asking price | `core:asking_price` | `asking_price` | — |
| Asking $/m2 | `core:asking_m2` | `asking_m2` | — |
| Comentarios | `core:comentarios` | `notas_internas` | Reuse the existing private long-text field (decision D4) |
| Archivos | `core:archivos` | Team B | Slot only |
| KMZ | `core:kmz` | Team B | Slot only |
| X | `core:x` | `lat` | — |
| Y | `core:y` | `lon` | — |

The existing fields outside the fourteen (`direccion`, `afectaciones_m2`, `moneda`, `price_on_request`, `availability`, `public_description`, `contacto`) stay in the record and remain editable from the detail panel. `moneda` is the optional currency control next to the price cells. Nothing is dropped.

### 2.3 Validation that conflicts with blank or partial entry

One rule conflicts; everything else already allows it.

| Rule today | Where | Proposal |
|---|---|---|
| Typing a price without a currency is rejected (`"Indica la moneda del precio"`) | `server/inventario.py` `check_merged`; probe 2 | **Remove from saving.** A price with `moneda = NULL` saves as "currency unknown". The publication blocker `currency_required` already covers publishing and stays. |
| A blank record carries nine `attention` reasons (name, location, area, price…) | `inventario.attention`; probe 1 | No server change. They describe readiness to publish, not errors. The grid does not show them as cell errors. |
| Negative amounts, non-numbers, latitude/longitude out of range are rejected | `_number` | Keep. This is the "sensible type validation" the plan asks for; the rest of the record is untouched. |

Sorting and filtering by price keep the existing rule: amounts in different or unknown currencies are never ranked together.

### 2.4 Custom columns, per work base

```
inventory_column
  id            TEXT PK          'custom:<uuid>'
  base_id       TEXT NOT NULL    → maestra_base(id): the column exists only in that base
  nombre        TEXT NOT NULL
  tipo          TEXT NOT NULL    CHECK IN ('texto','numero','opcion','fecha')
  opciones_json TEXT             for 'opcion'
  orden         INTEGER NOT NULL
  creado_en/por, actualizado_en/por
  retirado_en/por                reversible; purge is a separate later operation

inventory_revision.custom_json   TEXT   {"custom:<uuid>": value, …}
```

The fourteen core columns exist in every work base. **Custom columns belong to one work base**, so the person working in "Base Ejemplo" can add the data that matters there without changing anyone else's table. Whoever may edit a base may add, rename and retire its custom columns.

Values live in the revision, keyed by column ID, so renaming a column changes no stored value and every edit is versioned and audited like a core cell. Retiring a column hides it and keeps its values. Moving a terrain to another base keeps its custom values stored; they show again if it returns. Attachment-type custom columns are **not** in the first packet; they wait for Team B's contract.

Filtering already happens in Python over the whole inventory (`repo.all_records`), so a JSON column needs no SQL that differs between SQLite and Postgres. Ceiling: a few thousand records, the same ceiling the list has today.

### 2.5 Editing and conflicts

The existing route and body are kept: `PATCH /api/inventario/terrenos/:id` with `{expected_version, changes}`, plus an optional `custom` map. One cell edit is one small PATCH.

Two people editing **different cells of the same row** would collide on the record version. The server answer is unchanged (HTTP 409 with the latest record). The grid then:

- retries once against the new version when the other person's changes touch other cells;
- shows both values in the cell and lets the user choose when they touched the same cell.

No edit is lost silently and no server merge logic is added. Saves for one record are sent one at a time; different records save in parallel.

### 2.6 Routes

| Route | Status |
|---|---|
| `GET /api/maestra/bases` | New: the work bases the caller may open |
| `POST /api/maestra/bases`, `PATCH /api/maestra/bases/:bid`, `POST …/:bid/archivar`, `…/restaurar` | New: create empty, rename, archive, restore |
| `GET/PUT /api/maestra/bases/:bid/acceso` | New, admin only: which operators may open this base |
| `GET /api/maestra/bases/:bid/terrenos`, `POST /api/maestra/bases/:bid/terrenos` | New paths over the existing list and create logic, scoped to one base |
| `GET/PATCH /api/inventario/terrenos/:id`, `GET …/historial` | Existing; reused. Access is decided by the base the terrain belongs to |
| `POST /api/inventario/terrenos/:id/archivar`, `…/restaurar` | New. `archived_at` exists but has no route today. "Remove" in the interface is this reversible archive |
| `GET /api/maestra/bases/:bid/columnas` | New: core + that base's custom column definitions |
| `POST /api/maestra/bases/:bid/columnas`, `PATCH/DELETE …/columnas/:cid` | New: add, rename, reorder, retire/restore |
| `GET/POST /api/inventario/terrenos` (unscoped) | Existing; becomes admin only, since it spans every base |

The record routes keep the `/api/inventario/` prefix. Renaming them would break Team B's proposed routes and the existing tests for no user benefit.

---

## 3. Proposed role and capability contract

Fictional example: `examples/01-sesion.json`.

### 3.1 Requirement relayed with this assignment

The Team A account holder stated, on October 7, to be confirmed through the supervisor:

1. For now there is one operator, who works in one base named after her (called "Base Ejemplo" in this report).
2. That base can be **created from nothing**, without uploading a spreadsheet or PDF. Either she creates it or an administrator creates it for her.
3. Inside it she may see, add, edit and remove terrains, upload files and KMZ layouts, and **add columns that exist only in that base**.
4. She can see and change **nothing outside that base**.
5. Access for her or for any later operator may be changed over time.

This is stricter and more specific than MASTER_PLAN §6, and it changes §4 of that plan: instead of one shared master table, there are several editable work bases with access granted per person. The proposal below implements it and marks the difference as decision D0, because it also affects Team B (access is decided per terrain, through its base) and the later "filtered base and map" phase.

### 3.2 Model

Two things decide access: **what** a role may do, and **where**.

**What — role and capabilities.** `team_user.rol TEXT NOT NULL CHECK (rol IN ('admin','operador'))`. A role is a fixed set of capabilities defined in `server/auth.py`. Routes check capabilities, never role names.

| Capability | Admin | Operator | Covers |
|---|---|---|---|
| `maestra.ver` | ✔ | ✔ | Open a work base: list, detail, history, columns, its map |
| `maestra.editar` | ✔ | ✔ | Add terrain, edit core and custom cells |
| `maestra.archivar` | ✔ | ✔ | Remove (archive) and restore a terrain |
| `columnas.gestionar` | ✔ | ✔ | Add, rename, reorder, retire that base's custom columns |
| `archivos.ver` | ✔ | ✔ | List, open, download (Team B) |
| `archivos.subir` | ✔ | ✔ | Upload, replace, choose layout (Team B) |
| `archivos.retirar` | ✔ | ✔ | Retire a file (Team B) |
| `bases.gestionar` | ✔ | — | Create, rename, archive work bases; grant and revoke access; move terrains between bases |
| `derivados.ver`, `derivados.gestionar` | ✔ | — | Legacy workspace: imported bases, saved maps, folders, formats, import, export |
| `usuarios.gestionar` | ✔ | — | Accounts and roles |

**Where — scope.** An administrator's capabilities apply to every work base. An operator's apply **only inside the work bases granted to that person**:

```
maestra_base_acceso
  base_id   TEXT NOT NULL → maestra_base(id)
  user_id   TEXT NOT NULL → team_user(id)
  otorgado_en, otorgado_por
  PRIMARY KEY (base_id, user_id)
```

So the operator, granted "Base Ejemplo", has full working control inside it and reaches nothing else: no other work base, no unassigned record, no imported base, no saved map, no import or export, no accounts. Granting her a second base, or adding a second operator to hers, is one row. Everything an operator can remove is reversible; permanent deletion is not offered to anyone in this packet.

Who creates a work base is decision D1b. The proposal: administrators create it and grant access, which matches "or we create it for her" and needs no extra rule. Letting operators create their own bases is one more capability (`bases.crear`, automatically granted to its creator) if the owner prefers it.

### 3.3 Enforcement

- **Capability, checked in the dispatcher.** `server/auth.py` maps every private route to a capability. `server/app.py` `_dispatch` checks it right after it resolves the session, before the handler runs. A missing capability returns HTTP 403 with `{"code": "forbidden", "capacidad": "…"}`; no session returns the existing 401.
- **Scope, checked where the record is known.** `auth.require_base(request, base_id, capacidad)` and `auth.require_terreno(request, terreno_id, capacidad)`; the second resolves the terrain's base first. A terrain or base outside the caller's scope answers **404, not 403**, so an operator cannot learn that other bases or records exist.
- **Deny by default.** A test fails if any registered private route has no declared capability. All 41 routes registered today get one; the legacy workspace routes map to `derivados.*`. A second test walks every route that takes a terrain or base ID and asserts an operator without a grant gets 404.
- **Session payload.** `GET /api/session` adds `user.rol`, `capacidades` and `alcance` (the work bases the user may open). The client uses it only to choose what to show. Hiding a button is never the control.
- **Changing a role ends that user's sessions**, reusing the existing `credential_revision` mechanism. Granting or revoking a base takes effect on the next request, because scope is read from the database on every call.
- **Helper for Team B's handlers:** `auth.require_terreno(request, terreno_id, "archivos.subir")`. This is the per-terrain signature Team B asked for in R2. Every file and geometry route must call it, including batch geometry reads, where each requested ID is checked.
- **Audit.** Role, account and access changes are recorded with actor and time (`team_user_event`, append-only).

### 3.4 Account, role and access management

- First packet: `scripts/cuentas.py crear … --rol`, `cuentas.py rol USUARIO admin|operador`, and the admin routes for work bases and their access (§2.6). This is enough to create the first work base and give the operator access to it.
- Later packet: an admin screen in the app to create accounts, reset passwords, deactivate, change roles and grant bases, behind `usuarios.gestionar` and `bases.gestionar`. This is what lets the company manage access without a terminal.
- **Migration of existing accounts.** The new column defaults to `operador` with **no base granted**, which is no access at all. The release step lists every account and names the administrators explicitly. No account becomes an administrator by default.

---

## 4. Table interaction concept

A sketch for this checkpoint; no prototype code is proposed for production.

```
 Base Ejemplo ▾                        128 terrenos · Guardado 18:02      [Buscar…] [Filtros] [+ Columna] 
 ┌────┬──────────────┬────────────┬───────────┬────────────┬──────────────┬──────────┬───────────┬─────┐
 │    │ Nombre       │ Tipo       │ Estado    │ Superficie │ Asking price │ Archivos │ KMZ       │  …  │
 ├────┼──────────────┼────────────┼───────────┼────────────┼──────────────┼──────────┼───────────┼─────┤
 │ ⋮  │ Encino Fict. │ Industrial │ Ficticio  │   12,500   │ 1,500,000 ?  │ 2 PDF    │ ✔ contorno│     │
 │ ⋮  │ Sin nombre   │            │           │            │              │ ＋       │ ＋        │     │
 │ ⋮  │ Roble Fict.  │            │ Ficticio ◐│  ⚠ "SD"    │              │ ⟳ 40 %   │ ⚠ elegir  │     │
 └────┴──────────────┴────────────┴───────────┴────────────┴──────────────┴──────────┴───────────┴─────┘
 [+ Agregar terreno]                                    ▾ lists only the bases granted to the user
```

| Interaction | Behaviour |
|---|---|
| **Add blank record** | "Agregar terreno" sends `POST` with `{}` and an idempotency key. The row appears at once labelled "Sin nombre" (a display label; `terreno` stays empty) with focus in its first cell. |
| **Edit a cell** | Click or Enter opens the cell; Enter or leaving it saves; Esc cancels. Arrow keys and Tab move between cells. Only the changed cell is sent. |
| **Saving** | The cell shows ◐ while its PATCH is in flight; the header shows "Guardando…" then "Guardado HH:MM". |
| **Error** | The cell keeps what the user typed, is marked ⚠ and shows the server's message for that field. The rest of the row and every other edit stay saved. |
| **Conflict** | Other cells changed by someone else: silent retry. Same cell: the cell shows "tu valor / valor de otra persona" and the user picks one. |
| **Currency** | A price with unknown currency shows a `?` marker; the currency is set from the detail panel or a small control beside the price cells. |
| **Empty base** | A new work base opens as an empty grid with the fourteen core columns and "Agregar terreno". No file is needed. |
| **Custom-column control** | "+ Columna" asks for name and type and adds the column to this base only. A column header menu offers rename, move and retire. |
| **Remove** | The row menu (⋮) offers "Quitar". It archives the terrain; "Mostrar quitados" lists them with "Restaurar". |
| **Attachment-cell slot** | The `Archivos` and `KMZ` cells are rendered by Team B's `ArchivoCelda`. The grid passes it the terrain ID, the column, the summary and the permissions, and gives it focus like any cell. Until B's component exists the cell shows "—". |
| **Detail panel** | A side panel for long comments, the non-core fields, history and B's `ArchivoDetalle`. |
| **Narrow screens** | The table keeps the name column pinned; editing happens in the detail panel. |

Implementation shape: a native `<table>` with a single input moved into the active cell, in `web/components/maestra/`, with the cell state machine and save queue as pure functions in `web/lib/maestra.js` (testable with `node --test`). No grid library and no build step. Routes `#/maestra` (base list) and `#/maestra/<base id>`. Rows are not virtualized in the first packet; that is the upgrade if the table passes a few thousand rows (decision D7).

---

## 5. Shared changes and what Team B needs

### 5.1 Answers to Team B's requests (PR #8, §5)

| B's request | Team A answer |
|---|---|
| R1 tables `archivo`, `archivo_version`, `geometria`, `archivo_evento` | Landed by A as **schema 10**, after B's contract absorbs the supervisor's corrections (active layout separate from uploaded version; attachment-level revision). Not included in schema 9, so A's migration does not wait on those open points. |
| R2 capability helper | `auth.require_terreno(request, terreno_id, capacidad)` with `archivos.ver`, `archivos.subir`, `archivos.retirar` (§3.3): the per-terrain signature B asked for. It checks the capability and that the terrain's work base is in the caller's scope; out of scope answers 404. |
| R3 route registration | A registers B's routes in `server/app.py` and adds each to the capability table. B supplies method, path, handler and capability per route. |
| R4 `ubicacion` and `archivos` summaries in the terrain DTO | A adds them in `repo._dto` through a batch helper supplied by B: **one query per listing, not one per row**. Field names inside the summaries are B's. |
| R5 `ubicado` from boundary or X/Y | A applies B's `ubicacionDe` in `web/lib/inventario.js` `itemDeInventario`. |
| R6 `app.js` hooks | A mounts the geometry loader and `ArchivoDetalle`. |
| R7 column IDs | `core:archivos`, `core:kmz` accepted and present in every work base; column definition shape in `examples/02-columnas.json` (`tipo: "archivo"`, `acepta`, `multiple`). |
| R8 snapshot references | Wave 3; noted, not designed here. |
| R9 CI | Confirmed by reading `.github/workflows/checks.yml`: `unittest discover -s tests -t .` picks up any `tests/test_*.py`. No change needed. |

### 5.2 What Team A needs from Team B

1. Final names and shape of the two summaries in the terrain DTO (the supervisor noted `ubicacion.geometria` versus `geometria` is unresolved), and an upper bound on their size per row.
2. Confirmation that file operations never change `inventory_terrain.version`. The grid relies on that so an upload cannot make a cell edit conflict; it then refreshes the row from `onCambio` alone.
3. The revised schema requirements for schema 10.
4. The capability each of B's routes requires, including the batch geometry route, and confirmation that every route resolves a terrain ID it can pass to `auth.require_terreno` (a version or geometry ID must lead back to its terrain).
5. Keyboard contract of `ArchivoCelda`: which keys it handles and which it leaves to the grid.

### 5.3 Shared-change queue (Team A is sole editor)

| # | File | Change | For |
|---|---|---|---|
| S1 | `server/db.py`, `server/postgres.py` | Schema 9: `team_user.rol`, `team_user_event`, `maestra_base`, `maestra_base_acceso`, `inventory_terrain.base_id`, `inventory_revision.tipo_terreno`, `inventory_revision.custom_json`, `inventory_column` | A |
| S2 | `server/auth.py`, `server/app.py` | Capability table, dispatcher check, scope helpers, session payload | A, B |
| S3 | `web/components/app.js`, `web/lib/router.js`, `web/lib/store.js`, `web/lib/api.js` | `#/maestra` route, navigation driven by `capacidades`, grid mount | A |
| S4 | `server/db.py`, `server/postgres.py` | Schema 10: B's tables | B |
| S5 | `server/app.py`, `server/repo/inventario.py`, `web/lib/inventario.js`, `web/components/app.js` | R3–R6 hooks | B |
| S6 | `AGENTS.md` | Domain rules for master records (explicit or unknown currency, stable IDs, KMZ can locate a terrain), as the handoff already states | Both |

---

## 6. Proposed implementation PRs

Each is small, starts from `origin/main`, and runs `./verificar.sh` plus the GitHub checks (which include disposable Postgres).

| PR | Branch | Content | Depends on | Acceptance checks |
|---|---|---|---|---|
| **A-1** | `claude/team-a/schema-9` | S1 only: additive migration on SQLite and Postgres, no behaviour change | Consolidated contract | Migration 8→9 test on both databases; existing data and saved maps unchanged; repeatable; backup taken first |
| **A-2** | `claude/team-a/roles-and-bases` | S2; work-base and access routes; `cuentas.py` roles | A-1 | Admin creates an empty base and grants it. The operator sees only that base; gets 404 for any other base or terrain and 403 for every `derivados.*`, `bases.gestionar` and `usuarios.gestionar` route; anonymous gets 401; every registered route has a capability; revoking the grant takes effect on the next request; both databases |
| **A-3** | `claude/team-a/master-record` | `tipo_terreno`; remove currency-on-save rule; base-scoped list/create; archive/restore; core column definitions | A-1, A-2 | Blank create inside a base; price without currency saves and is still blocked from publishing; a terrain created in one base never appears in another; archive and restore by the operator inside her base |
| **A-4** | `claude/team-a/master-grid` | S3; base picker; grid with add, edit, remove, save/error/conflict states; attachment slot placeholder | A-3 | `node --test` for the cell state machine and save queue; browser test: the operator opens an empty base, adds an unnamed terrain, edits a cell, a second session sees it after reload; simulated concurrent edit is not lost |
| **A-5** | `claude/team-a/custom-columns` | Per-base column routes and UI; `custom` in PATCH | A-4 | Add, rename, retire and restore keep values; a column added in one base does not appear in another; an operator cannot touch another base's columns |
| **A-6** | `claude/team-a/user-admin` | In-app accounts, roles and base access | A-2 | Admin creates, deactivates, changes roles and grants bases; operator gets 403; every action is audited |
| **A-7** | `claude/team-a/attachments-integration` | S4, S5 with Team B | B-3, B-4 | First joint milestone from the delivery plan, locally, with the operator restricted to one base |

A-1 to A-3 unblock Team B's B-3 (which needs the scope helper and route registration). A-4 can proceed in parallel with B-2. Search, sort and filter refinements follow A-4 as separate small PRs.

---

## 7. Decisions that affect the first packet

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| **D0** | The owner requirement in §3.1 replaces "one master table" (MASTER_PLAN §4) with several editable work bases and per-person access. Is that the intended direction, and how do filtered bases and saved maps relate to a work base later? | Adopt work bases now; they are a small additive change (two tables, one column) on the same record model. Treat filtered views and maps as derived from one work base when that phase is planned. Whether administrators also need one combined view across bases can wait. | A-1 |
| D1 | Operator scope | Only the work bases granted to that person, with full working control inside them (add, edit, remove, files, KMZ, columns). Nothing else. | A-2 |
| D1b | Who creates a work base | Administrators create and grant it. Operator-created bases are a small addition if wanted. | A-2 scope |
| D2 | Two roles, or permissions chosen per person? | Two roles plus per-person base grants. This already answers "which person can see what" without a permission matrix per person. | A-2 |
| D3 | May a price be saved without a currency? | Yes, as "unknown"; publishing still requires one. | A-3 |
| D4 | Is "Comentarios" the existing private "Notas internas"? | Yes, reuse it. A second long-text field would split the same information. | A-1 |
| D5 | "Tipo de terreno": free text or fixed list? | Free text with suggestions from existing values now; a controlled list once the vocabulary is known. | A-3 only for the list |
| D6 | Role of each existing account at migration | Everyone starts as operator with no base; the owner names the administrators. | Release, not A-1 |
| D7 | Expected size and simultaneous editors; is multi-cell paste needed? | Design for up to a few thousand rows per base and a handful of editors; no paste in the first packet. | A-4 scope |
| D8 | Naming: today "Bases" means imported spreadsheets | Call the new ones "Bases" for operators, who see nothing else, and rename the legacy list "Bases importadas" for administrators. | A-4 |

Left for their phase: live versus frozen derived datasets, permanent deletion, custom attachment columns, public visibility of master data.

---

## 8. Evidence and limits

```bash
python3 reports/team-a-master-table-prep-2026-10-07/experiment/baseline_probe.py
./verificar.sh
```

- The probe ran on macOS with `/usr/bin/python3` 3.9.6 against a temporary SQLite file; its output is committed beside it.
- `./verificar.sh` on this branch: results are in the PR description, for the exact head.
- **Not established here:** anything on Postgres, Vercel or with real records; the grid's usability (it is a sketch); performance with real row counts.
- No production credentials were used. No production, Preview or database was read or changed.

## 9. Next action

Await the supervisor's consolidated contract. On receipt, start A-1 and A-2. A-1 depends on D0, because the work-base tables are part of schema 9.
