# ARA Map — supervisor acceptance review

Reviewed September 21, 2026 against the supplied source code and workbook.

**Decision: return for corrections before handing this over as a finished tool for customer conversations.** The interface and basic workflow are promising. The blocking problems concern whether updates, saved history, and comparisons can be trusted.

This was a review, not a repair pass. Application code and the existing production database were not changed. Tests and exploratory writes used a separate database at `/tmp/ara-supervisor-review-20260921.db`. Screenshots accompany this report.

## Fit against the requested workflow

| Requirement | Assessment |
| --- | --- |
| Input datasheets | Works for supported Excel workbooks with recognized headers. It is not a general CSV/PDF/arbitrary spreadsheet importer. Missing-name rows can disappear without a warning. |
| Locate terrains on a map | Works for records with usable coordinates; no automatic address geocoding. Invalid coordinate pairs are still counted as located. |
| Click a terrain to see its information | Verified directly by clicking the Tijuana marker. Detail view includes prices, area, address, coordinates, extra fields, and data-quality findings. |
| Save maps for later | Frozen snapshots work in normal use and survive source deletion, but source-ID reuse can make a subsequent refresh load unrelated records. |
| Compare maps | Two-source standard checks pass. Three or more layers can report false new terrains, and location-only changes are not reported. |
| Create a map by merging existing maps | Works for different sources. Different historical snapshots of the same source are incorrectly collapsed. |

## Required corrections

P1 means fix before handoff because the result can omit or misrepresent customer information. P2 means a significant correctness issue to include in the acceptance work.

### 1. P1 — a saved map can reconnect to an unrelated source

**Reproduction:** save a one-terrain map from the newest source; delete that source; import an unrelated workbook; refresh the saved map. The deleted source and the new source both received ID `2`. The old map then reported its source as existing. Refresh changed its count from **1 to 79**, while its layer still displayed the old source name.

**Cause:** `server/db.py:25` uses a reusable SQLite integer primary key. Saved layers retain that ID after deletion. `server/repo/mapas.py:89–102` treats any base with that ID as the original source and replaces the snapshot.

**Required fix:** use non-reusable source identity and safely disconnect deleted sources from saved layers. Include migration handling. Test delete → import unrelated workbook → reopen → refresh, checking both provenance and terrain contents.

### 2. P1 — coordinate corrections are discarded when adding an updated workbook

**Reproduction:** import a terrain without coordinates, then use the append workflow with the same name, place, area, and price but valid coordinates. Preview returned **0 new, 1 duplicate, 0 conflicts**. Confirmation returned **0 updated, 1 omitted**; the stored coordinates remained empty.

**Cause:** `server/matching.py:103–104` decides whether an identity match is a duplicate using total price only. `server/repo/terrenos.py:115` does not even retrieve the existing coordinates or other editable fields for comparison.

**Required fix:** distinguish identity matching from content equality. Compare all imported business fields, show old/new values for changes, and allow a deliberate update. Verify coordinate, address, unit-price, restriction, and extra-field corrections.

### 3. P1 — comparisons with three or more layers invent new terrains

**Reproduction:** pass the same terrain with identical values in three layers to `compareLayers`. Actual statuses were **Base, Sin cambio, Nuevo**. The third layer should also be unchanged.

**Cause:** `web/lib/comparar.js:91–102` shares one set of claimed baseline rows across every subsequent layer. A match in layer two makes that baseline row unavailable to layer three.

**Required fix:** maintain one-to-one matching separately for each comparison layer. Also define and display removals per comparison layer; current removal reporting is restricted to exactly two layers.

### 4. P1 — merging different historical versions drops a version

**Reproduction:** save map A with one terrain, add a second terrain to its source, and save map B with two terrains. Merging A then B produced **one layer with one terrain** and classified B's layer as a duplicate. Selecting B first would instead retain B's contents. The original saved maps remain intact, but the merged result cannot compare their history.

**Cause:** `server/repo/mapas.py:174–175` deduplicates by source ID rather than frozen contents or snapshot identity. The preview warns that a layer will be omitted, but offers no way to keep both different versions.

**Required fix:** retain distinct snapshots of the same source, label them by map/version/date, and deduplicate only genuinely identical layers or let the user choose explicitly.

### 5. P1 — incomplete rows disappear without being accounted for

**Reproduction:** preview a workbook containing one named row and a second row with area, price, state, municipality, and coordinates but no terrain name. Preview reported **one terrain and no findings**. It did not identify the omitted row.

**Cause:** `server/importer.py:193–196` drops unnamed rows. Although its comment says the caller reports a count difference, the import result and preview do not retain the necessary rejected-row information.

**Required fix:** account for every nonblank input row as accepted or rejected. Show rejected row numbers and reasons, and preserve enough information to correct them. An incomplete record must not disappear behind a clean import message.

### 6. P2 — invalid coordinates are treated as map-ready

**Reproduction:** preview latitude `-103.7`, longitude `20.6`. Validation correctly reported `COORD_INVERTIDA`, but the same preview reported **1 located, 0 unlocated**. The marker renderer accepts records on that same located flag.

**Cause:** `server/importer.py:114–116`, `server/repo/terrenos.py:145`, and the snapshot repository define located as merely having two non-null values.

**Required fix:** retain the original values but separate valid, missing, and invalid locations. Exclude impossible coordinates from normal plotting and framing; show suspicious locations for deliberate review. Do not silently swap coordinates.

### 7. P2 — location changes are labeled unchanged

**Reproduction:** compare matching terrains with coordinates changed from `(20, -103)` to `(21, -104)` and all reported financial values unchanged. The second terrain is labeled **Sin cambio**.

**Cause:** `web/lib/comparar.js:26–31` considers only total price, unit price, area, and percentage affected.

**Required fix:** report coordinate, address, and other relevant field changes, or explicitly narrow the label to the fields actually compared. A materially moved map marker should not appear to have unchanged information.

## Evidence and limits

- `./verificar.sh --todo`: 203 Python tests passed under the default Python and the suite also passed under macOS Python 3.9.6; Ruff and mypy passed; reported backend coverage was 93%.
- JavaScript suite: 36 tests passed.
- Browser smoke suite against the isolated server: 20/20 checks passed with no console errors. Covers filtering, details, satellite switching, two-layer comparison, frozen snapshots, refresh, and preservation after deletion.
- Additional manual browser inspection: imported the actual supplied workbook through the UI, inspected its preview and rendered map, and clicked the Tijuana marker to open its details.
- Additional focused API and JavaScript reproductions confirmed the seven issues above. The existing suite does not cover these cases sufficiently. Some browser checks inspect application state rather than actual rendered marks; passing them alone does not establish visual correctness.
- This was not a large-dataset load test or a clean-machine installation test. Suitability for thousands of terrains, arbitrary supplier templates, or other computers remains unverified.

The supplied workbook contains **79 terrains: 39 with coordinates and 40 without**. Its preview identifies 47 rows with observations, including a price inconsistency, a zero price, possible duplicates, and nonnumeric values. Missing coordinates are a source-data limitation, not proof that the map renderer is failing. The boss should see an explicit coverage count during customer conversations.

The app depicts points and area-equivalent circles, not property boundaries. Its existing explanation of this limitation is useful. Basemap imagery depends on external tile services; a reliable offline map experience was not established.

## Useful additions after correctness fixes

1. **Location review queue:** locate a terrain by address or dropping a pin, preview the proposed coordinates, and record who confirmed them and when.
2. **Stable terrain identifiers:** support a persistent property reference and a reviewed matching process. Name plus area is insufficient when parcels are renamed, corrected, or share similar names.
3. **Explicit comparison controls:** select the reference map, show old/new values and numerical differences, and filter to changed, added, or removed terrains.
4. **Customer shortlist and presentation view:** select relevant properties, hide internal notes, and export a printable map with property details, source date, and a boundary disclaimer.
5. **Spreadsheet setup assistant:** choose the worksheet and map supplier columns to terrain fields, with a downloadable template and full accepted/rejected counts.
6. **Visible backup and recovery controls:** show the latest backup, provide a restore workflow, and confirm recovery using a disposable copy before rollout.

## Approval gate

After the corrections, rerun the supplied tests and add regression coverage for the reproduced failures. Then complete one uninterrupted acceptance scenario: import a real workbook → reconcile every row → correct a missing location → click and verify details → save and reopen the map after restarting → compare three versions → merge versions of the same source → delete and replace a source without changing historical provenance.

Approve a supervised pilot once that scenario passes and the missing-location limitation is understood. The current build is suitable for a demonstration of the concept, but not yet for a final handoff as a dependable customer reference.
