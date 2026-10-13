# Shared contract v1 — workspaces, records and geometry

This is the implementation boundary for the current A-1 and B-2 packets, following owner approval. It resolves shared assumptions needed now. Provider-specific file upload APIs and snapshot persistence remain separate later packets; neither team should invent those in this scope.

## 1. Product decisions

- One canonical `inventory_terrain` UUID record set. Work bases are assignment/access containers, not independent terrain databases. Each record has zero or one owning work base; unassigned records are admin-only. A person may receive several bases, and several people may share a base.
- Administrators create empty work bases, manage grants, move terrains, and edit the global master table. Operators can open only assigned bases, add/edit terrains, see their base's map, archive/restore terrains, upload/replace/choose/retire files, and manage local custom columns. Permanent purge is outside this release.
- The fourteen core columns always exist and all business values are optional. Use existing fields and IDs, adding nullable `tipo_terreno`. Comentarios uses private `notas_internas`. Save unknown currency explicitly as null; publication rules remain separate. Tipo de terreno starts as free text with suggestions. No silent monetary/area conversion.
- Custom columns are base-local text/number/choice/date definitions with stable IDs. Operators may rename/retire/restore them inside an assigned base. Core columns cannot be retired. Custom attachment columns are deferred; core PDF/KMZ columns stay in scope.
- The global table initially shows the fourteen core columns plus Base. Local custom columns appear for a single selected base or authorized record detail. Cross-base comparison/filtering of arbitrary custom fields is not promised in this release.
- UI vocabulary: **Base de trabajo** (ownership/access), **Tabla maestra** (admin aggregate), **Vista filtrada** (saved selection rule), **Base importada** (legacy dataset), **Mapa guardado** (frozen snapshot). A terrain may appear in many filtered views without changing its owning work base or being copied. Existing saved maps remain frozen.

## 2. Access, archive and transfer rules

Use Team A's capability names from PR #10: `maestra.ver`, `maestra.editar`, `maestra.archivar`, `columnas.gestionar`, `archivos.ver`, `archivos.subir`, `archivos.retirar`; admin-only `maestra.global`, `bases.gestionar`, `derivados.ver`, `derivados.gestionar`, `usuarios.gestionar`. Roles define actions; base grants define scope. There are no individual action switches in this version.

Server helpers are `require_base(request, base_id, capacidad)` and `require_terreno(request, terreno_id, capacidad)`. Resolve attachment/version/geometry IDs to their terrain before access checks. A batch must authorize every requested ID. Missing sessions produce 401, missing action capability 403, and unavailable/out-of-scope resources a non-disclosing 404. List counts, facets, search, history and files must respect scope before serialization. UI hiding is not access enforcement. Grant revocation is checked on each request.

Archiving is reversible removal of the shared record from active work, not merely hiding a row for one user. It preserves history and file versions. Restoration restores the same ID. No operator action may indirectly change public visibility; a published record whose archival would remove public content requires an admin action. Base archival is admin-only and preserves records, columns and files; define normal versus archive views explicitly in A-2/A-3. Operators cannot reopen an archived base by restoring a terrain.

**Transfer semantics for the later A-3 implementation:**

1. Admin-only, conflict-checked transaction: change the owning base, increment the record version, record old/new base and actor, and retain the stable terrain ID. A stale operator edit cannot succeed after a transfer: recheck current scope and expected version at the write boundary.
2. Core fields, core attachments, active layout and their retained versions stay with the terrain. Users authorized for the destination base may access those core records and their history; users authorized only for the source base lose access. Never duplicate the terrain as a transfer mechanism.
3. Base-specific custom values keep their original definition IDs and remain stored. They are not remapped by name or silently copied into destination columns. Operators can see/edit only current-base definitions and values. History responses must redact old-base custom values and labels outside the operator's scope; admins retain access to the full audit. Moving back makes the original base's retained values available again.
4. The transfer UI must preview the destination's access and which local columns will become hidden, then require the administrator to confirm. Already downloaded copies cannot be recalled. Later signed file grants must be short-lived and clearly document their revocation window; no new grants are issued after scope loss. Client state must be cleared on session/scope changes.
5. Frozen snapshots do not change content when a record moves. Snapshot access remains admin-only initially and must be handled explicitly in the later snapshot contract; do not expose history through a new public route.

Existing accounts default to `operador` with no grants when the role schema is introduced. No schema migration silently promotes anyone. Before authorization enforcement is deployed, the release procedure must establish and verify a named administrator and required grants with a recovery path. This packet authorizes no production account or grant changes.

## 3. Record, edit and column boundaries

The existing record ID, revision chain, optimistic `expected_version`, per-field validation and idempotent create remain authoritative. Normal cell edits use the existing PATCH shape; custom values use a separate `custom` map keyed by stable `custom:<uuid>` IDs. Core attachment column IDs are `core:archivos` and `core:kmz`.

Membership must be represented in current record state and reconstructable in future revision/audit history. Historical records remain unassigned at migration; never bulk-import legacy rows or merge names in a schema change. New base/custom-column changes must have actor/time history and conflict protection where two users can change the same definition.

File edits will use attachment-level concurrency and audit, independent of terrain cell versions. This is a reserved integration requirement, not approval to implement an incomplete file API. The future contract must prevent late upload completion overwriting a newer layout or resurrecting a retired file, preserve the last usable geometry during unsuccessful replacements, and keep finalized bytes/geometry immutable for snapshot references.

## 4. Geometry interface frozen for B-2

The parser's processing states (`listo`, `requiere_seleccion`, `rechazado`) are not attachment persistence states and not renderer states. Only an explicitly selected, active and usable geometry becomes the terrain's current geometry descriptor.

**Record DTO:** add `ubicacion = { modo, xy, geometria }` alongside the existing `draft`. `modo` is `geometria`, `punto`, or `ninguna`; `xy` uses existing `valida`, `sin_dato`, or `invalida`. `geometria` is null or a descriptor containing:

```text
id                    immutable geometry ID
archivo_version_id    source finalized file-version ID
utilizable            true for an active geometry eligible to locate this terrain
bbox                  [west, south, east, north]
punto_interior        GeoJSON Point, coordinates [longitude, latitude]
```

The descriptor slot denotes the active geometry; a pending replacement never overwrites it. The attachment summary separately describes the pending/failed upload. Unusable stored geometry may remain in file history but is not supplied as active. Geometry metadata and full bodies are separate. No private storage key or signed file URL goes into this DTO.

**A-owned adapter:** `itemDeInventario` keeps its existing fields, `registro`, raw `lat`/`lon` and ID. It places the descriptor at `t.geometria = registro.ubicacion.geometria ?? null`. B provides `ubicacionDe({lat, lon, geometria}) -> {modo, ubicado, xy}` using the existing X/Y validator; A uses its `ubicado` for filters/unplaced lists. A must not copy the interior point into raw X/Y. Existing XY-only callers remain supported. The old renderer-row `ubicacion` string remains an XY diagnostic; do not overwrite it with the record DTO object.

**B-owned renderer:** preserve `createMapCanvas` and its current methods/callbacks. Extend `render(terrenos, options)` with optional `options.geometrias`, a `Map` keyed by geometry ID whose values are the normalized geometry bodies illustrated in the example. No option means the legacy XY path still works. Bodies have `geojson`, `bbox`, `punto_interior` and optional approximate-area/count metadata. B-2 renders preloaded fixture bodies; it creates no network endpoint or credential handling.

Behavior:

- Active usable geometry takes precedence over X/Y. Draw its actual polygon/multipart/holes when visible at parcel scale. At distant zooms, use a legible symbol derived from `punto_interior`, not an estimated area circle. Every part maps back to the same terrain ID and selection.
- If an active descriptor exists but its body has not loaded, retain location and show a distinct boundary-unavailable symbol at the descriptor's interior point; do not pretend that the outline is loaded or switch to an unrelated X/Y location. Later A/B integration owns load/error messaging and retries. Malformed render input must not crash the existing map or fabricate a boundary.
- If there is no active usable geometry, preserve the existing valid-X/Y marker behavior. If neither exists, remain unplaced. A failed replacement with an old active layout still uses that old layout.
- Selection, fit bounds, zoom-to-scale, symbol coincidence and scale reporting must handle boundary-only records. Existing XY result codes and behavior are preserved; B documents any additive boundary result fields/states for A's caller.
- Render text as text/escaped content. Do not use arbitrary KML descriptions as HTML or fetch external KML resources.

The [fictional example](examples/boundary-terrain.json) gives the DTO-to-renderer mapping. Its local IDs are illustrative. This freezes the renderer boundary needed for parallel work; it does not finalize attachment table SQL or a public geometry route.

## 5. Query scale and geometry delivery

For A's later master-view packet, database-side authorization, filtering, sorting and bounded pagination are acceptance requirements. The browser must not collect every page to perform global filtering. Counters/facets must come from the same authorized query scope. Only visible rows/pages should be rendered.

Initial **synthetic verification target**, not an owner growth forecast: 25,000 master records across multiple bases, a 3,000-record work base, and five concurrent editing sessions. Record latency, query counts, memory, response bytes and conflict outcomes; page size is bounded (initial maximum 200 rows). Establish measured UX targets in the grid packet before claiming capacity; larger rollout requires further measurements. Keep this separate from schema A-1.

A standard terrain list returns geometry descriptors, not full vertex arrays. Before hosted geometry integration, A/B must agree authenticated bounded delivery, response-byte and batch limits, cancellation and private cache invalidation. The accepted parser's full-limit geometry can be megabytes. B-2 therefore accepts already loaded bodies, leaving the provider/transport decision open without blocking renderer work.

## 6. Shared prerequisites and sequencing

1. **Now, parallel:** A-1 schema foundation; B-2 renderer and pure helper, with fixtures and no application-shell edits.
2. **After A-1 review:** A-2 roles/work-base grants and guarded routes, then A-3 scoped record APIs/transfer/archive behavior. Grid and admin aggregate follow; split performance/query work as a prerequisite to accepting that aggregate, not an indefinite later optimization.
3. **Before B-3:** B returns its revised attachment schema/state/concurrency requirements. A lands a separate small attachment prerequisite migration (expected next schema after A-1, recheck main) plus authorized route hooks when the handlers are available. B may use explicitly stacked draft dependencies; schema prerequisites merge before dependent handlers. No circular “A integration waits for B API which waits for A integration.”
4. A later integration PR mounts widgets, adapts DTOs and loads geometry. It does not hold back the prerequisites. Integrate a real blank terrain + PDF + KMZ boundary early, before every customization is complete.

Only A edits schema, auth, routes, shared API/store/router, `web/lib/inventario.js` and the application shell. Only B edits its geometry helpers and map extension in this packet. No production resources, paused Excel work, or incidental deployment changes. Public continuity and migration/recovery remain release gates.
