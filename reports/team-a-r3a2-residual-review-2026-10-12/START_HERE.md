# Team A — R3-A2 residual accepted

Independent supervisory review, 12 October 2026, 14:55 America/Mexico_City (20:55 UTC). Repository: Andre07-hash/ARA-MAP.

## Verdict

**Accept the R3-A2 residual correction at `4670df7348265af66c640069e5ece2a274830fa3`, draft [PR #29](https://github.com/Andre07-hash/ARA-MAP/pull/29).** The previously reproduced global-master row-permission defect is closed. No further A correction is requested for this finding.

This is acceptance of the bounded correction. It does not certify a hosted MVP or authorize a PR/main merge, deployment, provisioning, real-data import or account change. The owner's delivery priority remains ASAP, private portal first.

## Scope and source inspection

Compared reviewed `41d029c54848a7aebb1d46dfd053848ccf265afc` with final `4670df7`. Code head is `191491e387709ef21b0ee81437abe1768b0dbd76`. Only application delta: `web/components/tabla/Tabla.js`, plus the new browser journey and report/evidence.

`filaEditable()` now combines the current view, the row's own base permission and the terrain's archive state. `puedeCambiarFila()` already governs the detail; the same base rule now applies when painting cells, opening editors and mounting/updating file cells. The server policy is unchanged. `base_archivada` revalidation reloads the bases and reapplies permissions across the current page; pending/open editors are preserved by the existing repaint rules.

Confirmed B's accepted `b2ac9bd176043fc4b1625b13993f8f21407dc978` is an ancestor of the reviewed final head. Existing merge `e795935c7aebedce8b1e58a6ba87cf8ef396fafe` has parents `0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db` and `b2ac9bd176043fc4b1625b13993f8f21407dc978`; no duplicate merge is needed. Frozen C1 stays unchanged.

## Independent evidence

Exact application/test archive of final `4670df7`; macOS, installed Google Chrome, `/usr/bin/python3` (Python 3.9), disposable SQLite and local private file storage. Historical reports were excluded from extraction because one contains an absolute node_modules symlink; application and tests are from the exact commit. Existing Playwright dependencies were linked into the disposable tree. No application code was changed.

| Check | Result |
|---|---|
| Original independent global-master probe, reused unchanged | Real completion **409**; detail read-only `1`; row cell `aria-readonly=true`; double click opens **0** editors. |
| A's newly added regression, independently executed with a narrow filter | **Pass**: archived-base rows refuse Enter/double-click/typing; unresolved sibling text remains in cell/tray; previously stored PDF downloads byte-identical; active and unassigned rows save; direct server write refused; restored base edits after reload. |
| Browser error controls in that partial run | 8 session checks pass; **9/9 total checks**, including the one residual journey; **27 unrelated journeys omitted**. This is not a rerun of A's full 41-check suite. |
| Affected table unit module | **8/8**, no skips. |
| GitHub exact-head checks | JavaScript and Python/disposable Postgres successful in [run 38305224940](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38305224940). |

Flow confirmed: upload completion reaches the real API; the archived base causes the real server refusal; the client reloads authoritative permission state; detail and master-table row stop offering new edits. Allowed reads and other writable bases remain usable.

The original probe's `fileCellReadonly` values are null because it asks the outer cell wrapper for an attribute. They are not evidence of widget writability; the actual detail attribute, row editor check and focused journey are the relevant observations.

Saved outputs: [original probe result](evidence/original-master-probe.json), [focused browser summary](evidence/recorrido-sqlite.json), [server log](evidence/focused-server.log), [table unit summary](evidence/table-unit-summary.json), [GitHub metadata](evidence/github-pr29.json). Original reproduction source: [probe-master-base.mjs](probe-master-base.mjs). It expects to be copied into the exact archived repository root and run against a fresh disposable `tabla_servidor.py --puerto 8486` harness; never a normal installation.

Focused regression command, from the exact archive:

```sh
RECORRIDO_SOLO='R3-A2 residual|sin errores de página' \
RECORRIDO_PUERTO=8487 PYTHON=/usr/bin/python3 \
CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
node tests/e2e/recorrido-completo.mjs
node --test tests/js/tabla.test.mjs
```

## Evidence reused and limits

A reports combined SQLite 41/41, Postgres smoke 18/18, mounted widget/scope and other table suites, full repository checks, Python floor and full disposable Postgres. These remain developer evidence, alongside independently verified CI. The unchanged earlier supervisor evidence is reused; no broad browser, renderer, 25k timing, memory, full Python or Postgres suite was repeated for this client-only delta.

The residual journey was independently run on SQLite only. External archives/restores are learned on refusal, refresh or reload; no live push update is promised. Already open editors intentionally retain their text, with server-side writes protected. This is an acceptable disclosed limitation, not a reason for another correction packet.

No new actionable finding. The heap slope and optional batching do not reopen this acceptance. B's separate draft #30 remains a distinct review; it was not integrated or accepted here. Hosted persistence, private storage and database-plus-file restoration still require the planned candidate verification.

## Next action

A can move to the read-only hosted-integration/onboarding readiness brief in [TEAM_A.md](TEAM_A.md). Do not reissue R3-A2, merge #28 again or start advanced saved views/public catalogues. B preserves its deliveries; the supervisor handles #30 separately. Hosted implementation packets follow the concrete provider/access decision in the [private MVP plan](../client-mvp-plan-2026-10-12/START_HERE.md).

This review and evidence are saved locally on the supervisor checkout, not published to GitHub. No application code or team branch was changed. Both disposable review servers were stopped; the older synthetic preview on port 8459 was not interrupted.
