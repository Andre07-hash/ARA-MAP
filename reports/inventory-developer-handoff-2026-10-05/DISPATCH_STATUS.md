# Developer coordination status

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

**Current implementation instructions:** [Excel + BigQuery developer packet](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). The owner has asked to proceed with this plan. Assignments, shared contract, company setup inputs and acceptance criteria are ready; no developer dispatch or software completion is claimed by this notice.

> **Priority changed after the owners’ meeting (October 5, 2026).** Read [Excel + BigQuery realignment](../product-plan-2026-10-05/EXCEL_BIGQUERY_REALIGNMENT.md) first. Connected Excel refresh and company BigQuery storage now come before all further inventory/public-catalog work. The earlier website-authoritative assumption, spreadsheet-sync deferral and database-provider restriction below are superseded. Preserve completed work; do not resume Stage 2 from this historical plan. This notice changes priorities only; no connector, migration or deployment is complete.

October 5, 2026. Scope of this task: create and communicate implementation instructions as requested by the owner. This status distinguishes completed briefing work from software implementation.

| Workstream | Assignment communicated | Outcome |
|---|---|---|
| Backend specialist | Inspect actual database/auth/API/import paths and prepare a concrete build packet | BACKEND_PACKET.md delivered; public-route hazards and migration dependencies identified |
| Interface specialist | Inspect actual UI/state/API code and prepare component/workflow assignments | FRONTEND_PACKET.md delivered; anonymous loading, private extras and mobile controls addressed |
| Independent verifier | Inspect actual source/tests and define acceptance/release evidence | ACCEPTANCE_MATRIX.md delivered; no runtime pass claims made |
| Supervisor | Resolve contract disagreements and define priorities/dependencies | START_HERE.md, INTEGRATION_DECISIONS.md and DEVELOPER_PROMPTS.md delivered |

The supervisor sent the reconciled integration contract back to all three specialists. All three completed their consistency review and updated their packets. Final small clarifications (preview publication timestamp and geographic multiselect serialization) are resolved in INTEGRATION_DECISIONS.md. Their assignment for this turn was documentation, not source implementation. Ready-to-send implementation prompts are in DEVELOPER_PROMPTS.md and intentionally begin with a bounded Stage 1 handoff.

## Scope decisions resolved during coordination

- One equal signed-in user type; no role hierarchy or managerial approval.
- Private legacy workspace routes and a distinct public catalog allowlist.
- Public content derived from a selected immutable revision; no separate duplicated publication table required.
- Individual attribution, version-checked saves/publication and safe retry of creates/imports.
- Inventory bulk additions/skips only; preserve existing legacy base update workflows internally.
- Public price-on-request representation and explicit currency semantics.
- Complete map/table pagination coverage, including an additional 251-row verification case.
- No deployment of intermediate stages with only half of the public/authentication flow implemented.

## What has not happened

No application code or tests have been changed, no inventory has been migrated or published, no accounts have been provisioned, and no deployment has been performed. No production credentials were read or live databases accessed. The software acceptance matrix has not been executed; it specifies future verification.

## Next implementation handoff

Dispatch the backend and interface Stage 1 prompts against the frozen contract. The backend provides real draft persistence/authentication; the interface can prepare against contract fixtures but cannot report completion until integrated. The verifier prepares fictional cases and independently tests the integrated slice. Send focused repair assignments for failures before proceeding to publication/catalog integration.

Before any release, review the complete candidate, migration rehearsal, public/private route evidence and recovery runbook. The broader roadmap is not an instruction to implement AI or other deferred features in the first slice.

## Stage 1 dispatch — October 5, 2026

Supervisor review of the full packet against source found no blocking contradictions. Noted: matrix VIEW-01 phone width (375×812) differs from FRONTEND_PACKET (390×844), so both are covered; geographic multiselect serialization is already resolved in INTEGRATION_DECISIONS §6; DEVELOPER_PROMPTS supersedes BACKEND_PACKET's "no edits authorized" briefing note for Stage 1.

Pre-change baseline: `BASELINE_MANIFEST.sha256` (158 source files). Python suite 624 OK (21 Postgres skipped); JS suite 68 pass.

| Workstream | Dispatched | Boundary |
|---|---|---|
| Backend | Stage 1 (B1 + B2): auth/sessions, deny-by-default route policy, schema v8, version-checked drafts, history | `server/`, `api/`, `scripts/`, Python tests; disposable Postgres on port 55432; app port 8431 |
| Interface | Stage 1 slices 1–2 plus phone filter drawer; fixtures first, then integration once BACKEND_RESPONSE.md exists | `web/`, `tests/js/`; app port 8432 |
| Verifier | Phase A: fixtures, legacy v7 workspace, Stage 1 HTTP acceptance scripts, Postgres harness. Phase B after both responses | `verification/` only; Postgres port 55433; app port 8433 |

### Backend Stage 1 — supervisor review (October 5, 2026)

Supervisor reran the suites: 670 OK on Python 3.14 and macOS 3.9 (29 Postgres skipped; backend reports 670 OK, 0 skipped on disposable Postgres). The deny-by-default check is shared by both servers in `server/app.py` and runs before routing; the anonymous allowlist matches §3. `datos/ara_map.db` is untouched (Sep 21). Accepted for integration, pending independent verification.

Deviations accepted: top-level create body, 200 on create, `confirm` on PATCH, extra internal fields, PBKDF2 (no scrypt on system Python), Stage 2 public placeholders, `inventory_source`/`inventory_import_batch` deferred to Stage 3.

Carry-forward items:
- Stage 3 (blocking for adoption): the price-without-currency 422 at `server/inventario.py:121` checks the merged draft, so an adopted record with a price and no currency could not be edited at all. Apply it only when price or currency changes, or keep adopted NULL-currency records editable.
- Stage 2: login throttling is keyed by username only, so a stranger can lock a known account out for 15 minutes. Add per-client keying.
- Before cutover: decide whether to retire `ARA_MAP_READ_ONLY` or make it public-only. Update `tests/cloud_smoke.py`, `tests/e2e/smoke.mjs` and the README. Retire `ARA_MAP_EDIT_PASSWORD`.
- Owner note: the local launcher now upgrades a local database to v8 (backing it up first) and then requires sign-in. No accounts exist until someone creates them with `scripts/cuentas.py`.

Next: interface integrates against the real backend; verifier Phase B runs the API-level Stage 1 checks now and the browser pass after integration.

### Interface Stage 1 — supervisor review (October 5, 2026)

Supervisor reran `node --test tests/js/*.test.mjs`: 98 pass. Integrated log: 9 ok, 0 failed against the real backend on a temp database. Reviewed the conflict and 390-px filter screenshots. No backend files were edited. Accepted for integration, pending independent verification. The public catalog with records is fixture-only until Stage 2.

The "Latitud (X)" / "Longitud (Y)" labels are intentional: they match the existing importer (`server/importer.py`, where "x" maps to lat) and the original terrain detail.

Carry-forward items for Stage 2:
- Interface: split `web/components/app.js` (1,318 lines) before adding publication UI. Rewrite `tests/e2e/smoke.mjs` for individual sign-in. Add a status column to the inventory table. Stop toasts from covering the phone editor's action bar.
- Backend: `/api/config.readOnly` should reflect only `ARA_MAP_READ_ONLY`, not the sign-in state. Facet counts are optional.

Verifier: Stage 1 API checks are running, followed directly by the integrated browser pass.

### Stage 1 accepted; Stage 2 issued (October 5, 2026)

Independent verification found no blocking defects: 0 FAIL across five API passes (SQLite and disposable Postgres through the cloud adapter), 0 sentinel hits in 594 anonymous probes per pass, and 90 PASS / 0 FAIL in the browser. The candidate manifest was rechecked by the supervisor and is unchanged. One low-severity defect (D-1) is folded into Stage 2. Decisions O-1 to O-7 are in INTEGRATION_DECISIONS.md §10. Stage 2 work is in STAGE2_ASSIGNMENTS.md. Nothing is deployed; Stage 2 output also remains local until the integrated cutover.
