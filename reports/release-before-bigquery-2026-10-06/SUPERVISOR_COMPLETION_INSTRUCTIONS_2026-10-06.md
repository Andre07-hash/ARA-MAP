# Supervisor instructions: complete ARA Map before BigQuery

Issued October 6, 2026. Give this entire document to the lead AI developer. It reviews `DEVELOPER_STATUS_2026-10-06.md` at `33c8526`, the schema draft `8d7c8f1`, and PR #4 at `077b4e0`. This is a planning and review decision, not a claim that the draft has been tested or approved for migration.

## 1. Decision and scope

Continue, with the corrections below. The general direction is accepted: Microsoft OAuth, a persistent workbook connection, stable row IDs, Excel as the authority for connected fields, Neon as the shared store, and existing map/table/export components. Do not restart the application or resume the unrelated Stage 2 roadmap.

The release is complete only when the production app works, an ordinary shared OneDrive workbook is connected once, and an employee can refresh saved changes without selecting or uploading the file again. The owner's computer must not be required. Existing terrains, saved maps, ordinary uploads, and employee access must survive. BigQuery is a later release.

Personal OneDrive is an accepted initial source. Work-account OneDrive should use the same supported connector. Do not advertise arbitrary SharePoint or shared-link support unless its access path and permissions are implemented and verified. Record any remaining SharePoint coverage explicitly; do not quietly substitute a public download link for a private Microsoft connection.

The supervisor reviews plans and evidence and reports to the owner. The lead developer coordinates implementation and returns one consolidated report. The owner should not have to resolve technical design questions already settled here. A developer/operator with access to the required cloud services performs hosted operations. Do not assign implementation, credential handling, or deployment execution back to the supervisor.

## 2. Answers to the three pending questions

**A. OAuth callback: approved with the controls below.** Add only the exact `GET /api/microsoft/callback` route to the anonymous allowlist. The connection-start endpoint requires an active ARA Map team session and the existing origin protections. The callback is a narrowly scoped OAuth response handler, not an anonymous workspace API. Keep the ordinary session cookie `SameSite=Strict`.

Use a server-generated unpredictable state, a short expiry, PKCE S256, and a separate short-lived Secure/HttpOnly/SameSite=Lax browser-flow cookie. Use the authorization-code flow's GET/query response mode to match that cookie policy. Bind the pending flow to the original server-side team session and user. Check state and browser binding, atomically claim the pending flow once, and verify that the original session and account are still valid before attaching credentials. Recheck session validity at final attachment if token exchange takes place outside the database transaction. Invalid, missing, expired, reused, revoked-session, or wrong-browser flows must attach nothing.

Do not accept a user ID, connection owner, callback URL, tenant authority, or destination URL from callback query fields as authoritative. Handle cancellation safely, clear the flow cookie, redirect to a fixed same-origin application page, and remove the authorization code from the visible URL. Use no-store and an appropriate referrer policy on the callback. Avoid logging callback codes, state values, cookies, tokens, or preauthenticated URLs. If an ID token is used for identity, validate it with a maintained implementation; decoding its payload is not validation. Otherwise derive the connected account from the authenticated Graph response and do not rely on an unvalidated ID token.

**B. Web-first connector: approved for this release.** The connected workbook feature can require the hosted Postgres application. Preserve all existing local SQLite features, uploads, and tests. The local UI must accurately state when the cloud connector is unavailable; it must not offer a broken connection flow. This is an intentional release scope choice, not a reason to damage the local app.

`pgcrypto` is acceptable subject to the credential and recovery requirements in section 5. There is no blanket product requirement in this supervisor brief to avoid maintained dependencies at the expense of correctness. Do not invent cryptography or weaken OAuth just to keep the dependency count unchanged. If a maintained library is needed, document its exact purpose and packaging impact in the PR.

**C. Account ownership: approved.** The workbook owner connects their Microsoft account once. Authenticated ARA Map team members may refresh that designated connection without each completing Microsoft OAuth. They edit the same workbook through its existing OneDrive sharing permissions. This is delegated access through the owner's grant, not proof that every ARA Map user individually has Microsoft file permission. Clearly state this behavior in setup, record who connected the account, and audit who initiated each refresh. Do not change the existing equal-capability team model or silently grant anonymous access. Employees must never receive the owner's Microsoft tokens.

**D. Deleted Excel rows: approved for removal from the live view, not destruction of history.** After a complete, validated refresh, absent stable IDs disappear from the live base/map/table/export. Keep their prior values and logical identity in immutable version history. Dated saved maps remain frozen. Removing and later reintroducing the same stable ID must not become an unrelated logical terrain. Deletion does not mean sold or withdrawn unless the workbook explicitly says so. An unexpectedly empty workbook requires a review state and an explicit confirmation tied to the exact candidate version before activating an empty source. Fetch/permission/parser failures are never interpreted as a valid empty file.

These decisions unblock design and local implementation. Do not wait for another general go-ahead.

## 3. Current verified status and release boundaries

- PR #3 is merged as `5cbf6718c1fc84deaec660ac69c433a68bd63d77`. Its head `550643e` passed Python/Postgres and JavaScript CI.
- PR #4 is draft at `077b4e0f1c184b2c2ef6d1c63ebb80381a113316`. GitHub Actions now also shows both checks passing. Update the report: CI is no longer merely a local claim.
- Vercel still reports `Deployment was blocked` for that commit. Its cause is unconfirmed. Do not report an author-membership hypothesis as the diagnosed cause.
- The 13/13 hosted result belongs to `5ea77f4`. It establishes the tested flows on that build, not completeness of Preview and not validation of `077b4e0`, schema 9, or connected Excel. The inventory browser failure was found afterward and is precisely why another hosted check was added.
- The actual existing Preview has an isolated Neon branch/database/role, verified in the recorded Mac evidence. That evidence is a baseline, not a perpetual guarantee about later variables or deployment environments.
- `8d7c8f1` is an untested schema draft. Update the status document's obsolete “nothing committed” statement. No schema-9 readiness or production approval follows from committing it.

Before every hosted test, verify its exact commit, project, target, effective database connection, and absence of production overrides. Keep Production values, credentials, domains, and data outside disposable tests. Continue using generated records and a designated test workbook in Preview.

## 4. Correct the schema before dependent implementation

The current draft is not sufficient as the persistence contract. Replace or amend it before merging or migrating anything.

| Finding in `8d7c8f1` | Required correction | Evidence required |
|---|---|---|
| `excel_version` contains hashes, tags, counts and timestamps, but no historical row payload or reference to durable row versions. | Store an immutable normalized row snapshot or immutable row revisions sufficient to reconstruct every retained source version, including removed rows. Metadata alone is not history. | Reconstruct version 1 after several edits/deletions and compare its complete normalized content. |
| `excel_fila.terreno_id` cascades on terrain deletion. | Preserve a durable source-ID registry/tombstone independent of deleting a live terrain row. A removed ID must remain identifiable and reconnect to its original logical identity when reintroduced. | Add, delete, re-add an ID; show retained identity and previous values. |
| Source deletion cascades through versions and runs; the source itself cascades on base deletion. | Protect connected bases from generic deletion that destroys source history. Use explicit disconnect/archive semantics that preserve retained data and dated maps. Define any later permanent deletion separately. | Generic base delete cannot bypass the source lifecycle; disconnect/reconnect does not erase history. |
| Runs lack an idempotency key and request fingerprint. | Persist a source-scoped operation key and fingerprint with uniqueness. Same key/same request returns the recorded result; same key/different request conflicts. Include source creation so a retry cannot leave duplicate bases or connections. | Repeat lost-response requests before and after commit; verify one logical operation and no duplicate base/version. |
| A partial unique index prevents two currently active rows, but does not fence an expired worker. | Add an active run ID/generation or equivalent compare-and-swap fence, expected source/configuration version, and durable lease/expiry. Activation must verify ownership atomically. | Worker A expires, B completes, then A returns: A must not overwrite B or change B's run status. |
| Only four run states exist. | Represent review-required, expired/interrupted and conflict outcomes explicitly, either as states or unambiguous structured results. Include last checked, last successful refresh and latest failure separately. | UI can distinguish old usable data, no-change success, review, reconnect and failed work. |
| There is no versioned interpretation identity. | Store configuration version/fingerprint: file identity, sheet/table, stable-ID mapping, currency mapping, parser/normalization version. A mapping change must reprocess even when bytes/tags are unchanged. | Same bytes with changed mapping produce the correct new interpretation; an identical refresh is a no-op. |
| Account linkage is a bare text ID while all account rows are excluded from content backups. | Preserve non-secret account/source metadata and restore it in an explicit reconnect-required state. Split credentials from metadata if useful. Avoid dangling links and undocumented repair-by-SQL. Scope Microsoft account identity appropriately; email is not an identity key. | Restore a content backup and reconnect through the UI while retaining source IDs, versions and mappings. |

Add constraints or transaction-level checks that an active version belongs to its source and that a run/version link cannot cross sources. Require valid non-negative counts and supported state transitions. Do not solve referential integrity by silently deleting dependent history. Decide and document whether one workbook can have multiple connected sheets; the present `(drive_id, item_id)` uniqueness permits only one. A single selected sheet per workbook is an acceptable initial limit if enforced clearly and changing sheets is treated as a reviewed configuration change.

The backing legacy base can remain the materialized live view. Keep it stable, update it atomically, and retain the source-version authority elsewhere. Do not create another ordinary base on every refresh. Add a test demonstrating that a partially applied materialization rolls back completely.

Keep this persistence layer provider-independent enough to support the later BigQuery migration, but do not build BigQuery adapters now.

## 5. Microsoft permissions, credentials and restore behavior

The proposed `/shares` link-resolution flow is incompatible with the selected least-privilege scope. Microsoft's current `shares-get` documentation lists delegated `Files.ReadWrite` as the least permission for both personal and work accounts. Downloading an owned drive item supports `Files.Read`.

For the first release, select the owner's workbook using the owner's OneDrive file/folder picker or another documented read-only lookup. Persist stable `driveId` and `itemId`. Remove the `/shares` promise from the first implementation unless a read-only path is independently proven. Do not silently add write permissions to make link pasting work. If SharePoint or another person's shared file requires a different read scope, document and review that exact endpoint/scope separately. Personal OneDrive does not eliminate app registration.

Use authorization-code OAuth with PKCE and `offline_access`. Use `User.Read` only for the account-identity functionality that requires it; explain other requested OIDC scopes. The registration's supported account types must match the chosen authority. Resolve access through the connecting account's grant; never send arbitrary supplied URLs to an authenticated HTTP client.

For downloaded content: authenticate only to fixed Microsoft Graph endpoints, obtain fresh provider-issued download URLs server-side, validate each redirect/hop, require HTTPS, and never forward the Graph bearer token to a download host. Use a carefully scoped Microsoft download-host policy, not a loose string-suffix test. Enforce request timeouts, response size, total redirect count, expanded ZIP size and workbook/row bounds. Handle 429/Retry-After and transient errors within a bounded retry budget. Never persist or return preauthenticated download URLs. Preserve a safe user-facing link to the workbook separately, validating its scheme/host before rendering it.

`pgcrypto` requirements:

- Use its supported PGP symmetric encryption functions, not raw home-made encryption. Encode ciphertext explicitly if storing it in TEXT, or use an appropriate binary type with tested backup serialization.
- Keep the encryption key in server-only deployment secrets, independent between Preview and Production and outside the database. Require encrypted database transport. Do not put keys/tokens in SQL literals, command arguments, logs, exceptions or report artifacts; use bound parameters and review database error/logging behavior as well as application logging.
- Document that the database server participates in encryption and therefore receives plaintext/key material for these operations. This protects stored values, not against a trusted database administrator seeing data during execution.
- Store a key version or implement an explicit tested reconnect-on-key-change policy. Never silently generate a new key at process startup.
- Serialize credential refresh per connected Microsoft account across sources/workers, persist replacement refresh tokens correctly, and avoid stale token writes. Do not hold the application's workspace-wide transaction lock while calling Microsoft.
- Missing/invalid encryption configuration must disable connector operations safely, not break existing map/login/export behavior or store plaintext fallback credentials.
- Verify extension availability on the actual disposable Neon target using the intended migration role. No request handler may install extensions or run migrations. Review whether mandatory extension creation would unnecessarily prevent upgrading a deployment where the connector is disabled.

Correct the backup claim. Excluding tables from `postgres.TABLES` affects the application's content backup; it does not automatically exclude them from `pg_dump` or Neon recovery snapshots. Distinguish:

1. **Content export/restore:** excludes live sessions, pending OAuth flows and usable connector credentials; retains sufficient non-secret connection identity and shows reconnect required.
2. **Private disaster-recovery backup:** may include encrypted credentials and operational tables; remains restricted outside Git and reports. Before a restored environment serves requests, apply the documented session/OAuth invalidation and credential/reconnection policy. Never clone production credentials/data into ordinary Preview as a shortcut.

Test both paths. A “restore requires reconnecting” statement must be true for the actual restore command used, not only one helper.

## 6. Refresh execution and user behavior

Use brief database transactions to create/claim runs and to activate completed candidates. Fetch, download and parse outside the existing Postgres session's global advisory lock. Verify this specifically: the current wrapper serializes workspace sessions, so leaving it open around network calls can block unrelated employees.

A refresh must have a durable recorded outcome. Choose either a bounded synchronous request with durable run/lease recovery, or a real durable background execution mechanism. If returning 202, document exactly what continues executing after the HTTP request ends. An untracked Python thread on Vercel is not an acceptable worker. If a request/worker dies, the old version remains readable and a later request safely identifies interruption and permits a fenced retry. Do not claim unattended completion if the design only recovers on a later request.

Read a complete, consistent workbook version. If the file changes during download/parse, detect a changed provider revision and retry within limits or report a retryable conflict. Never activate a mixed version. A changed raw file hash caused only by workbook packaging or row order should not create business changes. Compare normalized records by the exact stable ID; preserve text IDs and leading zeros, and do not silently case-fold or coerce them into numbers. Reject duplicate/missing IDs with row-specific diagnostics. Document treatment of blank rows, formulas/cached values, merged headers and unsupported structures. Do not infer an ID from row position or terrain name.

Keep currency explicit, including an honest unknown state where supported; never silently relabel old prices. Preserve the application's latitude/longitude conventions. Block activation on partial parse failure or missing required fields, so rejected rows cannot masquerade as deletions.

The source DTO/API contract must include safe source identity, live base ID, mapping/configuration version, active data version, connection state, latest run, last checked time, last successful refresh time, result counts and safe error/retry information. Document endpoints before frontend integration. Setup must show the chosen workbook/sheet/ID mapping and a validation preview before activating live data. Source creation and refresh mutations need authenticated team access, origin checks and idempotency.

Audit every applicable write path to a connected base. Block adding/appending/editing Excel-owned values and destructive generic actions on the server, not just disabled buttons. Ordinary unconnected bases retain their behavior. A source may be renamed/organized locally only where that is clearly application metadata and does not pretend to write into Excel.

The UI must support: connect; choose workbook; review sheet/ID/currency; initial import; open the live map/table; refresh; actual counts/status; reconnect; interrupted run recovery after reload; and retained last-good data on failure. Explain that Refresh reads saved cloud changes, not unsaved desktop edits. Show workbook owner/connection state without exposing tokens. On successful activation, invalidate live data caches and update map/table/filter/export consistently. Dated saved maps must not refresh automatically. Prevent double clicks, but still enforce concurrency on the server. No simulated progress percentages.

## 7. Work order and ownership

The lead developer may divide work across its team, but owns integration and a single consolidated response. The supervisor will not launch agents or make application changes on the lead's behalf.

**Track A — deployment readiness, first release gate.** Keep PR #4 draft until evidence is complete. A cloud-enabled operator must inspect the actual Vercel failure reason. Do not change author identity to impersonate a team member, disable deployment protection, or upgrade a paid plan without the owner's decision. If account linking/membership is required, report the specific supported action and have an authorized account holder perform it. A successful manual CLI Preview may validate the application but does not prove Git-triggered deployment.

Observe the actual non-sensitive rewrite parameter shape on Vercel, with a safe diagnostic that excludes cookies, codes and secrets. Do not broaden query normalization speculatively by joining arbitrary duplicate parameters. Handle the observed transport form narrowly and retain invalid-filter/authentication tests. Obtain a READY Git-triggered Preview at the reviewed SHA, run the expanded smoke test including inventory listing, and verify the inventory page in the browser. Confirm main remains excluded from automatic production deployments. Publish sanitized deployment/commit evidence and recheck database isolation.

**Track B — corrected persistence and refresh core.** Amend the untested schema draft with section 4, write migrations and local/Postgres tests, then implement transactional activation, ID mapping and recovery. Open a draft PR as soon as there is reviewable tested work. Do not merge an untested schema bump or couple unrelated changes to PR #4. Use the actual current main as the base; record dependencies clearly.

**Track C — provider, OAuth and UI.** Implement against the agreed API contract using local fixtures while registration is unavailable. Complete the callback and credential tests, owner-file picker, and Spanish user workflow. Keep provider and token operations behind testable boundaries. Test fixtures must not create a production option for arbitrary OAuth/Graph/download hosts.

**Track D — real account and release verification.** Assign a developer/operator whose environment can reach Vercel, Neon and Microsoft. Network restrictions in one container do not become a supervisor coding assignment. The operator registers/configures the application in a directory where they have permission, or provides an exact registration request for an authorized account holder. Use the existing stable Preview callback URL and verify it is routed to the intended candidate. Keep secrets out of the report; return only identifiers, allowed redirects/scopes and completion evidence. If no operator has access, deliver all independent local work and a concise list of the exact remaining access actions; do not stop the whole team over the already answered design questions.

## 8. Required acceptance evidence

Run the full relevant Python and JavaScript suites at the final integrated SHA, including disposable Postgres and existing SQLite regressions. Verify target-relevant behavior on PostgreSQL 18/Neon as well as any older version retained in CI. Existing 673/98 counts belong to PR #4; do not recycle them as schema-9 evidence.

| Scenario | Required observation |
|---|---|
| First connection | Personal OneDrive sign-in, owner file selection, validated setup, initial version, live map/table/export; no anonymous connection access. |
| Normal saved edit | Another employee edits the same workbook; Refresh updates the expected fields and reports correct counts. No upload/file reselection or new duplicate base. |
| Stable identity | Reorder, insert before an existing row, change a terrain name, remove and re-add its ID; logical identity and history remain correct. |
| No change | Repeated refresh and reordered-only data report unchanged business records and no duplicate business version. Last checked time advances. |
| Invalid input | Missing/duplicate ID, missing required name, malformed file, unsupported currency/mapping, oversized/ZIP-expanded workbook: no partial activation; actionable safe diagnostics. |
| Empty candidate | Old data stays active, review is required, confirmation binds to the same candidate, and an approved empty version activates atomically. |
| External failures | Revoked grant, deleted/moved file, expired token, 429, 5xx and timeout preserve old data and show the appropriate reconnect/retry action. No raw token/provider URL leakage. |
| Changed interpretation | Same file content with changed sheet/mapping/currency/parser configuration is re-evaluated; no stale conditional-download shortcut. |
| Request replay | Lost response, double click, retry with same key, conflicting payload under same key: recorded result or clear conflict, never duplicate source/version. |
| Concurrency | Two users refresh simultaneously; stale worker returns after a newer run; token refresh races across two sources under one account. Only valid ownership can activate. |
| Process/browser failure | Reload/close browser or terminate the worker; run state is durable; old data remains; recovery is bounded and the UI does not spin forever. |
| File changes mid-refresh | Candidate is pinned to a coherent provider version or safely retried/rejected. |
| Frozen saved maps | Values, row membership and snapshot identity stay unchanged after every connected refresh. |
| Server write restrictions | Direct API calls cannot append/edit Excel-owned terrain fields or delete history through generic base actions. Ordinary uploads still work. |
| OAuth defenses | Wrong/missing/expired/reused state, missing/wrong flow cookie, session logout/deactivation during flow, concurrent callback replay and account switch all behave safely. |
| Recovery | Restore content without usable credentials and reconnect through UI; restore private DR backup with documented invalidation; retain source identity/history. |
| Independence from Mac | Real hosted Refresh completes from another device while the owner's Mac is off. Neon remains the durable store. |

Label results explicitly: local fixture, local real Postgres, hosted synthetic workbook, and real Microsoft account/workbook. Attach the exact commit and sanitized test results to each category. Screen recordings/screenshots should omit credentials and unrelated personal files.

## 9. Production continuity and release procedure

Keep today's anonymous browsing behavior for the records and fields already public. Prepare a narrowly scoped continuity implementation and a record/field comparison against the old site. Do not make all legacy/connected routes public or publish new private Excel records as a shortcut. If existing public membership/fields cannot be established from the live baseline, return the specific proposed public manifest and unresolved business decision; do not ask the owner a vague architectural question or block unrelated work. This is a compatibility requirement, not authorization to resume the full old publication feature roadmap.

Update the rehearsal for the actual release. The current script contains schema-8 wording, tests that all Git deployments are off, and expects an empty public catalog. Those checks are no longer the final desired release contract. Preserve historical evidence and create new results for schema 7 to 9, schema 8 to 9, fresh 9, repeated migration, connected-source history, content restore/reconnect, and rollback to the old code. Add schema-specific checks, not only equality to a moving SCHEMA_VERSION constant. Derive expected production counts from the fresh backup rather than hardcoding the historical 3/104/2 baseline if production has changed.

Use a private, verified real-production backup restored into an isolated recovery environment outside Git, with compatible Postgres dump/restore tools and explicit target variables. Test recovery end to end. The in-database content backup is not by itself a complete migration rollback. Record hashes, row/field comparisons, commands with redacted targets, migration logs and recovery duration. Never commit the backup or real row payloads.

Prepare real employee account provisioning and secure credential delivery. Employees do not need shell access to a production machine. Account names and delivery method need owner input; developers must prepare the mechanism first. Confirm existing staff can sign in and that new private sources remain private.

Replace immediate `vercel deploy --prod` promotion with a staged production deployment using the reviewed release commit and production configuration, without assigning the public domain (`--prod --skip-domain` or an equivalent supported staged flow). A staged deployment still has production credentials: it is not a disposable test destination. Do not run the destructive/generated-data Preview smoke against it.

The release packet must specify a verified server-enforced write freeze, including old deployment URLs and in-flight refreshes, before the final backup/migration. Keep writes frozen through staging checks and the rollback decision. Take the final private backup, migrate through the explicit-target script, provision accounts through the approved mechanism, validate the staged build with authorized non-destructive checks, then promote only after the release gate is approved. Confirm production OAuth uses the production callback and credentials, not Preview's. Plan final OAuth/callback verification on the real domain explicitly; staging-host tests cannot prove that callback alone.

Rollback is a rehearsed combination of a matching database restore and the previous deployment. Do not restore schema 7 while the new code can receive traffic, or run the old code against an incompatible schema. Define the maintenance routing sequence, restore target, validation and promotion commands. A maintenance window without an enforced freeze does not prevent lost writes. After writes reopen, do not blindly restore an older dump: stop new writes, preserve/reconcile intervening changes, and obtain a specific recovery decision.

Return the release packet to the supervisor for review and an owner-facing release decision before replacing production. This instruction authorizes development and verification work; it is not authorization for an unreviewed production cutover.

## 10. Required next report

Return one consolidated `COMPLETION_RESPONSE.md` with:

1. The reviewed branch/PR/SHA for each deliverable and the actual integrated release SHA.
2. Decisions implemented from this brief, and any proposed deviation with its concrete reason and impact.
3. Schema diff, version-history/identity strategy, run/idempotency/lease contract, and transaction boundaries.
4. OAuth endpoints, account types, exact Graph scopes, credential encryption/rotation and restore policy. No secrets.
5. Local and hosted evidence kept separate; CI links, Preview URL/deployment ID, exact SHA, isolation verification, browser outcome and real OneDrive before/after proof.
6. Remaining access actions assigned to an authorized operator, with the exact requested action. Do not label all of them “supervisor to implement.”
7. Production compatibility comparison, migration/recovery evidence, employee provisioning method, staged release and write-freeze plan.
8. A checklist of each acceptance scenario above: passed, failed or blocked, with evidence. No “done” label while required scenarios remain unverified.

The next checkpoint is a corrected and tested schema/core plus PR #4 hosted evidence (or an exact diagnosed access block), not another request to approve the same three design questions. Continue independent provider/UI work while those tracks run.

## References checked during this review

- [Developer report](https://github.com/Andre07-hash/ARA-MAP/blob/33c852637725908ab5b03516bbe6016717f7d51e/reports/release-before-bigquery-2026-10-06/DEVELOPER_STATUS_2026-10-06.md)
- [Schema draft](https://github.com/Andre07-hash/ARA-MAP/commit/8d7c8f1ff7f9e04d9141ba293f19a20e10e3f216)
- [PR #4](https://github.com/Andre07-hash/ARA-MAP/pull/4)
- [Microsoft shared-item permissions](https://learn.microsoft.com/en-us/graph/api/shares-get?view=graph-rest-1.0)
- [Microsoft drive-item downloads](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Microsoft authorization-code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [PostgreSQL pgcrypto security limitations](https://www.postgresql.org/docs/current/pgcrypto.html#PGCRYPTO-SECURITY-LIMITATIONS)
- [Vercel staged deployments](https://vercel.com/docs/cli/deploying-from-cli)

