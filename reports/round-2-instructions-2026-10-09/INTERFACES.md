# Round 2 — shared seams and bounded transport

This document refines the earlier shared/attachment contracts for 2A/2B.
Neither terrain summary mounting nor file-widget implementation happens here.

## A table → future B file widgets

Core column IDs remain `core:archivos` and `core:kmz`. A reserves a cell mount
and a detail mount with: terrain UUID, current base context, file kind (`pdf`
or `kmz`), read-only state and current safe summary **when available**. In 2A
the summary is absent; show an honest unavailable integration state, not zero
files or an enabled fake uploader. Do not import B's unfinished handler code
into frontend modules.

Freeze the future host adapter shape (plain objects/functions, no framework):

```text
mount({container, terrenoId, tipo, soloLectura, resumen,
       onCambio, onError}) -> {update({soloLectura, resumen}), destroy()}
onCambio({terrenoId})      invalidates that terrain's attachment summary
onError({codigo, mensaje}) sanitized, user-facing error only
```

Use a new mount for a changed terrain/account/base; `destroy()` cancels work,
removes listeners and releases sensitive state. `resumen` is the existing
caller-aware 1B summary, not a second shape. File changes do not increment
terrain cell versions or wipe unsaved core/custom edits. No `revision_max`
aggregate cache token. Refresh the indicated summary on a completed mutation;
ignore results from an obsolete scope generation. Detail controls can use the
same identity/lifetime contract while rendering outside the cell.

A exposes/document these seams now; B's widgets implement them in 3B. The
3A host owns real summary fetching, DTO/location adaptation and mounting.

## Geometry delivery — finalize D4 for local 2B

Keep descriptors separate from bodies. Geometry is immutable and belongs to
one terrain, attachment, finalized version and successful attempt. Current
authorization follows that terrain, even for retained/retired history. This
is not a public endpoint or a snapshot authorization bypass.

Use a two-step bounded protocol:

1. **Metadata batch:** at most **50 unique UUIDs**, with a **16 KiB request
   ceiling** and **128 KiB encoded JSON response ceiling**. Return
   `{geometrias, no_disponibles}`: keyed metadata for authorized IDs and one
   indistinguishable list for missing/out-of-scope IDs. Dedupe deterministically;
   preserve a documented order. Invalid UUID/shape/oversized input is controlled
   validation, not per-ID existence disclosure. Each requested ID must be
   authorized before any descriptor is returned; never query/hydrate all bodies.
   No arbitrary user filename, full parser candidate list or credentials in
   this metadata envelope. Use the existing geometry/version IDs, bbox,
   interior point, counts and persisted `bytes_geojson`/`sha256_geojson`.
2. **Body chunks:** one immutable geometry per request, at most **512 KiB raw
   bytes** per response. Use a nonnegative bounded integer byte offset aligned
   to that chunk size, with the final partial chunk explicitly identified.
   Return exact bytes of the stored UTF-8 GeoJSON, without reformatting,
   simplification or altered coordinates. Include/document geometry ID, byte
   offset, total byte count, next offset/end and SHA-256 so the client can
   reassemble and verify before JSON parsing. A UTF-8 codepoint may straddle
   chunks: chunks are bytes, not independently decoded JSON strings. No
   user-controlled SQL identifier/range, unbounded offset or silent truncation.

The future client combines the verified GeoJSON with descriptor metadata into
the accepted B-2 body shape; no renderer changes in 2B. Chunks use private
`no-store`, authorize on **every** request and never accept storage keys or
credential-bearing URLs. A same-version hash is identity, not authorization;
do not issue an unauthenticated 304. Replacement may change the current pointer
but cannot change old chunks. Scope loss prevents subsequent chunks; it cannot
recall already received bytes.

**Allocation guard:** at most one full geometry body may be materialized per
request, with a **16 MiB serialized GeoJSON ceiling** before parsing/copying;
never load the batch's bodies to enforce the response cap afterwards. Prefer
byte-range retrieval when practical. This is a bounded local transport design,
not a claim of 512 KiB total process memory or a total-browser memory budget.
Use stored length/hash carefully and validate consistency for corrupt data.

Prove the guard accommodates the accepted parser's full 100,000-vertex limit,
including multipart/ring overhead and long finite coordinate encodings. Test
an actual near-limit accepted result plus serialization-bound cases; report
actual sizes/query counts/allocations. If a valid accepted parser output cannot
be delivered under these bounds, return the counterexample for a narrow
contract correction **before** declaring handback complete. Do not silently
reduce parser limits or downgrade to an interior point as successful delivery.

B selects and freezes exact route names/status/header fields in its API
contract; A consumes that contract in 3A. Authenticated metadata POST may need
a read-only-mode registry exemption: include it in A's precise mounting request,
never globally allow all POSTs in read-only mode. JSON validation responses use
the existing error envelope; private unavailable IDs stay non-disclosing.

## Preserved policies

1B file-size/deadline/lease/initiator/cancellation/retirement rules remain intact.
Custom-column history uses accepted A2 scalar diffs, not arbitrary embedded
maps. Unknown values remain null, no forced MXN or derived prices/areas; X is
latitude and Y longitude. Attachment versions do not change terrain edit
versions. Public DTOs remain restrictive. Cloud transport and grants,
production render budgets, saved views/maps and widget/map integration remain
in their later packets, not implicit additions to this pair.
