# Packet 3A — application integration: final handback

The combined local workflow with **Team B's real widgets and geometry loader**
mounted in the real application: an operator creates a blank terrain, edits it,
uploads and downloads a PDF, uploads a KMZ with blank X/Y, chooses among its
candidates, activates explicitly and sees the true boundary on the page map; a
second authorized session reads the same stored files and boundary; a no-grant
account is denied. It runs on one local machine with local disk storage. It is
not a cloud service and not a release.

This replaces the partial host checkpoint `161cfa5` (same branch, same draft
PR). For supervisory review. Nothing here is merged or deployed.

## 1. Heads

| What | Exact commit |
|---|---|
| Instructions | `4682793f290718cfd49fd661ef16f2af4448fafb`, `reports/round-3-instructions-2026-10-09/` |
| 2A input (#26) / 2B input (#25) | `32a2a55e4a7417499cc384109bd44666e7a568cb` / `bf4c6a694ca95087368bb2d89325d7a240a7b676` |
| C1 (#27), frozen | `49b782d147591236cc7f311c7e0de1948ad5258e` (pure composition `72553e4…`) |
| 3A host checkpoint (partial, earlier) | `161cfa59ea8a73a579d321e651d5c8b8b175fd48` |
| **3B candidate consumed** (#28, named green in its description, CI run 37996070565) | **`01d64541e929009ea2d149e3c6f5980805c76c73`** |
| Ordinary `--no-ff` merge of exactly that head | `368428d` (parents `161cfa5`, `01d6454`; no conflict) |
| Integration code | `e6266f4` (host fixes, CSS link, journeys), `aa9a3ed` (measurement script fix) |
| Final head (adds this report and evidence) | stated in the draft PR description (this file cannot name its own commit) |

Branch `claude/team-a/application-integration`; draft PR #29 targets
`claude/integration/round-3-baseline`. No rebase, no force push. B's branch was
not touched and A's moving branch was not pushed into it. #20–#28 are
unchanged. Schema stays **10**.

## 2. What changed since the partial checkpoint

| File | Owner | Change |
|---|---|---|
| (merge `368428d`) | B | B's `web/components/archivos/`, `web/lib/archivos.js`, `web/lib/cargadorGeometrias.js`, `web/styles/archivos.css`, B's tests and report, unchanged |
| `web/index.html` | A | B's stylesheet linked after the shared sheets (B's request A-3) |
| `web/components/tabla/vistaPrevia.js` | A | (a) A boundary load that fails is not retried on every repaint; only "Reintentar", another selection, or a different active descriptor tries again. (b) Removing the map waits one frame (bug below). (c) The status line includes B's sanitized message. |
| `web/components/tabla/Tabla.js` | A | The page map's loader errors `no_disponible`/404 make the table re-check that one terrain: its location is updated, or the row leaves the view if it left scope (INTERFACES §3 "404/scope loss … prompts host revalidation"). |
| `tests/e2e/recorrido-completo.mjs` (new) | A | The final journey, below. Starts its own server, restarts it, cleans up. |
| `tests/e2e/tabla-mapa-memoria.mjs` (new) | A | Bounded memory/teardown run with the page map and the real loader. |
| `tests/e2e/tabla_servidor.py` | A | `--carpeta DIR` (database and store kept, so a second start is a restart) and `--postgres-esquema NAME` (a schema of the disposable Postgres in `ARA_MAP_TEST_DATABASE_URL`). Default behavior unchanged. |
| `tests/e2e/tabla-archivos.mjs` | A | The "modules missing" case now makes them fail to load (they exist now). The stand-in cases remain as host-only checks. |
| `tests/e2e/tabla-integrada.mjs` | A | The file cells now show B's real text ("Sin PDF", "Sin KMZ"), and the detail waits for B's controls, where both used to show the placeholder. |
| `tests/e2e/tabla-medicion.mjs` | A (2A's) | Keyboard timings are armed and awaited before the key is pressed (a race that hung the script here). |

Host requests from B (`SOLICITUDES_A.md` at `01d6454`): A-1 registration, A-2
detail lifetime, A-4 `resumen`/`soloLectura` and A-5 `onCambio`/`onError` were
already in the host checkpoint and are now exercised with the real widgets.
A-3 (CSS link) is done here. A-6 (one selected body; `reset()` on page, filter
or base change; `destroy()` at session end) is exercised with the real loader.
A-7: the harness-only routes stay in B's harness server and are not mounted by
the application. A-8: C1's CI is green on attempt 8 of run 37992169820.

No server, schema, auth, dispatcher, renderer, geometry helper or B-owned file
was changed in 3A after the merge.

### Two defects found by the real journey and fixed (host)

1. **A removed preview map could still draw.** At session end the table
   repaints the empty page (a `fitBounds`) just before destroying the preview.
   Leaflet 1.9.4's synchronous canvas redraw clears `_redrawRequest` while a
   redraw is still queued for the next frame, so `map.remove()` cannot cancel
   it. That queued redraw then ran on the removed canvas and threw
   `Cannot read properties of undefined (reading 'save')`. Reproduced in
   isolation with an instrumented renderer. The map is already empty and
   detached, and is now removed one frame later. The reproduction and the full
   journey show no page error.
2. **A boundary that left scope only said "could not load".** It now prompts
   the host to revalidate. The journey "revoked while chunks are read" proves
   the row, files and outline go and nothing is drawn later.

## 3. Evidence

All on one Linux container (not the owner's Mac), loopback only, synthetic data
and fictional accounts. Chromium 141 (`/opt/pw-browsers`). Disposable SQLite
files, and a disposable local Postgres 16 cluster (UTF-8) whose test schemas
are dropped at the end. Logs and JSON are in `evidencia/final/`.

### 3.1 The real combined journey: `recorrido-completo.mjs`

**SQLite, all journeys: 22/22.** These are real clicks in the real application
with B's widgets, against the mounted server and its local disk store.

| # | Journey | Proves |
|---|---|---|
| 1 | Operator creates a blank terrain | Business cells are blank, not zero; real cells say "Sin PDF"/"Sin KMZ"; `ubicacion.modo = ninguna` |
| 2 | Edits cells | Saved with versions |
| 3 | PDF upload in the detail; download | Byte-identical (SHA-256) download with its UTF-8 name; terrain version unchanged |
| 4 | KMZ with 3 candidates and blank X/Y | "Requiere elegir" → choose → valid but **not active** until "Activar"; row DTO has no body, key, hash, URL or candidate keys; X/Y stay null; the page map loads only that body and draws the outline at parcel scale (zoom 18) |
| 5 | Invalid replacement KMZ | Rejected; the same active geometry id; the map still loads it |
| 6 | Ten rapid selections between two boundaries | At most 1 body request in flight (one superseded chunk request was cancelled); the last selection is installed; 1 body held, none for the other |
| 7 | A file completes while a cell is edited | The widget's refresh is held, an editor is opened with text and a 2-character selection, then released: the count updates, and the editor keeps text, selection and focus; the save then lands at version +1 with no conflict |
| 8 | Retire the KMZ of a terrain with X/Y | `modo = punto`, descriptor gone, map says "coordenadas X/Y" |
| 9 | 100,000-vertex body (the parser's limit) | Upload through the widget, select, load and draw; "Ver a escala" shows the real outline (no truncation or simplification). Numbers below |
| 10 | Second authorized session | Same files, identical download, same geometry id loaded |
| 11 | No-grant account | No rows; terrain, file list, versions and chunk all 404 |
| 12 | **Server restart** on the same database and store | New process; byte-identical download, history (3 files), same active geometry |
| 13 | Grant revoked while chunks are read | Chunk request held, grant revoked, released: 404 → loader `no_disponible` → host revalidates → row, files and outline gone, 0 bodies |
| 14 | Terrain transferred while a download is out | Download request held, transfer, released: no file delivered, detail closed, row gone, name not on screen |
| 15 | Session expires during a throttled upload | Sign-out from another tab; the bridge's 401 tears down the table, widgets, dialogs and map. Then 3 s with no private node, no late DOM mutation and no `completar` request |
| 16–22 | Every session | No page error |

**Postgres, focused smoke: 13/13.** The same journeys 1–5 and 10–12 (upload →
second session → no-grant denial → restart on the same schema and store) run
against a schema of the disposable Postgres. The schema is dropped afterwards.

Screenshots `evidencia/final/capturas/`: PDF uploaded in the detail;
candidates chosen but not active; the real outline on the page map; the
100,000-vertex body to scale; revoked during reading; expired during upload.

### 3.2 Other browser suites on this tree

| Suite | Result |
|---|---|
| B's 19 widget journeys (`archivos-recorridos.mjs`, mounted mode) | 19/19 |
| Host journeys (`tabla-archivos.mjs`) | 6/6 |
| 2A table journeys (`tabla-integrada.mjs`) | 13/13 (after the expected text change above) |
| 2A identity journeys (`tabla-identidad.mjs`, 4,200 records) | 16/16 |

### 3.3 Suites

| Check | Result |
|---|---|
| Python, SQLite (3.13, container) | 1,254 run, 223 Postgres skips, 1 environmental failure |
| Python 3.9.25, SQLite | 1,254 run, 223 skips, the same 1 environmental failure |
| Python, disposable Postgres 16 | 1,254 run, **0 skipped**, the same 1 environmental failure |
| JavaScript | 181/181 |
| `ruff check server/ tests/`, `mypy server/` | clean (54 files) |
| `./verificar.sh --todo` (zsh installed in the container) | JS, ruff, mypy, coverage OK; both Python lines fail only on the environmental test below |
| Exact-head CI | green on code head `e6266f4` (run 38201561488); final head in the PR |

The environmental failure is `test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`.
This container's system Python has its own openpyxl, which a Mac's does not.
B reported the same failure. It passes in CI.

### 3.4 Near-limit body (100,000 vertices), in the real app

| | |
|---|---|
| Upload through the widget (439 KB KMZ; the server parses it) | 10.8 s |
| Selection to "Contorno cargado" (metadata, chunks, SHA-256, parse, draw) | 0.5 s |
| Chunks | 8 (B measured 4,117,139 B for this body; this run's byte field undercounts, see `CABEZA.txt`) |
| Zoom: whole body framed / "Ver a escala" | 13 / 19 |
| JS heap before / peak / after another selection | 4.4 / 30.9 / 4.5 MiB |

Its 20,000 parts are spread wider than one parcel. Framed whole, each part is
the renderer's symbol; "Ver a escala" (`zoomToScale`) shows the outline. That
is the accepted renderer behavior, not a host choice.

### 3.5 Synthetic 25,000 records / 3,000 in a base / five sessions

**The same machine and the same client script, 2A head `32a2a55` vs 3A**
(`medicion-2a-misma-maquina.json`, `medicion-3a.json`). 2A's original report
was measured on a Mac, so its absolute numbers are not comparable with these.

| Median (max), ms | 2A | 3A |
|---|---|---|
| Operator first page (reload to 100 rows painted) | 572 (709) | 602 (623) |
| Next/previous page, base of 3,000 | 208 (308) | 231 (328) |
| Save one cell (to saved) | 106 (163) | 105 (151) |
| Admin master table, next page | 336 (384) | 375 (446) |
| Admin base change | 202 (229) | 224 (305) |
| Five sessions, 50 edits on distinct rows | 186 (379) | 190 (426) |
| List bytes, 100 rows | 173,010 | 186,770 |

- **Five sessions:** 50/50 saved with 0 unresolved, in both. On one cell
  edited at once, conflicts are shown `[1,1,1,0,1]` and final version 2, in
  both.
- **Summary cost on the server** (`medir_resumenes.py`, SQLite, 60 of the first
  page's terrains with files): the 200-row page went from 58 to 69 ms and from
  346 to 393 kB. Statements went from 11 to **1,611**, that is 8 per terrain
  in B's summary hook. This is request R3-A1 to Team B, still open; nothing
  was rewritten or cached to hide it.
- **Memory, 2A transitions on 3A** (`memoria-2a-en-3a.json`): +47 / +72 / +50
  KB of heap per 100 transitions, with DOM nodes and listeners flat. That is
  the pattern of 2A's own run.
- **Memory, page map with the real loader** (`mapa-memoria.json`): 40 rounds
  of 3 boundary selections each, a page change, a base change and a detail
  with B's widgets. At most 1 body was held at any check, and nothing was
  loading at rest. DOM nodes (4,454) and listeners (314) stayed flat. Heap grew
  +172 / +90 / +173 KB per 10 rounds, about 15 KB per round. That is not
  levelled within this bounded run. It is reported as measured, not explained
  away, and is not a total-browser-memory guarantee.

No body is prefetched and no page accumulates. The preview never requests
another page.

### 3.6 Coverage gate and `verificar.sh`

`evidencia/final/verificar.log`: coverage **95%** (gate 80%), ruff and mypy
clean, JS OK. Both Python lines report "FALLA" for the one environmental test
(1,254 run, 1 failure). Here `/usr/bin/python3` is 3.13, not macOS's 3.9; the
3.9 floor is the separate Python 3.9.25 run. `evidencia/final/CABEZA.txt`
says which commit produced each file.

## 4. Run it (owner)

```bash
# A disposable local application with fictional accounts (ada, alan: administrators;
# olga, omar, …: operators; otto: no grant). Password: TEST_PASSWORD in tests/support.py.
python3 tests/e2e/tabla_servidor.py --puerto 8433 --carpeta /tmp/ara-demo
#   open http://localhost:8433
#   ada:  Tabla → "Bases y accesos" → create a base, grant olga and omar.
#   olga: "Agregar terreno", edit cells, "⋯" (Abrir terreno) → upload a PDF and a KMZ
#         (with several outlines: Versiones → Contornos → Elegir contornos… → Procesar →
#         Activar este contorno), close, "Mapa de esta página", click the row.
#   omar in another browser profile: the same files and outline. otto: nothing.
#   Stop and start the same command again: everything is still there (same folder).
#   Delete /tmp/ara-demo when done.

# The whole journey, automated (Chromium; starts and restarts its own server)
cd tests/e2e && npm ci
node recorrido-completo.mjs                                     # SQLite, 22 journeys
ARA_MAP_TEST_DATABASE_URL=postgresql://…/desechable RECORRIDO_BD=postgres \
  PYTHON=../../.venv-dev/bin/python node recorrido-completo.mjs  # focused Postgres smoke
# CHROMIUM=/path/to/chrome if not in /opt/pw-browsers; RECORRIDO_CAPTURAS=dir for screenshots.

# 25,000-record measurements (server in another terminal)
python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000
ARA_URL=http://localhost:8434 node tabla-medicion.mjs salida.json
ARA_URL=http://localhost:8434 node tabla-mapa-memoria.mjs salida.json   # fresh server for each
```

A normal local start (`python3 -m server.app`) keeps uploaded bytes in the
`archivos` folder next to the SQLite database and prints it on start.

## 5. Known limits

- One machine, local disk, loopback. Not durable cloud storage, not hosted
  capacity, and no deployment.
- The page map is the **current table page** only, with one selected body at a
  time. It makes no claim about all 3,000/25,000 rows or all outlines.
- The summary hook costs 8 statements per terrain (R3-A1 to B). Locally that
  is about 11 ms on 200 rows; on a networked database it would be one round trip
  each. Not measured on a networked database.
- The page-map memory run grew about 15 KB per round over 40 rounds, with
  DOM and listeners flat. One bounded run, as the packet asks. Not levelled.
- Upload progress is indeterminate (B's limit: fetch exposes no upload bytes).
  A pending upload found after a reload needs the same file again.
- The browser runs here are Linux/Chromium, not the owner's Mac/Chrome. Map
  tiles are blocked in tests (blank background). No screen-reader pass.
- Already downloaded copies cannot be recalled by a later revoke.

## 6. Reserved for Round 4

Full filtered-map persistence and saved views; the whole-base and dense-map
display policy (E5 and the research memory settings are not used); the cloud
storage provider; R3-A1 batching if B takes it.

Stop for supervisory review: no 4A, no PR or main merge, no deployment, no
real account or data.
