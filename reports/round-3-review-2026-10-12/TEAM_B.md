# Team B — bounded corrections to 3B, same draft PR #28

Start from your preserved head
`01d64541e929009ea2d149e3c6f5980805c76c73` on
`claude/team-b/file-ui-geometry-client`. Read START_HERE.md here. Original
Round 3 ownership/interfaces remain fixed. Do not consume A's moving feature
branch; do not edit #21/#23/#25, C1/#27, auth/schema/server or renderer. Use
additive commits, no reset, rebase or force push.

## R3-B1 · P1 · No cancellation work after destruction/scope loss

`web/components/archivos/subida.js:268–290`: `cancelar()` checks `muerta` only
on entry, aborts the active step, then yields while waiting for `ocupado`.
It subsequently calls `cliente.iniciar(...)` or `cliente.cancelar(...)`
without a lifetime signal or a renewed liveness check. `abortar()` cannot
abort those requests either. A delayed cancellation can therefore call the
bridge after teardown, capturing whatever private session is now current.

Independent probe `cancel_after_destroy`: start PUT, request cancellation,
destroy upload while cancellation waits, replace the fixture identity, settle
the PUT. Observed **one cancel call under `new`, without a signal**.

Required: cancellation and ambiguous-start replay are part of the original
upload's abortable lifetime. Recheck after every wait and before each send;
propagate that lifetime through all cancellation/replay requests. A destroyed
upload must never begin another write or publish a callback. Treat AbortError
as teardown, not evidence that start never happened. Preserve honest late
completion/cancellation/cleanup reporting.

Regression: destroy during the wait; destroy during ambiguous-start replay;
destroy during cancellation; same-account and different-account re-entry.
Show zero late requests and callbacks, plus a live-scope cancellation control
that still reaches the server exactly as required.

## R3-B2 · P1 · Upload 404 must reach private-state teardown

`subida.js:126–160` converts upload errors into local phases. Its caller in
`detalle.js:216–219` only paints `alCambiar`; upload errors do not pass through
the mount's `fallo()`/`onError` path used by downloads and lists.

Real-browser reproduction in `probe_upload_scope.mjs`: use the actual app,
upload a PDF, hold completion, let start refreshes settle, revoke the user's
grant via the real admin API, release completion. Server correctly returns
**404**. After settling: **row count 1, open detail count 1, private filename
still visible, phase `fallido`**. This differs from A's passing download/chunk
denial journeys: uploading has a separate error path.

Required: propagate sanitized scope-loss errors from start/PUT/completion,
retry and explicit cancellation through the existing widget contract, so
private resource state is cleared and the host revalidates/removes it. Stop
pending work and prevent late content from returning. Preserve 401's existing
shared expiry behavior and honest differentiation from ordinary network or
parser failures; do not solve this by logging everyone out on every failure.
Any public interface change needed must be a small explicit request to A,
not a competing edit to A's files.

Regression: real mounted harness plus a host callback test. Cover revoke and
transfer during upload at controlled boundaries, including failure after the
last successful start refresh. A will rerun the combined application probe.

## R3-B3 · P2 · Recovery state must agree with the actions offered

Two independently reproduced paths:

1. `contenido_temporal_ausente` and `almacen_no_disponible` produce
   `FASE.FALLIDO` with `reintentable=true` and potentially `cancelable=true`.
   But `FALLIDO` is unconditionally terminal: `cancelar()` returns immediately,
   the widget hides cancellation, and removes the handle from the factory's
   unfinished-upload count. Probe: pending upload with missing temporary bytes
   says retryable/cancelable yet **cancel endpoint calls = 0**. Retrying an
   operation is not the same as a confirmed terminal server failure.
2. `terminar()` sets `paso='hecho'` before validating the outcome. An incomplete
   success envelope (probe: HTTP-success JSON `{}`) sets `incierto` and offers
   retry, but `ejecutar()` immediately returns because the step is already
   `hecho`. Probe: **completion calls stay 1 after retry**. The server outcome
   is unresolved, and the UI's retry is a no-op.

Required: distinguish transient/unresolved state from confirmed terminal
version state. Keep pending handles counted until truly terminal or locally
disposed, retain valid cancellation and same-operation retry, and release
resources truthfully. An unreadable/semantically incomplete completion must
remain at completion replay, never create a new version, and not spin in an
automatic retry loop. Cover known terminal failure, temporary failure,
retry hints/deadlines, incomplete JSON outcome and successful terminal replay.

## R3-B4 · P2 · Do not release the hash pipeline while work still runs

`subida.js:312–315`: `abortar()` calls `soltarTurno()` before an outstanding
`File.arrayBuffer()` or crypto digest settles. Those operations are not
cancelled by the AbortController. Closing a mount and starting another in
the same surviving widgets factory can overlap their expensive work; repeated
close/reopen can exceed the promised single pipeline.

Probe holds the first file read, destroys that upload, then begins a second
with the same turn object: **maximum concurrent reads = 2**.

Required: prevent UI/network use immediately, but retain the shared pipeline
permit until the unabortable work actually releases its bytes. Release exactly
once; no stale operation may unlock somebody else's permit. Pending requests
remain bounded and user-controlled, not an unbounded promise/file queue.
Test delayed reads AND digests, repeated mount destruction/recreation in one
factory, and cleanup. Tiny controlled fixtures suffice; no giant allocations
or full research matrix. Do not add workers or a new rendering strategy.

## R3-B5 · P2 · Geometry digest/cache must retain private generation

`web/lib/cargadorGeometrias.js:254–277`: post-digest `vigente()` omits the
bridge's private signal. Only local/external cancellation remains checked.
The ready cache also does not retain/check the scope that authorized its body.

Probe completes all bytes, holds SHA-256, aborts the bridge's returned private
signal, then finishes digest without separately calling host destroy. Observed
**resolved body, `listos=1`**, rather than AbortError and no retained body.
This violates the frozen bridge/client contract even though A's normal host
destroy also cancels the loader and its ordinary expiry journey passed.

Required: carry the captured scope through final hashing/parse/installation
and ready-body reuse. Reject/drop obsolete bodies; reset/destroy remain required
at the host and are not replaced by this guard. Release listeners/references
without adding a new identity authority or changing the shared bridge API.
Test scope abort during final digest, immediately before install, and after a
body is ready; include a live-scope reuse control and existing selection/queue
negative cases. Also audit your attachment client's post-await scope checks
for the analogous gap (notably the successful PUT body-read return).

## Evidence and handback

- Reproduction trees: run `probe_client_edges.mjs` against your own reviewed
  `01d64541e929009ea2d149e3c6f5980805c76c73`. The real-app
  `probe_upload_scope.mjs` needs A's completed host, so reproduce that one in a
  **separate disposable archive** of
  `0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db`. Its B production modules are
  byte-identical to your reviewed head (supervisor verified). This is diagnostic
  use only: do not merge A's feature into your branch. Verify your B2 correction
  in your mounted widget harness and host-callback tests; A owns the subsequent
  corrected combined-application run.
- Reproduce these probes on the reviewed head first. Commit regressions that
  fail there, then show corrected behavior; keep the original evidence.
- Run all relevant JS tests, real mounted widget/browser cases affected by
  these paths, lint/static checks and required pre-push checks. No Python
  service change is requested; rely on exact-head repository CI for its full
  database matrix rather than repeating research or all performance runs.
- Return the same draft #28 with full reviewed/code/final SHAs, scoped diff,
  exact-head green CI, per-finding evidence and limitations. Include the named
  **green candidate SHA for A's ordinary merge**, as before. Report under a
  new corrections subfolder of your existing 3B handback.
- Stop. No 4B, PR/main merge, deploy or edits to A's branch. The owner relays
  your candidate; do not wait for A's final combined evidence to publish it.
