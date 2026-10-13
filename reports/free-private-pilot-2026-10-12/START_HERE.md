# F0 — accelerated private pilot with no payment method

**Owner release, 12 October 2026:** the owner has explicitly authorized Team A, with B as support, to provision/configure free isolated test resources under owner-controlled accounts, create fictional accounts, deploy candidate `31b6a1d`, and execute the hosted/recovery tests. The [recorded authorization and exact scope](PRUEBA_ALOJADA_PARA_AUTORIZAR.md) supersede this packet's earlier hold on those operations only. No payment method, charges, real data, production changes or PR/main merge are authorized. Do not ask again for the same approved test operations.

**Current delivery agreement:** read [PLAN_DE_ENTREGA.md](../../PLAN_DE_ENTREGA.md) first for the owner's essential release gates, latest recorded A/B slices and deferred backlog. This F0 packet remains the technical implementation contract. Its initial status snapshot below predates draft PRs #31 and #32; neither an early slice nor green CI establishes combined hosted acceptance.

Supervisor decision, 12 October 2026. The owner now requires no payment method, no billing exposure, an initial 50–100 terrains, and concurrent work by the two external Claude teams. This packet supersedes the Vercel/AWS M1 implementation instructions at `718f4b76807f745fe5b1088a7950b0fbe090a660` when relayed. Preserve any implementation already made; reuse relevant pieces, but do not finish the superseded transfer design merely because it was assigned.

## Delivery decision

Target a **small private pilot**: the existing Python application and static frontend together on **Render Free**, existing application Postgres on **Neon Free**, and attachment bytes in **Supabase Free private Storage**. All browser requests remain same-origin through the Python application. Supabase is only the byte store: do not migrate the database, accounts, sessions, grants or geometry into it.

Keep the accepted raw whole-file PUT and whole-file verified download. Preserve 20 MiB KMZ and 25 MiB PDF limits. Reuse the existing parser, explicit selection/activation, widgets, table and renderer. There is no new chunk protocol, composition API, direct browser storage token, AWS OIDC/STS, custom signer, framework rewrite or cross-provider abstraction project in this packet. This reduces application changes; it is an engineering judgment, not a measured delivery-time guarantee.

Use the private portal, a fresh empty isolated database, managed accounts/resets, assigned bases, editing/filtering, PDF/KMZ and current-page boundary display. Public catalogues, self-service signup/reset email, historical-data migration, 1,000/25,000-record benchmarks, heap-slope research and unrelated polish are deferred. The 100-record scale is a pilot operating scope, not a new schema limit or permission shortcut. A must prove the actual route for loading records into the editable master table; the legacy import route must not be assumed to do that.

## Free capacity and availability are explicit

- Supabase documents 1 GB file storage, 5 GB uncached egress, a 50 MB per-file free-plan limit and pausing after one inactive week. Plan an initial **700 MB decimal working budget for all retained final files and histories**, leaving space for temporary/test objects. This is an operator budget, not a claim that the app has a new atomic quota engine. Inventory actual provider usage, including staging and unreferenced objects. The free account must have available quota. [Pricing](https://supabase.com/pricing)
- Terrain count does not establish file capacity. At the application's maximum sizes, 100 terrains with one KMZ and one PDF each require 4,718,592,000 bytes before history or staging. That does **not** fit this plan. Before importing real data, inventory the actual proposed files. Preserve per-file sizes; report an aggregate-capacity blocker rather than silently dropping attachments or promising unlimited free use.
- Render Free sleeps after 15 idle minutes and can take about a minute to wake. It has no persistent disk; never keep authoritative files or SQLite there. With no payment method, exhausted bandwidth can suspend services; unusual service-initiated traffic can also cause suspension. Render recommends paid compute for production. We are preparing a limited pilot with these disclosed availability limits, not an always-on service commitment. [Free services](https://render.com/docs/free)
- Keep Neon on a verified Free project with room for rows, geometry, history and traffic. Check its actual limits before launch. No paid trial, credits that convert to charges, payment method, automatic upgrade, paid disk, domain purchase, add-on or billing-backed R2/AWS account is authorized. If a provider demands a card at signup, report that specific blocker; do not substitute a paid plan.
- The client/business portal must not be assumed eligible for Vercel Hobby, which is restricted to personal/non-commercial use. The pilot's frontend is served by Render as well. [Vercel Hobby](https://vercel.com/docs/plans/hobby)

Provider pages were inspected on 12 October 2026. Free quotas and feature descriptions are not a substitute for testing the actual account and deployed candidate. Neon Object Storage's larger free allowance was considered, but its inspected [compatibility page](https://neon.com/docs/storage/s3-compatibility) did not establish the required create-only race behavior. This is a documentation gap, not a claim that Neon cannot support it. Do not start another provider survey; Supabase documents the duplicate-path concurrency behavior this adapter needs.

## Pins, preservation and authority

- Application baseline: `4670df7348265af66c640069e5ece2a274830fa3` (#29).
- Accepted batching: `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3` (#30), integrate once in A's new candidate after checking ancestry. It is completed work, not a new performance assignment.
- #28 at `b2ac9bd176043fc4b1625b13993f8f21407dc978` is already consumed. Do not merge it again. Preserve C1 `49b782d147591236cc7f311c7e0de1948ad5258e` and old #20–#30 branches/PRs.
- GitHub was checked for this packet: #29 and #30 remain at the pins above, draft; no new hosted implementation PR was visible. This does not establish whether either team has unpublished work.
- Teams work on different computers/accounts. Share published commits, PRs and handbacks through the owner. Never depend on the other team's local path, environment, credentials, chat or unpushed commit.
- Authorized now: implementation on new branches, isolated test dependencies, synthetic/local verification, branch publication and new draft PRs. A may perform ordinary local integration merges into its new candidate. No force push, GitHub PR/main merge, provisioning, account/secret changes, deployment or real-data import is released by this packet. Prepare an executable operator checklist and finish all independent code while resource access remains pending.

## One shared interface, separate ownership

| Item | Contract / owner |
| --- | --- |
| Store | B: `server/almacen_supabase.py`, implementing the existing `Almacen` contract |
| Factory | B: `fabrica_desde_entorno(environ) -> FabricaAlmacen | None`; pure construction, no provider I/O |
| Configuration | `ARA_MAP_ARCHIVOS_SUPABASE_URL`, `ARA_MAP_ARCHIVOS_SUPABASE_KEY`, `ARA_MAP_ARCHIVOS_SUPABASE_BUCKET` |
| Credentials | Server-only dedicated storage-project secret/service credential, never browser output or logs; bucket private, no anonymous read/write policies |
| SDK | B selects/tests a pinned official Python Storage SDK; A owns dependency declaration and deployment lock. Document any necessary bounded HTTP streaming through the provider's documented API. No invented SDK calls |
| App/storage boundary | Existing API routes, DTOs and `Almacen` methods; no new `componer`, `parte`, `desde`, transfer DTO or storage URL in the client |
| Runtime | A: new Render entry point, deployment manifest/configuration, dependencies, proxy/security tests, operator/onboarding documents |
| Lifecycle | B: minimal necessary changes in `server/archivos.py` and `server/api/archivos.py`; A reviews during integration |
| Verification/recovery | B: byte inventory/export/integrity tools and tests. A: consistent database backup, isolated restore instructions and combined acceptance |

No team edits the other team's branch. Within a team, agents have named file ownership or isolated worktrees and a lead integrator. A shared-file change needs one owner, not two simultaneous implementations.

## Storage and lifecycle requirements retained

1. Implement `guardar_temporal`, `copiar`, `leer`, `tamano_de`, `borrar`, `listar` with accepted key validation, atomic staging replacement, bounded reads, lazy pagination and create-only final writes. `copiar` may bounded-read a snapshot and upload it to a fresh final key with `upsert=false`. Do not emulate create-only using HEAD-then-overwrite. Supabase documents one winner for concurrent uploads without upsert; verify its actual error mapping. [Standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads), [Python upload](https://supabase.com/docs/reference/python/storage-from-upload)
2. For staging, validate/materialize the bounded input before publishing replacement bytes. Validation/pre-publication failure preserves the old staging object; a lost remote response is an uncertain outcome and must not be described as proof that the old object survived unchanged. Recovery rechecks state and complete bytes before retry/completion. A local temporary buffer/spooled file is disposable scratch only. Reads must enforce size/buffer bounds even when provider metadata is wrong; do not load an unlimited response through a convenience SDK method. Disable caching for staging reads and test overwrite followed by immediate completion. Do not assume CDN overwrite visibility.
3. Authorize the application session, capability, current resource scope and pending owner before provider access or a failing store resolution. Missing configuration must not break module import or unrelated portal/geometry routes. A new start must not create a pending row when the store is unconfigured. Keep idempotent replays valid. Pure configuration checks may run before insertion; provider I/O must remain outside database write locks.
4. Preserve existing deadlines (15-minute upload, 60-minute completion), 180-second lease, pending-slot policy, cancellation, activation revision checks, pending privacy and write reverification. Keep full size/SHA/signature validation and parser limits. Each download is authorized and fully verified before bytes are returned, with the current safe binary headers.
5. Track each final write attempt before I/O. On an uncertain response, retain the object or clean up only the attempt's own nonce after reliable proof it is unreferenced. Never delete a collision winner or reuse the final nonce. Failed reference checks mean retain; report cleanup pending. Do not implement a broad orphan sweep.
6. Distinguish application denials from provider/configuration/quota failures. Provider credential failures are safe storage 503s, not application 401/403; transient failures are retryable; unknown outcomes must not be automatically replayed as if they were confirmed failures. Full storage/paused provider must leave existing committed rows and geometry intact and expose a useful operator error. Do not automatically delete accepted history to make space.
7. Keep server credentials off the browser. No Supabase Auth migration, public bucket, direct public URL, or permissive storage policy. The server credential bypasses provider RLS; application authorization remains essential. [Access control](https://supabase.com/docs/guides/storage/security/access-control)

Supabase recommends resumable transfer above 6 MB, but its standard upload supports the required file sizes. Use the existing whole-file flow first and prove 20/25 MiB reliability through the real host; no new TUS/chunk work unless that proof exposes a blocker. Provider conformance and full-size hosted timing remain unproven today.

## Parallel delivery and short handoffs

Each team may run up to three focused agents if its Claude environment and current allowance support them; do not purchase capacity. Start implementation now. Agents receive the same pin/contract, separate files/worktrees and explicit tests. The team lead reviews and integrates every contribution.

| Track | First delivery | Work continuing at the same time |
| --- | --- | --- |
| B storage | Factory + adapter + contract tests, a fetchable commit | Lifecycle errors/retries; recovery tool |
| A hosting | Render entry/config with existing local/fake test store | Synthetic 100-row import/onboarding journey; backup instructions |
| A integration | Locally integrate B's first usable exact SHA after a focused review | B finishes focused fault tests and recovery work |

Aim to publish the first usable slice in the next working session. Publish early draft PRs after required checks, then additive commits. An early slice is provisional integration input, not final acceptance. Do not wait for polished reports or all subagents to finish before sharing a usable commit. Send an exact SHA and interface note through the owner; A never pulls an unspecified moving branch. Later B commits arrive through ordinary local merges, with no duplicated cherry-picks or rewritten shared history.

No fixed delivery promise is made. The next milestone is a combined, locally verified candidate ready for a free hosted smoke test. Code and runbooks must not sit idle awaiting accounts.

## Proportional acceptance and recovery

- Component changes: focused reproducer/contract tests, affected tests and normal required repository checks/CI before push. Run SQLite and disposable Postgres where service/lifecycle behavior changes; provider-only conformance does not require rerunning unrelated DB suites.
- Once on the combined candidate: the actual private login → assigned base → load 50–100 synthetic rows → edit/filter → KMZ upload/selection/activation → boundary without X/Y → PDF download flow. Confirm that the load reaches the intended editable master table, not only a legacy imported view.
- Actual hosted gate, after an explicit operator release: both full-size limits, >4 MiB transfer, invalid replacement retaining the old boundary, a second authorized session, forbidden account/scope, archive/revocation during completion, byte-identical download, and a near-limit KMZ completion within the lease and memory budget. Reuse unchanged parser/renderer research; do not repeat broad 25k/heap studies.
- Verify cold wake and redeployment with the same database/store; persisted bytes, geometry and history must survive. Measure peak process memory for one near-limit completion and a small bounded concurrency case. A fast laptop result does not prove the free host.
- Use an operator-held **logical database backup plus referenced immutable-file manifest and byte export**. Snapshot under a brief write freeze or another demonstrated consistent boundary. Verify every exported file's size/SHA. Incremental file export avoids rereading every immutable file daily and exhausting free egress. Keep the copy outside the ephemeral host and outside the sole live bucket. No paid PITR/versioning requirement for this pilot.
- Perform one restore drill into a fresh disposable target; verify rows, history, geometry and every referenced final file. Exclude/reset sessions, login-failure state and processing leases before access; pending rows keep their original deadlines and need safe cancel/restart if staging was not backed up. Report orphans, never delete them during verification. A provider metadata backup is not a backup of file bytes.
- Before real handover, identify the operator responsible for daily database/incremental-file backup and provider quota checks. First backup and restore must pass. Defer backup automation and high availability, not the ability to recover the pilot.
- Block release for unauthorized access, lost/corrupt data, broken required workflows, exhausted capacity or failed restoration. Record minor server-protected UI issues without reopening accepted phases.

Read the separate [Team A packet](TEAM_A.md) and [Team B packet](TEAM_B.md). They are ready to relay independently.

## Supervisor publication verification

The supervisor changes only these instructions and the older packet's supersession notice. Referenced commit objects and relative links were checked locally. The required `./verificar.sh` publication check is recorded in [the log](evidence/supervisor-prepush.log). These checks run on the supervisor branch; they do not test the proposed hosted application, Supabase adapter or a deployed pilot.
