# R3-A1: batched file summaries for one page (Team B)

A bounded optimization for supervisory review. A measured that one page of
200 terrains went from 11 statements (the list alone) to 1,611 (the list with
`archivos`). The file summaries cost 8 statements per terrain. This change
authorizes and summarizes the page by batch. Results, permissions, privacy
and errors are unchanged.

## Heads

| What | Commit |
|---|---|
| Base: pinned combined candidate (green CI) | `41d029c54848a7aebb1d46dfd053848ccf265afc` |
| Tests, failing on the base where they must | `459dc59e3f5f0c1c8f69357e7c3454b513366419` |
| **Code head** | `781e79b4a881e63c73d02403118664f14ce039e9` |
| Final head (adds this report) | given in the draft PR's description |

The branch is `claude/team-b/file-summary-batching`, a new branch from the
pin. Its draft PR targets `claude/team-a/application-integration`. Nothing was
written to that branch. PR #28 and its branch are unchanged. Using the pin as
a base does not mean Round 3 is accepted.

## Changed files

| File | Change |
|---|---|
| `server/auth.py` | New `terrenos_legibles` (plus `LOTE_LECTURA`): `require_terreno`'s read decision for a bounded list. No other line changes |
| `server/repo/archivos.py` | `summaries` is batched (plus `LOTE_RESUMENES`, `RECIENTES_PDF`). The projection `_summary_row` / `pending_view` is reused unchanged |
| `server/archivos.py` | `resumenes_de_archivos` calls the two batched reads. Same signature and response |
| `tests/test_resumenes_lote.py` | Equivalence, privacy, permissions, sessions, inputs, chunks and statement counts, on SQLite and Postgres |
| this folder | Report, `medir_lote.py` (before/after), `mutaciones_lote.py` (negative controls), evidence |

No change to the frontend, the schema, `require_terreno` or `_verificar`,
write re-verification, locks, the dispatcher or the consumer (`_presentar`).
There is no new dependency, no cache between requests, and nothing touches
cloud storage or the renderer.

## How it works

**Authorization: `auth.terrenos_legibles(conn, sesion, ids, capacidad)`.**
- **Capabilities.** It works only for read capabilities and raises
  `ValueError` for any write capability.
- **Duplicates.** They are dropped in first-seen order, as before.
- **Empty list.** It sends no statement, as before.
- **Session first.** The session and the capability are checked once through
  `_verificar(conn, sesion, capacidad)` itself, with no terrain. So a revoked
  or expired session, an inactive account or a changed credential raise the
  same 401, and a missing capability the same 403, before any terrain is
  read. That is exactly what the first per-ID call did.
- **Batch reads.** Terrains, their bases, and the operator's grants on those
  bases are read once per 500 IDs. Administrators skip the grants.
- **Per-ID decision**, the same as `_verificar` for reads: a missing terrain
  is unavailable. A terrain without a base is unavailable to operators. A
  missing base is unavailable. An operator without a grant on the base, or
  whose base is archived, gets unavailable. Read capabilities never raise
  409, so an archived terrain stays readable inside the scope.
- **No shortcuts.** It takes no locks, it is not a write check, and it does
  not trust the caller: `_presentar` already listed the page, and every ID is
  authorized again here.

**Summaries: `repo.summaries`.** Per 500 terrains, two statements:
1. **Count.** `COUNT(*) … GROUP BY inventory_id` over live PDFs.
2. **Rows.** One query returns only the rows shown. For each terrain that is
   its five most recent live PDFs, chosen in SQL by a correlated
   `ORDER BY creado_en DESC, id DESC LIMIT 5` (the same order as before),
   plus its one live KMZ (`idx_archivo_kmz_vivo`). Each row carries its
   latest version and the live-lease flag, through the same `_LATEST_VERSION`
   join.

Rows are then projected with the unchanged `_summary_row`. Another account's
pending upload therefore stays generic, an overdue upload with no live lease
reads as `expirado`, and retired files stay out. Nothing beyond those rows
is loaded.

## Statements and time (before → after, same script, same data)

`medir_lote.py` was run unchanged in an archive of the base and in an archive
of the code head. The data is A's 3A dataset: 25,000 synthetic terrains,
3,000 in the measured base, and 60 with a PDF and a KMZ. The caller is one
operator session. Statements were counted by wrapping each connection's
`execute`. Times are the median of 9 rounds after a warm-up, in this
container only.

| Terrains | Service statements | Handler statements (whole list request) |
|---|---|---|
| 1 | 8 → **7** | 19 → **18** |
| 50 | 400 → **7** | 411 → **18** |
| 100 | 800 → **7** | 811 → **18** |
| 200 | 1,600 → **7** | 1,611 → **18** |

These are the same on SQLite and Postgres. For an administrator the service
takes 6 statements, because grants are not read.

**Remaining cost:**
- **Statements.** The service cost is constant up to 500 terrains, then 5
  more per further 500 (4 for an administrator), plus 2 once for the session.
  Pages are capped well below 500, so a page costs 7 statements.
- **Rows.** Rows returned grow with the page: at most 5 PDF rows and 1 KMZ
  row per terrain. The correlated subquery runs once per live PDF of the
  page's terrains, using the existing `idx_archivo_terreno` index.

| Median ms (this machine) | Service, 200 | Handler, 200 | Handler, 50 |
|---|---|---|---|
| SQLite | 12.2 → 4.4 | 46.7 → 36.5 | 26.5 → 26.3 |
| Postgres 16 (loopback) | 222.2 → 14.7 | 285.4 → 93.7 | 131.6 → 79.1 |

Times are noisy where the list query dominates. At one terrain, the handler
median was higher after the change on both backends (SQLite 21.4 → 30.8 ms,
Postgres 76.1 → 104.3 ms) with the same statement count, which is noise at
that size. The statement counts are the result. The tests assert counts,
never times.

**Same answer on the large dataset too.** In the code tree, the script also
compares each page's result with the old algorithm on the same connection:
`igual_a_la_referencia` is true for all four page sizes on both backends.

## Tests and checks

| Check | Result |
|---|---|
| `tests/test_resumenes_lote.py`, SQLite | 10/10 |
| `tests/test_resumenes_lote.py`, disposable Postgres 16 | 10/10 |
| The same final file on the base `41d029c` (SQLite) | **4 of 10 fail**: the statement count (8 per terrain for an operator, 7 for an administrator), chunking and the two helper tests (no batching, no helper). The 6 equivalence and projection tests pass, as they must, because the base *is* the reference behavior |
| `mutaciones_lote.py` (9 rules broken one at a time) | **9/9 detected**, control passes |
| Full suite, SQLite, Python 3.13 / 3.9.25 | 1,274 run, 233 skipped (Postgres), 1 failure: the known environmental `test_the_system_python_has_no_openpyxl_of_its_own` (this container's system Python has openpyxl); identical on both versions |
| Full suite, disposable Postgres 16 | 1,274 run, 0 skipped, the same single environmental failure |
| `ruff check server/ tests/`, `mypy server/` | clean; clean (54 files) |

**What the equivalence tests compare.** The old per-terrain algorithm is kept
verbatim in the test as the reference. Both run on the same fixture, and the
tests compare the full output: keys, insertion order of `resultados`, order
of `no_disponibles`, and every value, or the error's status and code. The
fixture has:
- **Accounts:** an administrator, operators with different grants, an
  operator without grants, an inactive account, and a changed credential.
- **Sessions:** revoked and expired, plus non-session values.
- **Scopes:** a granted base, an ungranted base, an archived base, an
  archived terrain, and an unassigned terrain.
- **Inputs:** empty, single, all, reversed, duplicated, missing,
  malformed and injection-shaped IDs, and only-foreign IDs.
- **Scope changes:** a revoke, a transfer and an archive between calls.
- **Chunk boundaries:** forced by shrinking both chunk sizes.
- **Files:**
  - seven live PDFs with a creation-time tie and two newer retired PDFs;
  - latest versions available, failed, cancelled, own pending, foreign
    pending that is overdue with no lease (`expirado`), and foreign pending
    that is overdue under a live lease;
  - a retired KMZ, and a live KMZ under another account's pending
    replacement;
  - a file with no version at all.

**Explicit assertions** (not only "same as before") cover:
- counts that exclude retired files;
- exactly five recent PDFs, in order;
- generic-only foreign pending uploads, with no private name, storage key or
  hash in the output;
- the administrator's own pending upload marked `propia`;
- operator scope: other, archived and unassigned terrains are reported
  unavailable.

**Auth helper.** `terrenos_legibles` is tested directly against per-ID
`require_terreno` for both read capabilities, `archivos.ver` and
`maestra.ver`. It refuses write capabilities.

## Limits

- No timing is asserted. The times above come from one container: they
  compare before and after and are not targets. A hosted or remote database
  was not measured; there, fewer round trips should matter more.
- The A measurement dataset has attachment rows without versions. Version
  states, leases and privacy are covered by the fixture in the tests, not by
  the timing dataset.
- No browser run, renderer benchmark or memory test, as the instructions
  ask. The consumer `_presentar` is unchanged, so A's interface work is not
  touched or duplicated.

Stopped for supervisory review. No merge, deployment or other tasks.
