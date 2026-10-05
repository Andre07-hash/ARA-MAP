# Deployment review — import assistant and saved-map merge correction

**Decision: ready for a controlled deployment with AI disabled.** The previously outstanding disposable-Postgres acceptance gate is now satisfied. No further blocking finding was identified in the reviewed corrections. This review does not claim that the release has been deployed or that production configuration has been verified.

Reviewed source: `FINAL_SOURCE_SNAPSHOT.json`, captured `2026-09-25T04:10:44.682634+00:00`, **142 files**. Reviewed the developer's `ACEPTACION_POSTGRES.md`, relevant application changes and acceptance tests.

## Independent verification

- All **142 recorded file hashes matched before and after** this review and verification.
- Created a fresh, separate PostgreSQL **17.11** cluster bound to loopback, using the already-installed Homebrew binaries. No production connection or `.env.local` was used for this test setup.
- Ran `tests.test_postgres` and `tests.test_postgres_aceptacion`: **20 tests executed, zero skipped, all passed**. This independently covers the new-base and append stale-confirmation cases, failure cleanup, cross-connection budget reservations, repeated v5-to-v6 migration through the real script, and saved-map merging.
- Ran the complete default `verificar.sh --todo`: **545 Python tests run, 20 Postgres tests skipped in that local run, 525 executed and passed**; macOS Python 3.9.6 compatibility, JavaScript, ruff and mypy pass; coverage **93%**. The 20 Postgres cases were executed separately as described above.
- No test schemas remained after the Postgres run. The temporary cluster was stopped and its directory deleted. The existing Homebrew installation was retained.
- Browser results in the developer packet were reviewed but not independently repeated in this pass. The developer reports 44/44 in both provider modes on both storage backends, and an all-545-tests Postgres-configured run. Those are distinct from the supervisor runs above.

No application code or existing tests were edited during this review. No production data was changed, migration run against Neon, deployment made or paid provider called.

## Merge fix accepted; release-note wording

`server/repo/mapas.py::layer_fingerprint` now hashes the named column values rather than iterating the row object. This is correct for both the SQLite row and the Postgres mapping adapter. The local compatibility test preserves the former SQLite digest; the real Postgres test preserves distinct layers while still identifying identical snapshots as duplicates.

One precision correction to the developer's impact description: the old Postgres implementation hashed column names **once for each terrain row**. Different layers with the same terrain count could therefore receive the same fingerprint and be incorrectly dropped as duplicates. It did not make every possible layer size identical.

Suggested release note:

> Fixed merging saved maps in the shared web version: distinct layers with equal terrain counts could be discarded as duplicates. New merges preserve these layers. Previously saved comparisons missing layers must be recreated from their original source maps; this deployment does not repair them automatically.

The current production deployment was not inspected in this pass. Its affected status is reported by the developer; the defect and correction are independently established for the inspected code path.

## Deployment sequence

1. Verify the release still matches the reviewed snapshot. Record the existing deployment identifier and the target project/database before changing production. Keep paid AI unconfigured or explicitly disabled for this release; do not use the simulated provider in production.
2. Record a recoverable production backup before migration. The migration script takes a workspace backup itself; preserve the identity of that backup or recovery point rather than assuming a later rolling backup still represents the pre-release state.
3. Apply the migration to the explicitly intended production connection and verify **schema version 6**. `--url-env NAME` is suitable for explicit targeting: it does not load `.env.local` and fails if its named variable is absent. The default invocation still targets the normal configured workspace.
4. Deploy the reviewed source to the intended Vercel project. Verify the resulting deployment identifier and production URL.
5. Smoke-test as an editor using clearly labeled, removable fictional records: familiar CSV import; one ambiguous-header question and correction; append; folders; save and reopen maps; and merging **two distinct saved maps with equal terrain counts**, confirming both layers and their data survive. Check comparison Excel export and viewer/editor access. Confirm the import assistant works with AI disabled.
6. Remove only the smoke-test artifacts created during that run, then verify ordinary saved maps and databases remain accessible. Record migration, deployment and smoke-test outcomes in the release response.

If a migration or smoke test fails, stop release progression and report the failure. Use the recorded deployment/recovery plan; do not automatically erase newer production data by restoring an old workspace snapshot. Previously damaged comparisons should be recreated deliberately from their original maps, not silently replaced or deleted during a smoke test.

An isolated Neon-branch rehearsal remains an optional additional check for hosted connection behavior; it is not an unresolved failure of the completed Postgres acceptance tests.

## Separate remaining work

- **Before the boss's demonstration:** fix the pre-existing navigation `false` and mobile header overflow, then verify desktop and phone layouts. These presentation issues remain open and were not changed by this review.
- **Before paid AI activation:** configure the selected model, key, prices and budget, and evaluate actual interpretation, ambiguity handling, usage accounting, cost and latency on fictional or approved samples. Simulated-provider success is not a real-model evaluation. The boss's interaction remains automatic analysis plus necessary questions, with no AI toggle.
