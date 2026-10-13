# Round 3 checkpoint C1 — attachments mounted in the application

A development checkpoint so 3A and 3B build on one tested commit: accepted 2A
and accepted 2B combined, plus the small early 3A work that mounts B's
attachment HTTP in the real application. **Not a merge approval, not a release
candidate, and deliberately not a merge-only baseline.** No grid, widget or map
work is in it.

- Instruction commit: `4682793f290718cfd49fd661ef16f2af4448fafb`,
  `reports/round-3-instructions-2026-10-09/` (START_HERE, INTERFACES, TEAM_A).
- Branch `claude/integration/round-3-baseline`; draft PR targets
  `claude/integration/round-2-baseline`.
- **The one frozen C1 SHA for Team B is the head of that draft PR, stated in
  its description** (this file cannot name its own commit). Merge that exact
  SHA with an ordinary merge, not "the branch tip later".
- Frozen after publication. A correction, if ever needed, is an additive
  replacement checkpoint with a new pin and an explicit handoff.

## Source manifest

| # | Input | PR | Exact commit | How it entered |
|---|---|---|---|---|
| 0 | 2A editable grid + corrected dispatcher | #26 | `32a2a55e4a7417499cc384109bd44666e7a568cb` | Branch start |
| 1 | 2B attachment HTTP + corrected privacy tests | #25 | `bf4c6a694ca95087368bb2d89325d7a240a7b676` | Ordinary `--no-ff` merge |

**Pure composition head: `72553e4b471e6744392afa9711c13d737f5d906a`**
(parents `32a2a55…` and `bf4c6a6…`). No textual conflict. Everything after it
on this branch is the C1 work below. #20–#26 and their branches are unchanged.
Not included: research prototypes, the hosted adapter branch, parked Excel.
Schema version stays **10**; nothing here touches the schema.

## What C1 adds (all A-owned unless marked)

| File | Change |
|---|---|
| `server/app.py` | R-1: registers exactly `api_archivos.RUTAS`, in its order, after the earlier routes (75 routes in total, 15 new, all private with a capability). R-2: a `RespuestaBinaria` result is sent with its own status, type and headers, ahead of the unchanged XLSX tuple branch. R-4: `READ_ONLY_POSTS` gains exactly `POSTS_DE_LECTURA`. R-3: `raiz_de_archivos()` / `configurar_archivos()`, called by `serve()` only. One correction to accepted R2-A5, below. |
| `web/lib/api.js` | `peticionPrivada`, as INTERFACES §2 defines it. Existing callers and their never-settling cancellation are untouched. |
| `tests/test_montaje_archivos.py` (new) | The mounted-server regression: registry and order, anonymous refusal of all 15, disk store wiring, exact binary bytes/headers, read-only exemption and mutation refusal, malformed framing on an attachment route. |
| `tests/js/peticionPrivada.test.mjs` (new) | The bridge against a real local HTTP server. |
| `tests/test_despachador_cuerpos.py` | One added regression (multipart type is not a framing defect). |
| `tests/test_roles_y_bases.py` | The A-owned capability matrix: the attachment routes get their own expectation (see changed assertions). |
| `tests/archivos_http_harness.py`, `tests/test_archivos_http.py` (B's; the C1-only exception) | Adapted to production registration; every changed assertion is listed below. |

No B production module was edited: `server/api/archivos.py`,
`server/api/binario.py`, `server/archivos.py`, `server/repo/archivos.py`,
`server/almacen.py`, `server/kmz.py` and `tests/test_archivos.py` are
byte-identical to `bf4c6a6…`. `api/index.py` (the cloud adapter) is unchanged.

### Local byte store (R-3)

Wired by `serve()` — the local server's startup — and by nothing else. The
cloud adapter never calls it.

- `ARA_MAP_ARCHIVOS=<folder>` names the root explicitly.
- Without it, a local **SQLite** database gets the sibling folder `archivos`
  next to the database file (`ARA_MAP_DB` or the default).
- Without it, a **Postgres** database (`ARA_MAP_DATABASE_URL`) gets **no**
  store: a local server pointed at a shared database never starts a byte store
  on whatever machine runs it.
- Only that one directory is created (`mkdir`, mode `0700`, never parents). The
  provider's own path and symlink safeguards are unchanged.
- If it cannot be created or opened, nothing is wired: the console says so and
  content routes answer the existing controlled `503 almacen_no_configurado`.
  There is no in-memory stand-in anywhere in production code.
- The console's startup lines now include `Archivos: <folder | reason>`.

### A defect in accepted R2-A5, found by mounting, corrected here

R2-A5 refused any request whose header block the standard parser reported as
defective. That parser also reports a defect for a `multipart/...`
`Content-Type` with no parts — about a body it never saw, not about the
headers — so every multipart request got the framing 400 instead of reaching
its handler (B's upload handler answers 415 for it). `_read_body` now counts
only the two header-block defects (`HeaderDefect`, which includes the invalid
header line, and `MissingHeaderBodySeparatorDefect`). All 22 R2-A5 socket cases
still pass unchanged, plus a new one for the multipart type. No other
dispatcher protection changed.

### Changed assertions in B's test files (the C1-only exception)

`tests/archivos_http_harness.py`: `HandlerBinario` (the `_send_json` binary
override) and `rutas_registradas` (temporary route injection and
`READ_ONLY_POSTS` patch) are **removed**. `Servidor` and `Cliente` are
unchanged; the module docstring says what it now is.

`tests/test_archivos_http.py` (29 tests per backend before, 30 after; 3 more are backend-independent):

1. `setUp`: one `Servidor(app_module.Handler)` for JSON and binary; no route
   registration. Every existing test now runs against the mounted application.
2. `test_content_length_is_checked_as_ascii_decimal_too`, mounted layer: a
   signed length and a 20-digit zero-padded length are now **400 from the
   dispatcher** (no `detalle` code), nothing staged — was `400
   cuerpo_incompleto` and `200` respectively from the handler. Added: a
   12-digit zero-padded length is `200` and staged.
3. New `test_handler_alone_validates_the_declared_length_and_encoding`: the
   handler called directly, without the dispatcher, keeps its own coverage —
   signed, non-ASCII, wrong and absent length are `400 cuerpo_incompleto`;
   `Transfer-Encoding` is `411 longitud_requerida`; a 20-digit padded length is
   accepted. These are handler promises, not mounted-endpoint promises.
4. `test_metadata_post_needs_its_read_only_exemption`: read-only mode now
   answers the metadata POST `200` through the application's own
   `READ_ONLY_POSTS` (asserted to be `/api/exportar` plus `POSTS_DE_LECTURA`);
   completion stays `403`; the negative control patches the exemption **out**
   and gets `403`. Before, the test patched it in.

No lifecycle or privacy test was edited.

### Changed assertion in A's capability matrix

`tests/test_roles_y_bases.py::test_the_dispatcher_enforces_each_routes_capability`
walks every registered route with an empty request and expected `404
not_found` for an operator with no grant. Attachment routes validate the
request's own shape first (idempotency key, media type, store), so an empty
request is refused for that instead. For those 15 routes the test now asserts
anonymous `401`, a refusal (`>= 400`, not `403`) for the no-grant operator, and
no `401/403` for the administrator. Denial of well-formed out-of-scope requests
is asserted in B's suite and in `test_montaje_archivos.py` (download `404`).

## Mounted HTTP behaviour to rely on

- One `Content-Length` of 1–12 ASCII digits; any `Transfer-Encoding`, a
  repeated/empty/signed/longer length or a malformed header line is `400` and
  the connection closes; a declared body over 25 MiB is `413` and closes. The
  handler-only examples (TE → 411, 20-digit length → 200) are not reachable
  through the mounted endpoints.
- A browser sets `Content-Length` itself for a `File`/`Blob`/bytes body.
- Read-only mode: only `POST /api/archivos/geometrias/metadatos` (and the old
  export) pass; every attachment mutation is `403`.
- Downloads and geometry chunks: exact bytes, the handler's status and type,
  `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox`, and the handler's
  `Content-Disposition`. XLSX export is unchanged.

## `peticionPrivada` (INTERFACES §2)

`import { peticionPrivada } from "web/lib/api.js"`:

```text
peticionPrivada(ruta, {method='GET', headers, body, signal}={})
  -> Promise<{response: Response, signal: AbortSignal}>
```

- `ruta` must be a same-origin `/api/...` path (one leading slash, no
  backslash, space or control character); anything else throws `TypeError`
  before a request is made.
- Sent with `credentials: "same-origin"` and `cache: "no-store"`; `body` goes
  as given; the response is returned undecoded and unread.
- The returned `signal` is the private session current at call time combined
  with the caller's, and aborts body reads still in flight when that session
  ends (logout, expiry, another account) — verified with a stalled real body.
- Cancelled or obsolete calls **reject with `AbortError`**.
- A 401 calls the existing session-expiry handler first, then rejects
  (`AbortError` once the scope has ended; otherwise an error with
  `status: 401`). It never resolves.
- Other non-2xx responses are returned for the caller to decode.
- An unreachable server rejects with the existing readable network error
  (`error.red === true`).

It is not a replacement for a host's own destroy/reset.

## Verification on the C1 head

Run on this machine (macOS, loopback only, synthetic accounts and data) on
the final C1 code; the last commit after these runs changes only this report.

| Check | Result |
|---|---|
| `./verificar.sh` — Python suite, SQLite | 1,230 tests OK (211 skipped: they need Postgres) |
| `./verificar.sh` — full suite on Python 3.9.6 | OK |
| `./verificar.sh` — JavaScript | 136/136 (128 before + 8 for the bridge) |
| Full suite, disposable local Postgres 16 (UTF-8) | 1,230 tests OK, zero skipped |
| `ruff check server/ tests/` | clean |
| `mypy server/` | clean (54 files) |
| Mount regression `tests/test_montaje_archivos.py` | 8 tests OK, also on Python 3.9.6 |
| GitHub Actions on the exact head | see the draft PR; the SHA B merges is the one with both checks green |

A one-line type widening (`_send` accepts `bytes | bytearray`, so the binary
branch passes the handler's buffer without a copy) was made after the two full
runs; the mount, dispatcher and API modules were rerun on both interpreters
after it, and CI runs everything on the exact head.

Counts against the inputs: 2A alone had 1,154 Python tests; with 2B's files
and the C1 tests the combined suite is 1,230.

## Startup, for a developer or Team B

```bash
ARA_MAP_DB=/tmp/ara-r3/prueba.db python3 -m server.app      # folder /tmp/ara-r3 must exist
# console: "Archivos: /tmp/ara-r3/archivos" (created, mode 0700)
python3 tests/e2e/tabla_servidor.py --puerto 8433            # disposable server + fictional accounts
```

`tabla_servidor.py` (accounts ada/alan administrators, olga… operators,
password = the test fixture's) starts the same `serve()`, so its temporary
database gets a sibling disk store that is deleted with it on exit.

## Limits

- Local disk storage on one machine. No cloud provider; the hosted adapter has
  the routes (it shares the router) and no store, so content routes there
  answer `503 almacen_no_configurado`. That path was not exercised on a hosted
  environment.
- The dispatcher still buffers a whole body (25 MiB limit) in memory; this is
  not streaming.
- Mount tests run on SQLite; B's 30 HTTP tests run mounted on both SQLite and
  disposable Postgres. No browser test is part of C1 (3A/3B add them).
- `peticionPrivada` is tested under Node's fetch against a real loopback
  server, not yet in a browser.

Stop: C1 is published for B to consume. Nothing was merged to a PR base or
main, nothing deployed, no real account or data used.
