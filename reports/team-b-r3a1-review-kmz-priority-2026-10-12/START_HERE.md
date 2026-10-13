# Team B — batching accepted; KMZ required for deployment

12 October 2026, approximately 15:03 America/Mexico_City (21:03 UTC).

## Decision

**Accept R3-A1 at `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3`, draft [PR #30](https://github.com/Andre07-hash/ARA-MAP/pull/30), within its bounded batch-summary scope.** No correction or further optimization assignment is requested. This does not authorize integration/PR merge or deployment.

The owner's latest direction makes **KMZ a required private-MVP deployment capability**. Local accepted KMZ work is preserved; B's next milestone is durable private files and the hosted upload → selection/activation → boundary display flow. Public catalogues, new saved-view features and renderer research remain deferred.

## Exact state and source review

Verified on GitHub: #30 remains draft at the stated head, branch `claude/team-b/file-summary-batching`, targeting `claude/team-a/application-integration`; GitHub reports it mergeable. Both checks are successful in [exact-head run 38306147799](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38306147799).

Compared pinned base `41d029c54848a7aebb1d46dfd053848ccf265afc` to final `bc7e421`. Code head `781e79b4a881e63c73d02403118664f14ce039e9`; tests `459dc59e3f5f0c1c8f69357e7c3454b513366419`. Reviewed the three changed server modules and the equivalence fixture against the existing `_verificar` read policy.

The new helper checks session/capability through `_verificar`, reads only bounded ID batches and refuses write capabilities. Admin/operator scope and archived-base behavior follow the existing read policy. Empty inputs, first-seen ordering, duplicates and unavailable IDs retain their behavior. No write locks, write reauthorization or policy rules changed.

SQL counts live PDFs separately and selects only five recent PDFs per terrain plus its live KMZ; it does not load all attachment rows into Python and truncate. The latest-version/lease and caller-aware privacy projection are reused. No schema, API shape, consumer, browser or renderer change. Changed-file whitespace check passes.

## Independent verification

Exact final application/test archive; macOS; SQLite on `/usr/bin/python3` 3.9.6 and fresh loopback Postgres 17 through the existing development environment. Fixtures are synthetic. Historical report files were excluded from extraction; no application changes were made.

| Check | Result |
|---|---|
| New batch equivalence, permissions, privacy, errors, forced chunks and query bounds | **10/10 SQLite; 10/10 Postgres** |
| Affected real mounted summary/location integration | **12/12 SQLite; 12/12 Postgres** |
| Independent service count probe, same fixture/connection for old and new algorithms | Operator: **8/400/800/1600 → 7/7/7/7** for 1/50/100/200; admin: **7/350/700/1400 → 6/6/6/6**, identical on both backends. |
| Exact-head GitHub CI | Python/disposable Postgres and JavaScript green. |

The first SQLite invocation also discovered 12 Postgres cases and skipped them for missing test URL; these 12 were then run explicitly on the fresh disposable Postgres target and passed. Total independently executed passing cases: 44. No remaining skipped coverage within those selected cases.

The mounted tests cover active KMZ boundaries without X/Y, rejected/pending replacement preserving the prior boundary, retirement/XY fallback, private pending projection and public-route restrictions, as well as the list response. They do not establish hosted file persistence or browser display on a deployment.

Saved evidence: [SQLite checks](evidence/sqlite-focused.log), [Postgres batching](evidence/postgres-batching.log), [Postgres mounted summaries](evidence/postgres-mounted-summaries.log), [SQLite counts](evidence/service-counts-sqlite.json), [Postgres counts](evidence/service-counts-postgres.json), [GitHub metadata](evidence/github-pr30.json). [Supervisor count probe](probe_summary_counts.py) reuses the synthetic test fixture; its Postgres mode refuses non-loopback targets.

Developer handler counts (200 rows: 1,611 → 18), timing medians, nine mutation controls and broad suite results were inspected as reported evidence, not independently rerun. The independent counts above measure the service only and include versioned file fixtures. CI's Postgres environment and the local Postgres 17 run are separate evidence. No browser, renderer, memory or 25k timing cycle was repeated.

## KMZ deployment priority

Accepted work already includes the parser, local/fake storage interface, upload lifecycle/API, candidate activation, geometry client and boundary rendering. A already consumed accepted B #28 in merge `e795935`; do not rebuild or merge it again. A's R3-A2 residual at `4670df7` is independently closed.

The deployment gap is not closed by batching. The combined candidate has local/in-memory file stores; neither proves durable hosted private storage. The cloud entry point declares a 4 MiB body cap while the accepted KMZ contract permits 20 MiB: trace the actual attachment request paths and confirm runtime compatibility before choosing the hosted transfer mechanism. This is a concrete compatibility question, not a measured provider-limit claim.

**Deployment gate:** an authorized operator can upload a valid KMZ, choose/activate its permitted polygon when required, see the correct boundary without X/Y, reload from another session/device, and retain the file, geometry and history after restart/redeployment. Failed replacement preserves the previous layout; denied accounts cannot obtain file/geometry; database-plus-file restoration recovers that same state. Test representative accepted sizes on the actual host.

Next owner actions are in [TEAM_B_KMZ.md](TEAM_B_KMZ.md). B returns one short concrete hosted-KMZ gap/implementation handback; A coordinates adapter/configuration and store injection. Provider/access/cost decisions and external operations still need explicit owner confirmation. Readiness preparation can proceed now; do not start another roadmap or optional optimization round.

The review and packet are saved locally, not published to GitHub. No merge, cloud operation, real account/data change or application edit occurred. The isolated local Postgres instance was stopped.
