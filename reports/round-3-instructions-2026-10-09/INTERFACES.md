# Round 3 — frozen integration seams

This refines, not replaces, the accepted Round 1 lifecycle, Round 2 HTTP and
shared geometry contracts. These names are fixed so both teams can start.

## 1. Ownership

A: `server/app.py`, route/config/startup wiring, terrain DTO/list/query modules
and their repositories, shared `web/lib/api.js`, `web/lib/inventario.js`, store,
session/router/app shell, `web/components/tabla/`, map host and shared CSS entry.
B: new `web/components/archivos/`, `web/lib/archivos.js`,
`web/lib/cargadorGeometrias.js`, dedicated file CSS and tests/harnesses.

No renderer/helper redesign: reuse accepted `MapCanvas.js` and `geometria.js`.
If a real defect requires a shared/other-owner edit, return a bounded request
with reproduction. A narrow **C1-only ownership exception** permits A to adapt
`tests/archivos_http_harness.py` and mounting-dependent assertions in
`tests/test_archivos_http.py` to production registration. Preserve handler-only
coverage and record every changed assertion; do not edit lifecycle privacy
tests or B production modules merely to make integration green.

## 2. A-owned private transport bridge (early C1)

Export **`peticionPrivada`** from `web/lib/api.js`:

```text
peticionPrivada(ruta, {method='GET', headers, body, signal}={})
  -> Promise<{response: Response, signal: AbortSignal}>
```

`ruta` is a same-origin `/api/...` path, never an absolute/foreign URL. Body is
already encoded (JSON text, File/Blob or bytes); the bridge does not JSON-decode
or buffer successful responses. Force same-origin credentials and `no-store`;
combine the caller's signal with the current private-session signal. A private
401 invokes the existing session-expiry teardown before results can reach UI.
Cancelled or obsolete calls **reject AbortError**, so B can release resources
in finally. Preserve existing API callers' behavior rather than globally
rewriting the legacy never-settling cancellation convention. The returned
signal remains bound to that captured private generation through body reads.

B checks this signal and its own generation after every await, consumes bodies
with explicit byte limits, and maps the established error envelope to readable
errors. Other non-2xx responses may be returned by the bridge for B to decode;
401 and cancellation may not escape as a successful result. Do not return a
cached private body after scope reset or install a second session authority.

Both test same-account logout/relogin, another account, and body-read-in-flight
cancellation. The bridge alone is not a replacement for host destroy/reset.

## 3. B-owned widgets; A-owned registration/lifetime

Export `crearWidgetsArchivos({peticionPrivada})` from
`web/components/archivos/index.js`, returning `{mount, mountDetalle, destroy}`.
`mount` and `mountDetalle` both take the already agreed arguments:

```text
{container, terrenoId, tipo, soloLectura, resumen, onCambio, onError}
  -> {update({soloLectura, resumen}), destroy()}
```

`tipo` is pdf/kmz. `resumen` is the complete caller-aware 1B per-terrain summary
`{pdf_total, pdf_recientes, kmz}`, unchanged, or undefined while unavailable.
Undefined is not zero. Cell mounts are compact; detail mounts supply the full
controls/paged history. A registers `widgets.mount` through
`registrarWidgetDeArchivos` and explicitly manages each detail mount's lifetime.
B may reuse shared DOM/dialog helpers but does not edit them; use their dialog
registry so session teardown cannot leave private content behind.

`onCambio({terrenoId})` tells A to invalidate that terrain's summary and active
location; it is not a terrain-version update. Coalesce requests and update
only file/location state, preserving dirty core/custom cells and focus.
`onError({codigo,mensaje})` is sanitized text. 404/scope loss clears the resource
and prompts host revalidation; do not merely toast while stale data remains.

Destroy/reset aborts active network/digest work where possible, invalidates
callbacks, drops queues/File references/metadata, removes dialogs/listeners and
revokes object URLs. No private payload in localStorage, IndexedDB or a service
worker. Cancelling local work is not proof that a server operation was rolled
back; explicit upload cancellation uses the existing endpoint only while the
same authorized scope is current. Never send queued writes under a new user.

## 4. Terrain summaries and location (A)

Add private current-record DTO siblings **`archivos`** (the 1B summary) and
**`ubicacion = {modo, xy, geometria}`** (the preserved shared contract). Supply
the same safe shapes on list/detail and current-row responses used by the grid;
do not bulk-rewrite historical records/events. Reauthorize every exposed ID.
Pending/failed replacement cannot replace the last active usable descriptor.
Retired attachments are absent from current summaries but remain in authorized
history. No storage keys, credential URLs, candidate lists or vertex bodies in
terrain rows. Public DTOs remain explicit allowlists without these additions.

Read only the bounded page (max 200); use B's existing authorized summary hook
and bounded descriptor lookups. Measure query count/bytes/latency, including
its existing per-terrain summary queries; do not silently hydrate a whole base
or rewrite B's repository for an optimization. Bring a measured bottleneck
back as an explicit B-owned request if required. Summary refreshes should be
coalesced, not one browser request per cell; one authorized record refresh is
enough for a mutation if applied only to attachment/location state.

Use `ubicacionDe` for client located/unplaced behavior and equivalent SQL for
any server-wide located/unplaced counts or filters: active usable KMZ first,
otherwise valid XY, otherwise unplaced. Do not filter only an already-paged
result and call it a global count. Keep raw XY, its diagnostics, and the legacy
renderer-row `ubicacion` string intact. Do not quietly relax public publication
requirements or redefine the existing general attention filter in this packet.

## 5. Geometry client (B) and bounded preview host (A)

Export **`crearCargadorGeometrias({peticionPrivada})`** from
`web/lib/cargadorGeometrias.js`, returning:

```text
{cargar({terrenoId, geometria}, {signal}={}) -> Promise<cuerpo>, reset(), destroy()}
```

`geometria` is the active record descriptor. `cuerpo` is the accepted B-2 shape
`{geojson,bbox,punto_interior,...}` after immutable-ID/version/terrain matching,
length and SHA-256 verification. Use the frozen metadata/chunk routes; never
send storage keys. Verify metadata matches the requested descriptor and every
chunk's ID, offsets, total, length, next/final marker and hash. Enforce metadata
128 KiB, chunk 512 KiB and body 16 MiB bounds before unbounded reads/allocations.
Use bytes across chunk boundaries, verify the complete hash, then strict UTF-8
decode/JSON parse. Missing/truncated/oversized/corrupt/stale data is an explicit
unavailable/error, never a successfully drawn partial boundary.

**Round 3 deliberately narrow residency:** one preview host, one selected
geometry load in flight, at most one latest replacement request queued and one
ready body retained. Rapid selections cancel/replace obsolete work rather
than building an unbounded queue. Release obsolete raw buffers, parsed objects
and renderer references; do not keep a hidden cache per row/map/account. Measure
transient peak and cancellation cleanup; this is not a total-browser-RAM budget
and does not approve the research 64/128 MiB settings or E5 implementation.

A hosts the existing map for the **current table page only**, labelled as such
with its page count, and synchronizes terrain selection by UUID. Render page
descriptors/XY; load the **selected** geometry body on demand and provide it as
`options.geometrias` (at most one entry) to the unchanged renderer. Clearly
explain that other outlines load on selection. Preserve the active descriptor's
interior-point unavailable symbol while loading/error; never move to unrelated
XY or pretend all outlines are loaded. The selected terrain fits/scales using
the accepted renderer methods. Unplaced rows stay in the table, not at an
invented map position. Page/filter/base/session changes dispose obsolete work.

This is an honest first-workflow preview, **not** the final whole-base/multi-map
performance or fallback policy. Full filtered views/snapshots and that policy
remain Round 4. One accepted near-limit 100,000-vertex body must still load and
render without silent truncation or simplification; report actual timings.

## 6. Mounted HTTP behavior

R-1–R-4 from B's request document are applied in C1. All 15 routes remain private
and capability-declared. Only geometry-metadata POST is added to the read-only
exemptions. Binary responses keep exact bytes/status/type/private no-store,
nosniff/CSP and filename behavior; old XLSX export tuple handling remains intact.

The corrected dispatcher has precedence over handler-only framing examples:
one Content-Length of 1–12 ASCII digits; any TE or malformed/duplicate length
gets 400/close, oversized declared bodies 413/close. Thus old harness examples
of TE=411 or 20-digit padded length=200 are not promises for mounted endpoints.
Document/test both layers instead of weakening the dispatcher. The browser
sets Content-Length for File/Blob requests; B must not try to set that forbidden
header manually. JSON successes stay 200, completion may take 9–11 seconds,
and server buffering is not streaming or a hosted-capacity guarantee.
