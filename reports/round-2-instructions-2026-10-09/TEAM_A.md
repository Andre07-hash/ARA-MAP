# Team A — packet 2A: editable table and work-base controls

Your 1A corrections are accepted; do not reopen them. First publish the tested
combined checkpoint exactly as START_HERE.md specifies. Preserve #20 and #22.
Then implement this feature on the separate `claude/team-a/master-grid` branch.

## 1. Usable employee table, not attachment/map integration

Mount a real local employee entry point in the existing application:
operators see their assigned work bases (a useful no-access state for zero
grants); administrators can use the global Tabla maestra, unassigned records
and a selected base. Keep legacy imported-base/map access admin-only and
working. Use the real session/API, not a fixture-only demo or widened legacy
admin endpoints. No account creation/password/role-management console.

Render all fourteen core columns, preserving the mapping in 1A. Global view
also shows Base; custom columns appear only in a selected base. All business
values remain optional. Add an unnamed blank terrain, edit it and reload it
from another session. No inferred MXN, conversions, derived area/prices,
name-based identity or swapped X/Y. Keep publication rules separate.

Implement inline text/number/choice/date editing as applicable, clear save/
error/pending feedback and keyboard navigation (Tab/Shift-Tab, Enter, Escape),
accessible labels and focus restoration. Use real `expected_version` writes;
serialize pending edits for the same row or otherwise prevent stale response
overwrites. A 409 preserves the user's unsaved input and shows the authorized
current row; provide explicit refresh/reapply, never silent last-write-wins.
Do not blindly replay an ambiguous mutation or duplicate blank creation:
retain its original idempotency key until its outcome is resolved.

Search/sort/filter/counts stay server-side through accepted 1A endpoints;
render/load only bounded pages (default 100, maximum 200). Reset cursors when
scope/filters/sort change; cancel or ignore stale responses. Do not fetch all
pages to filter in JS. Definition/value filtering across bases is out of scope.
Preserve honest XY-only located/unplaced semantics until 3A adds active KMZ
descriptors. PDF/KMZ cells are the integration slots in INTERFACES.md; no fake
upload action, fabricated file count, B widget or renderer change.

## 2. Base-local custom-column backend and UI

Use schema-9 `inventory_column`, `inventory_revision.custom_json` and
`maestra_base_event`; preserve stable IDs and original-base values. Add scoped
definition list/create/rename/order/retire/restore endpoints and management UI.
Use `columnas.gestionar`, current base authorization and final transaction
reverification. Definition mutations have their own `expected_version` and
actor/time audit; creating definitions must not duplicate them on a retry.
Do not bump every terrain's version merely to rename/retire a definition.

Freeze these conservative rules for this packet:

- Types are `texto`, `numero`, `opcion`, `fecha`; a definition's type is
  immutable. Rename labels, not IDs. No custom attachment type or core-column
  retirement. Validate bounded names, text and option lists and document exact
  technical limits, including how existing definitions are handled.
- Missing/cleared values are null; omitted keys preserve prior values.
  Numbers are finite and reject booleans; dates are real calendar dates in
  `YYYY-MM-DD` form without timezone conversion; choices match allowed values.
  Choice values are stable strings in this packet: additions are allowed,
  destructive removal/renaming of existing options is deferred. No coercion
  or automatic conversion of stored data.
- A definition can be retired/restored without deleting its values/history.
  Normal edits refuse unknown, retired or other-base IDs even for an admin;
  retained historical values remain preserved. Restoring makes them visible
  again under the same current-base projection. Admin audit remains full.
- Extend the existing PATCH with sibling `custom: {"custom:<uuid>": value}`
  beside `expected_version`, `changes` and optional `confirm`. Core/custom
  changes in one request create one atomic terrain version/revision/event.
  Copy forward untouched and hidden custom values; never rebuild storage from
  the caller's redacted DTO. Existing core-only clients remain compatible.
- Write custom history in the **accepted A2 shape**: `changes` entries keyed
  by stable `custom:<uuid>`, each with scalar `before` and `after`. Do not add
  nested full custom maps, secret labels or a competing diff shape. Exercise
  the real new writer through transfer/retirement/transfer-back and every
  history/detail/list/conflict/replay projection; seeded fixtures alone are
  no longer sufficient.

Reuse P2's write boundary and locking order for column/terrain edits, transfers,
retirement, grant changes and archived bases. A column retired while a cell
save waits cannot accept a stale write after retirement wins. No new schema
is expected; if a real gap is demonstrated, submit the smallest separate
prerequisite for review rather than changing schema implicitly in the grid PR.

## 3. Administration and preservation

Use the accepted base APIs for create/rename/archive/restore and grant editing.
Grant updates replace the full set with `expected_version`; show conflicts,
never overwrite concurrent changes silently. If the existing response lacks
an eligible-account picker, a narrow admin-only bounded lookup returning only
the minimum account identity/status needed for grants is allowed. No password,
session, token or unrestricted account-management data. Do not widen operator
access to account lists.

Add authorized terrain archive/restore and admin transfer controls. Transfer
uses the real preview, shows destination access and columns becoming hidden,
requires explicit confirmation and rechecks version independently when saved.
Preserve stable IDs/files/geometry/history and operator public-visibility
restrictions. Archived-base screens are clearly read-only where P2 requires.

On logout, account/base change, denied access or transfer out of scope, clear
private rows, details, custom definitions, pending responses and unsaved
sensitive state for the lost scope. Never display an old request's response
under a newly selected account/base. Explain discarded unsaved work without
leaking its content. Future file/geometry widgets get the same disposal hook.

## 4. Acceptance and ownership

Own new table/base/column UI modules and A's existing shared shell/client/API/
repo files. Do not alter B's lifecycle/parser/store/renderer. Keep separate
dedicated tests; avoid rewriting shared e2e documentation or another team's
fixtures. Plain ES modules, no build framework or new local runtime dependency.

Required evidence:

1. Real HTTP tests on SQLite and disposable Postgres for definition CRUD,
   custom PATCH validation/atomicity/audit/idempotency and current-base
   projection, including real custom writes before transfer/back and retirement.
2. Both race orders for custom edits versus definition retirement, transfer,
   grant loss and base archive, and concurrent definition/grant changes. No
   partial revision or secret conflict response. Preserve A1 legacy replay,
   A2 history and A3 cursor regression tests and 1B version independence.
3. Real-browser operator/admin journeys using actual local HTTP and fictional
   sessions: blank create, edit every core/custom type, refresh/second session,
   two-user conflict, keyboard-only save/cancel, archive/restore, grants,
   transfer preview/confirmation, no-grant state and session/scope loss.
   Include screenshots and runnable steps; component mocks alone are not UI
   acceptance. Public/legacy admin journeys must not regress.
4. Synthetic 25,000 total / 3,000 in one base / five editing sessions. Report
   page DOM row count, requests/query counts, response bytes, page latency,
   input responsiveness and retained client memory after repeated paging/base
   switches. No unbounded page accumulation. Local UX targets: visible typing/
   focus feedback within 100 ms and first usable 100-row page within 2 seconds
   on the documented test machine; report misses and their cause, not a vague
   capacity claim. These are measured local targets, not hosted guarantees.
5. Full suites, Python 3.9, JS, applicable lint/types, exact-head green CI.

Report: `reports/team-a-master-grid-2026-10-09/START_HERE.md`, with API examples,
custom-definition contract, actual history format, component seams, browser
evidence, measurements, limitations and explicit 3A reservations. Separate
draft PR and exact heads. Stop; no 3A, main merge or deployment.
