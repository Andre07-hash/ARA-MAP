# Pre-demo polish: header "false" and phone layout

Follows the release acceptance, which asked for three things before the boss's demonstration. All three are done and deployed. AI stays off.

| Requested | Done |
|---|---|
| 1. Remove the stray "false" from the navigation | Fixed |
| 2. Fix the phone header overflow | Fixed |
| 3. Verify desktop and phone layouts | 62/62 local browser checks and 12/12 production layout checks |

**Deployment:**
- The new production deployment is `dpl_GyGqP2Lfanq7eqV4VjcEvmd4qaXr` (`ara-5cwj2kgzd-aicore2.vercel.app`), serving https://ara-map-ivory.vercel.app and https://ara-map-aicore2.vercel.app.
- The rollback target is the previous release, `dpl_3VdC4NrQYuuf6tNBJLYdUFTnBGnV`.
- Only the page code and styles changed. The database was not touched: no migration, no data written.
- The `ARA_MAP_IA_*` settings were not changed and are still absent.

## What was wrong

1. **"false" in the navigation.**
   - The header was built with the browser's native `Element.append`, which prints `false` as text.
   - The session button is written `authRequired && …`. Where no login exists, as in the local app (port 8420), that value is `false`, and it appeared beside "Mapas guardados".
   - The shared web version always has a login button, so it never showed "false" there.
   - The header now uses the app's own `append()` helper, which skips such values ([web/components/app.js](../../web/components/app.js)). No other place in the code has this pattern.
2. **Phone overflow.** There were two causes:
   - The app's grid column could grow to the header's minimum width. On a phone, the whole app was therefore laid out wider than the screen and clipped, which is also why the map toolbar (Encuadrar, Exportar) ran off the edge.
   - The header's single row (brand, status chip, three sections, session button) needs about 740 px.

## The new layout ([web/styles/global.css](../../web/styles/global.css))

- **Every width:** the app column is clamped to the screen width, and the section and brand labels never break mid-label.
- **Below 768 px:**
  - The header uses two rows: the logo, status chip and session button on the first, and the three sections across the full width on the second.
  - The header is 100 px high, and the terrain detail panel starts exactly below it.
  - The map toolbar wraps from the left inside the screen.
- **Below 420 px, shared version only:** the logo stands for the brand. The written "ARA Map" stays available to screen readers, and the gaps are slightly tighter. At 320 px this leaves about 10 px of margin.
- **Desktop (768 px and above):** unchanged, one 52 px row.

## Verification

- **Local browser suite** (`tests/e2e/smoke.mjs`), on a throwaway database:
  - **62/62**, with no console errors.
  - This includes 18 new layout checks: 3 header modes (local, shared visitor, shared editor) × widths 320, 375, 700, 768, 1024 and 1440, each with the busiest toolbar (a saved comparison, as editor).
  - Each check requires:
    - no stray `false`, `true`, `null` or `undefined` in the header;
    - no control cut off at the screen edge;
    - no page wider than the screen;
    - no header content spilling below it;
    - a single 52 px header row on desktop.
  - The new checks were **run before the fix and failed**: "false" in the header at every width in the local mode, and cut-off controls at 320 and 375 px in the shared modes.
  - The Bases screen, the table and the terrain detail panel were also checked at 375 px.
- **Default verification** (`./verificar.sh --todo`): 545 run, 20 Postgres cases skipped as usual, all passed. Python 3.9 compatibility, ruff, mypy, JS 62/62, coverage 93%.
- **Production, after deploying:**
  - The same measurements as a visitor and as an editor, on the existing "prueba comparación", at all six widths: **12/12**, with no script errors.
  - The editor view used a normal login and only opened and viewed that map. Nothing was created or changed.
- **Source:** [POLISH_SOURCE_SNAPSHOT.json](POLISH_SOURCE_SNAPSHOT.json) differs from the reviewed snapshot only in `web/components/app.js`, `web/styles/global.css` and `tests/e2e/smoke.mjs`. The test file is not deployed.

Screenshots are in [pulido/](pulido/):
- `antes-*`: before, on the local test server.
- `despues-local-1440`: the local app after the fix.
- `produccion-*`: production after deploying.

## Notes

- The app already open on port 8420 serves the corrected files. A browser page opened before the change needs a reload to lose the "false".
- **Noticed, not changed:** on phones, the map's layer legend covers much of the map. This predates the polish and is outside what was asked. It could be made collapsible if it matters for the demo.
- **Still separate:** choosing the AI provider and testing with a real model.
