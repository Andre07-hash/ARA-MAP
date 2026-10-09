# 2A accepted — correction 2 independently closed

Reviewed #26 at **`32a2a55e4a7417499cc384109bd44666e7a568cb`**, additive to
`cda5c20580179abcd8673010797a9975b1b7a06d`. GitHub heads rechecked
**2026-10-09 20:32 UTC**;
[exact-head run 37980805663](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37980805663)
passes Python/disposable Postgres and JavaScript. The PR remains a draft.

**R2-A5 closed; 2A accepted at the named head.** The only production delta
is `_read_body` in `server/app.py`: all Content-Length occurrences count,
explicit emptiness is not absence, any Transfer-Encoding field is rejected,
and parser-reported malformed header blocks are rejected rather than allowing
later hidden framing fields to disappear. Conservative rejection of equal
duplicate lengths is approved. Existing refusal precedence, body size ceiling,
valid keep-alive and the close-unless-read strategy are preserved.

Independent checks from an exact-head archive:

- Dispatcher + API suite: **39 tests, OK** (`a-focused.log`). Socket regression
  cases include the new 22 malformed-header inputs and valid sequential reads.
- Python 3.9: **5 dispatcher tests, OK** (`a-py39.log`).
- Unmodified supervisor edge probe: six cases return one response and close:
  **400, 400, 413, 400, 400, 400** (`a-framing.jsonl`).
- Original early-refusal probe: read-only, foreign Origin, invalid Host each
  return only **403** (`a-refusals.jsonl`). Probe stderr is empty.
- Ruff on the changed production/test files is clean (`a-ruff.log`).

No SQL or frontend changed in this delta: previous independent SQLite/Postgres
and real-browser evidence is reused. A's full 1,154-test Postgres run and
`verificar.sh` are developer evidence, not an independently repeated full
suite. GitHub CI is separately verified. The supervisor documentation branch's
own required verification is `supervisor-verificar.log`, not feature evidence.
No claim of surveying every HTTP parser leniency or hosted behavior is made.

B's 2B acceptance remains #25 **`bf4c6a694ca95087368bb2d89325d7a240a7b676`**:
see `reports/team-b-2b-closeout-2026-10-09/START_HERE.md` at supervisor commit
`b7f5fa83c1ef1f1d3c454365e7a939b586bfa9b6`. Its correction is already closed.

Old accepted PRs and frozen #24 are not modified. This accepts the table and
HTTP components, not their still-unbuilt combined file/map workflow. The
sibling START_HERE.md releases the next bounded pair at the owner's request.
