# Next assignments — P1 attachment schema and large-KMZ display investigation

These assignments replace the instruction to keep both teams idle after A-1 review. They are independently executable now. Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP).

| Team | Start now | Output |
|---|---|---|
| A | [P1 attachment prerequisite migration](TEAM_A_P1.md), stacked on accepted A-1 | Draft implementation PR with tested SQLite/Postgres schema and exact dependency commit |
| B | [Bounded large-KMZ display investigation](TEAM_B_DISPLAY.md), using accepted B-2 | Reproducible benchmarks, isolated prototypes and a recommended display strategy in a separate draft PR |

A builds the next dependency on the attachment critical path. B resolves the already recorded large-multipart rendering requirement while A works; this is a bounded investigation, not a new product feature or permission to rewrite the accepted renderer.

## Fixed inputs

At issue, `origin/main` remains `09452fd26d38319567dce28a89db100ea61c739a`.

- A-1, PR #14: `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`, accepted schema 9.
- B-1, PR #9: `efc362818ba64618dbfc23556db8678cde525336`, accepted parser.
- B-2, PR #11: `5d8e2dcc125a688dbba38a260d5d7eca88a6d223`, accepted renderer.
- B attachment proposal, PR #12: `28bf0dbbf718571e35d501a7810d7e7d882ee3dd`; use §9 refinements over conflicting earlier text.
- B-3S, PR #13: `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53`, accepted local/fake storage core.

Read this supplied instruction commit using `git show`; do not switch to, merge, or develop on the supervisor's documentation branch. Fetch and report current main and dependency SHAs. An existing accepted PR need not merge before a explicitly stacked draft or an isolated benchmark can use its exact commit. Do not update another team's branch or rewrite shared history.

## Scope and ownership

P1 freezes only the persistence requirements described in TEAM_A_P1.md. It does not freeze the whole PR #12 API proposal or silently resolve D1–D5. Provider choice, final file limits, single-candidate activation policy, batch failure semantics and credential lifetimes do not prevent these two assignments. No provider or credentials are needed.

Schema/auth/routes/shared app adapters remain A-owned. Geometry/rendering experiments remain B-owned. Neither team changes the parked Excel work, CI or deployment configuration. No merge, deployment, provisioning, real account change or production database operation is authorized.

## Next dependency handoff

1. A returns P1's exact PR/head and concrete schema map. Supervisor reviews it against the constraints below; no additional preparation-only report is required before A starts implementation.
2. The next parallel implementation pair is A-2/P2 authorization and B's attachment repository/state-machine work, once their shared transaction interface and remaining relevant policy defaults are frozen. B must not invent a permissive authorization substitute to get ahead. Registration of HTTP handlers still follows those handlers, not the schema.
3. B's display investigation returns independently. It does not gate A's P1 or the attachment schema review. A later renderer implementation packet uses its evidence; do not turn an unsuccessful prototype into a production fallback without review.

The supervisor owns contract consolidation and issuance of subsequent packets. Neither team is expected to guess that work or repeatedly ask the owner for another assignment. Return at the explicit checkpoints; the owner can send these two packets at the same time.
