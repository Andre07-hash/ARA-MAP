# Team B — packet 3B: file controls and bounded geometry client

2B accepted at **`bf4c6a694ca95087368bb2d89325d7a240a7b676`**; R2-B1/B2 closed.
Read START_HERE.md and INTERFACES.md here. Preserve #25/#23/#21 and frozen #24.
Create **`claude/team-b/file-ui-geometry-client`**, a new draft, not more 2B
feature commits. Start now from accepted #25 if A's C1 is not yet published.
Build against the fixed interfaces; merge the exact tested C1 when A names it.
Do not wait for A's finished table/map integration or consume its moving branch.

## Owned implementation

New `web/components/archivos/`, `web/lib/archivos.js`,
`web/lib/cargadorGeometrias.js`, dedicated file CSS, focused JS/browser tests
and a standalone synthetic development harness. Export the factories exactly
as INTERFACES specifies. Reuse shared DOM/dialog utilities and the supplied
private transport; no second session manager or direct unaffiliated fetch path.
Do not edit A's shell/table/shared API/store/router, auth/schema, dispatcher,
terrain queries or existing renderer/helper behavior. If needed, supply a
precise integration request instead. No production lifecycle change is expected.

## 1. PDF/KMZ cells and detail controls

- Compact file cells reflect the caller-aware summary and distinguish absent,
  loading, pending, failed and usable content. Full detail supports a file
  picker and drag/drop, bounded pagination of files/versions/history/attempts,
  and current/retired status. Do not enumerate/download every file on mount.
- Validate type/size before reading; hash the exact bytes for the frozen start
  contract, start → raw PUT → complete. Use honest phase/progress indicators:
  if fetch cannot expose transmitted-byte progress, show indeterminate upload
  progress rather than fabricated percentages. Browser sets Content-Length.
  At most one active upload/hash pipeline per widgets factory; bounded pending
  handles (no more than the server's five) and no unbounded dropped-file queue.
- Keep one idempotency key per logical operation, reused only with the same
  body. Resolve an ambiguous start by same-key replay, completion by terminal
  replay; do not create another version merely because a response was lost.
  Re-stage only the same version/verified file within its allowed state/window.
  Distinguish network uncertainty, known failure, expiry and lease-in-progress.
  Respect server retry hints; bounded, user-controlled retry, no blind mutation
  loop. Reloaded pending uploads may need file reselection; do not claim bytes
  can resume without the File or after the upload deadline.
- Explicit cancel uses the accepted initiator/admin policy. Do not claim a
  locally aborted request undid a completed server operation. Display cleanup
  pending truthfully; never hide a failed cancellation as success.
- PDF download/open uses the authenticated immutable-version bytes and safe
  filename path, no storage key/token URL. Create object URLs only on demand
  and revoke them on closure/reset. Retained versions remain readable under
  current authorization. Do not execute arbitrary file/KML descriptions as HTML.
- KMZ: show processing outcome separately from upload state. Multi-candidate
  selection uses the actual candidate identifiers; validate selection and show
  errors as text. Reprocess/select does not activate by itself; require explicit
  activation with current `expected_revision` and a stable logical key. A stale
  409 requires refresh and user choice, never automatic overwrite. Show which
  version/geometry is truly active, retaining the old usable layout during a
  failed/pending replacement. Retirement requires explicit confirmation and is
  irreversible under this lifecycle; do not invent attachment restore.
- Read-only/archive/scope rules disable unavailable controls but never replace
  server authorization. Another person's pending metadata stays hidden. File
  changes call onCambio, not terrain PATCH; do not overwrite core/custom cells.
- Keyboard-accessible picker, actions, progress/error/status messages, focus
  return and safe text. Do not claim screen-reader validation unless performed.

## 2. Bounded cancellable geometry loading

Implement `crearCargadorGeometrias` from INTERFACES using accepted metadata and
512 KiB byte-chunk delivery. Validate ID/terrain/version, sizes, offsets and
all sequence/final/hash headers. Verify whole-body SHA-256 before strict UTF-8
decode/JSON parsing; never decode each chunk separately or trust only an HTTP
200. Keep the 16 MiB ceiling and accepted normalized renderer body shape.

One selected geometry load, one replaceable pending selection, one ready body;
rapid selection cancels and releases obsolete work. `reset`/`destroy` forget
all private state and forbid late installs, including after successful network
completion but before digest/parse finishes. No persistent cache, worker/E5
integration, extra simplification, geometry rewriting or lowered parser limits.
Loading/error is communicated to A; the host preserves the interior-point
symbol until a verified body is supplied. No implicit XY fallback here.

## 3. Evidence and handoff

1. Deterministic client tests: idempotency/replay and uncertain replies, lease
   and deadline errors, cancellation/readonly/conflict/retirement, pending
   privacy, mount/destroy/reset, and zero late installs across identity changes.
2. Geometry tests: multichunk UTF-8 boundary, wrong ID/version/terrain/hash,
   missing/repeated/out-of-order/truncated/oversized chunks, bad final marker,
   transfer/revocation between chunks, read failure, parse error and retry. Prove
   the queue/residency caps with rapid selections and cleanup/negative controls.
3. A standalone browser harness with actual widgets and **real C1-mounted APIs**
   (not mocked success): PDF/KMZ upload, candidate selection/activation, retained
   download, second-session reload, no-grant denial, expiry and active work
   cancellation. Use local disk storage at least once, not only memory. The
   harness may compose shared components in dedicated test files; do not edit
   A's app shell or silently call that harness the finished product.
4. One real near-limit accepted 100,000-vertex geometry: exact bytes/hash,
   selected outline using the unchanged renderer, timings and transient-memory
   observations. This is not a full research/paint/DPR benchmark rerun or an
   approval of total browser memory/performance. Include a UTF-8 codepoint split
   fixture as a separate transport test if the normal geometry is ASCII-only.
5. Full relevant JS/Python suites, Python 3.9, SQLite/disposable Postgres,
   lint/types, required pre-push checks and exact-head green CI; disclose skips
   and any known environment-only failure separately. Full browser Postgres
   combined-flow smoke belongs to A; coordinate rather than duplicate it.

Publish `reports/team-b-file-ui-geometry-2026-10-09/START_HERE.md`, component/
loader contract examples, exact source/C1/code/final heads, changed files,
evidence/limits and precise A integration requests. Return the new draft's
**green-CI candidate SHA for A to merge and test**, without waiting for A's
complete feature. Preserve that head; subsequent corrections are additive and
explicitly relayed. Stop for supervisory review. No 4B, PR/main merge, deploy,
cloud provider, renderer strategy or memory research extension.
