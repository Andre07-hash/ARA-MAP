# Round 2 — independent correction review

GitHub checked **2026-10-09 19:08 UTC**. This is a delta review, not a new
feature packet. Previous instructions: `750164b6761b3c3fe160010bc4163df1b7b2389f`.
The owner relays TEAM_A.md and TEAM_B.md; delivery is not inferred.

| Deliverable | Reviewed final head | Verdict |
|---|---|---|
| A / #26 / 2A | `cda5c20580179abcd8673010797a9975b1b7a06d` | Original four reproductions corrected; bounded framing follow-up R2-A5 required |
| B / #25 / 2B | `704d8b8745b79f7b72f35350079ccd788e6d2e0a` | R2-B1 closed; inherited privacy-test repair R2-B2 required |
| #24 checkpoint | `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` | Frozen and unchanged; do not repair it in place |

Both feature PRs remain open drafts, targeting `claude/integration/round-2-baseline`.
Exact-head GitHub Python/disposable-Postgres and JavaScript checks are green:
[A run](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37976622134),
[B run](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37975159654).
#20, #21, #22 and #23 retain their accepted pins in STATE.json. Main remains
`09452fd26d38319567dce28a89db100ea61c739a`. No 3A/3B, merge or deployment is released.

## Closed corrections and decisions

- **R2-A1 original early refusals:** read-only, foreign Origin and invalid Host
  now each produce only 403 and close. A's expanded socket tests pass.
- **R2-A2:** private rows/dialogs/unsaved edits are removed on expiry and identity
  loss; delayed work cannot repaint the old account's data in the tested paths.
  The original independent probes and A's 16 expanded real-browser journeys pass.
- **R2-A3:** original unsafe Unicode/NUL/date probes produce controlled 422 on
  SQLite and Postgres; focused tests include non-mutation and valid Unicode.
  The declared analogous text-validation scope is accepted. Stored history is
  not rewritten and short-text whitespace normalization remains as documented.
- **R2-A4:** a returning save no longer destroys another active editor, its
  text or focus; the expanded core/custom/conflict/save/cancel journeys pass.
- **R2-B1:** original three Unicode-numeric probes now return controlled 400 on
  both databases, without tracebacks. ASCII bounded parsing and the declared
  leading-zero widening are accepted; the shared router's empty-query behavior
  remains unchanged.
- **B's R-7 is already addressed by A's current head.** Anonymous login with
  only the headers for `Content-Length: ²` or `-1` immediately returns 400 and
  closes, before any body is sent. Declaring 26 MiB immediately returns 413.
  Do not ask A to repeat a fix already present. B's branch still carries the
  older dispatcher by design; consume A's reviewed fix at the later checkpoint.
- Keep Inventario as the administrator landing page. Browser-Postgres and
  screen-reader coverage remain explicitly unperformed, not automatic extra
  gates for these corrections. A's reported Python coverage is 96%; the
  supervisor did not repeat the full coverage run. The bounded memory report
  shows flat DOM/listener counts but residual heap growth; it does **not** prove
  a plateau or absence of all retained objects. No open-ended memory work is
  assigned, and no total-browser-memory guarantee is accepted.

## R2-A5 — P2: ambiguous framing still reaches a second request

At #26, `server/app.py:291` (`_read_body`), `headers.get()` sees only the first
field value and `... or "0"` treats an explicitly empty length as absent.
Checking `Transfer-Encoding` by truthiness also misses an empty first field
followed by another encoding field.

Independent raw socket cases against the real ephemeral server, anonymous
`POST /api/login`, with a 64-byte body consisting solely of a public
`GET /api/config ... Connection: close`:

| Header input | Observed statuses on one connection |
|---|---|
| `Content-Length: 0` followed by a second `Content-Length: 64` | `[401, 200]` |
| Explicitly empty `Content-Length:` | `[401, 200]` |
| `Content-Length: 0`, empty `Transfer-Encoding:`, then `Transfer-Encoding: chunked` | `[401, 200]` |

The 401 is login's normal refusal; the 200 is the body being interpreted as
another request. This is a request-boundary defect, **not evidence of a
private-data authorization bypass**. Fix the same dispatcher only; do not
change auth policy, introduce body draining, or start 3A. Require one controlled
400 followed by connection close for malformed/ambiguous framing, before body
reads. Preserve legitimate absent-length requests and normal keep-alive after
a valid body was read. See TEAM_A.md for bounded tests.

## R2-B2 — P2 test reliability: privacy assertion has deterministic false positives

At #25, `tests/test_archivos.py:650–681`, the hidden byte count is converted to
the short string `145` and asserted absent from `repr()` of the entire response.
An intentionally public event UUID can legitimately contain those characters.
The original redacted version, actor and details are correct in this case.

The supervisor reran the existing test with unique valid UUIDs whose public
event IDs contain `145`; it fails deterministically on **both SQLite and
Postgres** with the same false positive. This confirms A's diagnosis. It does
not reopen the accepted lifecycle privacy implementation.

B owns a **test-only** correction in #25, explicitly permitting the inherited
`tests/test_archivos.py` file. Preserve #23. Assert the structured privacy
contract, not substring absence from unrelated public identifiers. Keep the
original privacy coverage and add a deterministic collision case plus negative
controls proving that actual leaked metadata still fails. Do not merely remove
the byte-count assertion, retry until green, or suppress the test.

## Independent evidence

Exact-head archives; macOS, Python 3.14.5/3.9.6, fresh UTF-8 Postgres 17,
Node 23.7.0 and Chrome 154. Synthetic accounts/data and loopback only.

| Check | Result / file |
|---|---|
| A columns + dispatcher + composition, SQLite/Postgres | 33 tests, zero skips, OK (`a-focused.log`) |
| A same modules, Python 3.9 | 33 run, 15 PG skips, OK (`a-py39.log`) |
| B HTTP + composition, SQLite/Postgres | 63 tests, zero skips, OK (`b-focused.log`) |
| B same modules, Python 3.9 | 63 run, 30 PG skips, OK (`b-py39.log`) |
| A JavaScript | 128/128 (`a-js.log`) |
| A browser identity/editor journeys | 16/16 (`a-browser-identity.log`); team-authored suite independently rerun |
| Original supervisor browser probes | all corrected (`a-session-probes.jsonl`) |
| Original supervisor HTTP input probes | A five 422s/backend; B three 400s/backend (`*-inputs-*.jsonl`) |
| Original socket refusal probe | one 403 per case (`a-dispatcher.jsonl`) |
| Additional framing edges / R-7 | `a-framing-edges.jsonl`; three original fixes pass, three new boundary cases fail |
| Deterministic privacy-test collision | failure reproduced on both backends (`b-privacy-*.jsonl`) |

Reproductions are in `probe_edges.py`; set PYTHONPATH to an archive of the named
head and run `framing`, or `privacy sqlite` / `privacy postgres`. For Postgres,
ARA_MAP_TEST_DATABASE_URL must name a disposable database. Reuse the previous
review's unmodified `probe_inputs.py`, `probe_dispatcher.py`, `probe_session.mjs`
for the original cases. The browser run uses A's synthetic `tabla_servidor.py`.
No application code was edited by the supervisor. Only the archive's Playwright
dependency was linked to the already installed test dependency.

Full feature/coverage suites are developer-reported and CI evidence; this
independent correction review used focused tests, not a repeated full combined
integration suite. The unchanged #24 suite is reused from the previous review.
The supervisor documentation branch's required `./verificar.sh` is recorded
separately in `supervisor-verificar.log`; it is not a feature-head test.

## Next owners

A applies R2-A5 on #26; B independently applies R2-B2 on #25. Neither waits for
the other. Both return additive exact-head draft handbacks and stop. Preserve
the old checkpoints and accepted decisions. R-1–R-4 mounting/wiring and client
widgets stay reserved for 3A/3B. No further feature packet is released here.
