# B-1 second review — one remaining correction

Reviewed [PR #9](https://github.com/Andre07-hash/ARA-MAP/pull/9) at `11ae1a82f4729c3e1eef02df70bfb0337d84e287`. This follows the [first review](REVIEW.md), published at `3a8b28b5a32ea67cb3b6dc6d176a33351fb2fe11`, and Team B's `RESPUESTA_REVISION_B1.md` at the reviewed head.

**Decision: F1 and F3 closed; F2 improved but not yet closed. Keep PR #9 draft for one focused correction.** This is the current Team B assignment. Do not restart the parser or repeat already accepted corrections. B-2 remains pending.

## Accepted corrections

- **F1:** the original rectangle reproducer now returns `listo`. The new scanline method, verification of the resulting point, structured fallback, and regressions for holes, multipart geometry, and selections address the finding.
- **F3:** the original forged-count archive is now rejected. The preallocation central-directory walk counts actual headers, including directories; the regression also verifies that `zipfile.ZipFile` is not invoked for that over-limit input.
- **F2, completed portions:** one shared budget now reaches the candidate, selection, crossing, containment, interior-point, and normalization paths. The many-hole containment pass no longer does the earlier unchecked pairwise scan. The measurements distinguish observed cases from guarantees.

All 89 parser tests passed independently on both local runtimes, including macOS Python 3.9.6. GitHub's Python/disposable Postgres and JavaScript jobs are green at the reviewed head. Those passing checks do not cover the allocation below.

The full `./verificar.sh` also passed in an isolated archive of this exact head: 761 Python tests with 29 Postgres-only skips, the full macOS Python 3.9.6 compatibility suite, and JavaScript tests. Verification used temporary local data with cloud database and paid-AI environment credentials removed. The reproducer printed below was separately executed against that archive and matched the observations.

## Remaining F2 issue: quadratic destination sets are built before the budget check

[Location: `server/kmz.py`, lines 1011–1013](https://github.com/Andre07-hash/ARA-MAP/blob/11ae1a82f4729c3e1eef02df70bfb0337d84e287/server/kmz.py#L1011).

Before calling `_alguno_dentro`, `_validar_partes` constructs one set of every other part index for each part:

```python
[{j for j in range(len(poligonos)) if j != i}
 for i in range(len(poligonos))]
```

For N parts this materializes N × (N − 1) memberships. There is no budget charge before that construction. The downstream batched containment and its budget cannot stop an allocation that has already completed. This leaves both unchecked work and potentially excessive memory use in the public parser path.

I reproduced it through `procesar_kmz` with one placemark containing a `MultiGeometry` of disjoint square polygons. A wrapper recorded the arguments at entry to `_alguno_dentro` and then called the original function:

| Polygon parts | Positions | Already allocated destination memberships | Work charged when helper is entered | Result |
|---:|---:|---:|---:|---|
| 100 | 500 | 9,900 | 12,800 | `listo` |
| 400 | 2,000 | 159,600 | 51,200 | `listo` |
| 800 | 4,000 | 639,200 | 102,400 | `listo` |

The 500-candidate limit does not constrain this case: all parts belong to **one** candidate. The 100,000-position limit permits 20,000 five-position polygons; the same expression would construct 399,980,000 memberships. That is an arithmetic extrapolation, not a large-memory test I ran.

### Required correction

Represent “any part except this point's own part” implicitly or with bounded metadata, rather than materializing all other indices for each point. Preserve the separate target-subset semantics needed for contact-piece checks. Audit this path's intermediate containers as well as its edge comparisons: budget enforcement must occur before expensive work/allocation.

Add a regression through `procesar_kmz` for one candidate with many disjoint parts. It must check the allocation/work property, not merely that a result is returned or the final budget matches itself. Use an allocation/construction guard, deterministic work accounting, or controlled peak-memory scaling; avoid a fragile runtime threshold. Also exercise a deliberately small budget, and retain overlap, containment, islands in holes, shared-edge, and F1/F3 regressions. Do not generate the full 399-million-membership case on the existing implementation.

The desired outcome is that ordinary disjoint multipart geometry stays efficient; genuinely expensive geometry still returns `GEOMETRIA_DEMASIADO_COMPLEJA` before unbounded work. No new dependency or application integration is needed for this correction.

## Reproducer

Run in an isolated checkout of `11ae1a82f4729c3e1eef02df70bfb0337d84e287`. This creates fictional KMZ data in memory and leaves the original helper behavior intact.

```python
import io
import json
import zipfile
from server import kmz

for count in (100, 400, 800):
    polygons = []
    for i in range(count):
        x, y = -100.4 + (i % 40) * .003, 20.6 + (i // 40) * .003
        ring = [(x, y), (x + .001, y), (x + .001, y + .001),
                (x, y + .001), (x, y)]
        coordinates = " ".join(f"{a},{b}" for a, b in ring)
        polygons.append("<Polygon><outerBoundaryIs><LinearRing><coordinates>"
                        + coordinates + "</coordinates></LinearRing>"
                        "</outerBoundaryIs></Polygon>")
    xml = ("<kml><Placemark><MultiGeometry>" + "".join(polygons)
           + "</MultiGeometry></Placemark></kml>")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", xml)

    original = kmz._alguno_dentro
    observations = []
    def inspect(points, targets, rings, owners, budget):
        observations.append({
            "memberships": sum(len(target) for target in targets),
            "charged_so_far": budget.usado,
        })
        return original(points, targets, rings, owners, budget)
    kmz._alguno_dentro = inspect
    try:
        result = kmz.procesar_kmz(data.getvalue())
    finally:
        kmz._alguno_dentro = original
    print(json.dumps({"parts": count, "state": result["estado"],
                      "observations": observations}))
```

This reproducer targets the reviewed implementation's helper signature. A corrected implementation may use a different internal interface; its permanent regression should verify the bounded behavior rather than preserve that signature.

## Return and sequencing

Continue on `claude/team-b/kmz-parser` and update existing PR #9 with additive commits. Return the new head, the regression that detects this allocation, test evidence, and updated many-part measurements. Do not reopen F1 or F3 unless a change actually regresses them. Keep all original B-1 ownership boundaries.

No Team A preparation PR is visible among open PRs at this review. The shared contract remains pending; acceptance of B-1, once this is fixed, will not by itself authorize B-2 integration. No merge, production change, or new monitoring schedule was performed as part of this review.
