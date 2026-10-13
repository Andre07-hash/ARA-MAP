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

## 7. Round 3 review: Team B's corrections consumed and verified (2026-10-12)

Supervisor packet `341c83036d7a861e88a1b3d28f6e3359ada057a2`,
`reports/round-3-review-2026-10-12/` (START_HERE, TEAM_A). **Integration
evidence, not final acceptance.** Sections 1–6 above are the earlier handback
and are unchanged.

### Heads

| What | Exact commit |
|---|---|
| #29 head reviewed by the supervisor (start) | `0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db` |
| Team B corrected candidate consumed (#28, green CI run 38268732577) | `b2ac9bd176043fc4b1625b13993f8f21407dc978` |
| Ordinary `--no-ff` merge (parents `0e9e2c1…` and `b2ac9bd…`), no conflict | `e795935c7aebedce8b1e58a6ba87cf8ef396fafe` |
| Code head (the merge plus the new journeys) | `0fdf1908a3466393f49741e1304633134c8e467a` |
| Final head (this section and its evidence) | the head of draft PR #29, in its description |
| Frozen C1 (#27), unchanged | `49b782d147591236cc7f311c7e0de1948ad5258e` |

Pins were checked on GitHub before merging: #28 at `b2ac9bd…` with both
exact-head checks successful, descending from the previously consumed
`01d6454…` and containing C1. Nothing was pushed to B's branch; #20–#27
untouched; no force push.

### Additive diff over `0e9e2c1`

- From the merge: only Team B's files (`web/components/archivos/{subida,detalle,index}.js`,
  `web/lib/archivos.js`, `web/lib/cargadorGeometrias.js`, their two test files
  and their report folder).
- From A: `tests/e2e/recorrido-completo.mjs` (six journeys added) and this
  section with `evidencia/correccion-r3/`.
- **No host, server, DTO or shared-file change was needed.** B's new contract
  (`onError({codigo: "no_encontrado"})` + `onCambio` on an upload 404; a
  write-right loss reported with `onCambio`) lands on callbacks the host
  already had: the row is removed, dialogs close and the bases are
  revalidated. B requested no host change and none was made speculatively.

### The supervisor's two probes, unmodified, on an exact archive of the merge

| Probe | Reviewed `0e9e2c1` | Merged tree |
|---|---|---|
| `probe_upload_scope.mjs` (real app, real revoke; completion is a real 404) | row 1, open detail 1, private filename visible, phase `fallido` | **row 0, open detail 0, filename not visible** (`sonda-upload-scope.json`) |
| `probe_client_edges.mjs` — cancel after destroy | one cancel call under the new identity | `cancelCalls: []` |
| — retryable failure | `fallido`, 0 cancels | `interrumpido`, retryable, cancellable, 1 cancel |
| — uncertain completion | 1 completion call | 2 (it replays) |
| — hash pipeline | 2 concurrent reads | 1 |
| — scope ends during digest | resolved, 1 ready body | `AbortError`, 0 ready (`sonda-client-edges.json`) |

### New journeys in the real application (`recorrido-completo.mjs`)

Real host, B's real widgets, mounted server and disk store; a Playwright route
only holds one request and then continues it unchanged. Their own base and
operators, so the earlier journeys are undisturbed.

| Journey | Merged tree | Same script on `0e9e2c1` |
|---|---|---|
| R3-B2 grant revoked while an upload **completes** (map panel open): real `completar` 404 → rows gone, detail closed, private filename and terrain names off the page, 0 boundary bodies; 2 s later nothing repopulated and no attachment write sent | ok (SQLite and Postgres) | **fails**: the rows stay |
| R3-B2 terrain **transferred** while its content is being sent: that row and its detail go, the other row of the base stays, no later write | ok | **fails**: the transferred row stays |
| R3-B1 "Cancelar subida" still waiting for its held upload step, sign-out in the same task, **another account** (no grant) signs in, the step is then released: 2.5 s with no attachment write, no upload row, no private name | ok | **fails**: `POST /api/archivos/versiones/…/cancelar` left the page under the new account |
| R3-B1 the same with **the same account** signing in again | ok | not reached (the previous failure left that page signed in as the other account) |
| R3-B1 cancel while the detail is **closed and reopened**: at most the one explicit cancel (sent while that detail was open and this scope current), nothing late once reopened, no stale upload row, and a new upload in the reopened detail reaches `listo` and shows in the cell | ok | not reached |
| R3-B5 the session ends **during the final digest** of a selected boundary (the browser's own SHA-256, answered 1.2 s later, after the whole body was read): no install, no private node, no DOM mutation in the next 2.5 s; a new session then loads the same boundary | ok | not reached |

"Not reached" rows are a cascade of the third failure on the old tree, not
evidence either way; B's node regressions cover those cases against
`01d6454`. On the old tree the cancel was sent with the new account's
session; this run does not show what the server answered and no data change
was looked for.

One expectation was corrected while writing them: closing the detail in the
same task as the click does **not** suppress the explicit cancel — the dialog's
`close` event, which destroys the mount, is a later task, so the cancel is
sent first, under the same account and scope. That is the permitted
"explicit cancellation while the same authorized scope is current"; the
journey asserts it is at most that one request and that nothing follows.

### Combined workflow rerun

Run on the owner's Mac (macOS, Google Chrome, loopback, synthetic accounts and
data), at the code head.

| Check | Result | Evidence |
|---|---|---|
| Real combined journey, SQLite | **30/30** (the earlier 22 + 6 new + 2 more no-page-error sessions), including the true restart on the same database and store (2 server starts), 100,000 vertices, second session, denial, chunk revocation, download transfer, upload expiry | `recorrido-sqlite.{log,json}` |
| Real combined journey, focused disposable Postgres 16 | **16/16**: create → edit → PDF → KMZ candidates/activation → rejected replacement → second session → no-grant denial → restart on the same schema and store → upload denial by revocation | `recorrido-postgres.{log,json}` |
| Team B scope-loss journeys, mounted | 8/8 | `b-alcance.log` |
| Team B widget journeys, mounted | 19/19 | `b-recorridos.log` |
| Host journeys (stand-ins) | 6/6 | `anfitrion.log` |
| 2A table / identity journeys (4,200 records) | 13/13, 16/16 | `tabla-integrada.log`, `tabla-identidad.log` |
| Near-limit body, as part of the SQLite journey | upload 8.5 s; selection → drawn 161 ms; 8 chunks, 4.1 MB; zoom 13 → 19 at scale; heap 4.5 → 25.8 (peak) → 4.6 MiB after leaving and collecting | `recorrido-sqlite.json` (`medidas.limite`) |

### Repository checks at this boundary

| Check | Result |
|---|---|
| `./verificar.sh --todo` | all OK: Python suite 1,254 (223 skipped need Postgres); full suite on Python 3.9.6; JavaScript 211/211; ruff; mypy (54 files); coverage **95%** (gate 80%) |
| Full suite, disposable local Postgres 16 (UTF-8) | 1,254 OK, zero skipped |
| Exact-head CI | on the final head of #29; see the PR |

The test the Linux container reported as environmental
(`test_the_system_python_has_no_openpyxl_of_its_own`) passes on this Mac, as
it does in CI.

### Reused, not rerun

The 25,000-record timings, the summary-cost table, the renderer/research
evidence, the earlier screenshots and the multi-round memory runs. One new
screenshot: `correccion-r3/capturas/07-r3-b2-revocado-durante-completar.png`.

### Limits of this step

- The final-digest journey delays the page's `crypto.subtle.digest` to make
  the window observable; the digest itself is the browser's. The other
  journeys change nothing in the page.
- Write-right loss during upload (archived terrain or base) is covered by B's
  mounted journey with its passive host, not repeated in the real host here.
- R3-B3 (recovery phases) and R3-B4 (pipeline permit) have no integration
  boundary of their own; they are covered by the supervisor's probe above, B's
  node regressions and B's 19 + 8 browser journeys, all rerun on this tree.
- A table that has lost its whole scope does not look again by itself: after
  the grant is given back the page has to be reloaded (or "Actualizar"). Not
  changed here.
- Browser runs on Postgres remain the one focused smoke. No screen reader.
- Still open, as the packet reserves them: R3-A1 summary batching (8
  statements per terrain) and the unexplained ~15 kB/round heap slope.

Stop for supervisory review. No 4A, no GitHub PR or main merge, no
deployment, no real account or data.

## 8. R3-A2: write permission is revalidated when a file write is refused (2026-10-12)

Supervisor packet `63b363a6e2553121d0db43d9e9981ea397905887`,
`reports/round-3-corrections-review-2026-10-12/` (START_HERE, TEAM_A). Only
R3-A2 and its verification. Team B's candidate was **not** merged again; R3-A1
batching was not started.

### Heads

| What | Exact commit |
|---|---|
| #29 head with B's corrections consumed (start) | `84a3656429ea4cb3eda05e741794d11efb39b4c8` |
| Team B candidate already consumed, merge `e795935…` (parents `0e9e2c1…`, `b2ac9bd…`) | `b2ac9bd176043fc4b1625b13993f8f21407dc978` |
| Code head (the fix and its journeys) | `3f77c537b1d2ade93cb88c686dea9a4e5b4dcda1` |
| Final head (this section and its evidence) | the head of draft PR #29, in its description |
| Frozen C1 (#27), unchanged | `49b782d147591236cc7f311c7e0de1948ad5258e` |

### Reproduced first

The supervisor's unmodified `probe_archive_readonly.mjs` on an exact copy of
`84a3656`: completion 409, upload control visible and enabled, detail
`data-solo-lectura="0"`, row present (`correccion-r3-a2/sonda-antes-84a3656.json`).

### Fix (A-owned host files only)

`web/components/tabla/Tabla.js`, `web/components/tabla/dialogos.js`,
`web/components/app.js`, one style rule. No server, schema, bridge or Team B
file changed; no new dependency.

- **A distinct path.** The widget codes `terreno_archivado`, `base_archivada`
  and `forbidden` no longer end in a toast. They start a revalidation of
  exactly what the refusal names. 404 keeps its own path (row, detail and
  private names removed, bases looked at again); 401 keeps the session's.
- **The record.** The one-terrain refresh that already existed now also takes
  `archived_at` and `base_id` — permission metadata — and still nothing else:
  not the version, the draft or the custom values. They are taken only from
  an answer **at least as new as the row** (`version >=`), so an older answer
  cannot undo an archive, a restore or a transfer the table already has.
- **Visibility by view.** A terrain now archived leaves a view that does not
  include archived records, and a terrain moved to another base leaves a base
  view — the same thing that happens when this person archives or transfers
  it — **unless the row holds an open editor or an unresolved change**: then
  it stays, marked archived and read-only, with that work intact. With
  "Incluir archivados" it always stays, read-only.
- **Live read-only.** Rows, cell file mounts and the open detail get the
  current `soloLectura`. The detail no longer captures it once: a new
  `permisos({archivado, puedeCambiar, resumen})` updates B's mounts, the
  "Archivado" note and the actions (archive ↔ restore, transfer) while what is
  being read — lists, history, a download — stays.
- **The base.** `base_archivada` reloads the bases. An operator loses an
  archived base (the existing scope-loss path clears the view); an
  administrator keeps it and every row, mount and the open detail become
  read-only, with the existing notice and without "Agregar terreno".
- **The role and the mode.** `forbidden` asks the server again who this is and
  whether the application is read-only (`onRevalidar`). A changed account or
  role goes through the session's existing teardown; an unchanged one keeps
  its table and only repaints what may be written.
- **Editors.** Permission changes repaint rows cell by cell: a cell with an
  open editor is not touched, and unresolved changes stay in the tray.
  `tabla.permisos()` no longer skips its work while an editor is open.
- **One related defect found by the journeys and fixed.** A dialog's `close`
  event arrives a task after it closes; the focus it hands back to the table
  could land on top of a cell or editor focused in between. Focus is now
  returned only if nothing else has it.

### Evidence

Owner's Mac (macOS, Google Chrome, loopback, synthetic accounts and data), at
the code head. Files in `evidencia/correccion-r3-a2/`.

| Check | Before (`84a3656`) | After |
|---|---|---|
| Supervisor `probe_archive_readonly.mjs`, unmodified | control visible and enabled, `soloLectura=0`, row 1, detail 1 | **no upload control, row 0, detail 0** in the default active-only view (`sonda-despues.json`) |
| Terrain archived while an upload completes, active-only view: real 409; row and detail leave, no write control anywhere; the other row of the base still edits and saves | fails: the archived row stays | ok (SQLite and Postgres) |
| The same with "Incluir archivados": the row stays with its "Archivado" mark and read-only cells; the open detail turns read-only (`data-solo-lectura="1"`, no picker), says it is archived and offers "Restaurar", not "Archivar"; **the stored PDF is still listed and downloads byte-identical**; then, with an editor open in another row holding unsaved text and a 2-character selection, a second terrain is archived during its upload: text, selection and focus are intact and the cell then saves at version +1 | fails: the detail stays editable | ok |
| A row with an unresolved change (a rejected value kept in the tray) is archived during its upload, active-only view: the row is **not** removed, it shows archived and read-only, the typed text is still there | fails: the detail stays editable | ok |
| Base archived while an **administrator** uploads: real 409; the detail and every cell become read-only, the notice appears, "Agregar terreno" is gone, both rows remain readable | fails: the detail stays editable | ok |
| Base archived while an **operator** uploads: the base is no longer theirs; row, detail and names are gone, no write control | ok (already the scope-loss path) | ok |
| `forbidden` — **simulated** answer (the test fulfils the completion with 403 `forbidden`; with the two existing roles the real policy cannot produce it for a file write): `/api/session` and `/api/config` are asked again, the table is not rebuilt, the row and the detail stay, another row still edits | fails: nothing is asked | ok |

404 still clears private state: the four R3-B2/B1 scope-loss journeys of §7
pass unchanged on this head. The live writable control is the unchanged PDF
and KMZ journeys.

| Combined rerun | Result |
|---|---|
| Real combined journey, SQLite | **39/39** (the 30 of §7, six R3-A2 journeys, three more no-page-error sessions), with the true restart on the same database and store (2 server starts) and the 100,000-vertex body (upload 8.4 s, selection → drawn 163 ms, heap 4.5 → 26 → 4.6 MiB) |
| Focused disposable Postgres 16 | **18/18**: the §7 smoke, restart on the same schema and store, upload denial by revocation, and the archived-during-upload journey |
| Team B scope / widget journeys, mounted | 8/8, 19/19 |
| Host / 2A table / identity journeys | 6/6, 13/13, 16/16 |
| `./verificar.sh --todo` | all OK: Python suite 1,254 (223 skipped need Postgres); full suite on Python 3.9.6; JavaScript 211/211; ruff; mypy (54 files); coverage **95%** (gate 80%) |
| Full suite, disposable local Postgres 16 | 1,254 OK, zero skipped |
| Exact-head CI | on the final head of #29; see the PR |

The before column of the six journeys is the same script run on an exact
archive of `84a3656` with `RECORRIDO_SOLO=R3-A2`
(`recorridos-a2-antes-84a3656.log`).

### Decisions made here, for review

1. In an active-only view an archived terrain **leaves**, with its detail, and
   a message says where to find it — unless it holds unsaved work. Keeping the
   detail open read-only there was the alternative the packet also allowed.
2. `archived_at` and `base_id` are applied only from an answer whose version is
   not older than the row's.
3. Focus is handed back from a closed dialog only when nothing else has it.

### Limits

- `forbidden` is exercised with a simulated answer only. The application's
  read-only mode answers file writes with a 403 that carries no code; the
  widget reports that as an ordinary error and the host does not revalidate on
  it. Not changed: it is not one of the three codes of the contract.
- After an administrator restores a terrain or a base, an open table learns it
  on its next refresh ("Actualizar", a save, or a file event), not by itself.
- An editor that is open on a row at the moment that row becomes read-only is
  left open on purpose; its save is then refused by the server and the text
  stays in the tray.
- The journeys ran on SQLite, with one of them also on Postgres. No screen
  reader. The 25,000-record timings, renderer and research evidence are
  reused, not rerun.
- Still open, as reserved: R3-A1 summary batching and the heap slope.

Stop for supervisory review. No 4A, no GitHub PR or main merge, no
deployment, no real account or data.

## 9. R3-A2 residual: write permission per row in global views (2026-10-12)

Owner-relayed supervisor instruction, on top of `41d029c54848a7aebb1d46dfd053848ccf265afc`.
Only this residual case. Team B's candidate was not merged again.

### Heads

| What | Exact commit |
|---|---|
| Reviewed #29 head (start) | `41d029c54848a7aebb1d46dfd053848ccf265afc` |
| Code head (fix + journey) | `191491e387709ef21b0ee81437abe1768b0dbd76` |
| Final head (this section and its evidence) | the head of draft PR #29, in its description |
| Team B candidate consumed earlier / frozen C1 | `b2ac9bd176043fc4b1625b13993f8f21407dc978` / `49b782d147591236cc7f311c7e0de1948ad5258e` |

### Reproduction, on `41d029c`

Administrator in `#/tabla/maestra` opens a terrain and uploads a PDF; the
completion is held; another administrator session archives that terrain's
base; the completion is released and answers a real 409. The detail turns
read-only (§8), but once it is closed a new editor still opened on the row.
The new journey fails there with "la fila de la base archivada sigue editable"
(`correccion-r3-a2-residual/residual-antes-41d029c.log`).

### Cause and fix

`web/components/tabla/Tabla.js`: `filaEditable()` asked whether the **view's**
base was archived. The master table and the unassigned view have no base
(`baseActual()` is null), so a row there was writable whatever had happened to
its own base. The rule is now one expression used everywhere a row's cells or
file cells are decided (painting, repainting, opening an editor, mounting and
updating the file slots):

```js
filaEditable = (t) => !vistaSoloLectura() && puedeCambiarFila(t) && !t.archived_at
puedeCambiarFila = (t) => !soloConsulta() && !(t.base_id && baseDe(t.base_id)?.archivada)
```

So a row is writable only if the view, **the row's own base** and the row
itself allow it. In a base view the two base checks coincide, so nothing
changes there. `puedeCambiarFila` already governed the detail; the table and
the detail now agree. No other file changed.

A base the table does not know about (not in the list the server gave this
account) does not make a row read-only by guesswork: the server still decides
each write.

### Regression and controls (one real-application journey, master table)

Two bases and four terrains: the uploading terrain and a sibling in the base
that gets archived, one terrain in another active base, one unassigned.

- Before the archive all four rows are editable.
- The sibling holds an unresolved change (a rejected value kept in the tray).
- Real 409 on completion; the detail becomes read-only with no write control.
- **Permitted read:** the PDF stored earlier is still listed in that detail and
  downloads byte-identical.
- After closing the detail: both rows of the archived base are read-only
  (`aria-readonly`), and neither Enter, a double click nor typing opens an
  editor on them.
- **Pending text kept:** the sibling's unresolved text is still in its cell
  and in the tray.
- **Controls:** the terrain of the other active base and the unassigned one
  still open an editor, save, and move to version +1; "Agregar terreno" is
  still offered in the master table.
- The server agrees: a direct write to the archived base's terrain is refused
  (409).
- After the base is restored and the page reloaded, the same row is editable
  again.

The by-base views keep their own journeys from §8 (administrator: whole view
read-only; operator: view cleared), unchanged and passing.

### Verification

Owner's Mac (macOS, Google Chrome, loopback, synthetic data), at the code head.
Files in `evidencia/correccion-r3-a2-residual/`.

| Check | Result |
|---|---|
| The new journey on `41d029c` | fails on the defect |
| The new journey on the fix | ok, three runs in a row |
| Real combined journey, SQLite | **41/41** (the 39 of §8, the new journey and its session), true restart on the same database and store, 100,000-vertex body (upload 8.5 s, selection → drawn 163 ms, heap 4.5 → 26 → 4.6 MiB) |
| Focused disposable Postgres 16 | 18/18, with restart on the same schema and store |
| Team B scope / widget journeys, mounted | 8/8, 19/19 |
| Host / 2A table / identity journeys | 6/6, 13/13, 16/16 |
| `./verificar.sh --todo` | all OK: Python suite 1,254 (223 skipped need Postgres); full suite on Python 3.9.6; JavaScript 211/211; ruff; mypy (54 files); coverage **95%** (gate 80%) |
| Full suite, disposable local Postgres 16 | 1,254 OK, zero skipped |
| Exact-head CI | on the final head of #29; see the PR |

### Limits

- The new journey ran on SQLite; the Postgres smoke is unchanged and does not
  include it. The rule is client-side and has no SQL of its own.
- Row permissions follow the bases as the table last loaded them: a base
  archived or restored elsewhere is learned on a file refusal, a refresh or a
  reload, not by itself. Until then the server refuses the write and the text
  stays in the tray, as before.
- An editor already open on a row at the moment its base is archived is left
  open, as in §8.
- Reused, not rerun: 25,000-record timings, renderer and research evidence.
  Still open as reserved: R3-A1 batching and the heap slope.

Stop for supervisory review. No 4A, no GitHub PR or main merge, no
deployment, no real account or data.
