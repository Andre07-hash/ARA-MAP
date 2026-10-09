# Team B research correction 2 — independent closeout

GitHub receipt checked **2026-10-09 at 02:25 UTC**; A/baseline checkpoint
checked during the review at approximately 02:27 UTC.

## Decision

**Accept the corrected research handback at PR #21 head
`5e9ed42ef740fcee881c54e011172fae9c6f209b`. R1a, R2a and R1-test are closed.**
The earlier R3/R4 closures remain valid. There is no outstanding Team B
correction request from these reviews.

This is acceptance of a bounded research result, **not approval to integrate
E5**, a total-browser-memory guarantee, approval of visual differences, or a
release of packet 2B. Preserve the prototype and evidence separately.

Exact inputs:

- [PR #21](https://github.com/Andre07-hash/ARA-MAP/pull/21): diff reviewed from
  `68077cc366dd3e1885da36b8f5c7223093e4bd63`; code/tests
  `259303d761baacde7aeb63c1017c0a9eefc0f594`, final head above. Its final commit
  only adds/updates documents and evidence. All changes stay under
  `reports/team-b-display-memory-budget-2026-10-08/`. The research base stays
  `9da0ab10a344e66099d919f2da15d3a638e7292a`.
- Developer handback at that head:
  `reports/team-b-display-memory-budget-2026-10-08/CORRECCIONES_2_2026-10-09.md`;
  evidence in `correcciones-2026-10-09/ronda-2/`.
- [PR #23](https://github.com/Andre07-hash/ARA-MAP/pull/23) remains unchanged
  and accepted for 1B at `a9dc8af8cc511bde0a67168da335398353b80aa6`.
- Baseline #20 remains `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb`.
  A's #22 remains `f6cd6b2c45385d149f042c8eabd0e2a2e4db8037`; its correction-2
  instructions are unchanged. Do not infer delivery of a new A correction.
- #21 and #23 were still open drafts. No merge/deployment action was taken.

## Finding closure

| Finding | Reviewed correction | Independent result |
|---|---|---|
| R1a | Cache-hit construction pins before reserving the layer array; the preparation-completion path uses `crearFijada`. Refusal/failure unwinds the pin. `inventarioCapas` compares every unique prepared body reachable from a live layer against registry identity and sufficient pin ownership. | A 2,487 B budget retains the 2,408 B body and refuses its layer, with zero pins left; a 2,488 B budget admits both with exact accounting. Browser cache-hit/new-body pressure cases refuse truthfully and recover on the next render. A deliberately lost pin/evicted body is detected as 480,052 B outside the registry. |
| R2a | `asegurar` rechecks terminal state after synchronous budget relief, releases any new reservation and returns `fallido` before installing/sending. The reliever/controller stop on the failed client. | One failure notification, no post after termination, zero bytes/copies retained. Browser pressure-triggered forget failure settles to `sin_trabajador`; explicit retry recovers with a fresh worker. Both post-after-termination double behaviors are covered by passing unit tests. |
| R1-test | Small three-part fixture with an injected initializer failure replaces the platform-dependent 16-GiB allocation. Assertions retain reservation cleanup and add pin unwinding. | Exception observed; zero layer reservation after failure, zero pins on the registered body, and only its legitimate prepared-body reservation remains until teardown. |

The additional refusal-state correction is within scope: a layer that was not
constructed must not have its `sin_memoria` status overwritten with `listo`.
The E5-specific condition leaves E1–E4 behavior unchanged in the reviewed diff.
The browser cache-hit test exercises this actual MapCanvas path.

The audit now awaits worker statistics before synchronously reading the ledger
and owner counters, avoiding the previously split main-thread snapshot. Test
filler reservations are explicitly reported, not silently treated as real
allocated bytes. The handback appropriately narrows its claim to evidence over
the scenarios run, not proof for all interleavings.

The original edge script manually reconstructs the **old unsafe caller order**.
That first probe is therefore still a useful audit negative control, not a
test of the corrected constructor sequence. The adapted probe uses the actual
pin-first path; review of both MapCanvas paths and the browser test verifies
that adaptation is legitimate. Future integration must retain this ownership
ordering rather than call the low-level constructor without it.

## Independent evidence

- **37/37 prototype tests, twice**, Node **23.7.0**, no failures or skips:
  [first run](prototype-tests.log), [repeat](prototype-tests-repeat.log).
  This includes the audit negative control, sharing/two-map/pinned-raster
  cases, replacement/teardown, deterministic failure and both R2a worker doubles.
- Independently executed the developer's adapted scripts after inspecting
  their changes from the supervisor reproducers:
  [three edge probes](adapted-edge-probes.jsonl),
  [four original adapted probes](original-adapted-probes.jsonl).
- Independently ran the exact-head browser harness for **`presion,cambio,reinicio`**,
  Chrome **154.0.8037.99**, headless on this Mac. All checks passed:
  [browser log](browser-targeted.log),
  [pressure evidence](browser/memoria-presion.json),
  [resize evidence](browser/memoria-cambio.json),
  [reset/teardown evidence](browser/memoria-reinicio.json).
  Pressure tests include the deliberately failing audit control; its expected
  error is evidence of detection, not an unexplained clean-audit claim.
- Browser inputs were fresh archives of accepted B-2
  `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` and E1
  `eed9a4cb404406b8b261803c38947e8297a5edec`. Existing generated fictional case
  bodies were reused only after SHA-256 checks against both their generated
  and committed manifests: [input checks](browser-input-checks.log).
- Browser reset retained worker-copy charges until acknowledgement, kept the
  other map intact and ended with the shared ledger at zero after teardown.
- [Exact-head GitHub CI run 37874302919](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37874302919)
  is successful for Python/disposable-Postgres and JavaScript. That repository
  CI is separate from these prototype tests and targeted browser executions.

Portable commands, from an isolated archive of the reviewed head:

```sh
node --test reports/team-b-display-memory-budget-2026-10-08/pruebas/memoria.test.mjs
node reports/team-b-display-memory-budget-2026-10-08/correcciones-2026-10-09/sondas-bordes.mjs
node reports/team-b-display-memory-budget-2026-10-08/correcciones-2026-10-09/sondas.mjs
# Set B2_DIR, E1_DIR and CASOS_DIR to the verified inputs above.
# Provide playwright-core and Chrome, and EVIDENCIA for output JSON.
node reports/team-b-display-memory-budget-2026-10-08/memoria.mjs presion,cambio,reinicio
```

## Preserved limits and later integration gates

1. This review did **not** repeat the full 24-case browser matrix, pixel/click
   matrix or timing runs. Their new Chromium-141/Linux results remain developer
   evidence. The historical visual limitation is unchanged: **8/12 RGBA-identical
   in Chromium 141; historical 4/12 in Chromium 154**. The targeted Chrome-154
   run here is not a new pixel-identity measurement. Coverage/click agreement
   does not waive pixel identity.
2. The developer's `cambio` run audited before Leaflet had applied its final
   resize. Our run did reach the final 900×500 viewport step, with both bitmap
   and padded canvas at **2160×1200**, DPR 2. This adds one observed final-size
   result; it does not make the harness's completion condition deterministic.
   Before claiming repeatable resize acceptance during a future integration,
   require an explicit assertion that the requested final viewport/map sizing
   has settled, not merely bitmap/current-canvas agreement. This is a recorded
   evidence limitation, not a new open correction gate for this bounded study.
3. Caller GeoJSON, browser transient allocations, Leaflet canvas, JS overhead
   and process/OS/GPU memory remain outside the managed ledger. R3 bounds
   retained-body count, not byte size. The 64/128 MiB values are study budgets,
   not approved product settings or a total-memory guarantee.
4. A refused layer retries on a later explicit render. Production integration,
   UX/budget policy and renderer selection remain future work; none is released.
5. Full repository Python/Postgres/lint/type/coverage suites were not rerun by
   the supervisor for report-folder-only prototype changes. Exact-head CI and
   developer evidence remain separately identified. The developer's missing
   zsh/system-openpyxl container limits are not represented as local passes.

## Team instructions and next review

**Team B:** both assigned deliverables are accepted at their exact heads:
1B #23 `a9dc8af…` and corrected research #21 `5e9ed42…`. Preserve both draft
PRs and branches. No further correction is requested now. Do not start 2B,
integrate the research, merge, deploy or provision resources without the next
explicit packet/authorization. No monitoring or background work is assigned.

**Team A:** continue its existing correction 2 on #22. Do not resend the
Round-1 assignment or change the accepted B modules.

**Supervisor next:** review A's next exact-head handback and the combined
baseline checkpoint before selecting/releasing the next bounded packet. This
closeout does not independently accept the combined application or baseline.

Supervisor documents are published through the existing PR #5. The separate
documentation-branch verification is in `supervisor-verificar.log`; it is not
another execution of the research or lifecycle branch's full application suite.
`./verificar.sh` passed: 672 Python tests with 29 Postgres skips, the complete
Python 3.9.6 suite and JavaScript checks. Optional `--todo` checks were not
rerun for this documentation-only publication.
