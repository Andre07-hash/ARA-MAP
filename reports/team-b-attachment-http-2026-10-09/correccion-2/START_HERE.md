# Packet 2B — correction 2 (R2-B2, test only)

Review: `reports/round-2-corrections-review-2026-10-09/` at
`f2939edc4f680fab596605e51a6bd8a48f792ea4` (START_HERE.md, TEAM_B.md). Same
draft PR #25, additive to `704d8b8745b79f7b72f35350079ccd788e6d2e0a`.
R2-B1 is accepted and not touched. R-7 is already fixed in A's current head,
so nothing is requested from A here.

| What | Commit |
|---|---|
| Reviewed head | `704d8b8745b79f7b72f35350079ccd788e6d2e0a` |
| Test correction (code head) | `4dcf66551b09c3674db013cc68083d0c4f231787` |
| Final head | the head of PR #25, stated in its description (only this report follows) |
| Unchanged | #23 `a9dc8af8cc511bde0a67168da335398353b80aa6`, #21, frozen #24 `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` |

The only file changed is `tests/test_archivos.py`: the inherited
`test_l2_pending_privacy_is_one_rule_on_every_read_surface` plus two new
tests. No production code changed, no HTTP contract changed, no dispatcher
patch, and A's branch is not consumed.

## The false positive

The test converted the hidden byte count to `"145"` and asserted it was
absent from `repr()` of the whole response. A public event UUID such as
`00000145-0000-4000-8000-…` contains those digits, so the test failed even
though the version, actor and details were correctly redacted.

## What the test asserts now

`assert_private_view(view, pending, state, hidden)`, used for another
operator and another admin at every point the old test checked:

1. **Exact projection.**
   - The listing's and the summary's `ultima_version` equal
     `{"estado": state, "propia": False}`.
   - History equals the durable `archivo_evento` rows projected field by
     field. Only `id`, `accion` and `at` stay public; `revision`, version,
     attempt, geometry and base ids and `actor` are `None`; `details` is `{}`;
     `privado` is `True`; `version` is the generic status.
   - Any extra or unredacted field fails the equality.
2. **Leak search over every field** of the full listing item, all events and
   the full summary row (`leaked_paths`), wider than before:
   - The file name, version id, uploader id and uploader display name (the
     last is new) are searched inside every string.
   - The byte count matches only a whole value: the number itself, or its
     decimal text as the entire string. The same digits inside a public UUID
     or a timestamp are not a leak.
   - A failure names the exact path, for example `$[0].tamano`.

Kept: the uploader still sees name, declared size, details and actor, and the
expiry boundary (−1 s, equality, +60 s). The live lease during completion now
uses the full structured check. Out-of-scope reads stay absent after
revocation and after transfer, and the view is private again once back in
scope. The durable audit row still holds the name.

New tests (both databases, via `LifecycleChecks`):

- **Collision regression**
  (`test_l2_privacy_check_ignores_public_ids_that_contain_hidden_digits`).
  `uuid.uuid4` is patched deterministically during the upload, so every
  public event id contains `145`. The test asserts that the collision is
  really present and that the old substring rule would have matched it. The
  structured check then passes.
- **Negative controls** (`test_l2_privacy_check_still_detects_real_leaks`).
  A real private view passes. Eight injected leaks each fail, and the failure
  message is checked for the specific field or path:
  - the size in `ultima_version`;
  - the size as text on the listing item;
  - the name in the history details;
  - the uploader as the history actor;
  - the version id in a history event;
  - the version id on the summary row;
  - the uploader's name inside a summary string;
  - the size nested two levels deep.

  The finder is also checked directly: a UUID or timestamp containing the
  digits is ignored, while `145.0`, `"145"` and an embedded file name are
  each reported.

## Before / after

| Evidence | Before (`704d8b8`) | After (`4dcf665`) |
|---|---|---|
| Review's `probe_edges.py privacy sqlite` | assertion failure: `'145' unexpectedly found` (public UUID) | pass |
| Review's `probe_edges.py privacy postgres` | same failure | pass |
| Leaky-code mutations (`mutaciones_privacidad.py`), SQLite | n/a | control passes; 6/6 mutations fail |
| Same, Postgres | n/a | control passes; 6/6 mutations fail |

The mutations patch the real read path during one run of the main test:
- history keeps the private details;
- history keeps the uploader;
- the listing projection adds the byte count;
- the listing projection adds the file name;
- the privacy rule is removed everywhere;
- the listing item carries the byte count as text, which only the leak
  search can catch.

Each fails at the expected assertion (`evidencia/mutations-*.jsonl`). The
probe's stderr is empty in every run.

## Verification at code head `4dcf665`

Local container, synthetic data, disposable Postgres 16.15.

| Check | Result |
|---|---|
| `tests.test_archivos` + `tests.test_archivos_http` + `tests.test_composicion_ronda2`, SQLite + Postgres | 145/145 OK, 0 skipped |
| same, Python 3.9.25 | 145 run, OK, 71 Postgres skips |
| Full suite, SQLite, Python 3.13 | 1,186 run, 196 skipped, 1 environmental failure |
| Full suite, SQLite, Python 3.9.25 | 1,186 run, 196 skipped, 1 environmental failure |
| Full suite, disposable Postgres | 1,186 run, 0 skipped, 1 environmental failure |
| JavaScript | 120/120 |
| `mypy server/` | clean, 51 files |
| `ruff` on B's files, `tests/test_archivos.py` and this folder | clean |
| `ruff check server/ tests/` | only the carried-in #22 finding (`tests/test_registros_maestra.py:562`) |

Limits:
- The environmental failure is the disclosed
  `test_the_system_python_has_no_openpyxl_of_its_own`: this container's
  system Python has openpyxl.
- `./verificar.sh` was not run as a script (no zsh); its components were run
  directly.
- Exact-head CI is linked in the PR.
- No browser, research or memory rerun, since this is a test-only change.

Stopped for review: no 3B, no merge, no deployment.
