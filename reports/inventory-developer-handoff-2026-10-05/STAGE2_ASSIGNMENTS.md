# Stage 2 assignments — public catalog and publication

Issued October 5, 2026 by the supervisor after Stage 1 acceptance (VERIFICATION_RESPONSE.md: no blocking defects). Read START_HERE.md, INTEGRATION_DECISIONS.md (including §9–§10), and the specialist packets. The contract is unchanged except where §9–§10 say otherwise. This is local work on disposable data only: no deployment, no production access, no publication of real or legacy data.

Stage 2 exit evidence (START_HERE.md): draft edits stay private; publish updates public detail, map and table; private data cannot be fetched through older routes or exports.

## Backend (owns server/, api/, scripts/, Python tests)

1. **B3 publication:** POST `/api/inventario/terrenos/:id/publicar` `{expected_version,revision_id}`; `/despublicar`, `/archivar`, `/restaurar` `{expected_version}`. Compare-and-set in the same transaction as the pointer, timestamp and event. Publish only the current saved draft and apply the §5 publication gate, including §9.1 geographic validation. Archive and unpublish withdraw immediately; restore never republishes. Publishing sold/withdrawn removes the record from the public list and detail.
2. **Preview:** GET `/api/inventario/terrenos/:id/vista-publica?revision_id=…` returns `{id,version,revision_id,preview:true,terreno:PublicTerrain,blockers,warnings}` with `published_at` null. One shared explicit `PublicTerrain` serializer and eligibility predicate are used for preview, public list and public detail.
3. **Public catalog:** replace the placeholders. GET `/api/publico/terrenos` and `/:id` select fields only from the revision named by `published_revision_id`. Filters, facets, counts and cursor work on published fields per §6, private and unknown selectors return 422 (O-2), and missing or nonpublic records return a uniform 404.
4. **InternalTerrain lifecycle fields:** `publication_state`, `public_visible`, `has_pending_changes` and `attention` reflect the published pointer; the internal list filters by them.
5. **Carry-forwards:** O-5 (generic 500), O-7 (throttle keyed by login and client), and `/api/config.readOnly` reflecting only `ARA_MAP_READ_ONLY`.
6. **Tests:** both engines, stale publish (CON-02), preview/public equality, sold/withdrawn withdrawal, and every lifecycle transition under version checks.

Deliver BACKEND_RESPONSE_STAGE2.md.

## Interface (owns web/, tests/js/, tests/e2e/)

1. First split `web/components/app.js` (1,318 lines) into focused modules with no behavior change, proven by the existing suites.
2. Integrate the real public catalog (map, table, detail, filters, "Precio a consultar", "En negociación", empty state). Anonymous and signed-in "Catálogo público" views both fetch the real public response.
3. Add `PublicationPreview` (same renderer as public detail, "Vista previa · Aún no publicada"), Publicar using the exact reviewed `{expected_version,revision_id}`, Retirar del catálogo, Archivar and Restaurar with named confirmations. Implement the FRONTEND_PACKET publication-state labels, including "Fuera del catálogo · Vendido", and make pending price or availability changes conspicuous. A stale publish returns to review.
4. **Carry-forwards:** D-1 (Historial focus return), a status column in the inventory table, toasts no longer covering the phone editor action bar, and a rewrite of `tests/e2e/smoke.mjs` for individual sign-in on a disposable server.
5. Start against contract fixtures; integrate once BACKEND_RESPONSE_STAGE2.md exists.

Deliver FRONTEND_RESPONSE_STAGE2.md.

## Verifier (owns verification/)

Prepare now; execute once both Stage 2 responses exist. Stage 2 cases:
- PUB-01, PUB-02, PUB-03 and CON-02.
- PRE-01.
- VIEW-01, VIEW-02 and VIEW-03 with the public catalog, at all seven widths.
- The §5 legacy and new-route anonymous audit, now a **blocking gate**, including sold/withdrawn, archived, unpublished and draft ID guessing.
- REG-01, and regression of all Stage 1 cases.

Deliver VERIFICATION_RESPONSE_STAGE2.md.

Not in Stage 2: import/adoption, duplicate review, the attention list UI beyond server reasons, migration rehearsal, and any deployment.
