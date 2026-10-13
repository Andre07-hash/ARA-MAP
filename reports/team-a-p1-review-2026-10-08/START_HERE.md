# P1 review — five stricter rules accepted; two corrections required

Reviewed PR [#15](https://github.com/Andre07-hash/ARA-MAP/pull/15) at **`75886658f5c41d5fb6ebe591b6833350958ccace`**, stacked on accepted A-1 `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`. Instruction: `84b2b84a05592b9f31b860e831925990274b481b`, `reports/next-parallel-packets-2026-10-08/TEAM_A_P1.md`. Review date: October 8, 2026.

**Disposition:** the five stricter rules are compatible with the intended writers and accepted as the persistence contract. Do not loosen them merely to simplify future code. P1 implementation acceptance is pending the two concrete corrections below. Team A can make these corrections immediately on its existing P1 branch; no owner decision or separate Team B sign-off is needed to start.

## Five rule dispositions for Team B

| Rule | Disposition and writer consequence |
|---|---|
| Exact mutual attempt/geometry relationship | Accepted. For `listo`, allocate both IDs, insert the terminal attempt with its geometry ID, then insert the matching geometry inside the same transaction. The geometry-to-attempt FK is immediate; the reverse FK is deferred until the outer transaction commits. Rejected, selection-required and internal-error attempts carry no geometry. A `listo` result may have `utilizable = 0`; storing a valid result is separate from activating an eligible layout. |
| Available bytes require final key, verified size and hash | Accepted. Verify the final object before the transaction; set these fields when moving to `disponible`. No half-finalized available row. |
| Finalization and termination metadata follow the state | Accepted. Completion/failure records finalization actor/time; all terminal states record termination time. Pending versions have neither. This does not authorize long byte I/O or parsing inside a database transaction. |
| Retirement always has a reason | Accepted. The same mutation records retirement time and the allowed reason. |
| Audit references to attempts/geometry require a file version | Accepted. Events must retain the version ID, including when they also identify the attempt and geometry. This closes a nullable-composite-reference gap. |

The atomic successful path is: copy/verify/parse outside the database transaction; inside a short transaction recheck current authorization and lease ownership, finalize the version, insert attempt then geometry, conditionally update the active decision, append events and release the lease. All steps commit together. Retries/selection on an already finalized version add their attempt/geometry without rewriting that immutable version. An unsuccessful parse stores its permitted terminal attempt without a geometry; it never invents a polygon to satisfy the constraint.

The handoff claim “a one-line change” is not an acceptance criterion. Any change to a constraint also needs the corresponding migration/fixture test and a clear writer contract.

## F1 — [P2] NULL bypass in the non-application reason constraint

**Location:** reviewed `server/db.py:533`, `archivo_version`:

`CHECK (motivo_no_aplicada IS NULL OR aplicada = 0)`

When `aplicada` is NULL and a reason is present, this expression evaluates to NULL, not false, so the CHECK accepts it. The adjacent outcome constraint intentionally requires `aplicada` to be NULL for `subiendo`, `cancelado` and `expirado`. Together they permit an impossible outcome representation that the report's state table says is forbidden.

**Independent reproduction on the exact head, SQLite:** each of these inserts successfully committed:

| State | aplicada | motivo_no_aplicada |
|---|---|---|
| subiendo | NULL | superada |
| cancelado | NULL | superada |
| expirado | NULL | superada |

**Required correction:** make a non-null reason require an explicitly non-null zero outcome, with NULL-safe boolean logic on both SQLite and Postgres. Preserve valid available/non-applied reasons and valid NULL reasons. Do not change the product lifecycle or weaken the state matrix.

**Regression evidence:** for each of those three states, reject both allowed non-null reasons (`superada`, `retirado`) at the database boundary. Include controls for their valid NULL-reason forms and available/non-applied forms. Run the cases against both schema test backends. The existing mutation/removal check did not cover these NULL combinations; testing that removal weakens a CHECK does not prove all its branches work.

## F2 — [P2] SQLite backups retain active processing leases

**Location:** reviewed `server/db.py:985–992`, existing `backup()` cleanup; new P1 backup requirements and tests.

Postgres excludes `archivo_trabajo` from its content payload. SQLite's actual backup copies the full database and then clears only `team_session` and `team_login_failure`. It therefore retains `archivo_trabajo`. Restoring that backup brings an old fencing token/lease into a database with no corresponding worker, contrary to P1's no-lease restore contract.

**Independent reproduction:** create a pending upload with one future-dated lease, call the actual `db.backup(explicit_disposable_path)`, then open the returned file. The backup contains **one lease** and the pending version; the source also retains its lease. The P1 test manually rebuilding rows from `postgres.ATTACHMENT_TABLES` proves logical insertion order but does not exercise this SQLite backup path.

**Required correction:** remove attachment lease rows from the SQLite backup copy using the existing operational-state cleanup mechanism. Do not delete them from the live source, alter durable attachment content, introduce a production cleanup job, or assume all backup sources already have schema 10. Existing table-presence handling must continue to support older databases.

**Regression evidence:** exercise actual `db.backup` on a disposable schema-10 database containing a live lease, a pending version, and finalized cyclic attachment data. The copy must contain zero leases while retaining durable rows/pointers; the source lease and content remain unchanged. Confirm older-schema backups still work. Keep the existing Postgres payload exclusion and restore-order tests.

## Evidence and limits

- Full independent `./verificar.sh` passed on the exact PR head in an isolated macOS archive: **750 Python tests, 68 Postgres-only skips**, complete **Python 3.9.6** suite, and JavaScript tests.
- GitHub on that same head: **Python and disposable Postgres SUCCESS; JavaScript SUCCESS**, run [37793895942](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37793895942).
- Both findings above were reproduced independently on SQLite after those checks. Green CI does not cover the missing cases.
- Independent positive controls committed `rechazado`, `requiere_seleccion` and `error_interno` attempts without geometry, and a `listo` attempt with a stored `utilizable = 0` geometry. The existing exact-head suite covers the stricter pointer/metadata cases.
- Local Postgres, hosted application flows and independent lint/type checks were not run by the supervisor. Require the corrected backend tests in disposable-Postgres CI; do not represent the local reproduction as a hosted test.

The supplied [reproduction script](reproduce.py) runs against a disposable archive of the reviewed head and uses fictional fixture data. It does not change application code. It prints both findings and exits nonzero while either persists.

## Immediate assignments

**Team A:** fix F1/F2 on `claude/team-a/attachment-schema` / PR #15 in normal commits. Add regressions, rerun required checks and obtain green CI on the corrected head. Append the disposition and exact test evidence to your report; preserve the original submission as history. Keep schema 10 for this unmerged/unreleased correction unless main or an actual deployment has changed; disclose any such change rather than assuming it. Return the exact corrected head for review. Preserve PR #14 and all B-owned branches. No merge, deployment or A-2/P2 implementation is included in this correction packet.

**Team B:** continue the independently released display-strategy investigation from `84b2b84`. The five writer requirements above are accepted for the later attachment packet; no new B application task or response is required now. Do not implement against the erroneous NULL behavior or assume the SQLite lease backup issue is a B-owned fix.

After these bounded corrections, P1 can be re-reviewed for the dependency handoff. The supervisor remains responsible for the next A-2/P2 and B lifecycle packets; there is no new owner choice created by this review. Nothing was merged, deployed or provisioned.
