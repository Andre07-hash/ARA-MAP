# Team A — implement P1, the attachment prerequisite migration

## Start now

A-1 is accepted at PR #14 head `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`. Implement this schema prerequisite now; no further planning-only deliverable is needed first.

After fetching, create `claude/team-a/attachment-schema` **from that accepted A-1 commit**, as an explicit exception to the default main-only branch rule for this dependent draft. Keep PR #14 unchanged. Open the new draft against `claude/team-a/schema-9` while that PR is unmerged, so its diff contains only P1. State that it depends on PR #14 and must not merge first. If main has since absorbed A-1, use main and explain the ancestry; if other schema changes exist, reconcile the version number and report them rather than overwriting them. Do not take the parked Excel migration.

Expected schema version: **10**, following the accepted version 9; recheck before assigning it. Scope: `server/db.py`, `server/postgres.py`, dedicated schema migration/constraint tests, necessary schema-version assertions, and `reports/team-a-attachment-schema-2026-10-08/`. No attachment repository, auth implementation, HTTP handlers, frontend, provider integration or application activation in this PR.

Read:

- The owner-approved work-base contract at instruction `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`, `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md`.
- The A-1 acceptance under `reports/team-a-schema-review-2026-10-08/START_HERE.md` in the current instruction history.
- PR #12 at **`28bf0dbbf718571e35d501a7810d7e7d882ee3dd`**, `reports/team-b-attachments-contract-2026-10-07/REPORT.md`, especially §§1.2–1.5, 9.2 and 9.4. §9 overrides earlier text. This packet further narrows and resolves the persistence requirements below; unrelated proposed policies remain proposals.

## Persistence requirements released for implementation

Use the existing migration framework and shared SQLite/Postgres definitions. The six logical tables and the named public-to-B storage fields in the proposal are the starting contract: `archivo`, `archivo_version`, `archivo_intento`, `geometria`, `archivo_evento`, `archivo_trabajo`. Prefer these names. Any necessary adapter-level naming adjustment must be mapped exactly in the handback before B consumes the schema; do not create a second schema or framework.

1. **Attachment decision row (`archivo`).** Stable UUID, canonical `inventory_terrain.id`, protected core column/type pairing, its own positive revision, nullable current-version and active-geometry pointers, retirement and actor/time metadata. PDF belongs to `core:archivos`; KMZ to `core:kmz`. At most one live KMZ attachment per terrain; replacement creates a version of that attachment. Retired attachments remain retained. Multiple PDF attachments are representable. Attachment decisions never bump or rewrite terrain cell versions or events.
2. **Upload/version row (`archivo_version`).** Preserve §1.3's ownership, unique per-attachment positive version number, upload state, starting decision revision, declared/verified metadata, opaque staging/final keys, initiator, deadlines and terminal metadata. Add §9.2's durable completion outcome (`aplicada`, `motivo_no_aplicada`, `finalizado_en/por`). Keep terminal-row outcome nullable only for the states specified in §9.2; failed verification is a durable non-applied outcome. `terminado_*` describes termination, including cancellation/expiry; `finalizado_*` describes completion finalization. Document those distinct meanings so later writers do not use them interchangeably. Do not hard-code proposed byte caps or time durations into DDL.
3. **Processing attempt (`archivo_intento`).** Version relationship, unique positive attempt number per version, optional selection, parser result and bounded-result JSON field, parser identity, geometry reference and actor/time metadata. Include `origen` (`completar`, `reintento`, `seleccion`) and the partial uniqueness rule allowing at most one completion attempt per version. Attempts are inserted terminal by future repository writers; P1 implements storage, not parsing.
4. **Immutable geometry content (`geometria`).** Store the exact normalized geometry, descriptor bbox/interior point and the proposed counts, eligibility, size/hash and provenance fields. Preserve the chain from geometry to attempt to file version to attachment to terrain. Coordinates remain GeoJSON longitude/latitude; no writes to raw X/Y, area or price fields. Retain the meaning of `bytes_geojson`/`sha256_geojson` as metadata for the exact stored GeoJSON text, not a promise about a future complete response envelope. Whole-body delivery size/hash belongs to the later transport contract; it must not incorrectly reuse these fields for different bytes.
5. **Attachment audit (`archivo_evento`).** Retain actor, time, action, owning terrain/attachment, optional related IDs and event-time base membership. Decisions allow one event per non-null attachment revision; informational events allow repeated NULL revision values. History references must not be able to name another attachment's or terrain's version/attempt/geometry. Future writers keep audit payloads free of storage keys and signed URLs. No public DTO or history endpoint is added here.
6. **Processing lease (`archivo_trabajo`).** One row per file version, non-null fencing token (`trabajo_id`), actor, operation, start and expiry. Support the completion/processing/activation operations in §9.2; no duration default is prescribed. It is ephemeral coordination, not audit or a snapshot reference. Durable backup/seed content includes the other five tables in a tested dependency order; omit active leases so a restore cannot resurrect a worker. Report how pending versions can be represented without a lease after restore. No cleanup job is implemented.

Use non-null UUID TEXT keys and the existing actor/time conventions; no generated numeric identity registration. Apply appropriate NOT NULL, enum, positive revision/sequence counters, nonnegative byte/geometry counts and relationship constraints (zero holes is valid). Do not add provider columns, an aggregate summary counter, terrain-version coupling or triggers implementing the future lifecycle.

## Referential integrity is required, not left to B to repair

Implement §9.4's composite relationships, including:

- Version ownership agrees with its attachment and terrain.
- Geometry ownership agrees with its version, attachment, terrain and processing attempt.
- An attachment's current version belongs to that attachment.
- Its active geometry belongs to that **same current version**, not merely the same attachment.
- A non-null active geometry requires a non-null current version and a KMZ attachment; do not leave a nullable-composite-FK bypass.
- If retaining both `archivo_intento.geometria_id` and `geometria.intento_id`, constrain the back-reference to that attempt and version as well. It must not name another attempt's result. Add the necessary composite uniqueness targets and deferred constraints rather than relying on insertion order to make a cycle disappear.
- Audit optional references, when populated, agree with their owning attachment/terrain and with each other when they describe the same attempt/version. Explicitly cover NULL combinations; do not assume MATCH SIMPLE checks skipped columns.

Use the existing deferred inventory-pointer approach for cycles on both databases; Postgres adds constraints after table creation. No destructive cascade. Cross-row lifecycle rules such as available/usable/selected state remain future transactional repository obligations; enumerate those in the report instead of claiming foreign keys enforce them.

## Required evidence

Use fictional data and disposable databases only. Test on SQLite and disposable Postgres:

1. Upgrade a populated accepted schema-9 fixture (including users, grants, a work base, local column definitions and inventory/history), preserve existing values exactly, rerun idempotently, and initialize a fresh database through the normal migration path. Run existing older-version migration tests too.
2. Accept valid PDFs and KMZ versions; reject bad core-column/type combinations, duplicate live KMZs, duplicate version/attempt numbers, orphan owners and invalid state/outcome combinations. Multiple PDFs and multiple retired KMZs must remain representable.
3. Explicitly reproduce the two-version error: V1/G2 rejected at commit, V2/G2 accepted; geometry with NULL current-version rejected. Cover another terrain/attachment and the attempt back-reference cycle.
4. Check audit-reference ownership, repeated NULL audit revisions, duplicate non-null audit revisions, duplicate completion attempts, and one lease per version. Use real commit boundaries for deferred constraint failures.
5. Show deleting referenced terrain/user/version/attempt/geometry fails without cascading history. Preserve valid empty attachments and pending uploads, which necessarily have nullable active/final fields.
6. Verify new durable tables appear in backup/seed support in a valid dependency order, with deferred cycles handled as needed; leases do not. Include representative cyclic attachment data in a disposable restoration/insertion-order check. Do not run the real cloud setup or migrate command against default configuration.
7. Run `./verificar.sh`, applicable lint/type checks, and green GitHub Python/disposable-Postgres and JavaScript checks on the returned head. Distinguish local skips from hosted CI evidence.

Return a separate draft PR with instruction SHA, exact application/dependency baseline, head, object/field/constraint map, future repository obligations, and release/backup notes. Name any genuine mismatch with the proposed future lifecycle rather than silently changing product behavior. This schema-only milestone needs no signed URL, provisioned service, real account operation or chosen provider.

## Next boundary

P1 handback gives B a concrete schema dependency. A-2/P2 authorization is the next A implementation assignment, including the transaction-scoped recheck, archive/scope rules and administrator bootstrap/recovery. It is not implicitly implemented or released by this packet. Keep PRs #14 and this new P1 draft separate and unmerged; stop for review of P1 before taking that next packet.
