# Team B — M1-B: implement private hosted files and bounded transfers

Read [START_HERE.md](START_HERE.md) at the supervisor instruction commit supplied by the owner. It is the authoritative common contract and overrides differing names in the two original handbacks. The owner relays this packet; A is a different session on a different computer/account. Do not contact it directly or assume access to its conversation, filesystem or credentials.

Your design and correction handbacks are sufficient. **When the owner relays this packet, local implementation, isolated development dependencies, synthetic verification, a new branch and a draft PR are released.** No further design report, provider survey or readiness audit is requested. Cloud operations, real data, accounts/secrets, deployment and GitHub PR/main merge remain held.

Start a new `codex/team-b-hosted-files-v1` branch from exact application pin `4670df7348265af66c640069e5ece2a274830fa3`. Preserve #28 and #30 unchanged; do not write A's branch or integrate old PRs. Create your new draft PR targeting `claude/team-a/application-integration`, with a clear hosted-files title distinct from batching. No force push.

Implement B-owned files only:

- `server/almacen.py`: `componer` for local and in-memory backends, preserving accepted existing interfaces and key/atomicity/bounds contracts.
- `server/almacen_s3.py`: private S3 adapter, lazy SDK import, pure factory construction, ContextVar handoff functions, STS and refreshed SDK credentials. Use the common factory/configuration names. Provider I/O belongs after resource authorization and outside DB write locks.
- `server/archivos.py`, `server/api/archivos.py`: chunks, compose-based completion, uncertain-write tracking, missing-part retry/deadline flow, full-verification sliced download, pure configuration start check, zero-byte validation and the common error mapping. A will review resource/error precedence; explicitly cover unavailable storage on out-of-scope resources.
- `web/lib/archivos.js` and affected `web/components/archivos/*`: sequential chunks, safe user-driven retries/cancel/fresh start, bounded download assembly and verification.
- `scripts/verificar_archivos.py`: read-only inventory/integrity/link verifier, synthetic recovery evidence and provider recovery procedure for A's runbook.
- Your focused tests and report. `server/repo/archivos.py` only if demonstrably needed for existing lease/lifecycle access; no new schema/auth policy by default.

Do not edit `api/index.py`, `pyproject.toml`, the cloud lock/runtime configuration or A-owned onboarding/runbook files. Give A the exact SDK versions, factory/config/context interfaces and packaging prerequisites in your handback. You may install pinned dependencies in an isolated local test environment; do not load real provider credentials or create cloud resources.

Verify backend contract semantics against the local/in-memory stores and an isolated local S3-compatible server where useful. A fake alone cannot prove AWS OIDC or real-provider behavior: label those remaining hosted gates explicitly. Cover final-write success followed by lost response, conditional collisions, failed DB reference checks, snapshotted composition, credential refresh/concurrency, forbidden access before store resolution, deadlines/cancellation, corrupt downloads and restore mismatch cases. Run meaningful affected client/widget journeys and the required repository checks before pushing. Reuse unchanged parser/renderer evidence.

Hand back:

1. New draft PR URL, exact base/code/final SHAs and exact-head CI.
2. Source path and exact supported public interface definitions for A.
3. Compatible SDK pins and cloud packaging prerequisites.
4. Focused evidence, changes, remaining limitations and hosted gates.

Stop for supervisor review. The owner will relay your exact candidate to A for integration; do not merge or message A. Do not claim the MVP is deployed.
