# B-2 acceptance — corrected boundary renderer

Reviewed and accepted as the **B-2 renderer foundation** at PR [#11](https://github.com/Andre07-hash/ARA-MAP/pull/11) head **`5d8e2dcc125a688dbba38a260d5d7eca88a6d223`**, October 7, 2026. Both F1 and F2 from [the first review](REVIEW.md) are closed. No additional B-2 correction is requested.

Acceptance is tied to this head. The PR remains a draft and unmerged. This is not a production release, acceptance of the full table/file/map workflow, or authorization to implement B-3. Team A's A-1 assignment remains unchanged.

## Findings closed

| Finding | Disposition and independent evidence |
|---|---|
| **F1 — coordinates inconsistent with declared bounds** | Fixed by `038326a`, with browser coverage in `4c20d86`. Validation visits bounded positions once, checks every ring against declared bounds, checks the union of shells, and rejects zero-width/height rings. The +2° longitude and four-identical-points reproducers now return `invalido`; the unchanged valid body returns `cargado`. Both real-browser cases preserve the unavailable symbol at the descriptor's interior point and return `contorno_no_disponible`. The consistency check does not claim to replace parser topology validation or prove immutable-version identity. |
| **F2 — pixel comparison before paint** | Fixed in `4c20d86`. Both runs await two animation frames, require nonempty painted canvases, and compare dimensions, painted counts and SHA-256 digests of RGBA bytes. The deliberately cleared-canvas control is rejected. The independent Chrome 154 run produced **26,228** nontransparent pixels on each side with matching digests. |

The synchronous diagnostic in this full corrected harness also captured 26,228 pixels on both sides, unlike the earlier independent synchronous probe. Whether synchronous reads are blank depends on the view/redraw path; no acceptance depends on that diagnostic. The required result is nonempty equality after paint. Team B's Chromium 141 count of 26,594 is from a different environment and is not expected to equal the supervisor's count.

## Verification and scope

The supervisor exported the exact accepted head into a disposable local archive, used the existing Playwright dependency and a temporary SQLite path, and removed database-service environment settings from the verification process. No production resources or real terrain data were used.

- All **20 browser checks passed**, including both added F1 cases and the repaired F2 check, on Chrome/Chromium **154.0.8037.98** with real mouse input.
- Both original helper reproducers were independently rerun alongside a valid-body control and produced the expected results.
- Full `./verificar.sh` on the accepted head: **672 Python tests, 29 Postgres-only skips; the complete macOS Python 3.9.6 compatibility suite; JavaScript tests — all passed**.
- GitHub at this head: **Python and disposable Postgres SUCCESS; JavaScript SUCCESS**. The supervisor did not run a local Postgres database; Team B's local Postgres evidence is separately documented in its report.
- Corrective changes remain inside B-owned geometry helpers, tests/harnesses and reports. The measurement-fixture bbox now derives from its actual vertices, consistent with the accepted parser. No A-owned file, schema, auth, storage, deployment or CI change was introduced.

Team B's report section 8 and `evidencia-correcciones-b2/` record the implementation and its environment-specific evidence. Prior report sections and the first supervisory review remain historical records. No application edits were made by the supervisor.

## Limits retained for integration

The extreme one-large-plus-19,999-small-part layout remains slow. Team B reports 1.5–3.3 seconds per view change in the original measurements and comparable corrected measurements. This review did not repeat the entire performance matrix or all three large parser-limit fixtures. That disclosed limit is acceptable for the current foundation milestone; a measured, bounded display strategy with an explicit deferred-outline status is still required before hosted employee rollout. Do not silently simplify/drop parts or alter B-1's parser budget to conceal rendering cost.

Hosted uploads/downloads, real company KMZ files, Safari/Firefox, mobile touch, grants/revocation, saved snapshots and combined master-table integration are outside this acceptance. New application behavior remains dependent on A's adapter and authenticated geometry-delivery integration.

## Next work

Team B may start the **documentation-only attachment contract preparation** in [NEXT_PACKET.md](NEXT_PACKET.md). It updates the existing preparation proposal for the approved work-base contract and supplies concrete requirements for Team A's early attachment prerequisites. B-3 application implementation remains unreleased until that proposal is consolidated and its dependencies are reviewed. No provider purchase/provisioning, account change, merge or deployment is authorized.
