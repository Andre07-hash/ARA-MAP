# Team B · B-2 report — boundary renderer

October 7, 2026 · Team B · draft PR on `claude/team-b/map-boundaries`

| Item | Value |
|---|---|
| Instruction commit | `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`: `reports/workspace-contract-2026-10-07/{START_HERE,SHARED_CONTRACT,TEAM_B_PACKET}.md` and `examples/boundary-terrain.json`, read with `git show` |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`, re-fetched before work; unchanged since issue |
| Branch / commits | `claude/team-b/map-boundaries`, started from that baseline: `327f9f3` renderer, helpers, tests and harness · `02a1e7c` largest-part handover and measurements · the commit adding this report |
| B-1 | PR #9 (`claude/team-b/kmz-parser`, head `efc3628`) untouched. Its parser was used only from an isolated `git archive` to generate fixtures (§5). Nothing imports it. |
| Scope | B-2 only. No A-owned file edited: `web/lib/inventario.js` is only imported, and the app shell, API/store/router, schema, auth, CI and deployment config are unchanged (verified with `git diff --name-only`). No storage, attachment API, widgets, geometry endpoint, snapshot persistence, dependency, build step or public access. |

## 1. What was built

| File | Content |
|---|---|
| `web/lib/geometria.js` (new) | Pure helpers for contract §4: `ubicacionDe({lat, lon, geometria}) → {modo, ubicado, xy}`, built on the existing `estadoUbicacion` (no second X/Y validator); `descriptorActivo`; `cuerpoLeaflet` (validates a body and converts it explicitly from GeoJSON `[lon, lat]` to Leaflet `[lat, lng]`); `limitesDeFilas`, `puntoDeSimbolo`, and the handover functions `contornoAEscala` / `zoomDeContorno`. |
| `web/components/map/MapCanvas.js` | `render(terrenos, {colorFor, dashFor, geometrias})`. Rows with an active, usable `t.geometria` draw from the body in `geometrias` (a `Map` from geometry ID to body). Rows with no `geometria` key take the established XY path unchanged. The factory, the existing methods and the callbacks are preserved. |
| `web/styles/map.css` | One tooltip line style for "Contorno no disponible" |
| Tests and harness | `tests/js/geometria.test.mjs` (18 tests), fixtures in `tests/js/fixtures/geometria/`, and in `tests/e2e/`: `contornos.html` (harness with the real `createMapCanvas` and vendored Leaflet), `contornos.mjs` (18 browser checks with real mouse input), `contornos-medicion.mjs` (measurements), `servidor-estatico.mjs`, plus a README section |

## 2. Required behaviour (packet §"Required behavior")

1. **Boundary before X/Y.** An active usable descriptor wins over X/Y. Shells, holes and every part are drawn as one `L.polygon`, and every part selects the same terrain ID. A blank X/Y or a missing declared area does not stop display or fitting. When X/Y disagrees with the boundary, the boundary is drawn and X/Y is never written.
2. **Symbol, then outline.** At distant zoom a symbol stands on the descriptor's validated `punto_interior`; it is never a circle scaled from area. The outline replaces it once the **largest part's** shell box is at least **24 CSS px on its shorter side**.
   - 24 px is the WCAG 2.2 minimum target size (SC 2.5.8).
   - The largest part, not the whole extent, decides because measurement showed that a multipart of scattered ~100 m parts otherwise became 1–2 px dots with no clickable target (fixed in `02a1e7c`, with a regression).
   - Coordinates are converted to Leaflet order only in `geometria.js`.
3. **Mixed data.** `select`, `fitTo`, `zoomToScale`, scale reporting and coincident rings all handle mixed boundary/XY rows.
   - `select(id, {pan})` frames the whole multipart extent.
   - `fitTo` includes every part.
   - Boundary symbols join the existing coincident-ring grouping.
   - XY-only behaviour is unchanged and **pixel-identical** to the baseline renderer (§4).
4. **Body missing or loading.** A body that isn't loaded, or that fails validation (malformed, oversized, or declaring bounds other than the active descriptor's; since the B-2 review also coordinates that disagree with its own bounds, §8), shows a hollow dashed symbol at the interior point with the tooltip "Contorno no disponible". It never becomes an outline and never jumps to X/Y. Without an active usable descriptor, valid X/Y keeps today's marker; with neither, the terrain is unplaced.
5. **Replacements, filtering and reset.**
   - The renderer draws only the active descriptor's body, so a pending or failed replacement body in the map is never drawn.
   - `render()` draws only the supplied rows, so stale map entries are ignored.
   - `render()` drops a selection or a pending click whose terrain is no longer drawn: there is no late `onSelect` for a filtered-out terrain.
   - **Reset path:** `render([])` clears every layer, the selection and any pending gesture. A calls it on session or scope change.
6. **Escaping and invalid input.** Names are escaped (the existing `escapeHtml`). KML descriptions and resources are never shown or fetched; the renderer receives only normalized bodies. Malformed rows, descriptors and bodies are handled without exceptions and never become footprints (browser check "entrada inválida").

**Additive results for A's caller**

| Surface | Addition |
|---|---|
| `render()` return | Count of placed terrains (XY marks plus boundaries), as before |
| `onScaleChange` | `contornos`, `contornosAEscala` (both 0 for XY-only maps); `aEscala` and `total` include boundaries |
| `zoomToScale(id)` on a boundary | Frames the boundary; returns the existing `a_escala` / `limite_de_zoom` plus `contorno: true` and `requerido` (the zoom at which the outline first shows). New state `contorno_no_disponible` when the body is not loaded. `app.js` currently shows no toast for an unknown state, so A should add one (§6). |
| `posicionDe(id)` (new method) | `{x, y, tipo: "punto" \| "contorno", contorno}` in container pixels, or `null`. Intended for the app's `?test=1` hook. |

## 3. Tests

| Check | Result |
|---|---|
| `node --test tests/js/*.test.mjs` | **116 pass**: 98 existing (including `geo.test.mjs`, unchanged) + 18 new |
| New helper tests | Cover: boundary only; XY only (existing validator, swapped X/Y stays invalid); neither; disagreeing locations without writing X/Y; 15 malformed or unusable descriptors; legacy rows; the contract example through A's adapter rule; explicit coordinate conversion; holes and parts; missing body; failed replacement (old body used; a body under the active ID with different bounds refused, a consistency check, not a version guarantee, §8); 9 malformed bodies; body over the vertex limit; the 24 px handover; largest-part box; mixed bounds; coincident rings |
| Browser, `tests/e2e/contornos.mjs` | **18/18 pass**, stable on 3 consecutive runs. Headless Chromium 141.0.7390.37, Playwright-core 1.63. Fixture `contornos.json` at this branch. Output: `evidencia/contornos-salida.txt`, `resumen.json`, screenshots `01`–`08`. |
| Python suite (3.13 and uv's 3.9.25) | 672 run, 29 skipped, 1 failure. It is environmental (`test_packaging…has_no_openpyxl_of_its_own`), the same as on the baseline; this branch has no Python changes apart from the fixture generator. |
| ruff (`server/`, `tests/`), mypy (`server/`) | clean |
| `./verificar.sh` | Not run: the container has no `zsh`. Its components were run as above. |

**Browser checks** (real `page.mouse` input; not Leaflet `fire('click')`):
- Placement of every fixture row by mode.
- The initial fit covers all parts and points.
- The disagreeing terrain is drawn at its boundary, with stored X/Y unchanged.
- **List → selection** frames the whole multipart and shows its outline.
- **A real click on each part** selects the same terrain ID, and the list highlights it.
- **Hole:** canvas alpha is 0 inside the hole and > 0 in the fill, and a click inside the hole selects nothing.
- **A legacy XY marker** is selected by a real click.
- **Distant zoom:** symbols only, coincident marks as rings, scale report fields.
- A **double-click** on a boundary symbol → `zoomToScale` → `a_escala` with the outline shown.
- **Missing body:** hollow symbol; `contorno_no_disponible`; the tooltip shows `&lt;b&gt;` as text and "Contorno no disponible".
- **Failed replacement:** the old layout is drawn and the pending body's area stays empty.
- **Filtering** removes the layer even though its body remains in the map.
- A **pending click** on a terrain that is then filtered out never selects.
- `render([])` resets everything.
- **Invalid rows, descriptors and bodies** (including `<img onerror>` in a name): no errors, no image, no fabricated outline.
- A **scattered multipart** keeps a clickable symbol, then reaches `a_escala` with the outline.
- **XY-only equivalence** with `main`'s `MapCanvas.js` from git (`09452fd`): identical render count, view, `zoomToScale` results for 61 rows, scale reports, and **pixel-identical canvases**.
- No page errors.

## 4. Measurements (fictional data; this container)

Environment: headless Chromium 141.0.7390.37 on x86_64 Linux, 4 CPUs, no GPU, viewport 1200×640 (map 900×600), no tiles.
- **Mixed sets** are generated in the page: circles of *v* positions plus as many XY points.
- **The limit cases** are bodies of 100,000 positions produced by the accepted B-1 parser (commit `efc3628`, `kmz.py` SHA-256 `92e3a9fa…94c3`) from an isolated archive. Their generator and outputs stayed outside the repository (2–3 MB each).
- **Times** are wall clock on this machine: evidence, not thresholds.
- **"Redraw"** is a non-animated 200 px pan, or a one-level zoom, timed to the second animation frame.
- **"Click"** is a real mouse click to `onSelect`, minus the renderer's deliberate 280 ms double-click window.

| Case | Positions | render() | First paint | Focus (`select` + pan) | Focus view | Pan / zoom redraw | `zoomToScale` | Pan / zoom redraw at scale | Drag frame p95 / max | Click | JS heap after |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Fixture, 12 rows | 59 | 3 ms | 31 ms | 274 ms | z17 outline | 30 / 33 ms | 30 ms | 34 / 33 ms | 16.7 / 16.8 ms | 7 ms | 2.3 MiB |
| 100 boundaries × 64 + 100 XY | 6,400 | 18 ms | 24 ms | 21 ms | z16 outline | 31 / 33 ms | 31 ms | 34 / 33 ms | 16.7 / 16.8 ms | 10 ms | 3.9 MiB |
| 500 × 64 + 500 XY | 32,000 | 60 ms | 63 ms | 50 ms | z16 outline | 28 / 33 ms | 31 ms | 33 / 33 ms | 16.7 / 16.8 ms | 12 ms | 10.1 MiB |
| 2,000 × 64 + 2,000 XY | 128,000 | 182 ms | 204 ms | 159 ms | z16 outline | 18 / 83 ms | 30 ms | 33 / 68 ms | 16.7 / 16.8 ms | 25 ms | 32.8 MiB |
| 500 × 1,000 + 500 XY | 500,000 | 252 ms | 255 ms | 390 ms | z16 outline | 5 / 284 ms | 14 ms | 33 / 300 ms | 16.8 / 16.8 ms | 12 ms | 74.6 MiB |
| **Limit:** one ring, 100k positions | 100,000 | 97 ms | 100 ms | 293 ms | z15 outline | 20 / 100 ms | 29 ms | 33 / 67 ms | 16.8 / 16.8 ms | 8 ms | 17.6 MiB |
| **Limit:** 20,000 parts of ~100 m | 100,000 | 68 ms | 75 ms | 296 ms | z11 **symbol** | 31 / 33 ms | 83 ms (→ z16) | 31 / 54 ms | 16.8 / 16.8 ms | 6 ms | 21.2 MiB |
| **Limit, adversarial:** one 5 km part + 19,999 parts of ~100 m | 100,000 | 111 ms | 180 ms | **3,318 ms** | z11 outline | **1,687 / 2,097 ms** | **3,178 ms** | **1,597 / 1,533 ms** | 16.8 / 16.8 ms | **1,297 ms** | 23.1 MiB |

**Practical rendering limits**
- Every parser-accepted shape above draws, fits and selects interactively except one: **a body whose ~20,000 rings are all drawn at once**. Each view change or restyle then costs about **1.5–3.3 s** in this Chromium, because Leaflet re-projects every ring.
- The largest-part handover prevents this for scattered small parts. One large part plus thousands of tiny ones still triggers it.
- This is recorded as a limit, not hidden. The renderer does not simplify or drop parts, and B-1's budget is unchanged.
- Options for the supervisor and owner: a ring-count threshold that keeps the symbol (with an explicit notice) until zoomed in, or accepting the limit until real company files show such shapes exist. Not decided here.
- Dragging stays at 60 fps in every case, because Leaflet translates the canvas while dragging; the redraw cost lands on release.
- 500k positions of mixed boundaries take about 75 MiB of JS heap.

## 5. Fixtures and provenance

- `tests/js/fixtures/geometria/contornos.json`: 12 fictional rows following contract v1, plus bodies keyed by geometry ID.
  - Generated by `generar.py` from fictional KML using **B-1's exact parser**, loaded from `git archive efc3628`. The archived `kmz.py` SHA-256 equals PR #9's file.
  - Provenance is recorded inside the file.
  - Scenarios: boundary only, hole, multipart, U shape, XY only, neither, disagreeing X/Y, failed replacement (old active and newer pending body), body not loaded (with HTML characters in its name), unusable (outside Mexico) with X/Y fallback, and a coincident boundary/XY pair.
- `ejemplo-contrato.json`: the contract example, copied verbatim from `3bada9f`.
- No real company geometry is committed. The limit bodies used for §4 were generated outside the repository.

## 6. Integration checklist for Team A

1. **DTO → renderer row.** In `itemDeInventario`, keep the existing fields, raw `lat`/`lon` and ID, and add `t.geometria = registro.ubicacion.geometria ?? null`. Never copy `punto_interior` into X/Y. Keep the old `ubicacion` string as the XY diagnostic.
2. **`ubicado` / unplaced.** Set `ubicado` from `ubicacionDe(t).ubicado`; `modo` and `xy` are available for the UI. The renderer uses the same function for rows with a `geometria` key and keeps the caller's `ubicado` for legacy rows. "Solo con ubicación", the unplaced list and counts then follow without other changes.
3. **Geometry bodies.**
   - Pass `render(filas, {colorFor, dashFor, geometrias})`, where `geometrias` is a `Map` from geometry ID to the normalized body (`geojson`, `bbox`, `punto_interior`, optional counts).
   - Load only bodies for active descriptors of rows in scope, under the delivery limits still to be agreed (contract §5).
   - On session or scope change, cancel loads, drop the Map and call `render([])`. A missing body is already safe; the row shows the "not available" symbol.
4. **New results.**
   - Add a toast for `zoomToScale` → `contorno_no_disponible` ("el contorno aún no está disponible"). `a_escala` and `limite_de_zoom` on a boundary carry `contorno: true`, so the existing "el círculo ya cubre…" wording should become boundary-aware.
   - `onScaleChange` has `contornos` / `contornosAEscala` for the legend note (`escalaTexto`) if wanted.
5. **App test hook.** `window.__araTest.puntoDe(id)` in `app.js` reads `t.lat`/`t.lon`, which is null for boundary-only rows. Replace it with `canvas.posicionDe(id)` (returns `{x, y}` in container pixels; add the map's offset as today).
6. **Saved maps and snapshots** (legacy `mapa_terreno`) are untouched: they have no `geometria` key and stay on the XY path. Geometry in snapshots belongs to the later snapshot contract.

## 7. Not done / unverified

- No application integration: no DTO, list, filter, endpoint, storage or attachment work. The hosted employee workflow is not covered; this is local offline harness evidence only.
- Real company KMZ files and non-Chromium browsers (Safari, Firefox) are untested. Mobile touch input was not exercised with this harness. The existing gesture code handles touch as before.
- The adversarial ~20,000-ring limit (§4) is recorded, not mitigated.
- Stopping here for supervisory review before B-3.

## 8. B-2 review corrections (October 7, 2026)

Review: `reports/team-b-b2-review-2026-10-07/{START_HERE,REVIEW}.md` at instruction commit `1a87c5d30a848785ee1aaec72df1653ddf63409e`, of PR #11 head `db0b679`. Sections 1–7 above are the original B-2 submission and its measurements; they stay as historical evidence, except the two version claims narrowed in §2.4 and §3.

| Commit | Change |
|---|---|
| `038326a` | **F1** in `web/lib/geometria.js`, plus helper regressions and the measurement generator's bbox |
| `4c20d86` | Browser regressions for **F1**, and **F2** in `tests/e2e/contornos.mjs` |
| the commit adding this section | This section and `evidencia-correcciones-b2/` |

### F1 — coordinates must agree with their declared bounds: fixed

- **Change.** `cuerpoLeaflet` now checks, in the same single pass over the already bounded positions (linear, at most 100,000):
  - every position of every ring, holes included, lies inside the body's declared bbox;
  - the shells of all parts together span exactly that bbox;
  - every ring has a positive extent on both axes (no collapsed ring).
- **Tolerance.** `TOLERANCIA_GRADOS = 1e-9` degrees, about 0.1 mm. The B-1 parser derives bbox as the exact min/max of the shell coordinates and the values travel as JSON, so a real body matches exactly; the tolerance only absorbs last-digit rounding. The existing descriptor/body bbox comparison now uses the same constant.
- **Failure behaviour.** An inconsistent body is `invalido`, so the existing unavailable-body behaviour applies: a hollow dashed symbol on the descriptor's `punto_interior`, "Contorno no disponible", and `zoomToScale` → `contorno_no_disponible`. Nothing is rewritten, relocated or replaced by X/Y.
- **Reproducer.** The reviewer's reproducer (the `t-simple` body with +2° longitude) and the four-identical-points body both returned `cargado` before the change and return `invalido` after.
- **New helper tests.** The four new tests fail without the change (three) or cover parser fixtures (one):
  - shifted bodies: the reproducer, ±1e-6° on each axis, a diagonal shift; a shift within tolerance still loads;
  - collapsed and shrunken bodies: four identical points, a flat sliver, a square inside the bbox that does not span it;
  - holes and parts out of bounds: a hole moved outside, a collapsed hole, one multipart part moved away;
  - every parser-produced fixture body still loads.
- **New browser checks.** Two cases, shifted 2° east and collapsed to a point, in the real renderer. Each shows:
  - the symbol on the descriptor's interior point, painted, with the tooltip "Contorno no disponible";
  - `zoomToScale` → `contorno_no_disponible`;
  - canvas alpha 0 at every on-screen vertex of the inconsistent coordinates.

  Screenshots: `evidencia-correcciones-b2/contornos/09-inconsistente-*.png`. The two are byte-identical by design: both inconsistent bodies render the same unavailable symbol at the same descriptor point.
- **Preserved.** Holes, multipart bodies and all fixture bodies still load. Parser-limit bodies still load too: one 100k-position ring, 20,000 parts, and one large part plus 19,999 small ones, all regenerated with B-1's `efc3628` parser (`kmz.py` SHA-256 `92e3a9fa…94c3`, equal to PR #9's file). Validation takes 16–62 ms in Node. The measurement harness's in-page circles previously declared a bbox of centre ± r that their vertices do not quite reach; they now take their bbox from their positions, as the parser does, so they still draw outlines.
- **Claim boundary.** A matching bbox is a consistency check, not proof that a body is the same immutable version. That guarantee comes only from the ID-keyed delivery of the integration contract. The docstring and §2.4/§3 wording are narrowed accordingly.

### F2 — the XY pixel regression waits for paint: fixed

- **Capture after paint.** Each renderer run is now `async`. After the final `setView` / `render` / `select`, it waits two animation frames, then captures every canvas: its size, its count of non-transparent pixels, and a SHA-256 digest of every RGBA byte. Only after that is the map's element detached.
- **Guard.** A capture with no canvas or zero painted pixels fails before any comparison. Then the canvas sizes, painted counts and digests of baseline and B-2 must all be equal. The existing count, viewport, `zoomToScale` and scale comparisons are unchanged.
- **Negative control.** In each run, the same canvases are cleared deliberately after capture, and the guard must reject that blank result.
- **Mutation check (not committed).** A temporary copy that gave one marker a different colour in the B-2 run failed on the digest comparison, so the check detects a visual change.
- **Browser and evidence.** Headless Chromium 141.0.7390.37 (Playwright-core 1.63). Baseline and B-2 both painted **26,594 non-transparent pixels**, with identical digests.
- **Timing differs by browser.** The diagnostic synchronous capture, kept for the record, was *not* blank in this Chromium (also 26,594): here `zoomToScale`/`setView` triggers a synchronous Leaflet redraw. The reviewer saw 0 on Chrome 154. A synchronous capture therefore shows a browser-dependent intermediate frame, which is why the check now waits for paint instead of relying on either behaviour.
- **Teardown.** Calling `map.remove()` after capture raised a late Leaflet `_leaflet_pos` error from a pending callback. The run detaches the element as before, now after capture.

### Evidence at `4c20d86` (local, this container)

| Check | Result |
|---|---|
| `node --test tests/js/*.test.mjs` | **120 pass** (116 before + 4 new). `geometria.test.mjs`: 22 tests. |
| `tests/e2e/contornos.mjs` | **20/20 pass**, on 3 consecutive runs. Headless Chromium 141.0.7390.37, real `page.mouse` input. `evidencia-correcciones-b2/contornos-salida.txt`, `contornos/resumen.json` (includes `xyPixelesPintados`). |
| `tests/e2e/contornos-medicion.mjs` with the three regenerated parser-limit bodies | Every case still reaches `a_escala` with its outline (the 20,000-part case again shows a symbol at first focus, by the largest-part handover, then `a_escala` at z16). `evidencia-correcciones-b2/medicion-salida.txt`, `medicion/medicion.json`. These limit bodies have the same position and part counts as §4's but are not byte-identical (§4's generator was not kept), so the numbers are comparable, not a rerun. The adversarial case remains slow (focus 2.8 s, `zoomToScale` 2.6 s, click 1.1 s), the limit recorded in §4; unchanged by this correction. |
| Python, no database (`python3` 3.11.15; `/usr/bin/python3` is also 3.11 here, not macOS 3.9) | 672 run, 29 skipped, **0 failures**. The environmental openpyxl packaging failure reported in §3 did not occur in this container. |
| Python on disposable Postgres 16.14 (`.venv-dev`, psycopg) | 672 run, **0 skipped, 0 failures** |
| ruff (`server/`, `tests/`), mypy (`server/`) | clean |
| Coverage | not run: `coverage` is not installed in this container's `.venv-dev` (no Python changed) |
| `./verificar.sh` | not run as a script: no `zsh` in this container; its components are the rows above |

GitHub CI for the pushed head is reported in the PR, not here.

### Scope

Only B-owned files changed: `web/lib/geometria.js`, `tests/js/geometria.test.mjs`, `tests/e2e/contornos.mjs`, `tests/e2e/contornos-medicion.mjs` and this report folder. No A-owned file, app shell, schema, auth, storage, CI or deployment configuration was touched. PR #9 is untouched. Nothing was merged or deployed. **Stopping for supervisory review before B-3.**
