# Team B · B-1 response to supervisor review F1–F3

October 7, 2026 · Team B · PR #9 (additive commits on `claude/team-b/kmz-parser`)

| Item | Value |
|---|---|
| Review | `3a8b28b5a32ea67cb3b6dc6d176a33351fb2fe11` — `reports/team-b-b1-review-2026-10-07/REVIEW.md` |
| Reviewed head | `c7efcf8754ad42c277f25a1afb8455762a52ba8d` (implementation `9a76148`) |
| Application baseline | `09452fd26d38319567dce28a89db100ea61c739a` (`origin/main`, unchanged) |
| Fix commits | `94fe5eb` (F1–F3 and regression tests), `27799d4` (per-row pair charging) |
| Scope | `server/kmz.py`, `tests/test_kmz.py`, and this report folder. Still not imported by the application. No shared files, SQL, routes, roles, storage, map or deployment changes, and no dependency added. |

## Disposition

| Finding | Disposition | Cause | Fix |
|---|---|---|---|
| **F1** — interior point can exhaust its samples and raise | **Fixed** | Fixed sampling heights; a valid ring with vertices at all of them left nothing to try, and `ValueError` escaped `procesar_kmz`. | Scanlines are placed halfway between **consecutive distinct vertex latitudes**. Such a latitude is never a vertex height, so the scanline crosses edges only in their interiors and its even-odd intervals are filled area. The 8 widest gaps are tried, and the widest interval midpoints are verified as inside the fill and on no ring. If floating point defeats every candidate, the result is `GEOMETRIA_INESTABLE`. That is a structured outcome: candidate-level during validation, `rechazado` or `requiere_seleccion` at the end. It is never an exception and never an unverified point. |
| **F2** — containment bypasses the work budget | **Fixed** | Hole/hole containment was pairwise (`holes²` × ring length) and uncharged. Part containment, contact pieces and interior points were also outside the grid's per-stage limits. | One `Presupuesto` of `MAX_TRABAJO` = 30,000,000 units **per `procesar_kmz` call** covers every geometry stage (table below). Hole and part containment now use one batched point-in-ring pass. Points are sorted by latitude and each edge visits only the points in its latitude band, with every (edge, point) visit charged. Grid pair comparisons are charged row by row, before the row runs, at 2 units each. Exhaustion gives `GEOMETRIA_DEMASIADO_COMPLEJA`. |
| **F3** — forged ZIP entry count bypasses the entry limit | **Fixed** | The limit trusted the end record's counts. | Before `zipfile` reads anything, the central directory span that `zipfile` will read is walked header by header, directories included. The walk stops with `KMZ_DEMASIADAS_ENTRADAS` at entry 1,001. The headers must tile the span exactly and end at the end record; the count must equal the declared count; the comment length must reach the end of the file. Anything else gives `KMZ_DANADO`. After opening, `len(infolist())` is re-checked as defence in depth. |

## Regression tests (`tests/test_kmz.py`, all through `procesar_kmz` unless noted)

Every new test fails on the reviewed implementation and passes now. To check this, the new classes were run with the reviewed `server/kmz.py` restored: F1 and F3 reproducers fail, and F2 tests error because no budget existed.

- **`F1PuntoInterior`**
  - The supervisor's exact reproducer (203 positions) returns `listo` with a point strictly inside. Coordinates are written with full precision; a first version of one test rounded them and silently stopped exercising F1. That was caught and fixed by the fail-on-old-code check.
  - The same ring with a hole; inside a two-candidate selection `[0, 1]`; inside a `MultiGeometry`.
  - Concave U, hole and multipart fixtures keep strict-interior points.
  - Fallback: when verification is forced to fail, the result is `GEOMETRIA_INESTABLE`, as `rechazado` for one candidate and `requiere_seleccion` for a selection. Attempts are bounded by `_LINEAS_INTERIOR`.
- **`F2PresupuestoDeTrabajo`**
  - The supervisor's many-hole fixture at 100, 500 and 1,500 holes returns `listo`. Charged work grows near-linearly (≈ 404, 429 and 431 units per hole), and the test asserts against quadratic growth.
  - Hole containment never calls the pairwise point-in-ring helper (patched to fail).
  - **Exact-boundary test for each stage:** with `MAX_TRABAJO` equal to the work a call used, the result is identical; one unit less gives `GEOMETRIA_DEMASIADO_COMPLEJA`. Cases: single polygon, hole, 300 holes, multipart, contiguous selection, overlapping selection, several candidates, and the F1 ring. These are deterministic unit counts, not wall-clock thresholds.
  - One budget is shared by all 40 candidates of a file.
  - A selection that exhausts the budget returns `requiere_seleccion`, keeping the candidates.
  - A direct `validar_poligonos` call is bounded too.
- **`F3DirectorioZip`**
  - The supervisor's exact forged-count reproducer returns `KMZ_DEMASIADAS_ENTRADAS`, and `zipfile.ZipFile` is patched to fail to prove nothing was materialized.
  - Forged counts within the limit (too low and too high) return `KMZ_DANADO`.
  - The 1,000-entry limit including 10 directory entries is accepted; 1,001 is refused, as are 1,000 directories plus `doc.kml`.
  - Truncated or inconsistent directories return `KMZ_DANADO`: directory size ±1, wrong offset, broken header signature, name length past the end record, trailing bytes, directory cut in half.
  - Ordinary archives (deflated and stored), data before the archive, and a ZIP comment still return `listo`.

## Bounded work by stage (replaces the B-1 report's §3 "Bounds" row and the "never raises" wording)

| Stage | Applies per | Limit |
|---|---|---|
| Package bytes | file | `MAX_KMZ_BYTES` 20 MiB, checked first |
| ZIP directory | file | Header walk, at most `MAX_ENTRADAS` (1,000) headers, directories included, before `zipfile` reads the directory |
| KML bytes | file | One member, `MAX_KML_BYTES` 16 MiB: declared size, then a streamed counter |
| XML parsing | file | Linear in the document; `MAX_ELEMENTOS` 500,000, `MAX_PROFUNDIDAD` 64, `MAX_CANDIDATOS` 500, `MAX_VERTICES` 100,000 (counted while streaming coordinates), `MAX_TOKEN` 128 |
| Ring checks, grid crossings, area, hole containment, part containment, contact pieces, interior points, candidate description, normalization | **one call**, across every candidate and any combined selection | `MAX_TRABAJO` 30,000,000 units (`Presupuesto`), charged before the work it pays for |

**Units:**
- 1 per position scanned, grid registration, or (edge, point) pair visited in a batched point-in-ring pass.
- 2 per edge-pair comparison, the most expensive unit-sized step.
- Sorting costs that are `n log n` are charged as `n` times the bit length of `n`.

Exhaustion is checked at the next charge, and charges are at most one grid row or one ring edge's latitude band. So a call overshoots `MAX_TRABAJO` by at most one such batch.

**Claims corrected.**
- *"Never raises"*: `procesar_kmz` returns structured results for malformed or hostile input, invalid selections, unstable geometry and budget exhaustion. Programming errors and process-level failures (`MemoryError`) are not caught.
- *"Worst case"*: the figures below are measured cases, not a proven worst case. The bound is the work budget plus the parse limits. Wall time per unit varies by stage and machine.

## Measurements (synthetic, fictional; this container)

Environment: this cloud container, x86_64, Linux 6.18, 4 CPUs, Python 3.13.16 and uv's CPython 3.9.25. Each case runs in a fresh process.
- **Time** is the median of 3 calls after one untimed call.
- **Work units** are those charged by the first call.
- **RSS Δ** is the resident-memory growth during the first call.
- Raw data: `evidencia/medicion-python3.{13,9}.txt`, produced by `medir.py`.

| Case | Outcome | Work units | 3.13 time | 3.9 time | tracemalloc | RSS Δ | JSON |
|---|---|---:|---:|---:|---:|---:|---:|
| circulo_100k_vertices | listo | 5,028,317 | 1.013 s | 1.648 s | 53.0 MiB | 41.2 MiB | 2.78 MB |
| con_hueco_100k_vertices | listo | 5,156,076 | 1.035 s | 1.653 s | 53.7 MiB | 42.2 MiB | 2.78 MB |
| peine_100k_vertices | rechazado `GEOMETRIA_DEMASIADO_COMPLEJA` | 30,001,059 | 6.155 s | 13.738 s | 34.1 MiB | 15.8 MiB | 260 B |
| 500_lotes_sin_seleccion | requiere_seleccion | 1,140,680 | 0.76 s | 1.166 s | 15.2 MiB | 12.9 MiB | 113 KB |
| 500_lotes_todos_seleccionados | listo | 5,209,984 | 1.676 s | 2.68 s | 48.2 MiB | 48.9 MiB | 2.88 MB |
| 2_partes_borde_compartido_100k | listo | 10,167,899 | 3.023 s | 5.14 s | 58.8 MiB | 55.2 MiB | 2.68 MB |
| F1_rectangulo_203_vertices | listo | 10,010 | 0.003 s | 0.005 s | 0.2 MiB | 0.4 MiB | 7 KB |
| F2_huecos_100 | listo | 40,442 | 0.012 s | 0.017 s | 0.5 MiB | 0.7 MiB | 11 KB |
| F2_huecos_500 | listo | 214,715 | 0.056 s | 0.086 s | 1.8 MiB | 1.7 MiB | 51 KB |
| F2_huecos_1500 | listo | 646,540 | 0.17 s | 0.304 s | 4.8 MiB | 3.7 MiB | 152 KB |
| huecos_19999_100k_vertices | listo | 14,160,792 | 2.807 s | 3.652 s | 41.3 MiB | 24.3 MiB | 2.22 MB |
| fila_de_2000_huecos | listo | 12,592,009 | 2.029 s | 2.454 s | 3.6 MiB | 3.3 MiB | 224 KB |
| fila_de_19999_huecos_adversaria | rechazado `GEOMETRIA_DEMASIADO_COMPLEJA` | 30,008,383 | 4.849 s | 6.041 s | 33.4 MiB | 12.7 MiB | 260 B |
| 500k_elementos_al_limite | listo | 165 | 0.58 s | 0.821 s | 8.9 MiB | 0.0 MiB | 715 B |
| vertices_300k_corte_en_100k | rechazado `KML_DEMASIADOS_VERTICES` | 0 | 0.232 s | 0.3 s | 23.5 MiB | 0.0 MiB | 268 B |
| kml_16MiB_justo_bajo_limite | listo | 165 | 0.05 s | 0.121 s | 33.6 MiB | 0.6 MiB | 715 B |

**Reading of the measurements**
- **Legitimate cases.** The largest uses 14.2M units (19,999 holes, about 100k positions), under half of `MAX_TRABAJO`. The slowest is 5.1 s on 3.9 (two parts sharing a detailed edge).
- **Budget exhaustion is the slowest outcome measured.** It took 6.2 s on 3.13 and 13.7 s on 3.9 for the adversarial 100k-position comb. Without the budget, the 19,999-hole row would have needed about 1.2 billion units (235 s on 3.13, measured during calibration). Vercel's speed per unit is unknown; the per-function `maxDuration` is 120 s.
- **Supervisor's many-hole probe.** At 1,500 holes it now takes 0.17 s on 3.13 and 646,540 units, against 2,250,000 pairwise ring tests before.
- **Parsing at its caps** (500,000 elements; 16 MiB) uses almost no geometry budget and takes under 1 s.

## Still unverified / unresolved

- Real company KMZ files, Vercel execution speed, and macOS hardware. Local Python 3.9 here is uv's CPython 3.9.25; the supervisor's macOS 3.9.6 was not available to me.
- `MAX_TRABAJO` is calibrated on synthetic shapes. Real files may justify a different value. Changing it is one constant, and the exact-boundary tests do not depend on it.
- Layouts that are inherently quadratic for an even-odd horizontal ray, such as thousands of holes in a single row, are refused as too complex rather than validated slowly. A 2,000-hole row passes; 19,999 does not.
- Everything in the B-1 report's §6 and §8 still applies: overlap tolerance for adjacent lots, the GEOS question, coordinate syntax, geometry transport size, storage comparison, and DTO naming.
