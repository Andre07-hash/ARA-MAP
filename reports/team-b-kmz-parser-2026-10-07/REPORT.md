# Team B · B-1 report — standalone KMZ parser

October 7, 2026 · Team B

| Item | Value |
|---|---|
| Instruction commit | `c6bb9dc3d0f7cbe7a3d7157f2b05b9346a4e3abd` — `reports/team-b-review-2026-10-07/REVIEW_AND_NEXT_PACKET.md`, read with `git show` without switching branches |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`, freshly fetched; unchanged since PR #8 |
| Branch | `claude/team-b/kmz-parser`, the name in the packet. This session's assigned branch (`claude/wonderful-pasteur-py6va6`) carries PR #8; it was not rewritten. |
| Implementation commit | `9a76148e0537c6d9919b36d2a479f2a496a60a3a` (this report is the commit after it) |
| Scope | B-1 only. **No** SQL, migrations, routes, roles, storage, upload API, map renderer, grid, deployment or production change. `server/kmz.py` is not imported anywhere in the application, and a test enforces that. |

## 1. What was delivered

| Path | Content |
|---|---|
| `server/kmz.py` | `procesar_kmz(datos: bytes, seleccion=None) -> dict`: a pure function. Standard library only; Python 3.9 floor; mypy-strict clean. |
| `tests/test_kmz.py` | 71 focused tests |
| `tests/fixtures/kmz/` | 38 fictional KML documents, `generar.py` to regenerate them, and a README. KMZ packages are built in memory by the tests. |
| `reports/…/medir.py`, `evidencia/` | Measurements near the limits, on Python 3.13 and 3.9 |
| `reports/…/ejemplos.py`, `ejemplos/` | 12 exact parser outputs for contract reconciliation |

Nothing from the disposable experiment in PR #8 is imported. The parser was rewritten.

## 2. Parser result contract (pure parser; it does not freeze A's API names)

Every result has the same eight keys:

```text
estado      "listo" | "requiere_seleccion" | "rechazado"
error       {codigo, mensaje} | null
avisos      [{codigo, mensaje}]               warnings, Spanish messages
ignorados   {"Point": 1, "LineString": 2, …}  non-boundary content found
candidatos  [{indice, nombre, carpeta[], partes, huecos, vertices, bbox,
              area_aproximada_m2 | null, valido, error | null}]   no coordinates
seleccion   [int] | null                      the indices used for "listo"
geometria   {geojson, bbox, punto_interior, area_aproximada_m2,
             partes, huecos, vertices} | null  only for "listo"
ubicacion   {dentro_de_mexico, utilizable} | null    only for "listo"
```

These three states describe the outcome of **processing**. They are deliberately different from future attachment/persistence states such as uploading, stored or active. The parser mints no ids and decides no active version.

- **Coordinate orders.**
  - `geojson` is a `MultiPolygon` with positions `[longitude, latitude]`, as in KML.
  - `bbox` is `[west, south, east, north]`.
  - `punto_interior` is a GeoJSON `Point`, also `[longitude, latitude]`. It lies strictly inside a filled part and outside that part's holes; it is computed with scanlines through the largest part, not from the bounding-box centre. A U-shaped fixture proves the difference.
  - X/Y are never read or written, and a test asserts that no `lat`/`lon`/`x`/`y` key appears in the output.
- **As written.** Rings, winding and repeated consecutive positions come back exactly as in the file. Altitude is dropped, with the `KML_ALTITUD_DESCARTADA` warning. Nothing is repaired or reordered.
- **Area.** `area_aproximada_m2` is a spherical approximation (the formula Leaflet.draw and Turf use). It never stands in for Superficie or HA.
- **Validity vs. eligibility.** A valid boundary outside the Mexico extent from `server/validation.py` (the same constants object X/Y uses) is returned with `estado: listo`, `ubicacion.utilizable: false` and the warning `GEOMETRIA_FUERA_DE_MEXICO`. It is not corrected.
- **Selection.**
  - Several polygon-bearing placemarks → `requiere_seleccion`. The parser never chooses.
  - A selection must be a list or tuple of distinct, in-range `int`s (not `bool`, `float` or `str`), nonempty and no longer than the number of candidates. Anything else gives `requiere_seleccion` plus `SELECCION_INVALIDA`, and never raises.
  - Choosing an invalid candidate gives `SELECCION_CONTORNO_INVALIDO`.
  - Several chosen candidates form one multipart terrain, which must not overlap; otherwise the result is `GEOMETRIA_PARTES_SUPERPUESTAS`.

Example outputs: `ejemplos/01…12-*.json`. These include the supervisor's `[0, 0]` (05) and `[0.0]` (06) probes.

**Codes.**
- Package: `KMZ_DEMASIADO_GRANDE`, `KMZ_NO_ES_ZIP`, `KMZ_DANADO`, `KMZ_NO_SOPORTADO` (ZIP64/multi-disk), `KMZ_DEMASIADAS_ENTRADAS`, `KMZ_SIN_KML`, `KMZ_VARIOS_KML`, `KMZ_CIFRADO`, `KMZ_COMPRESION_NO_SOPORTADA`.
- XML: `KML_DEMASIADO_GRANDE`, `KML_XML_INVALIDO`, `KML_CODIFICACION_NO_SOPORTADA`, `KML_DTD_NO_PERMITIDA`, `KML_DEMASIADO_ANIDADO`, `KML_DEMASIADOS_ELEMENTOS`, `KML_DEMASIADOS_CONTORNOS`, `KML_DEMASIADOS_VERTICES`, `KML_COORDENADAS_INVALIDAS`, `KML_COORDENADAS_FUERA_DE_RANGO`, `KML_POLIGONO_INCOMPLETO`, `KML_SIN_CONTORNO`, `KML_SIN_CONTORNO_VALIDO`.
- Geometry: `GEOMETRIA_VERTICES_INSUFICIENTES`, `GEOMETRIA_ANILLO_ABIERTO`, `GEOMETRIA_AUTOINTERSECCION`, `GEOMETRIA_SIN_AREA`, `GEOMETRIA_HUECO_INVALIDO`, `GEOMETRIA_PARTES_SUPERPUESTAS`, `GEOMETRIA_DEMASIADO_COMPLEJA`.
- Selection: `SELECCION_INVALIDA`, `SELECCION_CONTORNO_INVALIDO`.
- Warnings: `KMZ_ARCHIVOS_ADICIONALES`, `KML_CONTENIDO_IGNORADO`, `KML_ENLACE_EXTERNO`, `KML_ALTITUD_DESCARTADA`, `GEOMETRIA_FUERA_DE_MEXICO`.

## 3. Supervisor's required corrections

| Requirement | How it is met | Evidence (`tests/test_kmz.py`) |
|---|---|---|
| Probe: four copies of one coordinate | `rechazado`, `GEOMETRIA_VERTICES_INSUFICIENTES` (fewer than 3 distinct positions) | `FormasInvalidas` · fixture `cuatro_copias_mismo_punto` |
| Probe: bow-tie | `rechazado`, `GEOMETRIA_AUTOINTERSECCION`. Crossings are checked before area, so the cause is named correctly; the symmetric bow-tie has zero signed area. | `FormasInvalidas` · `monio_autointerseccion` |
| Probe: `[0, 0]` | `SELECCION_INVALIDA`; no doubled area | `test_seleccion_duplicada_no_duplica_el_area`, `test_selecciones_invalidas_nunca_fallan` |
| Probe: `[0.0]` | `SELECCION_INVALIDA`; no `TypeError` | same, plus 18 other malformed selections |
| More than one KML, including duplicate names | `KMZ_VARIOS_KML` even when one of them is `doc.kml` (also `doc.kml` + `DOC.KML`). No chooser. | `test_varios_kml_son_ambiguos_aunque_haya_doc_kml` |
| Distinct vertices, nonzero area, self-intersection, holes vs. shells | Closed rings with ≥ 3 distinct positions; no self-contact or doubling-back spike; holes strictly inside their shell and outside each other, not touching any ring; parts may share edges or corners but never overlap | `FormasInvalidas` (12 cases), `PartesQueSeTocan`, `Seleccion` |
| Malformed, truncated, encrypted, unsupported-compression, corrupt ZIP/XML | Controlled `rechazado`. The ZIP end record is validated before `zipfile` builds its directory; nothing is extracted to disk (dangerous paths tested). | `Paquete`, `TextoMalformado`, seeded mutation test |
| DTD/entities and external fetching disabled | expat with DTD, entity and external-entity handlers that refuse, and parameter entities off. NetworkLinks and overlays are recorded, never fetched; the test patches the socket to prove no network use. | `entidades_dtd`, `entidad_externa`, `test_nunca_usa_la_red` |
| Bounds enforced while reading | Package bytes; ZIP entries (from the end record, before parsing the directory); KML bytes (declared size and streamed counter); depth, elements, candidates, vertices and token length during parsing. Coordinates are parsed as they stream, so the vertex cap stops work at exactly the limit. | `Limites`: each limit at exactly its value and one past it; real values for entries, depth, candidates, vertices and package size |
| Validation compatible with the vertex budget | Adaptive sparse grid (cell = median segment length, coarsened only if long edges would exceed the registration budget) with a comparison budget. Beyond either budget → `GEOMETRIA_DEMASIADO_COMPLEJA`, never an unchecked acceptance. | `test_presupuesto_de_validacion`; measurements below |
| Mexico extent as a separate result | `ubicacion` is separate from validity | `Geografia` |
| Measure time, memory, result size | §4 | `evidencia/medicion-python3.{13,9}.txt` |

The validation rules are deliberately stricter than OGC in one respect: a hole touching its shell at a single point is rejected.

## 4. Measurements near the limits (synthetic, fictional)

Environment: this cloud container — x86_64, Linux 6.18, 4 CPUs. Python 3.13.16 (system) and 3.9.25 (uv-managed CPython, standing in for macOS's 3.9). Limits: 100,000 vertices, 16 MiB KML, 500 candidates, 20 MiB package.

Each case runs in a fresh process.
- **Time** is the median of three calls after one untimed call.
- **Memory:** tracemalloc gives the peak of Python allocations, and *RSS Δ* is the resident-memory growth during the first call.
- **JSON** is the size of the serialized result.

| Case | Outcome | 3.13 time | 3.9 time | tracemalloc | RSS Δ | JSON |
|---|---|---|---|---|---|---|
| 100k-vertex circle | listo | 0.98 s | 1.47 s | 53 MiB | 41 MiB | 2.78 MB |
| 100k vertices, shell + hole | listo | 0.96 s | 1.42 s | 54 MiB | 42 MiB | 2.78 MB |
| Two parts sharing a detailed ~50k-vertex edge, both selected | listo | 2.94 s | 4.42 s | 59 MiB | 55 MiB | 2.68 MB |
| 500 lots, no selection | requiere_seleccion | 0.72 s | 1.10 s | 15 MiB | 13 MiB | 113 KB |
| 500 lots, all selected | listo | 1.48 s | 2.40 s | 48 MiB | 49 MiB | 2.88 MB |
| 100k-vertex comb of long overlapping teeth (adversarial) | rechazado `GEOMETRIA_DEMASIADO_COMPLEJA` | 3.41 s | 6.85 s | 34 MiB | 16 MiB | 0.6 KB |
| 300k vertices (3× the limit) | rechazado `KML_DEMASIADOS_VERTICES` | 0.22 s | 0.24 s | 24 MiB | — | 0.3 KB |
| 16 MiB KML just under the limit | listo | 0.05 s | 0.14 s | 34 MiB | 0.5 MiB | 0.7 KB |

**Reading of the measurements**
- Worst measured completion is under 7 s, against `maxDuration: 120`. Vercel CPU speed is not known from here.
- A result at the vertex limit is about 2.8 MB of JSON. That is under the 4.5 MB function response limit but not by much. The geometry-transport point in the packet stands: integration should not return raw full-limit geometry in ordinary list responses.
- Shapes made of many long overlapping edges are refused as too complex rather than validated slowly.
- An earlier longitude sweep refused a realistic north–south detailed edge as "too complex"; the adaptive grid replaced it.

Measurements were not taken on Vercel, real company files, or macOS hardware.

## 5. Checks run (branch head, this container)

| Check | Result |
|---|---|
| `python3 -m unittest tests.test_kmz` (3.13.16) | 71 tests OK, ~2 s |
| Same on Python 3.9.25 | 71 tests OK |
| `python3 -m unittest discover -s tests -t .` (3.13 and 3.9) | 743 run, 29 skipped (no Postgres URL), **1 failure**: `test_packaging…test_the_system_python_has_no_openpyxl_of_its_own`. This is environmental: this container's system Python has its own openpyxl. Baseline `09452fd` shows the identical failure (672 run, same 1 failure). |
| `node --test tests/js/*.test.mjs` | 98 pass |
| `ruff check server/ tests/ reports/team-b-kmz-parser-2026-10-07/` | clean |
| `mypy server/` (project config, strict defs) | clean, 44 files |
| Coverage (`coverage run -m unittest discover`) | `server/kmz.py` 97 %; total 94 % (floor 80 %) |
| Mutation fuzz, separate script, 20,000 seeded mutations of fixtures/KML/ZIP | 0 unhandled exceptions. The first run found `LookupError` on a mangled `encoding=` declaration; it now gives `KML_CODIFICACION_NO_SOPORTADA` and a seeded 600-case version is in the suite. |
| `./verificar.sh` | Not run: the container has no `zsh`. Its components were run individually as above, with ruff/mypy/coverage standing in for `--todo`. Browser e2e: not applicable (no UI). |

Postgres CI: B-1 adds no SQL. GitHub Actions on the draft PR will run the suite against its disposable Postgres.

## 6. Known limits of the validation (not claimed)

- **Floating point, no snapping.** Predicates are plain floating-point arithmetic on longitude/latitude.
  - Parts that share edges are accepted when shared vertices coincide exactly, or a vertex lies exactly on the other edge.
  - Hand-digitized adjacent lots usually overlap or gap by centimetres. When selected together they may be refused as `GEOMETRIA_PARTES_SUPERPUESTAS`. Choosing parts separately still works.
  - A tolerance policy (accept slivers under N cm²?) needs real samples and an owner decision. It is not decided here.
- **Not a full topology library.** The checks cover the rules in §3, by construction and by the tests listed. They are not GEOS. If the supervisor wants OGC-complete validation, the narrow proposal is an optional `shapely` (GEOS) check for the **cloud only**. It cannot run in the dependency-free local app on macOS's Python 3.9, so local and cloud would validate differently. I recommend not adding it until real files show the stdlib rules are insufficient. **No dependency was added.**
- **Strict coordinate syntax.** A tuple must be `lon,lat[,alt]` with no spaces inside it, as the KML spec requires. Files written as `lon, lat` are refused (`KML_COORDENADAS_INVALIDAS`); real samples may show whether tolerance is needed.
- **Open rings are refused, not closed.** This follows the "do not repair" rule. Google Earth writes closed rings; other tools may not.

## 7. Correction acknowledged: storage research

The supervisor is right that Vercel publishes an official Python SDK: the `vercel` package on PyPI, including a `vercel.blob` module. The preparation report's claim that only a JavaScript SDK existed was wrong. I have **not** re-evaluated the provider in this packet. vercel.com is not reachable from this container, and the comparison needs to be checked against the Python 3.9 floor, browser delivery and the dependency policy. S3-compatible storage remains a candidate only, and handwritten request signing is withdrawn as a selection argument. This belongs to the storage step before B-3.

## 8. Unresolved items

1. Real company KMZ samples (5–10, shared privately) — needed to settle the vertex/size limits, the snapping/tolerance policy, coordinate syntax tolerance and internal-lines scope.
2. The overlap tolerance for adjacent lots (§6). This is an owner/supervisor decision informed by samples.
3. Whether geometry validation should ever use GEOS in the cloud (§6). The recommendation is no for now.
4. How geometry travels to the map. At the limit, one result is ~2.8 MB (§4). This needs the contract's segmentation or private-delivery decision before B-2/B-3 integration.
5. Storage provider comparison redo (§7), before B-3.
6. Mapping of parser output names to A's DTO (`ubicacion.geometria` vs. `geometria`; `punto_interior` replaces the preparation report's `punto_simbolo`). For the consolidated contract.

## 9. Next step

Waiting for the consolidated shared contract. B-2 (map boundaries) and later packets start only when the supervisor issues them. Nothing here depends on a storage account or the unfinished table.

Sources: [Google KMZ guidance](https://developers.google.com/kml/documentation/kmzarchives), [KML reference](https://developers.google.com/kml/documentation/kmlreference), [Vercel function limits](https://vercel.com/docs/functions/limitations), [`vercel` on PyPI](https://pypi.org/project/vercel/), [Vercel Python SDK changelog](https://vercel.com/changelog/vercel-python-sdk-in-beta).
