# Team B · B-1 response to the second review (F2 allocation)

October 7, 2026 · Team B · PR #9 (additive commits on `claude/team-b/kmz-parser`)

| Item | Value |
|---|---|
| Review | `badd1705797ff39f9f66774d060168e2c406b2e2` — `reports/team-b-b1-review-2026-10-07/SECOND_REVIEW.md` |
| Reviewed head | `11ae1a82f4729c3e1eef02df70bfb0337d84e287` |
| Application baseline | `09452fd26d38319567dce28a89db100ea61c739a` (`origin/main`, unchanged) |
| Fix commit | `461254a` (fix, regression, measurement cases) |
| Scope | Unchanged: `server/kmz.py`, `tests/test_kmz.py`, this report folder. F1 and F3 are not reopened; their reproducers still give `listo` and `rechazado`. No dependency, no application integration. B-2 remains pending. |

## Disposition: fixed

**Cause.** `_validar_partes` called the containment helper with one set per part holding every other part's index:

```python
[{j for j in range(len(poligonos)) if j != i} for i in range(len(poligonos))]
```

That is N × (N − 1) memberships, built with no charge first. Reproduced on the reviewed head with the supervisor's script: 9,900 / 159,600 / 639,200 memberships at 100 / 400 / 800 parts, with only 12,800 / 51,200 / 102,400 units charged.

**Fix (`461254a`).**
- **Interior-point test.** `_alguno_dentro` now takes its targets in one of two forms:
  - `propias`: point *i* may count inside any part except `propias[i]`. For interior points this is `range(len(poligonos))`, which is O(1) and not materialized.
  - `destinos`: explicit target sets, kept for contact pieces. Each edge's set holds at most as many parts as that edge has contacts, which were already charged. The edge's pieces share one `frozenset` instead of copying it.
- **No per-pair scan.** The helper only examines the (point, part) pairs that the charged batched point-in-ring pass actually visited. Nothing it builds scales with points × parts.
- **Audit of this path's other containers.**
  - Charged before they are built: the ring/owner lists (`Σ rings + parts`) and the hole points in `_validar_huecos` (`len(polygon)`).
  - Already bounded by earlier charges: the contact map, the pieces list, the parity sets and the interior points.
  - The rest of the geometry path was re-read for the same pattern. Every other intermediate container is built after a charge proportional to its size.

## Regression (`tests/test_kmz.py`, class `F2SegundaRevisionMuchasPartes`, all through `procesar_kmz`)

The cases use one candidate (one placemark's `MultiGeometry`) of disjoint 0.001° squares, 40 per row, as in the reviewer's layout.

| Test | Property checked | Reviewed head `11ae1a8` | Fix |
|---|---|---|---|
| `test_memoria_lineal_en_el_numero_de_partes` | tracemalloc peak at 1,600 parts < 16 × the peak at 200 parts (linear ≈ 8×; the old per-part sets grow with parts²) | **fails**: 281.6 MB vs 1.9 MB = **145×** | passes: 5.0 vs 0.6 MiB ≈ 8.3× |
| `test_trabajo_lineal_en_el_numero_de_partes` | charged work at 1,600 parts < 12 × the work at 200 parts | passes; work was already linear, which is exactly why the memory test is needed | passes: 385,639 / 48,239 = 8.0× |
| `test_presupuesto_pequeno_se_detiene_antes_de_crecer` | `MAX_TRABAJO` = 50,000 on 1,600 parts → `GEOMETRIA_DEMASIADO_COMPLEJA`, with a peak below the full run's | — | passes |
| `test_partes_que_se_enciman_entre_muchas` | one overlapping square among 400 → `GEOMETRIA_PARTES_SUPERPUESTAS` | — | passes |
| `test_copia_o_parte_contenida_entre_muchas` | a contained square, and an exact copy, among 400 → `GEOMETRIA_PARTES_SUPERPUESTAS` | — | passes |
| `test_islas_en_huecos_y_bordes_compartidos_entre_muchas` | a part with a hole, an island exactly filling it, and an edge-sharing neighbour among 400 → `listo`, 403 parts | — | passes |

These are scaling properties and outcomes, not wall-clock thresholds. The older overlap, containment, island-in-hole, shared-edge, F1 and F3 regressions are unchanged and pass. The 399-million-membership case was not generated on the reviewed code.

## Many-part measurements (one candidate; this container)

| Parts (one candidate) | Positions | Outcome | Work units | 3.13 time | 3.9 time | tracemalloc | RSS Δ | JSON |
|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 100 | 500 | listo | 23,339 | 0.015 s | 0.021 s | 0.3 MiB | 0.6 MiB | 13 KB |
| 400 | 2,000 | listo | 96,439 | 0.061 s | 0.09 s | 1.2 MiB | 1.6 MiB | 60 KB |
| 800 | 4,000 | listo | 192,839 | 0.114 s | 0.189 s | 2.4 MiB | 2.8 MiB | 116 KB |
| 4,000 | 20,000 | listo | 923,239 | 0.621 s | 0.862 s | 11.9 MiB | 10.9 MiB | 544 KB |
| 20,000 | 100,000 | listo | 4,235,239 | 2.92 s | 4.186 s | 51.9 MiB | 44.4 MiB | 2.71 MB |

- **Scaling.** Work grows at about 212–241 units per part and peak memory at about 2.6–3.2 KB per part, from 100 to 20,000 parts.
- **At the limit.** 20,000 parts (100,000 positions) use 4.2M of the 30M units.
- **The reviewed code at the same size.** It would have built 20,000 × 19,999 ≈ 400 million memberships before any charge. That figure is arithmetic; it was not run.
- **Other cases.** All other cases in the full re-run keep their earlier outcomes and work units within a few percent.

The full re-run of every measurement case at `461254a` is in `evidencia/medicion-python3.{13,9}.txt`. The non-multipart cases are unaffected.

## Test evidence (this container, head `461254a`)

- `tests.test_kmz`: **95 OK** on Python 3.13.16 and uv's CPython 3.9.25.
- Full `unittest discover` on 3.13 and 3.9: 767 run, 29 skipped (no Postgres URL), and 1 failure, `test_packaging…has_no_openpyxl_of_its_own`. It is environmental: the container's system Python has its own openpyxl, and the failure is identical on the baseline.
- `node --test`: 98 pass. ruff (`server/`, `tests/`, report scripts) and mypy (`server/`) are clean. Coverage is 98 % for `server/kmz.py` and 95 % overall.
- `./verificar.sh` was not run, because this container has no `zsh`; its component commands were run as above. macOS Python 3.9.6 is not available here.
- GitHub Actions on the pushed head: see the PR.

## Unchanged open items

Everything listed in `RESPUESTA_REVISION_B1.md` and in the B-1 report's §6/§8 remains open. Real-file acceptance, hosted performance, storage, the map DTO and B-2 are later work.
