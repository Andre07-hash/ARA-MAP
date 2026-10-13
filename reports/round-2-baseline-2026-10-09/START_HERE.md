# Round 2 combined baseline

A development checkpoint: accepted 1A (terrain records) and accepted 1B
(attachment lifecycle), assembled and tested together, so 2A and 2B build on
one commit. **Not a merge approval and not a release candidate.** It adds no
route, screen or domain behaviour of its own.

- Instruction commit: `13840c0deaf7f78f79609126115d03769e27fd0a`,
  `reports/round-2-instructions-2026-10-09/START_HERE.md`.
- Branch: `claude/integration/round-2-baseline`. Draft PR targets
  `claude/integration/round-1-baseline`. PR #20 and its branch are unchanged at
  `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`.
- `origin/main` when assembled: `09452fd26d38319567dce28a89db100ea61c739a`.
- **The exact checkpoint head is the head of that draft PR, stated in its
  description.** Team B: merge that SHA, not "the branch tip later". This file
  cannot name its own commit.
- The branch is frozen after publication. A repair, if one is ever needed, is
  an additive commit recorded at the end of this file and announced to both
  teams.

## Source manifest

Heads observed on GitHub when assembled, equal to the accepted pins.

| # | Component | PR | Exact commit | How it entered |
|---|---|---|---|---|
| 0 | 1A scoped terrain-record backend | #22 | `1ef2238766eae3e111c031b4fa24f9d849ef4753` | Branch start. Contains the round 1 baseline (#20, `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`) as an ancestor; not merged again |
| 1 | 1B attachment lifecycle | #23 | `a9dc8af8cc511bde0a67168da335398353b80aa6` | Ordinary merge (`--no-ff`), commit `0c4345f`; source history preserved |

**Not included:** the display research #21 and #16, Excel #6, the hosted
adapter #4, and every other parked branch.

Schema version: **10**. No migration is added by the assembly.

## Conflicts and resolutions

**None, textual or semantic.** The merge applied cleanly and the combined suite
passed without a repair. After the merge each team's files are byte-identical
to their accepted pin (`git diff <pin> HEAD -- <files>` is empty):

- against #22: `server/api/`, `server/app.py`, `server/auth.py`, `server/db.py`,
  `server/postgres.py`, `server/inventario.py`, `server/repo/inventario.py`,
  `server/repo/maestra.py`, `web/`;
- against #23: `server/archivos.py`, `server/repo/archivos.py`,
  `server/kmz.py`, `server/almacen.py`, `tests/test_archivos.py`,
  `tests/fixtures/`.

No authorization, schema or lifecycle code was changed to make anything pass.

## The composition test

`tests/test_composicion_ronda2.py`, one test per database. Test only.

1A is exercised through its real routes and real sessions over HTTP. 1B has no
route yet (2B), so it is exercised through its real service functions
(`server.archivos`) with the same validated sessions, the real parser and the
in-memory store.

1. An operator creates a blank terrain in her base (`POST
   /api/maestra/bases/:bid/terrenos`). Terrain version 1.
2. She attaches a PDF and a KMZ layout (`iniciar` → `escribir_temporal` →
   `completar`). Both apply, the layout has an active geometry, and the terrain
   version is still 1.
3. A cell edit (`PATCH`): terrain version 2; every attachment row, and each
   attachment revision, is unchanged.
4. An administrator transfers the terrain to another base: version 3, same
   attachment rows. The source-only operator now gets the one `not_found` for
   the attachment list, its history, a `completar` replay of her own upload, an
   `iniciar` replay with her own idempotency key, and a retirement. The
   destination operator and the administrator read the same attachment and
   version ids.
5. Transferred back: her `completar` replay returns the same version id with
   `replay: true` and creates nothing.
6. Her grant is revoked: denied again, as is an operator with no grant; the
   others still read the same references. Granted again: the replay and the
   list return the same ids.
7. Retiring the PDF moves that attachment's revision by one and leaves the
   terrain at version 4 with 4 revisions (create, edit, two transfers).

`archivo_version`, `archivo_intento` and `geometria` rows are compared whole
before and after every step and never change.

## Combined verification

All on the checkpoint head named in the PR. Disposable databases and fictional
data only. One developer Mac.

| Check | Result |
|---|---|
| `./verificar.sh` (macOS, SQLite) | Python suite 1,121 tests OK, 165 skipped (all require Postgres); complete suite on Python 3.9.6 OK; JavaScript 120 tests, 120 pass |
| Same suite on disposable local Postgres 16 (Python 3.12.15, psycopg 3.3.6) | 1,121 tests, 0 skipped, OK |
| `mypy server/` (2.4.0) | clean, 49 source files |
| `ruff check server/ tests/` (0.16.10) | **1 finding, carried in, not repaired here:** `tests/test_registros_maestra.py:562` UP031 (percent format), a line of accepted #22. This ruff is newer than the one #22 was checked with. The checkpoint changes no accepted file; the one-line fix goes in the 2A branch |
| GitHub Actions on the PR | recorded in the PR (Python + disposable Postgres, JavaScript) |

Test count by origin: 1,041 on #22; 1B's suite brings it to 1,119; the
composition test adds 2 (one per database).

Not run: browser tests (`tests/e2e/`), any hosted or Preview environment,
coverage measurement.

## What the checkpoint is, for each team

- **Team B (2B):** merge the exact checkpoint head into
  `claude/team-b/attachment-http` and target your draft PR at
  `claude/integration/round-2-baseline`. Do not merge Team A's
  `claude/team-a/master-grid`.
- **Team A (2A):** `claude/team-a/master-grid` starts at the checkpoint head.

## Known state carried in, not introduced here

- 1B's lifecycle has no HTTP route and no screen; 1A's routes have no screen.
- Every existing account is an operator with no grant until an administrator
  is named with `scripts/cuentas.py` (P2 release gate).
- Release notes from 1A still stand: `ANALYZE` after a bulk load on Postgres,
  the list maximum is 200, idempotency keys are per account and per base.

## Additive repairs after publication

None.
