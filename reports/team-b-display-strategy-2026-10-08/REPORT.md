# Team B — large-KMZ display strategy (measured prototypes)

Team B · bounded investigation · October 8, 2026

| Item | Value |
|---|---|
| Instruction commit | `84b2b84a05592b9f31b860e831925990274b481b` on `codex/supervisor-completion-brief`: `reports/next-parallel-packets-2026-10-08/START_HERE.md` and `TEAM_B_DISPLAY.md`, read with `git show`. The checkout was not switched. |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`, fetched today and unchanged since the packet was issued. |
| Inputs, used from disposable `git archive` extractions only | B-2 renderer, PR #11 **`5d8e2dcc125a688dbba38a260d5d7eca88a6d223`**. B-1 parser, PR #9 **`efc362818ba64618dbfc23556db8678cde525336`** (archived `server/kmz.py` SHA-256 `92e3a9fa…bb94c3`, equal to PR #9's file). Leaflet 1.9.4: the vendored `web/vendor/leaflet.js` is byte-identical to npm's `leaflet@1.9.4` `dist/leaflet.js`, SHA-256 `db49d009…e5641a`. Its readable source was used for reading only. |
| Listed in the packet, not needed here | A-1 PR #14 `24073dc`, PR #12 `28bf0db`, B-3S PR #13 `c375a1d`. This investigation touches none of them. |
| Branch / PR | `claude/team-b/display-strategy` · separate draft PR |
| Measured prototype commit | **`45117497cf1abc3f1ede48e73a5adf2105a7c51d`**. Every measurement in §3–§5 ran at this commit. |
| Browser / machine | Headless Chromium **141.0.7390.37** (Playwright's build); software rasterization, no GPU. Intel Xeon @ 2.80 GHz, 4 cores, 15.7 GiB RAM, Linux 6.18. Node 22.22.0. |
| Scope | Everything lives in this folder. No application file, accepted B branch, Team A file, CI, deployment or real data changed. No service or credential was used. |

---

## 1. Answer in brief

**The bottleneck was not geometry volume or fetching. It was one browser call.** Leaflet's canvas renderer draws a polygon as one path and calls `ctx.closePath()` after every ring. In this Chromium, each `closePath()` costs time proportional to the subpaths already in the path. Building one 20,000-ring path therefore spends about **2 s in `closePath()` alone**, against **4 ms** when each ring is closed with `lineTo(first point)` (§2.2). That single cost is the 1.5–3.3 s per view change that B-2 recorded.

Removing it leaves two real costs:
1. **Synchronous preparation of a 100k-position body inside `render()`.** B-2 validates the body, converts it to `[lat, lng]`, and Leaflet then creates 100k `LatLng` objects and projects them. Done in one go, that is a main-thread task of up to about 0.4 s on a cold load (E2, which prepares synchronously: 300–385 ms).
2. **Software rasterization of every visible ring on each redraw.** It costs about 120–140 ms for 20,000 stroked rings in Leaflet's round-join style (§2.3). Viewport culling cannot remove it when the whole body is on screen, which is exactly the adversarial case at its outline zoom.

**Recommended strategy: E4.** It combines approaches (a) and (b) of the packet:
- Validated bodies are prepared once into exact projected coordinates in typed arrays, in cancellable slices of 8 ms or less.
- They are cached by immutable geometry ID within a byte budget.
- Off-screen parts are culled.
- When the visible geometry is heavy, the exact outline is rasterized in a **Web Worker** (`OffscreenCanvas`), with an explicit, located "pending" state until the bitmap for the current zoom is painted.

On the recorded machine, E4 had **no main-thread task of 50 ms or more** in any measured case or action: cold load, repeated real drags and wheel zooms, direct redraws, selection, rapid cancellation and teardown. Input to next paint stayed at **32 ms or less**, and the exact outline always completed (§3).

**Smallest safe first step: E1.** It changes only how rings are closed. Its output is **pixel-identical to B-2 in every case and zoom measured** (identical SHA-256 of the canvas). It cuts the longest view-change task from 1,177 ms to 123 ms on the adversarial case and from 2,300 ms to 181 ms on the dense case. It still leaves tasks of 120–330 ms, so E1 alone does **not** meet the 50 ms target.

| | Accepted B-2 | E1 | E4 (recommended) |
|---|---:|---:|---:|
| One large part + 19,999 small: longest task, repeated views | 1,177 ms | 123 ms | **0** |
| Same: longest task, cold load | 2,433 ms | 185 ms | **0** |
| Dense all-visible: longest task, repeated views | 2,300 ms | 181 ms | **0** |
| Same: longest task, cold load | 4,423 ms | 334 ms | **0** |
| Worst input→paint, all cases | 1,608 ms | 184 ms | **32 ms** |
| Painted output | — | identical to B-2 | exact positions (§3.3) |

0 means no task of 50 ms or more.

---

## 2. Where the time goes (question 1)

### 2.1 Profile of the accepted renderer

The CPU profile (`Profiler`, 100 µs sampling) covers a non-animated 200 px pan plus a one-level zoom at the outline view of "one large part + 19,999 small" (`perfil` in §9):

| Self time | Function |
|---:|---|
| **1,854 ms** | `closePath` (native canvas) |
| 260 ms | `(program)`: native, mostly rasterization |
| 30 ms | Leaflet `_projectLatlngs` |
| 20 ms | Leaflet `latLngToPoint` |
| 11 ms | Leaflet `_updatePoly` |
| < 6 ms each | clipping, simplification, `moveTo` / `lineTo` |

Projection, clipping and Leaflet's own JavaScript total under 100 ms. Data transfer is not involved at all: the bodies were already in memory. **Fetching or chunking geometry cannot fix this.**

### 2.2 `closePath()` cost grows with the subpaths in the path (`micro.mjs`)

Time to build one path of N small closed squares, best of 3, Chromium 141. Paint is excluded:

| Subpaths | ctx `closePath` | ctx `lineTo(first)` | `Path2D` `closePath` | `Path2D` `lineTo(first)` |
|---:|---:|---:|---:|---:|
| 1,000 | 5.4 ms | 0.3 ms | 5.5 ms | 0.4 ms |
| 2,000 | 21.6 ms | 0.4 ms | 23.5 ms | 0.5 ms |
| 5,000 | 140.0 ms | 1.3 ms | 147.3 ms | 1.3 ms |
| 10,000 | 518.4 ms | 3.7 ms | 528.3 ms | 4.9 ms |
| 20,000 | **2,027.2 ms** | **4.0 ms** | 2,075.6 ms | 5.4 ms |

Doubling the subpaths roughly quadruples the `closePath` time, so it is quadratic overall. `Path2D` behaves the same. Closing a ring with `lineTo(first)` is equivalent for the fill, which closes subpaths implicitly, and with Leaflet's round caps and joins it gives the same stroke. E1 proves that by pixel identity (§3.3). Firefox and Safari were **not** measured; whether they share this cost is unknown.

### 2.3 What remains: rasterizing visible rings (`micro.mjs`)

Building and painting 20,000 rings in one path with a 2 px stroke, forced with a 1×1 `getImageData`, best of 3:

| Ring size | Fill only | Stroke, round (Leaflet) | Stroke, miter | Fill + stroke, round (Leaflet) | Fill + stroke, miter |
|---|---:|---:|---:|---:|---:|
| 0.6 px | 13.6 ms | 121.7 ms | 65.6 ms | **140.8 ms** | 75.6 ms |
| 3 px | 18.0 ms | 122.1 ms | 65.6 ms | **135.0 ms** | 75.1 ms |
| 8 px | 20.8 ms | 123.4 ms | 66.2 ms | **135.7 ms** | 87.2 ms |

On this machine the stroke dominates. Even miter joins (a visible style change) stay above 50 ms. Off-screen culling helps only when parts are off screen; at the outline zoom of the adversarial and dense cases, every part is on screen.

### 2.4 Cold work, hit testing and selection

- **Cold (first render of a body).** B-2 validates, converts and builds the `L.polygon` synchronously inside `render()`, then draws. The final measurements in §3 put that single task at 0 ms for the small cases, and at up to 2.4 s and 4.4 s for the adversarial and dense cases, where the cold task also contains the `closePath` redraw.
  - Validation and conversion alone (B-2's `cuerpoLeaflet`) take 16–62 ms in Node.
  - Prepared-array preparation in the browser takes about 100–150 ms of work in total. E3 and E4 run it in slices of 8 ms or less, so the main thread is never held for that long.
- **Hit testing.** Leaflet tests every interactive layer on each mouse move or click. For a 20,000-part body, the prototype checks each visible part's box and then runs even-odd and stroke-distance tests only on the candidates. This is a few milliseconds and showed no long task in the selection runs (§3).
- **Selection.** Selecting restyles the outline, which in Leaflet is a full canvas redraw, so in B-2 and E1 selection costs as much as a view change. E4 rasterizes the normal and selected styles together in the worker, so selecting just swaps bitmaps.

---

## 3. Approaches compared (question 2)

Five renderers were measured on the same page and rows, all derived from or equal to the accepted code:

| ID | What changes against accepted B-2 | Packet approach |
|---|---|---|
| **b2** | Nothing: the accepted renderer from `git archive 5d8e2dc` | baseline |
| **E1** | Only boundary rings are closed with `lineTo(first)` instead of `closePath()` (an `L.Polygon` subclass) | bottleneck fix |
| **E2** | Body prepared once (exact projected typed arrays and part boxes), cached by geometry ID, off-screen parts culled, drawn by a custom layer on the shared canvas. Preparation is synchronous. | (a) |
| **E3** | E2, with preparation in cancellable slices of 8 ms or less and an explicit "preparando" state | (a) + (b) |
| **E4** | E3, plus heavy views (> 2,000 visible rings or > 20,000 visible positions) rasterized exactly in a Web Worker, with an explicit "dibujando" state | (a) + (b) + off-thread raster |

**Method.** Each case and renderer runs in a fresh page, 3 times (`banco.mjs`). Input is real pointer input: Playwright's `page.mouse` drags and wheel steps on the map.
- Each run covers:
  - a cold load to the painted outline at outline scale;
  - 6 real drags and 4 real wheel zooms;
  - 4 direct (non-animated) redraws, as B-2 measured;
  - real clicks on the interior point and on a small part;
  - 4 renders one frame apart ending in a reset (rapid cancellation);
  - teardown while a body may still be preparing.
- **Long tasks** come from the Long Tasks API: any task of 50 ms or more, with its duration.
- **Input to paint** comes from the Event Timing API: input timestamp to the next paint, for discrete events.
- **Frame gaps** come from `requestAnimationFrame`.
- **Wall-clock times** of views include Leaflet's own zoom and inertia animations (about 250–650 ms), which are identical for all renderers.
- **Paint evidence** waits two frames and rejects blank canvases (B-2's corrected method).

### 3.1 Results

Median / worst over 3 runs. View actions: 14 per run (6 real drags, 4 real wheel steps, 4 direct redraws), 42 in total per row. **Task** = longest main-thread task in that phase (Long Tasks API; 0 = none of 50 ms or more). **Input→paint** = worst Event Timing duration, input to next paint.

| Case | Renderer | Cold: outline painted (ms) | Cold: first frame (ms) | Cold: longest task | Views: wall clock (ms) | Views: longest task / count of 50 ms or more | Exact outline complete after input (ms) | Input→paint, worst | Selection correct / longest task | Cancellation: longest task / clean | Teardown clean |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| B-2 fixture, 12 rows (control) | b2 | 98 / 98 | 32 / 33 | 0 | 414 / 693 | 0 / 0 | 410 / 688 | 32 | yes / 0 | 143 / yes | yes |
| B-2 fixture, 12 rows (control) | E1 | 97 / 129 | 30 / 30 | 0 | 414 / 677 | 0 / 0 | 409 / 671 | 32 | yes / 0 | 144 / yes | yes |
| B-2 fixture, 12 rows (control) | E2 | 98 / 98 | 32 / 32 | 0 | 414 / 700 | 0 / 0 | 409 / 681 | 24 | yes / 0 | 73 / yes | yes |
| B-2 fixture, 12 rows (control) | E3 | 122 / 130 | 22 / 31 | 0 | 414 / 678 | 0 / 0 | 410 / 674 | 32 | yes / 0 | 0 / yes | yes |
| B-2 fixture, 12 rows (control) | E4 | 127 / 131 | 30 / 31 | 0 | 415 / 682 | 0 / 0 | 411 / 678 | 32 | yes / 0 | 0 / yes | yes |
| 500 XY points (control) | b2 | 110 / 125 | 50 / 63 | 0 | 414 / 704 | 0 / 0 | 409 / 698 | 32 | yes / 0 | 133 / yes | yes |
| 500 XY points (control) | E1 | 109 / 109 | 49 / 50 | 0 | 411 / 679 | 0 / 0 | 406 / 674 | 32 | yes / 0 | 109 / yes | yes |
| 500 XY points (control) | E2 | 109 / 138 | 57 / 74 | 0 | 415 / 680 | 0 / 0 | 411 / 674 | 24 | yes / 0 | 0 / yes | yes |
| 500 XY points (control) | E3 | 110 / 124 | 50 / 65 | 0 | 414 / 686 | 0 / 0 | 409 / 681 | 32 | yes / 0 | 0 / yes | yes |
| 500 XY points (control) | E4 | 109 / 122 | 50 / 56 | 0 | 414 / 714 | 0 / 0 | 409 / 708 | 32 | yes / 0 | 0 / yes | yes |
| One ring, 100,000 positions | b2 | 313 / 345 | 263 / 279 | 0 | 431 / 672 | 53 / 4 | 426 / 666 | 32 | yes / 0 | 106 / yes | yes |
| One ring, 100,000 positions | E1 | 318 / 350 | 258 / 294 | 0 | 431 / 687 | 65 / 5 | 426 / 680 | 32 | yes / 0 | 105 / yes | yes |
| One ring, 100,000 positions | E2 | 369 / 410 | 308 / 356 | 300 | 580 / 1,031 | 357 / 39 | 576 / 1,027 | 152 | yes / 136 | 159 / yes | yes |
| One ring, 100,000 positions | E3 | 336 / 340 | 23 / 30 | 139 | 583 / 799 | 278 / 39 | 578 / 796 | 160 | yes / 148 | 157 / yes | yes |
| One ring, 100,000 positions | E4 | 438 / 444 | 28 / 30 | 0 | 646 / 832 | 0 / 0 | 641 / 825 | 24 | yes / 0 | 0 / yes | yes |
| 20,000 scattered parts | b2 | 292 / 370 | 232 / 315 | 0 | 415 / 680 | 0 / 0 | 410 / 674 | 24 | yes / 0 | 161 / yes | yes |
| 20,000 scattered parts | E1 | 316 / 317 | 253 / 253 | 0 | 416 / 682 | 51 / 1 | 411 / 677 | 32 | yes / 0 | 145 / yes | yes |
| 20,000 scattered parts | E2 | 129 / 137 | 75 / 76 | 0 | 414 / 699 | 0 / 0 | 410 / 694 | 32 | yes / 0 | 0 / yes | yes |
| 20,000 scattered parts | E3 | 154 / 171 | 30 / 33 | 0 | 414 / 680 | 0 / 0 | 410 / 674 | 32 | yes / 0 | 0 / yes | yes |
| 20,000 scattered parts | E4 | 150 / 151 | 33 / 35 | 0 | 415 / 699 | 0 / 0 | 409 / 694 | 24 | yes / 0 | 0 / yes | yes |
| **One large part + 19,999 small** | b2 | 3,619 / 4,044 | 3,558 / 3,986 | 2,433 | 961 / 1,819 | 1,177 / 28 | 954 / 1,812 | 1,016 | yes / 999 | 939 / yes | yes |
| **One large part + 19,999 small** | E1 | 519 / 622 | 469 / 558 | 185 | 450 / 753 | 123 / 21 | 445 / 749 | 152 | yes / 135 | 110 / yes | yes |
| **One large part + 19,999 small** | E2 | 468 / 519 | 415 / 453 | 385 | 497 / 855 | 230 / 24 | 492 / 849 | 232 | yes / 223 | 196 / yes | yes |
| **One large part + 19,999 small** | E3 | 464 / 479 | 33 / 35 | 193 | 493 / 847 | 213 / 24 | 488 / 842 | 240 | yes / 228 | 259 / yes | yes |
| **One large part + 19,999 small** | E4 | 548 / 602 | 28 / 38 | 0 | 415 / 673 | 0 / 0 | 411 / 667 | 24 | yes / 0 | 0 / yes | yes |
| **Dense: large + 19,999, all visible** | b2 | 6,828 / 7,068 | 6,771 / 7,007 | 4,423 | 1,332 / 2,957 | 2,300 / 27 | 1,329 / 2,951 | 1,608 | yes / 1,588 | 1,523 / yes | yes |
| **Dense: large + 19,999, all visible** | E1 | 664 / 737 | 608 / 678 | 334 | 498 / 825 | 181 / 26 | 493 / 820 | 184 | yes / 174 | 140 / yes | yes |
| **Dense: large + 19,999, all visible** | E2 | 436 / 476 | 377 / 422 | 366 | 482 / 848 | 212 / 23 | 478 / 845 | 200 | yes / 191 | 201 / yes | yes |
| **Dense: large + 19,999, all visible** | E3 | 466 / 508 | 28 / 33 | 236 | 497 / 981 | 266 / 25 | 493 / 977 | 216 | yes / 195 | 199 / yes | yes |
| **Dense: large + 19,999, all visible** | E4 | 540 / 550 | 25 / 32 | 0 | 414 / 682 | 0 / 0 | 412 / 677 | 24 | yes / 0 | 0 / yes | yes |

**Reading the table:**
- **B-2 on the adversarial and dense cases:**
  - cold loads take 3.6–7.1 s, with one task of 2.4 s or 4.4 s;
  - view changes hold the main thread for up to 1.2 s and 2.3 s, with 27–28 long tasks over the 42 actions;
  - a click waits up to 1.6 s for its paint.
- **E1:** removes the multi-second stalls with pixel-identical output (§3.3), but keeps tasks of 120–330 ms on the 20,000-ring cases.
- **E2 and E3 trade results across cases.**
  - They fix the cold path: E3's first frame comes at 23–35 ms because preparation is sliced. E2 is fast on scattered parts.
  - They are **worse than B-2 on the single 100k ring** (tasks of 280–360 ms): they stroke all 100,000 exact positions on the main thread, where Leaflet's 1 px screen smoothing paints far fewer.
  - They still pay the full rasterization when every part is visible.
- **E4:** **no task of 50 ms or more in any phase of any case**, input to next paint at most 32 ms in every case, correct selection, clean cancellation and teardown, and the exact outline always completes.
  - The price is latency, not blocking. After a zoom on a heavy body, the outline appears when the worker's bitmap arrives. "Exact outline complete" has medians of 409–641 ms, which include Leaflet's own animation, the same for every renderer.
  - In the meantime the located "Dibujando contorno…" symbol shows (§4).
- **Wall-clock view times** (median about 415 ms) are dominated by Leaflet's zoom and inertia animations, identical in every renderer.

### 3.2 When every part is visible

The adversarial case at its outline zoom, and the dense case (the same counts packed into about 20 × 17 km) at the outline zoom and two levels deeper, keep nearly all 20,000 parts on screen. Culling removes nothing there, and E2 and E3 draw every visible ring on the main thread, costing 160–320 ms per redraw (above). E4 moves exactly that work, the rasterization of the visible exact geometry, off the main thread. The main thread then only:
- recomputes which parts are visible (20,000 box tests, under 1 ms);
- posts a request when the zoom changes or the view leaves the rasterized area (the view plus half its size on every side);
- draws one bitmap per redraw.

Pans inside that area are blits. A new zoom shows the interior-point symbol in the "Dibujando contorno…" state until its bitmap arrives, measured in §3.1.

### 3.3 Paint fidelity against the accepted renderer

Captured after two frames, with blank canvases rejected (`comparar-pintura.mjs`, output in `evidencia/comparar-pintura.txt`). Views are the outline zoom and 2 and 4 levels deeper, centred on the body's last small part. The comparison also covers the overview and detail captures of every benchmark case (`banco.json` → `comparacionPintura`).

| Renderer | Against B-2 |
|---|---|
| **E1** | **Identical SHA-256 of the canvas in every case and every zoom**: 12 comparisons here plus the 12 overview and detail comparisons in `banco.json`. That includes the XY control, the 12-row fixture and all four limit cases. |
| **E4** | XY control: identical. Every boundary case: **100% of B-2's painted pixels lie within 1 px of an E4 painted pixel**, so nothing B-2 draws is missing. 92–100% of E4's painted pixels lie within 1 px of B-2's (95–100% within 2 px). Overlap of painted pixels is 0.97–1.0 for the ring and the scattered parts, and lower (0.50–0.88) where 20,000 tiny parts are 1–4 px wide. |

**Why E4 is not pixel-identical.** It draws the stored positions as they are, at sub-pixel precision. Leaflet, and therefore B-2 and E1, rounds every vertex to a whole pixel and simplifies each ring on screen at 1 px. For a 100 m square that is 0.7–3 px wide, B-2 paints a whole-pixel box (often hollow), while E4 paints the exact square, which with the 2 px stroke and anti-aliasing reads as a slightly fuller dot.

The crops `evidencia/detalle-z12-grande-b2.png` and `…-e4.png` show the same parts in the same places, with nothing missing or added. E4 is therefore a more literal drawing of the same geometry, not a coarser one. If the owner prefers B-2's look exactly, E4 can round to whole pixels, but Leaflet's 1 px smoothing should not be reintroduced into the exact raster without review.

---

## 4. What the employee sees while an outline is not drawn (question 3)

All states keep the terrain located at the accepted `punto_interior`. A boundary never moves to unrelated X/Y and is never drawn partially. Selection is kept across every transition: the prototype checks show the selected (black) outline painted after "preparando" → "listo".

| State (`posicionDe().estadoContorno`, `onContornoEstado`) | When | Mark on the map | Tooltip line (exact Spanish) | `zoomToScale` | Clickable as |
|---|---|---|---|---|---|
| `cargando` | The caller (A's loader) is still fetching the body: ID in the new `options.cargando` set | Symbol at the interior point, hollow, **dotted** (`1 4`) | **Cargando contorno…** | `contorno_pendiente` (`motivo: "cargando"`) | Symbol |
| `preparando` | The body is here; validation and conversion run in ≤ 8 ms slices | Same dotted symbol | **Preparando contorno…** | `contorno_pendiente` (`motivo: "preparando"`) | Symbol |
| `dibujando` (E4) | The outline is at scale but its bitmap for this zoom is not back from the worker | Dotted symbol over the area; **no outline pixels, no outline hit-testing** | **Dibujando contorno…** | `contorno_pendiente` (`motivo: "dibujando"`) | Symbol |
| `listo` | Outline painted (or symbol at distant zoom, as in B-2) | B-2's outline or solid symbol | — (B-2's tooltip) | B-2's `a_escala` / `limite_de_zoom` | Outline and symbol, as B-2 |
| `no_disponible` | Active descriptor, no body (absent from the map, not loading) | B-2's hollow **dashed** symbol (`3 3`), unchanged | **Contorno no disponible** (unchanged) | `contorno_no_disponible` (unchanged) | Symbol |
| `invalido` | Body failed B-2's validation (malformed, inconsistent with its bbox, over the limit) | Same dashed symbol | **Contorno no válido** (new, distinguishes it from missing) | `contorno_no_disponible` (unchanged) | Symbol |

Dotted means "in progress" and dashed means "not available". Both remain distinct from the solid symbol of a loaded outline. The look and wording are proposals for the owner and Team A to confirm.

**Additive interface needs.** Each is optional, so existing XY-only callers and B-2 callers keep their behaviour:

1. `createMapCanvas(…, { onContornoEstado(id, estado) })`: an optional callback on each state change. A can show a toast, for example for `zoomToScale` → `contorno_pendiente`. In the prototype, E4 can report `listo` and then `dibujando` within one task when preparation completes at a heavy view. The implementation should coalesce transitions inside one task before calling it.
2. `render(filas, { …, cargando: Set<geometryId> })`: bodies A is still fetching, which show "Cargando contorno…" instead of "Contorno no disponible".
3. `zoomToScale` gains the state `contorno_pendiente` with `motivo`. It is never reported as `a_escala` while preparing or drawing. B-2's `contorno_no_disponible` is unchanged.
4. `posicionDe(id)` gains `estadoContorno`. Its `contorno` is `true` only when the outline is actually painted.
5. `destruir()`: teardown. It cancels preparation, terminates the worker, drops cached bodies and removes the map.
6. `onScaleChange`'s `contornosAEscala` counts only painted outlines.

The frozen part of the interface is unchanged: `render(terrenos, {colorFor, dashFor, geometrias})`, the `Map` of bodies keyed by geometry ID, and the existing methods and result codes.

---

## 5. Cache, memory, cancellation and cleanup (question 4)

| Concern | Design (prototype `planificador.js`, `raster.js`, `capa.js`) | Evidence |
|---|---|---|
| Cache key | Immutable geometry ID (contract §4). The entry also stores the descriptor `bbox`, and a lookup with a different bbox misses (re-prepared, never trusted). | Node test "cache: … checked against the descriptor bbox" |
| What is cached | The prepared body only: `Float64Array` x/y world coordinates (16 B per position), ring and part offsets, and part boxes. About 1.0 MB for a 60k-position body, about 1.6 MB at the 100k limit. No `LatLng` objects and no nested arrays. | `bytesDe()` byte accounting |
| Bound | LRU by bytes, default **32 MiB** (about 2M positions). A body larger than the budget is never cached. | Node test (eviction at 2.5 bodies) · browser visits below |
| Invalidation | IDs are immutable, so a replaced layout is a **new descriptor ID** and the old entry ages out by LRU. `render([])`, the session/scope reset path, **empties the cache** and the worker's copies. | Visits run: cache 0 B after reset |
| Generation cancellation | Each `render()` increments a generation. Preparation jobs whose ID no longer appears in the latest render are cancelled, and a result delivered to an older generation is dropped. Jobs for IDs still needed continue, because a filter change that keeps a terrain does not restart its work. Worker replies for superseded requests are discarded and their bitmaps closed. | Behaviour check "a newer render cancels older preparation; no late outline"; bench "cancelación limpia" |
| Viewport changes | They never cancel preparation (it is view-independent). In E4, a newer view supersedes an in-flight raster request whose area no longer covers it. | `CapaContornoRaster._update` |
| Teardown | New `destruir()`: stops the planner (refusing new work), empties the cache, terminates the worker and removes the map. | Bench "desmontaje limpio": no pending job, no page error |
| Cold work | Counted in the budget: preparation is sliced at 8 ms or less, interleaved with input and painting. The longest slice observed in the node planner test was under 30 ms (ceiling asserted), and no long task appeared in E3/E4 cold loads (§3). | §3, node test |
| Worker bitmaps (E4) | Two bitmaps (normal and selected style) per heavy layer, each covering about 2× the renderer bounds in each dimension: at 1,200 × 640 that is 2,880 × 1,536 × 4 B ≈ **17.7 MB each, 35 MB per heavy outline**. This is an estimate from dimensions, not measured; external memory is not visible in the JS heap metric. Released on zoom change, layer removal and teardown. | Code; see §7 for the recommended reduction |

**Many visits** (`banco.mjs`, `visitas`): 45 distinct fictional bodies of 60,000 positions each, rendered one after another with each outline drawn at scale, then the reset `render([])`:

| Renderer | Bodies visited | Cache peak (bytes / entries) | Cache after reset | JS heap after GC, MiB (after visits → after reset) | Long tasks during visits / longest |
|---|---:|---|---|---|---|
| b2 | 45 | — | — | 8.9 → 2.1 | 11 / 101 ms |
| E1 | 45 | — | 0 B | 8.9 → 2.1 | 22 / 98 ms |
| E2 | 45 | 31.1 MiB / 34 | 0 B | 2.2 → 2.1 | 58 / 107 ms |
| E3 | 45 | 31.1 MiB / 34 | 0 B | 2.2 → 2.2 | 12 / 162 ms |
| E4 | 45 | 31.1 MiB / 34 | 0 B | 2.3 → 2.2 | 0 / 0 ms |

The cache stays at its 32 MiB budget (31.1 MiB, 34 of 45 bodies) while the oldest bodies are evicted, and it is emptied by the reset. The JS heap does not grow, because the prepared bodies are typed arrays held outside the JS heap. Their 31 MiB is the exact `byteLength` total.

E4 is the only renderer with no long task over the 45 visits. B-2 and E1 rebuild every body synchronously, and E2 and E3 stroke each 60k-position ring on the main thread.

---

## 6. Invariants (packet) — how each prototype treats them

| Invariant | E1 | E4 |
|---|---|---|
| Exact stored geometry and B-1 validation unchanged | Same `cuerpoLeaflet` and Leaflet pipeline as B-2 | Its own validator gives **the same verdict as `cuerpoLeaflet` on 183 bodies** (fixtures, the four limit cases, targeted mutations including F1's shifted and collapsed bodies, the 100,001-position limit, tolerance edges). Positions are kept in order, unrounded; nothing is simplified or dropped. |
| Active usable geometry keeps priority; never jumps to unrelated X/Y | As B-2 | Pending states stay at the accepted interior point (§4) |
| Every part maps to the original terrain ID; selection agrees with paint | As B-2 | Clicks on each multipart part select the same ID, and a hole selects nothing. While "dibujando", the outline is not hit-testable; only the symbol is. |
| No false completion | As B-2 | `posicionDe().contorno`, `contornosAEscala` and `zoomToScale` report an outline only when it is painted (`contorno_pendiente` otherwise) |
| Culling omits only off-screen parts | Leaflet's own clipping, as B-2 | A part is skipped only if its box is wholly outside the renderer bounds plus the stroke tolerance |
| Coarser visible representation only if explicit | As B-2: Leaflet's existing whole-pixel rounding and 1 px screen smoothing | None: sub-pixel parts are drawn at their exact positions (§3.3) |
| XY-only behaviour compatible | Pixel-identical | Pixel-identical (`xy` control, §3.3) |

---

## 7. Recommended implementation plan

**Step 1 — E1, small and immediately safe.**
- A two-function change in B-owned `web/components/map/MapCanvas.js`: an `L.Polygon` subclass used only for boundary outlines. It overrides `_updatePath` to close rings with `lineTo(first)`.
- Regression tests:
  - the existing B-2 browser checks;
  - a pixel-identity check against `closePath` drawing on the fixture and the limit cases (this report's `comparar-pintura.mjs`);
  - a timing guard on the 20,000-ring case: the redraw task must be well under the old 1 s.
- It removes the multi-second stalls with no visible change. It does not meet the 50 ms target alone.

**Step 2 — E4 renderer packet.**

Proposed B-owned files, production versions of this prototype:

| File | Content |
|---|---|
| `web/lib/geometria-preparada.js` | Resumable validation and preparation (same verdicts as `cuerpoLeaflet`, which stays the reference), world projection, byte accounting |
| `web/lib/planificador-contornos.js` | Cooperative scheduler with cancellation, and the byte-bounded LRU cache |
| `web/components/map/capa-contorno.js` | Leaflet layer for prepared bodies: culling, exact drawing, hit testing |
| `web/components/map/raster-contornos.js` | Worker client |
| `web/components/map/raster-contornos.worker.js` | Module worker |
| `web/components/map/MapCanvas.js` | Wiring and states |

The changes to `MapCanvas.js` are additive only; §4 lists them.

**Team A integration needs.** All are optional and additive:
- pass `cargando` while bodies are being fetched;
- subscribe to `onContornoEstado` for toasts;
- treat `zoomToScale` → `contorno_pendiente`;
- call `destruir()` on teardown.

Nothing in the frozen `render(terrenos, {colorFor, dashFor, geometrias})` contract changes.

**Regression tests for step 2:**
- **Node:** verdict equivalence with `cuerpoLeaflet` (`pruebas/prototipo.test.mjs`); sliced preparation equals one-shot; cancellation; LRU bound.
- **Browser:** this folder's `comprobaciones.mjs` (holes, multipart, every state's wording and `zoomToScale` result, selection kept across preparation, no stale outline, E4 drawing state); the B-2 checks; the paint comparison against `closePath` drawing.
- **Performance guard:** `banco.mjs` run as a non-CI benchmark with "no long task of 50 ms or more" on the limit cases.

**Changes recommended over the prototype:**
1. **Coalesce state callbacks.** In the prototype, E4 can emit `listo` then `dibujando` within one task when preparation finishes at a heavy view; the final code should emit one callback per state change actually reached.
2. **Reduce worker bitmap memory.** For example: pad the raster area by 25% instead of 50% per side, rasterize the selected style only for the selected terrain, and stop rasterizing for heavy layers that are not visible. Measure GPU and external memory.
3. **Make the thresholds configurable.** The heavy-view thresholds (2,000 rings, 20,000 positions) are measured on this machine. Keep them as constants with this report's measurement as their source, and re-measure on the target employee hardware.
4. **Keep a direct-drawing fallback.** Where `OffscreenCanvas` 2D in workers is unavailable, fall back to E3's direct drawing and show the "dibujando" state for heavy views until drawn, never a partial outline. Browser support for module workers with `OffscreenCanvas` should be confirmed for the supported browsers (Safari was not tested here).

**Decisions needed before step 2, with proposed defaults:**

| Decision | Proposed default | Blocks |
|---|---|---|
| Pending look and Spanish wording (§4) | Dotted symbol; "Cargando / Preparando / Dibujando contorno…", "Contorno no válido" | Final UI copy in step 2 |
| Accept off-main-thread raster (adds a module worker and about 35 MB of bitmap memory per heavy outline at default padding, to be reduced) | Accept | Step 2 architecture. Without it, the remaining choice is the B-2 report's product option: keep the symbol and show a notice above a visible-ring threshold. |
| Ship E1 first as its own small PR | Yes | Nothing; independent of step 2 |

---

## 8. Limitations

- **One browser.** All figures come from one headless Chromium 141 with **software rasterization** on this container. GPU-accelerated canvas on employee machines may rasterize much faster or differently, and whether `closePath` is quadratic in Firefox, Safari or newer Chrome was **not** measured. These are investigation targets on the recorded machine, not device guarantees.
- **Test conditions not covered:** device pixel ratio 1 only (retina doubles raster work and bitmap memory), desktop pointer only (no touch), no basemap tiles (offline page).
- **Fictional geometry.** Real company KMZ files remain untested.
- **Memory.** Typed-array and bitmap memory is external to the JS heap, so the heap figures understate it. Cache bytes are exact accounting; bitmap memory is computed from dimensions.
- **E4's deliberate latency.** E4 has no long tasks, but the exact outline appears only when the worker's bitmap arrives (§3.1, "outline complete"). Until then the explicit pending state shows.
- **Equal animation share in wall-clock times.** View wall-clock times include Leaflet animations and inertia, which are identical across renderers.

---

## 9. Reproduce

From the repository root at this branch's head, with `tests/e2e` dependencies installed (`cd tests/e2e && npm install`, as for B-2):

```bash
D=reports/team-b-display-strategy-2026-10-08
W=$(mktemp -d)                                   # disposable working directory
git archive 5d8e2dcc125a688dbba38a260d5d7eca88a6d223 | (mkdir -p $W/b2 && tar -x -C $W/b2)
git archive efc362818ba64618dbfc23556db8678cde525336 | (mkdir -p $W/b1 && tar -x -C $W/b1)
python3 -I $D/generar_casos.py $W/b1 $W/casos     # 4 fictional limit cases + manifest.json
export B2_DIR=$W/b2 CASOS_DIR=$W/casos CHROMIUM=/path/to/chrome
python3 -I $D/prototipo/derivar.py $W/b2          # regenerates prototipo/MapCanvas.js (+ .diff)
node --test $D/pruebas/prototipo.test.mjs         # verdict equivalence, slicing, cancellation, cache
node $D/micro.mjs                                 # §2.2–2.3
REPETICIONES=3 EVIDENCIA=$W/ev node $D/banco.mjs  # §3, §5 (about 40 min)
node $D/comparar-pintura.mjs e1,e4                # §3.3
node $D/comprobaciones.mjs e4                     # behaviour checks (also: e3)
```

`generar_casos.py` is deterministic. `$W/casos/manifest.json` must show the SHA-256 values below. The 2–3 MB case files are not committed.

| Case | Parts | Positions | JSON SHA-256 |
|---|---:|---:|---|
| `circulo-100k` | 1 | 100,000 | `20601c3f…62d0c01b` |
| `multiparte-20000` | 20,000 | 100,000 | `4d470b4f…3098d260` |
| `grande-mas-19999` | 20,000 | 100,000 | `fb58322f…62e04c36` |
| `denso-grande-mas-19999` | 20,000 | 100,000 | `b6e312b8…22b3fc` |

Plus the B-2 12-row fixture (`fixture`, normal-size control) and 500 XY points (`xy`, XY-only control).

**Files in this folder:**
- `generar_casos.py`: the case generator.
- `servidor.mjs`, `banco.html`: local static server and benchmark page.
- `banco.mjs`, `comparar-pintura.mjs`, `comprobaciones.mjs`, `micro.mjs`: measurement drivers.
- `pruebas/`: node checks.
- `prototipo/`: `preparar.js`, `planificador.js`, `capa.js`, `raster.js`, `trabajador-raster.js`, plus `MapCanvas.js` derived from the accepted file by `derivar.py`, with its replayable patch `MapCanvas.diff`.
- `evidencia/`: raw outputs, `banco.json` and screenshots.

None of this is imported by the application.

## 10. Repository verification at this branch

Run on the branch head before pushing. The branch adds only files under this report folder.

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests -t .` (3.13 and 3.9.25) | 672 run, 29 Postgres-only skips. 1 failure: the environmental `test_packaging…no_openpyxl_of_its_own`, because this container's `/usr/bin/python3` ships openpyxl. It was disclosed before and did not reproduce on the supervisor's macOS. |
| `node --test tests/js/*.test.mjs` | 98 pass |
| `ruff check server/ tests/ <this folder>`, `mypy server/` | Clean |
| `./verificar.sh` | Not runnable here (no `zsh`); its components were run as above |
| Prototype checks (`pruebas/`, `comprobaciones.mjs`) | 6/6 node checks; behaviour checks 21/21 for E4 in 10 of 10 runs and 17/17 for E3 in 5 of 5 runs (`evidencia/comprobaciones-repeticiones.txt`) |
| GitHub CI | Reported on the draft PR |

Browser measurements are separate evidence from CI. CI does not run anything in this folder.
