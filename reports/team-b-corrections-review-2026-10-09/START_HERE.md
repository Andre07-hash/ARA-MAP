# Team B — correction review and 1B acceptance

GitHub checked **2026-10-09, 01:47 UTC**; baseline/A checkpoint checked again
at approximately 01:51 UTC. This continues Round 1 without releasing a later
packet. Supervisor changed reports/reproducers only, not application code.

## Verdict

| Delivery | Exact reviewed head | Decision |
|---|---|---|
| [PR #23 — 1B](https://github.com/Andre07-hash/ARA-MAP/pull/23) | `a9dc8af8cc511bde0a67168da335398353b80aa6` | **Accepted for the local/fake lifecycle scope. L1–L6 closed.** |
| [PR #21 — research](https://github.com/Andre07-hash/ARA-MAP/pull/21) | `68077cc366dd3e1885da36b8f5c7223093e4bd63` | **Research corrections still required:** R1/R2 pressure interactions and R1's allocation-failure test. R3/R4 closed. |

Both PRs were open drafts with exact-head Python/Postgres and JS CI green.
There was no main merge or deployment. Acceptance is tied to the named head
and scope, not a later branch tip or hosted readiness.

- #23 remains stacked on `claude/integration/round-1-baseline`,
  `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`. Diff reviewed from
  `6f303e1d0672c0b0c0e9170a601f8ef388b0f3b7`. Implementation/test changes are
  `d70eb0e07e5c61218df75e90a094581b5704fefc`; its final commit changes reports
  only. No A-owned application, schema/auth/store/parser/HTTP/renderer changes.
- #21 remains based on `9da0ab10a344e66099d919f2da15d3a638e7292a`.
  Diff reviewed from `229d424aab2aa7659f5572fce3be41821e435c56`.
  Implementation/test changes are `6fad4a7afe29b280283d6a5fffb3a11c06b37de4`;
  its final commit adds report/evidence updates only. Changes stay within
  `reports/team-b-display-memory-budget-2026-10-08/`.
- A's #22 was still `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037` at this
  check. Its separate correction-2 instructions at supervisor
  `6832a9bd1eb6dfbc1b114e517e79475957b01f0f` remain unchanged.

## 1B closure and interface freeze

| Finding | Independent closure evidence |
|---|---|
| L1 | Missing/out-of-scope resources and foreign/missing activation versions now have identical 404s. Ownership validation precedes lease inspection. New tests also cover expired/revoked-session 401 behavior and same-terrain foreign attachment IDs. |
| L2 | Shared `pending_view` redacts pending metadata consistently in list, summaries and history, including overdue rows and live leases; stored audit remains intact. Clock/transfer/revocation cases pass. |
| L3 | Clock reads occur after write-boundary acquisition and scope/resource locking. The independent stale-clock probe now gets controlled `lease_perdido`; expired reprocessing also produces a controlled conflict without terminal writes. Live-lease/deadline and both takeover cases pass. |
| L4 | SQL returns at most `limit + 1` rows in one hydration statement. Independent 105-entry traversal gives 50/50/5 unique entries; the developer's 106-entry, equal-timestamp/limit/scope/query-count test also passes independently. |
| L5 | Retired PDFs no longer crowd current summaries. One active PDF plus five retired PDFs returns the active entry and count one. Lower-revision PDF replacement beside a higher-revision attachment is covered. |
| L6 | Failure cleanup reports pending truthfully; terminal and retirement replays inspect leftovers without deleting. Unknown DB reference state preserves bytes. Failed/omitted cleanup, successful cleanup and uncertain-commit retention cases pass. |

Accept the corrected signatures documented in the developer handback
`reports/team-b-attachment-lifecycle-2026-10-08/CORRECTIONS_2026-10-09.md` §4
at the accepted head:

- `listar(..., cursor=None, limite=50, bd=None, reloj=None)` returns
  `{"archivos": [...], "cursor_siguiente": ...}`, maximum limit 100.
- `historial` adds `reloj`; history events carry `privado`. Redacted events
  expose generic status and position, not another initiator's pending details.
- Completion results/replays include `limpieza_pendiente`. It reports possible
  leftovers; it is not a cleanup guarantee or authorization to run a sweep.

Later consumers must use these signatures, not the original list-return shape.
History/bytes remain immutable and retirement irreversible in this release.
No HTTP adapter, UI, cloud storage or renderer integration is accepted here.

### Independent lifecycle verification

- **78/78** dedicated lifecycle tests, zero skips: Python 3.14.5, SQLite and
  a newly initialized disposable **UTF-8 Postgres 17** instance.
  [lifecycle-tests.log](lifecycle-tests.log).
- **39/39** SQLite lifecycle tests on macOS Python **3.9.6**, zero skips:
  [lifecycle-python39.log](lifecycle-python39.log).
- Repeated the original eight probe groups on each database:
  [SQLite](lifecycle-probes-sqlite.jsonl),
  [Postgres](lifecycle-probes-postgres.jsonl). Important interpretation:
  the old `unbounded_list` probe reports `2` because it counts keys in the new
  envelope, not attachment rows. The new independent page probe below replaces
  that obsolete metric. The original privacy probe omits the newly injectable
  history clock, so it observes overdue status; the dedicated test separately
  covers pre-deadline, equality, later expiry and a live lease.
- Added **actual completion-boundary-first** checks for eight scope changes:
  grant removal, transfer, terrain/base archival, account deactivation, role
  change, credential reset and logout. Separate threads/connections and a
  barrier inside the real finalization path show the administrative write
  waits, completion commits once, then the next replay is denied without an
  audit write. All eight pass on both databases. This complements the suite's
  nine scope-change-first cases; time expiry is not itself a competing writer.
  [Reproducer](reproduce_lifecycle_edges.py),
  [SQLite results](lifecycle-edges-sqlite.jsonl),
  [Postgres results](lifecycle-edges-postgres.jsonl).
  Administrative mutations use authorized fixture SQL through `db.escritura`,
  not future HTTP handlers. Serialization includes SQLite's write reservation
  and Postgres's existing advisory lock; no row-lock-only throughput claim.
- The same edge script traverses 105 attachments, asserting exact ID coverage,
  no duplicate, and 50/50/5 page sizes on both databases.
- [Exact-head CI run 37868620749](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37868620749)
  passed; its log reports 1,065 Python tests and 120 JS tests. The full 1,065
  suite was not independently repeated here. Developer ruff/mypy/coverage
  results remain separately attributed developer evidence.

The reported Linux system-openpyxl failure was **not reproduced on macOS**:
the specific clean-system test passed. Running the packaging module alone
first exposed its existing dependency on a prior `import server`; with that
ordinary suite prerequisite, all 11 packaging tests passed. Both logs are kept:
[standalone](packaging-python39.log), [with import](packaging-with-import.log).
No package/app change was made, and no failure is silently reported as green.
The Linux baseline comparison remains the developer's evidence.

All tests use fictional data. The disposable Postgres instance was stopped.
No hosted or production test was performed. Accepted P2 guarantees and the
separate combined-baseline review gate remain unchanged.

## Research: closed cases and remaining corrections

The four adapted original probes now show the originally requested behavior:
layer-array admission/refusal, direct send failure releasing reservations,
silent startup timing out, and 32 admitted jobs/68 explicit refusals in a
100-request burst. Independently rerun output:
[memory-adapted-probes.jsonl](memory-adapted-probes.jsonl).

**R3 closed:** pending requests have a finite per-map admission bound and each
admitted preparation retains only its own caller body. The 32-body count is
not a byte limit; upstream body-size policy remains needed. This is prototype
behavior, not approval of 32 as a product setting.

**R4 closed:** cancellation now uses the injected clock and passes independently,
including a separate focused repeat:
[memory-cancellation-repeat.log](memory-cancellation-repeat.log).

R1 and R2 improve their direct cases but fail in the interacting pressure paths
below. Reproduce all three edge cases with:

```sh
node /path/to/this/report/reproduce_memory_edges.mjs /path/to/pr21-archive
```

This script calls the actual registry/budget/layer/client modules with small
arrays and worker/Leaflet doubles. It does not modify prototype code or claim
to be an independent browser run. [Results](memory-edge-probes.jsonl).

### R1a — P1 for the research claim: layer admission evicts its own prepared body

Locations: `prototipo/MapCanvas.js:374–391, 434–439`,
`prototipo/registro.js:23–39, 61–68`, and `memoria.mjs:99–124`, all within the
research folder at the reviewed head.

The cache-hit path obtains an unpinned prepared body, then reserves the new
layer array, and pins the body only after constructing the layer. Reservation
can synchronously invoke the registry's pressure reliever. With insufficient
room for both allocations, it evicts that same body and releases its ledger
entry. The layer still retains it through `_prep`; the later `fijar` is a no-op
because the registry entry has gone. The preparation-completion handoff has
the same ownership ordering to inspect.

Independent exact-order probe: budget **2,487 B**, ledger **80 B**, no registry
entry, but a live layer owns **2,408 B prepared arrays + 80 B layer array =
2,488 B**. Actual managed arrays exceed the budget. Current audit sums the
registry and the layer's own visibility array, also reporting only 80 B; it
does not discover the retained `_prep` outside the registry.

Required: protect/transfer the prepared body's ownership **before any
reservation can evict it**, unwind correctly on refusal/allocation failure,
and strengthen the audit to detect every unique prepared buffer retained by
live layers as well as registry/jobs. Avoid double-counting legitimately shared
bodies. Test tight cache-hit and newly-prepared paths, existing pinned rasters,
two layers/maps, replacement, refusal and teardown. Do not merely increase the
budget or suppress the audit error.

### R2a — P2: failure during memory relief resumes allocation on a dead client

Locations: `prototipo/cliente.js:72–92, 168–188` and the synchronous reliever
call in `prototipo/presupuesto.js:49–57`.

`asegurar` checks client state before `presupuesto.reservar`. That reservation
can synchronously evict an old worker copy. If the `olvidar` send fails,
`fallar` terminates/releases the client while `asegurar` is still on the stack.
The reservation then succeeds, and `asegurar` installs/posts a new copy without
checking the now-failed state. A second call to `fallar` would return early.

Independent small-array probe: replacing a 128 B copy triggers a throwing
`olvidar`. The client ends `fallido` but `asegurar` returns **`listo`**, sends
`cuerpo` after termination and retains **128 B / one copy**. This breaks the
single failure-path ownership claim even though direct send-stage tests pass.

Required: prevent any post/admission after a terminal transition during
reentrant pressure callbacks, and release any reservation acquired across
that transition. Test pressure-induced forget failure during `asegurar`,
including a send to the terminated worker that returns normally and one that
throws. Preserve one terminal notification, truthful return state, zero copy/
forget ownership, and explicit retry with one fresh worker. Inspect analogous
reservation-triggered transitions rather than only the direct send helper.

### R1-test — P2 evidence: allocation failure assumes a platform array limit

Location: `pruebas/memoria.test.mjs:566–570`.

The test requests `Int32Array(2**32)`, a **16 GiB** backing store, and assumes
it throws `RangeError`. Node 23.7.0 here accepts that allocation, so the test
fails with `Missing expected exception`. The full prototype run was **28/29**,
and a second invocation produced the same result:
[first log](memory-tests.log), [repeat log](memory-tests-repeat.log).
The attempted name filter on the repeat did not exclude this case; no claim
is made that it was a safe filtered pass. No further giant allocation was run.

Required: inject a deterministic allocation/initializer failure using a small
fixture. Assert the exception and release of the admitted reservation. Do not
increase the requested size or weaken the assertion. The independent injected
failure probe already confirms the current layer cleanup releases to zero;
this item is a test portability/safety correction, not proof that that catch
path itself leaks.

### Evidence boundaries to preserve

The developer's corrected Chromium 141/Linux matrix, failure scenarios, burst,
paint/click and one-repeat timing evidence were read, not independently rerun.
The known visual limit remains **8/12 RGBA-identical on Chromium 141** versus
historical **4/12 on Chromium 154**; coverage and click agreement are not pixel
identity. No E5 integration or acceptance of visual differences is approved.

The R1 audit miss means zero mismatches in the supplied scenarios cannot prove
complete managed-allocation coverage. Preserve their raw measurements, mark
the revised universal-accounting headline as not yet established, and append
the corrected pressure/audit evidence after fixing it. Browser/OS/GPU transient
allocation and caller bodies remain distinct from the study's managed ledger.

## Next actions

Team B: keep accepted #23 unchanged; only the bounded research corrections in
[TEAM_B.md](TEAM_B.md) remain. No need to redo L1–L6 or wait for A's record APIs.

Team A: continue its existing correction 2 in #22; no instruction is reissued
or broadened here. The supervisor next reviews changed A/research heads and
the combined baseline before releasing a later integration packet.

No merge, deploy, cloud provisioning, real-data/account action or 2A/2B release.
The supervisor documentation publication gate is recorded separately in
`supervisor-verificar.log`: `./verificar.sh` passed (672 Python tests with 29
Postgres skips, full Python 3.9.6 suite and JavaScript checks). It is not PR
#23's full application suite; optional `--todo` lint/type/coverage checks were
not rerun for this documentation-only publication.
