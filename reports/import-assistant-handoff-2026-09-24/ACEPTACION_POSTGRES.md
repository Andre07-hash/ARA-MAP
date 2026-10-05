# Disposable-Postgres acceptance packet

Response to [SUPERVISOR_REVIEW_03.md](SUPERVISOR_REVIEW_03.md). September 24, 2026 (America/Mexico_City).

**Result: the cloud storage path passes all requested checks. One pre-existing cloud defect was found and fixed: merging saved maps could drop distinct layers that had the same number of terrains.** Production Neon was not touched. Nothing was deployed, and no real AI call was made.

## Environment

- **Database:** PostgreSQL 17.11 (Homebrew), in a throwaway cluster created for this run inside the session's scratch folder. It listened on 127.0.0.1 only, had no Unix socket and no registered service, and was deleted afterwards.
- **Access:** local trust authentication for a single test role, so there are no credentials to disclose. The connection was passed only through `ARA_MAP_TEST_DATABASE_URL`, never written to files.
- **Isolation:** `tests/test_postgres*.py` create a uniquely named schema per class and drop it. After every run, zero `test_ara%` schemas remained.
- **Browser runs:** used a separate disposable database, recreated for each run.
- **Source tested:** [FINAL_SOURCE_SNAPSHOT.json](FINAL_SOURCE_SNAPSHOT.json), captured `2026-09-25T04:10:44.682634+00:00`, 142 files. Before starting, the code matched the snapshot the supervisor reviewed (141/141).

## Tests actually executed

| Run | Result |
|---|---|
| `tests.test_postgres` (the 10 existing cases), exactly as instructed | **10/10 pass** (first time they have executed) |
| `tests.test_postgres_aceptacion` (10 new cases, below) | **10/10 pass** |
| Both suites, 5 consecutive runs | 20/20 each time |
| Entire suite with the disposable DB configured | **545 run, 0 skipped, all pass** |
| Entire suite in the default environment (`./verificar.sh --todo`) | 545 run, 20 skipped (the Postgres cases), 525 executed and passed; Python 3.9.6, JS 62/62, ruff, mypy, 93% coverage |
| First and second reviewers' scripts, unmodified | 8/8 and 4/4 |
| Browser suite, **app using Postgres as its storage** | **44/44** without AI, **44/44** with the simulated provider (its usage row was written to Postgres) |
| Browser suite, app on SQLite (re-run after the fix) | 44/44 without AI, 44/44 with the simulated provider |

## Requested checks → evidence

| # | Requested | Evidence (`tests/test_postgres_aceptacion.py` unless noted) |
|---|---|---|
| 1 | The ten existing Postgres cases execute and pass | Table above |
| 2 | Late confirmation and failure cleanup for **append as well as new base**, on separate connections | `ConfirmacionTardia.test_new_base` / `test_append`: the reviewer's three-request ordering, with the old request refused 409/410 and the price left unknown. `test_threaded_confirm_and_correction_on_separate_connections`: 10 real races, never both succeed, always one does. `FallasSinResiduos.test_new_base` / `test_append` × {write, provenance, backup} failures. |
| 3 | Upgrade from an existing workspace preserves bases, terrains, folders and saved maps, reaches v6, and can be re-applied | `MigracionDesdeEspacioExistente` runs the **real `scripts/migrate_cloud.py`** in a subprocess against a v5 workspace seeded like `setup_cloud.py`: folders of both kinds, bases in and out of folders, terrains with extra data, findings, a map in a folder with layers and frozen terrains. `--check` reports "not current" before; the upgrade runs **twice**; all seven pre-existing tables are **identical** before and after; `--check` then reports current (v6); the four new tables exist; a pre-upgrade backup holding the original data was taken before each run. `test_the_upgraded_workspace_is_usable`: an assistant import then succeeds, remembers its format, and leaves folder membership intact. |
| 4 | Cross-connection budget reservations cannot share the remaining budget; unknown-usage settlement | `PresupuestoEntreConexiones`: the **in-process lock is removed**, so only Postgres serializes. 6 simultaneous callers with room for one bounded request, and the first call is held in flight → exactly **1 provider call**, 5 refused. The unknown usage was settled at the full reservation (`ok_uso_desconocido`) and persisted. Known usage replaces the reservation. |
| 5 | Injected failures: no partial import, format or provenance; prompt cleanup; later requests work | `FallasSinResiduos`: after each failure, 0 terrains, 0 remembered formats and 0 import records; the draft is closed; it completed in under 10 s (no lock timeout; actual runs take milliseconds); and **the next import succeeds** with exactly 1 format and 1 record. |

## Defect found and fixed

**Merging saved maps could discard distinct layers in the cloud.** Found by running the browser suite with the app on Postgres: all 9 comparison checks failed, and every other check passed. (The suite's two fixture bases both have 79 terrains.)

- **Cause:** `server/repo/mapas.py::layer_fingerprint` hashed `repr(tuple(row))`. SQLite rows iterate their values, but the Postgres adapter's `Row` is a mapping and iterates its **column names**. Each row contributed the same column-name tuple, so a layer's fingerprint depended **only on its number of terrains**. Distinct layers with equal terrain counts got the same fingerprint, and the merge dropped all but the first as duplicates. Layers with different counts were kept. *(Corrected per [DEPLOYMENT_REVIEW.md](DEPLOYMENT_REVIEW.md); an earlier version of this packet overstated it as "every layer".)*
- **Scope:** this code predates the import assistant and folders, so the web version deployed from earlier source is expected to have it. The production deployment itself was **not inspected**. Saved maps merged there (*Nueva comparación → Mapas guardados*) from layers with equal terrain counts may be missing layers. Comparisons built directly from bases are unaffected, as is the local SQLite app. Existing merged maps in Neon are not repaired automatically; they would need to be merged again after deployment.
- **Fix:** hash the named columns' values explicitly. For SQLite the digest is byte-for-byte what it was before, and a test proves this.
- **Tests:** `tests/test_snapshots.py` (Postgres-style rows hash their values; SQLite digest unchanged) and `ComparacionesEnLaNube` on real Postgres (two different maps keep both layers; a genuinely identical snapshot is still recognized as a duplicate). The Postgres test **fails against the original function** and passes with the fix. The browser suite then passed 44/44 on Postgres.

## Other change

`scripts/migrate_cloud.py --url-env NAME` upgrades the database named by that environment variable **without ever reading `.env.local`**. A missing variable exits with an error instead of falling back to production, and a test confirms the refusal. The default command is unchanged.

## Cleanup confirmation

- The disposable cluster was stopped and its data directory deleted after the final run.
- No test schemas remained.
- The local test server on port 8471 is stopped.
- The PostgreSQL 17 Homebrew package stays installed for future runs (`brew uninstall postgresql@17` removes it).

## Remaining before production

1. Deployment review of this release, with the merge fix called out.
2. Optionally, repeat this acceptance run on an isolated Neon branch to cover Neon-specific behavior (pooler, TLS, latency), using `--url-env`.
3. Back up production, then `scripts/migrate_cloud.py`, deploy, and smoke-test with removable fictional data. Merged comparisons already in production should be merged again.
4. AI stays disabled until a model, prices, key and spending limit are configured and a real-provider evaluation is done.
5. Presentation follow-ups before the demonstration: the stray `false` in the navigation and the header overflow on phones.
