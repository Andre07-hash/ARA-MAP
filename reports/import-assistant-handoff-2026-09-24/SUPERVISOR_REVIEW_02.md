# Second supervisor review — import assistant corrections

Reviewed September 24, 2026, America/Mexico_City. This reviews the R1–R5 revision described in `DEVELOPER_RESPONSE.md`, against `FINAL_SOURCE_SNAPSHOT.json` captured at `2026-09-25T03:32:49.239045+00:00`.

**Decision: return for two focused corrections before deployment.** The original eight regressions now pass, but R2 still permits a stale confirmation after a newer import completes. Its new exception cleanup also creates a cloud database lock problem. No additional product features are requested.

## Verification and limits

- All **139 source/test/fixture hashes match** the developer's final snapshot, checked before and after this review.
- The original `review_regressions.py` is unchanged and passes **8/8**.
- Independently reran `env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ./verificar.sh --todo`: **514 Python tests run, 8 skipped, 506 executed and passed**; macOS Python 3.9.6 compatibility, JavaScript suite, ruff, mypy and **93% coverage** all pass. The skipped Postgres tests remain unverified.
- Added `review2_regressions.py`: **four cases, all four fail** on this snapshot. Two deterministically schedule overlapping operations through the real import handlers; two instrument session lifetime during a forced write failure. All use fictional data and disposable SQLite. These are not live Postgres tests.
- Browser checks were **not rerun in this second pass**; 44/44 in each provider mode remains the developer's reported result. This pass concentrates on the revised backend correctness paths.
- No application code or existing tests were edited. No production deployment, Neon migration or paid AI call was performed. No server was started by this review.

Run the new cases from the repository root:

```sh
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL python3 reports/import-assistant-handoff-2026-09-24/review2_regressions.py -v
```

## Disposition of the original findings

| Finding | Second-pass result |
|---|---|
| R1 — duplicate headings in remembered formats | Original failure resolved. Unique names still reuse; ambiguous repeated headings are withheld for focused confirmation. New developer controls cover different answers and additional repeated/blank headings. |
| R2 — confirmation versus correction | **Still open**, for the additional ordering below. The atomic claim fixes the original ordering but treats a missing draft as permission to proceed. Error cleanup also introduces a separate lock issue. |
| R3 — foreign currencies relabeled as MXN | Original failures resolved. Header and all text-cell scanning, expanded currency markers and plan validation cover automatic, saved and manual assignments. No conversion was introduced. |
| R4 — budget admission and unknown usage | Original local failures resolved. The request/schema byte bound and enforced output allowance replace the old estimate; missing/invalid usage retains the reservation; overruns remain fully recorded. Acceptance here concerns inspected code and simulated tests. Verify model compatibility, configured prices and actual metering before enabling paid calls. |
| R5 — malformed provider results | Original failure resolved. Primitive types are validated before lookups, and provider exceptions fall back without logging their potentially sensitive messages. |

## R2a — P1: a completed corrected import lets an older confirmation succeed

**Locations:** `server/asistente/borradores.py:97–132`, especially the `return False` branches at 111–112 and 125–127; `server/api/importar.py:204–220`, which ignores that return value. Successful confirmation subsequently deletes the draft through `_cerrar_borrador`.

### Reproduction

Use the fictional input:

```csv
Terreno,Precio
Norte,1000000
```

The following is a valid ordering of overlapping requests:

1. Confirmation A takes the old preview token, then pauses immediately before `_vigente` claims the draft.
2. Correction B changes `Precio` to additional data. It successfully saves revision 2 and returns a new preview whose price is unknown.
3. Confirmation C imports that corrected preview successfully. It closes/deletes the draft.
4. Confirmation A resumes with its already-taken old preview. `reclamar` sees no draft and returns `False`. `_vigente` ignores this, so A writes the old price.

The new regression hooks only the scheduling boundary. It calls the original claim implementation and real handlers; it does not fake a successful claim, remove the draft directly or alter business records.

**Observed for a new database:** B, C and A all succeed. Two databases exist, with stored prices `[None, 1000000.0]`.

**Observed for append:** B, C and A all succeed. C appends the corrected terrain with no price; A subsequently applies its stale value and leaves `asking_price=1000000.0`. The test supplies the existing supported `actualizar` conflict choice, representing a confirmation payload already in flight.

Deleting a draft proves neither that its revision matches nor that confirmation owns it. “There is nothing left to correct” is insufficient: it may mean that a different revision already finished importing.

### Required correction

For a preview that carries assistant draft metadata, require a **successful claim of a present, valid draft at the exact revision** before any business-data write. Treat missing/expired/deleted drafts as stale or expired (409/410). Do not fall through on a false claim result. Apply this to both SQLite and Postgres.

Preserve compatibility with genuine legacy previews that have no assistant draft metadata; `_vigente` already has a separate early-return path for those. Do not turn missing assistant state into the legacy path.

Retain the existing atomic ownership rule: if confirmation claims first, preparation must fail; if correction wins, stale confirmation must fail. Do not move the claim back to an uncoordinated check or rely solely on deleting preview tokens; an in-flight request may already hold one.

### Acceptance checks

- Both new stale-confirmation cases pass: the corrected import succeeds, the old request returns 409/410, one destination database remains, and its price stays unknown.
- Preserve the original reviewer regression and the developer's new-base/append concurrency controls.
- Add missing/expired/evicted draft controls and a genuine legacy-preview compatibility control.
- Exercise the three-request ordering against disposable Postgres, with separate connections/workers. Repeated two-request races do not cover completion/deletion before an older request resumes.

## R2b — P2: error cleanup tries to reacquire the cloud workspace lock

**Locations:** `server/api/importar.py:301–306` and `359–364`; `server/asistente/borradores.py:134–138`; `server/postgres.py:66–94`.

Both commit handlers call `_cerrar_borrador(pending)` in their exception blocks **while still inside `with db.session()`**. In cloud mode, closing the draft calls `borradores.borrar`, which opens a new Postgres session.

Every Postgres session acquires the same transaction-scoped workspace advisory lock. The first session still holds it. Its explicit `ROLLBACK` is translated by `Connection.execute` to `ROLLBACK TO SAVEPOINT import_transaction`; it does not end the outer transaction or release the earlier workspace lock. The cleanup connection therefore waits for the first connection, while the first is waiting for cleanup to return.

The code configures a 30-second lock timeout. The expected cloud outcome is a cleanup lock timeout that masks the original error and prevents draft deletion, rather than the intended prompt error and clean closed draft.

**Evidence boundary:** the lock conclusion follows from the inspected session/savepoint implementation. The two new fault-injection cases independently confirm that both handlers invoke the separate-session deletion while outer-session depth is **1**. I did not run a real Postgres timeout and am not presenting this instrumentation as a live database test.

### Required correction

Perform cleanup that opens its own session **after the business-data session has exited and released its lock**, on success and failure. A surrounding exception/finally structure can accomplish this; preserve the original import error if cleanup itself fails. Do not swallow or misreport a failed import as success.

Alternatively, redesign cleanup to use an already-held connection with correct transaction and rollback semantics. If choosing that approach, replace the session-depth instrumentation with an equally strong assertion that cleanup never opens another lock-taking session under the existing lock. The supplied tests assume the current `borrar` API, which always creates its own cloud session.

Audit the full post-claim failure path while restructuring it: validation, backup, session entry, transaction write and commit failures should not strand the draft indefinitely as `confirmando`. Successful records, import provenance and remembered formats must retain the existing atomic commit behavior.

### Acceptance checks

- Force a write failure in both new-base and append handlers. Business data rolls back, the original error is preserved and the claimed draft is closed or has an explicitly recoverable failure state.
- Cleanup does not open a nested cloud session that reacquires the workspace lock.
- On disposable Postgres, force the same errors and verify prompt completion without `LockNotAvailable`/lock timeout, no partial imported rows or remembered formats, and no blocked workspace left behind.
- Cover a destination disappearing after initial validation and a backup failure after the claim. A spent preview must yield an understandable retry outcome rather than an unusable draft.

## Next developer handoff

1. Fix R2a and R2b without changing the approved import interaction or broadening feature scope.
2. Preserve the original eight tests. Add these four cases, or equivalent stronger outcome/lock tests, to normal verification.
3. Rerun affected tests and full verification on the final code. Update `DEVELOPER_RESPONSE.md` and the source snapshot with results and remaining limitations.
4. Before production rollout, validate schema migration and assistant behavior against **disposable Postgres**, including these concurrency and failure paths. Production Neon must not be the first test of them.
5. Real AI configuration and evaluation remain a separate activation step. Detection plus questions can operate without a configured provider; paid assistance is not accepted as live-tested based on stub results.

The pre-existing navigation `false` and mobile header overflow remain presentation follow-ups. They are not substitutes for these corrections. Nothing in this review authorizes deployment or asks the developer to make a paid provider call.
