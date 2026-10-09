# Supervisor review: B-1 standalone KMZ parser

## Decision and scope

**Request changes: keep PR #9 draft and complete the three corrections below.** The implementation stays within B-1 ownership and fixes the four preparation-stage defects. Its test suite passes, but additional independent probes expose gaps in the no-crash and bounded-work contract. B-1 is not accepted yet. No application integration or production release is authorized by this review.

Reviewed [PR #9](https://github.com/Andre07-hash/ARA-MAP/pull/9) at `c7efcf8754ad42c277f25a1afb8455762a52ba8d`; implementation `9a76148e0537c6d9919b36d2a479f2a496a60a3a`; application baseline `09452fd26d38319567dce28a89db100ea61c739a`; prior packet `c6bb9dc3d0f7cbe7a3d7157f2b05b9346a4e3abd`.

The module remains disconnected from the running application. There are no schema, route, role, storage, map, or deployment changes. The branch choice and preservation of PR #8's history are correct.

## Blocking findings

### F1 — A valid boundary can exhaust the interior-point samples and raise an exception

[Code: `punto_interior`, lines 925–943](https://github.com/Andre07-hash/ARA-MAP/blob/c7efcf8754ad42c277f25a1afb8455762a52ba8d/server/kmz.py#L925).

The algorithm tries 199 predetermined scanline heights and skips a height whenever a vertex has that latitude. A valid rectangle with extra collinear vertices at those heights passes boundary validation but exhausts every attempt. The public parser then raises `ValueError: no interior point: the polygon was not validated` instead of returning its structured result. This occurs with approximately 200 vertices, far below the limit.

**Required:** choose an interior point using a method that can handle this valid input, with an explicit bounded fallback for numerically problematic geometry. Catching all exceptions and rejecting this ordinary rectangle is insufficient: the regression must return `listo` and a point strictly inside the filled area. Exercise this through `procesar_kmz`, both as a single polygon and within multipart/selection validation. Preserve holes and concave-shape coverage.

### F2 — Geometry containment checks bypass the validation work budget

[Code: hole containment, lines 626–634](https://github.com/Andre07-hash/ARA-MAP/blob/c7efcf8754ad42c277f25a1afb8455762a52ba8d/server/kmz.py#L626), and [part containment, starting at line 857](https://github.com/Andre07-hash/ARA-MAP/blob/c7efcf8754ad42c277f25a1afb8455762a52ba8d/server/kmz.py#L857).

The grid budgets registrations and edge-pair comparisons, but the subsequent hole-with-hole containment loop compares every hole with every other hole without charging a budget. The part-containment and contact post-processing stages also need coverage. A vertex cap alone does not bound these stages to the work promised by the report.

Independent measurements on valid, disjoint square holes:

| Holes in one shell | Total positions | Calls to `_en_anillo` | Elapsed time on review machine |
|---|---:|---:|---:|
| 100 | 505 | 10,000 | 0.009 s |
| 500 | 2,505 | 250,000 | 0.102 s |
| 1,500 | 7,505 | 2,250,000 | 0.785 s |

All returned `listo`. Counts were measured by wrapping `_en_anillo`, retaining its original behavior. The growth is quadratic; these timings are not a measurement of the maximum-size case or of Vercel. The accepted 100,000-position budget allows far larger inputs than this probe. The report's comb benchmark exercises a different stage and does not establish a worst case for containment.

**Required:** enforce a documented work budget across the entire processing call, including all candidates, combined selections, hole/part containment, contact post-processing, and interior-point work. Spatial filtering may reduce comparisons, but it does not replace a safe termination rule. Return `GEOMETRIA_DEMASIADO_COMPLEJA` when the work cannot be completed within the agreed budget. Count the cost of scanning ring edges, not only calls to a helper. Add deterministic budget tests and representative many-hole/many-part benchmarks; do not use a fragile wall-clock threshold as the regression test.

To reproduce the many-hole fixture: outer rectangle starts at `(-100.4, 20.6)` with width/height `0.2`. Hole `i` starts at `(-100.399 + (i % 50) * 0.003, 20.601 + (i // 50) * 0.003)` with width/height `0.001`. Close every five-position ring, put them in one polygon and one placemark, and measure counts 100, 500, and 1,500. This is entirely fictional geometry.

### F3 — A false ZIP entry count bypasses the archive-entry limit

[Code: `_revisar_directorio`, lines 271–280](https://github.com/Andre07-hash/ARA-MAP/blob/c7efcf8754ad42c277f25a1afb8455762a52ba8d/server/kmz.py#L271).

The entry limit trusts the ZIP end record's declared counts. Construct an archive containing `doc.kml` plus 1,000 empty resources, then change both end-record entry counts to 1. `zipfile` still reads the 1,001 actual central-directory entries, and the parser returns `listo`. The end-record consistency test accepts this because both forged counts agree with each other. No subsequent check enforces the actual count.

**Required:** check actual central-directory entries with bounded work before allowing unrestricted directory materialization, and validate the relevant directory/end-record consistency. A check of `len(infolist())` only after all entries have been allocated does not meet the preallocation requirement. Preserve supported ordinary archives and return a controlled error for inconsistent or oversized directories. Include directory entries as well as regular-file entries in resource accounting. Add this exact forged-count regression, ordinary limit/limit-plus-one cases, and truncated/inconsistent-directory cases.

## Exact independent reproducer for F1 and F3

Run this in an isolated checkout of the reviewed application head. It creates archives in memory and uses no database, filesystem extraction, or network. On the reviewed head, F3 prints `listo`; F1 prints the uncaught `ValueError`.

```python
import io
import struct
import zipfile
from server import kmz

def polygon(points):
    coords = " ".join(f"{x},{y}" for x, y in points)
    return ("<kml><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
            + coords + "</coordinates></LinearRing></outerBoundaryIs>"
            "</Polygon></Placemark></kml>")

def package(xml, resources=0):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", xml)
        for i in range(resources):
            archive.writestr(f"files/{i}.txt", b"")
    return data.getvalue()

rectangle = [(-100.4, 20.6), (-100.39, 20.6), (-100.39, 20.61),
             (-100.4, 20.61), (-100.4, 20.6)]
data = bytearray(package(polygon(rectangle), kmz.MAX_ENTRADAS))
end = data.rfind(b"PK\x05\x06")
struct.pack_into("<HH", data, end + 8, 1, 1)
print("F3:", kmz.procesar_kmz(bytes(data))["estado"])

south, north = 20.6, 20.61
heights = sorted({
    south + (north - south) * (
        0.5 if k == 1 else (0.5 + k * 0.6180339887498949) % 1.0)
    for k in range(1, 200)
})
points = rectangle[:4] + [(-100.4, y) for y in reversed(heights)] + rectangle[:1]
try:
    print("F1:", kmz.procesar_kmz(package(polygon(points)))["estado"])
except Exception as error:
    print("F1:", type(error).__name__, str(error))
```

## Next assignment to Team B

1. Continue on `claude/team-b/kmz-parser` and update **the existing PR #9** with additive commits. Do not rewrite PR #8 or create a parallel implementation branch for these corrections.
2. Add public-entry-point regression tests for F1–F3, fix the causes, and keep the scope inside the standalone parser, fictional tests/fixtures, and reports. Shared application files remain A's responsibility.
3. Review the remaining validation and parsing stages for the same bounded-work assumption. Update the measurements and describe exactly which limits apply per file, candidate, selection, or stage. Correct broad “never raises” or “worst case” claims where the evidence does not support them.
4. Keep Python 3.9 and both execution environments consistent. A geometry-library dependency is not authorized by this packet; if necessary, propose it with the local/cloud implications. Do not silently introduce automatic repairs, snapping, or tolerance-based acceptance of overlapping parts.
5. Run focused tests, the repository verification checks (or disclosed equivalents when `zsh` is unavailable), and applicable lint/type checks. Wait for GitHub checks on the updated head. Return the new exact SHA, report path, F1–F3 disposition, regression evidence, and anything still unverified.

## Evidence and remaining coordination

The supervisor independently ran all 71 parser tests on the default Python and macOS system Python 3.9.6; both passed. The full `./verificar.sh` also passed in an isolated archive of the reviewed head: 743 Python tests with 29 Postgres-only skips, the full macOS Python 3.9.6 compatibility suite, and JavaScript tests. Verification used temporary local data with cloud database and paid-AI environment credentials removed. GitHub's Python/disposable Postgres and JavaScript checks are green at the reviewed head. These results do not cover the new reproductions above.

Real company KMZ acceptance, hosted performance, storage selection, and the final map DTO remain later work. Do not turn those into new requirements for this correction packet. Team A's preparation remains unchanged; no Team A preparation PR was visible at review time. B-2 is still pending the consolidated contract.
