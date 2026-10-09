# Packet 1B — corrections L1–L6 after supervisory review

Date: 2026-10-09  
Branch: `claude/team-b/attachment-lifecycle` (same draft PR #23, same base
`claude/integration/round-1-baseline` at checkpoint
`1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`)  
Status: corrections complete; stopped for supervisory review

This is the correction handback requested by
`reports/team-b-round-1-review-2026-10-08/` at supervisor commit
`009a724e4534e419e5703bd411425fd06776db62`. It amends `START_HERE.md` in this
folder; where the two differ, this file wins. `START_HERE.md` is otherwise
kept as the historical first handback.

## 1. Exact inputs and heads

| Input | Commit |
|---|---|
| Supervisor review (findings, probes) | `009a724e4534e419e5703bd411425fd06776db62` |
| Reviewed 1B head (PR #23 before correction) | `6f303e1d0672c0b0c0e9170a601f8ef388b0f3b7` |
| Baseline checkpoint / PR base | `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb` |
| Code + tests correction commit (all evidence below) | `d70eb0e07e5c61218df75e90a094581b5704fefc` |
| Final branch head | the commit adding this file; authoritative `headRefOid` of PR #23 |

Before work, the remote heads of PR #23, its base and the supervisor branch
were fetched and matched the reviewed commits exactly; no later work existed
to preserve. No force push, rebase or restart. Team A's branches were not
consumed. The research branch (PR #21) is handled separately.

## 2. Changed files

| File | Change |
|---|---|
| `server/archivos.py` | Scope-normalized lookups (L1), post-boundary clock reads and controlled lease conflicts (L3), paged `listar` and `historial(reloj=)` (L2/L4), truthful cleanup reporting (L6). |
| `server/repo/archivos.py` | `version_of_attachment`, `live_lease_expiry`, `check_activation`, `retirement_staging_keys`; one caller-aware `pending_view` for every read; single-query paged listing; active-only PDF summaries; redacted history projection. Removed unused `versions_for_attachment` (it projected every pending version as the caller's own). |
| `tests/test_archivos.py` | 18 new behavior tests in the shared SQLite/Postgres matrix; three existing tests updated only for the paged `listar` shape. |
| `reports/.../CORRECTIONS_2026-10-09.md`, `corrections-2026-10-09/` | This handback, probe outputs and logs. |
| `reports/.../START_HERE.md` | One pointer line at the top to this file. |

No schema, migration, P2/auth, database adapter, storage, parser, HTTP, UI,
CI, deployment or renderer file changed. The diff against the reviewed head
touches only 1B-owned files.

## 3. Finding dispositions

| Finding | Disposition | Regression tests (both databases) |
|---|---|---|
| **L1** P1 scope/absence oracle | **Fixed.** Every file/version-addressed operation resolves the resource and authorizes its real terrain through P2's public `require_terreno` before any lease or write. A missing ID is authorized against a terrain ID that never exists, so it fails at the same point as an out-of-scope one: after P2's 401/403 checks, with the same 404. P2 404s on these operations are translated to the single `{"code": "not_found"}` / `El archivo no existe.` result, inside write transactions too. Activation resolves `version_id` against the authorized attachment (missing, other terrain, or another attachment on the same terrain → identical 404) and validates state/geometry **before** reading or taking a lease. No raw `IntegrityError`/`ForeignKeyViolation` remains. P2 is unchanged. | `test_l1_missing_and_out_of_scope_resources_are_one_result`, `test_l1_activation_resolves_version_ownership_before_any_lease` |
| **L2** P2 pending privacy | **Fixed.** One rule, `repo.pending_view`, serves list, summaries and history: privacy follows the durable row (`subiendo` belongs to its initiator whether or not overdue); the projected state is `expirado` only with no live lease. Another caller (operator or admin) sees `{"estado": <projected>, "propia": false}` everywhere. History returns another account's still-pending event redacted (no actor, version ID, name or size; position kept for the cursor); the durable audit row is not rewritten. | `test_l2_pending_privacy_is_one_rule_on_every_read_surface` (before/at/after deadline, live lease, revoke, transfer, regrant) |
| **L3** P2 stale clock / raw conflicts | **Fixed.** Each write transaction reads the clock after entering `db.escritura()`, revalidating scope and locking, immediately before its guarded decision (start, lease acquisition, failure/available finalization, cancel, reprocess, activate, retire). Equality is still expired; a pre-deadline lease may still finish after the deadline. At the completion deadline with a live lease the caller gets `procesamiento_en_curso` with `reintentar_despues_de`, not `subida_expirada`. An expired reprocessing lease returns `409 lease_perdido` before any attempt, geometry, event or idempotency write; the same key can then be retried. No lock removed, no automatic retry added. | `test_l3_completion_reads_the_clock_after_acquiring_its_boundary`, `test_l3_start_and_failure_boundaries_use_post_acquire_time`, `test_l3_deadline_with_live_lease_is_in_progress_not_expired`, `test_l3_expired_reprocessing_lease_is_controlled_and_writes_nothing`, `test_l3_takeover_while_late_holder_waits_then_commits_first`, `test_l3_reprocessing_takeover_fences_the_late_holder`, existing `test_live_lease_takeover_fences_late_holder_and_keeps_one_final` |
| **L4** P2 unbounded listing | **Fixed.** `listar` returns one page: default 50, maximum 100, cursor `creado_en|id` descending (ties broken by ID). One SQL statement selects `limite + 1` rows and hydrates each attachment's latest version and lease liveness; no per-item queries. Retired attachments stay listed. History was already bounded and keeps its contract. | `test_l4_listing_is_bounded_paged_and_stable_with_equal_timestamps` (106 rows at one timestamp, 50/50/6, no duplicates, limit/cursor validation, scope, one-statement assertion) |
| **L5** P2 retired PDFs in summaries | **Fixed.** Recent PDFs use the same eligibility as `pdf_total` (`retirado_en IS NULL`). Retired files remain in paged `listar` and `historial`. | `test_l5_retired_pdfs_do_not_crowd_active_summaries`, `test_l5_summary_replaces_lower_revision_pdf_beside_higher_revision` |
| **L6** P2 hidden cleanup failure | **Fixed.** `limpieza_pendiente: true` means an unreferenced object may remain. Verification-failure completion now removes its own nonce (only when a fresh DB read proves it unreferenced) **and** its staging, and reports either failure. Cancellation and retirement report `true` when deletion failed or no store was given. Retirement stores `true` before external cleanup when it had staging to remove; replays re-check the staging read-only. Completion replays re-check read-only: their staging and any final nonce under the version's prefix other than the referenced one. Replays never delete (another holder may own a nonce). Handled `ApiError`s raised after a copy (`lease_perdido`, `503`) carry `limpieza_pendiente: true` in `detalle` when cleanup failed. An unprovable reference still keeps the bytes. No keys are exposed; no sweeper, no schema change. | `test_l6_verification_failure_reports_failed_cleanup_and_replay_rechecks`, `test_l6_unprovable_reference_keeps_bytes_and_reports_pending`, `test_l6_successful_completion_staging_failure_survives_replay`, `test_l6_lost_lease_error_carries_cleanup_status`, `test_l6_cancellation_never_claims_an_unattempted_or_failed_cleanup`, `test_l6_retirement_replay_reports_actual_staging_state`, existing `test_uncertain_commit_never_deletes_a_referenced_final` |

Additional oracle found while testing L1: at the reviewed head a revoked or
expired session received `404` for a missing ID but `401` for an existing one,
because the resource was looked up before the session was checked. The L1
change closes it; `test_l1_missing...` asserts `401` for missing, out-of-scope
and in-scope IDs alike.

Unchanged behavior rechecked: authorization/replay, both scope-race orders
(the nine after-slow-work scope changes test; boundary-wins-first remains the
inherited P2 guarantee and is not claimed as new 1B evidence), cancellation
and retirement, immutable outcomes, and uncertain-commit retention all pass
unchanged in the same matrix.

## 4. Updated public service interface

Only these signatures changed (all other signatures in `START_HERE.md` §3
stand):

```python
listar(
    sesion, terreno_id, *, cursor=None, limite=50, bd=None, reloj=None,
) -> dict   # {"archivos": [...], "cursor_siguiente": str | None}

historial(
    sesion, archivo_id, *, cursor=None, limite=50, bd=None, reloj=None,
) -> dict   # {"eventos": [...], "cursor_siguiente": str | None}
```

- `limite` must be an `int` in 1–100 (`limite_invalido` otherwise); a malformed
  cursor is `cursor_invalido`. Cursors are opaque to callers.
- `listar` items keep the attachment DTO plus `ultima_version`. An own pending
  version now also carries `"propia": true`.
- Every history event carries `"privado": false`, or is the redacted form:

```json
{"id": "33333333-3333-4333-8333-333333333333", "accion": "subida_iniciada",
 "revision": null, "archivo_version_id": null, "intento_id": null,
 "geometria_id": null, "base_id": null, "actor": null,
 "at": "2026-10-08T12:00:00+00:00", "details": {}, "privado": true,
 "version": {"estado": "subiendo", "propia": false}}
```

- Completion results, including replays, always include `limpieza_pendiente`.
  Cancellation and retirement results already did; the value is now truthful.
- Error envelopes are unchanged except that a file/version-addressed 404 is
  always `{"code": "not_found"}` with message `El archivo no existe.`, a
  completion at its deadline with a live lease is `procesamiento_en_curso`,
  an expired reprocessing lease is `lease_perdido`, and post-copy errors may
  add `"limpieza_pendiente": true` to `detalle`.

`resumenes_de_archivos` keeps its signature and DTO; `pdf_recientes` now
contains live PDFs only.

## 5. Verification

All rows below ran on the tree of `d70eb0e` in this cloud container (Linux,
fictional data only). They are developer evidence, not independent review, CI
or hosted evidence.

| Gate | Result | Log |
|---|---|---|
| Supervisor probes on reviewed head `6f303e1`, SQLite + Postgres | all 8 findings reproduced as reported | `probes-reviewed-6f303e1-*.jsonl` |
| Same probes on the corrected tree | all 8 corrected (see note on `unbounded_list`) | `probes-corrected-*.jsonl` |
| Paged variant of `unbounded_list` | `[50, 50, 5]`, total 105, both databases | `probe-paged-listing.jsonl` |
| Negative control: new tests against reviewed code | 32 failures/errors (subtests counted individually) across the new and shape-updated tests | §5 note |
| `tests.test_archivos`, SQLite + disposable UTF-8 Postgres 16.15, Python 3.13 | 78 passed, 0 skipped (39 per database) | `focused-sqlite-postgres-py313.log` |
| `tests.test_archivos`, SQLite, Python 3.9.25 | 39 passed, 39 Postgres-only skips | `focused-sqlite-py39.log` |
| Full Python suite, SQLite, Python 3.13 | 1,065 run, 138 Postgres-only skips, 1 environmental failure | `full-py313-sqlite.log` |
| Full Python suite, SQLite, Python 3.9.25 | 1,065 run, 138 skips, same 1 environmental failure | `full-py39-sqlite.log` |
| Full Python suite with disposable Postgres, Python 3.13 | 1,065 run, 0 skips, same 1 environmental failure | `full-py313-postgres.log` |
| JavaScript | 120 passed | `js.log` |
| `ruff check server/ tests/` | passed | `ruff.log` |
| `mypy server/` | passed, 49 files | `mypy.log` |
| Coverage, full suite with Postgres | 95 % total; service 86 %, repository 94 % | `coverage-summary.log` |

Notes:

- The single full-suite failure is
  `test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`:
  this container's `/usr/bin/python3` (3.13) has openpyxl installed system-wide.
  It fails identically on the untouched baseline and is unrelated to 1B.
  `./verificar.sh` itself could not run because the container has no `zsh`;
  its three components were run directly as listed. The Python 3.9 floor was
  exercised with a uv-managed CPython 3.9.25, not macOS `/usr/bin/python3`.
- The supervisor ran Postgres 17; this container has Postgres 16.15, the same
  major version as GitHub Actions.
- The reviewed `unbounded_list` probe counts `len(listar(...))`; on the new
  dict result that prints 2. The adapted probe in this folder measures pages.
- Negative control: in the reviewed code the new tests fail for the reported
  reasons (different 404 messages, `404 != 401`, raw `ConflictError`,
  `IntegrityError`, `subida_expirada` at a live lease, stale deadlines,
  retired rows in summaries, missing or false `limpieza_pendiente`). Some
  failures are interface-shape errors (`listar` cursor/dict, `historial`
  `reloj`), which the supervisor's probes cover directly. The two
  takeover-order tests and the lower/higher-revision test pass on the reviewed
  code as well: they add explicitly requested coverage, not a regression.
- GitHub Actions results for the final head are recorded on PR #23's checks
  page; local green is not reported as CI.

Reproduce from the repository root:

```bash
python3 -m unittest -v tests.test_archivos
ARA_MAP_TEST_DATABASE_URL=<disposable UTF-8 database> python3 -m unittest -v tests.test_archivos
PYTHONPATH=. python3 <supervisor folder>/reproduce_lifecycle.py sqlite
PYTHONPATH=. python3 reports/team-b-attachment-lifecycle-2026-10-08/corrections-2026-10-09/probe_paged_listing.py sqlite
```

## 6. Remaining limitations

- History orders events by `(at, id)`; events committed in the same second sort
  by random UUID, not causally. The cursor is stable; causal order inside one
  second is not promised (unchanged from the reviewed contract).
- Redacted history still shows that an upload started and when (`accion`,
  `at`); the listing already reveals that a pending upload exists.
- `limpieza_pendiente` reports; it does not reclaim. Reclamation stays the
  future safe sweep defined in `START_HERE.md` §7. A process crash can still
  leave an unreported orphan, as already disclosed.
- `resumenes_de_archivos` does not cap the number of requested terrain IDs; its
  caller (3A) supplies one page. Unchanged and outside these findings.
- Postgres concurrency remains additionally serialized by the workspace
  advisory lock; parity is behavioral, not a throughput claim.

## 7. Stop condition

Stopped for supervisory review on draft PR #23. No merge, deployment,
provisioning, real data or account action, and no 2B/3B work.
