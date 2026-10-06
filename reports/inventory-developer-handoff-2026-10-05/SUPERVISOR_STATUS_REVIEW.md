# Supervisor status review after developer interruption

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

**Current implementation instructions:** [Excel + BigQuery developer packet](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). The owner has asked to proceed with this plan. Assignments, shared contract, company setup inputs and acceptance criteria are ready; no developer dispatch or software completion is claimed by this notice.

> **Priority changed after the owners’ meeting (October 5, 2026).** Read [Excel + BigQuery realignment](../product-plan-2026-10-05/EXCEL_BIGQUERY_REALIGNMENT.md) first. Connected Excel refresh and company BigQuery storage now come before all further inventory/public-catalog work. The earlier website-authoritative assumption, spreadsheet-sync deferral and database-provider restriction below are superseded. Preserve completed work; do not resume Stage 2 from this historical plan. This notice changes priorities only; no connector, migration or deployment is complete.

October 5, 2026. Read-only source/evidence review; no application launch, migration, account creation, test rerun or deployment performed.

For a new developer session, start with `CLAUDE_RESUME_HERE.md` in this directory. This status report explains the stopping point; the restart brief supplies the read order, current assignment, execution boundaries and required outputs.

## Current assessment

Stage 1 has a documented acceptance backed by saved independent verification evidence. It is a development milestone, not acceptance of the whole product. Stage 2 assignments have been issued, but no delivered Stage 2 implementation or acceptance report is present in the reviewed workspace.

## Evidence checked

- Read developer responses, VERIFICATION_RESPONSE.md, DISPATCH_STATUS.md, STAGE2_ASSIGNMENTS.md and updated INTEGRATION_DECISIONS.md.
- Recomputed all 113 entries in verification/runs/CANDIDATE_MANIFEST_stage1_final.sha256: zero changed or missing files. This confirms the listed candidate files still match the verifier's snapshot; it does not rerun behavioral tests or certify arbitrary unlisted files.
- Five saved API result files report zero failures, 757 or 760 passes each, two warnings and five skips each. These are Stage 1 scenarios, not full-product acceptance.
- Browser results contain 90 PASS, one WARN, one N/A and two INFO. The warning is the recorded history-dialog focus defect.
- Current server/api/inventario.py still explicitly implements empty public-list and 404 public-detail placeholders. The router has no publish/unpublish/archive/restore/preview endpoints. No BACKEND_RESPONSE_STAGE2.md, FRONTEND_RESPONSE_STAGE2.md or VERIFICATION_RESPONSE_STAGE2.md was found.
- Read the actual datos/ara_map.db with SQLite mode=ro: schema version 4, no team_user table. The original local database has not been upgraded to the new inventory schema or provisioned with individual accounts. A normal launch would invoke migration; it was not launched during this review.

## What is complete versus pending

Completed Stage 1 scope: individual equal-access sign-in, master draft create/edit/read, stable identity, history, save conflicts, repeat-create handling and integrated internal UI, supported by the reported independent tests. Legacy anonymous reads were also tested as denied. Public inventory with records, publication transitions and preview were explicitly outside Stage 1 acceptance.

Next: execute STAGE2_ASSIGNMENTS.md against the current preserved candidate, resolve the carried-over login-throttle/error/focus issues, and independently verify publication, public browsing and private-data boundaries. Do not treat the earlier statement that agents were working as proof of current activity or delivered output.

Then Stage 3: reviewed Excel additions/adoption into the master inventory, duplicate review and attention UI. Retain the recorded requirement that adopted records with unknown currency remain editable without guessing currency. Finally: full migration/recovery rehearsal, actual-user setup, pilot and reviewed release.

The v7→v8 synthetic legacy checks do not by themselves establish a complete rehearsal for the owner's actual local schema-v4 database. Exercise that path on a separate copy before recommending normal use of the launcher. Preserve original data and explicitly distinguish the local database from the cloud database.

No deployment is recorded in this development handoff; current live production was not inspected in this review. Detailed client search parameters and the future AI search agent remain deferred.
