# Round 1 combined prerequisite baseline

A development checkpoint: the accepted components, assembled and tested
together, so both teams build round 1 on the same commit. **Not a merge
approval and not a release candidate.** It adds no feature of its own.

- Instruction commit: `f3fd0f05c0ba9f28bd8b3e7321f374368027e784`,
  `reports/round-1-instructions-2026-10-08/START_HERE.md`.
- Branch: `claude/integration/round-1-baseline`. Draft PR targets `main`.
- `origin/main` when assembled: `09452fd26d38319567dce28a89db100ea61c739a`
  (unchanged from the instruction).
- **The exact checkpoint head is the head of that draft PR, stated in its
  description.** Team B: branch from that SHA, not from "whatever the branch
  tip is later". This file cannot name its own commit.
- The branch stays stable. Any later repair is an additive commit, recorded at
  the end of this file and announced to both teams.

## Source manifest

Started at the accepted P2 head; the other three merged in this order with
ordinary merge commits (`--no-ff`), source history preserved.

| # | Component | PR | Exact commit | How it entered |
|---|---|---|---|---|
| 0 | A-2/P2 roles and write-boundary authorization | #17 | `5d0844cfd678c2f7ec55ddb4b364275482d1a801` | Branch start. Contains P1 (#15, `edf9bcd1dc51e74a627d54d5ce01d37113206055`) and A-1 (#14, `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`) as ancestors; not merged again |
| 1 | B-1 KMZ parser | #9 | `efc362818ba64618dbfc23556db8678cde525336` | Merge `d1eaa76` |
| 2 | B-3S storage core | #13 | `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53` | Merge `6b6375f` |
| 3 | B-2 boundary renderer with E1 drawing | #19 | `eed9a4cb404406b8b261803c38947e8297a5edec` | Merge `be2e484`. Contains B-2 (#11, `5d8e2dcc125a688dbba38a260d5d7eca88a6d223`) as an ancestor; not merged again |

**Not included:** Excel #6, the hosted adapter #4, the display research #16, the
memory-budget prototype, the attachment proposal #12 (documentation), and the
preparation reports #8 and #10.

Schema version: **10**. No migration is added by the assembly.

## Conflicts and resolutions

**Textual conflicts: none.** All three merges applied cleanly. After the merges
each component's files are byte-identical to its pinned commit (checked with
`git diff <pin> HEAD -- <its files>`): `server/kmz.py`, `tests/test_kmz.py` and
`tests/fixtures/kmz/` against #9; `server/almacen.py` and `tests/test_almacen.py`
against #13; `web/` and `tests/js/` against #19; `server/auth.py`, `server/db.py`,
`server/app.py`, `server/postgres.py`, `server/repo/`, `server/api/`, `scripts/`
and the role and schema tests against #17.

**One semantic conflict, repaired in one additive commit,
`9f9944013458c17254fdcde2c347b61e3122cd70`: `tests/test_kmz.py`, one assertion.**

- *What failed.* `Forma.test_el_modulo_no_esta_conectado_a_la_aplicacion`
  asserted that no file under `server/` or `api/` other than `kmz.py` contains
  the word `kmz`. That was true on the parser's own branch. Combined with the
  accepted P1 schema, `server/db.py` contains `'kmz'` as an attachment type and
  `'core:kmz'` as a column id, so the test failed although nothing imports the
  parser.
- *Resolution.* The assertion now looks for an `import` / `from … import` of
  the name `kmz`, which is the property the test's name states. Verified that
  it still fails when a probe file under `server/` imports the parser.
- *What did not change.* No parser, storage, renderer, schema or
  authorization code. No interface. The other 986 tests are as merged.
- *Why Team A edited a Team B test.* The assembly is A's, the alternative was a
  red baseline, and the edit is confined to the one assertion that the
  combination made false. **Team B and the supervisor should confirm it states
  the intended guard**; if B prefers another wording it replaces this one in an
  additive commit. When B wires the parser into its attachment service (1B),
  this test will need to name that one allowed importer; that is B's change.

No other failure, warning-as-error or type error appeared in the combined
tree.

## Combined verification

All on the checkpoint head named in the PR. Disposable databases and fictional
data only.

| Check | Result |
|---|---|
| `./verificar.sh` (macOS, SQLite) | Python suite 987 tests OK, 99 skipped (all require Postgres); complete suite on Python 3.9.6 OK; JavaScript 120 tests, 120 pass |
| Same suite on disposable local Postgres 16 (Python 3.12, psycopg 3) | 987 tests, 0 skipped, OK |
| `ruff check server/ tests/` | clean |
| `mypy server/` | clean, 47 source files |
| GitHub Actions on the PR | recorded in the PR (Python + disposable Postgres, JavaScript) |

Test count by origin, for orientation: 812 on the P2 head; the parser and
storage suites bring the Python total to 987; the renderer brings the
JavaScript total to 120.

Not run: browser tests (`tests/e2e/`), any hosted or Preview environment,
coverage measurement.

## What the checkpoint is, for each team

- **Team B (1B):** branch `claude/team-b/attachment-lifecycle` from the exact
  checkpoint head, or merge that head into a preparation branch. It gives you
  schema 10, `db.escritura()` and `auth.reverificar_terreno`, `server/kmz.py`
  and `server/almacen.py` in one tree. Target your draft PR at
  `claude/integration/round-1-baseline`. Do not include Team A's
  `claude/team-a/master-record-backend`.
- **Team A (1A feature):** `claude/team-a/master-record-backend` starts here.

## Known state carried in, not introduced here

- Every existing account is an operator with no grant until an administrator is
  named with `scripts/cuentas.py`; the current interface is not usable by
  operators. Both are release gates recorded in the P2 report.
- The parser, the storage core and the renderer's boundary path are present but
  not connected to any route or screen.

## Additive repairs after publication

None.
