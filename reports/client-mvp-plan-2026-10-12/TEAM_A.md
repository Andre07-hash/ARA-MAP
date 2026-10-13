# Team A — planning brief for private MVP readiness

Ready for the owner to relay. This is read-only preparation and a proposed next scope, not a released implementation or deployment packet.

The owner wants an ASAP private administrator/operator portal. Public catalogues per base are deferred. Preserve `claude/team-a/application-integration`, draft #29 at `4670df7348265af66c640069e5ece2a274830fa3`, the consumed B candidate/merge, and frozen C1. Your R3-A2 residual is delivered and awaits supervisory review; do not create another correction or rerun broad suites unless a concrete new finding requires it.

B has delivered R3-A1 as separate draft #30 at `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3`, targeting your integration branch. It is not yet accepted or authorized for integration. Do not duplicate batching or repeat the merge of accepted #28.

Prepare a short readiness handback using current code and existing evidence:

1. Inventory the gap between the combined candidate and the hosted adapter #4 at `077b4e0f1c184b2c2ef6d1c63ebb80381a113316`. Identify the minimal adapter/dispatcher/configuration changes, actual authentication route behavior, migration path and store-injection boundary. Preserve shared server authorization. Do not copy the historical shared-password onboarding instructions into the private MVP guide.
2. Identify the recorded Vercel deployment block and the authorized operator action needed to resolve it. Distinguish known evidence from anything requiring account access. Do not deploy, modify linkage or change accounts.
3. Trace attachment upload/download paths through the adapter. It declares a 4 MiB body limit; the file contract permits PDF 25 MiB/KMZ 20 MiB. State what is affected and what B's private-store contract must provide. Do not guess current provider capabilities.
4. Describe isolated Preview configuration, startup/schema validation, no production fallback, individual account bootstrap and base grants. List environment variable names only; never values. Separate code work from operator-only resource/secret/account actions.
5. Produce a minimal Spanish onboarding outline and a proposed hosted acceptance run using the matrix in START_HERE.md. Include restart/redeployment and B's database-plus-file restore rehearsal. Keep advanced views, renderer research and public catalogues outside this scope.

Return owned files, dependencies/shared-file requests, estimated remaining effort, the next concrete milestone and the decisions needed from the owner. A will own application integration and shared configuration; B will own private files and recovery. B's pending narrow auth helper must not overlap with your changes.

Stop after the readiness report. Do not write application code under this brief, alter deployment configuration, integrate PRs, migrate/provision/deploy, create real accounts or import real data. The supervisor will issue exact pins and bounded implementation instructions after current reviews and a concrete hosting decision. Use existing evidence; no new broad browser, renderer, memory or performance cycle is requested.
