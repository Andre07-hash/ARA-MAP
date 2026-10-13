# Team B — planning brief for private files and recovery

Ready for the owner to relay. This is read-only preparation and a proposed next scope, not a released implementation or cloud-operation packet.

The owner wants an ASAP private portal. Preserve accepted draft #28 and its branch at `b2ac9bd176043fc4b1625b13993f8f21407dc978`; R3-B1–B5 remain accepted. R3-A1 has now been delivered as draft #30 at `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3`, branch `claude/team-b/file-summary-batching`, based on combined pin `41d029c54848a7aebb1d46dfd053848ccf265afc`, targeting A's integration branch. Do not restart or broaden batching. Await concrete supervisory feedback on that PR.

Prepare a short private-storage/recovery handback:

1. Map the accepted `server/almacen.py` interface and file lifecycle onto a proposed durable private backend. Identify the smallest provider-specific code surface, configuration names, dependency requests and unresolved capability questions. The provider is not yet approved; do not provision anything or assume account access.
2. Preserve API shapes, immutable finalized bytes, owner-scoped pending state, expiry/lease, safe completion replay and retirement. Do not weaken authorization or place slow file I/O under database write locks. Explain handling of ambiguous commit outcomes without deleting a possibly committed final object.
3. Define authorized transfer/read paths jointly with A. Preserve file privacy on direct requests, transfer, revocation and session loss. If temporary read grants are proposed, retain the accepted short-lived contract and state its revocation limits. Verify capabilities before claiming immediate revocation or size support.
4. Specify one database-plus-file backup and restore procedure, including consistency/quiescence, pending uploads, object inventory, fixture hashes, active geometry/history and the fresh isolated restore target. Identify missing-object detection, backup ownership, proposed frequency/retention and measured recovery evidence needed. Do not claim a database-only backup preserves uploaded bytes.
5. Give A the store-injection/configuration contract and a focused synthetic acceptance checklist. Coordinate adapter upload constraints with A; keep the current page map and accepted parser/renderer intact.

Return proposed owned files, shared-file requests, estimated remaining effort and next milestone. A owns adapter/dispatcher/auth policy/schema/shared configuration. Your #30 read-helper allowance is bounded to that optimization; request broader shared changes rather than making them concurrently. Separate application implementation, provider decisions and operator actions.

Stop after the readiness report. No application edits, unrelated renderer/memory work, new feature round, PR/main merge, deployment, provisioning, account changes or real-data import is released by this brief. The supervisor will name implementation pins and acceptance cases after review and the concrete hosting decision. Use current evidence; do not rerun broad suites for this planning exercise.
