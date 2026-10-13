# Approved workspace contract and parallel implementation packets

The owner approved the Team A workspace proposal with the supervisor's adjustments on October 7, 2026. This packet releases new work; earlier instructions to wait for Team A or keep B-2 pending are superseded **within the scope below**.

Read these from GitHub at the exact instruction commit supplied by the supervisor:

1. [SHARED_CONTRACT.md](SHARED_CONTRACT.md), both teams.
2. [TEAM_A_PACKET.md](TEAM_A_PACKET.md), Team A: A-1 schema foundation.
3. [TEAM_B_PACKET.md](TEAM_B_PACKET.md), Team B: B-2 boundary renderer.
4. [Fictional interface example](examples/boundary-terrain.json), both teams.

Overall scope: [master plan v2](../master-table-plan/MASTER_PLAN.md) and [delivery/ownership plan](../master-table-plan/TWO_TEAM_DELIVERY_PLAN.md). Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP). Documentation branch/PR: `codex/supervisor-completion-brief`, [#5](https://github.com/Andre07-hash/ARA-MAP/pull/5).

## Reviewed inputs

- Team A preparation: [PR #10](https://github.com/Andre07-hash/ARA-MAP/pull/10), `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6`. Accepted as a preparation report subject to this consolidated contract; its dependency sequence is corrected here.
- Team B parser: [PR #9](https://github.com/Andre07-hash/ARA-MAP/pull/9), `efc362818ba64618dbfc23556db8678cde525336`. B-1 accepted, findings closed; do not rewrite it as part of B-2.
- Application baseline at issue: `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`. Fetch again before work and report any change; the documentation commit is not an application starting point.
- Excel PR #6 remains parked. PR #4's API adapter fix remains a separate hosted-verification prerequisite; do not casually adopt its deployment-configuration change.

## Authorization and stopping point

Both teams may start their named packet now on separate branches. Deliver small draft PRs with exact commits, evidence and shared-change requests. This publication does not dispatch Claude sessions, merge any PR, modify accounts, provision cloud services or authorize a production deployment. Return for supervisory review before proceeding beyond the named packet.

The next sequence is A-1 → A-2 role/base access → A-3 master APIs, alongside B-2. Before B-3 starts, B supplies the revised attachment requirements and A lands a small **attachment prerequisite** migration/route integration PR. The later joint integration PR must not own prerequisites on which B-3 itself depends. That removes the circular dependency in the preparation report.
