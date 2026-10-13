# Round 3 review — corrections, not a new feature round

Repository: Andre07-hash/ARA-MAP. Supervisor check: 2026-10-12, 13:33 UTC.
Read this packet at the exact supervisor commit supplied by the owner.
Original Round 3 instructions remain `4682793f290718cfd49fd661ef16f2af4448fafb`.
Earlier accepted decisions and assignments are unchanged. **Do not start 4A/4B.**

## Decision

The first combined local workflow is real and demonstrable. The supervisor
reran A's complete real-application browser journey on macOS/Chrome 154:
**22/22 passed**, including PDF byte identity, candidate selection/activation,
100,000 vertices, second session, denial, true database/store restart, download
transfer, chunk revocation and upload session expiry.

**Round 3 is not accepted yet.** Additional independent probes found five
bounded correction groups in B-owned client code. In particular, an upload
404 after grant revocation leaves the old private UI visible, and an explicit
cancellation can continue sending after its upload was destroyed.

No separate A-owned blocker was established in this review. A's final
combined PR nevertheless inherits B's defects and must consume the corrected
candidate and verify the combined result. This is not approval to merge a PR,
deploy, use real data or introduce new scope.

## Exact reviewed heads and live GitHub checks

| Artifact | PR | Exact head | Exact-head checks |
|---|---|---|---|
| Frozen C1 | #27 | `49b782d147591236cc7f311c7e0de1948ad5258e` | Python/Postgres + JS success; run 37992169820 |
| B / 3B | #28 | `01d64541e929009ea2d149e3c6f5980805c76c73` | Python/Postgres + JS success; run 37996070565 |
| A / combined 3A | #29 | `0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db` | Python/Postgres + JS success; run 38204396420 |

All three remain drafts. Main was independently checked unchanged at
`09452fd26d38319567dce28a89db100ea61c739a`.

The historical C1 Docker timeout in B's handback is **not its current status**:
GitHub now reports the C1 Python/Postgres rerun successful.

History verified: C1 records the pure composition `72553e4...` of accepted
2A/2B; A's `368428d5426e666435b7cc642bcab3825379e883` has exactly the named B
candidate as its second parent. B's own delta over C1 stays within its owned
client/tests/report files; A's delta over B comprises its host/DTO work,
integration tests and reports. No circular feature merge was needed.

## Corrections and ownership

| ID | Priority | Owner | Required correction |
|---|---|---|---|
| R3-B1 | P1 | B | Explicit cancellation cannot outlive the upload/scope that authorized it |
| R3-B2 | P1 | B; A verifies integration | Upload permission-loss errors must clear private state and reach host revalidation |
| R3-B3 | P2 | B | Distinguish retryable failure from terminal outcome; uncertain completion must actually replay |
| R3-B4 | P2 | B | Hold the factory pipeline permit until unabortable read/hash work settles |
| R3-B5 | P2 | B | Keep captured private scope valid through geometry digest, installation and cache reuse |

Read [TEAM_B.md](TEAM_B.md) for reproductions, causes and acceptance; read
[TEAM_A.md](TEAM_A.md) for the exact-head integration follow-up.

## Independent evidence, separate from developer claims and CI

Exact combined tree: `0e9e2c1...`, extracted with `git archive`, no application
module edited. Node 23.7, Python 3.14.5, macOS, Chrome 154. Local loopback,
fictional fixture accounts, disposable SQLite database and byte store only.

- JavaScript: **181/181** passed, zero skips.
- Mount/summary/dispatcher selection: **38 run, 26 passed, 12 Postgres skips**.
  Command: `python -m unittest tests.test_montaje_archivos
  tests.test_resumenes_terreno tests.test_despachador_cuerpos`.
- A's `tests/e2e/recorrido-completo.mjs`: **22/22 passed** with the real widgets,
  mounted handlers and local disk, including its actual server restart.
- Independent `probe_client_edges.mjs`: five diagnostic observations reproduced
  R3-B1/B3/B4/B5; no app monkey patch, only controlled client/IO/digest fixtures.
- Independent `probe_upload_scope.mjs`: actual browser/production handler
  returns completion 404 after a real grant revocation; 1 old row, 1 open
  detail and the private filename remain, upload phase `fallido` (R3-B2).

The probe output is **evidence of defects**, not passing acceptance tests.
See `evidence/`. The controlled B1 fixture demonstrates a call starting after
destruction under a replacement identity; it is not a claim that a real
cross-account server mutation was executed. B5 is an independently tested
module-contract gap; A's usual destroy path mitigates it in the ordinary
session-expiry journey, which passed.

The supervisor did not duplicate the full Python/Postgres/coverage or research
matrices after finding blockers. A's reported Postgres browser smoke and
complete suites remain developer evidence; current exact-head CI independently
reports success. A focused full-story check stopped at the newly reproduced
upload permission-loss boundary, per the verification skill. Supervisor-branch
`verificar.sh` is a separate pre-push check, not evidence for the feature tree.

## Running the independent probes

`TREE` below means an exact disposable archive of the reviewed or corrected
tree, with its existing Playwright development dependency available. It is not
a production checkout or a configured real database.

```sh
node /path/to/this/packet/probe_client_edges.mjs /absolute/path/to/TREE

# In TREE; default harness creates its own disposable database/store/accounts.
python tests/e2e/tabla_servidor.py --puerto 8482
# Separate terminal; Chrome path can be supplied through CHROMIUM.
node /path/to/this/packet/probe_upload_scope.mjs /absolute/path/to/TREE http://localhost:8482
```

The second probe writes only synthetic bases/records/grants in that disposable
harness. It deliberately revokes its own synthetic grant. Stop the harness
when done. Do not point it at an ordinary local installation with real data.

## Reserved, not newly assigned

The measured summary cost (8 statements per terrain, 1,611 per 200-row page)
and A's roughly 15 KB/round heap growth remain explicit follow-ups, not proof
of cloud capacity or a memory plateau. No speculative batching, renderer/E5
rewrite or renewed research matrix belongs in these corrections. Screen-reader
validation remains unperformed. The map still represents only the current
bounded page with one selected body. Saved/live views, full-base display policy
and cloud storage remain later decisions, not silently released work.
