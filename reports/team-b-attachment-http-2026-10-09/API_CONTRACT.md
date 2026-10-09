# Packet 2B — attachment HTTP API contract (frozen for 3A/3B)

Handlers: `server/api/archivos.py` (`RUTAS` is the exact registry list).
Service: `server/archivos.py` (accepted 1B lifecycle plus 2B reads). SQL:
`server/repo/archivos.py`. Binary type: `server/api/binario.py`.

**Status of these endpoints:** exercised through the real dispatcher in an
isolated test harness only. They are **not mounted** in `server/app.py`
until A applies INTEGRATION_REQUESTS.md (3A).

## 1. Common rules

- **Authentication / authorization.** Every route is private. The dispatcher
  answers `401 unauthenticated` without a valid cookie session and `403
  forbidden` when the role lacks the route's capability, before the handler
  runs. Inside, every resource is resolved to its real current terrain and
  authorized there with P2 (`auth.require_terreno` / `reverificar_terreno`).
  Actor and base always come from the session and the database.
- **Non-disclosure.** For every route addressed by a version, attachment,
  attempt or geometry ID, a missing ID, an ID outside the caller's scope, an ID
  of another kind, another account's still-pending version (where private) and
  a non-downloadable version all give the **byte-identical** answer
  `404 {"error": "El archivo no existe.", "detalle": {"code": "not_found"}}`.
  A dead session gets `401` for existing and missing IDs alike. Terrain-
  addressed routes use P2's own `404 "El terreno no existe."`.
- **Archived policy (P2).** Reads (`archivos.ver`) remain available in scope
  on archived terrain; writes answer `409 terreno_archivado` or `409
  base_archivada`. An archived base is closed to operators (`404`).
- **Errors** use the dispatcher envelope `{"error": <Spanish message>,
  "detalle": {"code": <code>, ...}}`. Unexpected defects are `500 internal`
  (never relabeled as validation). A lock not obtained in time is `503
  ocupado`; nothing is retried automatically.
- **JSON success** is always `200` with `Content-Type: application/json;
  charset=utf-8`, `Cache-Control: no-store` (the dispatcher has no 201 path).
- **Idempotency.** Start, reprocess/selection, activation and retirement read
  the `Idempotency-Key` header (1–200 characters). Same key + same body
  replays the stored result with `"replay": true`; a changed body is `409
  idempotencia_conflictiva`; absent/invalid is `400 idempotencia_invalida`.
  Keys are scoped per account, operation and resource. Completion replay needs
  no key: completing a terminal version returns its stored outcome.
- **Paging.** `limite` 1–100 (default 50), else `400 limite_invalido`;
  cursors are opaque strings returned as `cursor_siguiente` (`null` at the
  end), else `400 cursor_invalido`.
- **Numeric parameters** (`limite`, `desde`, the upload's `Content-Length`;
  correction 1, R2-B1). Only ASCII digits `0`–`9`, at most 9 (20 for
  `Content-Length`); leading zeros are allowed. Signs, spaces, separators,
  exponents, hexadecimal and non-ASCII numerals (`²`, `٣`, `５`, …) get the
  parameter's controlled error, never a 500. An empty query value
  (`?limite=`) is dropped by the shared router and means the default. Both
  query values are validated before any resource lookup, so the error is
  identical for authorized, out-of-scope and missing IDs; a dead session
  still gets `401` first.
- **Body parsing.** Malformed JSON is `400 cuerpo_invalido`. Bodies above the
  dispatcher's `MAX_BODY` (25 MiB) are refused with `413` from
  `Content-Length` alone (dispatcher message, no code) and the connection is
  closed. The dispatcher buffers the whole body before the handler runs:
  **this is not end-to-end streaming.**

## 2. Routes

| # | Method and path | Capability | Service |
|---|---|---|---|
| 1 | `POST /api/inventario/terrenos/:id/archivos` | `archivos.subir` | `iniciar` |
| 2 | `GET /api/inventario/terrenos/:id/archivos` | `archivos.ver` | `listar` |
| 3 | `PUT /api/archivos/versiones/:vid/contenido` | `archivos.subir` | `escribir_temporal` |
| 4 | `POST /api/archivos/versiones/:vid/completar` | `archivos.subir` | `completar` |
| 5 | `POST /api/archivos/versiones/:vid/cancelar` | `archivos.subir` | `cancelar` |
| 6 | `POST /api/archivos/versiones/:vid/procesar` | `archivos.subir` | `reprocesar` |
| 7 | `GET /api/archivos/versiones/:vid/intentos` | `archivos.ver` | `intentos` |
| 8 | `GET /api/archivos/intentos/:iid` | `archivos.ver` | `intento` |
| 9 | `GET /api/archivos/versiones/:vid/descarga` | `archivos.ver` | `descargar` (binary) |
| 10 | `POST /api/archivos/:aid/activar` | `archivos.subir` | `activar` |
| 11 | `POST /api/archivos/:aid/retirar` | `archivos.retirar` | `retirar` |
| 12 | `GET /api/archivos/:aid/historial` | `archivos.ver` | `historial` |
| 13 | `GET /api/archivos/:aid/versiones` | `archivos.ver` | `versiones` |
| 14 | `POST /api/archivos/geometrias/metadatos` | `archivos.ver` | `metadatos_geometrias` (read-only POST) |
| 15 | `GET /api/archivos/geometrias/:gid/contenido?desde=N` | `archivos.ver` | `fragmento_geometria` (binary) |

### 1 · Start an upload

Body (all required): `{"tipo": "pdf"|"kmz", "nombre_original": str,
"tamano_declarado": int, "sha256_declarado": "<64 hex>"}` + `Idempotency-Key`.
Result: the accepted 1B start DTO (`archivo_id`, `version_id`, `tipo`,
`numero`, `estado: "subiendo"`, `revision_base`, `nombre_original`,
`tamano_declarado`, `sha256_declarado`, `subida_vence_en` +15 min,
`completar_antes_de` +60 min). A KMZ start appends a version to the terrain's
one live KMZ attachment; a PDF start creates a new attachment.
Errors: `400 tipo_invalido | nombre_invalido | tamano_invalido` (PDF ≤ 25 MiB,
KMZ ≤ 20 MiB, declared) `| sha256_invalido | idempotencia_invalida |
cuerpo_invalido`; `409 limite_pendientes` (5 effective pending per account),
`idempotencia_conflictiva`, `terreno_archivado`, `base_archivada`; `404` (P2
terrain).

### 2 · List attachments

Query `cursor`, `limite`. Result `{"archivos": [...], "cursor_siguiente"}`:
newest first by `(creado_en, id)`, retired attachments included; each item is
the attachment DTO plus `ultima_version` under the caller-aware pending rule
(another account's pending upload is `{"estado": "subiendo"|"expirado",
"propia": false}`).

### 3 · Stage content

`PUT` with the file's exact bytes as the body. `Content-Type` must be
`application/pdf`, `application/vnd.google-earth.kmz` or
`application/octet-stream` (else `415 tipo_contenido_invalido`: no multipart,
JSON or base64). `Content-Length` is required, plain ASCII digits, and must
equal the bytes received (else `400 cuerpo_incompleto`, nothing staged); chunked transfer is
`411 longitud_requerida`. Bytes reach the store in ≤ 1 MiB chunks; a repeat
replaces earlier staging. Initiator only, before +15 min.
Result `{"version_id", "bytes_recibidos", "estado": "subiendo"}`.
Errors: `404`; `409 subida_no_pendiente | subida_expirada`; `413
tamano_excedido` (actual bytes above the type limit); `503
almacen_no_disponible` (`reintentar: true`) | `almacen_no_configurado`.

### 4 · Complete (and replay)

No body. Initiator only. Copies staging to a fresh final key, verifies actual
size, SHA-256 and signature, runs the KMZ parser, and commits one terminal
outcome. Result: `{"version", "intento", "aplicada", "motivo_no_aplicada",
"archivo", "replay", "limpieza_pendiente"}`. A verification failure is a
**200** with `version.estado = "fallido"` and `version.error.codigo` in
`tamano_no_coincide | sha256_no_coincide | firma_invalida | tamano_excedido`.
Parser outcomes are in `intento.resultado` (`listo | requiere_seleccion |
rechazado | error_interno`); a single usable `listo` candidate activates if
the attachment revision is unchanged, otherwise `motivo_no_aplicada` is
`superada` or `retirado`. Calling it again on a terminal version returns the
stored outcome with `replay: true` (use this to resolve an ambiguous result:
never start a new version for it).
Errors: `404`; `409 subida_expirada | subida_no_pendiente |
procesamiento_en_curso` (`reintentar`, `reintentar_despues_de`) `|
lease_perdido | contenido_temporal_ausente | terreno_archivado`; `503
almacen_no_disponible` (`reintentar: true`; may carry
`limpieza_pendiente: true`).

### 5 · Cancel

No body. Initiator or a currently authorized administrator.
Result `{"version_id", "estado": "cancelado", "limpieza_pendiente"}`.
Errors: `404`; `409 subida_no_pendiente`.

### 6 · Reprocess / select candidates

Body `{"seleccion": [int, ...] | null}` + `Idempotency-Key`. KMZ `disponible`
versions only. Result `{"version_id", "intento", "geometria_id", "archivo",
"replay"}`; a selection never activates by itself.
Errors: `400 seleccion_invalida`; `404`; `409 version_no_procesable |
procesamiento_en_curso | lease_perdido | idempotencia_conflictiva`; `503
almacen_no_disponible | objeto_final_inconsistente`.

### 7 · Attempts of a version · 8 · One attempt

7: query `cursor` (attempt number), `limite`. Result `{"intentos": [summary],
"cursor_siguiente"}`, newest first; a summary has `id, archivo_version_id,
numero, origen, seleccion, resultado, geometria_id, candidatos` (a count),
`creado_en, creado_por`. 8: the full attempt (`resultado_detalle` holds the
parser's candidate descriptions — names, folders, counts, bbox, validity; no
coordinates; at most 500 candidates by the parser's limit) plus
`archivo_version_id`, `archivo_id`. Another account's pending version is `404`.

### 9 · Download a finalized version (binary)

Only `disponible` versions; any other state is `404` like a missing ID.
Retired-but-retained content stays downloadable under current terrain
authorization. Bytes are read from that version's own immutable final key in
bounded chunks and checked against its recorded size and SHA-256.
Response `200`, body = exact bytes, headers:

```text
Content-Type: application/pdf | application/vnd.google-earth.kmz
Content-Disposition: attachment; filename="<ASCII fallback>"; filename*=UTF-8''<percent-encoded>
Cache-Control: private, no-store
Content-Security-Policy: default-src 'none'; sandbox
X-Content-Type-Options: nosniff
X-Archivo-Version-Id: <uuid>
X-Archivo-Sha256: <64 hex>
```

The fallback removes quotes, backslashes, `;` and every control character
(CR/LF included) and transliterates to ASCII. Range and conditional requests
are not supported (no `ETag`/`304`); every request is reauthorized.
Errors: `404`; `503 contenido_no_disponible | almacen_no_disponible |
objeto_final_inconsistente`.

### 10 · Activate a retained version / geometry

Body `{"version_id", "geometria_id" (KMZ only), "expected_revision": int}` +
`Idempotency-Key`. The version must belong to this attachment (else the
identical `404`) and be `disponible`; a KMZ needs a usable `listo` geometry of
that exact version. Result `{"archivo", "replay"}`.
Errors: `400 revision_invalida`; `404`; `409 version_no_activable |
revision_conflictiva | procesamiento_en_curso | lease_perdido |
idempotencia_conflictiva | terreno_archivado`.

### 11 · Retire

Body `{"expected_revision": int}` + `Idempotency-Key`. Cancels the
attachment's pending uploads; keeps finalized versions, bytes, attempts,
geometries and history. Irreversible in this release. Result `{"archivo",
"replay", "limpieza_pendiente"}`. Errors: `400 revision_invalida`; `404`;
`409 revision_conflictiva | idempotencia_conflictiva | terreno_archivado`.

### 12 · History · 13 · Versions

12: `{"eventos": [...], "cursor_siguiente"}`, newest first by `(at, id)`;
every event has `privado`; another account's still-pending upload event is
redacted (`actor`, `archivo_version_id`, `details` empty; `version` generic).
13: `{"versiones": [...], "cursor_siguiente"}` by version number descending,
with the same pending projection; cursor = version number.

### 14 · Geometry metadata batch (read-only POST)

Body ≤ **16 KiB** (`413 solicitud_demasiado_grande`), `{"ids": [uuid, ...]}`
with 1–50 entries, each a 36-character UUID (`400 ids_invalidos` otherwise,
never per-ID disclosure). IDs are canonicalized (lowercase) and deduplicated
in first-occurrence order. Session and capability are checked before any ID
is examined; then each ID is authorized on its own geometry's terrain.

```json
{"geometrias": {"<id>": {
   "id": "...", "archivo_id": "...", "archivo_version_id": "...",
   "terreno_id": "...", "intento_id": "...",
   "bbox": [oeste, sur, este, norte],
   "punto_interior": {"type": "Point", "coordinates": [lon, lat]},
   "partes": 1, "huecos": 0, "vertices": 5, "area_aproximada_m2": 1234.5,
   "utilizable": true, "activa": true,
   "bytes": 123, "sha256": "<64 hex>", "fragmento_bytes": 524288, "fragmentos": 1,
   "creado_en": "..."}},
 "no_disponibles": ["<id>", ...]}
```

`geometrias` keys and `no_disponibles` both follow request order. Missing and
out-of-scope IDs share `no_disponibles`. One descriptor query (`IN` over ≤ 50
IDs) plus one P2 check per distinct terrain; no body is read. `activa` is the
attachment's current pointer (false after retirement or replacement).
Response ceiling **128 KiB** (worst-case 50 descriptors measured well below;
`500 respuesta_excedida` is a guard, not an expected answer). No filenames,
candidate lists, keys or credentials. Not a public endpoint.

### 15 · Geometry body chunk (binary)

`GET /api/archivos/geometrias/:gid/contenido?desde=N`. `desde` is an ASCII
decimal integer (default 0; see Numeric parameters), a multiple of **524,288**, below the stored byte count
and below 16 MiB, else `400 desplazamiento_invalido`. Response body = the
exact stored UTF-8 GeoJSON bytes `[desde, desde + 524288)` (shorter only for
the final chunk); a codepoint may straddle chunks — reassemble bytes, then
decode.

```text
Content-Type: application/octet-stream
Cache-Control: private, no-store
Content-Security-Policy: default-src 'none'; sandbox
X-Content-Type-Options: nosniff
X-Geometria-Id: <uuid>
X-Geometria-Desde: <offset>
X-Geometria-Longitud: <bytes in this chunk>
X-Geometria-Bytes: <total bytes>
X-Geometria-Siguiente: <next offset> | fin
X-Geometria-Final: 0 | 1
X-Geometria-Sha256: <64 hex of the whole body>
```

Bytes are cut by SQL (`substr(CAST(geojson AS BLOB))` / `substring(
convert_to(geojson, 'UTF8'))`); Python holds one chunk. Every chunk checks the
stored byte length; the **final** chunk is served only after the whole body
(≤ 16 MiB) re-hashes, range by range, to the recorded SHA-256 — otherwise
`503 geometria_inconsistente`, so a corrupt or truncated object is never
presented as complete. Every request is reauthorized; there is no `304`. A
replacement or retirement does not change an old geometry's chunks; losing
scope stops further chunks (already received bytes cannot be recalled).
The client verifies the reassembled bytes against `X-Geometria-Sha256` /
the descriptor's `sha256` before parsing, then combines GeoJSON + descriptor
into the accepted B-2 body shape (3B).

## 3. Store provider

`configurar_almacen(fabrica)` installs a zero-argument factory returning an
accepted `Almacen`; it is built on first use and reused.
`almacen_local(raiz)` builds the accepted `AlmacenLocal`. With no factory,
content routes answer `503 almacen_no_configurado`. Keys never leave the
service. No provider SDK, signed URL or credential exists in 2B.

## 4. Examples (fictional)

```text
POST /api/inventario/terrenos/7b0e…/archivos
Idempotency-Key: subir-ficticio-0001
{"tipo":"kmz","nombre_original":"lote-ficticio.kmz","tamano_declarado":2210,
 "sha256_declarado":"9f1c…"}
→ 200 {"archivo_id":"…","version_id":"5d2a…","estado":"subiendo",
       "subida_vence_en":"…","completar_antes_de":"…", …}

PUT /api/archivos/versiones/5d2a…/contenido
Content-Type: application/vnd.google-earth.kmz   Content-Length: 2210
<2210 raw bytes>
→ 200 {"version_id":"5d2a…","bytes_recibidos":2210,"estado":"subiendo"}

POST /api/archivos/versiones/5d2a…/completar
→ 200 {"version":{"estado":"disponible",…},"intento":{"resultado":"requiere_seleccion",…},
       "aplicada":false,"archivo":{"revision":1,…},"replay":false,"limpieza_pendiente":false}

POST /api/archivos/versiones/5d2a…/procesar   Idempotency-Key: sel-0001
{"seleccion":[1]}
→ 200 {"intento":{"resultado":"listo",…},"geometria_id":"c41e…","replay":false,…}

POST /api/archivos/<archivo_id>/activar   Idempotency-Key: act-0001
{"version_id":"5d2a…","geometria_id":"c41e…","expected_revision":1}
→ 200 {"archivo":{"revision":2,"geometria_activa_id":"c41e…",…},"replay":false}

POST /api/archivos/geometrias/metadatos
{"ids":["c41e…","00000000-0000-4000-8000-000000000000"]}
→ 200 {"geometrias":{"c41e…":{…,"bytes":812,"fragmentos":1}},
       "no_disponibles":["00000000-0000-4000-8000-000000000000"]}

GET /api/archivos/geometrias/c41e…/contenido?desde=0
→ 200 <812 bytes>  X-Geometria-Final: 1  X-Geometria-Siguiente: fin

GET /api/archivos/versiones/0000…/descarga
→ 404 {"error":"El archivo no existe.","detalle":{"code":"not_found"}}
```
