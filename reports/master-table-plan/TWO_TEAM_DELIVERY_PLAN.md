# ARA Map — two-team delivery plan

Version 2 · October 7, 2026 · Coordination plan for two independent Claude Code accounts

**Decision: split ownership by feature. Team A owns the master table, roles, and shared application integration. Team B owns attachments and KMZ mapping. Each team delivers its feature across interface, backend, and tests.**

Both teams work in separate clones and branches of the same repository. The supervisor plans, resolves shared contracts, reviews, and reports; developers implement. This document assigns work but does not dispatch sessions, merge PRs, or authorize production changes.

The [master plan](MASTER_PLAN.md) governs product scope. Excel connectivity remains parked and preserved. The [approved workspace contract](../workspace-contract-2026-10-07/START_HERE.md) settles work-base access, local custom columns, transfer rules and the current A-1/B-2 boundary. Other pending choices remain assigned to their later packets.

## 1. Ownership

| Team | Primary responsibility | Concrete deliverables |
|---|---|---|
| **A — Master data and permissions** | Canonical terrain records, editable grid, roles, custom columns, filtered datasets | Blank record creation; fourteen protected core columns; direct editing and save feedback; history/concurrency; admin/operator enforcement; custom field definitions; filter/view persistence; reviewed data migration |
| **B — Documents and geography** | PDF/KMZ handling and terrain layout display | Private storage integration; upload/open/download/replacement; attachment cells and detail widgets; bounded KMZ parsing; normalized geometry; polygon selection/bounds; existing X/Y fallback; geometry/file version retention |
| **Supervisor** | Scope, contracts, decisions, reviews, readiness | Shared-contract decision record; scoped packets; review findings; acceptance assessment; owner-facing progress |
| **Designated developer integrator — Team A lead** | Assemble reviewed work | Shared-file integration PRs; dependency order; combined candidate; conflict resolution with the owning team |
| **Authorized cloud operator** | Environment and release operations | Isolated Preview resources, storage/configuration, hosted verification support, reviewed release procedure |

The integrator is a developer responsibility, not a coding assignment for the supervisor. The integrator may not rewrite Team B's owned modules without coordination. An integration duty does not grant unilateral product or production-release authority.

## 2. What can run in parallel

The master plan's phases remain acceptance milestones. Their implementation can overlap through these workstreams.

| Work wave | Team A | Team B | Dependency / joint checkpoint |
|---|---|---|---|
| **0 — Preparation** | Audit inventory/auth and existing fixes; identify canonical fields, migrations, and data sources; propose grid experience and record/role contract | Audit current renderer; inspect representative or generated KMZ files; propose file/geometry contract, upload experience, and storage options | Agree a small shared contract before dependent production implementation. Neither team waits idle: both perform their own audit, design, and isolated feasibility work. |
| **1 — Core implementation** | Master-record APIs, role enforcement, blank creation, grid editing, history/conflict handling | PDF/KMZ service modules and upload widgets; independent KMZ parser tests; render sample polygon geometry through the existing map | B develops against agreed sample terrain/permission responses. A lands necessary shared schema and route registration in small prerequisite PRs. Integrate a real persisted terrain + attachment as early as possible. |
| **2 — Complete the features** | Custom columns, search/filter/sort, grid/file-cell integration, role-management workflow | Real storage-backed PDF workflow; KMZ validation/processing; boundary-first map selection/fit; X/Y and invalid-file fallback | One Preview demonstrates: create incomplete terrain → attach file → render boundary. Mock-only work is not accepted as integration. |
| **3 — Derived datasets and history** | Save filtered views; one-action view/map creation; snapshot API/data contract; migration rehearsal preparation | Render derived datasets; geometry/file version retention for snapshots; layout performance and mixed polygon/point behavior | Agree live/frozen semantics before this wave. A owns dataset membership; B owns geographic representation. |
| **4 — Verification and release preparation** | Exercise B's file access, failed replacements, processing errors, and snapshot retention; rehearse data/role migration; integrate fixes | Exercise A's blank creation, permissions, custom columns, concurrent editing, and derived-view behavior; test browser flow with real hosted files | Both report against one combined candidate. The supervisor reviews. The cloud operator completes hosted/recovery/release work under the release packet. |

Each team tests its own feature during implementation; the last wave adds cross-team verification rather than postponing tests until the end. Teams can share findings earlier.

**Work that should not run independently:** defining two competing terrain schemas; assigning migration numbers separately; changing the same authorization policy; deciding saved-view semantics differently; editing the same application-shell sections; running two release migrations against one database. These need a single owner and explicit handoff.

## 3. The minimum shared contract

Avoid an exhaustive design document before anyone can work. First agree only the boundaries that the teams must share:

| Contract | Must establish | Draft / review |
|---|---|---|
| Terrain identity and editing | Stable terrain ID; nullable core fields; custom-field IDs; version/conflict and error behavior | A drafts, B reviews |
| Roles and capabilities | Which operations each role may perform; session/capability response; server-side enforcement; file-access checks | A drafts; supervisor resolves business choices with owner |
| Attachments | Relationship to terrain/column; file/version ID; processing states; open/download access; replacement/removal; which revisions change | B drafts, A reviews |
| Geometry | Active geometry/version; shape payload/reference; bounds; geometry-only terrain is located; X/Y fallback; pending/error/last-valid behavior | B drafts, A reviews |
| Component integration | File-cell/widget inputs and callbacks; grid invalidation/save events; map selection by terrain ID | Joint, A maintains the agreed entry points |
| Derived views and snapshots | Filter definition/membership; live versus frozen behavior; immutable geometry and file-version references | A drafts with B; settle before wave 3 |

The supervisor consolidates this into the phase packet with an exact instruction commit. Small fictional response examples and files travel in Git so both clones use the same contract. Contract changes require a short written impact note and acknowledgment from the dependent team; neither side changes shared field names or behavior silently.

Unresolved business choices only block the work that depends on them. The approved contract settles operator archive/restore rights and work-base scope. Provider selection and snapshot details remain later decisions; the current renderer packet does not depend on those choices.

## 4. File ownership and shared changes

Existing directories may contain shared concerns. Ownership below is the default for this milestone, not an instruction to reorganize the repository wholesale.

| Area | Owner / rule |
|---|---|
| `server/inventario.py`, `server/repo/inventario.py`, `server/api/inventario.py` | A: master record and dataset behavior |
| `server/auth.py`, session APIs and account tooling | A: roles, capabilities, provisioning |
| `web/components/inventory/`, master-grid modules, `web/lib/inventario.js` | A: grid and record state; calls B's attachment components through the agreed interface |
| New file-storage, attachment API/repository, and KMZ-processing modules | B: choose paths in the first packet; keep code modular |
| New attachment UI components/client module and feature-specific styles | B: exported widgets/actions usable by A's grid |
| `web/components/map/MapCanvas.js`, geometry helpers, map-specific styles | B: extend for KMZ; preserve established X/Y behavior |
| `server/db.py`, `server/postgres.py`, schema versions, migration entry points | A is sole editor/integrator. B supplies its schema requirements; A lands and tests the shared migration before B's dependent feature merges. Do not create a new migration framework solely for team coordination. |
| `server/app.py`, shared routing/auth dispatch, `web/components/app.js`, shared client/store/router | A is sole editor/integrator. B supplies route registrations/component hooks as explicit integration requests. |
| `server/repo/mapas.py`, map/base APIs, saved dataset wiring | A owns persistence/membership; B supplies geometry/file-version requirements and verifies preservation |
| `pyproject.toml`, shared CI, deployment configuration, shared CSS tokens | A integrates reviewed changes. B requests dependencies/checks; neither team changes production configuration independently. |
| Feature-specific tests and fixtures | Feature owner; create separate test modules where practical |
| Combined end-to-end harness | Assign one owner per scenario/file; during wave 4 B owns the new user-journey scenarios and A owns shared CI wiring |

**Shared-file request:** the requesting team records the path, needed change, contract/example, dependent PR, and acceptance check in its PR or handoff. The integrator implements the small shared change and returns the exact commit. Do not send an untracked local patch as the only evidence.

If a shared-file request becomes the bottleneck, transfer that file's ownership explicitly for one task, with a starting SHA and hand-back point. Do not have both teams edit it concurrently or route every routine line-level decision to the owner.

## 5. GitHub workflow and merge order

1. **Establish an exact baseline.** Before implementation, refresh repository state and review current open work. Start from the agreed main/prerequisite commit, not the paused Excel branch. Previously reviewed SHAs are historical references until checked again.
2. **Separate branches per deliverable.** For these Claude Code accounts, use `claude/team-a/<work-item>` and `claude/team-b/<work-item>`, following the repository's Claude-specific branch convention. Use independent clones/worktrees. No shared working branch, direct pushes to main, or force pushes to another team's branch.
3. **Open small draft PRs early.** State owner, instruction SHA, purpose, owned/shared files, dependencies, contract version, tests, and readiness. A draft is visibility into work, not permission to merge it.
4. **Keep dependent work explicit.** B can work against contract fixtures immediately. If actual development needs an unmerged A prerequisite, record the exact dependency and use an explicitly stacked draft PR; do not pretend it is independently mergeable. Once the prerequisite is merged, update/rebase onto main and verify the resulting diff and tests. Avoid copying the same fix through several undocumented cherry-picks.
5. **Merge shared prerequisites first.** Contract/examples → required schema/auth/shared hooks → feature implementation → combined integration corrections. Feature PRs from both teams can alternate once their dependencies are satisfied.
6. **Protect incomplete functionality.** Main must remain compatible with existing data/routes. Incomplete new UI may remain unavailable behind an agreed feature gate; never disable authorization to make a demonstration work. Use an isolated integrated Preview for acceptance.
7. **Review before integration.** After the owning team's tests and supervisory review, the designated developer integrator merges in dependency order. Approval belongs to the reviewed commit; significant follow-up changes need the corresponding review/checks. Production release is a separate gate.
8. **Verify the combined candidate.** Green isolated PRs are not proof that the final combination works. Run the relevant integrated scenarios against the exact candidate after merge, and report that SHA/deployment.

Branches do not isolate databases or uploaded files. Each team's tests must use its own disposable database and file-storage namespace/credentials with appropriate separation. A shared integration Preview has one operator and controlled migrations. Neither team runs destructive suites against production or against a Preview containing real business data.

The two Claude accounts may have different cloud access. A blocked cloud action does not stop independent local work. Record the exact access action and assign it to the authorized operator; never commit credentials to share access between teams.

## 6. Current assignments and dependency order

Preparation is complete: Team A PR #10 at `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6`; Team B preparation PR #8 and accepted B-1 parser PR #9 at `efc362818ba64618dbfc23556db8678cde525336`. Earlier kickoff briefs remain historical context.

- **Team A, A-1:** [schema foundation packet](../workspace-contract-2026-10-07/TEAM_A_PACKET.md), covering work bases, grants, role metadata and local custom-column schema. No new UI or permission enforcement yet.
- **Team B, B-2:** [boundary renderer packet](../workspace-contract-2026-10-07/TEAM_B_PACKET.md), covering geometry-first map behavior through fixed fictional interface examples. No attachment backend or A-owned application-shell edits.

These start concurrently from the current application baseline, each with a draft PR and supervisory checkpoint. The exact common contract is [SHARED_CONTRACT.md](../workspace-contract-2026-10-07/SHARED_CONTRACT.md).

After A-1 review, A-2 access control and A-3 scoped APIs follow. Before B-3, B supplies attachment requirements and A delivers a small shared schema/route prerequisite. The later widget/integration task must not hold that prerequisite: B's attachment API cannot depend on an integration task that itself waits for B's API. Explicitly stacked drafts are permitted; prerequisite commits merge first after review and authorization.

Database-side scoped queries and bounded pagination are required before accepting the global master view. Full-table browser loading is not the rollout approach. See the shared contract for synthetic capacity checks and transfer/history visibility rules.

## 7. Progress and acceptance

Each team reports at a PR-ready milestone, shared-contract change, or meaningful blocker:

| Item | Required information |
|---|---|
| Identity | Team, instruction commit, branch, PR, implementation SHA |
| Outcome | What now works; what is still mock-only or incomplete |
| Evidence | Tests/scenarios, environment, exact tested commit; hosted evidence separately |
| Coordination | Shared changes requested; dependencies; next independent task |
| Decision/access blocker | Exact question/action, affected work, proposed owner |

The supervisor maintains one owner-facing status table for A, B, integration, and release. The owner should not reconcile conflicting coder reports or decide Git merge conflicts.

**First joint milestone:** an operator signs in, opens an assigned work base, creates an unnamed terrain, edits a cell, uploads a PDF and KMZ, reloads from another session, and sees the stored PDF and KMZ boundary without supplying X/Y; a restricted action is denied. Test this early, before completing every customization and derived-view feature.

If one team finishes its current package sooner, use cross-testing, fixtures, performance checks, or a newly assigned independent package. Do not let it begin editing the other team's active files simply to stay busy. No assumption of a twofold speed increase: shared design, integration, and release still have sequential steps.

Use the [GitHub handoff instructions](GITHUB_HANDOFF.md) to read this plan and the kickoff briefs at the supervisor's named instruction commit. No Claude session is dispatched merely by publishing these documents.
