# Team B — corrections to existing research and packet 1B

Repository: `Andre07-hash/ARA-MAP`. These are corrections within your existing
assignments, not a new round. Read this folder's `START_HERE.md` in full.
The original Round 1 contract remains at instruction commit
`f3fd0f05c0ba9f28bd8b3e7321f374368027e784`.

1. Fetch and compare actual heads. Reviewed #23 is
   `6f303e1d0672c0b0c0e9170a601f8ef388b0f3b7`; reviewed #21 is
   `229d424aab2aa7659f5572fce3be41821e435c56`. Preserve any later work; report
   changed inputs and review only relevant deltas. No force push or restart.
2. Prioritize **1B L1–L6** on `claude/team-b/attachment-lifecycle`, same draft
   PR #23 targeting `claude/integration/round-1-baseline`, checkpoint
   `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`. Fix resource ownership/error
   indistinguishability, caller-aware pending history/projection, live clock
   and controlled lease conflicts, bounded listing, active PDF summaries,
   and truthful cleanup reporting/replay. Do not consume A's feature branch.
3. Reproduce the supplied cases against the reviewed code first. Turn them
   into meaningful regression assertions in your dedicated tests, using the
   same acceptance matrix on SQLite and disposable UTF-8 Postgres. Check the
   unchanged authorization/replay, both scope-race orders, cancellation and
   retirement, immutable outcomes and uncertain-commit retention as affected.
   Add missing cases explicitly; do not describe inherited P2 helper tests as
   direct evidence for new attachment behavior they do not execute.
4. Keep new service/repository/test edits within 1B ownership. Update the
   public service signatures, examples and report if bounded pagination or
   error/cleanup projections change. No HTTP, UI, provider, renderer, schema
   or authorization rewrite. Send a minimal reproducer for any real A-owned
   prerequisite issue while continuing independent corrections.
5. Separately correct **research R1–R4** on
   `claude/team-b/display-memory-budget`, same draft PR #21 targeting
   `claude/team-b/display-strategy`. Only the existing research folder may
   change. Include actual per-layer arrays in admission and independent audit;
   handle synchronous posts and silent startup; bound pending input retention;
   make the cancellation test deterministic. Preserve old measurements as
   historical and append corrected evidence. Rerun the affected memory,
   multi-map, cancellation/failure and visual/interaction checks. Repeat timing
   controls/measurements if the changes affect scheduling or rendering claims.
   Preserve the disclosed RGBA limitation; do not turn coverage into identity.
6. Run required verification at meaningful corrected heads: focused parity
   and negative controls, Python 3.9, applicable lint/types, `./verificar.sh`
   or all disclosed components, and GitHub Python/Postgres/JS checks. For
   research include its prototype checks and applicable browser evidence.
   Keep developer, independent, CI and browser evidence clearly attributed.
7. Return separate handbacks with exact final heads, base/checkpoint,
   finding-by-finding disposition, changed-file summary, reproduction commands,
   results/skips, updated interfaces and remaining limitations. Stop for review.

Research acceptance does not block 1B corrections. No 2B/3B, merge, deployment,
provisioning, real data/account action or recurring check-in is authorized.
