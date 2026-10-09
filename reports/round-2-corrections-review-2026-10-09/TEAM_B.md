# Team B — bounded test correction 2 to packet 2B

Continue existing draft **PR #25**, additive to
`704d8b8745b79f7b72f35350079ccd788e6d2e0a`. Read START_HERE.md here.
**R2-B1 is accepted.** No further HTTP parser implementation is requested.
Your R-7 is already fixed by A's current head; A owns the residual malformed
header cases R2-A5. Do not patch the dispatcher or consume A's moving branch.

**R2-B2:** correct the false positive in the inherited
`tests/test_archivos.py::test_l2_pending_privacy_is_one_rule_on_every_read_surface`.
Editing this B-owned test in #25 is explicitly authorized despite its origin
in 1B. Keep #23 `a9dc8af8cc511bde0a67168da335398353b80aa6`, #21 and frozen #24
`7117f57f0c52c092d421e5d4bacbcf068f8a65d0` unchanged. No lifecycle production
code or HTTP contract change is needed for this finding.

1. Run `probe_edges.py privacy sqlite` and `privacy postgres` here against the
   reviewed head. The existing test fails even though the version, actor and
   details are correctly redacted: a public event UUID contains the byte-count
   string `145`. PG requires a fresh disposable database.
2. Replace substring searches over the entire repr with structured assertions
   for the allowed private projection. Preserve verification that filename,
   byte count, uploader identity and version metadata cannot leak through list,
   summaries or history; retain expiry/live-lease/revocation/transfer/audit-row
   checks. Do not merely delete assertions, choose a larger fixture, rerun
   random tests until green or mark anything skipped.
3. Include a deterministic public-ID collision regression and negative controls
   demonstrating that actual leaked metadata is still detected. They should
   fail for the right reason, not because of unrelated identifiers/timestamps.
4. Run the affected lifecycle suite and HTTP/composition tests on SQLite and
   disposable Postgres, plus the Python 3.9 floor and required repository
   verification before push. Exact-head CI must be green. No browser/research
   rerun is needed for a test-only change; disclose any environment limitation.

Return the same draft PR, code/final full SHAs and a concise before/after
handback. Work independently of A, then stop for supervisory review. No 3B,
force push, merge, deployment or change to accepted checkpoints.
