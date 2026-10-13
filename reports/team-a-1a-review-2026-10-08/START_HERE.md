# Team A — independent review of 1A correction 1

Checked on **2026-10-09 at 00:43 UTC** (October 8 locally).
This is a bounded continuation of Round 1, not a new assignment.

## Verdict and exact inputs

**The SQL attention correction is accepted. PR #22 as a whole still needs
the three corrections below before 1A acceptance. Do not start 2A.**

- Reviewed [PR #22](https://github.com/Andre07-hash/ARA-MAP/pull/22), exact head
  `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037`.
- Correction diff: `5ec454f0d970f257455c23aabcb75cb694bd7299..f6cd6b2c45385d149f042c8eabd0e2a2e4db8037`.
- Intended baseline [PR #20](https://github.com/Andre07-hash/ARA-MAP/pull/20)
  is still `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`.
  Both PRs were open drafts. This review does not independently accept or merge
  the combined baseline and does not reopen the accepted P2 components.
- Instructions remain `f3fd0f05c0ba9f28bd8b3e7321f374368027e784`,
  `reports/round-1-instructions-2026-10-08/TEAM_A.md`.
- Developer handback:
  [correction comment](https://github.com/Andre07-hash/ARA-MAP/pull/22#issuecomment-6071832109)
  and `reports/team-a-master-record-backend-2026-10-08/START_HERE.md`
  at the reviewed head.

The correction was reviewed first, followed by the relevant compatibility,
history-projection and pagination paths in 1A. Findings A1–A3 are remaining
1A issues, **not regressions attributed to the SQL-attention correction**.

## Closed correction and numeric-warning decision

`repo.listar()` now counts and selects the attention-filtered page in SQL,
with `LIMIT n + 1`, instead of fetching every scoped record and filtering in
Python. The predicate covers the displayed reasons and its negation, including
the tested tolerance boundaries and extreme numeric inputs. The affected
integration tests passed independently on SQLite and disposable UTF-8
Postgres 17; two attention-specific tests also passed on Python 3.9.6.
No schema change is needed.

**Approve the added `VALOR_FUERA_DE_RANGO` AVISO as a technical consistency-check
guard**, not as a business limit. Keep the entered finite values, optional
fields, existing save validation and publication rules unchanged. The
`1e-100 … 1e100` guard is deliberately conservative; it is not a statement of
the database's complete representable range or of permissible property prices.

In the same corrective commit, replace the current message at
`server/inventario.py:168` ("fuera de cualquier rango real") with wording such as:

> Un valor es demasiado grande o pequeño para comprobar su consistencia
> automáticamente; revísalo.

Align the explanatory comment/constant description and report with that
meaning. No owner business decision is required for this non-blocking warning.
Do not clamp, convert, infer, reject or silently discard values to solve SQL
overflow/underflow.

## Remaining findings

### A1 — P2: legacy create retries compare incompatible request hashes

Locations: `server/api/inventario.py:113–117` and
`server/repo/inventario.py:300–317` at the reviewed head.

The fallback reads legacy `operation='create'` rows for the same actor, but
compares their old hash against the new scoped hash. The accepted baseline
hashed the normalized field map alone. 1A hashes `{base, campos}`. Thus an
unchanged request with the original key and actor returns **409
`idempotency_conflict`** after upgrading, contradicting the claimed legacy
compatibility. Both databases reproduce it; record count remains one, so this
is a failed retry, not evidence of duplicate creation.

Reproducer `old_idempotency` reconstructs the actual baseline hash and legacy
stored-result shape, then retries through the real HTTP dispatcher.

Required correction: distinguish legacy and scoped hash formats when reading
their respective operation rows. Preserve actor isolation and current-record
reauthorization; never return the old cached DTO. Do not weaken changed-body
conflicts or current base-scoped hashing.

Acceptance: same actor/key/body from a pre-1A stored operation returns the
current authorized record with no additional terrain, revision or event;
changed body still conflicts; another actor cannot obtain that record; revoked
access/demotion cannot replay private output. Exercise both database backends.

### A2 — P2: history projection only redacts top-level keys

Location: `server/repo/inventario.py:249–264`.

Non-admin history allows the entire `changes` object unchanged. With stored
custom diffs inside `changes`, a destination-only operator can read a retained
source-base custom value through `/historial` after transfer, even though the
detail DTO correctly hides it. The probe demonstrates both a stable
`custom:<definition-id>` entry and a nested `custom_json` before/after map.

**Evidence boundary:** this is a seeded stored-history fixture. Current
core-only writers do not generate these custom diffs; no claim is made that a
current normal core edit creates this exposure. Nevertheless, the released
1A contract explicitly requires protection of embedded history diffs and seeded
custom values, so deferring that read-side safeguard to 2A does not satisfy it.
No custom-column management or custom-value editing API is requested now.

Required correction: project permitted event details structurally using the
current terrain/base and stable definition IDs, including nested before/after
values and any labels. Unknown shapes must not become a pass-through. Preserve
the stored full audit and administrator access; do not destroy hidden values.

Acceptance: seed core plus source/destination custom history, transfer and
transfer back, retire a definition, and remove source access. Check source-only
denial, destination-only history redaction, preserved visible core/current-base
content, retained values on transfer back and the full admin audit. Verify
detail/list/replay/conflict projections remain safe. Run via the real dispatcher
on SQLite and Postgres. The precise supported event shape should be documented
now so 2A can use it without inventing a second contract.

### A3 — P2: wrong-type and unrepresentable cursors reach the database

Location: `server/repo/inventario.py:203–212`; API maps `CursorError` to 422,
but these cases never become `CursorError`.

The decoded cursor checks the sort name and excludes container/bool values,
but does not check the scalar against the sort's type or finite/representable
numeric domain. Independent actual requests produced:

| Decoded cursor value | SQLite | Postgres |
|---|---|---|
| `asking_price`, `"not-a-number"` | 200 | 500 |
| `asking_price`, integer `10**1000` | 500 | 500 |
| `terreno`, integer `5` | 200 | 500 |
| `terreno`, `NaN` | 200 | 500 |

Postgres reports invalid double input, numeric overflow or invalid text/numeric
comparison; SQLite raises an integer binding overflow on the huge integer.
The existing scope predicate remains present: this is controlled validation
and backend-parity failure, **not a demonstrated authorization bypass**.

Required correction: validate cursor shape, matching sort, ID and scalar type
before SQL binding; reject nonfinite/unrepresentable numeric payloads and
wrong-type text payloads with the documented controlled 422 response on both
backends. Preserve all valid emitted cursors, null-last traversal, stable ties
and scope enforcement. Do not turn arbitrary database failures into validation
errors to hide this problem.

Acceptance: the four probes above plus malformed encoding/shape, wrong sort,
invalid IDs, null values, finite numeric boundaries and valid ascending/
descending pagination. Include a reused cross-base cursor to retain the scope
guarantee. No cryptographic cursor redesign is required.

## Evidence and limits

- **GitHub exact-head CI verified:**
  [run 37865206294](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37865206294),
  Python/disposable-Postgres and JavaScript successful. Its log reports 1,035
  Python tests and 120 JS tests, zero JS failures. Team A reports no Python skips.
- **Independent:** all 48 `tests.test_registros_maestra` tests passed on the
  exact PR head using Python 3.14.5, SQLite and a fresh UTF-8 Postgres 17 instance,
  no skips: [record-tests.log](record-tests.log).
- **Python floor:** two affected SQLite attention tests passed on Python 3.9.6:
  [python39-attention.log](python39-attention.log).
- **Independent additional probes:** [reproduce.py](reproduce.py),
  [SQLite observations](probes-sqlite.jsonl),
  [Postgres observations](probes-postgres.jsonl), with corresponding
  [SQLite stderr](probes-sqlite-stderr.log) and
  [Postgres stderr](probes-postgres-stderr.log).
- Tests use fictional sessions/data and the real HTTP dispatcher. No production
  database, real terrain files or real accounts were accessed. The temporary
  Postgres instance was stopped after testing.
- The full 1,035-test suite and 25,000-record measurements were not independently
  repeated in this review. Their green CI/developer results do not negate the
  targeted reproductions. No new browser or hosted readiness claim is made.
- **Documentation publication gate:** `./verificar.sh` passed on the supervisor
  branch: 672 Python tests with 29 Postgres skips, full Python 3.9.6 suite and
  JavaScript checks. [supervisor-verificar.log](supervisor-verificar.log) is
  **not** an execution of PR #22's application code. Lint/type/coverage optional
  `--todo` checks were not rerun for this documentation-only publication.

To reproduce, use an isolated checkout/archive of the exact reviewed head and
run this report's script with its directory on `PYTHONPATH`:

```sh
PYTHONPATH=/path/to/pr22 python /path/to/this/report/reproduce.py sqlite
# Set ARA_MAP_TEST_DATABASE_URL to an explicitly disposable UTF-8 database only.
PYTHONPATH=/path/to/pr22 python /path/to/this/report/reproduce.py postgres
```

The script imports the PR's test fixtures and creates/cleans their test data.
Do not point it at a real application database.

## Next owners

Team A: follow [TEAM_A.md](TEAM_A.md), add only these bounded corrections to
the existing PR #22 and return an exact-head handback. Keep #20 unchanged.

Team B: its assignments and separate correction packet at supervisor commit
`009a724e4534e419e5703bd411425fd06776db62`,
`reports/team-b-round-1-review-2026-10-08/`, are unchanged. Do not wait for A's
record branch or move B's work onto it. This review does not assert that the
owner has delivered B's correction prompt or that B has begun it.

Supervisor: review the next correction deltas and the combined baseline before
closing the relevant acceptance gates. No 2A/2B, main merge or deployment is
released by this review.
