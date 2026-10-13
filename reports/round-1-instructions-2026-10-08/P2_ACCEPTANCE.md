# Corrected P2 accepted for development integration

PR [#17](https://github.com/Andre07-hash/ARA-MAP/pull/17), exact head **`5d0844cfd678c2f7ec55ddb4b364275482d1a801`**, October 8, 2026. Supersedes the pending F1/F2/point-2 disposition in the earlier review; original reports remain historical.

**Accepted as the Round 1 prerequisite.** This is component acceptance, not permission to merge, deploy or enable operators on the current screen.

## Re-review

- Read the correction diff against originally reviewed `1e27715afc74cfe342b1c209d2881c4f05ffef02` and appended handback. F1 now catches controlled busy errors in initial authentication acquisition and handler work; shared database boundaries translate actual lock exceptions. No automatic retry or advisory-lock removal.
- Independently ran `tests.test_roles_y_bases` from an exact-head disposable archive: **58 tests passed, no skips**, with real SQLite and a fresh UTF-8 Postgres 17 database. Includes dispatcher advisory-lock contention, write-boundary row contention, classification controls and the existing authorization/race matrix. [Summary](evidence/p2-role-matrix-summary.txt).
- Repeated the original real **30-second** contention reproduction, adding explicit assertions for HTTP status/body, unchanged row count and retry success: **503**, `detalle.code = ocupado`, **30.00 seconds**, unchanged base count, **200** after lock release. [Result](evidence/p2-real-timeout.json), [reproducer](reproduce_corrected_timeout.py). It requires an explicit disposable test database and a separate exact-head source directory; never use production configuration.
- Exact-head `./verificar.sh` passed: **812 Python tests, 99 Postgres-only skips** in the no-database suite, full Python **3.9.6** suite, and JavaScript. [Output](evidence/p2-verificar.txt). The independent Postgres run in this closeout was the targeted 58-test module, not a repeated full 812-test Postgres suite.
- GitHub's full Python/disposable-Postgres and JavaScript checks are green on this exact head: [run 37855959400](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37855959400).
- F2 now explicitly withdraws safe rollback to older role-ignorant code; recovery uses the reviewed explicit-target CLI and role-aware code before traffic switches. No purported validated application rollback remains.
- Point 2 correctly limits the transaction guard to SQLite and requires `db.escritura()` on both backends. Non-SQLite connections are not certified safe merely because `en_escritura()` returns true.

No new application code was written by the supervisor. No hosted/operator UI acceptance, real account change, migration or deployment was performed. The next packets must preserve these boundaries. Existing accounts defaulting to operators, named administrator bootstrap and an operator-capable screen remain release gates.
