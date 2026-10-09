# Team A — packet 3A: mount and connect the local application

2A accepted at **`32a2a55e4a7417499cc384109bd44666e7a568cb`**; R2-A5 is closed.
Read START_HERE.md and INTERFACES.md here. Do not continue adding features to
#26. Preserve #24/#25/#26 and their predecessors. Two new drafts are expected:
the early shared C1 checkpoint and your 3A feature/integration handback.

## A. Publish C1 early — B must not wait for the whole feature

1. Follow the exact merge/branch protocol in START_HERE: accepted #26 plus
   accepted #25 `bf4c6a694ca95087368bb2d89325d7a240a7b676`. Record pure composition
   separately. No research prototype, hosted adapter branch or parked Excel.
2. Register B's exact `RUTAS`, keep literal/parameter route ordering and every
   capability, and add the `RespuestaBinaria` branch before the old tuple/JSON
   branches. Keep old XLSX export working. All real handlers use the production
   Handler on one server, not the binary subclass from the development harness.
3. Add only `api_archivos.POSTS_DE_LECTURA` to existing read-only exemptions.
   Retain all accepted framing/auth/refusal protections. Resolve the documented
   mounted-vs-handler numeric/framing differences without weakening them.
4. Wire the accepted local store on **local startup only**, with a stable root
   associated with the explicit local database (e.g. sibling `archivos`). If
   creating it, create only that specific directory with owner-only permissions;
   retain the provider's path/symlink safeguards. Missing/unusable configuration
   gives a controlled operational error, never an in-memory fallback that looks
   persistent. Do not initialize a local byte store for the cloud adapter or a
   production database. Tests always name disposable database/store paths.
5. Publish `peticionPrivada` exactly as INTERFACES defines. Test cancellation
   through response-body consumption and expiry before private UI callbacks.
   Do not rewrite legacy API cancellation semantics or add dependencies.
6. Adapt the narrowly authorized mounting-dependent harness/tests. A real
   mounted-server regression must prove the registry, binary headers/bytes,
   read-only metadata POST, mutation refusal and malformed framing, with no
   temporary route injection or `_send_json` binary override. Preserve separate
   handler validation coverage and B's corrected lifecycle tests unchanged.
7. Run full combined suites with disposable UTF-8 Postgres and SQLite, Python
   3.9, JS, ruff/mypy and required `verificar.sh` (or all components with an
   explicit environment limitation). Publish a green exact-head C1 draft plus
   manifest: source heads, pure merge head, added files, test evidence, startup
   instructions and **the one frozen C1 SHA B should merge**. No later grid/map
   changes in C1 after publication; a needed correction must be an explicit
   additive replacement checkpoint with a new pin and a handoff, not silent drift.

Then branch `claude/team-a/application-integration` from C1 and continue below.
Tell the owner C1 is ready for B as soon as it is, not only at final handback.

## B. Private record summaries and location

- Add the frozen `archivos` / `ubicacion` DTO siblings to current private record
  surfaces used by the table/detail, with caller-aware redaction and active
  geometry descriptors only. No vertex bodies or storage keys in rows.
- Keep list bounds and server-side authorization/filtering/counting. Add or
  connect located/unplaced controls consistently with the actual server query
  if needed; a KMZ-only terrain counts as located without overwriting XY. Any
  added query parameter must be documented and validated, with matching total/
  facets. Do not repurpose the existing publication/attention semantics.
- Reuse the accepted `ubicacionDe` and adapt `itemDeInventario` without breaking
  its existing callers or raw XY fields. Avoid a circular import between
  inventario.js and geometria.js; if shared validation must be factored, keep
  behavior unchanged with focused compatibility tests and document the move.
- A pending/rejected/failed replacement preserves the previous active location.
  Retirement removes the active descriptor, using valid XY if present; otherwise
  unplaced. Transfers/grant changes hide everything outside current scope.
- Keep immutable history and attachment concurrency independent of terrain cell
  versions. A file refresh must not apply stale core/custom draft data over
  an active or unresolved editor. No `revision_max` aggregate cache shortcut.

## C. Real widgets, selected boundary preview, and teardown

- Mount B's factory in the existing file slots and record detail; provide real
  summaries/read-only state, not placeholders or fake zero counts. Coalesce
  onCambio refreshes by terrain; register meaningful sanitized errors.
- Add the explicitly labelled **current-page map preview** from INTERFACES.
  Keep page/filter selection in scope, synchronize terrain UUID selection and
  load only the selected boundary through B's loader. Do not fetch all pages.
  Use the existing renderer/methods; no new render strategy or E5 research code.
- Active descriptor with pending/failed body stays located at its interior
  point with an honest loading/unavailable indication and explicit retry. A
  boundary-only terrain can be selected, fit and scaled. No made-up XY/outline.
- Destroy cell/detail mounts, geometry loader, map and private URLs/state on
  page/base/session/identity loss as appropriate. Close all private dialogs and
  discard delayed reads/writes without reviving old data. Preserve the accepted
  R2-A2/R2-A4 behavior under file operations as well as normal cell saves.
- Keep the admin's Inventario default, operator-only allowed navigation, public
  catalog and old saved maps unchanged. Do not add persistent filtered views.

## D. Acceptance and final handback

Consume B's named green-CI 3B candidate via the exact-head merge protocol. Your
final result is the **combined working local journey**, not a host mock alone.

1. SQL/HTTP on SQLite and Postgres: authorization on every summary/descriptor/
   chunk, no pending metadata leaks, aligned counts/page bounds, body-free row
   DTOs, no schema change, immutable geometry and terrain-version independence.
2. Real browser against the real mounted app: operator creates blank terrain,
   edits, uploads/downloads byte-identical PDF, uploads KMZ with blank XY, chooses
   among candidates, explicitly activates if required, sees the true boundary.
   Another authorized session reloads the same stored version/geometry; a
   no-grant session is denied and receives no stale client content.
3. Replacement failure and concurrent selection retain the last usable layout;
   retirement changes location correctly; file completion while a cell is being
   edited preserves text/selection/focus. Grant revoke/transfer/session expiry
   during upload/download/chunk reading clears UI and prevents later responses
   from repopulating it. Already downloaded copies cannot be recalled.
4. Repeat one focused upload → reload → permission-denial browser smoke against
   disposable Postgres; no need to duplicate the entire browser matrix. Restart
   the local server against the **same disposable database and disk store** and
   verify retained bytes/hash/history. A test server that recreates its database
   on restart is not persistence evidence.
5. Synthetic 25,000 records / 3,000 in a base / five sessions: measure page
   summary query counts, response bytes/latency, edit conflicts, and repeated
   page/map selection teardown. Compare with 2A; no unbounded body prefetch,
   page accumulation or invented total-browser-memory guarantee. One bounded
   memory/teardown run suffices; do not restart the research matrix.
6. Full combined suites with SQLite/Postgres, Python 3.9, JS, ruff/mypy,
   configured coverage gate, required pre-push checks and exact-head CI.

Report at `reports/team-a-application-integration-2026-10-09/START_HERE.md`:
source/C1/B/code/final full SHAs, same new draft PR, manifest/diff ownership,
verification split by environment, screenshots or a short synthetic walkthrough,
run commands for the owner, known limits and remaining Round 4 reservations.
Stop for supervisory review. No 4A, PR/main merge, deploy or real-account work.
