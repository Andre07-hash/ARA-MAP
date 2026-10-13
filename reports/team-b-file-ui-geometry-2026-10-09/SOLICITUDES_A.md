# 3B → A: integration requests (repository Andre07-hash/ARA-MAP)

B's candidate head for A to merge and test is stated in the 3B draft PR
description (this file cannot name its own commit). It contains C1
`49b782d147591236cc7f311c7e0de1948ad5258e` plus only B-owned files. None of
these requests is applied in B's branch: A's shell, table, map host,
`web/lib/api.js`, `web/index.html`, store, router and server are unchanged.

## A-1 · Register the cell widget (required)

In A's table host, once per private session scope:

```js
import { peticionPrivada } from "../lib/api.js";
import { crearWidgetsArchivos } from "./archivos/index.js";
import { registrarWidgetDeArchivos } from "./tabla/ranuraArchivos.js";

const widgets = crearWidgetsArchivos({ peticionPrivada });
registrarWidgetDeArchivos(widgets.mount);
```

On logout, expiry, account or role change and grant loss: destroy the table's
slots (montarRanura already does per slot), call `widgets.destroy()`, and
create a new factory for the next identity. The factory holds the upload turn
and the unfinished-upload count, so it must not outlive the scope.
`registrarWidgetDeArchivos(null)` restores the placeholder.

## A-2 · Mount the detail controls (required)

In the terrain detail panel or dialog, for `tipo` `"pdf"` and `"kmz"`:

```js
const m = widgets.mountDetalle({ container, terrenoId, tipo, soloLectura, resumen, onCambio, onError });
// on close, terrain change, base change or identity change:
m.destroy();
```

The widget's dialogs use the shared `openDialog`, so C1's `closeAllDialogs()`
removes them on identity loss. Still call `destroy()`: it also aborts requests
and local uploads and revokes object URLs.

## A-3 · Link the stylesheet (required)

Add `<link rel="stylesheet" href="styles/archivos.css">` to `web/index.html`
(A-owned), after the shared sheets.

## A-4 · Supply `resumen` and `soloLectura` (required)

- **`resumen`:** the terrain DTO's `archivos` (the 1B summary, unchanged), or
  `undefined` until it is known.
- **`soloLectura`:** true for archived terrain or base, read-only mode, and any
  role or scope where file writes are not allowed.
- **Updates:** call `update({resumen, soloLectura})`. Do not remount for a
  summary change; that would drop an upload in progress.

## A-5 · Handle `onCambio` and `onError` (required)

- `onCambio({terrenoId})`: coalesce per terrain, then refresh that one record's
  `archivos` and `ubicacion` and apply only those fields. Never PATCH the
  terrain, never bump its version, and keep dirty cells and focus.
- `onError({codigo, mensaje})`: `mensaje` is safe text. `codigo ===
  "no_encontrado"` means the resource left the scope, so revalidate that
  terrain (it may disappear from the page).

## A-6 · Map preview: one selected body (required)

Create one loader per preview host: `crearCargadorGeometrias({peticionPrivada})`.
1. **Selection.** On terrain selection (by UUID), call `cargar({terrenoId,
   geometria: registro.ubicacion.geometria}, {signal})`.
2. **Success.** Call `render(filasDeLaPagina, { colorFor, geometrias: new
   Map([[cuerpo.id, cuerpo]]) })`, then fit or zoom with the existing renderer
   methods. The 3B harness shows the pattern in
   `tests/e2e/archivos/arnes.js` (`cargarContorno`, `pintarMapa`).
3. **Errors.** Keep the descriptor's interior-point unavailable symbol and show
   `error.message`. Never fall back to XY. An `AbortError` is silent.
4. **Lifecycle.** `reset()` on page, filter or base change; `destroy()` on
   session teardown and unmount.
5. **Label.** "Página actual: N terrenos… los demás contornos se cargan al
   seleccionarlos" (INTERFACES §5).

## A-7 · The harness-only summary route is not production

Until A's DTO exposes `archivos` and `ubicacion`, the 3B harness server adds
two test-only private routes (`GET /api/__arnes/terrenos/:id/archivos-estado`
and `GET /api/__arnes/modo`, both capability `archivos.ver`) in
`tests/e2e/archivos_servidor.py`. They must not be mounted by the application.
When A's DTO fields exist, the harness page can switch to them. That switch is
B's follow-up if A asks for it.

## A-8 · Notes, no action required

- PR #27's "Python and disposable Postgres" job on `49b782d` failed at
  `docker pull postgres:16` (Docker Hub timeout) before any test ran. A re-run
  is A's. B's PR CI runs the same suites on a tree that contains C1.
- The browser never sends `Transfer-Encoding` or a manual `Content-Length`: the
  PUT body is the `File`. This matches the mounted dispatcher's framing rules.
- Full browser-Postgres combined-flow smoke is A's (INTERFACES / TEAM_B §3.5);
  B's browser runs use the harness's SQLite and local disk.
