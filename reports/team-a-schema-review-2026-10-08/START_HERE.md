# A-1 supervisory review — schema 9 accepted

**Accepted for the schema-only A-1 milestone** at PR [#14](https://github.com/Andre07-hash/ARA-MAP/pull/14), head **`24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`**, October 8, 2026. No blocking finding or correction is requested for this scope.

Instruction reviewed: `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`, especially `reports/workspace-contract-2026-10-07/TEAM_A_PACKET.md`. Application baseline remains `09452fd26d38319567dce28a89db100ea61c739a`. PR #14 remains draft and unmerged. Acceptance does not deploy schema 9 or enable permissions, work-base assignment, custom-field editing or attachments.

This supersedes only the earlier status that no A-1 implementation was published. Previous reports remain historical evidence.

## What is complete

- Shared SQLite/Postgres definitions for work bases, grants, roles, local custom-column definitions, and account/base/column audit records.
- Nullable terrain and revision base membership, nullable terrain type, and empty-default custom values. Existing business values and history remain intact; accounts default to operator without grants, with no automatic administrator promotion.
- Additive, repeatable migration from schema 8, compatible existing reads/writes, and inclusion of the new content tables in Postgres backup/seed ordering.
- Migration and relationship tests on fictional SQLite and disposable Postgres data. Application role enforcement remains unchanged, as required by the packet.

Only the two database adapters, migration tests, two schema-version assertions and the team's report changed. No B-owned implementation, auth, route, UI, CI or deployment file changed.

## Contract dispositions

| Implementation choice | Supervisory disposition |
|---|---|
| Existing English metadata names (`created_at/by`, etc.) | Accepted. Consistency with existing inventory storage is appropriate; Spanish user-facing language is unchanged. |
| Additional `maestra_base_event` table | Accepted. It supports the explicitly required base/column definition audit and version history. |
| Bare UUID in `inventory_column.id`; `custom:` prefix at the API boundary | Accepted. A-5 must implement the agreed external key consistently. |
| Nullable account-event actor ID for command-line administration | Accepted for the CLI case, with actor name retained. Future HTTP writers must derive the actor from the authenticated session, never client input. |
| No base/column name uniqueness rule and no revision-base index yet | Accepted for A-1. Later packets must define relevant validation and add indexes based on actual scoped queries; this is not a new product decision about duplicate labels. |
| Existing revision writers still use defaults for the new fields | Accepted only while those fields cannot be populated through application workflows. Before any assignment/type/custom-value workflow is enabled, every affected writer must preserve those fields. A-3 is the planned owner, but the dependency follows behavior rather than a milestone label. |

Append-only audit behavior is an obligation of future repository writers; these tables alone do not enforce it against arbitrary SQL. Future writers must also validate that a column event's base matches the column's owning base. Neither requires expanding this schema-only PR into business logic.

## Independent verification

The supervisor reviewed the exact head's schema, adapter changes, tests and release note, then exported that commit into an isolated temporary directory. Database-related environment variables were removed and SQLite was directed to a disposable path.

- Full **`./verificar.sh` passed** on macOS: **702 Python tests, 44 skipped**, the complete system **Python 3.9.6** suite, and JavaScript tests.
- The skipped tests require Postgres. No local Postgres test or hosted application test was performed by the supervisor.
- GitHub checks on the same head: **Python and disposable Postgres SUCCESS; JavaScript SUCCESS**, run [37785875135](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37785875135).
- The team's reported ruff/mypy results were read; the supervisor did not independently rerun those tools. No production data, account or cloud resource was accessed.

The migration tests cover preservation of existing records, repeat initialization, default roles/unassigned membership, relationship constraints, audit retention, and unchanged existing responses. This is evidence for the database foundation, not for the complete employee workflow.

## What this unlocks, and what remains

**A-1 is complete.** The supervisor can now consolidate the attachment prerequisite against an exact accepted schema rather than waiting for unpublished Team A work.

The next coordinated packets still need to define:

1. **Team A: P1 attachment migration**, reconciled with PR #12's current proposal and the accepted A-1 schema. Do not allocate or implement the next migration from an unreviewed proposal.
2. **Team A: A-2/P2 roles, work-base grants and shared authorization**, including the transaction-scoped authorization recheck and a reviewed administrator bootstrap/recovery procedure before enforcement. No account is promoted by this review.
3. **Team B: database-backed attachment lifecycle**, after the consolidated contract and exact P1 dependency are released. HTTP handlers additionally depend on A's scoped authorization interface and implementation. Exact stacked draft commits can support dependent work without merging first.

PR #12 at `28bf0dbbf718571e35d501a7810d7e7d882ee3dd` has its four review responses accepted, but the full database/API contract and D1–D5 decisions remain to be consolidated. A-1 acceptance does not silently freeze those decisions or authorize B-3 against the proposal alone.

B's accepted parser (#9), boundary renderer (#11), and standalone local/fake storage (#13) remain available at their previously accepted heads. No additional B correction is requested. The large multipart display strategy remains an integration requirement.

**Coder stopping point:** A-1 is accepted, but its packet explicitly requires a separate next assignment. Preserve the reviewed heads while the supervisor issues the consolidated prerequisite/API packets. This review does not start A-2, P1 or B-3, and authorizes no merge, deployment or provisioning.
