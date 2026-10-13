# Team A — A-1 schema foundation (schema 9)

Storage for work bases, access grants, roles and base-local custom columns.
**Schema only:** no route, role check or screen uses it yet, and the running
application behaves exactly as it did on schema 8.

- Instruction commit: `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`
  (`reports/workspace-contract-2026-10-07/`, branch `codex/supervisor-completion-brief`).
- Application baseline: `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`,
  unchanged since the packet was issued. Schema 8 → **9**.
- Branch: `claude/team-a/schema-9`. The implementation commit is named in the PR.
- Excel PR #6 is untouched; nothing was taken from it and no number is reserved for it.

## What schema 9 adds

| Object | Purpose |
|---|---|
| `team_user.rol` | `'admin'` / `'operador'`, check-constrained, default `'operador'` |
| `maestra_base` | Work base: UUID, name, `version`, actor/time, reversible `archived_at/by` |
| `maestra_base_acceso` | One grant per (base, user), with who granted it and when |
| `inventory_terrain.base_id` | Owning base, nullable. Indexed for scoped queries |
| `inventory_revision.base_id` | The base the record belonged to when that revision was written |
| `inventory_revision.tipo_terreno` | Nullable text |
| `inventory_revision.custom_json` | Custom values, `NOT NULL DEFAULT '{}'` on both databases |
| `inventory_column` | Custom column of one base: `texto`/`numero`/`opcion`/`fecha`, `opciones_json` (default `'[]'`), `orden`, `version`, reversible `retired_at/by` |
| `team_user_event` | Append-only account, role and grant history |
| `maestra_base_event` | Append-only base and column-definition history, one event per version |

The definitions are in `server/db.py` (`WORK_BASE_SCHEMA`, `V9_COLUMNS`,
`V9_INDEXES`) and are the single source for both databases: `server/postgres.py`
derives its DDL from them. A new database receives the v9 columns through the
same `ALTER`s as an upgraded one, so the two cannot drift.

Properties that later packets rely on:

- **Nothing cascades.** A base, account or column that anything refers to cannot
  be deleted. Bases are archived and columns retired; terrains, revisions,
  stored custom values and history stay.
- **A revoked grant stays in history.** `team_user_event` names the user and the
  base, not the grant row, so the grant itself can be deleted.
- **The migration promotes nobody and assigns nothing.** Every existing account
  becomes `operador` with no grants; every existing terrain and revision keeps
  `base_id` NULL. No historical value or event is rewritten.
- **Core columns are not rows.** `inventory_column` holds custom columns only.
- Existing reads and writes name their columns explicitly, so the new fields
  appear in no existing response, internal or public. A test pins this.

## Contract notes and deviations

1. **Column names.** The preparation report sketched Spanish metadata names
   (`creado_en`, `otorgado_por`). The implementation uses the names the existing
   inventory tables already use (`created_at/by`, `updated_at/by`,
   `archived_at/by`, `granted_at/by`, `retired_at/by`). Domain names stay Spanish
   (`nombre`, `tipo`, `opciones_json`, `orden`, `rol`).
2. **`maestra_base_event` is an addition** to the tables listed in S1. The packet
   asks for actor/time history and conflict provision for base and column
   definitions; `team_user_event` is scoped to accounts, roles and grants.
3. **`inventory_column.id` stores the bare UUID.** The `custom:` prefix of the
   contract belongs to the API, which A-5 adds.
4. **`team_user_event.actor_id` is nullable**, for changes made from the
   operator's command line (`scripts/cuentas.py`), which has no signed-in account.
   `actor_name` is always recorded.
5. **Not added, on purpose:** uniqueness of base or column names (a product rule
   for A-2/A-5 to decide), and an index on `inventory_revision.base_id` (no query
   needs it yet).
6. **Edits outside the migration:** `postgres.INVENTORY_TABLES` gains the five new
   tables in dependency order, so cloud backups and `setup_cloud.py` seeding carry
   them. Two existing tests that pinned the literal version `8` now read
   `db.SCHEMA_VERSION`. No repository, auth, route or frontend file changed.
7. An existing edit writes a revision with `base_id` NULL and `custom_json`
   `'{}'`, which is correct while nothing can assign a base. **A-3 must carry
   `base_id`, `tipo_terreno` and `custom_json` forward** when it writes revisions.

## Release note for whoever deploys

- **New schema version: 9.** Additive only: five tables, five columns, one index.
  No table is rebuilt and no row is rewritten.
- **Upgrade path:** from 8, and from 7 directly (production was at 7 when this
  was written; the step creates the v8 tables first). SQLite upgrades on first
  open. Postgres upgrades with the existing reviewed command path
  (`scripts/esquema.py` / `scripts/migrate_cloud.py`), as a release step.
  Re-running either changes nothing.
- **Backup and restore:** SQLite takes its usual automatic copy before the
  upgrade. For Postgres take a backup before the step; backups taken after it
  include the new tables. There is no downgrade script: going back means
  restoring the backup. Code from `main` at schema 8 keeps working against a
  schema-9 database, because the new columns are nullable or defaulted.
- **Before role enforcement ships (A-2, not this PR):** every account is
  `operador` with no grants after this migration. Enforcing roles in that state
  would lock everyone out of administration. The A-2 release step must name an
  administrator, set that role and the needed grants with `scripts/cuentas.py`,
  verify the sign-in, and keep a recovery path (the same command, run by whoever
  holds database access). This PR changes no account and needs no production or
  cloud access.

## Evidence

See the PR description for the tested commit, the local results and the GitHub
Actions run on disposable Postgres. Local runs skip the Postgres tests; they are
not database-compatibility evidence.

Tests are in `tests/test_schema_v9.py`: one set of checks, run against a
synthetic schema-8 SQLite file and a synthetic schema-8 Postgres schema, both
with fictional data.

## Next

Stop for supervisor review. A-2 (roles and work-base grants) does not start
until this is reviewed.
