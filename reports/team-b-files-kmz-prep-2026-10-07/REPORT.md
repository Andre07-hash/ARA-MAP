# Team B preparation report — attachments and KMZ geography

Team B · first assignment (preparation) · October 7, 2026

| Item | Value |
|---|---|
| Instruction commit | `bbd640dec00c055b43454f61b35861c38063b550` on `codex/supervisor-completion-brief` (PR #5, open). Read with `git show <sha>:<path>`; the checkout was not switched. |
| Documents read | `reports/master-table-plan/GITHUB_HANDOFF.md`, `MASTER_PLAN.md`, `TWO_TEAM_DELIVERY_PLAN.md`, `TEAM_B_START_HERE.md` (and `TEAM_A_START_HERE.md` for boundaries) |
| Application baseline | `origin/main` = `09452fd3` ("Merge pull request #7 … agent-instructions"). No application code was changed. |
| Branch / PR | `claude/wonderful-pasteur-py6va6` (the branch this session was assigned; the delivery plan's `claude/team-b/<item>` naming will be used for implementation branches) · draft PR against `main` |
| Report path | `reports/team-b-files-kmz-prep-2026-10-07/REPORT.md` |
| Status | Preparation only. Experiments are **disposable** and use **fictional** fixtures. Nothing is real-file acceptance, persistent storage, or hosted evidence. |

Open work checked on GitHub before starting: PR #4 (`codex/fix-vercel-inventory-api`, draft: Vercel inventory query fix + `api/index.py`/`vercel.json`), PR #5 (instructions), PR #6 (`claude/excel-onedrive-refresh`, draft, parked; head `9d45279`, reviewed implementation `415eb26`). **PR #6 claims `SCHEMA_VERSION = 9`**; Team A should reserve migration numbering with that in mind. No Team A branch or PR existed when this report was written.

---

## 1. Feasibility findings

### 1.1 Current renderer, identity and X/Y (audit at `09452fd`)

- **Drawing.** `web/components/map/MapCanvas.js` draws every terrain as one `L.circleMarker` at `[t.lat, t.lon]` (`render`, line ~139–190), filtered by `t.ubicado`. It is a circle of the declared area once zoom makes that true-scale (`web/lib/geo.js` `markRadius`), otherwise a fixed 7 px symbol. Selection, double-click "zoom to scale", tooltips and the basemap all live in this one factory with a small API: `render`, `select`, `fitTo`, `setView`, `viewport`, `zoomToScale`.
- **Who decides "located".** `ubicado` is computed outside the canvas: `web/lib/inventario.js` (`estadoUbicacion` → `ubicacion()`, line ~50–61, used by `itemDeInventario`) for the inventory, and `server/repo/mapas.py` `terrenos()` via `server/validation.py` `location_state` for saved maps. `app.js` (lines ~585, 734), `UnplacedList`, `filters.js` ("Solo con ubicación", line 32) and the table's `is-unplaced` flag all key off `t.ubicado`. **So the smallest extension is: compute `ubicado` from "boundary or X/Y", and teach only `MapCanvas` to draw a boundary.** Tables, filters and the unplaced list then follow without edits.
- **Things that would break if `ubicado` simply became true for a boundary-only terrain** (blank X/Y), and therefore must be handled in the extension:
  - `coincidentRingOffsets` calls `terreno.lat.toFixed` (`geo.js` line 71) → TypeError on `null`.
  - `fitTo` collects `[t.lat, t.lon]` (`MapCanvas.js` ~264); `select({pan})` and `zoomToScale` read the circle marker's lat/lon and `superficie_m2`.
  - `reportScale` counts circles only; the test hook `__araTest.puntoDe` (`app.js` ~903) uses lat/lon.
- **X = latitude, Y = longitude** throughout: import aliases, `validation.py` (`ETIQUETAS_CAMPO`), exports (`server/api/exportar.py` lines 50–51), detail panels ("Latitud (X)"). KML and GeoJSON are **longitude, latitude**. The proposal keeps these apart: geometry is stored as GeoJSON `[lon, lat]`; anything handed to Leaflet as a point is `[lat, lon]`; **X/Y are never read from or written by KMZ processing**, and a geometry-only terrain exports blank X/Y.
- **Saved maps are frozen copies** (`server/repo/mapas.py`, `mapa_terreno` rows copied from legacy `terreno`, `base_id` intentionally not an FK). Existing maps have no geometry and need no change. The master-record → derived view/snapshot model is Team A's (wave 3); B's requirement is in §2.6.
- **Identity.** The inventory already gives stable UUID ids (`inventory_terrain.id`) with a `version` concurrency counter, immutable revisions and an append-only `inventory_event` with `UNIQUE (inventory_id, version)`. Attachments should hang off that id, not off legacy `terreno.id` / name+estado+municipio+superficie.
- **Coupling to flag for A:** `server/inventario.py` publication blockers require valid X/Y (`location_invalid`, line ~138). A boundary-only terrain is therefore unpublishable. That is consistent with "no automatic publication of master data/files", but it is an explicit decision (see §6).
- **Hosting constraints.** Vercel functions cap request *and* response payloads at 4.5 MB (the app enforces 4 MB in `api/index.py`); `vercel.json` sets `maxDuration: 120`. The local server accepts 25 MB (`server/app.py` `MAX_BODY`). Uploads already use raw-bytes bodies with the filename in a header (`server/api/importar.py`) — no multipart parser exists, and Python 3.13 removed `cgi`. A function's filesystem is not durable. Consequence: in the cloud, files larger than ~4 MB cannot pass through the function in either direction; **uploads and downloads must go browser ↔ private storage directly, with the server authorizing each transfer.**

### 1.2 KMZ processing — disposable experiment (fictional files only)

`experiment/kmz_experiment.py` (stdlib only, 3.9-compatible syntax) runs the proposed pipeline: bounded unzip → choose the KML document → parse with DTD/entities refused → extract polygons per placemark → choose or require a choice → normalize to a MultiPolygon with bbox, symbol point and calculated area. `experiment/make_fixtures.py` builds 20 fictional KML/KMZ cases (the `.kml` sources are in `experiment/fixtures/`). **No company KMZ was available; none of this is acceptance against real files.**

| Case (fictional) | Outcome | Rule |
|---|---|---|
| One polygon | `listo`, 1 part | Boundary becomes the terrain's layout |
| Polygon with hole | `listo`, 1 hole, hole subtracted from calculated area, rendered as a hole | Holes in first scope |
| One placemark, `MultiGeometry` of 2 polygons | `listo`, 2 parts | Multipart = one terrain |
| Folder with 3 placemarks, each a polygon | `requiere_eleccion`, 3 named candidates with folder path and area; **no geometry until someone chooses** | Never pick the first; user may choose one or several (several → one multipart terrain) |
| Polygon + LineString roads + Point | `listo` with warning "se ignoraron 1 LineString, 1 Point" | Internal lines not in first scope; reported, kept in original |
| Points only / lines only / GroundOverlay only | `fallido`, message names what the file *does* contain | Flag unsupported content |
| NetworkLink | Not fetched; `fallido` (no polygon) + warning if mixed | Never follow external links |
| `<!DOCTYPE>` / entity expansion | `fallido` `KML_DTD_NO_PERMITIDA` | Parser refuses DTD and entity declarations |
| 3D / extruded polygon | `listo` 2D + warning "altitud descartada" | 3D not reproduced |
| lat/lon written in the wrong order | `fallido` `KML_COORDENADAS_INVALIDAS` (Mexican longitudes exceed ±90 as latitudes) | No silent swap |
| In-range polygon outside Mexico | Stored, `utilizable: false`, warning; **not drawn, not "located"** | Same bounds as X/Y `location_state` |
| Ring with < 3 vertices / broken XML / not a zip / no KML | `fallido` with specific code | Plain-language message |
| Several root KMLs without `doc.kml` | `fallido` `KMZ_VARIOS_KML` | Ambiguous package: no guess |
| `doc.kml` + extra KML/images | Uses `doc.kml`, warns that others were not processed | Google KMZ convention |
| 8 MB of compressible padding (zip-bomb stand-in) | `fallido` `KMZ_EXPANSION_EXCESIVA` before full expansion | Ratio, total-size, entry-count, depth, vertex and placemark limits |

Evidence: `python3 -I experiment/test_kmz_experiment.py` → **14 tests OK** (covering all 20 KMZ + 1 bare KML case); raw outputs in `evidence/experiment-output.txt`. Calculated area of the 0.004°×0.003° fictional rectangle at 20.6° N is 139,195 m², matching the hand calculation (~139,100 m²) within the spherical approximation.

Not yet established (needs real files, Phase 4): typical vertex counts and sizes; whether company files use one placemark per terrain or folders of lots; whether internal roads/lot lines matter; self-intersecting rings (not validated yet; proposal: store, warn, still draw); KML `<Style>` colours (ignored; the app's colour rules apply).

### 1.3 Rendering — disposable experiment

`experiment/ubicacion_prototype.mjs` implements the proposed rule as pure functions over the existing `estadoUbicacion` and `geo.js` helpers; `experiment/render_harness.html` draws it with the app's vendored Leaflet in headless Chromium.

- `node --test …/ubicacion_prototype.test.mjs` → **7 tests pass**: boundary locates a terrain with blank X/Y; X/Y-only behaviour unchanged (including swapped/invalid pairs staying unlocated); processing/failed/unusable geometry falls back to X/Y; partition keeps each terrain once; bounds cover both kinds; small boundary is a symbol at country zoom and land at street zoom; X/Y far from the boundary is reported as a conflict and not altered.
- Screenshots `evidence/render-fit.png` (zoom 16: hole drawn as a hole, two-part terrain, X/Y terrain unchanged, selected boundary outlined), `render-12.png`, `render-7.png`, each with its text log (`render-*.txt`). A simulated Leaflet `click` on the multipart boundary selected terrain id `t-multi` — a simulated event, not a user-driven browser test.
- **Findings from the render:** (a) at country zoom a boundary must hand over to the existing symbol at a representative point, otherwise it vanishes (mirrors today's circle symbol→footprint handover); (b) the coincident-ring logic must include boundary symbol points — at zoom 7 three nearby fictional terrains collapse onto one dot (`render-7.png`); (c) at the handover zoom a ~400 m parcel is only ~15–20 px and hard to click; production should hand over later (e.g. ≥ 24 px) or keep the symbol on top until then. No basemap tiles were loaded (offline harness).

**Feasibility verdict:** boundary-first rendering fits inside `MapCanvas` as an added layer type next to the circle markers, with the X/Y path untouched. KMZ parsing is feasible with the standard library inside the existing hosting limits, provided the file reaches the server from storage (not through the request body) in the cloud.

---

## 2. Draft attachment and geometry contract (for A's review)

Fictional request/response examples: `examples/01…08-*.json`. Error shape is the existing one: `{"error": "<es>", "detalle": {"code": "<code>"}}`. All new routes are private (not in `server/auth.py` `PUBLIC_API`).

### 2.1 Entities (B's schema requirements — A lands them in the shared migration)

```
archivo                        one attachment on one terrain cell
  id                 TEXT PK (uuid)
  inventory_id       TEXT NOT NULL → inventory_terrain(id)
  columna_id         TEXT NOT NULL   'core:archivos' | 'core:kmz' | custom column id (A's stable ids)
  tipo               TEXT NOT NULL CHECK IN ('pdf','kmz')
  version_activa_id  TEXT NULL       last version that reached 'listo'
  creado_en/por, actualizado_en/por
  retirado_en/por    soft removal; purge is a separate admin operation

archivo_version                immutable; one per upload
  id                 TEXT PK (uuid)
  archivo_id         TEXT NOT NULL → archivo(id)
  numero             INTEGER NOT NULL, UNIQUE (archivo_id, numero)
  estado             TEXT NOT NULL CHECK IN ('subiendo','procesando','requiere_eleccion',
                                             'listo','fallido','abandonado')
  nombre_original, tipo_mime, tamano INTEGER, sha256 TEXT
  clave_almacen      TEXT NOT NULL   opaque storage key; never sent to clients
  error_codigo, error_mensaje, avisos_json, candidatos_json, eleccion_json
  creado_en/por, completado_en

geometria                      immutable; normalized output of one KMZ version
  id                 TEXT PK (uuid)
  archivo_version_id TEXT NOT NULL UNIQUE → archivo_version(id)
  geojson            TEXT NOT NULL   MultiPolygon, positions [lon, lat]
  bbox_oeste/sur/este/norte REAL NOT NULL
  punto_lat, punto_lon REAL          symbol point only — never copied into X/Y
  area_calculada_m2  REAL            shown as "calculada"; never overwrites Superficie/HA
  partes, huecos, vertices INTEGER
  utilizable         INTEGER (0/1)   false when outside the Mexico bounds
  creado_en

archivo_evento                 append-only audit (see question Q3)
  id, archivo_id, archivo_version_id, accion, actor_id, actor_name, at, details_json
```

All SQL in `server/repo/archivos.py`, written for SQLite and Postgres. Text UUID ids, so none of these tables joins `postgres.ID_TABLES`.

### 2.2 Rules

1. **Relationship.** Files belong to a terrain id **and** a column id. The core `KMZ` column holds at most one active `archivo` (its active version is the layout). The core `Archivos` column holds many PDFs. Custom attachment columns may hold PDF/KMZ but **never** feed the map.
2. **States.** `subiendo → procesando → listo | requiere_eleccion | fallido`; `requiere_eleccion → listo` after an explicit choice; `subiendo → abandonado` on cancel or after 24 h. A PDF goes `subiendo → listo | fallido` (magic-byte check `%PDF-`; contents are never rendered or executed server-side).
3. **Active / last-valid.** `version_activa_id` moves only when a version reaches `listo`, in the same transaction. Failed, pending-choice and in-progress versions never replace it. The terrain's **active geometry** = geometry of the active version of its `core:kmz` file, if `utilizable`.
4. **Located.** `modo = "geometria"` if there is an active usable geometry; else `"punto"` if X/Y is `valida`; else `"ninguna"`. A boundary-only terrain is located. `conflicto_xy = true` when valid X/Y lies outside the bbox + ~500 m; shown for review, nothing is corrected.
5. **Replacement / removal.** Replace = new version on the same `archivo`. Remove = soft-retire the `archivo` (versions and objects kept). Retiring the KMZ falls back to X/Y. Purge, restore and orphan cleanup are separate, admin-only, later operations.
6. **Record version.** File operations do **not** increment `inventory_terrain.version`, so an upload never makes a concurrent cell edit conflict. Listing/detail expose read-only `ubicacion` and `archivos` summaries (`examples/01`).
7. **Access.** Every list/upload/download/choose/retire call checks the caller's capability for that terrain on the server. Downloads: local streams with `Content-Disposition`, `nosniff`, `CSP: sandbox`; cloud returns `302` to a **signed URL valid ~60 s**, created only after the check, never stored, logged or rendered (`examples/06`). Storage objects are never public.
8. **Idempotency.** Starting an upload takes `Idempotency-Key`, as inventory create does today.
9. **Integrity.** Client sends size and SHA-256; `completar` verifies the stored object before processing.

### 2.3 Routes (handlers in B's `server/api/archivos.py`; A registers them)

| Method & path | Purpose |
|---|---|
| `GET /api/inventario/terrenos/:id/archivos` | Attachments + versions + server-computed `permisos` |
| `POST /api/inventario/terrenos/:id/archivos` | Start upload (new file, or new version with `archivo_id`) → version + upload target |
| `PUT /api/archivos/versiones/:vid/contenido` | **Local backend only**: raw bytes, like the importer |
| `POST /api/archivos/versiones/:vid/completar` | Verify object, process (PDF check / KMZ pipeline), maybe activate |
| `POST /api/archivos/versiones/:vid/eleccion` | Resolve `requiere_eleccion` with candidate indices |
| `POST /api/archivos/versiones/:vid/cancelar` | Abandon an in-progress upload |
| `GET /api/archivos/versiones/:vid/descarga?modo=ver\|descargar` | Authorized open/download |
| `DELETE /api/archivos/:aid` | Retire (soft) |
| `GET /api/geometrias?ids=…` | GeoJSON for immutable geometry ids (bulk, for the map) |

KMZ processing runs inside `completar` (bounded: ≤ 20 MB package, ≤ 60 MB expanded, well inside `maxDuration: 120`). If real files show it is slow, `completar` can return `procesando` and the client polls the version — the states already allow it.

### 2.4 Snapshot retention (requirement for A's wave-3 model, `examples/07`)

A dated snapshot stores `geometria_id` and the `archivo_version` ids it showed — references to immutable rows, not copies of GeoJSON/files. A version referenced by any snapshot cannot be purged. Replacing or retiring a terrain's KMZ moves pointers only, so saved maps keep their recorded boundary. Existing saved maps (no geometry) are unchanged.

---

## 3. Widget boundaries (for A's grid and detail panel)

Plain ES modules returning DOM nodes, built with `web/lib/dom.js` `el()` like the existing components. **B owns:** `web/components/archivos/`, `web/lib/archivos.js` (pure: labels, states, client-side type/size checks, error text), `web/lib/subidas.js` (upload jobs), `web/lib/geometria.js` (pure location rule, as in the prototype), `web/styles/archivos.css`.

```js
// Grid cell. Owns drop target, upload button, progress, status chip.
ArchivoCelda({
  terrenoId,                         // A's stable inventory id
  columna: { id, tipo: "pdf"|"kmz", multiple },   // from A's column definitions
  resumen,                           // terreno.archivos[columna.id] from A's listing (examples/01)
  permisos: { subir, retirar, descargar },        // from A's capability response; never assumed
  onCambio(resumenNuevo),            // B → A: replace the summary in the store (no mutation)
  onAbrirDetalle(),                  // A opens its detail panel / drawer
}) → HTMLElement

// Detail-panel section: file list, versions, open/download, replace, retire,
// KMZ status, warnings and the "elige el contorno" chooser.
ArchivoDetalle({ terrenoId, columna, permisos, onCambio, onVerEnMapa(terrenoId), onCerrar })
  → HTMLElement
```

- **Upload state survives re-renders.** The app replaces state and re-renders views; an in-flight upload must not live in a DOM node. `subidas.js` keeps jobs keyed by `terrenoId:columnaId`, exposes `suscribir(clave, fn)`, and uses `XMLHttpRequest` for upload progress (fetch has none) with abort and retry. Leaving the grid does not cancel an upload; signing out (`api.abortPrivate`) does.
- **Keyboard.** Cell is focusable; `Enter` opens detail; `Delete`/`Backspace` never removes files (retire is a confirmed action in detail only). The cell never captures the grid's arrow keys.
- **Events to A:** only `onCambio` and `onAbrirDetalle`. B never touches A's record fields, version, or save queue. After `onCambio`, A may refresh the row; no record conflict can result (rule 6).
- **Map hook:** `MapCanvas.select(terrenoId, {pan})` works for boundaries (fits the boundary). Selecting a boundary calls the existing `onSelect(id)`.

---

## 4. Storage recommendation

| Option | Fit | Notes |
|---|---|---|
| **S3-compatible private bucket (Cloudflare R2 or AWS S3) — recommended** | Direct browser PUT and short-lived GET via presigned URLs bypass the 4.5 MB function limit. SigV4 presigning is ~100 lines of stdlib `hmac`/`hashlib`, so **no new dependency** in local or cloud code. Provider-neutral. | Operator creates bucket, CORS for app origins, scoped key. R2 has no egress fees; S3 has mature versioning/backup. |
| Vercel Private Blob | Same vendor as hosting; private stores and signed URLs are GA. | SDK is JavaScript (`@vercel/blob`); client uploads use `handleUpload`/`upload()`. From a Python backend with no build step we would depend on the REST/control API and vendor a browser client. Higher integration risk; reconsider if the operator wants a single vendor. |
| Postgres `bytea` in Neon | Files and records restore together. | Still capped at 4.5 MB per request/response → chunked upload *and* download; grows the database and its backups. Fallback for small files only. |
| Function filesystem | — | Not durable. Excluded. |

**Local (Mac) backend:** files under `datos/archivos/<sha256 prefix>/<version id>` (`datos/` is already git-ignored), same API with a local upload URL. One interface in `server/almacen.py`: `destino_subida(clave, …)`, `verificar(clave) → tamano, sha256`, `leer(clave, limite)`, `url_descarga(clave, nombre, modo)`, `borrar(clave)`.

**Proposed limits (to confirm with real samples):** PDF ≤ 50 MB, KMZ ≤ 20 MB. Scanned deeds can exceed 20 MB; KMZ with only boundaries are usually KB-sized, larger only with embedded imagery.

**Operator actions (later, not done here):** choose provider/account; create **separate private buckets (or prefixes with separate keys) for local tests, Preview and Production**; block all public access; CORS allowing `PUT`/`GET` from the app's origins only; bucket-scoped credentials as Vercel env vars (Preview first); lifecycle rule for abandoned uploads; versioning/backup policy aligned with the Neon backup schedule so files and rows can be restored together. B needs nothing provisioned to start: the local backend and a fake S3 endpoint in tests cover packets 1–3.

---

## 5. Shared-file requests to Team A

| # | Path(s) | Change | Contract / example | Needed by | Acceptance check |
|---|---|---|---|---|---|
| R1 | `server/db.py`, `server/postgres.py`, schema version | Tables `archivo`, `archivo_version`, `geometria`, (`archivo_evento`) per §2.1 + indexes `(inventory_id, columna_id)`, `(archivo_id, numero)` | §2.1 | B-3 | Migration test on SQLite + disposable Postgres; existing data untouched; coordinate number with PR #6's v9 |
| R2 | `server/auth.py` / A's capability module | Capabilities for files: view/download, upload/replace, retire, choose layout; a helper B's handlers call, e.g. `require_capability(request, terrain_id, "archivos.subir")` | Role table in MASTER_PLAN §6 | B-3 | Operator allowed, unauthenticated 401, missing capability 403 — on every B route incl. download |
| R3 | `server/app.py` | Register the routes in §2.3 | §2.3 | B-3 | Route table test |
| R4 | `server/repo/inventario.py` DTO | Add read-only `ubicacion` and `archivos` summaries (B supplies the query helpers in `server/repo/archivos.py`) | `examples/01` | B-5 | Listing returns them; `version` unchanged by file ops |
| R5 | `web/lib/inventario.js` `itemDeInventario` | Compute `ubicado` via B's `ubicacionDe(t)` from `web/lib/geometria.js` | prototype `ubicacion_prototype.mjs` | B-5 | Boundary-only terrain is not in UnplacedList; "Solo con ubicación" keeps it |
| R6 | `web/components/app.js` | Pass geometry loader to `drawMap`; mount `ArchivoDetalle` in detail; feature gate | §3 | B-5/B-6 | Existing e2e map tests still pass |
| R7 | Column definitions | Stable ids `core:archivos`, `core:kmz` (or A's equivalent) and an attachment column type | §2.2 rule 1 | B-4 | Grid fixture uses them |
| R8 | Snapshot model (wave 3) | `geometria_id` + file-version refs per snapshot row; purge guard | `examples/07` | wave 3 | Replace KMZ after snapshot → snapshot unchanged |
| R9 | `.github/workflows/checks.yml` | Confirm B's new `tests/test_kmz.py` / `tests/test_archivos*.py` run in the Postgres job (discovery should already pick them up) | — | B-3 | CI green |

---

## 6. Questions and decisions

| # | Question | Recommendation | Owner | Blocks |
|---|---|---|---|---|
| Q1 | Storage provider | S3-compatible (R2 or S3) behind `server/almacen.py` | Operator/owner, Phase 3 | Hosted storage only (B-7) |
| Q2 | File limits and multiplicity | Multiple PDFs; one active KMZ; PDF ≤ 50 MB, KMZ ≤ 20 MB | Owner, after samples | Final limits only |
| Q3 | File audit: own table or extend `inventory_event`? | Own `archivo_evento` (the existing table's `UNIQUE(inventory_id, version)` ties events to record versions, which file ops do not bump) | A + supervisor | R1 |
| Q4 | Who may choose/replace/retire layouts | Operators may upload/replace/choose; retire per A's archive/delete decision | Owner via supervisor | Not B-1/B-2 |
| Q5 | Accept bare `.kml` uploads in the KMZ column? | Yes (same parser) | Owner | None |
| Q6 | Is a boundary ever public, and can a boundary-only terrain be published? | No public geometry/files in this release; keep the X/Y publication blocker | Owner | Nothing now |
| Q7 | Real company KMZ samples (5–10, varied) | Needed before Phase 4 acceptance; shared privately, never committed | Owner | B-4 acceptance |
| Q8 | Internal roads/lot lines | Ignore with a warning until samples show the need | Owner, Phase 4 | None |

---

## 7. Proposed PR sequence (small, independently reviewable)

Ready-local work (no A prerequisite, no cloud) is marked **L**.

| PR | Branch | Content | Depends on | Tests |
|---|---|---|---|---|
| **B-1 L** | `claude/team-b/kmz-parser` | `server/kmz.py` (production version of the experiment), fictional fixtures under `tests/fixtures/kmz/`, `tests/test_kmz.py` | Contract consolidation | All §1.2 cases; limits; 3.9 suite; mypy/ruff |
| **B-2 L** | `claude/team-b/map-boundaries` | `web/lib/geometria.js` + `MapCanvas` boundary layer, symbol handover, coincident points incl. boundary symbols, `fitTo`/`select`/`zoomToScale` for boundaries; driven by fixture data; X/Y path untouched | B-1 fixtures (data only) | node tests; existing `geo.test.mjs` unchanged; e2e: boundary click selects the row, X/Y maps unchanged |
| **B-3 L** | `claude/team-b/attachments-api` | `server/almacen.py` (local disk + S3 SigV4 presign, tested against a fake endpoint), `server/repo/archivos.py`, `server/api/archivos.py` | **R1, R2, R3** (stacked draft until they merge) | Upload/complete/replace/fail-keeps-previous/retire/download 401/403; SQLite + disposable Postgres |
| **B-4 L** | `claude/team-b/attachment-widgets` | `ArchivoCelda`, `ArchivoDetalle`, `archivos.js`, `subidas.js`, styles; KMZ chooser | B-3; R7 | node tests for pure modules; e2e against local server with fictional files |
| B-5 | `claude/team-b/integration` | Hand A the exact hook diffs for R4–R6; A lands them | A's grid | First joint milestone locally: blank terrain → PDF + KMZ → reload → boundary drawn with blank X/Y |
| B-6 | `claude/team-b/snapshot-geometry` | Geometry/file-version references in snapshots | A's wave-3 model, R8 | Replace after snapshot keeps snapshot |
| B-7 | — | Hosted storage verification in an isolated Preview | Q1 + operator provisioning | Hosted evidence, reported separately |

B-1 and B-2 can start the moment the supervisor issues the packet. B-3 can be built and tested locally against a stacked draft of A's migration, but must not merge before R1–R3.

---

## 8. Reproduce the evidence

From the repository root at this branch's head:

```bash
python3 -I reports/team-b-files-kmz-prep-2026-10-07/experiment/test_kmz_experiment.py
node --test reports/team-b-files-kmz-prep-2026-10-07/experiment/ubicacion_prototype.test.mjs
python3 -m http.server 8765 --bind 127.0.0.1   # then open
#   http://127.0.0.1:8765/reports/team-b-files-kmz-prep-2026-10-07/experiment/render_harness.html
```

Repository checks run on this branch are recorded in the PR description. Nothing here was run against Postgres, Vercel, real storage or real KMZ files.

Sources: [Google KMZ](https://developers.google.com/kml/documentation/kmzarchives), [KML reference](https://developers.google.com/kml/documentation/kmlreference), [Leaflet GeoJSON](https://leafletjs.com/examples/geojson/), [Vercel function limits](https://vercel.com/docs/functions/limitations), [bypassing the body limit](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions), [Vercel private Blob](https://vercel.com/docs/vercel-blob/private-storage), [Vercel Blob client upload](https://vercel.com/docs/vercel-blob/client-upload).
