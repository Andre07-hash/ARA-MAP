# ARA Map release before BigQuery

Current developer assignment: [supervisor next steps after the connector report](SUPERVISOR_NEXT_STEPS_2026-10-06.md). Read the [GitHub coordination protocol](COORDINATION.md) before submitting the next report. The [original completion instructions](SUPERVISOR_COMPLETION_INSTRUCTIONS_2026-10-06.md) are supporting context. The latest next steps govern; the infrastructure observations below remain historical evidence for their named commits.

Owner decisions confirmed October 6, 2026. This file supersedes the previous packet where its order or storage requirements differ.

## Required release

The current app must work online, and employees must connect an ordinary shared Excel workbook once, then click **Actualizar desde Excel** to see the latest saved cloud changes without re-uploading. Microsoft OneDrive/SharePoint is the selected provider. The owner has now supplied a company OneDrive for Business workbook; prioritize that account for real acceptance, retaining the existing personal-account support. A workbook stays owned by the account that hosts it. Sharing must give employees access to the same cloud workbook, not independent copies.

**Neon Postgres is the storage destination for this release. BigQuery is deferred until this release works and the owner proceeds with that migration.** Do not continue the old Stage 2 feature list independently.

## Verified infrastructure

- PR #1 is merged; automatic Git deployments are still disabled in main.
- PR #2 is merged at `5ea77f40f8b7a085cd67dd2180235a3aaf89a387`.
- GitHub `Andre07-hash/ARA-MAP` is connected to the existing Vercel `ara-map` project.
- Real Preview: https://ara-nygwebw37-aicore2.vercel.app
- Stable Preview alias: https://ara-map-preview-aicore2.vercel.app
- Deployment: `dpl_DUhaspKnS66Jy87WTKZXcZkDwvRC`, reviewed commit above.
- Neon project `tiny-salad-83614342`, schema-only branch `preview-ficticio` / `br-cool-boat-avwu9e7p`, endpoint `ep-wispy-feather-av1oxmt1`, database and role `ara_preview`.
- All 14 inherited tables were empty before seeding. The new database has schema 8 and only generated sample data.
- Preview gets only its own `DATABASE_URL` and `DATABASE_URL_UNPOOLED`. All 18 original integration values are Production-only and their values were compared unchanged. The Preview role does not exist in Production. No paid AI configuration in Preview.
- Automatic Neon branching was visibly unchecked in the integration settings. Do not enable it or reconnect the production integration to all environments.
- Hosted API smoke: **13 PASS, 0 FAIL**, including exact static asset hashes, sign-in, generated XLSX import, map data, saved map, export, inventory draft, two-session persistence and logout revocation.
- Production remains `dpl_3vsdvzhV86Y1goinejgcHP83vNML`, schema 7, 3 bases / 104 terrains / 2 saved maps. No production migration or deployment has happened.

Evidence: ../github-vercel-readiness-2026-10-05/preview/run-5ea77f4-mac-fresh-token/results.json and ISOLATION_MAC.txt. The earlier run failed at deployment protection because a pre-existing local environment file supplied an expired OIDC token; it performed no application writes. A freshly pulled development token fixed access without disabling protection.

## Remaining work, in order

1. Fix the hosted inventory-list failure discovered in the browser: Vercel injects a `path` rewrite parameter, which strict application query validation rejects. Add a cloud-adapter regression and an inventory-list hosted check. Finish browser verification and enable Git branch previews with `git.deploymentEnabled: {"main": false}`. Verify a branch push deploys exactly its commit against Preview. Keep automatic production deployments off.
2. Register the Microsoft application in a directory where registration is authorized. Company account sign-in succeeded, but Entra admin center returned access denied. A personal OneDrive workbook is supported by Graph, but does not remove the application's registration requirement. No registration has been created yet.
3. Implement server-side Microsoft OAuth, persistent file identity, encrypted credentials, source mapping and a required unique stable row ID. Connect once; Refresh must fetch saved file contents without uploading. Read-only file access; ARA Map must not write to the workbook.
4. Persist source versions, runs, terrain identity and active-version selection transactionally in Neon. Preserve the last good version on permission, parsing or network failure. Support added/updated/removed/unchanged counts, duplicate-ID rejection, reordering without identity changes, concurrent refresh handling and reconnect. Keep dated maps frozen; update the connected live map/table only after successful activation. Prevent website edits to Excel-owned fields on the server.
5. Verify a real OneDrive workbook before and after edits, with two employee sessions and the owner's computer off. Mock tests and ordinary upload tests do not establish connected Refresh acceptance.
6. Prepare production continuity: retain access to the existing public terrains, create actual employee accounts, rehearse migration and recovery using a privately held production backup, and plan a maintenance window. Then deploy the verified release, check the real site, and report completion.

The existing main has an empty public catalog and requires team sign-in for legacy bases/maps. It cannot replace today's public site unchanged. This is a release blocker, not permission to publish newly connected private records.

## Microsoft registration request

Create an app named **ARA Map Excel Connector** supporting personal Microsoft accounts and organizational accounts if both are required. Use the server authorization-code flow with PKCE. Configure Web callback URLs:

- `https://ara-map-preview-aicore2.vercel.app/api/microsoft/callback`
- `https://ara-map-ivory.vercel.app/api/microsoft/callback`

Start with delegated read access (`Files.Read` for a workbook owned by the connecting account) and `offline_access`; use `Files.Read.All` only if the chosen shared-file access path requires it. No file-write or application-wide unattended access is needed for the owner-connected first version. Match the exact permissions to the chosen Graph endpoints before consent. Tenant consent policies may still require an administrator for company accounts.

Store client credentials and a token-encryption key as server-only secrets. Keep client ID, account support and redirect URLs documented, but never commit tokens, client secrets, user passwords or preauthenticated file download URLs. The server must validate state, PKCE and callback/session binding and restrict Graph/download redirects to approved Microsoft endpoints. Use stable drive/item IDs and version information, not filenames or public anonymous links.

Official references:
- https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/security/zero-trust/develop/identity-supported-account-types
- https://support.microsoft.com/en-us/excel/get-started/share-your-excel-workbook-with-others
