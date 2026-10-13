# Round 2 — independent first review and bounded corrections

GitHub checked 2026-10-09, 18:15 UTC; exact heads/check receipts confirmed
again through 18:21 UTC. Main is unchanged. No application code was edited.

## Verdict

**Changes requested on both feature PRs. Do not start 3A/3B.** Green suites
do not close the independently reproduced gaps below.

| Deliverable | Exact reviewed head | Disposition |
|---|---|---|
| A/B integration checkpoint #24 | `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` | Composition/ancestry verified; retains inherited dispatcher defect R2-A1. Not release-ready. Preserve this frozen head. |
| A table #26 | `517223668405c1d4feb2deffbd2d16a072395fd9` | R2-A1 through R2-A4 require corrections on this same PR. |
| B HTTP #25 | `2ea602a940462fe8bb7d8f0208e0e1dbee19603e` | R2-B1 requires a narrow correction on this same PR; HTTP-harness-only evidence boundary remains correct. |

Round 1 acceptances are unchanged. This is a targeted first review of new
boundaries and affected tests, not blanket acceptance of all remaining 2A UI
behavior. Review corrected deltas and remaining acceptance evidence at handback.

## R2-A1 — P2: rejected HTTP bodies become a second request

Owner A; inherited, not introduced by B. Location `server/app.py`, early
Host, Origin and read-only exits in `Handler._dispatch` (approximately 149–169
at #26). B's R-5 was a valid finding; it must be repaired before mounting more
handlers, not left as an optional future decision.

Independent raw-socket tests on the real #26 dispatcher sent one POST whose
body was a harmless request for public `/api/config`. In each case the server
answered **403, then 200 on the same connection**:

- read-only POST refusal;
- foreign-Origin refusal (independently reproduced, beyond B's inspection);
- invalid-Host refusal (additional matching early exit).

The unread body is reinterpreted as HTTP framing. **This probe does not prove
access to private data, credential theft or an authorization bypass**; its
second request was intentionally public. Fix the refusal boundary by closing
the connection when returning without consuming a declared body (or another
equally safe bounded framing policy). Audit the analogous early exits; do not
read an unbounded attacker body merely to preserve keep-alive. Preserve valid
ordinary requests and existing 401/403/413/busy behavior.

Evidence: [socket probe](probe_dispatcher.py), [observations](dispatcher-probes.jsonl).

## R2-A2 — P1: private table/dialog state survives loss of identity

Locations: `web/components/app.js:233` revalidation/identity change,
`web/components/session/session.js:104` expiry with unsaved work,
and table/dialog disposal in `web/components/tabla/`.

Independent Chrome 154 tests against the actual disposable server:

1. Olga edits a fictional private comment; the actual session is ended at
   the server and the cell save gets 401. The app reports session **null**,
   but retains **10 private rows and the unsaved marker in the DOM** behind
   the sign-in dialog. This contradicts 2A's explicit clear-on-expiry contract.
2. Olga opens a terrain detail with a saved private marker. Otto (zero grants)
   then signs in through the same browser cookie jar. On forced pageshow
   revalidation the app correctly identifies **Otto**, but the old private
   detail dialog remains open, including its saved comment. A direct request
   under Otto correctly returns **404** for that terrain. The leak is retained
   client state, not failure of the backend's terrain authorization.

Destroying the table alone does not dispose its dialogs. Centralize invalidation
of the old private scope: pending requests/queued writes, rows/definitions,
unsaved fields, details/history/admin dialogs and file mounts. Remove private
DOM and invalidate delayed callbacks; closing a modal without removing its
private contents is insufficient. Do this on expiry/logout/account/role loss
before a new identity can see or act on old state. Do not show the discarded
content in a toast. No preservation behind a login overlay in this packet.

Test dirty and clean identity transitions, account change through revalidation,
login over expiry, role change, grant/transfer loss, open dialogs and delayed
responses. No requests queued by the old identity may resume as the new one.

Evidence: [browser probe](probe_session.mjs), [observations](a-session-probes.jsonl).

## R2-A3 — P2: custom text/date validation is not safe across backends

Location `server/columnas.py:60–117` and its callers. Real HTTP probes found:

| Input | SQLite | Postgres |
|---|---|---|
| Column name containing NUL | 200, stored | 500 |
| Column name with lone surrogate | 500 | 500 |
| Custom text with lone surrogate | 500 | 500 |
| Date `2026-10-09` plus trailing newline | 200, noncanonical value stored | same |

The date regex's `$`/`match` accepts a final newline; calendar parsing does
not reject it. Name and text validation allow strings that fail UTF-8 encoding
or backend binding. Option text also admits NUL (200 on both); use consistent
safe string rules for new definition/value input, without rewriting history.

Reject invalid input before hashing, SQL and audit serialization with controlled
field validation on both backends. Use an exact full date match; preserve valid
Unicode (including non-BMP characters), optional null values and existing
normalization. Assert no terrain/definition/version/audit/idempotency mutation
on rejected operations. Do not hide arbitrary SQL/encoding failures with a
broad exception handler or change schema to accommodate invalid input.

Evidence: [HTTP probes](probe_inputs.py), [SQLite](a-probes-sqlite.jsonl),
[Postgres](a-probes-postgres.jsonl), corresponding stderr logs.

## R2-A4 — P2: one cell's save response removes another active editor

Location `web/components/tabla/Tabla.js:495` (`pintarFila`), called by
`reemplazar` after a save response. It replaces the entire row even if another
cell in that row is currently being edited.

Independent browser probe: send a real name PATCH, hold only its HTTP response;
while it is in flight, open the same row's Comentarios editor and type a second
unsaved marker. Release the successful first response. The second editor
disappears: **0 editors, no second marker in the DOM, focus on BODY**. This
does not establish deletion of the detached JS editor object's value, but it
does demonstrate a broken visible edit/focus flow during ordinary fast typing.

Preserve active editing, unsaved text, selection/focus and queued intent when
another cell's save/conflict/error refreshes the row. Do not silently save a
detached editor later. Add deterministic real-browser tests for success and
conflict while another cell is open, followed by keyboard save/cancel, on
core and custom cells. Keep terrain optimistic versions authoritative.
Evidence: final case in [browser observations](a-session-probes.jsonl).

## R2-B1 — P2: Unicode digit query parameters produce 500

Location `server/api/archivos.py:97–101` (`_limite`) and `:240–243`
(`fragmento_geometria`). `str.isdigit()` accepts characters such as `²`, but
`int('²')` raises ValueError. Actual authenticated GETs with `limite=%C2%B2`
or `desde=%C2%B2` return **500 internal on both SQLite and Postgres**. Tested
the terrain attachment list, history and geometry content paths.

Use bounded ASCII decimal parsing (or equivalently explicit safe validation)
before conversion, preserving documented controlled errors, limits, aligned
offsets, defaults and legitimate values. Apply the shared limit correction to
all its callers; inspect analogous new integer parsing. Test superscript/
Unicode numerals, signs, empty/oversized inputs and valid boundaries through
real HTTP. Preserve normal session/capability and non-disclosure behavior.

Evidence: [HTTP probes](probe_inputs.py), [SQLite](b-probes-sqlite.jsonl),
[Postgres](b-probes-postgres.jsonl). This is not a reason to change lifecycle,
schema, geometry wire format or the shared dispatcher in B's branch.

## Evidence, decisions and limits

- Independent A focused suite: **28/28**, SQLite + disposable UTF-8 Postgres
  17, including the 26 column tests and two composition tests:
  [a-focused.log](a-focused.log). Python 3.9.6: **13/13** SQLite column tests;
  JS: **128/128**. [Python floor](a-python39.log), [JS](a-js.log).
- Independent B HTTP suite: **53/53**, SQLite + disposable Postgres 17:
  [b-http.log](b-http.log). Python 3.9.6: **28/28** SQLite/header tests:
  [b-python39.log](b-python39.log). Passing supplied tests did not cover R2-B1.
- Baseline: accepted-source ancestry/tree identity independently confirmed;
  only the manifest and composition test follow the merge:
  [component checks](checkpoint-components.log). **1,121/1,121 tests passed**
  independently with SQLite and disposable UTF-8 Postgres 17, no skips:
  [baseline-full.log](baseline-full.log). Its composition is verified; inherited
  R2-A1 remains an explicit A-owned correction before further integration.
- Verified exact-head green CI: #24 [37948759180](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37948759180),
  #25 [37957053180](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37957053180),
  #26 [37960011108](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37960011108).
  Individual PR JSON receipts are saved here. B's container packaging failure
  is separately disclosed; it is not the cause of the new reproductions.
- **Admin default:** keeping Inventario as the administrator landing page is
  acceptable for this packet; Tabla maestra remains accessible. No one-line
  navigation change or new owner decision is needed. The 250 → 200 legacy
  pagination repair is consistent with accepted 1A.
- The reported ~1 MB heap increase is **not evidence of a proven leak**. After
  repairing disposal, add a bounded longer warm-up/repeat paging/base/dialog
  measurement to determine whether retained growth plateaus; no new research
  assignment. Browser/Postgres duplication and screen-reader testing remain
  disclosed limits, not automatic blockers. The untested identity paths were
  material and produced the concrete failures above.
- This review did not repeat A's entire 13-journey/25,000-row matrix or B's
  allocation measurements. No hosted or production evidence. Run the relevant
  changed-path regression journeys for corrections; preserve earlier evidence
  where inputs are unchanged.
- `./verificar.sh` on the supervisor documentation branch is a separate
  publication gate, not either feature's suite. It passed: 672 Python tests
  with 29 PG skips, full Python 3.9.6 suite and JS checks:
  [supervisor-verificar.log](supervisor-verificar.log).

## Next owners and reproducing

A follows [TEAM_A.md](TEAM_A.md); B follows [TEAM_B.md](TEAM_B.md). Same feature
PRs, additive corrections, no force pushes. Do not modify #24 or propagate an
unreviewed A feature into B. Ordinary 3A mounting requests R-1–R-4 stay reserved;
the inherited dispatcher correction is explicitly assigned to A now.

For HTTP probes set PYTHONPATH to a fresh archive of the corresponding exact
head, then run `python probe_inputs.py sqlite a` (or `postgres a`, `sqlite b`,
`postgres b`). Postgres requires ARA_MAP_TEST_DATABASE_URL pointing only at a
disposable UTF-8 database; fixtures create/drop their own isolated schemas.
Run `probe_dispatcher.py` with A's tree on PYTHONPATH; it creates its own DB.

For the browser probe, start A's `tests/e2e/tabla_servidor.py --puerto 8458
--registros 10`, then run `REVIEW_TREE=/path/to/A node probe_session.mjs` from
this supervisor checkout (uses its existing optional Playwright dependency and
local Chrome). The server is synthetic/disposable only; no real account or
database may be substituted. Stop it after testing.
