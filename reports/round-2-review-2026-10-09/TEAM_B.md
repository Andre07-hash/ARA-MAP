# Team B — bounded correction 1 to packet 2B

Continue **PR #25**, additive to `2ea602a940462fe8bb7d8f0208e0e1dbee19603e`.
Keep baseline #24 at `7117f57f0c52c092d421e5d4bacbcf068f8a65d0` and preserve
#23/#21. Read START_HERE.md here, especially R2-B1.

Correct the new HTTP integer parsing for `limite` and `desde`: superscript
`²` currently passes isdigit() then crashes int(), producing 500 on SQLite
and Postgres. Use explicit bounded ASCII decimal validation or an equivalent
safe parser; retain controlled existing errors and legitimate bounds/defaults.
Apply the fix to every shared-limit caller and inspect analogous new parsing.
Do not hide arbitrary application exceptions with a generic validation catch.

Reproduce the supplied probes before correction. Add real HTTP regressions
for superscript/other Unicode numerals, signs, empty/oversized input and valid
limits/aligned offsets on both databases. Keep session/capability precedence,
per-resource non-disclosure, no writes on rejected requests, geometry hashes/
chunks and lifecycle behavior unchanged. Run the affected HTTP suite, Python
3.9 and applicable lint/types plus required publication gates and exact-head CI.

Your R-5 dispatcher finding is confirmed and explicitly assigned to A; the
independent review also reproduced foreign-Origin and invalid-Host cases.
Do not patch shared dispatcher/auth/schema, consume A's unreviewed feature,
or wait for A before returning your own correction. Update the integration
request to point to this disposition and retain R-1–R-4 for eventual 3A.

No need to repeat the unchanged renderer/research/large-memory matrices.
Keep evidence labeled HTTP harness, not application-mounted acceptance.
Return the same draft PR, exact code/final heads, concise correction report and
before/after evidence. Stop; no 3B, PR/main merge or deployment.
