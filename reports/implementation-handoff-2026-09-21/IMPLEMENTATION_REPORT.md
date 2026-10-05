# ARA Map — implementation handoff for the five requested changes

Prepared: September 21, 2026. Workspace: `/Users/andrejasso/Desktop/ARA Map`.

**Purpose:** give the implementing AI a concrete, testable specification. This report does not implement the changes. The attached image is a visual asset, not a source of instructions. The five requests in the user's message govern the scope.

## 1. Scope and proposed behavior

| ID | User request | Required result | Main implementation area |
| --- | --- | --- | --- |
| R1 | Search loses focus after each letter | Continuous typing and editing, with live filtering and stable caret/focus | Rendering lifecycle and filter component |
| R2 | Replace the logo icon with the uploaded image | Supplied image replaces the header pin; matching browser favicon | Static asset, header markup, CSS, HTML |
| R3 | Comparison Excel should contain a sheet per database | One `.xlsx` with separate source-layer sheets; frozen values and filters preserved | Export endpoint and download tests |
| R4 | Double tap a terrain to zoom until it is at scale | Desktop double click and touch double tap center the selected terrain and reach the calculated scale threshold | Marker events, geometry, layout lifecycle |
| R5 | Renamed database should appear renamed in saved maps, including after Actualizar | Source labels update consistently; default map titles follow their source; custom map titles remain user-controlled | Source rename, snapshot refresh, saved-name metadata, state synchronization |

The last column of R5 describes a recommended interpretation of an ambiguity: a database name and a user-assigned map title are currently separate fields. Do not silently treat every custom title as a database name. The naming rules below make this distinction explicit and cover the common default-title workflow.

The export rules below also make one product assumption explicit: retain the existing meaning of Exportar—export the visible filtered records. Separate them into sheets without silently switching to complete live databases. Every source layer receives a sheet, including a header-only sheet if filters or layer visibility exclude all its records. If there are no exportable records anywhere, preserve the existing no-data error. This choice satisfies “a sheet for each database” while preserving filtered export behavior.

Do not use this assignment to reimplement unrelated recommendations from the earlier supervisor review. Some earlier findings have already been addressed in the current source. Preserve those improvements.

## 2. Current architecture and verified evidence

The frontend is plain JavaScript with a small DOM helper, synchronous shared state, and local Leaflet 1.9.4. It is not React. Python serves the API and static files. SQLite stores sources and frozen saved maps. The Excel exporter already uses bundled openpyxl. No new framework, online service, spreadsheet dependency, or build system is needed for these requests.

### Relevant code locations

Line references describe the inspected version. Locate by function name again if another associate changes the files.

| File and anchor | Why it matters |
| --- | --- |
| [app.js:45](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:45>) — `mount`, subscriber | Rebuilds header and current view on every state change |
| [app.js:203](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:203>) — `renderMapa` | Replaces workspace, filters, and detail layout |
| [FilterRail.js:24](</Users/andrejasso/Desktop/ARA Map/web/components/terrain/FilterRail.js:24>) | Search input dispatches on every input event; numeric controls do too |
| [store.js:30](</Users/andrejasso/Desktop/ARA Map/web/lib/store.js:30>) | `setState` synchronously invokes subscribers |
| [dom.js:46](</Users/andrejasso/Desktop/ARA Map/web/lib/dom.js:46>) — `clear` | Uses `replaceChildren`, destroying focused descendants |
| [app.js:88](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:88>) — `renderHeader` | Creates the CSS pin icon |
| [global.css:69](</Users/andrejasso/Desktop/ARA Map/web/styles/global.css:69>) | `.brand-mark` and its `::after` draw the old pin |
| [index.html:10](</Users/andrejasso/Desktop/ARA Map/web/index.html:10>) | Inline SVG favicon is also the old pin |
| [app.js:619](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:619>) — `exportar` | Sends filtered row IDs and saved-map ID |
| [api.js:59](</Users/andrejasso/Desktop/ARA Map/web/lib/api.js:59>) — `exportXlsx` | Downloads one binary Excel response |
| [exportar.py:39](</Users/andrejasso/Desktop/ARA Map/server/api/exportar.py:39>) | Builds a single sheet for all exported rows |
| [MapCanvas.js:22](</Users/andrejasso/Desktop/ARA Map/web/components/map/MapCanvas.js:22>) | Map lifecycle, click binding, marker rebuild, zoom limits |
| [geo.js:44](</Users/andrejasso/Desktop/ARA Map/web/lib/geo.js:44>) — `trueScaleZoom` | Existing calculation for when the circle represents ground area |
| [Legend.js:55](</Users/andrejasso/Desktop/ARA Map/web/components/map/Legend.js:55>) — `escalaTexto` | Existing truthful scale wording |
| [bases.py:46](</Users/andrejasso/Desktop/ARA Map/server/repo/bases.py:46>) — `rename` | Changes only `base.nombre` |
| [mapas.py:77](</Users/andrejasso/Desktop/ARA Map/server/repo/mapas.py:77>) — `refresh_snapshot` | Refreshes rows but omits stored source-name update |
| [mapas.py:211](</Users/andrejasso/Desktop/ARA Map/server/repo/mapas.py:211>) — `_label_versions` | Builds distinct names for historical layers sharing a source |
| [app.js:488](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:488>) — `actualizarMapa` | Refreshes saved-map listing and reopens the refreshed map |
| [app.js:513](</Users/andrejasso/Desktop/ARA Map/web/components/app.js:513>) — `afterBaseChange` | Reloads bases but not the active saved map or map listing |
| [db.py:139](</Users/andrejasso/Desktop/ARA Map/server/db.py:139>) | Connections use autocommit; `session` is not a transaction |

### What was reproduced for this report

All exploratory imports, renames, and refreshes ran on a disposable database and server at port 8441, not on `datos/ara_map.db`.

| Check | Observed result |
| --- | --- |
| Focus search once and type `Paseo` with keyboard events | Input value became `P`; `document.activeElement.tagName` became `BODY` |
| Rename source `Prueba 08` to `Base Renombrada`, then refresh its saved comparison | Saved layer still returned `Prueba 08` |
| Export comparison of the generated August/September fixtures | One sheet, `Registro Análisis`, containing all 25 data rows |
| Double click `Paseo del Roble` from zoom 7 | Detail opened, zoom reached only 8; terrain requires zoom 14 to reach its single-marker scale threshold |
| Uploaded asset inspection | PNG, 522 × 478 pixels, alpha channel present |
| Existing Python tests | 236 tests passed in this run |
| Existing JavaScript tests | 46 tests passed in this run |

The Python run emitted resource-cleanup warnings from HTTP-error tests, but no failed tests. The complete existing browser smoke suite was not rerun for this report; browser verification was targeted at the reported behavior. Its local `tests/e2e/node_modules` was absent. A diagnostic browser probe used the installed bundled Playwright runtime instead. This is a verification-environment detail, not an application runtime dependency.

### Existing test blind spots

- Search smoke coverage uses `box.fill('marcenas')`. That assigns the whole value at once and checks a result count. It does not establish that sequential keystrokes keep focus.
- Existing geometry tests check scale arithmetic; the smoke test repeatedly clicks the map's zoom button. Neither verifies a double-click gesture on a terrain.
- Existing export tests mostly check a live base, row count, and ID filtering. They do not specify source-per-sheet comparison output.
- Snapshot tests cover changes to source rows and deletion. They do not test source rename propagation into stored layer names and map titles.

## 3. R1 — preserve focus and caret in the map search

### Root cause

The current sequence is:

```text
#buscar input event
  → FilterRail.onChange({ busqueda: value })
  → setFilter
  → synchronous setState subscribers
  → renderView → renderMapa
  → clear(main).append(new workspace)
  → old input is disconnected; a new, unfocused input replaces it
```

The same issue affects numeric filter inputs. `mapHost` preserves a DOM object, but moving it into a newly built stage does not preserve the other controls and still detaches/moves the map's surrounding layout. Calling `setState({})` also invokes the entire render cycle.

### Recommended implementation

1. Give the map workspace a create/update/dispose lifecycle. Mount its shell once when entering the map section. Keep the filter form, search input, numeric inputs, stage, and map host attached while the section is active.
2. Refactor the filter component into a persistent view, for example `createFilterRail(...)` returning `{ element, update, destroy }`. This is a suggested interface, not an existing API. `update` patches values, result counts, option groups, and active states rather than replacing the entire form.
3. Retain the same `#buscar` node while typing. Do not overwrite its `.value` if it already equals state. Preserve the current selection range, selection direction, focus, and horizontal scroll inside the text field.
4. Update state and derived results for every committed edit. The map, table, unplaced list, and result count must continue to consume the same filter state.
5. Do not rebuild the header for a filter edit. Render navigation only when section state changes. Do not repaint or recreate terrain markers for unrelated state changes such as selecting a terrain or opening its details.
6. Give numeric controls stable names/IDs such as `superficie-min`, `precio-max`, and `unitario-min`. Keep editing text local while focused where necessary so partial input such as `1.` or a decimal separator is not replaced mid-edit by normalized state. Convert to the existing numeric/null filter model using a documented commit policy.
7. Handle `compositionstart` / `compositionend` so accented/composed input is not interrupted. Either filter safely during composition while retaining the input node, or apply the composed value once on completion. Do not reconstruct the input during composition.
8. Make async render work read the latest state. If `requestAnimationFrame` callbacks are coalesced, retain and cancel the previous scheduled callback; do not draw a series of stale states after rapid input or navigation.
9. Explicitly clear preserved inputs when the user presses Limpiar or opens a different base/map. Persistence must not retain another map's search text over its saved filters.
10. Unsubscribe and cancel pending callbacks/timers when disposing a view. Repeated navigation must not accumulate input handlers or recreate multiple Leaflet maps.

The DOM helper currently uses attributes for most values. During updates, use DOM properties such as `input.value` and `input.checked`; updating their original attributes alone is insufficient for an already edited control.

### Smaller fallback, if a persistent view is not feasible

Capture the active filter's stable identity, text selection, and relevant scroll position before replacing the view, then restore them to the corresponding new control after rendering with `focus({ preventScroll: true })`. Only restore focus if that exact control had it and the user is still in the same view. Text selection restoration must be restricted to input types that support it—number inputs do not support `setSelectionRange`.

This fallback is less robust for composition, mobile keyboards, and double-click behavior. It is acceptable only if the complete typing acceptance tests pass. Merely adding autofocus, globally refocusing search on every update, changing `input` to `change`, or adding a debounce is not a complete fix.

### Acceptance tests

| ID | Test | Expected result |
| --- | --- | --- |
| R1.1 | Click search once; type `Paseo` one character at a time | Complete value remains `Paseo`; search remains the active element after each character |
| R1.2 | Type rapidly, then slowly; include spaces and accents | No lost characters, unexpected focus changes, or stale result count |
| R1.3 | Move caret into the middle; insert text, select a substring, Backspace/Delete | Correct edit and caret position preserved |
| R1.4 | Paste text; undo/redo; use the search field's clear control | Value and all filtered views agree |
| R1.5 | Enter a query with no results, then erase it | Search stays usable and complete results return |
| R1.6 | Type while a terrain detail is open and in a saved comparison | Same behavior; no focus theft from a rerender |
| R1.7 | Enter several digits and a decimal in numeric filters | Continuous editing works, including zero versus empty |
| R1.8 | Press Tab, open a dialog, or select another control | Search does not steal focus back |
| R1.9 | Change map/base, reset filters, or restore a saved view | Preserved controls reflect the newly authoritative filter state |
| R1.10 | Navigate away and back repeatedly | One handler per action; map keeps working; no orphaned timers |

Use actual keystrokes in Playwright (`pressSequentially` or `page.keyboard.type` after one focus). Do not use `fill` as the only regression test. Assert `toBeFocused()` as well as results.

## 4. R2 — use the supplied logo asset

### Asset identity

- Original: `/Users/andrejasso/Downloads/Screenshot_2026-09-21_at_5.07.00_p.m.-removebg-preview.png`.
- A byte-identical handoff copy is included next to this report as `provided-logo.png`.
- Format: PNG with alpha, 522 × 478 pixels.
- SHA-256: `11eeaee78424d706aa7cddf1956d174f32ef0550a7c044e31583dcd1e6f71159`.
- Appearance: overlapping blue and pale-blue diamond forms. Use this asset as supplied. No image generation, tracing, recoloring, or replacement artwork is required.

### Implementation steps

1. Copy the original or handoff asset into the distributable static tree, suggested destination `web/assets/ara-logo.png`. Do not reference Downloads, a local absolute filesystem path, or a `file://` URL from HTML.
2. Replace the `span.brand-mark` in `renderHeader` with an image whose source is `/assets/ara-logo.png`. Keep the adjacent ARA Map name.
3. Use a dedicated `.brand-logo` style and remove the obsolete pin styling/pseudo-element if unused. Do not apply the old circular border or stem to the image.
4. Suggested header size: height 32 CSS pixels and width proportional to 522:478. Use `object-fit: contain`, `display: block`, and `flex-shrink: 0`. Set intrinsic width/height attributes to avoid layout shifts. Keep the current header height unless inspection proves a small adjustment necessary.
5. With the visible text ARA Map immediately adjacent, use an empty `alt` for the decorative image to avoid reading the brand twice. If later used without visible text, give that instance an appropriate accessible label.
6. Replace the old inline pin favicon in `web/index.html` with the same PNG asset and an appropriate PNG MIME type. This is the recommended consistent scope for “logo icon.” Do not advertise unsupported icon dimensions or change the macOS launcher icon as an unrelated task.
7. Check the original's transparent edges on the light header. Preserve its aspect ratio and visible design; do not stretch it into a square or crop off the tips. A derived small favicon is optional only if the supplied PNG proves unreadable in an actual browser tab.
8. Confirm the asset is included when the app folder is copied to another Mac, and is served by the existing static-file handler. No CDN dependency is needed.

### Acceptance tests

- Header displays the supplied design at standard and high-DPI zoom, with no old pin or pseudo-element remaining.
- Image decodes successfully (`complete`, nonzero natural width/height) and its request returns PNG bytes, not the single-page HTML fallback.
- No distortion, clipping, black rectangle, navigation overlap, or header-height jump at the current desktop and narrower supported layouts.
- Logo remains correct across Bases, Mapa, Mapas guardados, and dialog interactions.
- Browser favicon uses the new design after a fresh load/cache refresh.
- A copied app folder resolves the logo without relying on the original Downloads file.

## 5. R3 — export comparison sources into separate Excel sheets

### Current behavior and constraints

`app.js::exportar` derives `filtrados` from visible layers plus active filters, then sends saved snapshot row IDs. The server correctly reads saved maps from `mapa_terreno`. It currently flattens those rows into one `Registro Análisis` sheet and adds a Base column.

Preserve the snapshot source of truth. Replacing this lookup with `repo_terrenos.for_base(...)` would export current source data instead of what the saved map shows, and would fail for deleted sources.

There can now be different historical layers sharing one `base_id`. Therefore the reliable export group is the saved **layer**, identified within a map by `orden` / `capa_orden`, not its display name or source ID. For a normal comparison, one layer equals one database. For historical comparisons, each represented version needs its own sheet to avoid mixing it back together.

### Output contract

| Situation | Required workbook behavior |
| --- | --- |
| Live base export | Keep one sheet named `Registro Análisis` |
| Saved simple map export | Keep one `Registro Análisis` sheet containing its frozen rows |
| Saved comparison | One sheet for each represented layer, in stored layer order |
| Comparison with one remaining/represented layer | Still use comparison sheet naming; branch by map type rather than only `len(capas) > 1` |
| Same source represented at different times | Separate sheets per layer/version, even when `base_id` matches |
| Deleted source | Export its frozen layer and retained label normally |
| Filtered or hidden layer | Header-only sheet for that layer; no excluded records leak into the export |
| No selected rows anywhere | Existing clear error; no misleading empty download |
| API request omits `ids` | Preserve current API behavior: all rows of the requested object |
| API sends `ids: []` | Explicit empty selection, not an instruction to export everything |

Use the existing 13-column `COLUMNS` order on each per-source sheet: ID, Terreno, Estado, Municipio, Dirección, Superficie m2, Superficie Ha, Afectaciones %, Afectaciones m2, Asking Price, Asking $/m2, X, Y. Keep X = latitude and Y = longitude. A redundant Base column is unnecessary once each sheet belongs to one layer; do not add a combined sheet unless requested later.

Preserve the existing exported ID meaning (`orden`). Do not swap it for an internal database ID while restructuring output. Keep numeric cells numeric, null values blank, percentage fractions as fractions, and the existing numeric formats.

### Implementation sequence

1. Keep `POST /api/exportar` and its binary response. No frontend XLSX library is required.
2. Resolve map metadata and snapshot rows using the current repository. Validate the map exists before exporting.
3. Apply the requested row-ID filter within those rows. IDs are snapshot row IDs, not source terrain IDs. Retain membership validation through the scoped lookup; an ID from another map must never export its row.
4. For a comparison, initialize one group per `mapa.capas` entry keyed by `orden`, then append each selected row using its `capa` or `capa_orden`. Initializing groups before appending preserves empty sheets and layer order.
5. Extract the common sheet-writing code into a small helper, e.g. `write_terrain_sheet(book, title, rows)`. Reuse it for simple and comparison exports.
6. In the comparison path, remove/reuse openpyxl's default sheet so the result contains exactly the intended sheets, with no extra Sheet or blank Registro Análisis tab.
7. Format each sheet: header in row 1, terrain data beginning row 2, freeze at A2, practical widths, and optionally an autofilter over the occupied range. Do not insert a report title above the header—the importer expects headers in the first row.
8. Save once to the response buffer after writing every sheet. Keep the Excel MIME type and existing download filename behavior.
9. If showing an enhanced toast such as “25 terrenos en 2 hojas,” derive both counts from the actual chosen contract. A frontend count of nonempty groups would be wrong when the workbook deliberately includes empty source sheets.

Suggested algorithm, not a ready-to-paste replacement:

```python
snapshot_rows = repo_mapas.terrenos(conn, mapa_id)
selected_rows = filter_requested_snapshot_ids(snapshot_rows, ids)
if not selected_rows:
    raise ApiError(existing_no_rows_message)

if mapa['tipo'] == 'comparacion':
    groups = {layer['orden']: [] for layer in mapa['capas']}
    for row in selected_rows:
        groups[row['capa']].append(row)
    for layer in mapa['capas']:
        title = unique_excel_sheet_name(layer['nombre'], used_names)
        write_terrain_sheet(book, title, groups[layer['orden']])
else:
    write_terrain_sheet(book, 'Registro Análisis', selected_rows)
```

### Worksheet-name handling

Names are user-editable. Do not send them directly to `sheet.title` and rely on library warnings or automatic renaming.

- Replace Excel's forbidden worksheet characters `: \\ / ? * [ ]` with a readable separator.
- Remove XML-illegal control characters, trim surrounding whitespace, and avoid leading/trailing apostrophes.
- Limit each final title to 31 characters, including any collision suffix. Reserve suffix space before truncating.
- Compare candidate names case-insensitively. `Norte`, `norte`, and names that collide after sanitization/truncation must get deterministic distinct titles such as `Norte`, `norte (2)`.
- If the cleaned name is empty, use a deterministic fallback such as `Base 1` or `Capa 1`.
- Treat reserved/problematic titles such as `History` conservatively by prefixing a safe label.
- Never mutate the stored database/layer name just to fit Excel. If the full name is important, preserve it in an ordinary cell outside the import table or workbook metadata; do not add a second header row or unrelated columns to the terrain table merely for decoration.
- Write user-controlled text fields as literal text, including names/addresses beginning with `=`. Preserve numeric fields as numbers. This should not introduce interpreted formulas while reorganizing the writer.

### Reimport limitation to document

The current importer selects `Registro Análisis` if present, otherwise the first worksheet. It does not offer a sheet selector or import every worksheet. Therefore a multi-sheet comparison export is suitable for inspection, but importing it as-is will not recreate all its databases. Document that limitation and explain how to save an individual sheet as a standalone workbook. A multi-sheet importer is a separate feature, not part of these five changes.

### Acceptance tests

1. Export the two fictitious fixtures without filters: workbook has exactly two sheets, with 12 and 13 terrain rows respectively, plus one header row per sheet.
2. Verify each sheet's terrain names, prices, coordinates, and order against its originating frozen layer, not only its total count.
3. Select a subset spanning two layers: only those exact snapshot rows appear, in the correct sheets.
4. Hide one layer: its sheet is header-only, and its rows appear nowhere else. Repeat when filters remove one layer's results.
5. Repeat with three or more layers, repeated source IDs, repeated source names, and a deleted source.
6. Change a live source after saving: export continues to contain saved values until the explicit refresh workflow updates the snapshot.
7. Test invalid characters, long names, case collisions, empty sanitized names, accents, and collision suffixes that would otherwise exceed 31 characters.
8. Assert the 13 header labels, A2 frozen panes, numeric cell types and formats, blank coordinate cells, and absence of an accidental default sheet.
9. Keep the existing live-base and saved-simple export tests passing.
10. Through the browser, click Exportar, wait for the download event, and inspect the downloaded file. An API-only workbook check does not verify the download flow.

## 6. R4 — double activation zooms a terrain to scale

### Meaning of “at scale” in this application

The data contains a point and an area, not surveyed boundaries. Preserve the existing area-equivalent circle. At distant zooms, its displayed radius is the larger of a fixed symbol radius and the projected physical radius. “At scale” means the physical radius has reached or exceeded that symbol radius, so the displayed circle represents the registered area.

Do not satisfy the request by multiplying the visible marker size independently of map zoom. Do not replace the circle with an invented property polygon or remove the existing shape-approximation explanation.

### Existing calculation to reuse

`geo.js` already contains `groundRadius`, `metresPerPixel`, `trueScaleRadius`, `trueScaleZoom`, and `markRadius`.

```text
groundRadius = sqrt(area_m2 / π)
metresPerPixel = 156543.03392804097 × cos(latitude) / 2^zoom
physicalRadiusPx = groundRadius / metresPerPixel
symbolicRadius = SYMBOL_RADIUS + coincidentRingOffset
scaleThreshold = ceil(log2(symbolicRadius × 156543.03392804097
                          × cos(latitude) / groundRadius))
```

Latitude in the cosine is in radians. The implementation already performs that conversion. Do not create a second inconsistent formula in the event handler.

At latitude 20.7042, the existing helper returns these thresholds:

| Area | Single symbol, radius 7 px | Coincident symbol, radius 28 px |
| --- | --- | --- |
| 10,000 m² | zoom 15 | zoom 17 |
| 48,000 m² | zoom 14 | zoom 16 |
| 1 m² | zoom 21 | zoom 23 |

The last example exceeds the current map maximum of 20. The UI must distinguish reaching the limit from actually reaching scale.

### Why adding one dblclick listener is insufficient

- Markers currently bind only `click` at `MapCanvas.js:113`.
- `selectTerreno` updates shared state synchronously.
- `renderMapa` rebuilds layout, potentially opening a detail column and moving/resizing the map.
- `MapCanvas.render` clears every marker and recreates it.
- A native double click includes earlier click events. Its second event can encounter changed geometry or a different marker instance.
- Leaflet also has ordinary background double-click zoom. The targeted browser test reached zoom 8 from 7, instead of the required 14.

R1's stable rendering work should therefore be implemented before this feature. Preserve both the canvas host's attachment and the relevant marker instances across selection updates; preserving only the outer JavaScript variable is not enough.

### Recommended interaction design

1. Expose a controller action such as `zoomToTerrainScale(id)` on the map wrapper. It should look up the latest currently rendered marker entry and return a structured outcome, such as reached scale, missing area, missing location, or limited by maximum zoom.
2. Reuse the selected entry's actual `symbolic` radius. For a comparison marker this includes its coincident-ring offset. A hardcoded radius of 7 would under-zoom some comparison layers.
3. Compute the target using `trueScaleZoom`; validate finite positive area and valid coordinates before the calculation. Guard a null, NaN, or infinite result before calling Leaflet.
4. Set the requested zoom to at least the current zoom and the calculated threshold, then clamp to the effective map min/max. Repeated double activation should not zoom out or increment arbitrarily once already at scale.
5. Center on the selected terrain's coordinates. Complete any detail-panel layout/invalidation before calculating the final viewport position, so the newly opened panel does not push the target off-center or behind itself.
6. Call `map.stop()` when appropriate to prevent prior animation from fighting the new movement; use `setView` or an existing appropriate animated method. Respect `prefers-reduced-motion`.
7. Let existing zoom-end resizing and legend updates apply the actual radius/style. Check the selected terrain's `markRadius(...).aEscala` at the final effective zoom; do not falsely set the legend to “all at scale” when other terrains remain symbolic.
8. On desktop, handle a marker's double-click event as the scale action and prevent the same gesture from applying an extra ordinary map zoom. Keep ordinary double-click zoom on empty map background.
9. Coordinate single and double activation. One bounded approach is to show immediate marker selection feedback but delay the layout-changing detail update for a short documented double-activation window, then cancel that pending single action if a valid double activation arrives. The timeout is an interaction choice, not a geometry constant. Make it configurable in one place and test both sides of its boundary.
10. For touch, verify what the bundled Leaflet/browser combination actually emits. Reuse a reliable synthesized double-click if it exists; otherwise implement one shared gesture recognizer that accepts two taps on the same terrain within bounded time and distance. Avoid firing both custom touch handling and synthetic mouse double-click handling for the same gesture.
11. Cancel pending actions on drag, pinch, pointer cancellation, navigation, or a different target. Two taps on different overlapping terrains must not zoom an unrelated ID. Clean up listeners and timers with the map view.
12. Keep single-click detail access. An accessible `Ver a escala` action in the detail panel is a useful small companion to the gesture and should call the same controller method. It can be added if needed for keyboard/mobile discoverability; it does not replace the requested double activation.

A fixed zoom of 13, 16, or 18 is not sufficient: the required zoom depends on area, latitude, and comparison offsets. `select(id, { pan: true })` currently ensures only a minimum zoom of 13 and must not be mistaken for this new action.

### Basemap zoom interaction

The map permits zoom 20, but the tile layers currently set both `maxZoom` and `maxNativeZoom` to the source limit: 16 for Claro, 19 for Satélite/Calles. Reaching a smaller terrain's scale can therefore zoom beyond the layer's display limit and leave its tiles absent.

To support the existing map maximum, keep each service's native limit as `maxNativeZoom` and allow tile display up to the map's max zoom where Leaflet overzoom works correctly. This enlarges available imagery without requesting nonexistent higher native tile levels. Do not imply that it creates additional imagery detail. Verify the loaded tiles remain visible on each basemap at the requested target.

Do not remove the map maximum or request arbitrary zoom levels to force tiny records to become physical circles. If scale remains unreachable, stop at the maximum and use a specific message such as “Este terreno necesita más acercamiento del disponible para verse a escala.” Preserve the truthful legend.

### Acceptance tests

| ID | Scenario | Expected result |
| --- | --- | --- |
| R4.1 | Double click 48,000 m² terrain at latitude 20.7042 from zoom 7 | Target centered; final zoom at least 14; selected circle actually at scale |
| R4.2 | Same area in a comparison with a larger coincident symbol | Target calculated using that marker's offset; no under-zoom |
| R4.3 | Already closer than threshold | No zoom-out or needless additional zoom; target still centered |
| R4.4 | Missing, zero, negative, or nonfinite area | No invalid Leaflet call; specific fallback explaining missing/invalid area |
| R4.5 | Missing or invalid coordinates | No attempted map centering on invalid data |
| R4.6 | Area requiring zoom above maximum | Bounded zoom; limitation reported; no false at-scale claim |
| R4.7 | First click would open detail panel | Second activation still selects the intended terrain and final centering uses the final layout |
| R4.8 | Different tap timings, overlapping markers, rapid repeated gestures | At most one scale action per gesture; correct marker ID; no delayed action later undoing it |
| R4.9 | Empty background double click; drag; pinch | Existing map navigation works; no accidental terrain-scale action |
| R4.10 | Claro, Satélite, Calles at target and maximum zoom | Tiles remain displayed, no unsupported native zoom requests |
| R4.11 | Reduced-motion preference and keyboard alternative | No unwanted animation; same final scale outcome |
| R4.12 | Touch browser double tap | Same result as desktop double click, without duplicate synthetic activation |

Test real pointer input against canvas-rendered markers. The app uses `preferCanvas: true`; do not write a test that assumes each terrain is an SVG path. Obtain target positions from the map instance via a test-only hook, then use real mouse/touch coordinates. Directly calling the controller or `marker.fire('dblclick')` is useful for a unit test but cannot prove that actual first-click layout changes preserve the gesture. If using a test hook, gate it to tests or intercept initialization in the test harness; do not expose an unnecessary production global.

## 7. R5 — propagate database names into saved maps

### Three currently distinct names

| Field | Role | Current source of display |
| --- | --- | --- |
| `base.nombre` | Current imported database name | Bases gallery and live-base toolbar |
| `mapa_capa.base_nombre` | Stored source/layer label | Saved-map chips, legend, terrain source label, comparison table, current export Base column |
| `mapa.nombre` | Saved map title, independently editable | Saved-map gallery title, map toolbar, download filename |

`bases.rename` changes only the first field. `_write_capas` copies a source name when creating a map, but `refresh_snapshot` never recopies it. `_shape` and `terrenos` return the retained layer label. Consequently reopening the map after a refresh cannot fix the missing database update.

There is also frontend staleness: `afterBaseChange` reloads only bases, and only reopens an active live base. Existing `mapas` and `mapaActivo` can remain stale in memory after a source rename.

### Recommended naming contract

- Treat a source rename as a metadata correction. Update the source labels of every saved layer still linked to that exact `base_id` when renaming the database. Do not change frozen terrain values just to rename their source.
- Also synchronize source names during Actualizar, so old saved maps with stale labels recover when refreshed.
- For simple maps whose title follows the database by default, update the title when the database is renamed. Persist this follow-name choice explicitly.
- For a custom simple-map title such as “Opciones para cliente López,” retain that title. Its source label still changes to the renamed database.
- Preserve custom comparison titles. Update the constituent source labels; do not perform string substitution inside an arbitrary title containing “vs.”
- A layer whose `base_id` has been detached because its source was deleted retains its last known source name and data. Never reconnect it using a text match.
- Name-only synchronization does not change the snapshot's data-refresh timestamp. Keep `actualizado_en` meaningful as the last data refresh unless a separate metadata timestamp is introduced.

### Implementation sequence

1. Add an explicit persistent title mode for new simple maps, for example a top-level `nombre_sigue_base` boolean/SQLite flag. Default new simple maps saved with the source name to follow it, and let a clearly custom name disable the flag. An explicit rename of a saved map should turn automatic following off unless the user deliberately chooses to follow again.
2. Keep that flag separate from viewport `config_json`. `guardarVista` currently replaces the whole config object, so a naming flag hidden inside it would be lost unless all such callers and merge rules were changed.
3. For existing simple maps, use a conservative one-time migration heuristic: infer following only when there is exactly one source layer and the map title equals its original stored source label. Otherwise preserve the title as custom. This cannot recover all historical user intent; record that limitation instead of repeatedly guessing on every rename. If both source and map have independently changed names, preserve the explicit map title.
4. Extend create/update validation and shaping to persist and return the flag. Validate it as a boolean. Preserve existing clients by defining a safe behavior when the field is omitted. In the save dialog, compute/send the desired mode deliberately; merely a default-filled textbox does not persist intent.
5. In source rename, identify dependent layers by `base_id`, never by name. Capture required old labels/title modes before changing anything. Update `base.nombre`, raw source names on dependent layers, and following simple-map titles atomically. Do not rebuild snapshots or write terrain rows in this operation.
6. In `refresh_snapshot`, fetch `SELECT nombre FROM base WHERE id = ?` instead of only an existence probe. For a live source, synchronize its stored raw name before/alongside copying its rows. Preserve orphaned layers and their names.
7. Preserve the data/provenance protections already in schema version 3: non-reusable source IDs and detachment of deleted sources. Do not remove those protections while adding a migration.
8. Refresh UI metadata after source rename: reload the map gallery, update the active source/map header, layer names, and each in-memory terrain's source label. Do not refresh terrain snapshots as a side effect of metadata reload.
9. Avoid an unconditional `openMapa` to fix metadata-only UI state if it would reset unsaved filters, selection, zoom, visible layers, or basemap. Patch the relevant names in current state, or reload metadata and merge it into the current view. Recompute comparison descriptions that incorporate layer names if applicable.
10. After explicit Actualizar, the existing `actualizarMapa` flow can use the returned refreshed metadata and reload rows. Verify all labels reflect the new names and the gallery/download filename follow the title rule.
11. Persist the result and verify after restarting/reconnecting, not just in the current browser state.

### Preserve historical version labels

Current merge code may store a combined string such as `Base Norte · Mapa Agosto` in `mapa_capa.base_nombre`. Blindly replacing that entire string with `Base Norte Nueva` can erase the distinction between two historical layers from the same base.

Normalize raw source naming and version labels before updating combined labels:

- Store a raw source name separately from optional version/provenance text; an additive `version_etiqueta` field on `mapa_capa` is one possible design.
- For newly merged layers, persist structured version information from the merge plan (`mapa_nombre`, source layer order, and available timestamp) instead of encoding all meaning only in a concatenated name.
- Expose a derived display label containing the current raw source name plus a stable version qualifier when needed. Keep the existing API display-name fields compatible, or update all consumers together.
- For legacy combined labels, do not split arbitrary user names at ` · ` and assume the suffix is authoritative. Preserve the old display text as opaque legacy provenance when ambiguity exists, with a deterministic version qualifier. Do not discard the only stored version label.
- On rename/refresh, update the raw source-name component only. On export, group by layer order and pass its distinct display label through Excel-name sanitization.
- Do not deduplicate historical layers merely because their updated labels now match. This assignment concerns names; merge identity remains content/version-aware.

This normalization may require a schema migration beyond version 3. Make it additive and idempotent, preserve row IDs, and exercise it on a disposable copy containing simple maps, comparisons, repeated-source versions, and orphaned layers. Avoid running any migration against the production database until the implementation and migration tests are ready.

### Transaction requirement

`db.connect` uses `isolation_level=None`, and `db.session` only opens/closes a connection. It does **not** atomically wrap a multi-statement rename or refresh.

Use an explicit transaction or a savepoint around coupled changes so a failure cannot leave updated names with partially deleted/reinserted snapshot rows. Prefer a reusable savepoint helper if repository functions can be called inside a caller's transaction. Do not nest `BEGIN` blindly. Roll back on failure and keep the prior names, rows, filters/configuration, and timestamp intact.

The existing refresh API already calls `db.backup()`. Preserve this behavior and decide transaction ownership once; avoid unrelated backup-directory changes.

### Acceptance tests

| ID | Scenario | Expected result |
| --- | --- | --- |
| R5.1 | Rename a source behind a default-titled simple map | Base label and following map title update consistently |
| R5.2 | Rename a source behind a custom-titled simple map | Source label updates; custom title stays unchanged |
| R5.3 | Explicitly rename a map, then rename its source | New explicit map title stays unchanged; follow mode is off |
| R5.4 | Rename one source in a comparison | Correct layer labels update everywhere; comparison title is preserved |
| R5.5 | Two version layers share one source | Both source components update; version labels remain distinct |
| R5.6 | Refresh a legacy saved map containing an old source label | Current source name is returned and persisted |
| R5.7 | Deleted source and subsequently imported similarly named source | Orphan's retained name/data stay intact; no relinking by name |
| R5.8 | Name-only rename with unsaved view filters/selection | Terrain snapshot bytes/values and current view remain unchanged |
| R5.9 | Export immediately after rename and after refresh | Per-source sheet names use the synchronized labels; filename respects map-title mode |
| R5.10 | Reopen app/database | Labels and title mode persist |
| R5.11 | Force a failure partway through update | Transaction restores the complete prior state |
| R5.12 | Run migration twice | No duplicate fields, lost rows, renamed custom titles, or ID changes |

## 8. Implementation order and file-level work plan

| Step | Work | Reason / completion condition |
| --- | --- | --- |
| 1 | Capture current tests; create isolated test DB; add focused failing cases for R1/R3/R4/R5 | Establish exact failures before making changes |
| 2 | Persistent map/filter view and selection-only updates | Fixes R1 and removes a major obstacle to reliable double activation |
| 3 | Scale controller, gesture coordination, basemap overzoom | Implements R4 using stable view/marker lifecycles |
| 4 | Name metadata rules, migration if needed, rename/refresh transaction, UI metadata refresh | Resolves R5 before exported sheet labels depend on it |
| 5 | Grouped comparison export and Excel title helper | Resolves R3 using the final naming contract |
| 6 | Supplied asset and favicon | Resolves R2; can be done independently of other code |
| 7 | Complete combined browser scenario, compatibility checks, README corrections | Confirm all five features work together |

Likely files to modify:

- Frontend: `web/components/app.js`, `web/components/terrain/FilterRail.js`, `web/components/map/MapCanvas.js`, `web/lib/geo.js`, `web/components/map/Legend.js` as needed, `web/components/maps/OverlayBuilder.js`, `web/lib/api.js` if API metadata changes, `web/styles/global.css`, `web/index.html`, and the new logo asset.
- Backend: `server/api/exportar.py`, `server/repo/bases.py`, `server/repo/mapas.py`, `server/api/bases.py`, `server/api/mapas.py`, and `server/db.py` only for the justified naming metadata/migration.
- Tests: `tests/test_api.py`, `tests/test_snapshots.py`, `tests/test_repo.py`, `tests/test_migration.py`, `tests/js/geo.test.mjs`, `tests/e2e/smoke.mjs`, plus focused new files if the existing ones become difficult to follow.
- Documentation: relevant README sections for logo packaging, double activation/scale, comparison workbook structure, reimport limitation, and naming behavior.

Do not refactor unrelated import classification, change the terrain data model broadly, replace Leaflet, or alter prices/coordinates in the user's real data.

## 9. Verification commands and integrated acceptance scenario

Run from `/Users/andrejasso/Desktop/ARA Map` after implementation:

```bash
python3 -m unittest discover -s tests -t .
node --test tests/js/*.test.mjs
./verificar.sh --todo
```

`verificar.sh --todo` prints browser-test instructions; it does not run the browser suite itself. Execute that suite separately against a throwaway database.

Example isolated launch for the implementing associate:

```bash
review_tmp=$(mktemp -d /tmp/ara-handoff-check.XXXXXX)
export ARA_MAP_DB="$review_tmp/ara_map.db"
python3 -u -c 'from server.app import serve; serve(port=8441, open_browser=False)'
```

Choose another free port if 8441 is occupied. In another terminal, install the declared browser-test dependencies if absent, then run:

```bash
cd "/Users/andrejasso/Desktop/ARA Map/tests/e2e"
npm ci
ARA_URL=http://localhost:8441 npm test
```

Use the supplied Python/runtime compatibility checks, not just the newest development Python. No new Python syntax or dependency should break the existing minimum-version launch workflow.

Perform this complete scenario with the already created fictitious workbooks in `outputs/comparacion-ficticia/`:

1. Import August and September as two separate bases. Verify 12 and 13 accepted terrain records, with one unplaced record in each.
2. Confirm the supplied logo appears in the header and browser tab.
3. Focus search once and type `Paseo`. Edit in the middle, clear it, and verify filters/results keep working.
4. Double click the located Paseo del Roble marker from a distant zoom. Check the final scale calculation and visible placement with the detail panel open. Repeat on touch and each basemap.
5. Save one map using its default source-derived title and one with a custom customer title. Save or create a comparison including both bases.
6. Rename a source. Check the gallery, active map heading, layer chips/legend, terrain details, comparison table, and naming-mode distinction.
7. Export the unfiltered comparison: two source sheets with 12 and 13 terrain records. Open the actual download and inspect values/types.
8. Apply a filter or hide a layer, then export again: preserve every source sheet but export only selected visible records; excluded layers have only headers.
9. Explicitly refresh the saved map and verify source names. Export once more to confirm output labels agree with the UI.
10. Restart/reopen, check saved view/name behavior, and confirm no fake records entered the production database.

Fixture caveat: the earlier response described 7 unchanged and 3 modified terrains, but Reserva El Encino changes from 91,000 to 91,300 m²—about 0.33%, below the comparison code's 0.5% tolerance. Do not use that previous advertised change count as a new regression oracle without inspecting current matching rules. The 12/13 source-row export counts are reliable; for a guaranteed change-status assertion use the substantial price change or affected-percentage change, or create a dedicated synthetic record.

## 10. Required handback from the implementing AI

Return a concise summary of the five completed behaviors, exact tests run, any untested platform-specific touch behavior, and the resulting workbook naming/filter semantics. Include screenshots of the supplied logo and a terrain after double activation, plus inspection of an actual downloaded multi-sheet workbook. State whether a schema migration was added and how existing custom titles and historical version labels are preserved.

Do not mark this work complete solely because existing tests pass. Completion requires the new acceptance cases, sequential typing, a real terrain double-click/tap, correct frozen-row membership per exported sheet, and persisted source-name propagation.

## Implementer brief

> Implement R1–R5 in the current ARA Map repository using this report as the technical specification. Preserve existing snapshot/data-integrity fixes. Keep search inputs and map interaction stable across state updates. Use the provided logo unchanged. Export comparison snapshots into one worksheet per layer while preserving filtered row selection. Calculate terrain-specific scale zoom and handle desktop/touch gestures without first-click rerender interference. Synchronize renamed source labels, explicitly distinguish following versus custom map titles, and preserve historical layer provenance. Add focused regression tests and run the combined acceptance scenario on a disposable database. Do not alter real terrain data or unrelated features.
