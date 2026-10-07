# Team A — A-1 schema foundation

## Assignment

Implement **A-1 only**, following [the shared contract](SHARED_CONTRACT.md). The owner has approved the work-base/access model and the review adjustments. Team A preparation PR #10 at `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6` is accepted as preparation with this packet's corrections; do not repeat that investigation or wait for D0 approval.

Fetch and start from current `origin/main` (at packet issue `09452fd26d38319567dce28a89db100ea61c739a`) on `claude/team-a/schema-9`. Read the exact supplied instruction commit using `git show`; do not develop on the supervisor's documentation branch. Follow the baseline `AGENTS.md`/`CLAUDE.md`, with current owner-approved domain rules taking precedence over obsolete descriptions.

## Scope

Add the next migration on both SQLite and Postgres, expected schema 9 from main's schema 8. Recheck main before assigning it. Do not reserve a number for parked Excel PR #6, take changes from it, or edit B's files.

Implement the schema requirements from PR #10 S1, refined as follows:

- `team_user.rol`: admin/operator check constraint, default operator; no automatic admin promotion. Append-only account/role/grant audit storage (`team_user_event`) compatible with current identity types.
- `maestra_base`: stable UUID, name, actor/time metadata, reversible archive state; provision conflict/version metadata for concurrent administration.
- `maestra_base_acceso`: unique base/user grant, granting actor/time, appropriate foreign keys/indexes. Grant revocation audit remains representable after deleting the active grant.
- `inventory_terrain.base_id`: nullable base relationship; existing rows remain unassigned. Membership for future edits must be reconstructable in revisions as well as current state: add a nullable base snapshot to revisions or an equally explicit compatible revision representation. Do not rewrite historical field values or events to fabricate assignment history.
- Nullable `inventory_revision.tipo_terreno`, and JSON-text `custom_json` with a consistent empty/default representation across databases. Keep private `notas_internas`; do not add a duplicate Comentarios field.
- `inventory_column`: stable custom ID, owning base, text/number/choice/date type, choice options, order, actor/time and reversible retirement metadata; provision definition conflict checks/audit. Core definitions remain protected and may be static; do not turn core field names into mutable custom rows.
- Add only the indexes/constraints required for these relationships and later scoped queries. No destructive cascade may erase terrains, revisions, retained values or file history when a base/user is removed.

Use the existing migration framework. Preserve current repository/application behavior; do not enable role enforcement or new screens in this schema-only PR. Adapt low-level row readers/types only if required to keep existing code/tests compatible and disclose those edits. Business endpoints, transfer implementation, grid, account UI, price validation changes and attachments are later packets.

## Acceptance evidence

1. Upgrade a synthetic schema-8 database on both SQLite and disposable Postgres. Keep existing terrain IDs, revisions/events, accounts, legacy bases and saved maps intact; business values do not change. Re-running initialization must not duplicate data or repeat migrations incorrectly.
2. Existing accounts become operator/no grants in the new columns only; the current running auth behavior is unchanged by A-1. Existing terrain membership remains null. No live account or data migration is performed.
3. Test meaningful constraints: bad roles/types, duplicate grants, orphan references and attempts to erase referenced records. Test valid empty bases and local column definitions for two distinct bases. Use fictional data.
4. Existing code can read/update records after migration, with defaults handled consistently and no private/internal fields leaking into public output. Future membership/type/custom fields must not silently enter public allowlists.
5. Run `./verificar.sh`, applicable lint/type checks and GitHub's disposable-Postgres job. Report exact tested commit and environment; do not substitute a skipped local Postgres run for database compatibility evidence.

Include a short release note: new schema version, supported upgrade path, backup/restore assumptions, and the **later** administrator bootstrap/recovery step required before enforcing roles. No production database or cloud account access is needed.

## Return / next step

Open a draft PR with the exact instruction SHA, baseline, implementation SHA, migration tests and any contract deviation. Return for supervisor review. Do not proceed automatically into A-2 or merge unrelated PRs as part of this packet.

In parallel, B implements B-2 in its owned map files. Review its shared-hook requests when provided; do not patch the map renderer yourself. Before B-3, you will receive a separate attachment-prerequisite packet so its migration is not trapped inside a later integration task. No additional owner approval is needed for the already approved workspace direction; ask the supervisor only about a concrete incompatible contract issue.
