# Round 3 — first complete local employee workflow

The owner requested the next assignments after review. **3A and 3B are now
released**, superseding earlier stop-before-3 statements. Read this packet at
the exact supervisor commit supplied by the owner, not a moving branch tip.

## Accepted inputs — do not redo earlier packets

| Input | Exact accepted head |
|---|---|
| 2A / #26 / editable grid + corrected shared dispatcher | `32a2a55e4a7417499cc384109bd44666e7a568cb` |
| 2B / #25 / attachment HTTP + corrected privacy tests | `bf4c6a694ca95087368bb2d89325d7a240a7b676` |
| Frozen Round 2 checkpoint / #24 | `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` |

See ACCEPTANCE_2A.md here and B's preceding closeout. #20–#26 stay unchanged;
preserve their branches and drafts. No research/Excel/deployment branch enters
the new tree. Schema stays 10 unless a concrete blocker is brought for review.

**Demo outcome:** an operator opens an assigned base, creates a terrain with
blank business fields, edits it, uploads a PDF and a KMZ, chooses a layout
when needed, and a second authorized session can read the stored files and
see the real boundary without XY. A no-grant account is denied. This is local
storage on one test machine, not durable cloud service or a public release.

## Reading path

Both teams read START_HERE.md and INTERFACES.md here, then their TEAM file.
Reuse, do not reread every historical report:

- At accepted #25: `reports/team-b-attachment-http-2026-10-09/API_CONTRACT.md`
  and `INTEGRATION_REQUESTS.md` (R-1–R-4 are now assigned to A; R-5/R-7 repairs
  already exist in accepted #26, not in #25's older dispatcher).
- At accepted #26: `web/components/tabla/ranuraArchivos.js` and relevant
  report sections in `reports/team-a-master-grid-2026-10-09/START_HERE.md`.
- Preserved domain/geometry contract: `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md`;
  transport/mount contract: `reports/round-2-instructions-2026-10-09/INTERFACES.md`
  at supervisor `13840c0deaf7f78f79609126115d03769e27fd0a`.
- Accepted lifecycle rules remain in the Round 1 ATTACHMENT_CONTRACT.md at
  supervisor `f3fd0f05c0ba9f28bd8b3e7321f374368027e784`.

## One early checkpoint, then parallel features

**A owns the shared prerequisite C1.** Create
`claude/integration/round-3-baseline` from accepted #26; merge accepted #25
with an ordinary non-fast-forward merge. Record both parents and the pure
composition head. Add only the small early 3A work defined in TEAM_A:
production route/binary/local-store mounting, read-only exemption, shared
private transport bridge and their integration tests. Thus C1 is explicitly
**not a baseline-only/no-code merge**. Do not put later grid/map work in C1.

Open a new draft checkpoint PR targeting `claude/integration/round-2-baseline`.
Run full combined checks and publish its exact green-CI head and manifest in
`reports/round-3-baseline-2026-10-09/START_HERE.md`. Then freeze that C1 head.
The packet authorizes using this tested development checkpoint before final
supervisory acceptance of all Round 3 work; it is not a main/PR merge approval.

- A branches **`claude/team-a/application-integration`** from C1, with a new
  draft PR targeting `claude/integration/round-3-baseline`.
- B branches **`claude/team-b/file-ui-geometry-client`** from accepted #25 now
  if C1 is not ready. Implement against the frozen seams with an isolated
  development harness. When A publishes C1, fetch and merge that **exact** head
  normally, record it, then test against the real mounted server. B's draft
  targets the Round 3 baseline when it exists; if publishing earlier, use #25's
  branch temporarily and document that temporary base. Do not create a second
  shared integration branch or wait for A's complete 3A feature.

Publish changed contracts or blocking shared-file requests as concise handoffs,
not competing edits. The owner relays messages between external accounts; do
not assume direct cross-session access. Include the repository, exact SHA,
path and requested action in each early handoff.

## Final integration without a circular dependency

B hands back a tested, exact-head 3B draft on C1, with real mounted API evidence
and a standalone widget harness. A can develop its host independently against
the seams in parallel. Once B names its green-CI delivery head, A merges that
**named candidate head** into A's new 3A feature branch for final integration
testing and records the consumed SHA. No rebase/force push of either team.
This controlled development-branch merge is authorized; it does not accept B's
candidate or merge either GitHub PR. B must not pull A's moving feature branch
back into its own feature to create a cyclic stack.

A's final handback must include the real end-to-end journey with B's actual
widgets, not placeholders. If B is not ready, A submits an explicitly partial
host checkpoint and waits for that artifact, not a false completed handback.
Supervisor independently reviews each delta and the final combined candidate.
Any corrections stay on their owning feature branch and propagate by recorded
ordinary merges of exact heads.

## Boundaries preserved

No cloud provider, deployment, real records/accounts, public file endpoints,
schema migration, renderer rewrite/E5 worker integration, saved views or new
snapshot behavior. Existing saved maps remain frozen. Round 4 governs full
filtered-map persistence and large/dense-map policy. For this first local
milestone the map preview is explicitly the **current bounded table page**,
with one selected boundary body loaded at a time; see INTERFACES. It must not
claim to show all 3,000/25,000 rows or all outlines.

Admin landing remains Inventario; operator navigation/grants and public
allowlists remain restrictive. X is latitude; Y is longitude. Unknown values
stay unknown; no currency/area conversions or derived prices. Attachment
changes never bump terrain cell versions or erase active editors.

Stop after the named Round 3 handbacks. No 4A/4B, GitHub PR/main merge, deploy,
provisioning, real-account changes or recurring monitoring is authorized.
