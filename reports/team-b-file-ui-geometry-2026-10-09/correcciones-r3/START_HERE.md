# 3B corrections R3-B1 to R3-B5 (same draft PR #28)

Team B handback for supervisory review. The instructions are in
`reports/round-3-review-2026-10-12/` (START_HERE, TEAM_B) at supervisor commit
`341c83036d7a861e88a1b3d28f6e3359ada057a2`. The original 3B handback in the
parent folder stays as it was. This folder adds the corrections, and the
contract changes listed below take precedence over `../COMPONENTES.md`.

## Heads

| What | Commit |
|---|---|
| Reviewed head (start) | `01d64541e929009ea2d149e3c6f5980805c76c73` |
| Regressions, failing on the reviewed head | `2cfa8b5` |
| Corrections | **code head** `f9510158024e2ef57eff70aaa8ea97eb9c29436c` |
| Report (this folder) | the final head of PR #28, given in its description |
| **Candidate for A** | the final head of PR #28 with exact-head CI, given in its description |

All commits are additive on `claude/team-b/file-ui-geometry-client`: no
reset, rebase or force push. A's branch was not merged or consumed. #21, #23,
#25, C1/#27 and frozen #24 are unchanged.

## Scope of the diff (reviewed head → code head)

| File | Change |
|---|---|
| `web/components/archivos/subida.js` | Upload lifetime (B1), access loss (B2), the `interrumpido` phase and completion validation (B3), object permits through `crearTurno` (B4) |
| `web/components/archivos/detalle.js` | Scope-loss teardown and host callbacks (B2) |
| `web/components/archivos/index.js` | Factory uses `crearTurno` (B4) |
| `web/lib/cargadorGeometrias.js` | Captured private scope kept through digest, install and reuse (B5) |
| `web/lib/archivos.js` | Scope re-checked after reading the PUT reply (B5 audit) |
| `tests/js/archivosCorrecciones.test.mjs` | 30 node regressions (25 defect cases, 5 controls) |
| `tests/e2e/archivos-alcance.mjs` | 8 browser journeys on the real mounted server |

No change to the server, auth, schema, dispatcher, renderer, A's host, the
shared API or the store. No new dependency, worker, cache or E5.

## Per finding

### R3-B1 · Cancellation cannot outlive its upload

**Cause.** `cancelar()` checked liveness only on entry. It waited for the
step, then sent the start replay and the cancel request with no signal, and
`abortar()` could not reach either of them.

**Correction.** Each upload has one lifetime `AbortController`. Every step,
the start replay and the cancel request carry that lifetime. `cancelar()`
re-checks it after each wait and before each send. After `abortar()`, nothing
is sent, shown or reported. An aborted replay counts as teardown, not as
proof that the start never happened.

**Regressions.** Node tests destroy the upload at three points: while the
cancellation waits for the PUT, during the ambiguous-start replay, and while
the cancel request is in flight. Each case runs with a same-account and a
different-account re-entry, and once through the real client. All show zero
requests under the new identity and zero callbacks after teardown. A
live-scope control proves a cancel still reaches the server once, with the
signal. The browser journey "cerrar el detalle mientras la cancelación
espera" clicks Cancel and closes the detail in the same task: no write
leaves the page afterwards.

**Supervisor probe `cancel_after_destroy`:** `cancelCalls` went from one
call under `new` with no signal to `[]`.

### R3-B2 · Upload scope loss reaches teardown and the host

**Cause.** Upload errors became local phases only. They never reached the
mount's `fallo()`/`onError` path.

**Correction.**
- **Subida.** A 404 from the start, PUT, completion, retry, cancellation or
  start replay calls `alPerderAcceso(error)` once and ends the upload. So
  does a write-right loss (403 `forbidden`, 409
  `terreno_archivado`/`base_archivada`).
- **Mount on 404.** The mount aborts its lifetime (lists, panels, downloads,
  actions). It aborts and uncounts its uploads, closes its dialogs, revokes
  its object URLs and clears every private list and upload row. It hides the
  write controls and becomes inert. Then it calls
  `onError({codigo: "no_encontrado"})` and `onCambio`.
- **Write-right loss.** The upload ends, readable content stays, and the
  host gets `onError({codigo})` and `onCambio`, so it revalidates the
  record's read-only state.
- **401** keeps the bridge's shared expiry path. Network and parser failures
  stay ordinary.

**Regressions.** Node tests cover 404 at the start, PUT, completion, retry
and cancellation, plus the write-right losses. Neither 401 nor network
failures trigger the callback, and nothing fires after teardown. The
browser journeys use the real mounted server and real administrator API, and
hold one request with a Playwright route that continues it unchanged:
- grant revoked during completion, after the start's refreshes settled;
- grant revoked during the PUT;
- terrain transferred to a base without the grant during completion;
- explicit cancellation after revocation;
- terrain archived during completion, which preserves readable content;
- a live control.

Each scope-loss journey checks the host callbacks, an empty private DOM, the
absent filename, hidden write controls and **zero** widget requests in the
following second. The harness host is passive on purpose, so the widget's
own teardown is what is measured.

**Supervisor probe `real_upload_scope_loss`.** This needs A's host, so it was
re-run only as a diagnostic: a separate archive of A's `0e9e2c1` with B's
five corrected modules copied in (see below). Results: `rowStillPresent`
1 → 0, `detailStillOpen` 1 → 0, `privateFilenameStillPresent` true → false.
The completion is still 404, correctly. A's host already removes the row and
closes its dialogs on `no_encontrado`, so **no interface change is requested
from A.** A owns the accepted combined run.

### R3-B3 · Recovery state agrees with the actions offered

**Cause.**
- `contenido_temporal_ausente` and `almacen_no_disponible` became `fallido`,
  which is terminal. The terminal phase dropped the cancel action and the
  pending count, while the state still said retryable and cancellable.
- `terminar()` marked the upload done before validating the reply. An
  incomplete success reply offered a retry that did nothing.

**Correction.**
- **New phase.** `interrumpido` is non-terminal: the server version is still
  pending after a failed step. It covers temporary content loss, an
  unavailable store (which honors a retry hint), and any refused step after
  the version exists. It stays counted and cancellable, and is retryable
  where safe.
- **Completion replies.** A completion reply must state a resolved outcome:
  a known version state and, for an available KMZ, a known attempt result.
  Otherwise it is `incierto` at completion replay. An oversized reply counts
  as unreadable too.
- **No automatic loop.** Retry is by hand, and it never re-sends content or
  starts a new version.
- **Terminal.** Only confirmed outcomes are terminal: verified, failed,
  cancelled, expired, or access lost.

**Regressions** cover temporary failures in both directions (cancelled, then
retried to `listo`), the incomplete JSON `{}`, an unknown state, a KMZ reply
without its attempt, an oversized reply, the retry hint and deadline, and a
refused PUT that stays cancellable. Controls show confirmed terminal
outcomes stay terminal with no cancellation.

**Supervisor probes.**
- `retryable_failure_cannot_cancel`: from `fallido`, 0 cancels to
  `interrumpido`, 1 cancel.
- `uncertain_completion_replay`: completion calls went from 1 to 2. The
  probe's server answers `{}` forever, so the upload correctly stays
  `incierto`.

### R3-B4 · The pipeline permit outlives unabortable work

**Cause.** `abortar()` released the factory permit while a file read or a
SHA-256 digest was still running.

**Correction.** `crearTurno()` hands out object permits, so a stale holder
cannot release another's permit. `abortar()` stops UI and network use at
once, but the permit is released exactly once, when the step in flight has
settled. A second upload meanwhile is refused with the existing "Otra
subida está en curso" message (bounded and user-driven, never queued).

**Regressions.**
- A delayed read and a delayed digest, each with destroy then a new upload.
- Six destroy-and-recreate cycles in one factory.
- The stale-permit case.
- Cleanup back to an idle turn.

**Supervisor probe `one_hash_pipeline`:** `maxConcurrentReads` went from 2
to 1.

### R3-B5 · Geometry scope kept through digest, install and reuse

**Cause.**
- The post-digest check ignored the bridge's captured private signal.
- The ready body did not record the scope that authorized it.

**Correction.**
- **Through install.** Every private signal the bridge returned for a load
  is kept. They are checked after each chunk, after the digest, after the
  parse and again right before install.
- **Ready body.** It keeps those signals and is dropped as soon as one of
  them aborts: listeners are released with the body, and reuse is
  re-checked.
- **Host duty unchanged.** `reset()` and `destroy()` remain the host's duty.
- **Client audit.** `subir()` now re-checks the scope after reading the PUT
  reply. The other client paths already did; an error read after the scope
  ended was already an AbortError.

**Regressions.**
- The scope ends during the digest, and right after the parse (before
  install).
- A ready body is dropped when its scope ends and reloads in a new scope.
- A live-scope reuse control answers without network.
- The selection and waiting-slot cases still pass.
- The PUT-read audit.

**Supervisor probe `private_scope_ends_during_digest`:** went from
`resolved, listos=1` to `AbortError, listos=0`.

## Contract changes for A (supersede ../COMPONENTES.md on these points)

- **`mountDetalle` on 404.** A 404 from any request of the mount, uploads
  included, clears the mount and leaves it inert. It then calls
  `onError({codigo: "no_encontrado"})` and `onCambio({terrenoId})`. The host
  should revalidate, and A's host already removes the row and closes its
  dialogs. Previously only list, panel and download 404s did this, and did
  not stop uploads.
- **`mountDetalle` on write-right loss.** For 403 `forbidden`, 409
  `terreno_archivado` or `base_archivada`, the mount calls
  `onError({codigo, mensaje})` and `onCambio`. Readable content stays. The
  host refreshes the record (and with it `soloLectura`).
- **New phase.** Upload rows can show `data-fase="interrumpido"`
  ("Interrumpida"). It is not terminal: retry and cancel stay available. The
  compact cell is unchanged.
- **Factory.** Behavior is unchanged for A, except that after
  `widgets.destroy()` a file read or digest still running keeps that dead
  factory's permit until it settles. A new factory is independent.
- **No change** to the factory signatures, `update`/`destroy`, the loader
  API or the bridge.

## Evidence (exact archive of the code head)

Local Linux container, Node 22.22, Python 3.13.16, Chromium 141, loopback,
fictional accounts and synthetic files, with a disposable SQLite database and
byte store. Every run used a `git archive` of the stated commit. The files are
in `evidencia/` (`antes/` = reviewed head, `despues/` = code head).

### Before: the same final regressions on the reviewed head `01d6454`

| Check | Result |
|---|---|
| Supervisor `probe_client_edges.mjs` | all five defects reproduced, identical to the supervisor's evidence |
| Supervisor `probe_upload_scope.mjs` on A's `0e9e2c1` (separate archive) | 404; row 1, open detail 1, private name visible, phase `fallido`: reproduced |
| `archivosCorrecciones.test.mjs` | **25 of 30 fail**; the 5 controls pass. Pending promises left by the defects kept the process alive until its outer timeout |
| `archivos-alcance.mjs` (browser) | **6 of 8 fail**. Five never reach the host. "Cerrar el detalle…" shows the R3-B1 defect in a real browser: `POST …/cancelar` left the page after its detail was closed. The control and the page-error check pass |

### After: code head `f951015`

| Check | Result |
|---|---|
| JavaScript `node --test tests/js/*.test.mjs` | **210/210** (C1's 136, B's 44, plus 30 new) |
| Supervisor `probe_client_edges.mjs` | `cancelCalls: []`; `interrumpido` with 1 cancel; 2 completions; max 1 concurrent read; `AbortError` with `listos: 0` |
| Scope-loss browser journeys, mounted mode | **8/8** |
| Existing browser journeys, mounted mode | **19/19** (unchanged file) |
| Near-limit 100,000 vertices | complete: sha match, 9 requests, load+verify 198 ms, draw 60 ms, zoom 19; heap 8.1 / 24.9 / 21.9 / 8.2 MiB |
| Loader mutation check (original 6) | 6/6 detected, control passes |
| New `mutaciones_r3.mjs` (10 corrections undone one at a time) | **10/10 detected**, control passes |
| Python suite, SQLite, Python 3.13 | 1,230 run, 211 skipped (Postgres), 1 failure: the known environmental `test_the_system_python_has_no_openpyxl_of_its_own` |
| `ruff check server/ tests/` / `mypy server/` | clean / clean, 54 files |

### Diagnostic overlay, not A's acceptance

This is a separate disposable archive of A's combined `0e9e2c1`, with only
B's five corrected modules from `f951015` copied in. Nothing was merged into
B's branch, and A's files were not edited.

| Check | Result |
|---|---|
| A's JavaScript suite | 181/181 |
| Supervisor `probe_upload_scope.mjs` | completion 404; **row 0, open detail 0, private name not visible** |
| A's `recorrido-completo.mjs` (SQLite) | **22/22** |

## Limits

- The real-app probe and A's 22-journey run used a **diagnostic overlay**
  (A's `0e9e2c1` plus B's five modules at the code head) in a separate
  disposable archive. They are not A's accepted combined evidence. A owns the
  corrected combined run.
- No Python service changed. Locally the Python suite ran on SQLite only;
  Postgres and Python 3.9 are left to exact-head CI (its Postgres job), not
  repeated here.
- The 100,000-vertex measurement was re-run only as a regression check of
  the loader change. It is not a memory claim.
- Screen readers are still not validated. No hosted environment was used.
- A version whose upload was destroyed mid-flight stays pending on the
  server until its owner cancels it or it expires (journey "cerrar el
  detalle…"). That is the lifecycle's rule; nothing is sent after teardown.

Stopped for supervisory review. No 4B, PR or main merge, or deployment.
