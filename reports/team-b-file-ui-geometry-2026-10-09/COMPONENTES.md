# 3B component and loader contract (for A's host)

Exact factories as Round 3 INTERFACES §3 and §5 define them. No framework, no
build step; ES modules served as they are. Every network call goes through the
`peticionPrivada` the host passes in (C1's `web/lib/api.js` export). Nothing is
cached, stored in localStorage/IndexedDB or handed to a service worker.

## 1. File widgets — `web/components/archivos/index.js`

```js
import { peticionPrivada } from "../lib/api.js";
import { crearWidgetsArchivos } from "../components/archivos/index.js";

const widgets = crearWidgetsArchivos({ peticionPrivada });   // one per private session
const celda   = widgets.mount({ container, terrenoId, tipo: "pdf", soloLectura, resumen, onCambio, onError });
const detalle = widgets.mountDetalle({ container, terrenoId, tipo: "kmz", soloLectura, resumen, onCambio, onError });
celda.update({ resumen, soloLectura });     // new summary or read-only state
celda.destroy();                            // this mount only
widgets.destroy();                          // every mount of this factory; nothing is sent or shown after it
```

| Argument | Meaning |
|---|---|
| `container` | An element the mount owns until `destroy()` (it is emptied then) |
| `terrenoId` | The terrain UUID; a new terrain, base or account gets a new mount |
| `tipo` | `"pdf"` or `"kmz"` |
| `soloLectura` | Hides and disables every control that changes server state (upload, cancel, activate, process, retire). Downloads, versions, history and attempts stay available. It never replaces server authorization |
| `resumen` | The caller-aware 1B summary `{pdf_total, pdf_recientes, kmz}`, unchanged, or `undefined` while unavailable. `undefined` is shown as loading ("…"), never as zero |
| `onCambio({terrenoId})` | A server-side file change happened (start, completion, cancel, process, activation, retirement). Refresh that terrain's file summary and location. Coalesced per mount and microtask. It is not a terrain-version change |
| `onError({codigo, mensaje})` | Sanitized text. `codigo: "no_encontrado"` means the resource left this scope: the mount has already cleared it, so the host should revalidate the terrain |

**Cell (`mount`).** Display only: it renders the summary and never fetches.
`data-estado` is one of `cargando | vacio | listo | pendiente | fallido |
sin_activar`, and its `title`/`aria-label` give the full sentence. Texts:
`…`, `Sin PDF`, `N PDF`, `Sin KMZ`, `Contorno activo`, `KMZ en curso`,
`KMZ falló`, `KMZ sin contorno activo`. Another account's pending upload is
only ever "Otra cuenta está subiendo una versión".

**Detail (`mountDetalle`).**
- **Upload.** A button opens the picker; dropping exactly one file also works,
  and more than one is refused, not queued. Type and size are checked before a
  byte is read (PDF ≤ 25 MiB, KMZ ≤ 20 MiB). The file is hashed (SHA-256),
  then start, raw PUT (the browser sets `Content-Length`) and complete.
- **Phases.** Calculando huella, Registrando, Enviando and Verificando show an
  indeterminate `<progress>` (fetch exposes no upload bytes). They end in Listo,
  Elige contornos, Guardado sin activar, Sin contorno utilizable, Falló, Sin
  confirmar, En proceso (with the server's retry delay), Vencida, Falta el
  archivo, Cancelando or Cancelada.
- **Retry and cancel.**
  - "Reintentar" is offered only when a retry is safe: replaying the same
    start key, re-staging the same version, or replaying completion.
  - "Cancelar subida" calls the cancel endpoint and reports its answer,
    including pending cleanup.
- **Limits.** One upload/hash pipeline at a time per factory, and at most five
  unfinished uploads per factory. An own pending upload found after a reload
  asks for the same file again; its size must match.
- **Lists.** Files, versions, history and attempts are paged ("Cargar más"; 20
  files, 10 rows otherwise). Versions, history and attempts load only when
  opened, and closing a panel drops what it showed. A refresh from elsewhere
  never wipes an open panel or candidate choice; it shows "La lista cambió:
  actualizar" instead.
- **Downloads.** "Descargar" and, for PDF, "Abrir" fetch the immutable version
  bytes, check the version id, type and SHA-256, then use an object URL created
  on demand. It is revoked 30 s later and always on `destroy()`.
- **KMZ.** "Contornos" lists a version's attempts. "Elegir contornos…" shows the
  parser's candidates as text and posts the chosen candidate indices.
  "Volver a procesar" reprocesses. Neither activates anything:
  "Activar este contorno" does, with the attachment's current
  `expected_revision` and one idempotency key per logical operation. A stale
  `409 revision_conflictiva` refreshes the list and asks the person to choose
  again.
- **Retire.** "Retirar…" asks for confirmation in a shared dialog that the
  mount can close. It is irreversible in this lifecycle.

## 2. Geometry loader — `web/lib/cargadorGeometrias.js`

```js
import { crearCargadorGeometrias, ErrorGeometria } from "../lib/cargadorGeometrias.js";

const cargador = crearCargadorGeometrias({ peticionPrivada });   // one per preview host
try {
  const cuerpo = await cargador.cargar({ terrenoId, geometria: registro.ubicacion.geometria }, { signal });
  canvas.render(filas, { colorFor, geometrias: new Map([[cuerpo.id, cuerpo]]) });   // at most one entry
} catch (e) {
  if (e.name !== "AbortError") mostrar(e.message);   // keep the unavailable symbol; never an XY fallback
}
cargador.reset();     // page / filter / base change: cancel and forget
cargador.destroy();   // session teardown / unmount: and refuse later loads
```

`geometria` is the record's active descriptor
`{id, archivo_version_id, utilizable: true, bbox, punto_interior}`. The loader:

1. Refuses a malformed descriptor before any request (`descriptor_invalido`).
2. POSTs `{"ids":[id]}` to `/api/archivos/geometrias/metadatos` and reads at
   most 128 KiB. The metadata must have the same id, terrain, version, bbox and
   interior point, `activa` and `utilizable` true, integer counts,
   `bytes ≤ 16 MiB`, a 64-hex `sha256`, `fragmento_bytes = 524288` and
   `fragmentos = ceil(bytes/524288)`.
3. Allocates the bounded body once, then GETs `contenido?desde=0,524288,…`.
   Every chunk's `Content-Type`, `X-Geometria-Id/-Desde/-Longitud/-Bytes/
   -Sha256/-Final/-Siguiente` and its exact length are checked against the
   sequence.
4. SHA-256 of the reassembled bytes must equal the metadata's. Then it strictly
   decodes UTF-8 (a codepoint may straddle chunks), parses JSON, and requires a
   non-empty MultiPolygon.
5. Returns the accepted B-2 body shape:

```json
{"geojson": {"type": "MultiPolygon", "coordinates": [...]},
 "bbox": [-100.4, 20.6, -100.3, 20.7],
 "punto_interior": {"type": "Point", "coordinates": [-100.35, 20.65]},
 "partes": 1, "huecos": 0, "vertices": 5, "area_aproximada_m2": 1234.5,
 "id": "<geometry uuid>", "archivo_version_id": "<uuid>", "terreno_id": "<uuid>",
 "bytes": 1234, "sha256": "<64 hex>"}
```

**Errors** are `ErrorGeometria`, with a readable `message` and one of these codes:
`descriptor_invalido`, `no_disponible` (404, e.g. revoked or transferred
between chunks), `obsoleta` (no longer active: refresh the record),
`metadatos_invalidos`, `demasiado_grande`, `fragmento_invalido`,
`hash_no_coincide`, `contenido_invalido`, `red`, `servidor`, `sesion`,
`destruido`. Cancellation (a newer selection, `reset()`, `destroy()`, the
caller's signal or the private session ending) rejects with `AbortError`.

**Residency.**
- At most one load is in flight, at most one waiting request (the latest), and
  one ready body.
- A different selection cancels the load in flight and replaces the waiting
  one, which rejects with `AbortError`.
- The same descriptor while ready is answered without network.
- `estado()` returns counts only (`{enCurso, enEspera, listos, destruido}`),
  for diagnostics.
- The raw buffer is released after parsing, and nothing is kept per row, map or
  account.

## 3. Client — `web/lib/archivos.js`

`crearClienteArchivos({peticionPrivada})`: one function per frozen 2B route
(`iniciar, subir, completar, cancelar, procesar, activar, retirar, listar,
historial, versiones, intentos, intento, descargar`).
- **Reads.** JSON bodies are read with a 2 MiB bound and error envelopes with a
  64 KiB bound.
- **Errors.** Failures are `ErrorArchivos {codigo, mensaje, status, detalle,
  incierto, reintentarDespuesDe}`. `incierto` means the server may have acted
  (a dropped connection or an unreadable reply), so a mutation is resolved by
  its replay rule.
- **Validation.** Malformed ids never reach the bridge.
- **Helpers.** `validarArchivoLocal(file, tipo)` checks a file before reading
  it, and `nuevaClave()` makes one idempotency key per logical operation.
