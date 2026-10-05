# ARA Map: presentation and handover readiness

Prepared for the project supervisor | September 30, 2026 | Presentation: October 1, 2026

## 1. My decision

**Conditional GO for a rehearsed desktop demonstration. NO-GO for an unrestricted handover or a promise that arbitrary spreadsheets and mobile use are fully supported.**

ARA already demonstrates the core business idea well: find a terrain visually, inspect its information, keep saved views, compare sources, organize them in folders and export a workbook. The principal workflows passed extensive checks. This is substantial working software, not just a visual prototype.

However, I would not put an unprepared owner in front of the current opening screen. A new visit selects a database with **34 terrains, zero map locations and zero prices**. The phone layout hides search and filters entirely. The latest import corrections have not all reached the live frontend, and four findings in the local candidate remain unresolved. These issues affect trust more than adding another impressive feature would help.

**My recommendation for tomorrow:** demonstrate the reliable desktop workflow with a prepared, approved dataset. Explain the remaining data and import limitations plainly. Treat the meeting as acceptance of the product direction and core workflow, not final acceptance of unrestricted production use. Do not enable paid AI or introduce a new major feature overnight.

| Decision | Recommendation |
|---|---|
| Show the core idea on a laptop / desktop | Yes, after selecting the demonstration database and rehearsing the route below |
| Let the owner upload an unfamiliar workbook without preparation | No; several layouts still fail to interpret fully |
| Present phone/tablet use as equivalent to desktop | No; search and filters disappear at 960 px and below |
| Promise all terrains are accurately located and priced | No; source/data completeness and price consistency need review |
| Hand over as a finished, generally reliable operational system | Not yet; resolve the focused defects and clarify access expectations |
| Add new AI or a major feature before tomorrow | No; prioritize a reliable demonstration and a clearly bounded next phase |

The canonical demonstration address is **https://ara-map-ivory.vercel.app**. The alternate **ara-map-aicore2.vercel.app currently redirects to Vercel login** in a fresh unauthenticated session. Do not send that alternate link to the owner.

## 2. What I checked and what works

I checked the actual public site, signed in through its editor login using the existing local credential, inspected the current code and earlier review findings, and exercised imports and editing in disposable local databases. Production was kept read-only: browser requests were restricted to reads, login/logout and non-mutating exports. No production upload, draft, import, rename, refresh, deletion, migration or deployment was performed. Credentials were not included in the report or evidence.

| Area | Evidence and outcome |
|---|---|
| Live availability and login | Main address loads; visitor mode and editor sign-in/sign-out work; private import settings return 401 to visitors |
| Map, search and detail | Desktop keystrokes retain focus; accent-insensitive search works; terrain details open and close with Escape |
| Zoom and basemaps | Live double-click reached required terrain scale, zoom 11 in the checked case; basemap controls and tile requests worked |
| Saved maps and comparisons | Both existing live comparisons reopen with their layers; hiding/restoring a layer affects the intended source |
| Live exports | All four bases and both comparisons exported readable workbooks with expected row counts; comparison sheets remain separated by source layer |
| Local end-to-end workflows | **65/65 browser checks pass**, including imports, questions, saved formats, folder actions, append, rename propagation, snapshot refresh and merging |
| Ordinary Python suite | **605 discovered; 584 executed successfully, 21 PostgreSQL tests skipped**; suite also passes on macOS Python 3.9.6 |
| Separate real PostgreSQL check | **21/21 pass** on a disposable PostgreSQL 17.11 cluster with UTF-8 encoding; production Neon was not used |
| JavaScript, lint and types | JavaScript suite passes; ruff and mypy pass; Python coverage is **94%** |
| Import variety matrix | 36 fictional files: **25 meet their expected outcome; 6 mismatch; 1 unresolved; 4 clearly rejected**. This is a boundary test set, not a real-world accuracy percentage |
| Narrow layouts | Header/page widths fit at 320, 375, 768 and 1440 px in live checks; functional search availability fails below the desktop breakpoint |

The initial live script recorded 19/20 passes because one test expected mixed-case "Coordenadas" while the UI displayed uppercase text. A focused, case-insensitive recheck passed; this was a test assertion issue. A separate focused pass confirmed the real mobile search failures at 375, 768 and 960 px and successful search visibility at 1024 px. There were no page errors or failed network requests recorded in the main live browser audit.

The first temporary PostgreSQL cluster used SQL_ASCII because the audit harness omitted an encoding setting. That produced bytes-versus-text failures. Recreating the disposable cluster explicitly as UTF-8 resolved them; the final 21 tests passed. No application code was changed to obtain that result.

## 3. Risks the owner would notice

### A. The opening screen is an empty map

A fresh session automatically opens **Copy of REPORTE RESERVA ARA**. All 34 stored records lack usable coordinates and asking prices. The interface reports this honestly, but a client expecting an immediate map sees an apparently empty product.

**Before the meeting:** open a prepared database explicitly. Do not claim that the application can place records without usable locations. I did not inspect the original uploaded reserve workbook during this audit, so I cannot determine whether coordinates were absent in the source or unrecognized during its import.

### B. Data quality still limits the value of the demonstration

| Current database | Terrains | Located | With asking price |
|---|---:|---:|---:|
| Copy of REPORTE RESERVA ARA | 34 | 0 | 0 |
| Base Terrenos 09.26 Gerardo | 79 | 39 | 59 |
| Fake 1 | 12 | 11 | 12 |
| Fake 2 | 13 | 12 | 13 |

These counts describe stored records, not unique properties across all databases. The Gerardo file has **40 unlocated terrains and findings on 47 records**; findings include warnings as well as errors. At least one terrain displays an explicit approximately tenfold inconsistency between total price and price-per-square-meter times area. The warning is useful; the displayed amount is not thereby verified.

The reserve data also splits state labels such as `Q. ROO` and `Q.ROO` into different filters. This is a data-normalization limitation, not proof that the map is broken. Test-oriented names such as "Fake 1", "Fake 2", "prueba comparación" and "Copy of..." remain visible. Do not present fictional records as actual inventory.

**Before the meeting:** select a small group of owner-approved records with verified coordinates, areas and prices. Keep fictional comparison data clearly labelled. The existing prepared files are suitable for a product demonstration, not for validating the company's commercial data.

### C. Mobile fits visually but cannot perform the main lookup task

At **960 px and below**, `.rail-slot` is set to `display: none`. There is no alternate Search/Filters button. The owner can browse a map on a phone but cannot perform the central "find this terrain" workflow there. I reproduced this on the live website at 375, 768 and 960 px; it works at 1024 px.

**Required before claiming mobile readiness:** expose search and filtering through an accessible drawer or equivalent control, and test actual searching, clearing and filtering. Passing an overflow test is not enough. For tomorrow, use a desktop viewport above 960 CSS pixels; a narrow browser or high browser zoom can trigger the same limitation on a laptop.

### D. Visitor access is public reading, not private access

Without signing in, a visitor can list the inventory, read terrain details and download spreadsheets. The login protects editing, not viewing. Additional source fields can include company and deed-related information. This is the current designed permission model, not an authentication bypass.

**Owner decision before handover:** is this an intentionally viewable catalog, or an internal company tool? If the records are confidential, requiring authentication for reads and exports becomes a release requirement. Do not describe the site as private merely because it has a login button.

## 4. Software issues and release status

### The live site and local candidate are different

The live `AssistantViews.js` and `ImportAssistant.js` match the earlier released polish snapshot byte-for-byte, and do not match the current local files. The local server/web source files checked are unchanged since the September 28 follow-up review. There is no evidence that its four requested corrections have been implemented.

This verifies **frontend release drift**; it does not prove the exact deployed Python backend revision. I did not create production import drafts to test that backend because you requested no changes. Consequently, passing local import tests cannot certify that the live importer includes the candidate's fixes.

| Unresolved issue | Consequence | Priority / decision |
|---|---|---|
| Certain valid Excel currency formats bypass foreign-currency detection | Explicit USD or pound amounts can become stored MXN asking prices. Reproduced through local preview and confirmation | High: fix before general import acceptance |
| Row exclusions follow their numeric index when switching worksheets | Excluding a terrain on sheet A can remove an unrelated terrain on sheet B. Reproduced through storage | High: fix before general import acceptance |
| Removing the last terrain hides all restore controls | The manager must restart or use an API workaround to undo a normal review action | Medium: retain a reversible zero-selection review state |
| Row correction controls are truncated | Only the first 12 exclusions are rendered; only the first 100 accepted rows are available in the preview | Medium: provide paging/search or another way to reach every source row |
| Search and filters are hidden on narrow screens | Terrain lookup is unavailable on phones and many tablets | High if mobile is promised; otherwise disclose desktop-only demonstration |

The fresh follow-up regression run has **one passing control and four failing assertions**, covering the first three issues above (two currency cases). The fourth remains evident in unchanged code and the prior browser reproduction. Detailed reproduction steps and acceptance criteria already exist in the September 28 supervisor review; the developer should work from that packet rather than reinterpreting this executive report.

### Remaining import boundaries

The seven files that still fall short are MapTest8, 12, 13, 15, 16, 18 and 34: repeated-price meanings on first import; transposed property cards; side-by-side tables; combined coordinates; degrees/minutes/seconds coordinates; mixed numeric conventions by column; and files with no header row. Some can be recovered through manual mapping, but they are not all supported by the guided flow.

UTF-16 and Windows-1252 CSVs currently require re-export as UTF-8. Empty and malformed CSVs are rejected clearly. The live upload limit is **4 MB**. Do not describe the importer as accepting any layout, encoding or file size.

AI was not activated or evaluated against a real provider in this audit. The existing integration can suggest column meanings; it is not a solution to the structural cases above. No paid AI call was made by the audit.

## 5. The presentation I would approve tomorrow

**Prepare a desktop browser at normal zoom, above 960 px, on the main ivory URL. Use a stable internet connection; map tiles depend on external services. Log in beforehand only if editing is part of the demonstration.**

| Time | Demonstration | Message to the owner |
|---|---|---|
| 0:00-1:00 | Open Bases, then the prepared Gerardo dataset or an approved demonstration database | "Your spreadsheets become a visual terrain inventory." Do not start on the empty reserve map |
| 1:00-2:30 | Search for an approved terrain; open its details; double-click or use Ver a escala | "We can answer where it is and inspect its source information quickly." Explain approximate circles |
| 2:30-3:30 | Filter by state and area; switch between map and table | "The same inventory can be explored visually or as a list." |
| 3:30-4:30 | Open Fuera del mapa and briefly show a data warning | "Missing or suspicious source information stays visible for review." |
| 4:30-6:00 | Open an existing saved comparison, show source layers, toggle a layer | "Maps are reusable and multiple sources can be viewed together." Identify fictional test data |
| 6:00-7:00 | Export the comparison and show its separate Excel sheets | "Each compared source remains identifiable in the export." |
| 7:00-8:00 | Show the Bases/Mapas folder navigation and explain the next acceptance step | "Organization and saved views make the tool useful beyond a single upload." |

**Optional live upload:** only use a file that has been rehearsed against the intended release and whose expected record count, coordinates and currency are known. The local MapTest1/2 controls are useful rehearsal inputs, but this audit did not upload them to production. If that rehearsal is not completed before the meeting, demonstrate import separately on a disposable local instance or show the recorded workflow; do not improvise with the owner's unfamiliar file.

**Preparation actions need no new feature:** choose the opening database, verify the sample terrain, confirm whether the audience may see commercial data, clearly identify test datasets, choose the correct URL and have the report/screenshots available if the venue connection fails. Do not rush an unreviewed deployment simply to say the newest code is live.

**Statements I would not approve:** "any spreadsheet works", "all properties are correctly mapped", "these circles are the legal boundaries", "the site is private", "AI is already interpreting everything", or "mobile has the same capabilities".

## 6. What should be added next

**Before adding functions, finish the import safety corrections and make search reachable on mobile.** Those are completion work for the existing promise, not optional extras.

| Proposed addition | Business value | Scope and timing |
|---|---|---|
| **Data-completion workflow** | Highest priority: turns unmapped inventory into usable map records. The live data shows why this matters | A list of missing/invalid location and price fields, source-row links, validated coordinate entry or map-pin correction, clear confirmed/proposed status, and an audit trail. A geocoding suggestion must require user confirmation. Plan after stabilization |
| **Customer-ready terrain factsheet** | Directly supports the owner's conversations with customers | A printable/PDF sheet with the selected terrain, map, area, verified price/currency, source/update date and relevant notes. Exclude internal/contact/deed fields by default and let the editor choose what to share. A strong second phase |
| **Controlled AI import pilot** | Could reduce mapping questions on unfamiliar headings | Benchmark on known and unseen files, with a small API budget and exact correctness checks. Keep manual fallback. Do not sell this as universal layout support or enable it the night before the presentation |

If only one new function is commissioned, I would choose **data completion** before AI: a better interpreter cannot recover coordinates that are not supplied, and the current opening dataset has none stored. If the owner's immediate priority is sending information to customers, the factsheet is the next most useful deliverable.

### Decision to take after the presentation

Ask the owner to confirm the intended users/devices, public versus internal access, the actual source files they expect to import, and who is responsible for verifying coordinates and prices. Agree on those acceptance boundaries before treating the project as handed over.

For developers, commission a narrow stabilization pass: resolve the four prior findings, restore narrow-screen search, identify the exact release, then verify that release before deployment. For the supervisor, the immediate job is approving the demonstration dataset and scope. **There is enough working functionality to make a strong presentation; there is not yet enough evidence to promise unrestricted operational readiness.**

## Evidence and limits

This report is a point-in-time functional, code and data-readiness audit. It is not a penetration test, a legal review of data disclosure, a survey of property boundaries, a valuation check, a high-concurrency/load test, or a browser certification for Safari and Firefox. Real AI, live production writes, backup restoration and arbitrary large workbooks were not exercised.

### Other limits to explain accurately

- Circles show area around a point, not surveyed parcel boundaries. The interface already explains the approximate shape.
- Saved maps preserve snapshots; updating source data does not silently replace a saved snapshot. Refresh is a deliberate action.
- Comparison exports have one sheet per saved layer, including an empty sheet if filtering removes that layer's rows. The workbook exports standard terrain fields, not every additional source column. Do not use it as a full-fidelity source backup.
- One saved three-layer comparison initially hides one layer in its saved view. Its total stored count and currently visible count can therefore differ. Toggle it on for a three-source demonstration.

### Evidence index

The evidence folder contains live API/source comparisons, export sheet counts, live browser results and screenshots, local browser output, the full verification log, PostgreSQL output, the 36-file matrix, reproduced open regressions, and before/after integrity checks. Test counts and observed limitations must be read together; passing existing tests did not cover the defects found by independent checks.

- `evidence/live-browser.json` and `live-focused.json`: current live checks and mobile failures.
- `evidence/live-data-and-exports.json`: stored-data counts and all six live export checks.
- `evidence/release-drift.json`: old-release versus current-local frontend comparison.
- `evidence/local-browser.txt`, `verification.txt`, `postgres.txt`: successful ordinary/browser/Postgres checks.
- `evidence/open-regressions.txt`, `import-matrix.json`: unresolved local cases.
- `../map-import-fixes-2026-09-28/supervisor-review/SUPERVISOR_REVIEW.md`: detailed existing developer work order.
- `evidence/unchanged-check.json` and `production-after.json`: application-source, local database and live terrain-row integrity checks.

Only audit scripts, evidence and this report were created. No application code or company records were changed. Temporary test servers/databases were stopped and removed. The owner should receive the presentation; this report and its technical evidence are for the supervisor's acceptance decision.
