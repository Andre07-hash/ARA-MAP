# Third supervisor review — R2a and R2b acceptance

Reviewed the correction described in `DEVELOPER_RESPONSE.md` §0b against `FINAL_SOURCE_SNAPSHOT.json`, captured at `2026-09-25T03:48:49.881777+00:00`.

**Decision: accept R2a and R2b at the code-review/local-verification stage. Proceed to disposable Postgres acceptance testing before deployment.** No new blocking finding was identified in these corrections. This does not constitute production or real-AI acceptance.

## Findings closed

**R2a — stale confirmation after a corrected import:** `_vigente` now rejects an unsuccessful draft claim with 410. The claim itself checks expiry and exact revision in both storage paths. A missing draft cannot fall through into business-data writes. Legacy previews retain a separate path without assistant draft metadata. The original three-request regressions pass for both a new database and append; the corrected price remains unknown and the stale request writes nothing.

**R2b — cleanup under the cloud workspace lock:** `_confirmacion` surrounds the business-data session, so its final cleanup runs after that session exits. Both successful and failed imports follow this ordering. Cleanup errors are caught and logged by type, preserving the import outcome and leaving an undeleted draft claimed. The original failure-injection/session-depth regressions pass for both handlers. The added controls exercise successful cleanup, missing destinations, backup failure, rollback of records/formats/provenance, and invalid input before token consumption.

The consumed-preview flag and JavaScript helper prevent the dialog from continuing to offer confirmation after the identified terminal failures. I inspected that change and its tests; I did not independently repeat a browser walkthrough in this pass.

## Independent evidence

- **141/141 hashes match** the developer's source snapshot, checked before and after source inspection and regression testing.
- First review script: **8/8 pass, unmodified**.
- Second review script: **4/4 pass, unmodified**.
- Independently reran `env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ./verificar.sh --todo`: **533 Python tests run, 10 skipped, 523 executed and passed**. The macOS Python 3.9.6 compatibility suite, JavaScript suite, ruff and mypy also pass; coverage is **93%**. The ten skipped tests are the real-Postgres suite, so this run does not establish cloud acceptance.
- No application code or existing tests were edited. This review added only this report. No server, production deployment, Neon migration or real AI call was started.

The developer's browser results, 44/44 with AI disabled and 44/44 with the simulated provider, remain developer-reported evidence. Simulated-provider results do not establish real-model accuracy.

## Next developer assignment: validate the cloud storage path

Use a disposable Postgres database or an explicitly isolated test branch. Keep production Neon untouched during this step. Configure its connection through `ARA_MAP_TEST_DATABASE_URL`; do not put credentials in reports, source files or chat.

The existing `tests/test_postgres.py` creates a uniquely named test schema and drops it afterward. With the disposable connection already available in the environment, run from the project root:

```sh
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ARA_MAP_IA_PROVEEDOR= \
  .venv-dev/bin/python -m unittest tests.test_postgres -v
```

This stage must demonstrate:

1. All ten existing Postgres cases execute and pass rather than skip. Record the actual results and any defects uncovered.
2. The late-confirmation ordering and failure-cleanup behavior work for **append as well as new-database imports**. The two new Postgres cases currently exercise new-database confirmation; add corresponding append coverage using separate request connections.
3. The schema upgrade from an existing workspace preserves databases, terrains, folders and saved maps, reaches schema version 6, and can be applied again safely. Validate on disposable data. The migration script reads `.env.local`; do not casually run its default command while intending to test an isolated database.
4. Cross-connection budget reservations cannot spend the same remaining budget. Use a simulated provider, including unknown-usage settlement; no paid call is needed for this check.
5. On injected failures, no partial import, remembered format or provenance entry remains; cleanup finishes without a workspace lock timeout and subsequent requests still work.

These are the outstanding cloud acceptance checks from the earlier reviews, not a request for new product features. If a test reveals a defect, fix that defect and rerun the relevant local and cloud checks. Otherwise return a concise acceptance packet with the tested source hashes, tests actually executed, migration results and cleanup confirmation. Keep connection strings and uploaded contents out of it.

## Subsequent steps

After cloud acceptance, prepare the release and production migration for deployment review. Keep AI disabled until a model, prices, key and spending limit are configured and a real-provider evaluation establishes mapping correctness, ambiguity handling, latency and actual costs on fictional or approved samples. Detection and focused questions remain usable without AI.

The existing navigation `false` and mobile header overflow remain presentation follow-ups before the boss's final demonstration. They do not reopen the corrected R2 findings.
