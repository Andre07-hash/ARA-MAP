# B-2 review — boundary renderer

## Decision and context

The implementation is a sound renderer foundation with two corrections required before acceptance. Review applies to PR [#11](https://github.com/Andre07-hash/ARA-MAP/pull/11) head `db0b679b0a30507a4458c0b9440e5b0168b1cc30`, against application baseline `09452fd26d38319567dce28a89db100ea61c739a` and the approved B-2 packet at instruction commit `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`.

The PR stays inside B's scope. It preserves the existing factory/callbacks, keeps raw X/Y unchanged, renders holes and multipart layouts, distinguishes missing bodies, clears filtered selections and documents A's later integration work. No app shell, database, auth, storage or CI implementation was introduced.

## F1 — P2: validate actual coordinates against declared geometry bounds

Location: [`web/lib/geometria.js`, lines 124–169](https://github.com/Andre07-hash/ARA-MAP/blob/db0b679b0a30507a4458c0b9440e5b0168b1cc30/web/lib/geometria.js#L124).

`cuerpoLeaflet` compares the body's declared bbox with the descriptor's bbox, but never checks that the vertex coordinates agree with those bounds. A body with valid numeric, closed rings at a completely different location is returned as `cargado`. The map then removes the descriptor's symbol, draws the outline elsewhere, and reports `a_escala` while framing the descriptor's original location. This violates the packet's requirement that malformed render input not be presented as a validated footprint.

**Reproduced independently:** copy the fictional `t-simple` body, add 2 to every longitude, and leave both bbox metadata and descriptor unchanged. The helper returns `cargado`. In the real renderer, `zoomToScale` returns `a_escala` at zoom 17, centered on `[20.6015, -100.398]`, while the first outline vertex is `[-98.4, 20.6]`. The location helper reports an outline at the old interior point, even though the actual outline is roughly two degrees east. This requires inconsistent input; normal parser-produced fixtures passed. It is a defensive consistency defect, not evidence of corrupt company data or a failed parser.

Standalone reproducer, run from the reviewed application's repository root:

```bash
node --input-type=module <<'JS'
import { readFileSync } from 'node:fs';
import { cuerpoLeaflet } from './web/lib/geometria.js';
const f = JSON.parse(readFileSync('tests/js/fixtures/geometria/contornos.json', 'utf8'));
const d = f.filas.find(t => t.id === 't-simple').geometria;
const body = structuredClone(f.cuerpos[d.id]);
for (const polygon of body.geojson.coordinates)
  for (const ring of polygon)
    for (const point of ring) point[0] += 2;
console.log(cuerpoLeaflet(d, new Map([[d.id, body]])).estado);
// Current: cargado. Required: invalido, followed by the unavailable symbol.
JS
```

**Correction:** while traversing the already bounded coordinates, validate their actual extent against the declared bounds using a documented numerical tolerance. Include all parts and prevent out-of-bounds hole coordinates. Do not silently rewrite the descriptor/bbox, relocate the symbol or fall back to the unrelated X/Y. Reject inconsistent bodies so the existing unavailable-body behavior remains in effect. This does not require duplicating the parser's full topology/intersection algorithm.

A second inexpensive structural case, four identical points with the original nonzero bbox, also returns `cargado`; cover collapsed/mismatched bodies in the same correction. Preserve legitimate parser-produced holes, multipart bodies and limit fixtures. Keep validation linear in the bounded number of positions.

**Acceptance:** focused regression(s) for shifted and collapsed bodies, plus a real-renderer check that the original descriptor location keeps a distinguishable unavailable symbol and `zoomToScale` returns `contorno_no_disponible`. Existing valid fixtures and XY behavior must still pass. A matching bbox alone is not proof that two shapes are the same immutable version; keep the report's version-integrity claims limited to what the ID-keyed integration contract actually guarantees.

## F2 — P2: make the pixel regression wait for actual paint

Location: [`tests/e2e/contornos.mjs`, lines 386–413](https://github.com/Andre07-hash/ARA-MAP/blob/db0b679b0a30507a4458c0b9440e5b0168b1cc30/tests/e2e/contornos.mjs#L386).

The XY equivalence helper calls `render()` and `select()`, then reads `canvas.toDataURL()` and removes the map synchronously in the same browser evaluation. Leaflet schedules canvas painting for a later animation frame. As a result, the pixel portion of this regression compares empty canvases and cannot detect a visual change.

**Reproduced independently on Chrome 154:** both synchronous snapshots contained **0 nontransparent pixels**. After waiting for two animation frames, both baseline and B-2 contained **26,228 nontransparent pixels**, and their image data matched. Thus the current XY renderer passed an independent painted comparison; the finding concerns the submitted regression test's ability to protect that behavior, not an observed visual regression.

**Correction:** make the per-renderer comparison asynchronous, wait for canvas painting after the final view/render/selection, assert nonzero painted pixels, and compare the resulting images. Await both runs and remove the Leaflet map only after capture. Retain the existing count, viewport, scale and result comparisons.

**Acceptance:** the revised browser check passes on painted, nonempty canvases. Record the browser and the nonempty-image evidence. A deliberately blank result must fail the guard; do not weaken the equality assertion or accept matching blank images.

## Independent verification of the reviewed head

The supervisor exported the exact head into an isolated temporary archive and used fictional data; no application code in the working repository was changed.

| Check | Result |
|---|---|
| GitHub CI at reviewed head | Python/disposable Postgres and JavaScript both SUCCESS |
| `./verificar.sh` on macOS | PASS: 672 Python tests, 29 Postgres-only skips; complete system Python 3.9.6 suite; JavaScript tests |
| Real-browser `contornos.mjs` | All 18 checks passed on Chrome/Chromium 154.0.8037.98 using the repository's Playwright harness and actual mouse input |
| Hole/selection screenshot | Independently inspected the generated hole-selection image; hole remains unfilled and the selection outline is visible |
| Additional geometry consistency probe | F1 reproduced in the pure helper and real renderer |
| Additional painted XY comparison | Pixel equality passed after paint, with 26,228 nontransparent pixels per renderer; F2's synchronous blank capture also reproduced |

The supervisor's environment did not reproduce the team's environmental openpyxl packaging failure. Local Postgres was skipped; the disposable-Postgres evidence is GitHub CI, not a local claim. No hosted employee workflow, real company geometry, Safari/Firefox, touch or production resources were tested in this review. The extra probes are review experiments, not production implementation.

## Recorded performance limitation — separate from these corrections

The team's measurements transparently disclose a layout containing one large part and roughly 19,999 small parts taking about 1.5–3.3 seconds per view change, with a roughly 1.3-second selection delay. Those timings are Team B's measured evidence; the supervisor did not repeat the entire performance matrix.

The B-2 packet expressly asked for measured limits without silent simplification. This disclosure satisfies that requirement for a renderer foundation; it does not establish release readiness for every parser-accepted geometry. Before hosted employee rollout, the integration packet must define and test a bounded display strategy for extreme multipart cases, with an explicit status when a full outline is deferred. Neither silently discard parts nor lower the accepted B-1 parser budget to conceal renderer cost. No performance redesign is added to this correction packet.

## Correction packet and return

1. Continue on `claude/team-b/map-boundaries`, updating draft PR #11 through normal commits. Preserve PR #9 and all other branches.
2. Fix F1 in B-owned geometry helpers and add focused helper/browser regressions. Fix F2 in the existing browser harness. Update the report with dispositions and new evidence; retain the original measurements as historical evidence.
3. Run the relevant JS and browser tests and repository verification. If the environment still lacks zsh, run and clearly report its components and let CI supply disposable-Postgres evidence. Do not call a baseline environmental failure a pass.
4. Return the new instruction SHA, implementation/head SHAs, CI results and report path. Stop for supervisory review before B-3. Do not merge/deploy or change Team A's owned files.

B-3 also needs the revised attachment schema/state/concurrency requirements and Team A's early schema/auth/route prerequisites, as established by the approved shared contract. No A-1 implementation PR was visible in the repository listing during this review; that does not imply Team A has not started. Team A may continue its assigned work while B addresses these corrections.
