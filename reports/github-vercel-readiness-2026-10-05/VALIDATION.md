# Readiness branch validation

## Local checks

- Existing Python suite: `python -m unittest discover -s tests -t .` on the existing development virtualenv, with production/test connection and AI credentials removed from the process environment: **670 tests, OK, 29 skipped**, approximately 40 seconds. The real Postgres suites require a disposable connection and were among the skips. This does not establish fresh-clone or cloud acceptance.
- JavaScript: `node --test tests/js/*.test.mjs`: **98 passed, 0 failed**.
- `git diff --check`: passed.
- No application source behavior changed in this branch. The new GitHub workflow is intended to run real Postgres tests against its own service container, in addition to the local test coverage.

## External checks

- Authenticated GitHub metadata and remote SHA inspection succeeded.
- Authenticated Vercel CLI project/deployment/environment-metadata inspection succeeded. The Vercel app connector was not connected; CLI access supplied the audit instead.
- Production `/api/config`: HTTP 200; production `/api/session`: HTTP 404, consistent with the documented older live authentication implementation.
- Private-repository ruleset and branch-protection APIs: HTTP 403 with an account-plan restriction. Enforcement was not enabled; the repository remains private.

## Not yet established

- GitHub-hosted CI result (record after the readiness PR runs).
- Isolated Vercel Preview database/account configuration and fresh-clone deployment.
- Vercel GitHub repository connection and deployment-to-commit traceability.
- Actual production database schema/account inventory and migration rehearsal.
- End-to-end browser/release readiness. This workflow covers Python/Postgres and JavaScript tests; it does not claim to replace browser and deployment acceptance.

No production deploy, database migration, environment-variable mutation, repository visibility change or paid-plan upgrade was performed.
