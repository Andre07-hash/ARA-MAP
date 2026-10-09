# ARA MAP — supervisor session handoff

**Snapshot: 2026-10-08, 23:17 UTC.** Compact machine-readable checkpoint: [STATE.json](STATE.json). Repository: https://github.com/Andre07-hash/ARA-MAP. This packet transfers project context; it does not change either team's assignment. Verify later GitHub changes before reporting current status. It is self-contained for orientation; linked source packets govern implementation details.

## 1. Read this first: role, current position and next action

You are the owner's **supervisor, analyst, reviewer and planner**, not an application coder. Two external Claude Code teams work in separate accounts on this GitHub repository. The owner normally relays prompts and handbacks between them and you. Prepare clear copy/paste prompts plus durable GitHub packets; do not assume access to, or send messages into, those accounts.

The owner values honest independent assessment, concrete progress and clear explanations of who is working and what actually blocks them. Avoid repeated permission questions, speculative blockers and endless research. Resolve routine technical choices within approved scope. Ask the owner for real business decisions, account identities, purchases/access and final release authorization when necessary. Report findings candidly; green CI is evidence, not proof of product completeness.

**Current assignment:** Round 1 is already released at instruction commit **`f3fd0f05c0ba9f28bd8b3e7321f374368027e784`**. Do not issue it again or invent a new first step.

- **Team A / 1A:** assemble the accepted prerequisites into a tested baseline-only draft PR early; then implement the scoped terrain-record backend on a separate feature branch.
- **Team B / 1B:** first finish and submit its memory-budget research handback; then implement the local/fake PDF/KMZ lifecycle. B need not await acceptance of that research or completion of A's new record APIs to start 1B.
- **Supervisor next:** refresh the relevant GitHub heads once; review whichever concrete deliverable is ready. Prioritize A's combined baseline as the shared integration checkpoint. Review B's final research separately without making it a gate for attachment development.

At this snapshot, the new baseline, A-record and B-lifecycle branches were **not yet visible remotely**. B's research branch remained at `a9b6970da824a7b561b84bad6fc53f2d9e8ca30f`, with no final PR. This does not prove the teams have not started locally, nor that the owner has actually pasted the prompts. Say “instructions released,” not “both teams are running,” unless you verify that.

Main remains **`09452fd26d38319567dce28a89db100ea61c739a`**. Feature PRs are still draft/unmerged. Many components are reviewed, but the integrated employee table/file/map workflow is not yet delivered.

## 2. Product vision and decisions to preserve

Replace the immediate Excel-based workflow with an interactive table inside ARA MAP. **Park and preserve Excel work; do not delete it.** One canonical terrain UUID record set; work bases are ownership/access containers, not copied databases. Admins access everything; operators can add/edit records and files only in their assigned active work bases. Several users can share a base and a user can have several bases. Unassigned records are admin-only.

The fourteen core columns always exist, but **none is mandatory to fill to create a terrain**:

Tipo de terreno; Nombre de terreno; Estado; Municipio; Superficie; HA; Afectaciones %; Asking price; Asking $/m2; Comentarios; Archivos (PDF); KMZ; X; Y.

- X is **latitude**, Y **longitude**. Reuse the existing XY behavior. Prefer an active usable KMZ boundary; if its body is unavailable/pending, keep its interior-point symbol rather than relocating to unrelated XY. With no active geometry, use valid XY; otherwise remain unplaced.
- Unknown values stay null; no inferred currency, price/area conversion or derived HA/asking-per-m². Draft asking amounts may have unknown currency under the current packet. Publication rules remain separate. Geographic Estado is not a workflow status. Comentarios maps to private `notas_internas`.
- Preserve stable UUIDs, optimistic versions and immutable history. No name-based terrain duplication or identity reconstruction for this workflow.
- Custom columns are base-local text/number/choice/date with stable IDs and reversible retirement; core columns cannot be removed. Custom attachment-column types are deferred.
- Transfers are admin-only, keep terrain ID/core files/history, and revoke source-only access. Base-specific custom values retain their original definition IDs, stay hidden outside the permitted current-base projection, and reappear if transferred back. History/replay/conflict responses must not leak hidden values.
- Archive/restore preserves data. Permanent purge is excluded. Operators cannot indirectly alter public visibility. Existing public allowlists stay restrictive.
- Users will create filtered views/maps in one action. Existing saved maps stay frozen. Live filtered views plus explicitly frozen snapshots are the recommendation for the later view packet; finalize that behavior before Round 4.

## 3. Source of truth and shortest reading path

Current instructions override explicitly superseded historical proposals. A handoff summary is not permission to override the full packet or later owner directions.

**Read initially:** this document, then the relevant team's current packet. Do not read the entire reports tree or conversation history.

All of the following current documents are at **`f3fd0f05c0ba9f28bd8b3e7321f374368027e784`**:

| Need | Repository path |
|---|---|
| Shared branches, pins and ownership | `reports/round-1-instructions-2026-10-08/START_HERE.md` |
| A's exact implementation scope/tests | `reports/round-1-instructions-2026-10-08/TEAM_A.md` |
| B's exact implementation scope/tests | `reports/round-1-instructions-2026-10-08/TEAM_B.md` |
| Consolidated lifecycle contract | `reports/round-1-instructions-2026-10-08/ATTACHMENT_CONTRACT.md` |
| Corrected P2 acceptance and independent evidence | `reports/round-1-instructions-2026-10-08/P2_ACCEPTANCE.md` |
| Twelve-packet plan, including release update | `reports/execution-status-2026-10-08/REPORT.md` |
| Earlier shared product/geometry contract | `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md` |

GitHub link form: `https://github.com/Andre07-hash/ARA-MAP/blob/<commit>/<path>`.

Supervisor documents are on **`codex/supervisor-completion-brief`**, [PR #5](https://github.com/Andre07-hash/ARA-MAP/pull/5), not on main. Fetch that branch or use GitHub contents at the exact SHA. Read via `git show SHA:path` without checking out another team's branch. If the new session cannot access GitHub, the owner can upload this packet and relevant current reports/diffs; do not claim live verification from this snapshot alone.

## 4. Accepted components and pending work

Acceptance applies only to the named version and scope, not every later branch tip.

| Component | PR | Accepted head / disposition |
|---|---|---|
| A-1 work-base/schema 9 | #14 | `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9` |
| P1 attachment/schema 10 | #15 | `edf9bcd1dc51e74a627d54d5ce01d37113206055`; includes A-1 |
| A-2/P2 roles, authorization/write boundary | #17 | **`5d0844cfd678c2f7ec55ddb4b364275482d1a801` accepted**; includes P1 |
| B-1 standalone KMZ parser | #9 | `efc362818ba64618dbfc23556db8678cde525336` |
| B-2 boundary renderer | #11 | `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` |
| B-3S local/fake storage | #13 | `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53` |
| E1 path-drawing optimization | #19 | `eed9a4cb404406b8b261803c38947e8297a5edec`; includes B-2 |
| Corrected display research | #16 | `9da0ab10a344e66099d919f2da15d3a638e7292a`; **research only**, not production worker integration |
| Historical attachment proposal | #12 | `28bf0dbbf718571e35d501a7810d7e7d882ee3dd`; §9 then the current consolidated contract supersede older sketches |

**Do not reopen resolved review items merely because an older report calls them pending.** P2's final acceptance is in the Round 1 folder. Independent closeout: 58 role/race/dispatcher tests passed on SQLite plus fresh disposable UTF-8 Postgres 17, no skips; the original 30-second lock case returned 503 `ocupado`, left state unchanged and retried with 200. Exact-head verificar passed 812 Python tests with 99 Postgres skips, Python 3.9.6 and JS. Full GitHub Python/disposable-Postgres and JS checks passed. The independent closeout did not repeat the full 812-test Postgres suite.

P2 also corrected the unsafe claim that old role-ignorant code is a safe rollback. Recovery must preserve the access policy; no validated application rollback is already available. Existing accounts become operators with no grants. Named administrators and an operator-capable screen are **release prerequisites**, not development blockers.

Other open work:

- B memory investigation: `claude/team-b/display-memory-budget`; instruction `7a71c93c1c1be68dc5ac992ae6ae801cde1d9cd5`, `reports/team-b-e1-review-2026-10-08/TEAM_B_MEMORY.md`. Final report/PR was absent at snapshot. Working HANDOFF notes may contain stale labels.
- #4 hosted adapter/Preview at `077b4e0f1c184b2c2ef6d1c63ebb80381a113316`: earlier deployment blocked; no accepted hosted proof. Keep separate from Round 1.
- #6 Excel at `9d452790b4f22a59e9d904d3403be4153cbd810a`: parked, preserve.
- #18 `b28db07f0d614140899ce1482a231a82aea7bb6b`: developer verification documentation, not a feature milestone.

## 5. How the active parallel handoff works

A creates **`claude/integration/round-1-baseline`** from accepted P2, merges the exact parser, storage and E1 heads in that order, verifies it and publishes a baseline-only draft PR targeting main. A-1/P1/B-2 are already ancestors of their respective pins; do not duplicate them. No research prototype, Excel or deployment work enters it.

A then creates **`claude/team-a/master-record-backend`**, targeting that baseline branch. B creates **`claude/team-b/attachment-lifecycle`**, also targeting it. If A's checkpoint is not ready, B may prepare from pinned P2 plus parser/storage, then merge the exact published checkpoint normally. B does not consume A's unfinished record-feature branch. Keep the baseline stable; repairs are additive, recorded and propagated. No force pushes or duplicate integration branch.

A owns schema/auth/transactions/terrain and base repositories/route registry/shared config/eventual app shell. B owns new attachment service/repository modules and dedicated tests; later its file/map modules. Shared-file changes are explicit requests, not concurrent edits. The supervisor plans/reviews; A performs application integration. A component acceptance or green development checkpoint does not authorize a main merge.

Round 1 contract details most likely to be forgotten:

- PDF ≤25 MiB, KMZ ≤20 MiB; maximum five effective pending uploads/user. Upload deadline 15 minutes from start, completion-start deadline 60 minutes from start; lease 180 seconds. History default 50/max 100. Future read grants 60 seconds. Provider remains undecided.
- A usable single-candidate upload may activate conditionally; multiple candidates require explicit choice. Retired attachment cannot be resurrected; finalized history/bytes remain. A failed replacement preserves the last usable layout.
- Always enter `db.escritura()` and reauthorize with `auth.reverificar_terreno` inside the final write transaction. No slow file/parser I/O under DB locks. Keep the advisory lock; no automatic retry. The helper's SQLite guard does not certify arbitrary Postgres connections.
- Save a successful attempt **first**, including its geometry UUID, then its geometry in the **same transaction**. Terminal outcome, pointer decision and audit are atomic; final bytes/geometry stay immutable. Do not weaken P1 constraints.
- Attachment edits do not bump terrain cell versions. Scope every idempotency key/result and reauthorize replay; never return private cached output after transfer/revocation. Do not delete a possibly committed final object after an ambiguous DB error.
- No HTTP/file UI/cloud/renderer implementation in 1B; no table UI in 1A. This pair builds the record and file backends.

## 6. Remaining plan: twelve packets, six per team

Only **Round 1 is released**. The later rounds are a plan, not standing instructions to start everything.

| Round | Team A | Team B | Milestone |
|---|---|---|---|
| 1 | Combined baseline + record backend | Attachment lifecycle core | Backend foundations connected |
| 2 | Editable table, custom columns, base/grant UI | Attachment HTTP handlers + bounded geometry delivery | UI/API pieces |
| 3 | Application/DTO/routes/widget integration | File cells/details + geometry client | First complete local employee journey |
| 4 | Filtered views + frozen saved maps | Approved bounded renderer + snapshot integrity | Full local functional vision |
| 5 | Hosted candidate, migration/admin readiness | Durable private cloud storage + recovery | Hosted pilot candidate |
| 6 | Final candidate/shared fixes/release procedure | Independent full-flow, permission, failure/load checks | Release-ready evidence |

Twelve means feature packets, not an exact number of PRs/messages. Corrections remain in their packet. First complete local workflow is after six packets; full local vision after eight, hosted candidate after ten, release readiness after twelve. Do not infer percent complete or delivery dates from these counts.

Before later release: owner names exact administrator accounts; approves provider/access/costs and authoritative source records; settles live-view/snapshot and large-map fallback policy; authorizes isolated hosted resources and final production cutover. Synthetic target is 25,000 total records, a 3,000-record base, five editing sessions, terrain pages at most 200. It is a test target, not a growth forecast or performance guarantee.

## 7. Review workflow that saves tokens and time without reducing quality

**Start narrow, expand when evidence requires it.**

1. Fetch once and collect relevant PR head/base/changed-file/check metadata in one batch. Record a checked-at timestamp. If no head changed and no new failure appeared, do not reread or rerun the same work.
2. Read the current packet, delivery report's latest correction section and diff summary. For a stacked PR, compare against its intended dependency, not main, so already reviewed code is not counted as new. For corrections, diff the last reviewed head against the new head; inspect surrounding code where behavior depends on it.
3. Build a short acceptance checklist from the packet. Prioritize authorization, race/transaction boundaries, data preservation, API compatibility and real user behavior. Verify claims against code and reproducible evidence; do not review only the prose.
4. Run focused reproductions and affected integration tests first. Reuse previously accepted evidence tied to unchanged exact inputs. Run required full checks at meaningful delivery/integration boundaries and before pushes where repository rules require it. Do not repeatedly run the whole suite after unchanged documentation or an identical head just to appear thorough; never skip an applicable required gate.
5. Separate developer-reported results, independent checks, GitHub CI, browser evidence and hosted validation. A full suite can miss a race; a targeted reproducer can expose it. Disclose skips and limitations. If evidence is absent, request it rather than inventing acceptance.
6. Save full logs/measurements as files; return compact counts, failures and paths. Use `rg --files`, targeted `rg`, `git show` and bounded outputs instead of dumping entire trees/reports/binary data. Batch independent reads; keep dependent edits/checks sequential. Prefer Git/GitHub CLI or APIs over browser navigation when available; discover only tools/skills relevant to the current task, not the whole catalog.
7. Preserve accepted SHA + evidence + open findings + next owner in a small state ledger. At session end, append only what changed; do not regenerate history. Read historical reports only to resolve a specific question. The core packet plus an incremental update should replace replaying the entire conversation.
8. Give each team bounded scope, owned files, exact dependencies, runnable acceptance cases and a stop point. Publish shared contracts once and reference them. Release early prerequisites so neither team waits for the other's whole feature. Do not turn routine choices into owner questions.
9. Use event-driven updates or one on-demand check. Do not create recurring polls/check-ins without a current explicit request; old team-reported scheduled checks are not evidence that this supervisor owns an automation. If the owner requests monitoring, notify only on actionable changes unless requested otherwise.
10. Parallelize independent reads/checks safely. Do not launch duplicate reviews, expensive research or subagents merely to consume parallel capacity. Delegate only when authorized and when the bounded subtask can run independently. Save time through reuse and narrower uncertainty, never through weaker acceptance.

**Review output template:** verdict and exact head; actionable findings with severity/location/reproducer; evidence and gaps; named next action for each team; owner decision only if genuinely needed. A short clean acceptance is enough when no material findings remain.

Memory-research traps to check when B hands back: account for main/worker/queued/pinned/in-flight/bitmap allocations across multiple maps; measure actual viewport/DPR; include pre-phase long tasks and observer draining; distinguish pixel identity from tolerance coverage; verify hit testing/layer order/selection/cancellation/failure fallback. The 64/128 MiB settings are research budgets, not approved total browser-RAM bounds. E1 is accepted but not a universal sub-50-ms guarantee. Do not repeat the full historical performance matrix unless new changes warrant it.

## 8. Practical tools and operational limits

Architecture: standard-library Python server, Python **3.9** floor; SQL in `server/repo/`; SQLite locally and Postgres in cloud; plain ES-module JS/Leaflet with no build framework. No new local runtime dependency without review. UI strings Spanish; code comments/docstrings English. Read current `AGENTS.md` and applicable instructions. Explicit released stacking/domain decisions supersede outdated generic main-only or legacy import rules only within their stated scope.

Useful read-only entry points when a clone/CLI is available:

```bash
git status --short
git fetch origin
gh pr list --repo Andre07-hash/ARA-MAP --state open --json number,title,headRefName,headRefOid,baseRefName,isDraft
git show f3fd0f05c0ba9f28bd8b3e7321f374368027e784:reports/round-1-instructions-2026-10-08/START_HERE.md
```

Review in disposable archives or isolated checkouts; never switch or reset a coder's working branch. Use a fresh **UTF-8** disposable Postgres database; SQL_ASCII caused misleading fixture failures in an earlier review. `ARA_MAP_TEST_DATABASE_URL` must never target production. Python/SQLite/PG/browser evidence are distinct. Some Claude containers lack zsh; require all `verificar.sh` components with that limitation disclosed. A reported openpyxl packaging failure occurred in those containers but not the Mac review; do not waive a new occurrence without checking its actual cause.

Supervisor documents have been committed/pushed on existing PR #5. Continuing that documentation workflow is authorized. Do not change app code, main, production, cloud resources or real accounts under this handoff. Never put secrets or real terrain files in the repository. No merge/deploy/provision/role change is approved. No background job is assigned by this packet.

If continuing on the same Mac: the working branch was `codex/supervisor-completion-brief`; unrelated untracked `reports/project-review-2026-10-06/` exists and must remain untouched. Development tools may exist in `.venv-dev` and local Postgres 17; inspect availability instead of reinstalling. Prior `/tmp` artifacts are conveniences, not dependencies or portable evidence. Never give desktop paths to the external teams. `gh pr edit` previously failed on a deprecated Projects query; `gh api --method PATCH repos/Andre07-hash/ARA-MAP/pulls/5 --input <JSON-file>` worked. Preserve real newlines and avoid shell interpolation of untrusted report text.

**First response in the new session:** acknowledge the supervisory role, verify current GitHub deltas if access exists, identify what each team should currently be doing and the next concrete review. Do not restart planning, repeat the initial prompts or claim the project is already integrated.

## Incremental update — October 8 evening / October 9 UTC

The initial snapshot above remains historical. See
[`reports/team-b-round-1-review-2026-10-08/START_HERE.md`](../team-b-round-1-review-2026-10-08/START_HERE.md)
and `STATE.json.latest_supervisor_review` for the subsequent review:
baseline #20 and A's #22 are published; B's #21 research and #23 lifecycle
received scoped correction requests with independent reproduction evidence.
Both B heads have green CI but are not accepted. Team B prioritizes lifecycle
corrections, with research independent. A's newer #22 head `f6cd6b2` was observed
but not reviewed in that packet. Later rounds remain unreleased. Verify any
subsequent changes before presenting these facts as current.

### Subsequent A review — 2026-10-09, 00:43 UTC

PR #22 at `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037` was independently reviewed.
Its SQL-attention correction is accepted; the extreme-number warning is approved
as a non-blocking technical guard with clearer wording. Three remaining 1A
corrections concern legacy idempotency hashes, embedded custom-history projection
(seeded fixture; current core writers do not produce those custom diffs) and
typed cursor validation. See
[`A review and evidence`](../team-a-1a-review-2026-10-08/START_HERE.md) and
[`bounded correction-2 instructions`](../team-a-1a-review-2026-10-08/TEAM_A.md).
Independent 48-test SQLite/Postgres module and two Python-3.9 attention tests
passed; targeted probes reproduced the additional gaps. Baseline #20 remains
`1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`; B's instructions and acceptance
status are unchanged by this A review. No later packet, merge or deployment is
authorized. Refresh changed facts before claiming live status.

### B corrections reviewed — 2026-10-09, 01:51 UTC

**1B accepted** at #23 `a9dc8af8cc511bde0a67168da335398353b80aa6`; L1–L6
closed. Independent 78 SQLite/Postgres tests, 39 Python-3.9 tests, original
probes and eight actual finalization-boundary-first races per database support
the local/fake lifecycle acceptance. The paged `listar` envelope, history clock/
privacy flag and cleanup-status interfaces are now the accepted service handoff.

#21 `68077cc366dd3e1885da36b8f5c7223093e4bd63` remains research-only and needs
three narrow corrections: prepared-body ownership/audit under layer-admission
pressure, worker failure during reentrant memory relief, and a deterministic
allocation-failure test instead of a 16-GiB allocation assumption. R3/R4 closed.
See [review/evidence](../team-b-corrections-review-2026-10-09/START_HERE.md) and
[research-only instructions](../team-b-corrections-review-2026-10-09/TEAM_B.md).
Both exact heads have green GitHub CI; the research-specific independent suite
is 28/29, with the allocation-limit assumption failing. Browser matrices remain
developer evidence. A's correction 2 and the baseline checkpoint are unchanged.
No later packet, merge or deployment is released.

### B research closed — 2026-10-09, 02:27 UTC

**Research handback accepted**, not renderer integration, at #21
`5e9ed42ef740fcee881c54e011172fae9c6f209b`. R1a/R2a/R1-test closed; R3/R4
remain closed. Independent 37/37 Node tests passed twice, adapted probes passed,
and Chrome 154 pressure/resize/reset checks passed, including detection of the
injected missing-body audit defect and zero-ledger teardown. The full browser
matrix/paint/timing results remain developer evidence; RGBA differences and
the total-browser-memory limitation remain. Record a deterministic final-size
assertion as a future resize-integration gate, not a new open research task.

See [closeout and evidence](../team-b-research-closeout-2026-10-09/START_HERE.md).
B's #23 stays accepted and unchanged at `a9dc8af…`. B preserves both draft
branches; no further correction is requested now. A's correction 2 remains
pending at the observed head `f6cd6b2…`; the supervisor next reviews A's new
handback and the combined baseline. No 2A/2B, merge or deployment is released.

### A correction 2 and prerequisite baseline closed — 2026-10-09, 14:32 UTC

**1A accepted** at #22 `1ef2238766eae3e111c031b4fa24f9d849ef4753`:
A1/A2/A3 closed, technical warning wording and bounded history cursor accepted.
Independent 54 SQLite/Postgres record tests, 28 Python-3.9 tests and the three
original probe groups on both databases passed. Exact-head CI is green.

**Baseline #20 accepted** at `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`:
component ancestry/tree identity confirmed, 987 Python tests with disposable
Postgres and no skips, Python-3.9 suite with 99 PG skips, 120 JS tests passed.
This is integration of the prerequisite pins, **not combined 1A + 1B**.

See [closeout/evidence](../team-a-round-1-closeout-2026-10-09/START_HERE.md).
B's two accepted heads are unchanged. Neither team has further Round 1
corrections; preserve draft branches while the supervisor prepares the next
bounded instructions and the 1A/1B integration dependency. No 2A/2B, main merge,
deployment or E5 integration is released by this closeout.

### Round 2 instructions released — 2026-10-09

The owner requested the next messages for both teams. The
[Round 2 packet](../round-2-instructions-2026-10-09/START_HERE.md) now releases
**2A and 2B**; it supersedes the earlier statements that only Round 1 is
released. Accepted pins are unchanged and were refreshed before publication.

A assembles accepted #22 + #23 into a new tested Round 2 checkpoint, preserving
#20, then builds the editable table/custom columns/base-grant UI. B starts
attachment HTTP/bounded geometry from its accepted lifecycle now, merging the
exact checkpoint when published; it does not wait for A's grid. Production
mounting of B handlers/widgets remains 3A/3B. The shared seam and geometry
transport bounds are in INTERFACES.md. Preserve all old PRs and use separate
drafts. No 3A/3B, main merge, deployment or E5 integration is released.
Prompt delivery or active external sessions are not inferred from publication.

### Round 2 first review — 2026-10-09, 18:21 UTC

Both handbacks arrived: #26 `517223668405c1d4feb2deffbd2d16a072395fd9` (2A),
#25 `2ea602a940462fe8bb7d8f0208e0e1dbee19603e` (2B), on #24
`7117f57f0c52c092d421e5d4bacbcf068f8a65d0`. Exact-head CI is green;
**both feature PRs require corrections**. See
[review/probes](../round-2-review-2026-10-09/START_HERE.md) and the TEAM_A/TEAM_B
files there. Round 1 acceptances are preserved under `STATE.round_1_accepted_review`.

A owns inherited unread-body HTTP refusal framing, client privacy across
session/identity loss, safe custom text/date validation and row repaint that
removes another active editor. B owns Unicode integer query parsing that
currently returns 500. These are independently reproduced findings, not just
missing screenshots. Retaining Inventario as the admin default is acceptable.

The composition checkpoint's ancestry/trees and 1,121-test SQLite/Postgres run
are verified, with inherited dispatcher correction explicitly carried to A.
Keep #24 frozen; corrections stay additive in #26/#25. B does not need to wait
for A to return its own correction. No 3A/3B, PR/main merge, deployment or E5
integration is released. See latest_supervisor_review for exact evidence/owners.

### Round 2 correction review — 2026-10-09, 19:08 UTC

Reviewed A #26 `cda5c20580179abcd8673010797a9975b1b7a06d` and B #25
`704d8b8745b79f7b72f35350079ccd788e6d2e0a`, both draft with exact-head CI green.
See [review and bounded next instructions](../round-2-corrections-review-2026-10-09/START_HERE.md).
The original A1–A4 and B1 reproductions are corrected. A's 16 identity/editor
journeys and the original supervisor browser probes pass independently.

Two residual actions, independent and on the same feature PRs: A owns R2-A5,
empty/repeated HTTP framing headers that still let the body become a second
public request; B owns R2-B2, a test-only privacy assertion repair because a
public UUID can contain the byte-count substring. Both are independently
reproduced; the latter is not an observed privacy leak. B's new R-7 negative/
non-ASCII Content-Length issue is already fixed at A's reviewed head, so do
not resend that repair. Do not modify the frozen #24 or accepted #21/#23.

STATE.latest_supervisor_review is current; round_2_first_review preserves the
previous findings. No 3A/3B, merge, deployment or open-ended memory research is
released. The owner still relays the new bounded correction prompts.

### Team B packet 2B closed — 2026-10-09, 19:40 UTC

**2B accepted for HTTP-harness scope** at #25
`bf4c6a694ca95087368bb2d89325d7a240a7b676`; R2-B1 and R2-B2 closed.
Only tests/evidence changed. The deterministic UUID collision passes on both
databases and all six deliberate production-path leak mutations are detected.
Independent affected suite: 145 SQLite/Postgres tests, zero skips; Python 3.9
lifecycle: 82 run with 41 PG skips. Exact-head GitHub CI is green. See
[closeout and raw evidence](../team-b-2b-closeout-2026-10-09/START_HERE.md).

B has no remaining 2B correction; preserve its draft and wait. A's new #26
head `32a2a55e4a7417499cc384109bd44666e7a568cb` was observed but not reviewed
in this closeout, so R2-A5 awaits verification. #21/#23/#24 remain unchanged.
No app-mounted endpoint acceptance, 3A/3B, merge or deployment is released.
