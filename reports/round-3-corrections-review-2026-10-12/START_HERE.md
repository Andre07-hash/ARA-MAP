# Round 3 correction review — B closed, combined acceptance still pending

Repository: Andre07-hash/ARA-MAP. Checked 2026-10-12, 16:58 UTC.
Previous correction instructions: `341c83036d7a861e88a1b3d28f6e3359ada057a2`.
This review preserves those instructions and all previously accepted decisions.

## Decision

**Accept Team B's five corrections R3-B1–R3-B5 at
`b2ac9bd176043fc4b1625b13993f8f21407dc978`, within 3B's component scope.**
All five original independent client observations now show corrected behavior;
the original full-app upload-404 probe now removes the row/detail/private name.
B stops and preserves this candidate. No further B work is assigned here.

**Round 3 as a combined application is not accepted yet.** A still owns the
recorded ordinary merge of this exact B candidate, final combined evidence,
and a newly reproduced **R3-A2 read-only revalidation defect**. See TEAM_A.md.
R3-A1 (query batching) is a different, deferred optimization; do not conflate
it with either R3-A2 or B's closed findings.

No 4A/4B, GitHub PR/main merge, deployment, cloud provisioning or real data.

## Exact versions and GitHub verification

| Item | Head / disposition |
|---|---|
| Reviewed B before corrections | `01d64541e929009ea2d149e3c6f5980805c76c73` |
| B correction code | `f9510158024e2ef57eff70aaa8ea97eb9c29436c` |
| B corrected final / draft #28 | `b2ac9bd176043fc4b1625b13993f8f21407dc978` |
| Exact B CI | run 38268732577: Python/disposable Postgres and JavaScript successful |
| A observed combined / draft #29 | `0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db`; still consumes old B `01d6454` |
| Frozen C1 / #27 | `49b782d147591236cc7f311c7e0de1948ad5258e`, unchanged |

The supervisor fetched the branches and checked the delta. B changed only its
five client modules, two test files and correction report; no server, schema,
shared bridge, A host or renderer edit. History is additive. No A feature
branch was merged into B. Previous findings/evidence remain historical.

## Independent verification

Exact B archive at `b2ac9bd`, macOS, Node 23.7, Chrome 154, synthetic data,
loopback and disposable SQLite/local disk. The unchanged Python service and
Postgres matrix were not rerun locally for this JS-only delta; exact-head CI
is independently checked, not conflated with local verification.

| Check | Supervisor result |
|---|---|
| All B JavaScript tests | **210/210**, no skips |
| Original `probe_client_edges.mjs` | all five observations corrected, below |
| B's mounted scope/cancellation browser suite | **8/8**, no page errors |
| B's correction mutation runner | unmodified control passes; all 10 mutants detected (nonzero test exit) |
| Original real-app upload-404 probe, diagnostic combined archive | 404, row 0, open detail 0, private filename absent |
| New archive/read-only combined probe | 409, picker visible and enabled, detail `soloLectura=0`: **R3-A2** |

Original client observations after correction:

- B1: `cancelCalls=[]` after upload destruction.
- B3: pending transient failure is `interrumpido`, cancellation reaches server
  once; incomplete completion is replayed, calls increase from 1 to 2.
- B4: maximum concurrent file reads is 1 with destruction during the first.
- B5: private scope ending during final digest yields AbortError, zero ready
  bodies, no active/waiting load after settlement.

The 8 mounted browser checks use the real server and administrator APIs:
revocation during completion/PUT, transfer, cancellation after scope loss,
archive preserving readable content and sending the host callback, close
during cancellation, live success/cancel control, no page errors. This confirms
B's interface behavior; it does **not** prove A applies every callback correctly.

The diagnostic combined archive is exactly A `0e9e2c1` with B's five production
modules from `b2ac9bd` overlaid using `git archive`. No application code was
authored and no feature branch was changed. It is **not** A's recorded merge
or final acceptance evidence. The full-story verification skill directed the
UI → API → data → UI checks; the combined walk stopped at the first newly
broken boundary, archive/read-only revalidation. A's full original 22-journey
run was not repeated here; its prior evidence and B's diagnostic run remain
separate from this focused check.

Evidence files here contain the actual local outputs. Node 23's default test
reporter leaves the mutation runner's parsed test-name arrays empty; the
recorded control/exit outcomes are what was checked, not an invented list of
failed assertion names. Supervisor-branch `verificar.sh` is separately required
before publication and is not evidence for the B feature tree.

## Handoff

- **B:** corrections accepted at the exact final head above. Preserve #28;
  wait for specific integration feedback. No 4B or unrelated batching.
- **A:** use TEAM_A.md here plus the preceding integration checklist. Merge
  the named B candidate if not already consumed, fix R3-A2 in A-owned host
  code and return the corrected combined draft #29/evidence.
- **Supervisor:** review A's additive host fix and exact combined candidate.
  Reopen B only if concrete new evidence requires a B-owned change.

Remaining limits stay explicit: local storage on one machine; current-page
map; one selected body; no production E5 or total-browser-memory guarantee;
query batching and the measured heap slope deferred; no screen-reader or
hosted validation. Closing an upload locally does not prove server rollback:
pending versions remain subject to the accepted cancellation/expiry lifecycle.
