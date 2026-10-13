# Team A — bounded 1A correction 2

Read this folder's `START_HERE.md` and independent probe outputs. This continues
your existing PR #22 at `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037`; do not restart
Round 1 or open a replacement feature PR.

Your SQL attention correction is accepted. The new `VALOR_FUERA_DE_RANGO`
warning is approved as a non-blocking technical guard, with the clearer message
and interpretation specified in the review. Do not introduce a business range,
reject/clamp stored values or change publication requirements.

Correct the three remaining 1A findings:

1. **A1:** honor the original field-only request hash for legacy same-actor
   `operation=create` retries, preserving current reauthorization, fresh output,
   scoped hashing and changed-body conflict behavior.
2. **A2:** enforce current-base custom projection within stored history diffs,
   including nested before/after data. The probe uses seeded history, not a
   current custom-edit API. This read-side safeguard is explicitly required in
   1A; implement it without starting custom editing or UI work. Preserve full
   admin audit and hidden stored values. Document the supported audit shape.
3. **A3:** reject invalid scalar types/nonfinite or unrepresentable numbers and
   malformed cursor IDs/structure before SQL binding, consistently returning
   the documented 422 on both databases. Preserve valid pagination and scope.

Keep the original ownership: terrain API/domain/repository and dedicated tests.
No B modules, attachment interfaces, schema changes, baseline edits, renderer,
HTTP file handlers, cloud or UI expansion. Baseline #20 stays pinned at
`1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`. Accepted P2 invariants remain binding.
If a genuine prerequisite requires changing that scope, report the narrow
reason before doing it.

Add failing regression cases first, then verify the acceptance cases in
`START_HERE.md` through actual HTTP dispatch on SQLite and disposable Postgres.
Use synthetic data only. Keep Python 3.9 compatibility. Run the repository's
required verification and exact-head CI; avoid rerunning unrelated performance
matrices unless your changes affect their claims.

Append a correction-2 section to your existing handback report. Return the exact
new head, baseline head, changed files, A1/A2/A3 closure evidence, warning wording,
commands/results/skips, CI run and remaining limits. Keep changes additive on
the existing draft PR. Stop for supervisory review. Do not start 2A, merge or
deploy.
