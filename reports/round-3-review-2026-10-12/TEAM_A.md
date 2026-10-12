# Team A — preserve 3A, then integrate B's bounded corrections

Reviewed combined #29 head:
`0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db`.
Frozen C1/#27: `49b782d147591236cc7f311c7e0de1948ad5258e`.
Already consumed B/#28: `01d64541e929009ea2d149e3c6f5980805c76c73`.

Your original 3A scope is unchanged. Supervisor confirmed the exact B merge,
current green CI and independently reran the real combined 22/22 browser
journeys on macOS/Chrome 154. No separate A-owned blocker was established in
this review, but the combined tree inherits the B-client defects listed in
START_HERE.md. **This is not final Round 3 acceptance.**

## Now

Preserve #29 and its branch. Read this packet and B's five bounded findings.
You may prepare integration regressions, especially the real upload-404
scope-loss reproduction in `probe_upload_scope.mjs`. Do not duplicate B's
fixes or make speculative host changes. No new checkpoint and no change to
C1/#27 or accepted #20–#26. No 4A.

The immediate dependency is B's corrected **named green-CI head**, not another
general planning round. You may wait for it; no unrelated work is required.

## When B supplies the corrected candidate

1. Fetch, verify full SHA and exact-head CI, then ordinary `--no-ff` merge of
   that exact candidate into the existing
   `claude/team-a/application-integration` branch / draft #29. Record parents.
   Do not merge the GitHub PR or send your moving feature branch back into B.
2. Verify the real widget emits the existing scope-loss callback and the
   host clears row/detail/map/private filename on upload denial. The independent
   probe currently observes completion 404 with stale row/detail/name; the
   corrected combined tree must remove them and never repopulate from late work.
   Cover grant revoke and terrain transfer, plus same/different-account re-entry
   during explicit cancellation. No queued old write may run as the new user.
3. Rerun the actual combined local workflow with the corrected widgets,
   SQLite and the focused disposable-Postgres upload/reload/denial smoke.
   Preserve true same-database-and-store restart evidence. Include upload
   cancellation while closing/reopening details and final-digest scope loss.
4. Run the full combined repository checks at this integration boundary:
   SQLite/Postgres, Python floor, JS, lint/types and configured coverage gate;
   required pre-push checks and exact-head CI. Keep developer environment issues
   separate from actual product failures. Reuse unchanged 25k-record timing,
   renderer/research and screenshot evidence; don't rerun whole matrices merely
   because the branch changed. Repeat a bounded near-limit cleanup measurement
   only if needed to demonstrate changed pipeline/loader lifetimes.
5. Return #29's exact consumed B/code/final heads, additive diff and correction
   report with each new regression outcome. Stop for supervisory review.

If B needs a host-owned change, return/implement only the bounded request and
its regression on your branch. Do not reopen closed Round 1/2 decisions.

The summary-query batching request and unexplained bounded heap slope remain
documented follow-ups. Neither authorizes renderer work, E5 adoption, cloud
storage, schema changes, saved/live views, main/PR merge or deployment.
