# Team B — accept 1B; bounded research correction 2

Read this folder's `START_HERE.md` and independent edge-probe results.

**1B is accepted at `a9dc8af8cc511bde0a67168da335398353b80aa6`. L1–L6 are closed.**
Preserve PR #23 and its unchanged baseline
`1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`; do not make additional lifecycle
changes for this request. Its corrected service interfaces are the handoff for
later consumers. Acceptance is not merge/deployment or 2B authorization.

Continue **only research PR #21**, additively from
`68077cc366dd3e1885da36b8f5c7223093e4bd63`, in the existing
`reports/team-b-display-memory-budget-2026-10-08/` folder:

1. **R1a:** layer admission must not evict/release the prepared body that the
   layer is about to retain. Protect ownership before pressure callbacks;
   unwind on refusal/failure. Audit prepared arrays reachable through live
   layers, not just those still present in the registry. Cover cache-hit and
   preparation-completion paths, sharing, pressure, replacement and teardown.
2. **R2a:** a synchronous failure during a reservation's memory-relief callback
   must stop the interrupted client operation. No subsequent copy/reservation
   may survive on the failed client, no post after termination, and no `listo`
   result. Test forget failure induced by a new copy request and explicit retry.
3. **R1-test:** replace the 16-GiB allocation assumption with an injected,
   deterministic small-fixture failure. Keep the release assertion.

R3's finite queue/retained-body contract and R4's deterministic cancellation
test are closed; preserve them. No new product budget/renderer policy is
requested. No application renderer, baseline, schema/auth/store/parser, HTTP,
UI or hosted changes.

Reproduce the supplied edge cases before fixing. Add meaningful regression
tests that fail on the reviewed code, rerun the prototype tests, and append
targeted browser evidence for tight-memory cache-hit/new-body admission,
two-map sharing/replacement/teardown, pressure-induced worker failure and retry.
Exercise the audit's new negative control: a live layer retaining an untracked
prepared body must be detected. Rerun other affected scenarios, not unrelated
historical matrices without cause. Do not claim a measured visual/timing result
is current if the change invalidates its inputs.

Preserve all historical measurements and RGBA limitations. Supersede the
unproven complete-accounting claim until the corrected audit and pressure
cases establish it. Keep managed bytes, caller-owned bodies, browser transient
memory and total process memory clearly distinguished.

Return exact new code/test and final heads, changed files, three closure
results, test commands/results/skips, browser version and evidence, remaining
limits and exact-head CI. Follow the repository's verification gate; disclose
the existing container zsh/packaging limitations if still applicable. Stay on
the existing draft PR; no force push. Stop for supervisory review. No later
packet, merge or deployment.
