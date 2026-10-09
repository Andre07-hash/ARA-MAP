# PR #12 review — attachment proposal and dependency decision

Reviewed head: **`ba3ad38599bb5f968164424f2ef6244e9ee24aca`**. The report and eight fictional JSON examples are documentation only. GitHub's Python/disposable-Postgres and JavaScript checks are green, and the supervisor independently parsed all eight JSON examples. CI does not establish correctness of a proposed concurrency or permission design.

## What is ready

The proposal meaningfully separates upload lifecycle, parser outcomes and active layout decisions. It preserves stable terrain IDs, independent attachment concurrency, immutable geometry references and the last usable layout. Copying staging bytes to a fresh final key before verification addresses continued writes through an outstanding staging credential. Shared route registration is correctly placed after B's handlers, so it does not block their isolated development.

The **local/fake storage core** can be separated from the proposed combined B-3a repository/state-machine assignment. Its byte operations need no inventory schema, role/grant helper, provider, upload lifetime or final product size limit. The next packet authorizes only that core and its tests.

The whole proposal is **not approved as an implementation contract**. All cloud-provider claims and product defaults in §7 remain proposed; no provider is selected and no credentials, services or dependencies are authorized. The current packet makes no decision based on the report's search-only provider research.

## Exact Team A dependencies

| Work | Team A input needed? | Dependency |
|---|---|---|
| Local/fake byte storage core and tests | **No** | Explicit temporary roots, opaque object keys and caller-supplied limits; no database or HTTP integration |
| Attachment repository and state machine (rest of proposed B-3a) | **Yes** | A-1 base foundation and a reviewed attachment-prerequisite migration (P1), after shared schema requirements are consolidated. An exact stacked draft commit can support development before merge. |
| Attachment handlers (B-3b) | **Yes** | A-2 scoped capabilities and `require_terreno` (P2), plus the repository prerequisite. Long-operation mutation checks need the agreed transaction contract below. |
| Routes, record DTO, grid/map wiring | **Yes, later** | P3–P6. Route registration follows reviewed handlers; later widget wiring must not hold up schema/auth prerequisites. |

After a fresh fetch, main remains `09452fd26d38319567dce28a89db100ea61c739a`. The only published Team A branch/PR identified for this work is preparation PR #10 at `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6`. No A-1 implementation or attachment-prerequisite branch/PR was found in the fetched remote branches/open PR listing. Team A may have unpublished work; B cannot use or assume it until a branch/PR and exact commit are supplied.

Team A should continue A-1, return its draft PR for review, then receive the small P1 migration and A-2 access-control packets in the agreed sequence. Do not interrupt A-1 by asking A to implement the entire unapproved PR #12 proposal.

## Clarifications required before the database/API contract is frozen

Team B should append its responses and corrected fictional examples to **PR #12** in normal commits. These documentation corrections may proceed alongside the separate storage-core assignment; they do not require A to finish coding.

1. **Authorization at the write boundary (§2.3, §3).** The report checks access on the completion/selection request, then may copy, read and parse for a significant time. During that interval an admin can transfer the terrain, revoke a grant or archive the terrain/base. `archivo.revision` and `retirado_en` alone do not detect those changes. Specify how A/B recheck the current actor, scope and relevant archive rules atomically with finalization/activation, including the synchronization rule when a transfer/revocation races that transaction. Add race scenarios for revocation/transfer after initial authorization but before the final write; define whether unused finalized bytes remain orphaned or history without granting a user a new decision. Do not substitute disabling authorization or incrementing terrain cell versions for this requirement.
2. **Replay after byte finalization but before processing (§1.6, §2.2, §2.5).** A version becomes terminal `disponible` before the parser/activation outcome exists. A concurrent completion can therefore see a terminal row while the first request is still processing or has crashed. The promise “200, same stored body” needs an explicit stored receipt or a deliberately different, documented idempotent state response. Resolve this interval, distinguish byte finalization from activation, define duplicate processing/selection outcomes and request identities, and specify the relevant durable fields for P1. No requirement to add a background worker.
3. **Summary invalidation (§1.7).** `revision_max` over independent attachment revisions cannot identify every change: attachments at revisions `[10, 2]` and `[10, 3]` both have max 10. It also misses some starts/attempts that intentionally do not increment the attachment decision revision. Remove its change-token claim or specify a summary token covering every represented change, including pending/failed results, creation and retirement. Keep terrain cell versions independent. Explain how A's grid refresh uses the chosen token; ordinary field comparison is acceptable if no aggregate token is needed.
4. **Same-version geometry integrity (§1.4, §2.3).** The proposed pointer FKs establish attachment ownership, but the active file version and selected geometry must also refer to the **same finalized version**, not just the same attachment. Spell out the composite references or transaction checks connecting geometry, attempt, version, attachment and terrain. Add a test with two finalized versions of one attachment: activating V1 with V2's geometry must fail. Carry these requirements into A's schema request without prescribing a second migration framework.

Retain D1–D5 and the other proposed defaults as unresolved until supervisory consolidation. The independent storage packet uses caller-supplied limits and no credential or activation policy, so those decisions do not block it. For later geometry transport, ensure byte accounting covers the full serialized response and that chunk reassembly yields the complete B-2 body shape, including metadata; these remain API-contract details, not storage-core work.

## Review outcome and next checkpoint

Accept PR #12 as **preparation with the above refinements**, not as permission for its full B-3a/B-3b implementation. Keep the PR draft and do not merge it. [TEAM_B_STORAGE_PACKET.md](TEAM_B_STORAGE_PACKET.md) is the only newly released implementation scope. The accepted B-1 and B-2 commits remain unchanged, and the extreme multipart display limitation stays an integration/rollout requirement.

No application change, account operation or production action was performed by the supervisor. Earlier instructions and reviews remain historical records.
