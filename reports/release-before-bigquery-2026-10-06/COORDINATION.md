# Coordination between the supervisor and Claude Cloud developers

GitHub is the shared record. The supervisor's Mac and each Claude Cloud session are separate clones. Uncommitted files, local paths, running processes, credentials and environment settings are not shared through Git.

## Current assignment

For the two independent Claude Code accounts, use the [two-team delivery plan](../master-table-plan/TWO_TEAM_DELIVERY_PLAN.md) and its Team A/Team B kickoff briefs. Each team owns a feature across backend, interface, and tests; Team A's lead integrates shared-file changes after review. The supervisor remains responsible for planning and review, not implementation.

Read the [master-table product plan](../master-table-plan/MASTER_PLAN.md) first. The owner has paused connected Excel in favor of direct terrain editing, PDF/KMZ attachments, KMZ-first mapping, filtered datasets, and admin/operator roles. The earlier [connector next steps](SUPERVISOR_NEXT_STEPS_2026-10-06.md) and [completion instructions](SUPERVISOR_COMPLETION_INSTRUCTIONS_2026-10-06.md) are historical context. Preserve that work, but do not resume it as the current assignment. Direct instructions from the owner take precedence. Expand and review one phase packet at a time before implementation.

The release target is the working production app with an interactive master table, files, layouts, roles, and derived maps. Retaining Neon is the current planning recommendation; BigQuery remains deferred. The supervisor owns planning, review and reporting to the owner; developers own implementation and verification. The owner relays links and makes necessary business/account decisions, without having to interpret technical disagreements.

## How to receive instructions

1. Fetch the supervisor's documentation branch or merged commit from GitHub. While the documentation PR is open, read its exact branch/commit; do not assume it is already in main.
2. Record the instruction path and commit SHA in your next report. State whether your implementation follows it or proposes a specific deviation.
3. Do not merge unrelated application changes just to read instructions. Do not overwrite your local work to synchronize a clone. Inspect changes and integrate deliberately.
4. Check for a newer supervisory brief before a major implementation milestone or release gate. Do not follow an older packet simply because it exists in your clone.

## How to submit work for review

Push the reviewable implementation and report to GitHub, then return these identifiers:

```text
Instructions followed: <path> at <full commit SHA>
Implementation: <branch>, <full commit SHA>, <PR URL>
Report: <path>, <report commit SHA or immutable GitHub link>
Local-only/uncommitted work: <none, or explicit description>
Local tests: <commands, results, environment, tested SHA>
Hosted tests: <deployment ID, URL, target, tested SHA, results, or blocked>
Production changes: <none, or exact authorized actions and evidence>
Remaining blockers: <specific action, assigned operator, what can proceed independently>
Requested review: <concrete questions not already resolved by the brief>
```

Clearly label draft or untested work. A report commit may differ from the implementation commit; name both. Never put credentials, private connection strings, OAuth codes, session cookies, real data dumps or preauthenticated download URLs in reports or Git.

The supervisor reviews the named implementation commit. If you push a newer commit during review, disclose the new SHA and changed scope; approval and test evidence do not automatically transfer. Reconcile a report's prose with its latest pushed state so that “local only” does not remain after the draft is committed.

## Evidence and access boundaries

- Local fixture tests, disposable Postgres tests, hosted synthetic tests and real employee/file acceptance are separate evidence categories. State which ones passed and which remain blocked. Real Microsoft workbook tests belong to the paused connector work.
- A successful test belongs to the exact commit/environment tested. The older 13/13 Preview result does not prove the new master table, roles, attachments, or KMZ workflow works.
- A blocked Claude Cloud network does not imply a service is unavailable everywhere. Assign cloud verification to an authorized operator with access; do not ask the supervisor to implement or deploy on your behalf.
- Access or account actions requiring the owner must identify the exact service, account and required step. Continue independent work while waiting.
- Production remains behind Phase 6 of the master plan and the subsequent detailed release packet. An instruction-document merge is not authorization to migrate or replace production.

## Review loop

Developer report and exact commit → supervisor review → written keep/correct/stop/redo instructions → developer implementation and evidence → supervisor release assessment → owner-facing decision where required.

Use new dated reports for completed milestones and link them from the next handoff. Preserve earlier reports as historical evidence rather than rewriting a failed result into a pass. The owner should need to forward a link, not explain which clone contains the truth.
