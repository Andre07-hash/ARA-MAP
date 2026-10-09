# B-3S acceptance — corrected standalone storage core

**Accepted as the B-3S local/fake byte-storage foundation** at PR [#13](https://github.com/Andre07-hash/ARA-MAP/pull/13) head **`c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53`**, October 7, 2026. S1 and S2 from [the first review](REVIEW.md) are closed. No further storage-core correction is requested.

Acceptance is tied to this exact commit. PR #13 remains draft and unmerged. This is not acceptance or authorization of the attachment database, state machine, HTTP handlers, cloud provider or hosted employee workflow. Nothing was merged, deployed or provisioned by the supervisor.

## Correction dispositions

| Finding | Result |
|---|---|
| **S1 — blocking open of a FIFO** | Fixed in `8a07c2c`: directory-relative/no-follow object access adds nonblocking open, then validates the opened descriptor. Regular files return to blocking mode. In independent macOS subprocess checks, both the original FIFO `leer` and `copiar` reproductions promptly returned `FalloAlmacenError`, each in about **0.033 seconds including process startup**, well within the two-second deadline. No final object was created. |
| **S2 — full buffer copy before chunk rejection** | Fixed in `8a07c2c`: byte size is checked before conversion, using `memoryview.nbytes`. Independently rejecting a preallocated 32 MiB memoryview peaked at **2,010 bytes** of additional traced Python memory for each backend, compared with roughly 32 MiB before the correction. Both retained the previous staging content. Accepted buffer types and the 1 MiB ceiling are preserved. |

The new regressions cover real FIFOs with subprocess deadlines, both backends' allocation limits and preservation behavior, typed/multidimensional/non-contiguous buffers, and regular-file blocking mode. Tests remain within the original standalone storage scope. The report records the old-code failures separately; the supervisor did not repeat that complete mutation run.

## Independent evidence

The supervisor exported the exact accepted head into a temporary archive and used only disposable paths and fictional bytes.

- Full **`./verificar.sh` passed on macOS**: **752 Python tests, 29 Postgres-only skips**, the complete system **Python 3.9.6** compatibility suite, and JavaScript tests. The full Python run includes all **80 storage tests**.
- Original FIFO read/copy reproducers and the oversized-memoryview allocation check were rerun independently, with the results above.
- GitHub at the accepted head: **Python and disposable Postgres SUCCESS; JavaScript SUCCESS**, run `37694260236`.
- Local Postgres was not used. The team's environmental openpyxl packaging failure did not reproduce on this Mac.
- The entire 256 MiB performance measurement was not repeated. The suite's bounded streaming, atomicity, concurrent-copy, containment and fault tests did run. No cloud-storage or hosted-workflow capacity claim follows from these results.

The correction changes only B-owned `server/almacen.py`, storage tests and its report. No Team A file, schema, auth, route, app wiring, CI or deployment configuration changed.

## Status of the contract and next dependency

PR #12 at `28bf0dbbf718571e35d501a7810d7e7d882ee3dd` still has its four requested design responses accepted as documented in REVIEW.md. The whole schema/API contract is not yet frozen; D1–D5 and consolidation with Team A remain pending.

The accepted independent foundations are now:

| Deliverable | Accepted PR head |
|---|---|
| B-1 KMZ parser, PR #9 | `efc362818ba64618dbfc23556db8678cde525336` |
| B-2 boundary renderer, PR #11 | `5d8e2dcc125a688dbba38a260d5d7eca88a6d223` |
| B-3S local/fake storage core, PR #13 | `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53` |

The next database-backed attachment work needs **A-1's published/reviewed schema foundation**, the consolidated **P1 attachment migration**, and, for request handling, **A-2/P2 scoped authorization including the transaction-scoped recheck**. Exact stacked draft commits can support dependent development; no merge is implicitly authorized by this review.

The refreshed GitHub listing still shows Team A's preparation PR #10 at `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6`, with no published A-1 implementation PR. This says nothing about unpublished work. Team A should continue its current assignment and return its implementation branch/PR and exact head for review. Do not change or bypass A's schema/auth design to keep B occupied.

**Team B stopping point:** preserve the accepted heads and wait for the next consolidated repository/API packet. No additional correction or independent implementation is assigned by this acceptance. Team A's A-1 authorization is unchanged. The B-2 extreme-multipart display limit, cloud-provider decision and hosted verification remain later integration/release requirements.
