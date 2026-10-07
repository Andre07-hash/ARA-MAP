# GitHub handoff for both Claude Code teams

Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP).

Instruction branch: `codex/supervisor-completion-brief`.

Documentation PR: [#5](https://github.com/Andre07-hash/ARA-MAP/pull/5). Its scope has been updated to the owner's master-table direction; the older Excel-first instructions on this branch are preserved as superseded history.

The supervisor supplies an exact instruction commit in the handoff message. Both teams must read that same commit, even if the documentation PR is still open. These files are repository documents, not paths on the supervisor's Mac.

## Read order

Read the repository's `AGENTS.md` and `CLAUDE.md` on the current application baseline as well. Their development/security rules remain applicable. Where older domain descriptions say MXN-only prices, composite name-based terrain identity, or that only X/Y can locate a terrain, the owner's newer master-table requirements govern: retain explicit/unknown currency, stable record IDs, and usable KMZ geometry without X/Y. Do not apply legacy importer identity rules to the new master record. The two Claude teams use the `claude/` branch prefix.

1. `reports/workspace-contract-2026-10-07/START_HERE.md`
2. `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md`
3. Your current packet: `reports/workspace-contract-2026-10-07/TEAM_A_PACKET.md` or `TEAM_B_PACKET.md` in that same directory.
4. The linked fictional interface example, master plan v2 and delivery plan for scope/ownership.

You can read the immutable GitHub links supplied by the supervisor. If using a repository clone, fetch the instruction branch without changing your checkout:

```bash
git fetch origin codex/supervisor-completion-brief
```

Then use `git show <instruction-commit>:<repository-path>` for each document. Substitute the real full commit supplied in the handoff. Do not invent a SHA or use a supervisor desktop path. If no exact commit was supplied, resolve the fetched instruction branch's tip and report the SHA you read before relying on it.

Do not switch branches over uncommitted work or merge unrelated application changes just to read instructions. The application baseline is a separate choice established in the kickoff audit; the instruction commit is not automatically the implementation starting point.

## Current assignment and return

Preparation is complete. The owner approved the work-base proposal with the supervisor's adjustments on October 7. Team A starts **A-1 schema foundation** while Team B starts **B-2 boundary renderer**, using the current packets above. Do not repeat kickoff preparation or treat the historical B-2 hold as current.

Return a draft PR naming the instruction SHA, application baseline, implementation/head SHA, report path, evidence and shared-change requests. Both teams stop at their packet's review checkpoint; later packages, merges and production operations are not authorized by this publication.

Each later handoff must use a GitHub PR/branch and exact commit. Changes that exist only in a local clone have not been delivered to the other team.

## Current packet and historical reviews

- [B-3S storage review and contract follow-up](../team-b-storage-review-2026-10-07/START_HERE.md): PR #13 at `2f4ec1d` needs S1/S2 corrections, independently of Team A. PR #12 at `28bf0db` answers the four design refinements; full contract consolidation remains pending.

- [Attachment proposal review and B-3S storage-core packet](../team-b-attachments-review-2026-10-07/START_HERE.md): PR #12 reviewed at `ba3ad38`. B may build the standalone local/fake storage core and refine the proposal while A continues. The attachment repository/API still await the consolidated contract and A's prerequisites.

- [B-2 acceptance at `5d8e2dc`](../team-b-b2-review-2026-10-07/ACCEPTANCE.md): F1/F2 closed. Team B may prepare the documentation-only attachment contract in the linked next packet; B-3 implementation remains unreleased. Team A A-1 is unchanged.

- [Team B B-2 review and correction packet, October 7](../team-b-b2-review-2026-10-07/START_HERE.md): historical corrections at PR #11 head `db0b679`, now closed by the acceptance above; B-3 implementation remains unreleased. Team A A-1 continues unchanged.

- [Approved shared contract and A-1/B-2 packets, October 7](../workspace-contract-2026-10-07/START_HERE.md): current authority for parallel implementation.

- [Team B B-1 acceptance, October 7](../team-b-b1-review-2026-10-07/ACCEPTANCE.md): accepted at PR #9 head `efc3628`, all F1–F3 findings closed. No additional B-1 correction is requested. Earlier reviews remain preserved. Its B-2 hold described the state at that review and is superseded by the approved packet above.
- [Team B preparation review and B-1 parser packet, October 7](../team-b-review-2026-10-07/REVIEW_AND_NEXT_PACKET.md): accepts preparation at PR #8's reviewed commit and authorizes only the isolated parser/tests while shared-contract consolidation remains pending. This is historical preparation/parser scope. Read this packet at the exact new instruction commit supplied by the supervisor.
