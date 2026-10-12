# M1 — private hosted file transfer implementation contract

Supervisor review, 12 October 2026. This reconciles A's consolidated VD1-A and B's final VD1-B delta. It supersedes the design-only status of the earlier VD1 packets **when the owner relays the implementation instructions**. The supervisor has authored no application code.

**Decision:** the designs are sufficient for bounded implementation with the requirements below. No further provider survey or general readiness/design handback is requested. S3 plus cloud-only boto3 is the working implementation choice; provider resources, access, cost and actual deployment remain separate owner/operator decisions.

The teams are independent Claude sessions on different computers/accounts. The owner relays instructions and handbacks. Neither session can assume access to the other's conversation, scratch files, environment, credentials or unpushed commits. This report and the two original handbacks are the shared written contract. Use [TEAM_A.md](TEAM_A.md) and [TEAM_B.md](TEAM_B.md) with this file.

## References and scope

- Shared starting application: `4670df7348265af66c640069e5ece2a274830fa3`.
- Accepted batching, still separate: `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3` (#30).
- Accepted #28 is already consumed in A. Do not merge it again.
- Preserve existing #29, #28, #30 and C1 `49b782d147591236cc7f311c7e0de1948ad5258e`. Work on new branches, not their heads.
- Owner scope: ASAP private portal; Vercel; 20 MiB KMZ / 25 MiB PDF; fresh isolated portal; managed accounts/password resets. No public catalogue or production-data migration.
- Local implementation, isolated development dependencies, synthetic tests, new branch publication and separate draft PRs are the next relay's scope. No GitHub PR/main merge, cloud provisioning, provider/account/secret changes, deployment or real data. Ordinary local integration merges into A's **new** candidate branch are allowed as described in TEAM_A.md.

At this review GitHub confirmed #29 at `4670df7` and #30 at `bc7e421`, both draft. Neither pasted design reports implementation or verification. Existing CI/local evidence is reused only for unchanged code; it does not prove the new transfer/backend or hosted candidate.

## Frozen shared interfaces

| Item | Agreed contract |
| --- | --- |
| Store module | `server/almacen_s3.py`, B-owned |
| Factory | `fabrica_desde_entorno(environ) -> FabricaAlmacen | None`; configuration/adapter construction must not perform STS or S3 I/O |
| OIDC handoff | `fijar_token_oidc(valor)` returns a ContextVar reset token; `restablecer_token_oidc(marca)` resets it; stdlib-only module import |
| New store method | `componer(origenes, destino, limite) -> int` (bytes composed); implement on local, in-memory and S3 stores |
| Existing reads | `leer` unchanged; no ranged-read addition, lectura token or verification registry |
| Cloud variables | `ARA_MAP_ARCHIVOS_S3_BUCKET`, `ARA_MAP_ARCHIVOS_S3_REGION`, `ARA_MAP_ARCHIVOS_S3_ROLE_ARN` |
| Test endpoint | Optional `ARA_MAP_ARCHIVOS_S3_ENDPOINT` for isolated local tests only; never allow a cloud endpoint override |
| Extra selectors | No `ARA_MAP_ALMACEN`, `ARA_MAP_S3_*` aliases or extra namespace prefix in this pilot |
| Chunk size | 3,145,728 bytes (3 MiB); indexes 0..P-1; P = ceil(declared size / chunk size), at most 9 |
| Staging keys | `<clave_temporal>-NN`, zero-padded two-digit index, generated only by the server |
| Content route | Existing PUT with `?parte=N`; exact declared body/chunk length, strict ASCII integer validation |
| Download route | Existing GET with `?desde=O`; unsigned ASCII integer, O a 3 MiB boundary and 0 <= O < verified file size |
| Download headers | `X-Archivo-Version-Id`, `X-Archivo-Sha256`, `X-Archivo-Bytes`, `X-Archivo-Desde`, `X-Archivo-Longitud`, `X-Archivo-Siguiente`; next offset as decimal, final value `fin` |
| Start DTO addition | `transferencia: {parte_bytes: 3145728, partes: P}`; preserve idempotent replay semantics |
| Common error details | `reintentar` (boolean), `limpieza_pendiente` (boolean), and `partes_faltantes` (bounded list), when applicable; no alternate retry-field spelling |

These names override inconsistencies in the original handbacks. The originals are retained as evidence, not competing contracts: [A](TEAM_A_HANDBACK.txt), [B](TEAM_B_HANDBACK.txt).

## Required behavior

1. Keep application routing/session/capability/origin/read-only policy and resource privacy. **Resolve current resource scope and pending ownership before resolving a failing store or making provider calls.** The reference API currently evaluates `_almacen_actual()` before the service's resource check in several routes; do not claim this precedence is already guaranteed. Cover authorized and out-of-scope requests with an unavailable store. Keep the 4 MiB application request cap.
2. Start validates fields, including new `400 archivo_vacio` for zero bytes, then existing authorization/reverification/idempotency behavior. New starts check pure storage configuration before inserting a pending row. A replay may return its original result. No STS/S3 call or credential refresh under a database write lock, including inside a factory or store check. Missing/invalid file configuration must not make the cloud entry fail to import or disable unrelated portal/metadata/database-geometry routes; defer the safe file error until the authorized operation needs the store.
3. Each part is an atomic whole-object replacement; exact lengths and counts come from the stored declared size. Validate state, actor, scope and upload deadline before and after writing. Refuse a live completion lease with `409 procesamiento_en_curso`. The ordinary `guardar_temporal`/`copiar` interfaces remain supported. Late staging writes cannot change a composed final object.
4. Compose pinned/snapshotted parts into a fresh create-only final nonce. Verify actual final size, SHA-256 and signature, run the existing bounded KMZ parser, then reauthorize and atomically commit under the current lease. Store/parser I/O stays outside database write transactions. Keep the 15/60-minute deadlines, 180-second lease and five-pending policy.
5. Track a final write attempt before I/O. An uncertain write returns retryable `503 almacen_no_disponible` and `limpieza_pendiente: true`; retain uncertain objects or delete only this attempt's nonce after a reliable database check proves it unreferenced. A failed database check means keep it. A 412 collision winner is never deleted; release the lease and return a retryable storage error with cleanup pending. Never reuse that nonce on an application retry. Versioning is recovery support, not deletion justification. No orphan sweep.
6. Missing parts return `409 contenido_temporal_ausente` with bounded `partes_faltantes` and `reintentar` true only while restaging is still allowed. After the upload deadline, cancel then start a new version with a fresh idempotency key. Completion's longer deadline does not extend upload. Cancellation frees the pending slot. Account for all derived part keys in cleanup/replay reporting.
7. Every download request reauthorizes, reads and verifies the entire final object against its database size/SHA-256, then returns at most 3 MiB **from that same verified buffer**. No separate unverified range read. Use octet-stream, private/no-store, CSP sandbox and nosniff. The browser verifies identity, totals, offsets and exact lengths across slices, then whole-file SHA-256 before creating the usable download. Abort/scope loss discards the buffer.
8. Disclose storage reads: 25 MiB PDF = 9 reads / 225 MiB; 20 MiB KMZ = 7 reads / 140 MiB. These are protocol counts, not hosted timings or a guaranteed heap bound. Measure actual time/memory/cost in the later hosted proof.

## Configuration, credentials and errors

A sets the documented `x-vercel-oidc-token` in the B-owned ContextVar and resets it in `finally`, including errors and early routing returns. Local startup does not obtain cloud credentials. B owns STS exchange and the SDK refreshable credential/client implementation. Credential exchange/refresh begins only after application resource authorization and outside DB locks.

Use the current request's token when refresh is needed. Scope the role/cache to the configured project/environment identity, not an end-user identity. Serialize initialization/refresh appropriately; demonstrate concurrency, expiry, missing token, provider errors and warm-instance reuse. Do not assume every simultaneous request necessarily results in exactly one refresh without testing the selected SDK behavior.

Trust policy uses exact team issuer, project/environment subject and audience; separate Preview and Production roles/buckets/configuration. Target supported cloud Python 3.12 while preserving the local Python 3.9 floor and dependency-free local launch. A owns cloud runtime/package configuration and dependency declaration/lock; B supplies and tests compatible SDK versions. Proposed range: `boto3>=1.38.38,<1.44; python_version >= '3.10'`, with exact compatible cloud pins recorded for verification. Do not add a redundant independent botocore range that conflicts with boto3's dependency. Both module import and ordinary local startup must work without the SDK installed.

| Condition | Client behavior |
| --- | --- |
| Missing/invalid storage configuration, absent required cloud OIDC token | 503 `almacen_no_configurado`; no pending insert for a new start |
| STS/S3 timeout, throttling, connection failure, 5xx, expired OIDC token | 503 `almacen_no_disponible`, `reintentar: true` |
| Expired AWS credentials | One forced refresh and one retry only of a safe operation; otherwise retryable storage error; uncertain writes follow the nonce rule |
| Provider access denied | 503 `almacen_no_disponible`, `reintentar: false`; never application 401/403/404 |
| Other factory failure | 503 `almacen_no_disponible`, no poisoned cached factory result; classify retryability rather than pretending it is invalid configuration |
| Missing staging/final object | Existing `contenido_temporal_ausente` / `contenido_no_disponible`, respectively |
| Corrupted finalized bytes | 503 `objeto_final_inconsistente`, no returned bytes |

Log condition class/type and safe diagnostics, not exception messages or raw credentials/tokens/provider paths/URLs. Existing application denials retain precedence over these provider failures.

## Recovery and hosted acceptance

Keep S3 versioning, private access, TLS and encryption. Retain all final versions for the pilot. Staging lifecycle must cover current objects, noncurrent versions and delete markers. Restore exact referenced bytes into a fresh bucket by recorded size/SHA-256 and re-hash them; provider checksum encoding must be normalized before comparing with the database digest. Missing or inconsistent referenced bytes block restore acceptance. Check history/attempt/geometry/active-descriptor links; report unreferenced objects without deleting.

**Neon PITR is not the application's filtered logical backup.** Its restored state can contain `team_session`, `team_login_failure` and `archivo_trabajo`. Before exposing the isolated restored target, the operator runbook explicitly clears these three tables in that target. This is a future, controlled restore step, not a mutation performed by B's read-only verifier. Keep pending versions/deadlines, omit staging, report them and allow authorized cancellation/fresh start. A owns the operational runbook; B owns `scripts/verificar_archivos.py` and recovery byte checks.

Local acceptance: meaningful store conformance/failure cases, real cloud-handler synthetic integration, SQLite and disposable Postgres, affected client/widget journeys and normal repository checks/CI. Reuse unchanged renderer/parser/research evidence; no broad performance research loop.

Actual hosted Preview proof remains a separate release gate: full-size KMZ and PDF transfer/download; explicit candidate selection/activation and boundary with null X/Y; invalid replacement preserves prior boundary; authorized second session and denied cross-account access; permission loss between slices; outages/missing parts; redeploy persistence; isolated restore; runtime/OIDC header delivery and spoofed-header behavior; actual duration, memory and transfer-read cost. Record exact candidate/deployment/isolated target identities. No hosted acceptance is claimed here.

## Source checks and scheduling

Supervisor checked source at the A pin and provider primary sources. B's `1.38.38` unsigned STS claim is supported by the [botocore changelog](https://github.com/boto/botocore/blob/develop/CHANGELOG.rst); [boto3 1.43.112 metadata](https://pypi.org/project/boto3/1.43.112/) requires Python >=3.10. [Vercel Python documentation](https://vercel.com/docs/functions/runtimes/python) lists 3.12 as default; this does not inspect the actual project's settings. [Neon restore documentation source](https://github.com/neondatabase/website/blob/main/content/docs/postgres/backup-restore/branch-restore.md) describes timeline restoration; application backup exclusions do not govern it.

B's estimate is about five working days; A's consolidated estimate is roughly 2.5 days of implementation/review/docs plus 0.5–1 day for later operator-assisted Preview proof. They are unmeasured estimates and partly overlap. B cannot reliably estimate A's work. Provider setup and hosted acceptance are additional dependencies, so no client handover date is promised.

Publication verification: required supervisor-branch `./verificar.sh` passed (672 Python tests, 29 Postgres skips; complete system Python 3.9.6 suite; JavaScript). [Log](evidence/supervisor-prepush.log). These are documentation-branch checks, not acceptance of the unimplemented S3/transfer candidate. No application, live cloud, account or real-data changes were made.
