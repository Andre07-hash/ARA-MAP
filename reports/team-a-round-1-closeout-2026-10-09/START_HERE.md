# Team A correction 2 and Round 1 prerequisite baseline — closeout

GitHub heads checked 2026-10-09 at 14:28 UTC; exact-head CI and unchanged
B heads confirmed during the review through 14:32 UTC.

## Decision

**Accept packet 1A at PR #22 head
`1ef2238766eae3e111c031b4fa24f9d849ef4753`. A1, A2 and A3 are closed.**
The rewritten `VALOR_FUERA_DE_RANGO` warning and bounded history cursor are
accepted within this correction; no schema change or new business rule.

**Accept the prerequisite integration baseline at PR #20 head
`1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`.** This combines the previously
accepted P2, parser, local/fake storage and E1 renderer, not the new 1A/1B
feature branches. Do not describe it as tested integration of #22 with #23.

No further Round 1 correction is requested from either team. B's #23 remains
accepted at `a9dc8af8cc511bde0a67168da335398353b80aa6`; research #21 remains
accepted **as research only** at `5e9ed42ef740fcee881c54e011172fae9c6f209b`.
All four PRs were open drafts. Main remains
`09452fd26d38319567dce28a89db100ea61c739a`.
This review releases no 2A/2B, main merge, deployment or E5 integration.

## Correction review

Reviewed the delta from `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037`, its
surrounding authorization/read/write paths, the new tests and §10 of
`reports/team-a-master-record-backend-2026-10-08/START_HERE.md` at the final head.

| Finding | Closure |
|---|---|
| A1 | Scoped creates retain their scoped hash; the same-actor global legacy fallback compares the normalized legacy field hash instead. Replays return an ID that is reauthorized and read freshly, never the stored old DTO. Tests cover current version, unchanged row counts, changed-body conflict, actor isolation and demotion. The original HTTP probe now returns 200 without a second record on both databases. |
| A2 | Non-admin history projects a documented scalar before/after shape using core fields and current-base live custom definition IDs. Unknown/nested shapes and extra keys do not pass through. Tests cover transfer/back, retirement, source/destination access, private response projections and unchanged full admin audit. The original seeded hidden-history probe is clean on both databases. Current core writers still do not generate custom diffs; 2A must use the documented supported shape. |
| A3 | Cursor UUIDs, matching sort, scalar types, finite numeric values and valid text are checked before binding. Original wrong-type/overflow probes all return controlled 422 on both databases. Tests retain null/tie traversal, both directions, scope and valid finite edges. The extra history-cursor bound uses 1–18 ASCII digits; it prevents incompatible/oversized inputs without changing the schema. |

The numeric warning now explains inability to check consistency automatically;
it does not claim the value is outside a real-world price range. It remains a
non-blocking technical warning, with input values and publication rules preserved.

## Independent evidence

Run from fresh archives of the exact reviewed commits, without changing the
working branch or application files. Fictional data only; Postgres 17 used a
new disposable UTF-8 cluster, stopped after verification.

- PR #22: **54/54** record HTTP tests on Python 3.14.5, SQLite and Postgres,
  no skips: [record-tests.log](record-tests.log).
- PR #22: **28/28** SQLite record tests on Python 3.9.6:
  [record-python39.log](record-python39.log).
- Reused the unchanged [original supervisor probes](../team-a-1a-review-2026-10-08/reproduce.py)
  against the corrected head. All three groups pass on both databases:
  [summary](probe-summary.log), [SQLite observations](probes-sqlite.jsonl),
  [Postgres observations](probes-postgres.jsonl). Corresponding stderr logs
  preserve the actual HTTP responses. The richer new regression tests above
  supplement, rather than replace, these original probes.
- Baseline #20: **987/987** Python tests with SQLite and disposable Postgres,
  no skips: [full baseline log](baseline-full-postgres.log).
- Baseline #20: **987 tests, 99 Postgres skips**, Python 3.9.6 without its PG
  driver: [Python floor log](baseline-python39.log).
- Baseline #20: **120/120** JavaScript tests:
  [JavaScript log](baseline-js.log).
- Baseline ancestry and component-tree comparisons independently confirm the
  accepted P2/parser/storage/E1 pins. Changes from P2 are confined to their
  component paths, reports and the explicitly reviewed parser test repair:
  [component checks](baseline-components.log). That repair stops treating the
  schema's literal file type `kmz` as a parser import; no parser behavior changed.

Portable test entry points, from the corresponding exact-head archive:

```sh
# Use ARA_MAP_TEST_DATABASE_URL only for an explicitly disposable UTF-8 DB.
python -m unittest tests.test_registros_maestra -v  # PR #22, SQLite + PG
python3.9 -m unittest tests.test_registros_maestra.RegistrosSqlite -v
python -m unittest discover -s tests -t .         # baseline, SQLite + PG
node --test tests/js/*.test.mjs                    # baseline
```

## External evidence and limitations

- [PR #22 exact-head CI run 37937475616](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37937475616)
  is green; its Python log confirms **1,041 tests**. This full feature suite
  was not independently repeated here: the correction review used focused
  tests/probes, while the newly accepted baseline received a full independent run.
  [CI receipt](github-ci.json), [PR #22 receipt](github-pr22.json),
  [baseline receipt](github-pr20.json).
- No new browser, load, hosted, cloud-storage or complete employee-workflow
  acceptance. Reuse unchanged accepted E1 evidence; do not relabel it as a new
  browser integration run. Research visual/memory limits remain in B's closeout.
- Baseline tests emit some existing ResourceWarnings but finish successfully;
  no newly failing test was waived.
- Publication gate `./verificar.sh` passed on the **supervisor documentation
  branch**: 672 Python tests with 29 Postgres skips, Python 3.9.6 suite and
  JavaScript checks, not either reviewed feature head. See
  [supervisor-verificar.log](supervisor-verificar.log); it is separate evidence.

## Next owners

Both teams preserve their accepted draft heads and stop pending the next
explicit bounded packet. Do not reopen closed findings or resend Round 1.

The supervisor owns preparation of the next instructions: A remains the
application integrator and owner of table/custom-column/base/grant work; B
retains attachment HTTP and bounded-geometry ownership. The next instructions
must define the tested checkpoint joining accepted 1A and 1B, preserve the
frozen #20 baseline, and specify dependencies before any 2A/2B work begins.
This closeout itself is not an instruction to assemble or start those features.
