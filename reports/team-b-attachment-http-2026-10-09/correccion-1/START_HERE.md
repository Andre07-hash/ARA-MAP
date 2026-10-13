# Packet 2B — correction 1 (R2-B1)

Review: `reports/round-2-review-2026-10-09/` at `750164b6761b3c3fe160010bc4163df1b7b2389f`
(START_HERE.md, TEAM_B.md). Same draft PR #25, additive to
`2ea602a940462fe8bb7d8f0208e0e1dbee19603e`. **HTTP harness evidence, not
application-mounted endpoint acceptance.**

| What | Commit |
|---|---|
| Reviewed head | `2ea602a940462fe8bb7d8f0208e0e1dbee19603e` |
| Fix + regressions (code head) | `4b59ad9d3be4b79fb9182e16560c6202c313255c` |
| Final head | the head of PR #25, stated in its description (only this report follows) |
| Baseline #24, unchanged | `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` |

Not touched: `server/app.py`, router, auth, schema, lifecycle, SQL, geometry
wire format, harness separation. No A feature consumed. #23 and #21 unchanged.

## R2-B1 — what was wrong

`str.isdigit()` accepts `²`, `¹⁰`, `٣`, `５` and other Unicode numerals.
`int()` then either raised (`limite=²`, `desde=²` → **500** on SQLite and
Postgres) or silently converted a non-ASCII digit (`limite=٣` meant 3 for an
authorized ID while a missing ID got 404).

## Fix (`server/api/archivos.py`)

One parser, `_decimal(valor, digitos)`: ASCII `[0-9]+` by `fullmatch`, at most
`digitos` characters, before `int()`; otherwise `None`. Used by:

| Input | Bound | On anything else |
|---|---|---|
| `limite` (listar, historial, versiones, intentos) | 9 digits, then the service's 1–100 check | `400 limite_invalido` (unchanged code/message) |
| `desde` (geometry chunk) | 9 digits, then the service's alignment/size checks | `400 desplazamiento_invalido` (unchanged) |
| declared `Content-Length` on content PUT | 20 digits, must equal bytes received | `400 cuerpo_incompleto`, nothing staged (unchanged) |

Analogous parsing inspected: the service's version/attempt cursor
(`_number_cursor`) already uses an ASCII `[0-9]{1,9}` full match; the
timestamp cursor is parsed by `datetime`/`uuid` inside a narrow `ValueError`
guard; body fields are type-checked as JSON integers. No generic exception
catch was added.

Behavior kept: defaults (`limite` absent → 50, `desde` absent → 0), the
1–100 range, 512 KiB alignment, 16 MiB ceiling, error codes and messages,
validation before any resource lookup, so the answer is the same for
authorized, out-of-scope and missing IDs, and 401 still comes first. One
deliberate widening: ASCII leading zeros up to 9 digits (`limite=000000001`)
are now read as their value; the old 4-character cap rejected them. An empty
value (`?limite=`, `?desde=`) is dropped by the shared router's `parse_qs` and
means the default, before and after (not changed here).

## Regressions (real HTTP, SQLite and disposable Postgres)

In `tests/test_archivos_http.py` (`HTTPChecks`, so both databases):

- `test_limite_accepts_only_bounded_ascii_decimals_on_every_paged_route`:
  all four paged routes × `² ³ ¹⁰ ٣ ５ ߁ +5 -1 -0 " 5" "5 " 1e2 0x10 1_0 1.0
  5\x00`, 10 nines, 5,000 nines, `0`, `101`. Every one gives one
  byte-identical `400 limite_invalido` for authorized, admin-only and missing
  resources; 401 without a session. Valid `1`, `100`, `0050`, `000000001`,
  empty and absent return 200 within bounds. File rows unchanged.
- `test_limite_pages_exactly_at_valid_ascii_bounds`: `limite=01` pages one
  item with a cursor; `limite=3` returns all three.
- `test_desde_accepts_only_bounded_ascii_aligned_offsets`: the same invalid
  set plus 10 zeros, `524288.0`, `1`, `524287` → identical
  `400 desplazamiento_invalido` across the three resource states, 401 without
  a session; default, empty, `0`, `000000000`, `524288` and `000524288` serve
  the exact chunks; full reassembly hash still matches. Rows unchanged.
- `test_content_length_is_checked_as_ascii_decimal_too` (raw socket): a
  signed `+N` length is `400 cuerpo_incompleto` and stages nothing; a
  20-digit zero-padded length is accepted.

## Before / after

| Evidence | Before (`2ea602a`) | After (`4b59ad9`) |
|---|---|---|
| Review's `probe_inputs.py sqlite b` | 3 × 500, `ValueError` in stderr | 3 × controlled 400, empty stderr |
| Review's `probe_inputs.py postgres b` | 3 × 500, `ValueError` in stderr | 3 × controlled 400, empty stderr |
| New regressions, SQLite | 31 subtest failures (500s; `٣`/`߁`/`５` converted; `000000001`) | 4/4 OK |
| New regressions, Postgres | same 31 failures | 4/4 OK |

Files: `evidencia/before-*.jsonl` / `after-*.jsonl` (+ stderr),
`evidencia/new-tests-on-before-*.log` (the new tests run unchanged against
the old code).

## Verification at code head `4b59ad9`

Local container, synthetic data, disposable Postgres 16.15.

| Check | Result |
|---|---|
| `tests.test_archivos_http` + `tests.test_composicion_ronda2`, SQLite + Postgres, Python 3.13 | 63/63 OK, 0 skipped |
| same, Python 3.9.25 | 63 run, OK, 30 Postgres skips |
| Full suite, SQLite, Python 3.13 | 1,182 run, 194 skipped, 1 environmental failure |
| Full suite, SQLite, Python 3.9.25 | 1,182 run, 194 skipped, 1 environmental failure |
| Full suite, disposable Postgres | 1,182 run, 0 skipped, 1 environmental failure |
| JavaScript | 120/120 |
| `mypy server/` | clean, 51 files |
| `ruff` on the 2B files and report folder | clean |
| `ruff check server/ tests/` | only the carried-in #22 finding (`tests/test_registros_maestra.py:562`) |

The environmental failure is the same disclosed
`test_the_system_python_has_no_openpyxl_of_its_own` (this container's system
Python has openpyxl). `./verificar.sh` was not run as a script (no zsh); its
components were run directly. Exact-head CI is linked in the PR. Renderer,
research and large-memory matrices were not repeated (inputs unchanged).

## R-5 and a related observation for A

- R-5 is confirmed and assigned to A as R2-A1; INTEGRATION_REQUESTS.md now
  says so. Not patched here; R-1–R-4 stay reserved for 3A.
- **R-7 (new, A-owned):** inspecting analogous parsing showed that the
  dispatcher's own `int(Content-Length)` gives **500** for `²`. It also does
  not bound `-1`: `rfile.read(-1)` read a 26 MiB anonymous login body,
  larger than `MAX_BODY`, until half-close. Probe: `probe_content_length.py`;
  output: `evidencia/dispatcher-content-length.jsonl`. Details and a
  suggested change are in INTEGRATION_REQUESTS.md R-7. Not patched here.

Stopped for review: no 3B, no merge, no deployment.
