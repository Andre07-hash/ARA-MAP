# Team B Round 1 supervisory review

Reviewed October 8, 2026 (Mexico City); GitHub receipt checked October 9,
00:25:50 UTC. **Changes requested on both deliveries.** These findings preserve
the released assignments, accepted prerequisites and separate research scope.
No application code was edited by the supervisor.

| Delivery | Reviewed head | Intended dependency | Verdict |
|---|---|---|---|
| Attachment lifecycle, [PR #23](https://github.com/Andre07-hash/ARA-MAP/pull/23) | `6f303e1d0672c0b0c0e9170a601f8ef388b0f3b7` | `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`, PR #20 | Correct L1–L6 below, same packet/PR |
| Memory research, [PR #21](https://github.com/Andre07-hash/ARA-MAP/pull/21) | `229d424aab2aa7659f5572fce3be41821e435c56` | `9da0ab10a344e66099d919f2da15d3a638e7292a`, PR #16 | Correct R1–R4 below, prototype only |

Both submitted heads match GitHub; Python/disposable-Postgres and JavaScript
checks passed for each. CI does not run the research's complete browser matrix.
The older “CI pending” sentence in #21's description is stale; it does not
change the verified green checks.

Read [TEAM_B.md](TEAM_B.md) for the bounded correction handoff. Prioritize the
1B corrections; research acceptance remains independent and is not a gate for
attachment development. No 2B/3B, merge, deployment or provisioning is released.

## Independent evidence and limits

- Reviewed the lifecycle's complete service/repository and dedicated test
  module against the released 1B contract, with the diff based on PR #20.
  The only changed existing test is the parser-import allowance already
  anticipated by the integration manifest. No A-owned application file changed.
- Ran `tests.test_archivos`: **42 passed, zero skips**, SQLite plus a newly
  initialized **UTF-8 Postgres 17** cluster and isolated generated schemas.
  See [lifecycle-tests.log](lifecycle-tests.log). Python was 3.14.5.
- Independently reran the 21 SQLite lifecycle tests on macOS Python **3.9.6**;
  all passed. See [lifecycle-python39.log](lifecycle-python39.log).
- Added independent diagnostic probes, not application fixes. All eight
  lifecycle probes produced the same substantive results on both databases:
  [SQLite](lifecycle-sqlite.jsonl), [Postgres](lifecycle-postgres.jsonl),
  [reproducer](reproduce_lifecycle.py). IDs/accounts/files are fictional.
  The probes print observed behavior; an exit code of zero is not acceptance.
- Inspected the research allocation, worker, scheduler and audit paths, plus
  its report, timing controls and disclosed paint limitations. Ran its 17 Node
  tests twice: **16 passed, one failed** each time on Node 23.7.0. See
  [memory-tests.log](memory-tests.log). R4 explains the test's timing dependence.
- Four isolated Node probes demonstrate the memory/lifecycle findings:
  [results](memory-probes.jsonl), [reproducer](reproduce_memory.mjs). They use
  the actual prototype modules with minimal layer/worker doubles. They are
  not browser screenshots, process-RAM measurements or a repeat of the full
  browser matrix.
- The developer's full suites (including the full Python 3.9 suite), file measurements and browser
  measurements remain developer evidence. This review independently reran the
  focused database suites and probes; it did not repeat those full matrices.
  Existing green CI is recorded separately above. No hosted validation occurred.
- Before publishing these supervisor documents, `./verificar.sh` passed on
  the supervisor branch: 672 Python tests with 29 Postgres-only skips, the
  full Python 3.9.6 suite and JavaScript. This is a documentation-publication
  gate, not a full rerun of PR #23. See
  [supervisor-docs-verificar.log](supervisor-docs-verificar.log).

## Attachment lifecycle corrections

Locations below refer to PR #23 at the exact reviewed head.

### L1 — P1: validate all resource ownership before lease lookup; normalize absence

`server/archivos.py:614–625` takes a lease on the caller's `version_id` before
`repo.activate` checks that the version belongs to the authorized attachment.
An operator can name their own attachment and a version in an inaccessible
terrain. If that foreign version has a live lease, the response is
`409 procesamiento_en_curso`, including its expiry. A nonexistent version
instead raises raw SQLite `IntegrityError` / Postgres `ForeignKeyViolation`.
An available foreign version gives a third, distinct conflict response.
No foreign pointer write was observed, but private existence/processing state
is disclosed and missing input becomes an uncontrolled error.

There is another absence oracle at `server/archivos.py:55–56, 86–95`:
missing file/version yields `El archivo no existe.`, whereas an existing
out-of-scope file yields P2's `El terreno no existe.`. Both are 404 with the
same code but different serialized messages. This affects multiple public
operations, not just activation.

Resolve and validate the requested version/geometry against the actual
authorized attachment/terrain before consulting its lease or mutating it.
Return one indistinguishable missing/out-of-scope result, including message
and details. Keep real 401/403/session handling and do not modify P2. Test
foreign/missing IDs, live and expired leases, other attachment on the same
terrain, other terrain, and both databases; assert no state change.

Probes: `absence`, `foreign_activation`.

### L2 — P2: apply pending privacy to history and consistent expiry projections

`server/repo/archivos.py:557–572, 619–624` serializes every event unchanged;
`historial` does not pass caller identity for pending projection. An operator
who sees only a generic pending status in `listar` can call history and read
another initiator's pending filename, declared size, version ID and actor from
`subida_iniciada`. This bypasses the advertised caller-aware privacy rule.

Also, `_summary_row:527–550` turns an overdue row into `expirado` before its
privacy decision and reveals that still-pending row's filename/size; the
equivalent `projected_version:575–586` keeps it generic. Make the projections
consistent. Preserve full durable audit rows internally; redact the returned
projection rather than rewriting history. Add tests before/at/after the
deadline, with a live lease and across transfer/revocation, on all read surfaces.

Probe: `pending_privacy` (live-history disclosure and expired-summary mismatch).

### L3 — P2: evaluate deadlines at the acquired boundary and return controlled lease conflicts

`server/archivos.py:420–425, 454–459, 570–580` computes `now` before entering
`db.escritura()`. Time spent acquiring the boundary is excluded from the lease
check. Reproducer: processing takes 178 seconds, opening the final write
boundary takes another two; completion still commits `disponible` at equality
with the 180-second lease expiry because it tests the earlier timestamp.
The same pattern affects lease acquisition/start deadlines and related writes.

Read the clock after acquiring the relevant boundary/locks, immediately before
the guarded expiry decision. Preserve the specified equality rule and valid
pre-deadline lease crossing. Do not remove locking or add automatic retries.

Separately, expired `reprocesar` reaches
`server/repo/archivos.py:451–452` and propagates raw `ConflictError` through the
public service. Map it to a controlled lease/state conflict with no partial
attempt/geometry/idempotency/audit writes. Inspect the existing deadline-first
branch in `_acquire_completion`: a caller at the completion deadline with a
still-live competing lease should receive the documented in-progress result,
not a claim that the live operation has expired.

Probes: `stale_clock`, `expired_processing`. Use a test clock/barrier rather
than wall-clock sleeps. Add both takeover orders and expiry while waiting.

### L4 — P2: bound the public attachment listing and its database work

`server/repo/archivos.py:484–495` calls `fetchall()` for every attachment,
including cancelled/retired entries, then queries a latest version per row.
`listar` exposes no limit or cursor. The pending cap does not limit historical
attachments: 105 start/cancel cycles return all 105 rows in one response;
the collection can grow without bound.

Apply the contract's default 50 / maximum 100 history limits and a stable
cursor to attachment/history retrieval; bound SQL rows and hydration before
serialization. Avoid an unbounded list plus per-item queries. Update service
signatures and examples coherently before 2B consumes them. Verify paging,
permissions, equal timestamps, retirement and large historical collections.

Probe: `unbounded_list`. This is the released bounded-read requirement, not a
new UI or transport assignment.

### L5 — P2: retired PDFs must not crowd active files out of current summaries

`server/repo/archivos.py:502–509` selects recent PDFs without excluding retired
attachments; `pdf_total` at 518–520 does exclude them. One active PDF followed
by five retired PDFs returns `pdf_total = 1` with five retired recent entries
and omits the active PDF entirely. Retired entries can dominate the limited
current-cell projection even though finalized history is correctly retained.

Select current eligible PDFs consistently for count/recent summary. Keep
retired files available through authorized, bounded history. Add the explicit
lower-revision PDF versus higher-revision attachment regression requested by
1B, as well as the five-retired-versus-one-active case.

Probe: `retired_summary`.

### L6 — P2: surface handled cleanup failure honestly

`server/archivos.py:341–353, 430–437` suppresses a final-object deletion error
and ignores the returned failure flag in verification-failure completion.
An injected `borrar` failure leaves a final nonce behind, but the returned
terminal result contains no cleanup-pending indication. Retirement also saves
`limpieza_pendiente=False` before external cleanup; an idempotent replay can
therefore claim a clean state after cleanup failed.

Preserve the original outcome and safe retention, while reporting recoverable
cleanup status consistently on handled failures/replays. Do not expose object
keys or add a sweeper/schema rewrite. An ambiguous database result must still
never delete referenced bytes. Add failed-removal/replay cases for completion,
cancellation and retirement. A process crash may still leave an orphan as
already disclosed; this finding concerns observed failures being hidden.

Probe: `cleanup` (terminal failure, one orphan final object, no pending flag).

## Memory-research corrections

Locations refer to PR #21 at its exact reviewed head. Keep fixes under
`reports/team-b-display-memory-budget-2026-10-08/` and preserve the research
base and accepted renderer/parser heads.

### R1 — P1 for the research claim: include per-layer arrays in admission and audit

`prototipo/e5.js:65` calls inherited `CapaContorno.initialize`, which allocates
`new Int32Array(preparado.partes)` at
`reports/team-b-display-strategy-2026-10-08/prototipo/capa.js:78`.
Neither `bytesDe`, the prepared reservation, nor `memoria.mjs`'s audit counts
this per-layer `_visibles` buffer. It is a prototype-owned typed array, not
caller GeoJSON, JS-object overhead or Leaflet's own canvas.

At 20,000 parts the omitted allocation is 80,000 bytes **per layer**. The
independent probe fills a 2,400,008-byte budget with a prepared body, then
constructs the actual E5 layer: held arrays total 2,480,008 bytes while the
ledger remains 2,400,008. Multiple layers/maps add distinct visibility buffers.
Thus the reported ledger/owner audit is not a proof that every managed
allocation respects the budget.

Reserve these buffers before allocation; account for per-layer multiplicity,
replacement, teardown and allocation failure. Inspect the full managed
allocation inventory, including scratch/bitmap transfer transitions, rather
than adding only one counter. Audit actual arrays owned by active layers too.
Rerun affected boundary, multi-map, tiny-part, replacement and teardown cases.
Revise the headline conclusion until that evidence exists. The 64/128 MiB
values remain study budgets; no total-browser-memory promise is approved.

Probe: `unaccounted_layer_array`.

### R2 — P2: synchronous posting and silent startup need a terminal fallback

`prototipo/cliente.js:145–149` registers a reservation/copy and calls
`postMessage` without handling a synchronous exception. Injecting such a
failure escapes to the caller; client state stays `listo`, reservation remains,
and neither failure callback nor termination runs. Similar sends should be
audited, including raster, forget and reset transitions.

The only watchdog starts for a raster (`172–178`); a worker that never sends
its initial `listo` stays `iniciando` indefinitely. A probe with a 10 ms limit
was still starting at 60 ms. This is distinct from the tested worker that
handshakes and then ignores a raster.

Catch posting failures and terminate/release/fallback through one coherent
path. Bound startup as well as unanswered jobs. Exercise synchronous failures
at each send stage, missing handshake, late responses and reset; prove that
no reservation remains falsely owned and the UI can settle to its declared
symbol/reason with an explicit retry.

Probes: `synchronous_post_failure`, `silent_startup`.

### R3 — P2: the two-job setting does not cap queued raw-body references

`prototipo/planificador.js:96–101` creates and stores every requested job.
`maxTrabajos` limits slice execution/allocated work, not the queue size.
Every `crearPreparacion` closure retains its supplied `geometrias` map until
completion or cancellation. The probe queues 100 distinct jobs/maps with
zero allocated jobs and no admission refusal; all 100 remain pending.

The report's statement that queued/running raw-body references are bounded by
two preparation jobs is unsupported. Give pending requests a finite admission
and supersession contract; bound retained input references separately from
prepared byte reservations, and explain any caller-owned retention left
external. Test large request bursts, distinct input maps, cancellation and
multiple visible maps. Do not relabel retained prototype references as absent.

Probe: `uncapped_waiting_jobs`.

### R4 — P2 evidence: make cancellation testing deterministic

`pruebas/memoria.test.mjs:168–174` assumes a 90,000-position preparation cannot
finish within one real 8 ms slice. It does finish on this review environment,
so its success callback throws `cancelled job reported` before cancellation is
requested. Both independent runs failed that one test (16/17 passed).

Inject the scheduler's existing clock/step control so the cancellation occurs
mid-work deterministically; do not increase fixture size or relax the assertion
as a machine-speed workaround. Rerun the prototype tests and identify actual
behavior fixes separately from this test-timing correction.

## Preserved decisions and next owner

- Retain the existing research evidence, including **8/12 complete-RGBA
  failures on Chromium 154**. Coverage/click agreement is useful but is not
  pixel identity. No product acceptance of visual differences is granted.
- The accepted E1 implementation and earlier component acceptances remain
  valid at their named heads. No research prototype enters the baseline.
- Team B owns L1–L6 on #23, then R1–R4 on #21 (or independent work as its
  existing sessions permit). A prerequisite change requires a specific
  failing case and a separate request to the owning team.
- Team A remains on its existing 1A review/correction assignment. Do not modify
  B's modules or advance either team into later packets solely because CI is
  green. The shared baseline stays at its recorded checkpoint unless an
  explicit additive repair is reviewed and propagated.
- Supervisor next: review corrected diffs against these exact heads and rerun
  affected probes; retain evidence for unchanged code. No owner business
  decision is needed to resolve the findings in this packet.
