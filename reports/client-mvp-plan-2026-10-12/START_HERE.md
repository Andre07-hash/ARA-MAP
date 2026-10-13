# ARA MAP — ASAP private client MVP

**Superseded planning snapshot:** the current [delivery agreement and backlog](../../PLAN_DE_ENTREGA.md) and [F0 technical packet](../free-private-pilot-2026-10-12/START_HERE.md) take precedence. The Vercel hosting choice and pending component reviews recorded below are historical; do not restart those assignments from this document.

Planning update, 12 October 2026. Owner confirms **ASAP** and **private portal first**.
Supervisor: planning and independent review; external Claude Code teams implement.
This report changes priorities, preserves accepted work, and does not release an implementation packet or authorize external operations.

**Later review update, 14:55 America/Mexico_City:** A's R3-A2 residual is now independently accepted at `4670df7`; the pending-A-review status in the original snapshot below is historical. See [acceptance and focused evidence](../team-a-r3a2-residual-review-2026-10-12/START_HERE.md). B's #30 review and hosted readiness remain separate.

**Later owner/review update, approximately 15:03:** KMZ is explicitly mandatory for deployment. B's R3-A1 is now independently accepted at `bc7e421`; the pending-#30-review snapshot below is historical. See [acceptance and KMZ deployment packet](../team-b-r3a1-review-kmz-priority-2026-10-12/START_HERE.md). B's next milestone prioritizes durable private KMZ files and the actual hosted upload/activation/boundary/persistence/recovery flow; no additional batching is requested. Hosting decisions and external-operation approvals remain pending.

**Latest owner decisions:** keep Vercel with full-size transfers; preserve 20 MiB KMZ / 25 MiB PDF; fresh empty isolated portal; operator-managed accounts/password resets. [Hosted route decision and current A/B design instructions](../hosted-readiness-decision-2026-10-12/START_HERE.md) supersede the generic readiness briefs and pending architecture choices here. Provider/resource/cost approval and external operations remain pending.

## Delivery decision

Deliver the existing administrator/operator workflow as a dependable hosted private portal. Do not wait for the historical six-round roadmap.

Day-one scope: individual accounts, assigned bases, blank terrain creation, editing/filtering, PDF/KMZ upload and permitted download, boundary display, persistent records and files, and a tested recovery procedure. Preserve UUIDs, versions, history, role policy, null values and accepted file lifecycle semantics.

Disclose that the map shows the current page. Advanced saved views, new frozen snapshots, large-map research, public catalogues per base, Excel reconnection, BigQuery and minor polish follow the pilot. Preserve existing saved maps and existing public-route restrictions; private-first does not authorize removal of existing behavior.

ASAP is a priority, not a committed date. Establish a handover date after the exact candidate, hosting route, operator access and recovery rehearsal are known. Ask teams for remaining effort and concrete dependencies, rather than deriving a date from packet counts.

## Verified state

GitHub read through authenticated CLI/API on 12 October 2026, approximately 14:48–14:51 America/Mexico_City (20:48–20:51 UTC). Local supervisor checkout is `63b363a6e2553121d0db43d9e9981ea397905887` on `codex/supervisor-completion-brief`.

| Item | Exact version | Disposition / next owner |
|---|---|---|
| [A / draft #29](https://github.com/Andre07-hash/ARA-MAP/pull/29) | `4670df7348265af66c640069e5ece2a274830fa3` | R3-A2 residual correction delivered; independent review pending. Both CI jobs successful in [run 38305224940](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38305224940). Supervisor reviews next. |
| [B / draft #28](https://github.com/Andre07-hash/ARA-MAP/pull/28) | `b2ac9bd176043fc4b1625b13993f8f21407dc978` | R3-B1–B5 accepted; preserve unchanged. Already consumed by A through ordinary merge `e795935c7aebedce8b1e58a6ba87cf8ef396fafe`. |
| [B batching / draft #30](https://github.com/Andre07-hash/ARA-MAP/pull/30) | `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3` | Newly delivered R3-A1, not independently accepted. Branch `claude/team-b/file-summary-batching`, based on `41d029c54848a7aebb1d46dfd053848ccf265afc`, targets A's integration branch. JavaScript green; Python/disposable Postgres still running when checked in [run 38306147799](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38306147799). |
| [Frozen C1 / draft #27](https://github.com/Andre07-hash/ARA-MAP/pull/27) | `49b782d147591236cc7f311c7e0de1948ad5258e` | Preserve frozen. |
| [Hosted adapter / draft #4](https://github.com/Andre07-hash/ARA-MAP/pull/4) | `077b4e0f1c184b2c2ef6d1c63ebb80381a113316` | Unchanged; GitHub Vercel status remains failure, “Deployment was blocked.” It is not hosted MVP evidence. |

A's delta from reviewed `41d029c` changes one application file, `web/components/tabla/Tabla.js`, plus a journey and report/evidence. `filaEditable()` now includes the terrain's own base permission through `puedeCambiarFila(t)`. This addresses the reported cause in the master table by source inspection. A reports archived-base rows refusing new editors, preserved pending text and permitted PDF reads, active/unassigned rows still saving, and restore restoring editability. These are developer claims until independently reproduced; this planning report does not accept R3-A2 or the combined application.

B's #30 touches only the summary service/repository, the allowed read-only authorization helper, tests and report. B reports a 200-row handler decreasing from 1,611 to 18 statements on synthetic SQLite/Postgres. Timings and equivalence are developer evidence, not hosted proof. Do not reissue this assignment or expand it into packet 4B.

## Shortest safe sequence

| Step | Owner | Deliverable / exit condition |
|---|---|---|
| 1. Close current review | Supervisor | Focused R3-A2 residual reproduction on A's exact head, with pending text, readable files and active-row controls. Separately review #30's authorization equivalence, bounded SQL, projection and focused tests, plus exact-head CI. Reuse unchanged accepted evidence. |
| 2. Prepare hosting and storage in parallel | A and B | A returns hosted-adapter/configuration/onboarding inventory; B returns private-storage/recovery inventory. Use the planning briefs here. No new feature implementation or external mutations are released by these briefs. |
| 3. Choose and authorize the pilot environment | Owner, supported by supervisor | One concrete plan names provider/project, isolated database and file namespace, costs, operator and access method, account identities, backup schedule, recovery objectives and permitted actions. Supervisor then releases bounded implementation packets with exact starting pins and file ownership. |
| 4. Build the hosted candidate | A: application integration; B: storage/recovery | Reviewable local/draft changes, accepted component pins, migration/configuration procedure and operator runbook. A integrates B only after a named acceptance and explicit integration instruction. Deployment configuration belongs in a dedicated PR. |
| 5. Rehearse on an authorized isolated host | Authorized operator; A/B support; supervisor reviews | One exact deployed candidate passes the focused hosted matrix below, including database-plus-file restoration. Use synthetic accounts/data. |
| 6. Handover | Owner authorizes; operator executes | Approved release/cutover, approved individual accounts and grants, client smoke test, short Spanish guide, support contact and recovery owner. Any real-data import requires separate explicit authorization. |

Review A and B's existing deliveries before asking them to fix hypothetical issues. R3-A2 is currently a server-protected UI defect; classify any residual proportionally. Block delivery for unauthorized access, data loss, broken core workflows or unsafe persistence. Do not automatically block for minor stale UI that the server safely rejects.

#30 is a useful bounded improvement, not the hosted-readiness critical path. If it is accepted promptly, propose one ordinary integration on A's preserved branch. If review uncovers material issues, keep it separate and assess actual hosted performance before making it a pilot gate. A must not duplicate B's batching implementation.

## Ownership and integration boundaries

- **A:** application shell, hosted adapter, shared configuration, authentication wiring, migration/account tooling and onboarding; coordinates the combined candidate.
- **B:** private file backend, file lifecycle/provider integration and file recovery. Its #30 allowance in `server/auth.py` stays confined to the read helper; no broader auth-policy or lock work.
- **Shared boundary:** A injects/configures the store; B preserves the accepted storage/service interfaces and gives A the required configuration names and integration steps. B requests any shared dispatcher/auth/schema change; A owns and schedules it. Serialize shared-file edits after #30 review.
- **Supervisor:** exact-version ledger, focused independent acceptance, final hosted review and owner-facing release recommendation. Does not write application code.
- **Authorized operator:** approved cloud resources, secrets, migrations, deployments, accounts and restore operations. Branch isolation does not isolate databases or files.

Do not prescribe new branches from main for this stacked work. Later packet pins and target branches are issued after current review. Preserve #28, #29, #30 and C1 history; no resets, rebases, force pushes or duplicate checkpoints.

## Hosted acceptance matrix

Run once at the meaningful hosted integration boundary, against a recorded candidate SHA, deployment ID/URL, runtime, isolated database and file namespace. Expand only for a new failure or changed boundary.

| Case | Evidence required |
|---|---|
| Authorized work | Admin sets up bases/grants; operator sees assigned active bases; blank create, edit, filter, PDF/KMZ workflow and boundary display succeed from a second device/session with the owner's Mac off. |
| Denied access | Unassigned operator and cross-account direct API/file requests are denied; transfer/revocation/session loss removes private state; archived objects obey the existing policy. |
| Concurrent edits | Two sessions create a version conflict; both values remain available for explicit resolution. A file event preserves unsaved terrain text. |
| Upload and failure | Exercise representative accepted file sizes, a failed replacement preserving the prior file/boundary, interrupted completion and safe retry. Verify actual hosted transfer paths and adapter limits. |
| Durability | Restart/redeploy/reconnect retains IDs, data, versions/history, PDF/KMZ bytes and active boundary. Confirm no dependence on one process or temporary local disk. |
| Recovery | Restore database and corresponding private file set into a fresh isolated target; compare fixture IDs, versions/history, file hashes and active geometry. Login/grants and denied-access checks still pass. Document restore time and achievable data-loss window. |
| Operational ownership | A named person can access backups, perform the tested restore and support login/grants. Client gets the URL, account access through a secure channel, current-page map limitation and short workflow guide. |

Source inspection identifies a concrete hosted question: the candidate's `api/index.py` declares a 4 MiB body limit, while accepted attachment limits are PDF 25 MiB/KMZ 20 MiB. Determine which upload paths actually use that limit and verify runtime compatibility before selecting the final transfer route. This is an integration question, not a measured platform limit or proof that every attachment upload currently fails.

The candidate's `server/almacen.py` implements local and in-memory stores. Their accepted interfaces are reusable; they do not demonstrate a durable hosted private file backend. Database backups alone are insufficient proof of recoverable attachments.

Recovery must preserve the newer role policy. An older role-ignorant deployment is not an accepted rollback. Re-promotion alone does not prove the restored database/files are connected correctly.

## Decisions and authorization still needed

Private-first and ASAP are settled. The remaining approval dossier must name the hosted route/provider and access/costs, isolated resource identities, administrator/operator identities and base grants, backup frequency/retention and recovery targets. Confirm whether first use starts empty or needs a separately authorized source-data import.

No PR merge, main merge, deployment, provisioning, real-data import or account change is authorized by this plan. The owner has authorized planning; preparation can proceed read-only. Request approval only against the resulting concrete operation plan, not an open-ended request to “set up hosting.”

## Team briefs and evidence

- [Team A planning brief](TEAM_A.md)
- [Team B planning brief](TEAM_B.md)
- [A residual report](https://github.com/Andre07-hash/ARA-MAP/blob/4670df7348265af66c640069e5ece2a274830fa3/reports/team-a-application-integration-2026-10-09/START_HERE.md), §9.
- [B batching report](https://github.com/Andre07-hash/ARA-MAP/blob/bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3/reports/team-b-file-summary-batching-2026-10-12/START_HERE.md).
- Supervisor handoff and correction packet at `63b363a` remain historical evidence; the owner's pasted brief and private-first/ASAP answers supersede conflicting waiting/roadmap priorities.

This is a local supervisor planning artifact. No application code, team branch, cloud environment or local synthetic preview was changed. The unrelated untracked `reports/project-review-2026-10-06/` was left untouched. No test suite ran for this documentation-only update.
