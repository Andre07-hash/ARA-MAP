# Frontend response — Stage 1 (delivery slices 1–2, plus the phone filter drawer)

October 5, 2026. Interface developer handoff for supervisor review. This is a local candidate. Nothing was deployed. No production URL, production data, `.env.local` or `datos/ara_map.db` was used. All evidence here was produced by the interface developer. **It is not independent verification.**

**Integration status:** integrated against the real Stage 1 backend (`server/` as described in BACKEND_RESPONSE.md). The run used a fresh temporary SQLite database, cloud variables unset and port 8432, with three fictional accounts. The public catalog is the one exception: its backend routes are Stage 2 placeholders, so it is integrated only for the empty state. Rendering a *non-empty* public catalog (detail, price-on-request, negotiation label, 251-record assembly) is fixture-only.

## Usable behavior delivered

### Public catalog and team inventory are separate contexts

Bookmarkable hash routes:

| Route | Context |
|---|---|
| `#/catalogo[/id]` | public catalog |
| `#/inventario[/id]` | team inventory |
| `#/inventario/nuevo` | new draft |
| `#/inventario/:id/editar` | edit a draft |
| `#/bases`, `#/mapas`, `#/mapa` | legacy workspace |

- **Anonymous visitors** see only `Catálogo` and `Iniciar sesión`.
- **Signed-in users** see `Inventario · (Mapa when a base or map is open) · Bases · Mapas guardados · Catálogo público`, their display name and `Cerrar sesión`.
- **All signed-in users get identical actions.** There are no roles.

### Anonymous startup is clean

Startup calls only `GET /api/config`, `GET /api/session` and `GET /api/publico/terrenos`. `loadIndex()` (bases, maps, folders) runs only after sign-in.

- Verified against the real server: no anonymous request returned 401.
- The empty catalog shows "Todavía no hay terrenos publicados" with a reload hint. It does not promise live updates.

### Individual sign-in replaces the shared-password dialog

- The dialog asks for `Usuario` and `Contraseña`.
- Wrong credentials show the server's generic message. A 429 shows a wait message.
- A private deep link opened without a session shows the catalog, opens the sign-in dialog, and returns to the requested route after sign-in.

### Logout and session expiry clear private data

On logout or expiry, the interface:

1. aborts every in-flight private request. This uses one shared `AbortController` scope in `web/lib/api.js`. A cancelled private request never settles, so a late response cannot repaint anything.
2. cancels dataset and detail loads.
3. destroys the editor, closes every dialog and clears toasts.
4. destroys the inventory and legacy filter rails, and clears the detail, table and map markers.
5. resets all private store keys (`clearPrivateState`).
6. replaces the URL with `#/catalogo`.

Pressing Back afterwards to a private route only offers sign-in.

Session revalidation and expiry:

- `visibilitychange`, `focus` and `pageshow` (bfcache) revalidate the session and the visible list, at most every 10 s. Nothing polls.
- A private 401 ends the session.
- **Exception:** if the editor holds unsaved input, the form stays on screen behind the sign-in dialog so the work can be saved. Cancelling that dialog clears everything.

### Inventory list and detail

The inventory reuses the persistent Leaflet workspace: map, table, legend, basemaps and the "Fuera del mapa" list. The filter, search, selection and viewport survive a trip to the editor and back.

**Assembly before counting.** The interface fetches *every* page of the query with `limit=250` and the server cursor before it states a count.

- While pages arrive, it shows "Cargando N de M…".
- The map, table, legend and count all read the same assembled result.
- A newer query aborts an older one.
- Writes revalidate the list.

**Detail panel** shows:

- the status chip, using the agreed labels (`Borrador · No publicado`, `Publicado · Cambios pendientes`, `Fuera del catálogo · Vendido`, …);
- the availability chip;
- the pending-sold/withdrawn warning;
- the server's attention reasons under "Necesita atención";
- the draft's business facts through the *public* facts renderer, which only accepts `pickPublic(...)` output;
- a separate "Solo equipo" block with contact, internal notes, confirmation stamps and source extras;
- the stable UUID, the version, and last modified by/at;
- buttons: `Editar`, `Historial`, `Ver a escala`.

**Sin coordenadas instruction updated.** For inventory records it now says to type latitude and longitude in `Editar`, offers `Editar ubicación` and a Google Maps search, and says no re-import is needed. Legacy base records keep the spreadsheet instruction, because they still cannot be edited directly.

### Draft editor (`components/inventory/TerrainEditor.js`)

The editor is a persistent form that is never rebuilt by a re-render. Sections:

- Identificación
- Ubicación (with the coordinate-pair status and a Maps link)
- Superficie (affectations shown as a percentage)
- Condiciones comerciales (currency, total and per-m², `Precio a consultar`, public description)
- Verificación ("Confirmo hoy el precio / la disponibilidad", sent as PATCH `confirm`; hidden for new drafts)
- Solo equipo (contacto, notas internas)

**What gets saved:**

- **Only fields whose text changed are parsed and sent.** Untouched values are never re-serialized: 122.5 stays 122.5, and null currency stays null.
- **Number parsing:** es-MX thousands separators are accepted ("1,200,000.50"). A decimal comma is refused with a field error rather than guessed.
- **Half coordinate pair:** per INTEGRATION_DECISIONS §9.1 it is a warning, not a block. The draft saves; publication will block it.

**After a save or a failure:**

| Situation | Behavior |
|---|---|
| Save succeeds | `Guardar borrador` announces "Borrador guardado · versión N · revisión xxxxxxxx" (or "Borrador creado · ID … · versión 1") and returns to the record's detail with the inventory context intact. If the user typed during the save, the editor stays open. |
| **422** | Errors map onto the fields: `aria-invalid`, an inline message, and a focusable summary. The input is kept. |
| **409** on PATCH | The current version is reread and the panel shows "Otra persona guardó este terreno mientras lo editabas": version N→M, who saved it, field-by-field old→new, and "tu valor" where both users changed the same field. Nothing is overwritten and save is disabled. **`Revisar cambios`** rebases the form on M: the other user's values fill the fields this user did not touch, this user's values stay, and clashing fields are marked with "En el servidor: X · Usar este valor". The user must save again deliberately. **`Recargar versión actual`** discards local input after a confirmation. Lifecycle changes, such as archived, are named. |
| Network failure on PATCH | The record is reread, not resent blindly. Same version: "no se guardó". Newer version: the conflict review. |
| Create, uncertain outcome | The `Idempotency-Key` is one per logical create. It is kept for an uncertain retry of the *same* body and replaced when the body changes. The retry replays the original result. |
| 409 `idempotency_conflict` | Starts a new attempt. |

**Leaving the editor:** a local leave/discard guard covers in-app navigation, Back and logout through a confirm dialog, and closing the tab through `beforeunload`.

### History panel

The panel reads `GET …/historial`. It shows the action, actor, time, version, confirmations, and before→after values per field with readable labels. It has `Cargar más` paging and loading, empty and error/retry states.

### Desktop and phone search and filters

**Server-filtered rail for catalog and inventory:**

- search;
- state and municipality multiselect, sent as repeated `estado=`/`municipio=` parameters, with options from the server's facets for the whole candidate set;
- area range;
- price: one explicit currency (`Cualquier moneda`/USD/MXN), one basis (total / por m²) and one range. The range is disabled until a currency is chosen, with the hint "los precios no se convierten";
- inventory only: publication state, availability, `Incluir archivados`.

Filter changes are debounced (250 ms).

**Long option lists are no longer cut off at 6/8.** A "Ver todos (N más)" / "Ver menos" toggle makes every value reachable. This also applies to legacy bases.

**Below 960 px**, a `Filtros (n)` button opens the *same persistent rail* inside a native modal `<dialog>` drawer. That gives a focus trap, Escape, an inert background, "Ver resultados" and ×. Filter state survives closing, and focus returns to the trigger, even across toolbar re-renders. Leaflet is re-measured after the drawer closes. Legacy bases and maps get the same drawer.

### Legacy workspace stays reachable when signed in

Bases, Mapas guardados, opening a base or map, imports and saved-map actions all keep working. The galleries revalidate when opened, because another user may have added a base.

### Unchanged

- Spanish copy, design tokens, visual style.
- Text-safe DOM rendering: no `innerHTML` of data. HTML-like names render literally, which the integrated test checks.
- Caret and IME preservation in the filter rail.
- The mixed-currency guards: no price bands, sorting or legacy price filters across currencies.

**Not built (later stages):** preview, publish, unpublish, archive, restore actions; import/adoption; attention list; duplicate review. There are no placeholders for them.

## Contract adaptations and deviations

All of these follow BACKEND_RESPONSE.md and INTEGRATION_DECISIONS §9. None changes the contract.

- Private draft fields are `contacto` and `notas_internas`.
- Confirmations are read from `terreno.confirmations.{price,availability}.{at,by}`. Source extras come from `terreno.source_extra`.
- Create sends a flat body with an `Idempotency-Key` header. PATCH sends `{expected_version, changes[, confirm]}`.
- On 409 the UI rereads the current record with GET rather than relying on `detalle.terreno`. The response shape still matches the fixture.
- `/api/config.readOnly` depends on the session (it is `true` when signed out). The UI reads it at startup and fetches it again after an in-app sign-in. Suggestion: make `readOnly` mean only `ARA_MAP_READ_ONLY`, or drop it.
- Facets are plain name arrays. The server rail therefore shows no per-option counts; legacy rails keep their counts. Counts in facets would be a welcome addition, not a requirement.
- The facet normalizer and error mapper accept a few equivalent shapes (`fields`/`campos`, `{valor,conteo}`/strings). This is a defensive adapter; the backend's actual shapes are what was tested.

## Files changed (sha256 after the change; baseline in `BASELINE_MANIFEST.sha256`)

No file under `server/`, `api/`, `scripts/` or the Python tests was edited. `web/vendor/*` is unchanged: it is absent from the baseline manifest, so it is omitted below.

```
ADDED    beb1dc90b5968abae072d4b2a0e32755228f4abd58778d08407e3bac6c033b34 tests/e2e/inventario-fixtures.mjs
ADDED    3a0336908647f01842d3a425f67b9096f0fd810c1711de7107e5a22ff08511df tests/e2e/inventario-integrado.mjs
ADDED    87b122cea04920f13efe748ac14732bcd0f841e84e677650bc998a15cde53c2c tests/js/fixtures/inventario/error-401.json
ADDED    9fc64773d15ea5d5dde3d2c64f7e658ce89fe5bd2a3e9393c912a6ee45aca586 tests/js/fixtures/inventario/error-404-public.json
ADDED    551bf4113a3ead20a79df32cc975bf5019e73087d114f639d346820f9e82736c tests/js/fixtures/inventario/error-409-conflict.json
ADDED    9bb74a80549fa54859e645f88cdad74c5317fdd9d0fa398d5d408e4e19605bae tests/js/fixtures/inventario/error-409-idempotency.json
ADDED    96328874f50bcf4ab14270bf63629fbd15fc0ef358663e0e644b08f01a49f1d6 tests/js/fixtures/inventario/error-422-validation.json
ADDED    c8e8e111c9ce65cebb099350ff02ccd3fe056e47a78b8fd5eec6a24a5342e418 tests/js/fixtures/inventario/historial-page2.json
ADDED    4e4ed1e30ae7f171f0e978bad1dd55d178c8b5b28d375a2cb81d7c2aadf79f34 tests/js/fixtures/inventario/historial.json
ADDED    42e96419bceea1e25f396ad8f817bb43c6b84c05bde3a951a7847d42a1bbbc68 tests/js/fixtures/inventario/index.mjs
ADDED    f237192572a5104bfdb05670a9edf582f8c8821be9af18085d45f6fe06b071b8 tests/js/fixtures/inventario/internal-list.json
ADDED    1779aab0be9e530e2b6413a9cb9f79f8eb8014094346df4ff4e85017ba8429f6 tests/js/fixtures/inventario/internal-terrain-draft-v4.json
ADDED    4be2dcd77e5735980a9c89c10640fbb3b28faa2ff01c8ddbf6fc292b3fe3c5b5 tests/js/fixtures/inventario/internal-terrain-draft.json
ADDED    3146eba6bbed68ce917649594d84762cd4375f30d550304f14c03f91e75229a5 tests/js/fixtures/inventario/internal-terrain-published-pending.json
ADDED    94cb9a42667479e77e71e0603b9aef6de91be45e8d76cf7ccbb31052c2c06b42 tests/js/fixtures/inventario/internal-terrain-unplaced.json
ADDED    72b72632a6c057f7315e9a35daf9270e1fd10473901d139c059c905423e7adaf tests/js/fixtures/inventario/public-list-empty.json
ADDED    b5a72276b3dbd3015d1900f03f9950904845b6af0f37203cbdc3e71184eee4f2 tests/js/fixtures/inventario/public-list.json
ADDED    0e555ec88f9f82ca3154c441955d5c4dfc13b79a70edcceee594ed068fb933ae tests/js/fixtures/inventario/public-terrain.json
ADDED    86eb02a0caec2729bbebbd33e8422343152ce4fff198995c48634a4b74435489 tests/js/fixtures/inventario/session-anonymous.json
ADDED    3b192a7a139ffe65b4f37c4b9d6430e78e6f54a7605eb88c444854f2fef7a2b7 tests/js/fixtures/inventario/session-user.json
ADDED    bd635cfeaac5a6e9ed76556d8f2885e330515e51bb24edd7c1dd0e50cb6631d8 tests/js/inventario.test.mjs
ADDED    d9429ead76fa722bcbf1300a306eb167b5661da88994a269d3aa75340286d2b1 tests/js/sesion.test.mjs
MODIFIED 154e195c1194cbc736e91ca7df85982116fdd841a836517f0767fe7406b5c8cc web/components/app.js
ADDED    ba85b63537e347496db436d9c74deba9531c7bac78cfa02b0b5365827b464221 web/components/inventory/DatosView.js
ADDED    ce05c49488b9e7b2b8a4be6ea53c60f8e25316eaf17eecb3ebd865d248923e2b web/components/inventory/InventoryDetail.js
ADDED    aad0e3a3759a58e86118621178d44b7eb2fba1e8da4d18c5dcbd15355a92a9c3 web/components/inventory/TerrainEditor.js
ADDED    9362b53299d36585b780557e005b20715a22d9f10fadb5c89c1bcc061f5d3c1d web/components/inventory/TerrainFacts.js
ADDED    c2fd950a5df6deb951ae822f17af3e14aed3abab057047686e9ae618f2dc2ced web/components/inventory/TerrainHistory.js
ADDED    e92fc85b3bb95ccc31a569a045d4da489997d3030ce2956524d9d4b9a8e16897 web/components/inventory/datasets.js
ADDED    4fdf29c833bc29d1682efb7242bf1c7c9995bdabc19743eafdce41352e20992d web/components/session/session.js
MODIFIED 101ce8eae836369e739fd950e0202ac32d49d6543c9e9770e8223a44c8d84ee2 web/components/terrain/FilterRail.js
ADDED    709196869a72b5c3091269eb936b96f09c3cab00ba3b36ec2a8305fc8c888be0 web/components/terrain/FiltersDrawer.js
MODIFIED 5bbc3b5f8515ea3952fd72c37ecbccb934d203b5dc2b16c21e2e353d83e9b787 web/components/terrain/UnplacedList.js
MODIFIED 42e99b8ecd7e70c71aeba3909e224805b545629aca3ea77694702c362864fae6 web/components/ui/toast.js
MODIFIED 1a9e3bf8659a9014d7bc9b3afdaecac7447807ac8bdf02b96af0790a57a388bc web/index.html
MODIFIED dd0f6613995872a6f1523fbade1087cc2d6dc4bab60ba913a02f09944e0d0b37 web/lib/api.js
ADDED    ac4661bd4e7abc292218e151386424caf45d0ef48507fa6e7607e24208258b9c web/lib/inventario.js
ADDED    c3ca2f98adf77033955e81ca2a1d95de28d4fa849fcb2c347c6de1e23d24b4f0 web/lib/router.js
MODIFIED 63bf19d777d9e18ec97f6718b291ffa22ca65f12cc3a8ca0efc05c091959ba4e web/lib/store.js
MODIFIED fd93536003d53a4b3224e4ea4914a325e652a4cebd5d9c16727c31bc15a160d2 web/styles/global.css
ADDED    fa37f2cbbe0b4869dccccd139ee4da0c0bbbdb4e8f99c8968dfe18ef79141fdd web/styles/inventory.css
```

Evidence (logs and screenshots) is under `frontend-evidence/` in this packet directory.

## Tests: commands, results, evidence

**1. JS unit tests.** Command: `node --test tests/js/*.test.mjs`.

- **Result: 98 pass, 0 fail.** That is the 68 baseline tests, unchanged and still passing, plus 30 new ones.
- New files: `tests/js/inventario.test.mjs` and `tests/js/sesion.test.mjs`. They cover:
  - public allowlist and sentinel exclusion;
  - status labels;
  - query serialization (repeated geography; price only with currency; internal-only keys never sent to the public catalog);
  - 251-record assembly at 250 and at 100, with no gaps or duplicates;
  - repeated-cursor guard;
  - es-MX number parsing;
  - untouched-field round trip;
  - 422 mapping;
  - conflict analysis;
  - idempotency-key lifecycle;
  - history normalization;
  - route round trip and privacy;
  - private-request abort with no late delivery;
  - 401 hook;
  - request bodies and headers;
  - `clearPrivateState`.
- One expectation changed during the work: "half a coordinate pair is a field error" became "half a pair saves as a draft (§9.1)". The replacement still asserts that an unparseable number (`20,67`) is refused.
- Log: `frontend-evidence/js-unit.log`.

**2. Fixture-mode browser tests — FIXTURE-ONLY.** Command: `node tests/e2e/inventario-fixtures.mjs <shots>`.

- **Result: 11/11 ok.**
- Setup: `web/` is served statically and `/api/*` is answered by an in-process contract mock built from `tests/js/fixtures/inventario/`.
- Cases: anonymous request audit; 251-record public catalog (2 pages, 251 table rows, legend count); phone drawer state, query and focus; price-on-request and negotiation labels; deep link → sign-in → return; 409 review flow; 422, decimal comma and lost-response retry with the same key; phone editor without overflow; dirty-leave guard; history paging; logout with a slow private response in flight, then Back.
- Log: `frontend-evidence/e2e-fixtures.log`. Screenshots: `frontend-evidence/fixtures/`.

**3. Integrated browser tests — REAL BACKEND.** Command: `ARA_URL=http://localhost:8432 ARA_PW_ANA=… ARA_PW_BETO=… ARA_PW_CARLA=… node tests/e2e/inventario-integrado.mjs <shots>`.

- **Result: 9/9 ok.**
- Server: started with `env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL ARA_MAP_DB=<scratch>/integ/ara.db .venv-dev/bin/python3 -c "from server.app import serve; serve(8432, open_browser=False)"`.
- Accounts: `printf '%s\n' "$PW" | .venv-dev/bin/python3 scripts/cuentas.py --sqlite <scratch>/integ/ara.db --password-stdin crear ana "Ana Prueba"`, and the same for `beto` and `carla`. All fictional.
- The database was fresh for the recorded run. The server log had no 5xx. The only 401s were the deliberate wrong-password attempt and the post-logout probe.

The nine integrated cases:

1. Anonymous startup calls exactly config, session and the public catalog. No 401s. The empty state shows at 1440, 768 and 390 with no horizontal overflow.
2. A deep link opens sign-in. A wrong password gets the generic message. The user then lands in the inventory.
3. Ana creates a draft in the UI. Price without currency gets the real server 422 on `moneda`. With USD it saves and returns an ID; it shows `USD 122.50/m²`, with HTML-like text kept literal.
4. **Three users, equal powers:**
   - Carla opens the editor at version 1.
   - Beto edits Ana's record without re-uploading anything and saves version 2.
   - Carla's stale save gets the real 409. Her values are retained and the panel names Beto.
   - After `Revisar cambios`, Beto's address is kept and the clashing price is marked.
   - Carla saves version 3.
   - The API reread confirms version 3 with both changes and `updated_by` Carla.
   - History lists Ana, Beto and Carla.
5. The price confirmation stamp is saved as version 4 and shown with the actor.
6. **251 more drafts.** They were created through the real API with Idempotency-Keys. A reload assembled 252 records in exactly 2 list requests. The count, legend and table (252 rows) agree. The server-side `estado=Guanajuato` filter in the rail gives 126 rows.
7. On a phone (390), the Filtros drawer filters on the server and focus returns to the trigger. The editor works at 390, 768 and 1440 with no horizontal overflow.
8. The legacy workflow works signed in: a base imported through the existing API appears in Bases, which is not read-only. It opens as `#/mapa`, and Mapas guardados and Inventario still work.
9. A reload keeps the session. Logout returns the catalog with no sentinel or private name in the DOM. A request with the old cookie gets 401, which shows the server-side revocation. Back shows only the sign-in dialog.

Log: `frontend-evidence/e2e-integrado.log`. Screenshots: `frontend-evidence/integrado/` (1440×900, 768×1024 and 390×844, as each case shows).

**4. Python suite, as a non-regression check only (I changed no Python).** Command: `.venv-dev/bin/python3 -m unittest discover -s tests` with `ARA_MAP_DB` pointing to a temp file and cloud variables unset. **Result: 670 tests OK (29 skipped: Postgres).**

**Not run:** automated axe accessibility audit, Firefox and Safari, Lighthouse/performance timings, HTTPS cookie behavior, Postgres-backed browser runs, real Vercel. Keyboard flows were exercised only incidentally (dialogs, Escape, drawer focus return) and not as a full keyboard-only journey.

## Migration and compatibility effects

- The front end needs no data migration.
- Old shared-password UI: the `api.login(password)` call and its dialog are removed. With the Stage 1 backend, a local install shows the public catalog until accounts exist (see BACKEND_RESPONSE "Important for the owner").
- **`tests/e2e/smoke.mjs` is now stale.** It provisions through anonymous legacy imports and the shared-password flow, which get 401. Before it is used again it must sign in with a fictional account. I did not rewrite it in this stage; the new integrated script covers the equivalent inventory flows. **Supervisor decision:** assign it to me or to verification.
- Legacy base and map behavior is unchanged except for: the signed-in landing is now Inventario instead of the most recent base; the "Mapa" nav item appears only while a base or map is open; galleries refetch when opened; long state/municipality lists expand.

## Known limitations and open issues

- **`web/components/app.js` is 1,318 lines** (the baseline was 894; the guideline is 800). Editor, conflict, history, session, dataset loading and presentational pieces now live in their own modules, but routing, workspace and legacy actions still share `app.js`. A follow-up split, for example into routing/session glue and legacy actions, is advisable before Stage 2 adds publication.
- A selected terrain that falls outside the current filters still shows its detail, fetched by ID, but has no map mark.
- The inventory table has no status or attention column yet. That is optional for this stage.
- When a session expires with unsaved editor input, the private form stays visible behind the sign-in dialog until the user signs in again or cancels. This is a deliberate trade-off to protect the input, as described above.
- Toasts can briefly cover part of the phone editor's action bar.
- A non-empty public catalog is verified only with fixtures until Stage 2 provides published records.
- There is no map point-picking for coordinates; the FRONTEND_PACKET makes it optional.

## Next dependency / supervisor decisions

1. Stage 2 backend: publish, preview and the real public catalog. The public view, `PublicTerrainDetail` and the fixtures are ready to integrate. The editor will gain `Vista previa` and publication actions in Stage 2.
2. Decide the meaning of `/api/config.readOnly` (see above) and the backend's read-only-mode question.
3. Assign the update of `tests/e2e/smoke.mjs`.
