# Team B — E1: boundary ring drawing without the `closePath()` stall

Team B · draft implementation · October 8, 2026

| Item | Value |
|---|---|
| Instruction | `75611396a1d085372d5a32cd0c76866d99b3d930` on `codex/supervisor-completion-brief`: `reports/team-b-display-review-2026-10-08/START_HERE.md` and `TEAM_B_E1.md`, read with `git show`. The checkout was not switched. |
| Branch / base | `claude/team-b/boundary-path-drawing`, created from accepted B-2 **`5d8e2dcc125a688dbba38a260d5d7eca88a6d223`** (PR #11). The draft PR targets `claude/team-b/map-boundaries`, as the packet says. |
| `main` | `09452fd26d38319567dce28a89db100ea61c739a`, fetched today. It has not absorbed B-2, so the stacked base applies. |
| Implementation commit (measured) | **`496233e3c86fac40981f23671633c4fbbd157b97`**. Every result below ran at this commit. |
| Investigation | PR #16, `claude/team-b/display-strategy`. Its F1–F3 corrections are returned separately on that branch (head `5a60f7a` plus its verification commit) and are not part of this PR. |
| Browser / machine | Headless Chromium **141.0.7390.37** (Playwright's build), software rasterization. Intel Xeon @ 2.80 GHz, 4 cores, 15.7 GiB RAM, Linux 6.18, Node 22.22.0. |

---

## 1. What changed

**Application code: one B-owned file, `web/components/map/MapCanvas.js`**, +86 / −1 lines.
- A boundary outline is now an `L.Polygon` subclass. Before, it was `L.polygon`; the options, tooltip, events and selection styles are unchanged.
- The subclass overrides only `_updatePath`, the step that writes the rings into the canvas:
  - The rings Leaflet has already projected, clipped and smoothed (`this._parts`), in the same order, become **one `Path2D` built from SVG path data**: `M x y L x y … Z` for each ring. `Z` closes a ring exactly as `closePath()` does.
  - **Leaflet's own `_fillStroke`** fills and strokes that path. It receives a view of the renderer's context whose `fill(rule)` and `stroke()` apply to the `Path2D`; every other property and method is the real context's.
- Projection, clipping, smoothing, even-odd fill, style and dash options, selection restyling, bounds and hit testing (`_containsPoint` on the same `_parts`) remain Leaflet's and B-2's.
- No change to:
  - the parser, body validation (`cuerpoLeaflet`), coordinates or terrain identity;
  - XY markers, symbols or other layers;
  - vendored Leaflet;
  - workers, caches, pending states, or the renderer interface.

**When the new path is used.** All of these must hold:
- `L.version === "1.9.4"`;
- the layer's renderer is an `L.Canvas` with `_fillStroke` and a 2D context;
- `Path2D` exists;
- **every position is a whole pixel**, so the text form is exact. Leaflet's canvas renderer rounds projected and clipped points, so in practice this always holds.

Otherwise the layer calls `L.Polygon.prototype._updatePath`, which is Leaflet's own drawing for that renderer: canvas `closePath()`, or SVG. §3.3 tests each fallback.

**New test and measurement files.** These are dedicated files; no existing file changed.
- `tests/e2e/contornos-trazo.html`: harness page. `?mapa=actual` loads this branch's renderer; `?mapa=base` loads the accepted B-2 file, served from `git show 5d8e2dc`.
- `tests/e2e/contornos-trazo.mjs`: complete-RGBA regression, plus mechanism and fallback checks.
- `tests/e2e/contornos-trazo-medicion.mjs`: before/after timing with the corrected instrumentation (PR #16 review F1).
- This folder:
  - `generar_casos.py`: a copy of PR #16's deterministic generator of the four fictional parser-limit cases (needs an archive of B-1, `efc3628`);
  - `micro-cierre.mjs`: the browser-call microbenchmark;
  - `evidencia/`.

## 2. Why not `lineTo(first)`, as the packet describes

The packet asked to close each ring "with a line back to its first point instead of repeated `closePath()` calls", and not to relax the comparison if a supported case differed. **It differs**, and so does the next obvious alternative. Both are the concrete incompatibilities this section reports.

1. **`lineTo(first)`.** A ring closed this way is an *open* subpath. Its seam gets two round caps where `closePath()` gives a round join, and the anti-aliased pixels at the seam change.
   - In the real renderer (PR #16 §11.6), it changes the complete RGBA buffer in 1 of 16 views at DPR 1 and 6 of 16 at DPR 2, wherever a seam is on screen. The alpha mask is unchanged.
   - In `micro-cierre.mjs` (synthetic rings, the three outline styles, DPR 1 and 2), 6 to 34,892 bytes differ.
   - Earlier comparisons, PR #16's and the supervisor's 12, never put a seam on screen.
2. **Each ring closed on its own `Path2D` (cheap `closePath()`), merged with `addPath`.** This is byte-identical on small sets. But on Leaflet's real parts of "one large part + 19,999 small" at zoom 10, where 19,999 rings are two positions long, **two-position rings stop being painted beyond about 1,000 rings in the path**: 78,520 painted pixels instead of 107,008. That is IoU 0.726 against B-2 (PR #16, `diagnostico-addpath.mjs`). The packet's comparison caught this before implementation.

**The mechanism used.** One `Path2D` from SVG path data matches `closePath()` drawing at every size tested, including that case (107,008 pixels).
- In `micro-cierre.mjs` it builds 20,000 rings in **23.1 ms**, against **2,020.6 ms** for `closePath()` and 6.6 ms for `lineTo(first)`.
- It differs from `closePath()` by **0 bytes** in all 12 style, DPR and set combinations (`evidencia/micro-cierre.txt`).

**This is a deviation from the packet's literal mechanism, for the supervisor to accept or reject.** The fill/stroke pipeline (`_fillStroke`, styles, selection) is retained. Fill and stroke receive the path as an argument instead of reading the context's current path.

## 3. Verification

### 3.1 Existing B-2 browser checks

`tests/e2e/contornos.mjs` (unchanged) passes against this branch: **20 of 20 checks** (`evidencia/contornos.txt`). It drives real mouse input on the 12-row fixture and covers:
- placement by outline, XY or neither;
- the initial frame;
- a discrepant XY that keeps the outline;
- list selection framing the whole multipart;
- a real click on each part selecting the same terrain;
- a hole: no fill and no selection;
- legacy XY selection;
- distant-zoom symbols;
- double-click `zoomToScale` → `a_escala`;
- a missing body and inconsistent bodies (shifted, collapsed) shown as "not available" symbols;
- a failed replacement keeping the previous active geometry;
- filtering;
- a pending click on a filtered terrain;
- a scattered multipart keeping a clickable symbol;
- `render([])` clearing everything;
- invalid input;
- **an XY-only render pixel-identical to the baseline renderer** (26,594 painted pixels each);
- no page errors.

### 3.2 Complete-RGBA paint identity against accepted B-2 (`contornos-trazo.mjs`)

**Method.** Both renderers run in fresh pages through the same deterministic steps. At every view and style the overlay canvas is read after two frames, recording:
- the real width and height (asserted equal on both sides);
- the count of painted pixels;
- the SHA-256 of every RGBA byte.

Blank captures fail. Zoom and centre are asserted equal on both sides.

**Coverage:**

| Dimension | Covered |
|---|---|
| Cases | 12-row fixture (simple, hole, 2-part multipart, U shape, discrepant, replacement, coincident…); 500 XY points; the four parser-limit cases (`circulo-100k`, `multiparte-20000`, `grande-mas-19999`, `denso-grande-mas-19999`). The generated JSON SHA-256s match PR #16's manifest (`evidencia/casos-manifest.json`). |
| Views per active boundary | Overview (`fitTo`); the outline zoom (`zoomToScale`); a small part 2 levels deeper (multipart); **the ring-closing seam**: the first position of the first ring, 3 levels deeper; **a corner of the bounds 1 level deeper**, where the outline is clipped at the canvas edges. |
| Styles at each view | Normal; dashed (`"3 2"`, as `layerDash` gives); selected. |
| DPR | 1 (1440 × 768 canvas) and 2 (2880 × 1536) |

**Result: 252 of 252 captures are RGBA-identical**, with equal SHA-256 and equal painted counts:

| Case | DPR 1 | DPR 2 |
|---|---:|---:|
| Fixture, 12 rows | 68 / 68 | 68 / 68 |
| 500 XY points | 5 / 5 | 5 / 5 |
| One ring, 100,000 positions | 11 / 11 | 11 / 11 |
| 20,000 scattered parts | 14 / 14 | 14 / 14 |
| One large part + 19,999 small | 14 / 14 | 14 / 14 |
| Dense: large + 19,999 | 14 / 14 | 14 / 14 |

Every capture's dimensions, painted count and both full hashes are in `evidencia/contornos-trazo.json`. Geometry, validation, coordinates and hit testing are untouched by construction (§1); the click checks in §3.1 exercise them.

### 3.3 Mechanism and fallbacks (`contornos-trazo.mjs`, fixture, DPR 1)

| Check | Result |
|---|---|
| Accepted B-2: rings closed on the context | 2 context `closePath()` calls per redraw at the multipart view |
| This branch | **0** `closePath()` calls on the context or on `Path2D`. Rings are closed by `Z`. Same bytes as B-2. |
| Fallback: Leaflet version not 1.9.4 | Leaflet's own drawing (2 context `closePath()` calls), same bytes as B-2 |
| Fallback: no `Path2D` | Same |
| Fallback: positions not whole pixels (Leaflet's rounding disabled in the page) | Leaflet's own drawing; same bytes as B-2 under the same condition |
| SVG renderer | The outline class draws Leaflet's SVG path (2 rings closed with `z` for the polygon with a hole), with no errors |

### 3.4 Timing before and after

**Browser call alone** (`micro-cierre.mjs`; 20,000 rings in one path; build time only; best of 3):

| Way of closing | Build time |
|---|---:|
| `closePath()` (accepted) | 2,020.6 ms |
| `lineTo(first)` | 6.6 ms |
| Per-ring `Path2D` + `addPath` | 27.9 ms |
| **One `Path2D` from path data (this branch)** | **23.1 ms** |
| One `Path2D`, `closePath()` per ring | 2,039.6 ms |

**Whole renderer** (`contornos-trazo-medicion.mjs`): the accepted file against this branch. 3 runs each, interleaved, each in a fresh page.
- **Cold** = `render()` plus `zoomToScale()` (or `fitTo` for XY).
- **Direct** = four non-animated redraws: pan ±200 px, zoom ±1.

Each phase starts in a page task. The longest Long Task overlapping the phase is read after the observer is drained. Negative controls run first through the same phase code (150 ms of busy work, 5 ms of it before the marker): **all 10 were detected**, at 155–173 ms. The synchronous call is reported separately.

DPR 1:

| Case | Renderer | Cold: call, median / worst (ms) | Cold: longest task | Direct: call, median / worst (ms) | Direct: longest task, median / worst | Direct tasks ≥ 50 ms |
|---|---|---:|---:|---:|---:|---:|
| Fixture, 12 rows (normal control) | B-2 | 19.7 / 26.2 | 0 | 1.0 / 6.3 | 0 / 0 | 0 of 12 |
| | this branch | 18.2 / 22.4 | 0 | 0.9 / 1.3 | 0 / 0 | 0 of 12 |
| 500 XY points (XY control) | B-2 | 42.4 / 53.5 | 53 | 1.8 / 3.8 | 0 / 0 | 0 of 12 |
| | this branch | 48.9 / 54.0 | 54 | 2.0 / 3.6 | 0 / 0 | 0 of 12 |
| One ring, 100,000 positions (single-large-ring control) | B-2 | 257.4 / 272.4 | 272 | 24.0 / 88.7 | 0 / 88 | 6 of 12 |
| | this branch | 247.2 / 249.4 | 249 | 12.8 / 133.3 | 0 / 133 | 6 of 12 |
| 20,000 scattered parts | B-2 | 250.0 / 263.5 | 263 | 8.6 / 87.3 | 0 / 87 | 4 of 12 |
| | this branch | 238.5 / 242.6 | 242 | 9.4 / 98.3 | 0 / 98 | 4 of 12 |
| **One large part + 19,999 small** | B-2 | 1,369 / 1,384 | **2,336** | 1,086 / 1,210 | **1,086 / 1,209** | 12 of 12 |
| | **this branch** | 276.5 / 287.7 | **287** | 33.4 / 97.8 | **86 / 97** | 12 of 12 |
| **Dense: large + 19,999** | B-2 | 2,509 / 2,641 | **4,714** | 2,038 / 2,262 | **2,038 / 2,262** | 12 of 12 |
| | **this branch** | 288.7 / 299.1 | **299** | 31.8 / 105.5 | **110 / 141** | 10 of 12 |

DPR 2, the two affected cases plus controls:

| Case | Renderer | Cold: longest task | Direct: longest task, median / worst | Direct tasks ≥ 50 ms |
|---|---|---:|---:|---:|
| Fixture | B-2 / this branch | 0 / 0 | 0 / 0 both | 0 / 0 of 12 |
| 500 XY points | B-2 / this branch | 0 / 84 | 0 / 0 both | 0 / 0 of 12 |
| One large part + 19,999 small | B-2 | 2,268 | 1,087 / 1,169 | 12 of 12 |
| | this branch | 302 | 69 / 101 | 11 of 12 |
| Dense: large + 19,999 | B-2 | 4,716 | 2,112 / 2,390 | 12 of 12 |
| | this branch | 448 | 129 / 210 | 11 of 12 |

**Reading:**
- **On the affected multi-ring cases**, a direct redraw drops from about **1.1–2.4 s** to **about 0.1 s** of main-thread work, and a cold load from **2.3–4.7 s** to **0.3–0.45 s**. This is the improvement expected from removing the `closePath()` cost.
- **The controls show no systematic change:** the 12-row fixture, the single 100,000-position ring and the 20,000 scattered parts, whose rings are mostly culled or simplified away at their views. Their redraw tasks are dominated by rasterization and Leaflet's projection, which E1 does not touch.
- **The XY control** never creates an outline, so the changed code does not run. Its cold calls vary between 38 and 85 ms in both renderers, run to run: base reached 53 ms in one DPR 1 run, and this branch 64 and 84 ms in two DPR 2 runs (`evidencia/medicion-dpr*.txt`).

**Newer browsers.** Only Chromium 141 is installed in this container; no Firefox, WebKit or other Chrome build is available, and none was installed. Whether newer Chrome builds already remove the `closePath()` cost is therefore **not measured here**. The supervisor's environment had Chrome 154, where this can be checked with `micro-cierre.mjs`. Where the cost is absent, this change should neither help nor harm: the drawing is byte-identical. Safari and Firefox were not tested (gap recorded).

### 3.5 Repository checks

Run at `496233e` (`evidencia/repo-checks.txt`). `./verificar.sh` needs zsh, which this container lacks, so its parts were run separately:

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests -t .` (Python 3.13.16) | 672 run, 29 Postgres-only skips, **1 failure**. It is the known environmental `test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`: this container's `/usr/bin/python3` ships openpyxl. |
| The same suite on Python 3.9.25 | Same: 672 run, 29 skips, the same single environmental failure |
| `node --test tests/js/*.test.mjs` | 120 pass |
| `ruff check server/ tests/ <this folder>`, `mypy server/` | Clean |
| Browser checks (§3.1–§3.4) | Local evidence on this machine; CI does not run them |
| GitHub CI | Reported on the draft PR |

## 4. Remaining responsiveness limitation

E1 removes the multi-second stalls and nothing else.
- On the adversarial and dense cases at their outline views, each redraw still holds the main thread for **about 70–140 ms at DPR 1, and up to 210 ms at DPR 2**. That is software rasterization of every visible ring plus Leaflet's projection.
- A cold load holds it for 0.25–0.45 s, which is the synchronous body preparation inside `render()`.
- **E1 does not meet the 50 ms target**, and it makes no absolute timing claim for any other machine.

What is left is the work PR #16 attributes to rasterization and synchronous preparation. Its remedy (E4 worker raster, or sliced preparation) is not authorized here.

## 5. Reproduce

From this branch, with `tests/e2e` dependencies installed (`cd tests/e2e && npm install`, which is `playwright-core` only):

```bash
W=$(mktemp -d)
git archive efc362818ba64618dbfc23556db8678cde525336 | (mkdir -p $W/b1 && tar -x -C $W/b1)
python3 -I reports/team-b-boundary-path-drawing-2026-10-08/generar_casos.py $W/b1 $W/casos   # 4 fictional limit cases
export CHROMIUM=/path/to/chrome
C="$W/casos/circulo-100k.json $W/casos/multiparte-20000.json $W/casos/grande-mas-19999.json $W/casos/denso-grande-mas-19999.json"
node reports/team-b-boundary-path-drawing-2026-10-08/micro-cierre.mjs
cd tests/e2e
node contornos.mjs                                        # B-2 checks (20)
node contornos-trazo.mjs $C                               # RGBA identity, DPR 1 and 2, fallbacks (252 + 7)
REPETICIONES=3 DPRS=1 node contornos-trazo-medicion.mjs $C
REPETICIONES=3 DPRS=2 node contornos-trazo-medicion.mjs $W/casos/grande-mas-19999.json $W/casos/denso-grande-mas-19999.json
```

The 2–4 MB case files are not committed. `$W/casos/manifest.json` must match `evidencia/casos-manifest.json`. CI does not run any of these browser checks.
