# Round 2 — released instructions 2A and 2B

Repository: **Andre07-hash/ARA-MAP**. This packet releases the next pair in the
existing twelve-packet plan. It does not restart Round 1 or authorize main
merges, deployments, cloud resources, real accounts/data or later packets.

Read this file, your TEAM file and [INTERFACES.md](INTERFACES.md). The existing
[attachment contract](../round-1-instructions-2026-10-08/ATTACHMENT_CONTRACT.md)
and [product contract](../workspace-contract-2026-10-07/SHARED_CONTRACT.md)
remain binding except for the explicit refinements here. Read the latest
correction sections, not every historical report.

## Accepted inputs — keep these pins

Verified from GitHub for this release on 2026-10-09. Main remains
`09452fd26d38319567dce28a89db100ea61c739a`.

| Input | Exact accepted head | Use |
|---|---|---|
| Prerequisite baseline, #20 | `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb` | Frozen base; includes P2/parser/store/E1 |
| A record backend, #22 | `1ef2238766eae3e111c031b4fa24f9d849ef4753` | Accepted 1A, A1–A3 closed |
| B lifecycle, #23 | `a9dc8af8cc511bde0a67168da335398353b80aa6` | Accepted local/fake 1B, L1–L6 closed |
| B research, #21 | `5e9ed42ef740fcee881c54e011172fae9c6f209b` | Research only; **do not merge into application** |
| Supervisor Round 1 closeout | `55ac1104f790747fd39a23c859216bdb360f21e5` | Acceptance evidence; not an application dependency |

Fetch and record observed heads. An unrelated new commit is not a replacement
for an accepted pin. Preserve #20–#23 and their branches; new work gets new
branches/PRs. No force push, rewriting accepted commits or retargeting old PRs.

## Parallel checkpoint protocol

1. **A owns assembly first.** Create `claude/integration/round-2-baseline`
   from accepted #22, then normally merge the exact accepted #23. #20 is
   already their common prerequisite; do not reassemble its component PRs.
   Publish a **baseline-only draft PR targeting
   `claude/integration/round-1-baseline`**. Do not update #20 itself.
2. Record both source heads, resulting head, conflict resolutions and tests in
   `reports/round-2-baseline-2026-10-09/START_HERE.md`. Run the full combined
   suite with disposable Postgres, Python 3.9, JS and applicable lint/types.
   Include a focused composition test: actual 1A-created terrain → actual 1B
   attachment → cell edit → transfer/revoke → authorized/denied attachment
   replay/read, with immutable references and independent version counters.
   This may be a test-only addition, not new routes/UI/domain behavior.
3. Publish this exact-head checkpoint and green CI **before substantive 2A**.
   A can then branch `claude/team-a/master-grid` from that recorded head and
   target the new baseline branch. A need not await review of its later grid.
   Contract-changing integration repairs require supervisor review before use;
   never silently change auth/schema or B's lifecycle to make tests pass.
4. **B can start now.** If the checkpoint is not yet published and green,
   create `claude/team-b/attachment-http` at accepted #23. Implement B-owned
   handlers/tests there. No wait for A's grid, new custom-column APIs or an
   additional research review. No competing integration branch.
5. Once A's manifest and exact-head CI are available, B normally merges that
   **recorded exact checkpoint**, not A's moving 2A feature tip. B's separate
   draft PR ultimately targets `claude/integration/round-2-baseline`. If opened
   earlier, temporarily target B's lifecycle branch and document the stack;
   retarget only the new 2B PR when the baseline is ready. Final 2B handback
   requires verification on the combined checkpoint.
6. Freeze the checkpoint after publication. Any necessary additive repair has
   a new manifest/CI head and explicit propagation to both feature branches.
   Do not turn it into a rolling feature-integration branch. No GitHub merge
   button or main merge is authorized: the ordinary branch assembly above is
   the only integration assigned here.

## Ownership and round boundary

- A: terrain/base/custom-column backend, schema if separately reviewed,
  authorization integration, route registry, shared API/store/router and shell,
  editable table and base/grant UI. Small shell wiring for a usable table is
  part of 2A; attachment/location/widget integration remains 3A.
- B: attachment HTTP handlers, attachment/geometry read support, dedicated
  HTTP/geometry tests and documented registration/transport requests. B does
  not edit `server/app.py`, `server/router.py`, auth, schema, shared config,
  terrain DTOs, frontend or renderer in 2B.
- Shared-file needs are explicit requests with a reproducer and contract.
  Routine handler registration/binary response mounting is **3A**, as planned.
  2B uses the isolated test harness described in TEAM_B.md, not an unreviewed
  production dispatcher patch. Both teams can progress independently.

No files from parked Excel, hosted deployment or memory-research branches enter
the new application checkpoint. No E5 integration or new memory investigation.

## Handback and verification economy

Run focused affected checks while iterating; full checks at the combined
checkpoint and feature handback, and `./verificar.sh` before pushes as required
by repository instructions. If zsh is absent, run each component explicitly
and disclose it. Preserve failures and explain environmental differences; CI
is not a substitute for the relevant authorization/race/browser tests.

Each team returns: instruction commit, source/checkpoint/code/final heads,
separate draft PR, changed-file scope, frozen interfaces/examples, exact-head
CI, independent types of evidence (SQLite/PG/Python floor/browser), limits and
specific remaining work. Synthetic data and disposable databases only.
Stop for supervisory review. Do not begin 3A/3B, merge or deploy.
