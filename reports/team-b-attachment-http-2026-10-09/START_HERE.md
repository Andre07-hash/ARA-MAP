# Packet 2B — attachment HTTP handlers and bounded geometry delivery

Team B handback for supervisory review. **HTTP harness evidence, not
application-mounted endpoint acceptance**: the routes are not registered in
`server/app.py`. Mounting is 3A (see INTEGRATION_REQUESTS.md).

> **Correction 1 (R2-B1, review `750164b`):** see
> [correccion-1/START_HERE.md](correccion-1/START_HERE.md). It adds code head
> `4b59ad9` on top of the reviewed head `2ea602a`. The rest of this page
> describes the original handback at `2ea602a` and is kept as it was.
>
> **Correction 2 (R2-B2, review `f2939ed`):** test-only. See
> [correccion-2/START_HERE.md](correccion-2/START_HERE.md); code head `4dcf665`.

## Heads

| What | Commit |
|---|---|
| Instruction packet | `13840c0deaf7f78f79609126115d03769e27fd0a` (`reports/round-2-instructions-2026-10-09/`) |
| Source (accepted 1B, PR #23) | `a9dc8af8cc511bde0a67168da335398353b80aa6` |
| 2B code, started from #23 | `39f355a7a0602e03e143d6d15c40b208ac7bad86` handlers, reads, harness, tests |
| | `dd5d53c6992506e3eed9e1f5513a392d71e9f5d0` deterministic KMZ fixtures |
| Round 2 checkpoint (PR #24, recorded in its description, CI green) | `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` |
| Ordinary `--no-ff` merge of that exact checkpoint | `621ed1bf582c85c3321a76e7492e383c2e4fd3d1` (no conflicts) |
| Code head after the merge | `7887af5` — Content-Disposition unit tests (test only) |
| Final head | the head of this PR, stated in its description (this report is the only later change) |

Branch `claude/team-b/attachment-http`. The PR targets
`claude/integration/round-2-baseline`. PR #23 and its branch are unchanged.

## Scope

Diff against the checkpoint is exactly six files plus this folder:

| File | What |
|---|---|
| `server/api/archivos.py` (new) | 15 handlers, `RUTAS` registry list, `POSTS_DE_LECTURA`, store provider (`configurar_almacen`, `almacen_local`), `disposicion` |
| `server/api/binario.py` (new) | `RespuestaBinaria`: typed binary result (status, type, headers, body) |
| `server/archivos.py` | 2B reads appended over the accepted lifecycle: `versiones`, `intentos`, `intento`, `descargar`, `metadatos_geometrias`, `fragmento_geometria` |
| `server/repo/archivos.py` | the SQL for those reads; byte-range chunk queries for SQLite and Postgres |
| `tests/archivos_http_harness.py` (new) | isolated harness: temporary registration on the real router, one-method binary adapter |
| `tests/test_archivos_http.py` (new) | 25 real-HTTP tests per database (SQLite, disposable Postgres) + 3 header tests |

Not touched: `server/app.py`, `server/router.py`, `server/auth.py`, schema
(stays 10), shared configuration, `api/index.py`, terrain DTOs, frontend,
renderer. No cloud storage, no E5, no second state machine: every write goes
through the accepted `server/archivos.py` lifecycle and its guards.

## Read in this order

1. [API_CONTRACT.md](API_CONTRACT.md) — every route: method, path,
   capability, body, result, headers, errors; geometry protocol; fictional
   examples.
2. [INTEGRATION_REQUESTS.md](INTEGRATION_REQUESTS.md) — A-owned requests:
   R-1 route registration, R-2 `RespuestaBinaria` dispatcher branch, R-3 store
   wiring, R-4 read-only exemption, **R-5 finding** (read-only / foreign-origin
   refusals leave the body unread on a kept-alive connection; reproduced),
   R-6 known transport limits.
3. `evidencia/` — logs from the combined merge (`combinado/`) and the final
   code head (`final/`), measurements and the R-5 reproducer output.

## Evidence

All local, in a Linux container; synthetic bytes and disposable databases
only. No hosted environment, no browser.

| Check | Where | Result |
|---|---|---|
| Full Python suite, SQLite, Python 3.13 | combined `621ed1b` | 1,171 run, 190 skipped (Postgres), **1 environmental failure** |
| Full Python suite, SQLite, Python 3.9.25 (floor) | combined `621ed1b` | same: 1,171 run, 190 skipped, 1 environmental failure |
| Full Python suite, disposable local Postgres 16.15 | combined `621ed1b` | 1,171 run, 0 skipped, 1 environmental failure |
| `tests.test_archivos_http` + `tests.test_composicion_ronda2`, Postgres | combined `621ed1b` | 52/52 OK, 0 skipped |
| same, Python 3.9.25 | combined `621ed1b` | 52 OK (26 Postgres skips) |
| `tests.test_archivos_http.Disposicion`, Python 3.13 and 3.9 | `7887af5` | 3/3 OK |
| Final full suites | `7887af5` | see "Final head re-run" below |
| JavaScript `node --test tests/js/*.test.mjs` | combined | 120/120 |
| `mypy server/` (2.4.0) | combined | clean, 51 files |
| `ruff check` (0.16.10) on the 2B files and this folder | combined | clean |
| `ruff check server/ tests/` | combined | 1 finding carried in from accepted #22 (`tests/test_registros_maestra.py:562`, UP031), also listed in PR #24; not B's file, not repaired |
| Coverage (Postgres run) | combined | 96 % total; `api/archivos.py` 96 %, `api/binario.py` 100 %, `archivos.py` 88 %, `repo/archivos.py` 94 % |
| R-5 reproducer | combined | defect reproduced: two responses on one connection, `403` then `200` |

The environmental failure is
`tests.test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`:
this container's system Python has openpyxl installed
(`evidencia/environment-openpyxl.txt`). It fails the same way at the
checkpoint and is unrelated to 2B; on macOS it passes (PR #24).

`./verificar.sh` itself was not run (the container has no zsh); its components
were run directly as above. CI on the exact final head is linked in the PR.

### Final head re-run

At code head `7887af58316ad3dcbd0a8d0ff1f757de48235c96` (the merge plus the
three header tests); logs in `evidencia/final/`:

| Check | Result |
|---|---|
| Full suite, SQLite, Python 3.13 | 1,174 run, 190 skipped, 1 environmental failure (same test) |
| Full suite, SQLite, Python 3.9.25 | 1,174 run, 190 skipped, 1 environmental failure (same test) |
| Full suite, disposable Postgres 16.15 | 1,174 run, 0 skipped, 1 environmental failure (same test) |
| JavaScript | 120/120 |
| `mypy server/` | clean, 51 files |
| `ruff check` on the 2B files and this folder | clean |
| `ruff check server/ tests/` | only the carried-in #22 finding |
| Environmental test at the checkpoint `7117f57` alone | fails the same way (`checkpoint-environmental-failure.log`) |

### Measurements (near-limit, SQLite, local store, combined tree)

`medir_http.py` drives the harness over loopback with tracemalloc. Server
and client share one process, so each peak includes the client's copy of the
request or response. Peaks are Python allocations, not RSS.

`evidencia/medir_http.json`, run on the combined tree (B's code there is
identical to `7887af5`):

| Phase | Request / response bytes | Peak MiB | SQL statements | Time |
|---|---|---|---|---|
| PDF exactly 25 MiB: PUT content | 26,214,400 in | 27.02 | 11 | 0.08 s |
| PDF: complete | — | 0.15 | 32 | 0.11 s |
| PDF: download (hash identical) | 26,214,400 out | 75.19 | 6 | 0.13 s |
| KMZ just under 20 MiB: PUT content | 20,968,109 in | 22.02 | 11 | 0.06 s |
| KMZ: complete (parsed, `listo`) | — | 42.44 | 36 | 0.15 s |
| KMZ: download (hash identical) | 20,968,109 out | 66.38 | 6 | 0.10 s |
| Parser-limit KMZ (100,000 vertices, 20,000 parts): complete | 439,185 in | 46.02 | 36 | 8.7 s untraced (87 s under tracemalloc) |
| Geometry metadata, 1 id | — | 0.04 | 9 | 0.01 s |
| Geometry metadata, 50 ids | 2,769 out | 0.04 | 9 | 0.01 s |
| Geometry chunk (each of 7 full chunks) | 524,288 out | ≤ 1.02 | 7 | ≤ 0.02 s |
| Geometry final chunk (whole-body hash) | 447,123 out | 1.46 | 14 | 0.02 s |

The 4,117,139-byte geometry arrives in 8 chunks and its reassembled SHA-256
matches. No request loads the whole GeoJSON: chunks read a byte range in SQL,
and the final chunk hashes range by range. Download peaks include the
in-process client's copy plus the harness's `bytes()` copy (R-2 notes that a
production branch can skip that copy). An earlier run at `39f355a` gave the
same peaks and 11.0 s untraced; timing varies with the machine's load.

## What the tests show

Through real loopback connections, real cookie sessions and the unmodified
dispatcher (binary routes add only the declared one-method adapter):

- PDF and KMZ round trips: start → raw PUT → complete → download with
  byte/hash identity; single-candidate auto-activation; explicit
  multi-candidate selection and activation; retained-version activation; a
  failed replacement keeps the active layout; terrain versions untouched.
- Cancel, retire, retired content still readable in scope; idempotent replay
  of start, selection, activation and retirement; completion replay.
- Non-disclosure: missing, out-of-scope, wrong-kind and other-account-pending
  IDs give byte-identical `404` on every route; dead sessions (logout, expiry,
  role change, deactivation) get `401` for existing and missing IDs alike.
- Grants, multiple bases, admins, archived terrain/base policy, pending
  privacy.
- Size equality and +1 for PDF and KMZ, declared vs actual size, type, hash,
  ZIP signature, `MAX_BODY + 1` refused from `Content-Length`, malformed
  bodies/cursors/limits/offsets, truncated upload stages nothing.
- Geometry: batch order/dedupe/validation and the 128 KiB worst case, mixed
  authorized/missing/out-of-scope batches, strict aligned offsets, chunks
  that split UTF-8 sequences reassemble exactly, final chunk identified and
  hashed, 16 MiB ceiling, corrupt stored bodies refused, replacement /
  retirement / revocation between chunks, a 100,000-vertex parser-limit
  geometry delivered within bounds.
- Races, both orders: scope loss during slow completion, finalization
  boundary first then revocation, cancellation and retirement during slow
  work; busy is a controlled `503 ocupado`, never retried; an ambiguous
  completion is resolved by replay.

## Limits (stated, not hidden)

- **Not mounted.** Endpoint acceptance needs 3A's registration (R-1 to R-4).
- **Not streaming.** The dispatcher buffers up to `MAX_BODY` (25 MiB) before
  the handler; the handler feeds the store bounded chunks after that. Not a
  hosted size guarantee.
- JSON successes are `200` only (no `201`). No range or conditional requests;
  every request reauthorizes. Already delivered bytes cannot be recalled.
- A parser-limit KMZ completion spends 9–11 s (measured locally) in the synchronous parser
  inside the request, without holding a write transaction.
- Local/fake store only; hosted content routes answer `503
  almacen_no_configurado` until a cloud storage packet.
- No renderer change, so no browser or renderer matrix was run.

## Remaining work

- **3A (A-owned mounting):** apply R-1 to R-4, and decide R-5. Then run
  `tests.test_archivos_http` against the mounted table (drop the harness's
  temporary registration) on SQLite and Postgres. The Vercel adapter needs
  the R-2 branch only when hosted transport is released.
- **3B (B, not started):** client work over this frozen contract — attachment
  panel and upload flow, and the geometry widget that consumes the metadata
  batch and chunk protocol (INTERFACES.md handoff). Not begun, per the packet.
