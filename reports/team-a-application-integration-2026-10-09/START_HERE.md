# Packet 3A — application integration: PARTIAL host checkpoint

**This is not the final 3A handback.** Team B's 3B candidate (the file widgets
and the geometry loader) did not exist when this was written, so the combined
operator journey with B's real widgets — the packet's acceptance — is **not
demonstrated here**. Per the packet ("If B is not ready, A submits an
explicitly partial host checkpoint and waits for that artifact"), this is the
host side, finished and tested against the frozen seams, waiting for B's named
green-CI head.

- Instruction commit `4682793f290718cfd49fd661ef16f2af4448fafb`,
  `reports/round-3-instructions-2026-10-09/`.
- Branch `claude/team-a/application-integration`, from C1; draft PR targets
  `claude/integration/round-3-baseline`. The exact head is in the PR
  description.
- C1: `reports/round-3-baseline-2026-10-09/START_HERE.md`, PR #27, head
  `49b782d147591236cc7f311c7e0de1948ad5258e`.
- Inputs unchanged: #26 `32a2a55…`, #25 `bf4c6a6…`, #24 `7117f57…`. Schema 10.
- B's consumed head: **none yet.**

## 1. What is done

### Server: `archivos` and `ubicacion` on current records (INTERFACES §4)

`server/api/inventario.py::_presentar` adds two private siblings to every
current-record answer the grid uses: both lists, detail, create, save
(`PATCH`), archive/restore, transfer, and the `terreno` inside a 409 conflict.

- `archivos`: Team B's `resumenes_de_archivos` result for that terrain,
  unchanged — `{pdf_total, pdf_recientes, kmz}`. That service authorizes every
  id again (`archivos.ver`) and applies its own pending-upload privacy. A
  terrain it reports unavailable gets `null`, not a zero summary.
- `ubicacion = {modo, xy, geometria}`: `geometria` is the shared contract's
  descriptor `{id, archivo_version_id, utilizable, bbox, punto_interior}` of
  the live KMZ's **active usable** geometry, or `null`; `xy` is the existing
  `valida | sin_dato | invalida`; `modo` is `geometria`, else `punto` when X/Y
  is valid, else `ninguna`.
- One added query per page (`repo.descriptores_activos`, in
  `server/repo/inventario.py`): no vertex body, storage key, candidate list or
  hash is ever in a row.
- Raw `draft.lat` / `draft.lon` are untouched; the terrain's `version`,
  `revision_number` and `updated_at` do not move when a file does.
- The public catalog DTOs are unchanged (explicit allowlists).
- **No query parameter was added.** A server-wide located/unplaced filter was
  not needed for this packet's screens (the page preview counts the rows it
  shows and says so), so none was invented; the existing attention filter is
  untouched.

### Client

| File | Change |
|---|---|
| `web/lib/inventario.js` | `itemDeInventario` adds `geometria` (the record's descriptor, or `null`) when the record has `ubicacion`. No import of `geometria.js`, so no cycle; `ubicacion` stays the XY diagnostic string and `lat`/`lon` the raw X/Y. A record without `ubicacion` produces exactly the old row. |
| `web/components/app.js` | The administrators' Inventario rows take `ubicado` from `ubicacionDe` (boundary first, then valid X/Y), so a KMZ-only terrain is not listed as unplaced there. |
| `web/components/tabla/ranuraArchivos.js` | Two registered factories (cell `mount`, detail `mountDetalle`); mounts remember their terrain. The unregistered state still shows an honest "No disponible". |
| `web/components/tabla/archivosAnfitrion.js` (new) | Loads B's two modules on demand, creates them with `peticionPrivada`, registers the widgets, and destroys widgets and loader with the table (session end). If a module fails to load the table still works and says which is missing. |
| `web/components/tabla/Tabla.js` | Real `resumen` to every file cell and detail mount; `onCambio` → one coalesced refresh per terrain that replaces only `archivos`/`ubicacion` of that row (no cell repaint, so an open or unresolved editor is untouched); `onError` → readable message, and a 404/scope code removes the row and revalidates the bases; terrain selection by id shared with the map; "Mapa de esta página" panel; teardown of all of it on scope/session loss. |
| `web/components/tabla/dialogos.js` | The detail mounts B's detail widgets with the summary and takes summary refreshes while open. |
| `web/components/tabla/vistaPrevia.js` (new) | The current-page map preview, below. |
| `web/styles/tabla.css` | Layout of the panel and the selected row. |

No file of Team B's was edited (`MapCanvas.js`, `geometria.js`, attachment
modules). The renderer is used as it is, through its existing methods.

### The page map preview (INTERFACES §5)

- Labelled "Mapa de esta página", with the count of rows on this page that are
  located / have a boundary / are unplaced, the view's total when it is larger,
  and a standing note that only the current page is drawn and that an outline
  loads when its terrain is selected. It never requests another page.
- Selection is one terrain id, shared both ways: a row focused or clicked in
  the table is selected and framed on the map; a mark chosen on the map selects
  and scrolls to its row without moving keyboard focus or touching an editor.
- Only the **selected** terrain's body is loaded, through B's
  `cargar({terrenoId, geometria}, {signal})`, and given to the renderer as
  `geometrias` with at most one entry. A new selection aborts the load in
  flight, drops the held body and calls the loader's `reset()`. Nothing is
  cached per row.
- While loading, on error, or if the loader module is missing, the terrain
  stays at its descriptor's interior point with the renderer's own
  "outline not loaded" symbol, the status line says which, and "Reintentar"
  asks again. It is never moved to X/Y and no outline is invented.
- A boundary-only terrain can be selected, framed ("Encuadrar página") and
  taken to scale ("Ver a escala", or double click) with the renderer's
  `select` / `fitTo` / `zoomToScale`.
- Page, filter, base or session change: body, load, selection dropped; on
  session end the map itself is removed.

Two defects found and fixed while testing it, both in the host:
Leaflet ignores a view change requested during a zoom animation, so a quick
selection was not framed (the request now waits for that step); and removing
the map during that animation threw from a Leaflet timer (the map is emptied
and detached at once and removed when the step ends).

## 2. Evidence

All on one Mac, loopback, synthetic accounts and data. "Stand-ins" below are
test doubles served by the test **in place of B's modules**: they prove the
host's side of the seam, not B's widgets.

| Check | Result | Where |
|---|---|---|
| Record siblings, SQLite + disposable Postgres 16 | 12 tests × 2 backends OK: every surface's shape; XY-only, boundary-only (X/Y stay blank, version unmoved), boundary over valid X/Y; pending / unusable / rejected replacement keeps the previous boundary; retirement falls back to X/Y or to nothing; another account's pending upload shows no metadata in a row; no body/key/candidate key in a row; grant loss, transfer and unassigned hide everything; bounded page with server count; conflict answer; public catalog unchanged | `tests/test_resumenes_terreno.py` |
| Host browser journeys, real mounted server + disk store | 6/6, three runs in a row | `tests/e2e/tabla-archivos.mjs`, `evidencia/recorridos-anfitrion.log`, `evidencia/capturas/` |
| Earlier browser journeys on this tree | 13/13 (`tabla-integrada`), 16/16 (`tabla-identidad`) | rerun, not modified except one placeholder text |
| Restart persistence | SQLite (sibling folder) and disposable Postgres (`ARA_MAP_ARCHIVOS`): after the server process is stopped and a new one started on the same database and folder, another authorized account downloads byte-identical PDF and KMZ (same SHA-256), reads the history, gets the same active geometry and a chunk whose hash matches; a no-grant account gets 404 and no bytes | `reinicio.py`, `evidencia/reinicio-*.json` |
| Page cost, 25,000 records / 3,000 in the base | below | `medir_resumenes.py`, `evidencia/resumenes-*.json` |
| Full suites | `./verificar.sh`: 1,254 Python OK (223 skipped need Postgres), full suite on Python 3.9.6 OK, JavaScript 137/137. Disposable local Postgres 16: 1,254 OK, zero skipped. `ruff check server/ tests/` and `mypy server/` clean. CI: see the draft PR | |

The six host journeys: (1) without B's modules the table works, file cells say
"No disponible", the page map counts honestly and editing still works;
(2) stand-in widgets receive the real summary in cells and in the detail, and
the detail's mounts are destroyed on close; (3) a PDF uploaded through the real
API while an editor is open with a selection: three change reports → one or
two refresh requests, the cell shows the new count, the editor keeps its text,
selection and focus, the terrain version is unchanged and the cell then saves
against it; (4) nothing is prefetched; selecting the boundary-only terrain
loads its real body from the mounted server in chunks, draws the outline at
parcel scale, holds exactly one body; another selection drops it; a failure is
said and retried; a superseded slow load never lands; (5) logout during a load
destroys factories, mounts, loader and map, and the next account on the same
page (no grant) gets nothing, late answers included; (6) a second authorized
session sees the same stored boundary, and when its grant is revoked the next
file refresh removes the row, the files and the outline.

### Page cost of the summaries (measured, not optimized)

Operator session, base of 3,000, first page; 60 of its terrains have
attachment rows. Median of 7 runs.

| Page | 2A list | 3A list | Statements (SQLite) |
|---|---|---|---|
| 50, SQLite | 12.9 ms / 87 kB | 15.2 ms / 111 kB | 11 → 411 |
| 100, SQLite | 14.5 ms / 173 kB | 18.1 ms / 207 kB | 11 → 811 |
| 200, SQLite | 17.5 ms / 345 kB | 24.1 ms / 392 kB | 11 → 1,611 |
| 50, local Postgres | 92.5 ms | 128.0 ms | — |
| 100, local Postgres | 95.0 ms | 146.7 ms | — |
| 200, local Postgres | 97.9 ms | 194.0 ms | — |

The response grows about 235 bytes per row. The time is small locally, but the
statement count is **8 per terrain**: B's hook authorizes each terrain
separately and then runs three queries for it; 3A adds one query per page. On
a loopback database that is 0.06 ms a statement; on a networked database it
would be one round trip each, so a 200-row page would wait for about 1,600 of
them. Nothing was rewritten or cached to hide it. See the request below.

## 3. Requests and handoffs

**R3-A1, to Team B (their repository and service; not blocking the local
milestone).** `server/archivos.py::resumenes_de_archivos` +
`server/repo/archivos.py::summaries` cost 8 statements per terrain
(`require_terreno` ×1 and its lookups, then 3 summary queries each). Requested:
a batched form for one bounded page (≤ 200 ids) — authorization of the page in
one or two queries and the three projections with `IN (...)` — returning the
same shapes. Reproduce with `medir_resumenes.py` at this head. A-side there is
nothing to change when it lands: `_presentar` calls the same hook.

**For the final integration (A, once B names its head).** Merge that exact
head into this branch with an ordinary merge and record it; run
`tests/e2e/tabla-archivos.mjs` with the stand-ins removed plus the real
journey (create blank → edit → upload/download PDF → upload KMZ with blank X/Y
→ choose among candidates → activate → see the boundary → second session →
no-grant denial; replacement failure; retirement; revoke/transfer/expiry
during upload, download and chunk reading); the focused Postgres browser
smoke; the 100,000-vertex body timing; the bounded memory/teardown run.
None of those is claimed here.

## 4. Decisions made here, for review

1. **Store location** (C1): explicit `ARA_MAP_ARCHIVOS`, else the SQLite
   database's sibling `archivos`; **no default store for a Postgres database**.
2. **R2-A5 narrowed** (C1): only header-block defects count as broken framing;
   the parser's multipart-body defects do not.
3. **Dynamic loading of B's modules**: a missing or failing module degrades to
   an honest unavailable slot/outline instead of a blank application.
4. **Selection follows focus**: focusing or clicking any cell selects that
   terrain for the map; the map never takes keyboard focus from the table.
5. **No located/unplaced server filter** was added (not needed by a screen).
6. **Administrators' Inventario** counts a boundary-only terrain as located
   and draws it at its interior point with the "outline not loaded" symbol; it
   does not load bodies there (only the table's page preview does).
7. `tests/test_registros_maestra.py`: the 1A assertion that records had no
   `archivos`/`ubicacion` yet is replaced by their exact key sets.
8. `tests/e2e/tabla-integrada.mjs`: the placeholder text is now
   "No disponible" (was "No disponible aún").

## 5. Run it (owner)

```bash
# 1. A disposable local application with fictional accounts (ada, alan: administrators;
#    olga, omar, …: operators; otto has no grant). The password is the test fixture's
#    (TEST_PASSWORD in tests/support.py). Everything is deleted when you stop it.
python3 tests/e2e/tabla_servidor.py --puerto 8433
#    open http://localhost:8433 — as ada: Tabla → "Bases y accesos" → create a base, grant olga.
#    as olga: "Agregar terreno", edit cells, "Mapa de esta página".
#    File cells say "No disponible" until Team B's widgets are merged.

# 2. The host journeys (needs Chrome; a FRESH server each run)
python3 tests/e2e/tabla_servidor.py --puerto 8435 &
(cd tests/e2e && npm ci && ARA_URL=http://localhost:8435 node tabla-archivos.mjs /tmp/capturas-3a)

# 3. Restart persistence and page cost
python3 reports/team-a-application-integration-2026-10-09/reinicio.py
python3 reports/team-a-application-integration-2026-10-09/medir_resumenes.py
```

A normal local start (`python3 -m server.app`) now also prints
`Archivos: <folder>` and keeps uploaded bytes in that folder next to the
database.

## 6. Limits

- **No real widget has been exercised.** Uploads in every check here were made
  by the test through the API; candidates/activation UI, download UI, upload
  cancellation and their teardown belong to 3B and to the final integration.
- Browser checks ran on SQLite only; the Postgres browser smoke is not done.
- The 100,000-vertex body was not loaded in a browser here; no memory run.
- The preview is the current page only, one body at a time. It is not a
  whole-base map and makes no claim about 3,000 or 25,000 rows or all outlines.
- Map tiles are blocked in the browser checks (no external requests), so the
  screenshots show outlines on a blank background.
- Summary cost on a networked database was not measured, only reasoned from
  the statement count.
- No screen reader pass. Coverage gate not rerun for this checkpoint.
- Reserved for Round 4: filtered-map persistence, saved views, whole-base and
  dense-map policy, cloud storage provider.

Stop: waiting for Team B's named 3B head. Nothing merged to a PR base or main,
nothing deployed, no real account or data used. No 4A.
