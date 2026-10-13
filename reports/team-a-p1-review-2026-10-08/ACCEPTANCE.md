# P1 accepted — corrected attachment schema

**Accepted for the P1 persistence milestone** at PR [#15](https://github.com/Andre07-hash/ARA-MAP/pull/15) head **`edf9bcd1dc51e74a627d54d5ce01d37113206055`**, October 8, 2026. F1 and F2 from [the original review](START_HERE.md) are closed. No further P1 correction is requested.

This acceptance is tied to that exact head. PR #15 remains draft and unmerged, stacked on PR #14 at `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`; its dependency must land first. Schema remains 10. The initial PR body still names the original implementation head; use the actual GitHub head and appended correction report for this acceptance.

## Corrections verified

| Finding | Disposition |
|---|---|
| F1 — NULL bypass in the non-application reason | Fixed. A populated reason now explicitly requires a non-null zero outcome. The same explicit guard was added to the failed-state check, whose NULL case was already excluded by another constraint. Independent original reproductions now reject pending/cancelled/expired rows carrying an outcome reason. The new shared backend test covers both allowed reason strings, all three NULL-outcome states and valid controls. |
| F2 — SQLite backup retains leases | Fixed. The existing operational cleanup clears `archivo_trabajo` in the backup copy when that table exists. The independent original reproduction reports backup leases **0**, preserved pending versions **1**, source leases **1**. Tests exercise actual backup creation, durable cyclic data and pointer preservation, source preservation, foreign-key integrity and older-schema backups. |

The five stricter writer rules accepted in the original review remain unchanged. Successful attempts and their matching geometries are inserted together, attempt first, in one transaction; unsuccessful or selection-required attempts do not need geometry. Finalized geometry and attachment records still do not imply permission to serve or activate them without the later repository/auth checks.

## Independent evidence

- Exported the exact accepted commit to a disposable archive; removed database/provider configuration from its test environment and directed SQLite to a disposable path.
- The previously published `reproduce.py` returned **zero remaining failures** without changing the reproducer.
- Full **`./verificar.sh` passed**: **754 Python tests, 69 Postgres-only skips**, complete system **Python 3.9.6** suite, and JavaScript tests.
- GitHub at that head: **Python and disposable Postgres SUCCESS; JavaScript SUCCESS**, run [37799522839](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37799522839).
- Local Postgres, hosted workflows and independent lint/type checks were not run by the supervisor. No company data, real account, cloud resource or production database was used.

The correction touches the database adapter's checks/backup cleanup, dedicated schema tests and the appended report. No B-owned implementation or route/auth/UI change was made. Historical review and submission text stay intact.

## Next assignment

Team A can now start the separate [A-2/P2 roles and work-base access packet](../team-a-a2-packet-2026-10-08/START_HERE.md). It contains a concrete implementation assignment, including the shared write-boundary authorization that B needs; do not wait for another owner approval or Team B's display report to start it.

Team B continues its current independent display-strategy investigation. P1 is now an accepted schema dependency for later attachment code; full B-3 is not released by this acceptance. The supervisor will consolidate its lifecycle/API packet against the concrete A-2/P2 interface and remaining applicable policy choices. Cloud provider selection is not a prerequisite for A-2/P2.

No merge, deployment, provisioning or dispatch to either external coder session was performed by the supervisor.
