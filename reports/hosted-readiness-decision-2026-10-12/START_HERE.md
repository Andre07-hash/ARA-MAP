# Hosted readiness — concrete route decision

12 October 2026. Owner priority: ASAP, private portal first, KMZ mandatory.

**Owner decisions now confirmed:** keep **Vercel with full-size transfers**, retain **20 MiB KMZ / 25 MiB PDF**, start with a **fresh empty isolated portal**, and use **operator-managed accounts/password resets**. This supersedes the pending route/scope discussion below. It authorizes design, not resource creation or deployment. The released next design scopes are [TEAM_A.md](TEAM_A.md) and [TEAM_B.md](TEAM_B.md); they replace the earlier generic readiness briefs and do not reopen accepted work.

## Review decision

**A's read-only readiness handback is sufficient to identify the deployment boundary.** It is not a hosted acceptance run or an implementation deliverable. A inspected exact candidate `4670df7348265af66c640069e5ece2a274830fa3`; no changes or tests were claimed. [Original handback](TEAM_A_HANDBACK.txt).

Supervisor independently checked the candidate source and current GitHub metadata: A #29 is still at `4670df7`, B #30 at `bc7e421`; both exact-head CI runs are successful. A's R3-A2 residual and B's batching acceptance remain as documented in their separate review packets.

Confirmed:

- The cloud entry point does not inject an attachment store. `_almacen_actual()` returns 503 `almacen_no_configurado` when no factory exists. Metadata/listing and database geometry paths are separate; do not claim the entire file feature is absent.
- Every routed request body passes through `api/index.py::_read_body()`, which rejects bodies above **4 MiB**. KMZ byte upload is one buffered PUT; there is no existing multipart/chunk protocol to bypass this check.
- Downloads currently return the complete buffered file after server-side verification. The existing browser subsequently verifies the downloaded bytes.
- Accepted attachment limits remain **20 MiB KMZ / 25 MiB PDF**. The browser exposes those limits, independently of the `/api/config` 4 MiB import limit. Store injection alone does not fix large-file transfers.
- Geometry is delivered as bounded 512 KiB slices; the existing parser, candidate selection, lifecycle, geometry client and boundary renderer can be reused.
- The local server binds loopback. A hosted service needs an explicit entry point and trusted TLS/proxy configuration; changing a bind address alone is insufficient.

Vercel's current primary documentation confirms a **4.5 MB request/response payload cap** for Functions. Larger bundles or a longer function duration do not change that cap. This verifies the previously unverified platform claim; it is not a test of our actual deployment. Sources checked 12 October: [Functions limits](https://vercel.com/docs/functions/limitations#request-body-size), [large-file upload guidance](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions).

## Corrections to planning assumptions

1. `configurar_archivos()` does support an explicit `ARA_MAP_ARCHIVOS` directory with Postgres; it avoids a directory **by default** when Postgres is enabled. A persistent-host route can reuse that explicit-directory contract without inventing an object-store backend.
2. Missing factory produces 503. A factory that raises unexpectedly is not automatically translated to that response: `_almacen_actual()` does not catch initialization errors. The implementation must define safe unavailable-store handling and diagnostic logging; do not promise all factory failures already produce 503.
3. Preserve the existing `serve(..., open_browser=False)` option. A new hosted entry point must use production host/origin and Secure-cookie behavior without opening a browser or depending on the owner's Mac.
4. For Vercel full-size files, direct browser-to-store transfers are one option; bounded transfers through authorized handlers or a separate file service are other design possibilities. All need explicit interface/security review. Do not declare one protocol obligatory or accept the “days to weeks” estimate as a measured schedule.
5. Rough “2x file size” memory is not a measured upper bound for KMZ parsing or concurrent work. Verify the chosen runtime with the accepted sizes and a small concurrent pilot workload; no renderer/memory research round is required.
6. `scripts/cuentas.py` rejects Postgres targets older than the current schema, rather than requiring exact equality. For the new pilot, target the reviewed schema deliberately. Production's schema has not been inspected; an upgrade of it is outside the current route plan.

## Route decision presented to owner

| Option | Behavior and remaining work | Planning disposition |
|---|---|---|
| **H: one hosted Python service behind HTTPS, private persistent volume, isolated Postgres** | Keeps full accepted file sizes and authenticated-handler transfers. Reuses `AlmacenLocal`; adds hosted entry/configuration, mounted-volume validation, service/proxy runbook and consistent database-plus-file backup/restore. | **Recommended for minimum application changes**, conditional on an acceptable provider/cost and a named operator. This is a source-based judgment, not a validated hosting/time/cost guarantee. |
| V: existing Vercel Functions, explicit 4 MiB attachment cap, private object store | Requires new durable store backend, hosted wiring and consistent server/client file-size policy. Smaller-file pilot changes the accepted contract and needs owner approval. | Do not silently reduce KMZ/PDF limits. |
| V: existing Vercel Functions, full-size attachments | Requires a reviewed large-transfer protocol and durable store integration. Keep parsing/activation/authorization semantics. | Use if retaining Vercel is a stronger constraint than minimizing application changes. |

The owner selected the third option: Vercel with full-size attachments. H and the smaller-file option are preserved here as the alternatives presented, not active assignments. The private object-store implementation/provider choice, access/costs, exact deployment and database/file namespaces remain pending. The route preference sets architecture only; it does not authorize purchases, provisioning, deployments or real accounts/data.

The owner confirmed an empty isolated database and operator-managed accounts/password resets. No production data carryover or new self-service password feature is needed for this pilot. A's effort estimates are rough A-only estimates, excluding B, operations and independent hosted acceptance; the full-size Vercel protocol still needs a concrete design estimate. Do not promise a handover date from the H/small-file estimates.

## Bounded next scopes after the decision

**Shared code reference:** A `4670df7`; accepted B #30 `bc7e421` remains separate. No new combined candidate is invented. Accepted #28 is already an ancestor of A. Exact branch/pin/integration instructions follow the chosen route; no duplicate merge is requested.

For H:

- **A** owns the separate hosted entry point, explicit Postgres/store configuration, host/origin/TLS-proxy assumptions, cloud-adapter attachment regressions, startup/schema validation, account/bootstrap runbook and short Spanish onboarding guide. Keep local startup and the existing Vercel entry point intact; no auth-policy redesign. Deployment configuration stays in a dedicated draft PR.
- **B** owns validation of `AlmacenLocal` on the intended mounted filesystem, file-lifecycle failure cases, consistent private-volume/database backup and restore, missing-object/hash/active-geometry verification, and the KMZ-specific hosted acceptance fixture. Do not rewrite the parser/renderer or build an object-store backend unless the chosen host requires it. No automatic orphan cleanup in this MVP without a separate reviewed need.
- Agree the explicit directory/factory/injection contract and operational backup boundary in one short shared contract. No parallel shared-file edits; A integrates the wiring.

For the chosen full-size V route, revise only the transfer/store contract and the affected ownership. Do not release a generic object-store SDK implementation before verifying its no-overwrite, staging, private reads and recovery semantics. No reduction in file limits is approved.

**Design candidate, not an approved resource:** private Vercel Blob plus small authorization/finalization requests and direct, tightly scoped staging uploads. Current primary docs describe private storage with Python SDK support and private client uploads: [private storage](https://vercel.com/docs/vercel-blob/private-storage), [client uploads](https://vercel.com/docs/vercel-blob/client-upload), [SDK reference](https://vercel.com/docs/vercel-blob/using-blob-sdk). A and B must establish Python/browser SDK compatibility, no-overwrite copy and grant expiry/revocation behavior before adopting this protocol. SDK examples are not an authorization policy. If the candidate cannot preserve the required semantics, propose the smallest bounded authorized-handler transfer alternative, not a hosting change.

This is a proposed amendment to the older bytes-through-handlers contract, rather than a claim that direct transfers are already accepted. B owns the technical transfer/store proposal; A validates and specifies authoritative grant/completion authorization and adapter wiring. The supervisor consolidates one reviewed contract before application implementation.

**Release proof remains mandatory:** actual hosted KMZ upload → selection/activation → correct boundary with null X/Y; failed replacement preserves the old boundary; second-device authorized read and denied cross-account access; persistence after redeployment; database-plus-file restoration. Record candidate SHA, deployment identity and isolated targets. Reuse unchanged local/CI evidence. Minor server-protected stale UI is not an automatic pilot blocker.

## Publication and team handoff

A correctly identified that earlier packets were only local. The supervisor is publishing the private-MVP plan, independent A/B acceptance evidence, KMZ priority packet and this decision report on `codex/supervisor-completion-brief`; no main/team branch is changed. After publication, the final response gives the exact instruction commit for the owner to relay.

A should reconcile only this packet's corrections and the latest acceptance updates, then return the Vercel control-plane design in TEAM_A.md. It does not need to repeat its readiness audit or broad checks. B's existing KMZ handback scope is now narrowed to the Vercel full-size transfer/private-store proposal in TEAM_B.md; do not return a second generic provider survey or plan for H. The owner relays these instructions; the supervisor does not message the external team accounts.

The required supervisor-branch pre-push `./verificar.sh` run passed: 672 Python tests (29 Postgres skips), full system Python 3.9.6 suite, and JavaScript. This is separate from feature/hosted acceptance. [Publication check log](evidence/supervisor-prepush.log). No production schema, account, credentials or data were queried or changed. No application code was authored.
