# Team A — bounded correction 1 to packet 2A

Continue **PR #26**, additive to `517223668405c1d4feb2deffbd2d16a072395fd9`.
Preserve #24 `7117f57f0c52c092d421e5d4bacbcf068f8a65d0`, #22 and #20.
Read START_HERE.md here for exact findings/evidence. Do not begin 3A.

1. **R2-A2 first:** eliminate retained private table/dialog state across expiry,
   logout and account/role/scope transitions. Follow the existing clear-on-loss
   contract, not the old keep-unsaved-form-behind-login behavior. Include all
   private dialog lifetimes, queued saves and delayed callbacks. Prove a
   zero-grant second account cannot see the prior account's comment, even
   though its backend request is correctly denied already.
2. **R2-A1:** repair A-owned dispatcher refusal framing, including read-only,
   foreign Origin and invalid Host, and audit analogous early exits. Closing
   unread-body connections is the bounded approach. Add real socket tests;
   do not claim an auth bypass merely from the public-config reproduction.
   This shared-file fix is assigned now, not deferred to 3A. Do not mount B
   handlers, change schema/auth policy, or modify B's branch as part of it.
3. **R2-A4:** preserve a second cell's active editor/text/focus when the first
   save returns; test real successful and conflicting responses with a
   deterministic barrier, plus subsequent keyboard save/cancel.
4. **R2-A3:** validate safe Unicode/text and exact calendar-date forms before
   hashing/writing. Real HTTP tests on both databases must return controlled
   validation and prove atomic non-mutation; keep valid Unicode working.

Add the previously missing real-browser cases: expiry with unsaved cells,
different-account sign-in, revalidated identity/role change, open private
detail/history/admin dialogs and responses in flight. Include a fresh same-user
relogin under changed grants and ensure old queued edits do not execute under
a new identity. Re-run the affected integrated journeys, not mocks alone.

After disposal fixes, perform a bounded warmed-up memory check with several
equal batches of page/base/dialog transitions (for example three batches of
100), identical final UI/GC conditions, retained heap and node counts. Report
whether growth plateaus or identify retained owners; do not label the existing
1 MB observation a proven leak and do not start open-ended memory research.
Run the configured coverage check once at the corrected feature handback and
disclose any unmet gate; full affected suites/Python floor/lint/types and
exact-head CI still apply. No requirement to duplicate all browser journeys
against Postgres or claim screen-reader coverage that was not performed.

Keep the administrator's Inventario landing page; that decision is accepted.
No redesign, new feature packet, upload widget, map integration or deployment.
Return exact code/final heads, same draft PR, correction report, reproductions
before/after and evidence/limits. Stop for supervisory review.
