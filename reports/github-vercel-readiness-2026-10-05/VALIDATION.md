# Readiness branch validation

## Local checks

- Existing Python suite: `python -m unittest discover -s tests -t .` on the existing development virtualenv, with production/test connection and AI credentials removed from the process environment: **670 tests, OK, 29 skipped**, approximately 40 seconds. The real Postgres suites require a disposable connection and were among the skips. This does not establish fresh-clone or cloud acceptance.
- JavaScript: `node --test tests/js/*.test.mjs`: **98 passed, 0 failed**.
- `git diff --check`: passed.
- No application source behavior changed in this branch. The new GitHub workflow is intended to run real Postgres tests against its own service container, in addition to the local test coverage.

## GitHub-hosted CI

[First repository check run](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37394237727) passed for commit `5d5b1d32e2f44bc46870a7ebf0835a6048eeda92`: both **Python and disposable Postgres** and **JavaScript** succeeded. Python ran 670 tests in approximately 56 seconds on Python 3.12/Linux with the job-local Postgres 16 container; JavaScript passed all 98 tests on Node 24. This verifies the new workflow and test baseline, not a Vercel preview deployment.

## External checks

- Authenticated GitHub metadata and remote SHA inspection succeeded.
- Authenticated Vercel CLI project/deployment/environment-metadata inspection succeeded. The Vercel app connector was not connected; CLI access supplied the audit instead.
- Production `/api/config`: HTTP 200; production `/api/session`: HTTP 404, consistent with the documented older live authentication implementation.
- Production database inspection inside a READ ONLY transaction: schema **7**, no `team_user` table, **3 bases / 104 terrains / 2 maps**. Current source expects schema 8. No rows, schemas or accounts were changed.
- Private-repository ruleset and branch-protection APIs: HTTP 403 with an account-plan restriction. Enforcement was not enabled; the repository remains private.

## Not yet established

- Isolated Vercel Preview database/account configuration and fresh-clone deployment.
- Vercel GitHub repository connection and deployment-to-commit traceability.
- Production schema/account inventory is complete; migration and recovery rehearsal remain outstanding.
- End-to-end browser/release readiness. This workflow covers Python/Postgres and JavaScript tests; it does not claim to replace browser and deployment acceptance.

No production deploy, database migration, environment-variable mutation, repository visibility change or paid-plan upgrade was performed.
