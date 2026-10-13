# Round 1 — released instructions 1A and 1B

Owner requested the first pair after the twelve-packet plan. These are implementation assignments for **Andre07-hash/ARA-MAP**, not approval to merge or deploy. Read these documents through GitHub or `git show`; no desktop checkout or private supervisor artifact is required.

- Team A: [TEAM_A.md](TEAM_A.md) — combined prerequisite baseline, then scoped terrain-record backend.
- Team B: [TEAM_B.md](TEAM_B.md) — attachment lifecycle core after handing back the current memory investigation.
- Both: [ATTACHMENT_CONTRACT.md](ATTACHMENT_CONTRACT.md).
- Corrected P2 acceptance: [P2_ACCEPTANCE.md](P2_ACCEPTANCE.md).
- Overall sequence remains [the twelve-packet plan](../execution-status-2026-10-08/REPORT.md). This releases only 1A/1B, not subsequent rounds.

## Exact inputs

Fetch first. The observed `origin/main` is `09452fd26d38319567dce28a89db100ea61c739a`. If main or an input PR has changed, report the new SHA and assess the difference; do not silently replace the pins below.

| Component | Exact accepted commit | PR |
|---|---|---|
| A-1 schema 9 | `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9` | #14 |
| P1 schema 10 | `edf9bcd1dc51e74a627d54d5ce01d37113206055` | #15, includes A-1 |
| Corrected A-2/P2 | `5d0844cfd678c2f7ec55ddb4b364275482d1a801` | #17, includes P1/A-1 |
| B-1 parser | `efc362818ba64618dbfc23556db8678cde525336` | #9 |
| B-3S storage | `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53` | #13 |
| B-2 + E1 drawing | `eed9a4cb404406b8b261803c38947e8297a5edec` | #19, includes #11 at `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` |
| Attachment design source | `28bf0dbbf718571e35d501a7810d7e7d882ee3dd` | #12; amendments here override it |

No feature from Excel #6, deployment #4, research #16 or the current memory prototype enters the combined application baseline. Read relevant research as context only. Keep those branches and all reviewed heads stable.

## Parallel branch and handoff protocol

1. **A owns assembly.** Create `claude/integration/round-1-baseline` at the exact P2 head. Merge, in order, the pinned parser, storage and E1 heads into this new branch with ordinary commits. Do not merge A-1/P1/B-2 twice; they are already ancestors. This explicit stacked assignment supersedes the generic start-from-main instruction. Preserve source history; never force-push another branch.
2. A runs combined verification and publishes a **baseline-only draft PR targeting main**, with `reports/round-1-baseline-2026-10-08/START_HERE.md`, exact source manifest, combined head, CI links and any conflict resolutions. Publish this checkpoint before starting the substantive record feature. It need not wait for a review of the later record feature.
3. A creates `claude/team-a/master-record-backend` from that checkpoint, with its own draft PR targeting `claude/integration/round-1-baseline`. Keep the baseline branch stable after publishing; any necessary repair is an additive commit explicitly recorded in the manifest and propagated to both teams.
4. **B can begin immediately after its current handback.** If A's checkpoint is available, branch `claude/team-b/attachment-lifecycle` from its recorded exact head. If not, start from pinned P2 and merge the pinned parser and storage heads in the same order; begin domain work and fixtures. This is a temporary preparation base, not a competing integration PR. Once A publishes the checkpoint, merge that exact head normally into B's branch and target B's draft PR to `claude/integration/round-1-baseline`. Do not include A's in-progress record-feature branch.
5. B discovers the checkpoint by fetching that named branch and reading its manifest/PR, not by assuming its moving tip is approved. B need not wait for all of 1A, new terrain routes, the table, a provider, administrator identities or acceptance of its display research. Existing schema fixtures and real fictional sessions suffice for 1B.
6. A may continue record APIs and B may continue lifecycle work against this development checkpoint once its combined tests/CI pass. A changed auth/schema/storage/parser contract or a failing combined prerequisite requires a narrowly scoped correction and supervisory review; it is not permission to redesign another team's module. Component acceptance and a development checkpoint do not authorize a main merge.

## Ownership

A owns schema, auth/transaction helpers, route registration, terrain/base repositories and rules, shared configuration and eventual application shell. B owns new attachment repository/service modules and their new dedicated tests. A only brings in B's pinned modules as integration dependencies; it does not refactor them. B does not edit A's files, migrate schema or create authorization substitutes. Request a precise shared-file change with its failing fixture if needed; continue independent work.

Both teams can add their own report folders and test modules. Do not rewrite shared test fixtures or `tests/e2e/README.md` concurrently. No UI or new attachment HTTP route is implemented in this pair. Existing terrain routes may be extended by A as specified in its packet.

## Required handback

Each report names instruction commit, fetched main, prerequisite checkpoint, implementation and final PR head; changed files and scope; SQLite/Python 3.9/disposable-Postgres/JS results and exact CI head; runnable fictional examples; unresolved findings and precisely what remains for the next packet. Run `./verificar.sh` before push; where zsh is genuinely unavailable, execute each component explicitly and disclose the omission. Run applicable lint/type checks. Never hide failures behind a generic green claim.

Use only disposable databases and fictional accounts/files. Keep secrets and real company data out of GitHub. No main merge, deployment, provisioning, real account change, destructive purge, provider purchase or automatically scheduled check is assigned. Stop for supervisory review of the completed packet. These instructions do not send messages to either external coder account.
