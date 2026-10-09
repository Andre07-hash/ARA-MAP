# Packet 2B — requests to A (registration and transport, for 3A)

None of these is applied in B's branch: `server/app.py`, `server/router.py`,
auth, schema and shared configuration are unchanged. The 2B test harness
(`tests/archivos_http_harness.py`) performs R-1, R-2 and R-4 temporarily per
test and restores them. No request below is required to finish 2B.

## R-1 · Register the routes (ordinary 3A mounting)

Register exactly `server.api.archivos.RUTAS`, in that order, after the existing
routes. Each tuple is `(method, path, handler, capability)`:

```python
from .api import archivos as api_archivos
for metodo, ruta, handler, capacidad in api_archivos.RUTAS:
    router.add(metodo, ruta, handler, capacidad)
```

| Method | Path | Handler | Capability |
|---|---|---|---|
| POST | `/api/archivos/geometrias/metadatos` | `metadatos_geometrias` | `archivos.ver` |
| GET | `/api/archivos/geometrias/:gid/contenido` | `fragmento_geometria` | `archivos.ver` |
| GET | `/api/archivos/intentos/:iid` | `intento` | `archivos.ver` |
| PUT | `/api/archivos/versiones/:vid/contenido` | `contenido` | `archivos.subir` |
| POST | `/api/archivos/versiones/:vid/completar` | `completar` | `archivos.subir` |
| POST | `/api/archivos/versiones/:vid/cancelar` | `cancelar` | `archivos.subir` |
| POST | `/api/archivos/versiones/:vid/procesar` | `procesar` | `archivos.subir` |
| GET | `/api/archivos/versiones/:vid/intentos` | `intentos` | `archivos.ver` |
| GET | `/api/archivos/versiones/:vid/descarga` | `descarga` | `archivos.ver` |
| POST | `/api/archivos/:aid/activar` | `activar` | `archivos.subir` |
| POST | `/api/archivos/:aid/retirar` | `retirar` | `archivos.retirar` |
| GET | `/api/archivos/:aid/historial` | `historial` | `archivos.ver` |
| GET | `/api/archivos/:aid/versiones` | `versiones` | `archivos.ver` |
| POST | `/api/inventario/terrenos/:id/archivos` | `iniciar` | `archivos.subir` |
| GET | `/api/inventario/terrenos/:id/archivos` | `listar` | `archivos.ver` |

The literal `geometrias` / `intentos` / `versiones` segments come before the
`:aid` patterns; keep this relative order. No path is public (`PUBLIC_API`
unchanged). Tests to run after mounting: `tests.test_archivos_http` with the
harness's registration removed (it then exercises the mounted table).

## R-2 · Typed binary responses (minimal dispatcher change)

The tuple result keeps meaning "XLSX export". Add a separate branch for
`server.api.binario.RespuestaBinaria` (or move that four-field dataclass to an
A-owned module; B will follow the import):

```python
from .api.binario import RespuestaBinaria
...
if isinstance(result, RespuestaBinaria):
    return self._send(result.status, result.cuerpo, result.tipo, extra=dict(result.cabeceras))
if isinstance(result, tuple):  # a file download (XLSX)
    ...
```

Contract: status/content type/headers exactly as the handler sets them;
`_send` keeps adding `Content-Length` and `X-Content-Type-Options: nosniff`.
Pass `cuerpo` as is (it may be a `bytearray`; the harness's `bytes()` copy is
avoidable and is part of the measured peak). Downloads and geometry chunks set
`Cache-Control: private, no-store` and `Content-Security-Policy: default-src
'none'; sandbox` themselves. The Vercel adapter (`api/index.py`) needs the same
branch when hosted transport is released; not in this packet. Harness
equivalent: `HandlerBinario._send_json` in `tests/archivos_http_harness.py`.

## R-3 · Wire the byte store at startup

```python
from .api import archivos as api_archivos
api_archivos.configurar_almacen(api_archivos.almacen_local(<root>))
```

Suggested local `<root>`: a directory next to the database (e.g.
`db.db_path().parent / "archivos"`), created by the operator with owner-only
permissions; it must exist (`AlmacenLocal` refuses a missing root). Do not wire
it in the cloud adapter: without a factory, content routes answer `503
almacen_no_configurado`, which is the honest hosted state until a cloud
provider packet.

## R-4 · Read-only mode: exempt the one read-only POST

```python
READ_ONLY_POSTS = {"/api/exportar"} | api_archivos.POSTS_DE_LECTURA
```

`POSTS_DE_LECTURA` is exactly `{"/api/archivos/geometrias/metadatos"}`. Do not
allow other attachment POSTs in read-only mode. Harness test:
`test_metadata_post_needs_its_read_only_exemption` (403 without, 200 with,
writes still 403).

## R-5 · Finding: read-only and cross-origin refusals leave the body unread on a kept-alive connection

`Handler._dispatch` refuses (a) a non-GET request in read-only mode and (b) a
non-GET request with a foreign `Origin` **without reading the body and without
`self.close_connection = True`**. The next request on the same connection is
then parsed from the unread body. The 401, capability-403 and 413 paths already
close the connection for this reason.

Reproducer for (a): `reports/team-b-attachment-http-2026-10-09/reproduce_read_only_keepalive.py`
(output: two responses on one connection, `403` then `200` for a request
smuggled in the refused POST's body). Evidence: `evidencia/repro-r5.txt`.
(b) is the same code shape, identified by inspection of `server/app.py`; it
was not separately reproduced.

Requested change (A-owned): set `self.close_connection = True` before both
early `return self._send_json(...)` refusals. Impact today: local loopback
only, and only in read-only mode or for a foreign-origin page; no attachment
behavior depends on it. B did not patch it or bypass it.

## R-6 · Known transport limits (no change requested now)

- The dispatcher buffers up to `MAX_BODY` (25 MiB) in memory before the
  handler. PDF's 25 MiB limit equals `MAX_BODY`; a PDF of exactly 25 MiB
  works end to end; one byte more is refused by the dispatcher (`413`, no
  code). This is not streaming and not a hosted-size guarantee.
- JSON successes are always `200`; there is no `201 Created` path. Clients
  must not rely on 201.
- A KMZ at the parser's 100,000-vertex limit takes 9–11 s of synchronous
  parser work inside the completion request (measured locally); the request
  holds no write transaction during it.
