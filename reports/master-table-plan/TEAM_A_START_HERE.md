# Team A — master table, permissions, and integration

**Preparation complete — current assignment:** read [Team A's approved implementation packet](../workspace-contract-2026-10-07/TEAM_A_PACKET.md) and its shared contract at the supervisor's supplied instruction commit. The preparation brief below is retained as history; do not repeat it.


Obtain these instructions from GitHub at the supervisor's named commit; see [GITHUB_HANDOFF.md](GITHUB_HANDOFF.md). Do not rely on desktop paths or assume this packet is already in main.

Read [MASTER_PLAN.md](MASTER_PLAN.md) and [TWO_TEAM_DELIVERY_PLAN.md](TWO_TEAM_DELIVERY_PLAN.md). Record their exact published instruction commit in your response. The owner has paused connected Excel; preserve that work and do not resume its previous assignment.

Your feature ownership: canonical master records, the editable table, optional core fields, custom columns, roles, history/conflicts, and filtered dataset persistence. Your lead is also the developer integrator for shared schema, routing, application-shell, and CI changes. The supervisor directs and reviews; the supervisor does not implement code.

**First assignment — prepare the first implementation packet while Team B investigates files/KMZ:**

1. Refresh repository/PR state without overwriting local work. Recommend an exact baseline and identify reusable inventory/auth/table code and any prerequisite fixes. Record the preserved Excel branch/commit; do not merge it to obtain unrelated features.
2. Propose the minimal master-record and role/capability contract. All fourteen core business fields are optional, including name and location. Preserve existing IDs/history where practical. Identify existing validation that conflicts with blank/partial entry or unknown currency.
3. Show a compact table interaction concept: add blank record, edit cell, saving/error/conflict state, custom-column control, and an attachment-cell slot owned by B. A sketch or non-production prototype is enough for this checkpoint.
4. Identify the shared schema/routes/client hooks B will need. Request its file/geometry requirements; do not independently design a competing attachment model. You own final edits to the shared files under the delivery plan.
5. Propose small implementation PRs with dependencies and meaningful acceptance checks. Identify business decisions that truly affect the first package, with recommendations. Leave later questions for their phase.

Deliver a concise report containing the exact baseline, reuse/changes, draft contract/examples, interaction concept, shared-change queue, initial PR sequence, and unresolved choices. This preparation does not require production credentials, real-data migration, or a production deployment.

After the supervisor consolidates the shared contract, implement the bounded Team A packet on your own branches. Test real persistence and server-enforced permissions. Coordinate B's integration early; do not wait for every grid enhancement before the first terrain + file + map demonstration.

Follow the delivery plan's ownership rules and handoff format. Do not edit B's active files, publish master records, grant new service access, or make production changes as a side effect of this preparation.
