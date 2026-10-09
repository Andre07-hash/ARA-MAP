# Team B — packet 2B accepted, correction 2 closed

GitHub checked **2026-10-09 19:40 UTC**. Reviewed draft PR #25 at
**`bf4c6a694ca95087368bb2d89325d7a240a7b676`**, additive to the reviewed
`704d8b8745b79f7b72f35350079ccd788e6d2e0a`. The test commit is
`4dcf66551b09c3674db013cc68083d0c4f231787`; the final commit adds only reports.
[Exact-head CI](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37980122942)
passes Python/disposable Postgres and JavaScript. PR remains open and draft.

## Verdict

**R2-B2 closed. Packet 2B is accepted at this exact head for its HTTP-harness
scope, not for app-mounted endpoints or the complete attachment UI.** R2-B1
remains closed. No further B correction is requested.

The sole non-report delta is `tests/test_archivos.py`. Production directories
`server/`, `web/` and `api/` are identical to the preceding reviewed head.
The test now compares the permitted history projection exactly, preserves
the generic private version on list/summary and checks hidden metadata over
the complete response values without confusing a byte-count substring in a
public UUID with an actual disclosed value. Original expiry, live-lease,
revocation, transfer and durable-audit assertions remain. Uploader and negative
control coverage is stronger; the test was not skipped or merely weakened.

## Independent verification

Exact final-head archive, synthetic fixtures, macOS; Python 3.14.5/3.9.6;
fresh disposable UTF-8 Postgres 17. No production data or application edits.

- Lifecycle + HTTP + composition: **145 tests, zero skips, OK**, SQLite and
  Postgres (`affected-sqlite-postgres.log`). This includes the deterministic
  collision regression and eight injected-leak negative controls per backend.
- Python 3.9 affected lifecycle: **82 run, 41 Postgres skips, OK**
  (`lifecycle-py39.log`). The unchanged HTTP Python-3.9 evidence from the
  previous review is reused rather than rerun.
- The supervisor's unmodified `probe_edges.py privacy` now passes on both
  databases (`collision-*.jsonl`). Before-fix failures remain in the preceding
  review folder; the unchanged old head was not run again.
- Independently executed B's `mutaciones_privacidad.py`: unmutated control
  passes; **all six deliberate leaky-production-path mutations fail** on each
  backend, at the expected structural or hidden-value assertions
  (`mutations-*.jsonl`). Those recorded failures are successful negative
  controls, not outstanding application regressions.
- Ruff passes on the changed test and mutation script. The supervisor branch's
  required `./verificar.sh` is logged separately (`supervisor-verificar.log`);
  it is not evidence for the feature head.

The feature's full 1,186-test runs, environmental openpyxl failure, JS and
mypy results are developer-reported, distinct from the independent focused
checks above and green GitHub CI. No full feature suite, browser, renderer,
memory matrix or hosted environment was rerun for this test-only delta.

## Preserved state and next action

#23 remains `a9dc8af8cc511bde0a67168da335398353b80aa6`, #21 remains
`5e9ed42ef740fcee881c54e011172fae9c6f209b`, and frozen #24 remains
`7117f57f0c52c092d421e5d4bacbcf068f8a65d0`; verified remotely.

A now has observed head `32a2a55e4a7417499cc384109bd44666e7a568cb` on #26.
**That new head was not reviewed in this B closeout.** R2-A5 therefore remains
pending supervisory verification, not presumed fixed or presumed still
reproducible there. The prior accepted A corrections are preserved.

B should preserve #25 and wait for the next bounded packet, without starting
3B or changing production code. Next supervisor action: review A's exact-head
R2-A5 handback, then prepare the next integration/client instructions when
the review gates are satisfied. No 3A/3B, merge or deployment is released here.
The owner's local fictional-data preview is unaffected by these checks.
