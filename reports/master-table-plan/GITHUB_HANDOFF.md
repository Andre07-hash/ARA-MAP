# GitHub handoff for both Claude Code teams

Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP).

Instruction branch: `codex/supervisor-completion-brief`.

Documentation PR: [#5](https://github.com/Andre07-hash/ARA-MAP/pull/5). Its scope has been updated to the owner's master-table direction; the older Excel-first instructions on this branch are preserved as superseded history.

The supervisor supplies an exact instruction commit in the handoff message. Both teams must read that same commit, even if the documentation PR is still open. These files are repository documents, not paths on the supervisor's Mac.

## Read order

Read the repository's `AGENTS.md` and `CLAUDE.md` on the current application baseline as well. Their development/security rules remain applicable. Where older domain descriptions say MXN-only prices, composite name-based terrain identity, or that only X/Y can locate a terrain, the owner's newer master-table requirements govern: retain explicit/unknown currency, stable record IDs, and usable KMZ geometry without X/Y. Do not apply legacy importer identity rules to the new master record. The two Claude teams use the `claude/` branch prefix.

1. `reports/master-table-plan/MASTER_PLAN.md`
2. `reports/master-table-plan/TWO_TEAM_DELIVERY_PLAN.md`
3. Your team's brief:
   - Team A: `reports/master-table-plan/TEAM_A_START_HERE.md`
   - Team B: `reports/master-table-plan/TEAM_B_START_HERE.md`

You can read the immutable GitHub links supplied by the supervisor. If using a repository clone, fetch the instruction branch without changing your checkout:

```bash
git fetch origin codex/supervisor-completion-brief
```

Then use `git show <instruction-commit>:<repository-path>` for each document. Substitute the real full commit supplied in the handoff. Do not invent a SHA or use a supervisor desktop path. If no exact commit was supplied, resolve the fetched instruction branch's tip and report the SHA you read before relying on it.

Do not switch branches over uncommitted work or merge unrelated application changes just to read instructions. The application baseline is a separate choice established in the kickoff audit; the instruction commit is not automatically the implementation starting point.

## First assignment and return

Execute the first preparation assignment in your own brief. Both teams may begin simultaneously. Return a preparation report in your own branch/draft PR, naming the instruction SHA, application baseline SHA, report path, findings, proposed contract, dependencies, and next action. Clearly identify any disposable experiments and their evidence.

The supervisor reviews both reports, consolidates the shared contract, and issues the first bounded implementation packets. Neither team should revive the paused Excel connector, deploy production, or implement unresolved shared contracts from an obsolete handoff.

Each later handoff must use a GitHub PR/branch and exact commit. Changes that exist only in a local clone have not been delivered to the other team.

## Follow-up packets

- [Team B B-1 acceptance, October 7](../team-b-b1-review-2026-10-07/ACCEPTANCE.md): accepted at PR #9 head `efc3628`, all F1–F3 findings closed. No additional B-1 correction is requested. Earlier reviews remain preserved. B-2 awaits the shared contract and Team A's preparation assignment is unchanged.
- [Team B preparation review and B-1 parser packet, October 7](../team-b-review-2026-10-07/REVIEW_AND_NEXT_PACKET.md): accepts preparation at PR #8's reviewed commit and authorizes only the isolated parser/tests while shared-contract consolidation remains pending. Team A's preparation assignment is unchanged. Read this packet at the exact new instruction commit supplied by the supervisor.
