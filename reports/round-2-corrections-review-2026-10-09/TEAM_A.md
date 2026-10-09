# Team A — bounded correction 2 to packet 2A

Continue existing draft **PR #26**, additive to
`cda5c20580179abcd8673010797a9975b1b7a06d`. Read START_HERE.md here and use
`probe_edges.py framing` against that exact head. No 3A; preserve frozen #24
`7117f57f0c52c092d421e5d4bacbcf068f8a65d0` and all prior accepted PRs.

Your original R2-A1–A4 reproductions are corrected. B's R-7 (`²`, `-1`, body
limit) is already fixed in your current dispatcher and independently checked;
do not redo it. The remaining **R2-A5** is the same framing boundary with empty
or repeated header fields:

1. Inspect all occurrences of Content-Length and Transfer-Encoding, not just
   the first truthy value. Distinguish absence from an explicitly empty field.
   Reject conflicting/ambiguous lengths; conservatively rejecting repeated
   Content-Length fields is acceptable. Unsupported Transfer-Encoding must be
   rejected whenever the field is present, including empty/duplicated values.
2. Before any body read, return controlled 400 and close for those malformed
   inputs. Preserve the current 413 size gate, plain bounded ASCII parsing,
   existing auth/refusal precedence and early-close strategy. Do not drain
   untrusted bodies or change policy, schema, B's handlers or route mounting.
3. Add real raw-socket regressions for the three supplied cases and reversed
   duplicate orders, comma-combined/empty lengths and TE plus CL. Assert exactly
   one response and closure, with no second public-config execution. Preserve
   valid absent/zero/nonzero lengths, legitimate sequential keep-alive and the
   prior read-only/Origin/Host/negative/non-ASCII/oversize cases.

Reproduce before/after, run affected dispatcher/HTTP checks and Python 3.9,
lint/types and required repository verification before push; exact-head CI
must be green. Unchanged browser/memory/renderer evidence can be reused; no
new open-ended research, Postgres browser matrix or screen-reader gate is
assigned. B owns the flaky inherited lifecycle assertion; do not edit it.

Return same draft PR, code/final full SHAs, short correction report with raw
evidence and limitations. Stop for review. No force push, merge or deployment.
