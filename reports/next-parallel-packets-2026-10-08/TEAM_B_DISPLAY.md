# Team B — resolve the large-KMZ display strategy with measured prototypes

## Start now, independently of A

Your B-1, B-2 and B-3S foundations are accepted. No further correction to those PRs is requested. While A implements the attachment schema, investigate the existing B-2 extreme-multipart limitation: one large part plus about 19,999 small parts can take 1.5–3.3 seconds per view change. The accepted B-2 review already makes a measured bounded display strategy a rollout requirement. This packet advances that requirement without waiting for database/auth work.

Deliver **one bounded investigation**, with reproducible browser measurements, isolated prototype code and a recommended implementation plan. This is not authorization to change the production renderer, parser, storage or attachment lifecycle yet. Do not expand into a framework rewrite, provider investigation or another general attachment proposal.

After fetching current main, create `claude/team-b/display-strategy` from main (at issue `09452fd26d38319567dce28a89db100ea61c739a`). Put deliverables only in `reports/team-b-display-strategy-2026-10-08/`. Load accepted parser/renderer commits into disposable working directories with `git archive` for measurement; they need not merge or be copied into production paths. Preserve the accepted branches.

Inputs:

- B-2 PR #11: **`5d8e2dcc125a688dbba38a260d5d7eca88a6d223`**. Read its report and existing browser/measurement harness.
- B-1 PR #9: **`efc362818ba64618dbfc23556db8678cde525336`**, used to produce valid fictional limit fixtures. Do not lower parser budgets to hide the problem.
- The shared geometry interface under `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md` and B-2 acceptance under `reports/team-b-b2-review-2026-10-07/ACCEPTANCE.md` in this instruction history.

## Questions to settle

1. Separate costs: one-time body validation/conversion, per-view visibility/projection work, canvas painting, hit testing and selection. Measure cold and repeated views. Identify the bottleneck rather than assuming fetching/chunking solves browser work.
2. Compare at least two concrete approaches: (a) caching validated immutable bodies and per-part bounds with viewport culling; (b) bounded/cooperative work with cancellation and an explicit outline-pending representation when exact work cannot finish promptly. They can be combined. Explain what happens when every part is visible, including a dense case that defeats simple culling.
3. Define the employee-visible behavior while work is pending: a distinct status at the accepted interior point, selection retained, and no claim that an incomplete outline is complete. Distinguish loading, invalid/missing body, and temporarily deferred drawing. Propose exact Spanish wording and any additive renderer callback/status needed by A; do not silently change the frozen interface.
4. Identify cache keys, memory bounds, invalidation, generation cancellation and cleanup. A newer viewport/filter/session/render or teardown must invalidate outstanding work. Memory must not grow without limit when the user visits many geometries. Include cold-start work in the budget; moving the stall from pan to first load is not a complete solution.

## Non-negotiable invariants

- Exact stored geometry and B-1 validation stay unchanged. No silent simplification, dropped parts/holes, coordinate rounding, weakened bounds validation or smaller parser acceptance limits.
- Active usable KMZ geometry retains priority; never jump to unrelated X/Y because drawing is costly. Pending outlines remain located by the accepted interior point. Existing XY-only behavior remains compatible.
- Every displayed part refers to the original terrain ID. Selection and hit testing must agree with what has actually been painted. An unfinished operation cannot report successful full-outline/scale completion.
- Culling may omit genuinely off-screen parts only; retained geometry remains complete. Any coarser visible representation is explicit, not an apparent exact boundary.
- Prototype code stays in the report or disposable archive. No changes to A-owned schema/auth/routes/adapters, accepted B application files, CI, deployment, or real data.

## Reproducible evidence and handback

Preserve a generator and commands for the three known valid limit cases: one 100,000-position ring; roughly 20,000 parts; one large part plus about 19,999 small parts. Add a dense all-visible case and a small normal/XY control. Generate fictional data rather than committing multi-megabyte artifacts where a small deterministic generator suffices. Record exact parser and renderer provenance, browser/version, machine and fixture counts/hash.

Use a real browser and real pointer input. Repeat a fixed set of cold loads, pan/zoom, selection, repeated-view, rapid cancellation and teardown actions. Measure wall-clock completion and longest main-thread/input delay, not just function timing. Paint evidence must wait for actual frames and reject blank captures, preserving B-2's corrected verification method.

Use an initial **engineering investigation target** of no single main-thread task above 50 ms during repeated interaction and visible acknowledgement of input/deferred status within 100 ms on the recorded test machine. These are measurement targets, not a universal device guarantee or a reason to falsify a pass. Report median, worst observed and iteration count, plus whether exact drawing eventually completes; explain misses and tradeoffs. Record memory evidence where supported and clearly mark estimates where not.

Provide before/after measurements, prototype source or a replayable patch confined to disposable fixtures, and a recommended final implementation with proposed owned files, additive interface needs, regression tests and remaining limitations. If neither approach meets the target, return the measured bottleneck and smallest explicit product/architecture decision needed. Stop after this bounded comparison; do not keep adding speculative prototypes indefinitely.

Run the baseline project's normal verification before pushing the report/prototype PR; report any environment limitation accurately. Run the benchmark's own checks and obtain normal repository CI on the draft. Browser measurements are separate evidence from CI. No cloud or company-file access is required.

## Stopping point

Return the draft PR, instruction/main/baseline/head SHAs and the recommended strategy. Production renderer implementation receives a follow-up packet after review of this evidence. Full B-3 attachment implementation still depends on reviewed P1 and the separately consolidated lifecycle/authorization contract. This investigation does not block A's work or require A to supply anything first.
