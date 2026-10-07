# Team B — attachment contract proposal (before B-3)

Team B · documentation-only preparation · October 7, 2026

| Item | Value |
|---|---|
| Instruction commit | `94b16db2f4740c2f00bc9d58232d8b93b5781ac1` on `codex/supervisor-completion-brief`: `reports/team-b-b2-review-2026-10-07/ACCEPTANCE.md` and `NEXT_PACKET.md`, read with `git show`. The checkout was not switched. |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`, refreshed for this work (unchanged since the packet). Schema 8. |
| Branch / PR | `claude/team-b/attachments-contract` · separate draft PR. It contains only this report and fictional examples. |
| Inputs reconciled | Team B preparation, PR #8 at `e93649c` (§2 entities and routes, §5 requests). [Shared contract v1](../workspace-contract-2026-10-07/SHARED_CONTRACT.md) at `94b16db`. B-1 parser, PR #9, accepted at `efc3628`. B-2 renderer, PR #11, accepted at `5d8e2dc`. Team A preparation, PR #10 at `5e1b1bf` (capabilities, `require_terreno`, schema plan). |
| Preserved | PR #8, #9 and #11 are untouched. No application, schema, auth, route, CI or deployment file changed. No service, account or credential was used. |
| Status | A proposal for supervisory consolidation. Nothing here authorizes B-3 code. |

**How to read the marks.** **[A]** means already approved: shared contract v1, the B-1/B-2 acceptances, or the reviews. **[P]** means proposed here, for the supervisor to freeze or change. Names marked [P] are suggestions; A may rename tables and columns to its own conventions as long as the meaning stays the same.

---

## 0. What changed since the preparation report (PR #8)

| PR #8 said | Now | Why |
|---|---|---|
| One `estado` on the file version mixed upload, parser and activation (`subiendo → procesando → listo …`) | Three separate things: upload state on the **file version**, the parser result on a **processing attempt**, and the **active pointers** on the attachment. | Contract §4 [A]: parser states are not persistence states. Review: last usable layout. |
| `version_activa_id` moved automatically when a version reached `listo` | Pointers move only through one **compare-and-set decision** on the attachment's own `revision`. A geographically unusable geometry can never become active. | Review: concurrent replacements and last usable layout. |
| Parser states `requiere_eleccion`, `fallido` | B-1's accepted states `listo`, `requiere_seleccion`, `rechazado`, kept only on the attempt row. | B-1 [A] |
| `punto_lat`/`punto_lon` symbol point | `punto_interior` as a GeoJSON Point, with columns named in `[lon, lat]` order. | Contract §4 [A], B-1 [A] |
| Custom attachment columns could hold files | Only `core:archivos` (PDF) and `core:kmz`. Custom attachment columns are deferred. | Contract §1 [A] |
| "Client can poll `procesando`" | Bounded **synchronous** processing in the completion request. There is no background worker and no persisted "processing" state to get stuck in. | Review: processing lifecycle |
| `GET /api/geometrias?ids=…` without bounds | A bounded batch, a chunked path for large bodies, per-ID authorization and cancellation (§4.3). | Contract §5, review: geometry transport |
| PDF ≤ 50 MB | PDF ≤ 25 MiB by default, equal to the local body limit, with no global limit raised (decision D2). | Review: local limits |
| Vercel Blob "JavaScript only"; handwritten SigV4 | Corrected. Vercel documents Python SDK support for private storage, and Private Blob is now GA. No handwritten signing is proposed (§5). | Review: research corrections |
| Upload jobs keyed by `terrenoId:columnaId` | Keyed by **file-version ID**, so several PDFs in one cell keep separate progress. | Review: upload widgets |

**B-2 renderer interface.** No incompatibility was found, so the frozen interface stays as it is. The server must take a body's `bbox` and `punto_interior` from the **same stored geometry row** as the descriptor. B-2's `cuerpoLeaflet` requires the body bbox to equal the descriptor bbox, and a mismatch shows the "contorno no disponible" symbol. §1.4 stores both values once per geometry, so they cannot differ.

---

## 1. Attachment data model (requirements for Team A's migration)

### 1.1 Principles

1. **[A]** File edits do not change `inventory_terrain.version`, `updated_at`/`updated_by`, or `inventory_event`. Terrain cell versions and attachment edits are independent, so an upload can never make a cell edit conflict. Attachments have their own concurrency token (`archivo.revision`) and their own audit trail (`archivo_evento`). This answers Team A's question 2 in PR #10 §5.
2. **[A]** Everything references the stable terrain UUID (`inventory_terrain.id`), never legacy `terreno.id` or name+estado+municipio+superficie.
3. **[P]** Finalized rows are immutable. An `archivo_version` row in a terminal state, an `archivo_intento` and a `geometria` are never updated again. Only `archivo` (the decision row) changes, and only by compare-and-set. That lets a later snapshot reference exact finalized versions and geometries by ID.
4. **[P]** No `ON DELETE CASCADE` anywhere. Retiring a file or archiving a terrain or base erases nothing. Purge is outside this release, and a later purge must refuse anything a snapshot references.
5. **[P]** Storage keys and upload or read credentials live only in server-side columns or the response that issues them (§3.3). They never appear in DTOs, events, logs or examples.
6. **[P]** Timestamps are ISO-8601 UTC `TEXT` and IDs are text UUIDs, like the existing inventory tables. None of these tables joins `postgres.ID_TABLES`.

### 1.2 `archivo` — one attachment in a core column of one terrain (the decision row) [P]

| Column | Type / null | Meaning |
|---|---|---|
| `id` | TEXT PK | UUID |
| `inventory_id` | TEXT NOT NULL → `inventory_terrain(id)` | Owning terrain. Scope is resolved through it. |
| `columna_id` | TEXT NOT NULL, CHECK IN (`core:archivos`, `core:kmz`) | Contract §3 [A] |
| `tipo` | TEXT NOT NULL, CHECK IN (`pdf`, `kmz`) | CHECK `(columna_id='core:archivos' AND tipo='pdf') OR (columna_id='core:kmz' AND tipo='kmz')` |
| `revision` | INTEGER NOT NULL DEFAULT 1 | **Attachment concurrency token.** Every decision increments it (§2.3). |
| `version_actual_id` | TEXT NULL | The finalized version the file currently presents for opening and download. For KMZ, it moves only together with the layout. |
| `geometria_activa_id` | TEXT NULL | Only for `core:kmz`: the **active layout**, the source of `ubicacion.geometria`. CHECK `geometria_activa_id IS NULL OR columna_id='core:kmz'`. |
| `retirado_en`, `retirado_por` | TEXT NULL, `retirado_por` → `team_user(id)` | Soft retirement; nothing is deleted. Restore is not in this release (§7). |
| `retirado_motivo` | TEXT NULL, CHECK IN (`usuario`, `sin_contenido`) | `sin_contenido` is the automatic retirement of a file whose only upload never finished (§2.2). |
| `creado_en`, `creado_por`, `actualizado_en`, `actualizado_por` | TEXT NOT NULL, actors → `team_user(id)` | |

Constraints and indexes:
- `UNIQUE (id, inventory_id)` lets version and geometry rows carry the terrain ID with a composite foreign key that cannot disagree.
- `INDEX (inventory_id, columna_id)` builds the per-page summary in one query.
- **At most one live KMZ attachment per terrain:** `UNIQUE INDEX ON archivo(inventory_id) WHERE columna_id='core:kmz' AND retirado_en IS NULL`. Partial indexes work on SQLite ≥ 3.8 and Postgres. A replacement is a new version on the same attachment. After retirement, a new upload creates a new attachment, so a retired one is never resurrected.
- Pointer integrity uses the same pattern as the existing `fk_inventory_draft`. It is deferrable, and Postgres adds it after both tables exist:
  - `FOREIGN KEY (id, version_actual_id) → archivo_version(archivo_id, id)`
  - `FOREIGN KEY (id, geometria_activa_id) → geometria(archivo_id, id)`
  
  So a pointer can only name a version or geometry of **the same attachment**.
- "The active geometry is usable" cannot be a cross-table CHECK. It is enforced inside the activation transaction (§2.3) and covered by tests in §6 (M-12).

### 1.3 `archivo_version` — one upload; immutable once terminal [P]

| Column | Type / null | Meaning |
|---|---|---|
| `id` | TEXT PK | Generated by the server at upload start. It is the natural idempotency key for completion and cancellation. |
| `archivo_id`, `inventory_id` | TEXT NOT NULL; composite FK `(archivo_id, inventory_id) → archivo(id, inventory_id)` | |
| `numero` | INTEGER NOT NULL; `UNIQUE (archivo_id, numero)` | 1, 2, … in start order, for display |
| `estado` | TEXT NOT NULL, CHECK IN (`subiendo`, `disponible`, `fallido`, `cancelado`, `expirado`) | Upload lifecycle only (§2.1) |
| `revision_base` | INTEGER NOT NULL | `archivo.revision` when this upload started. The completion's compare-and-set uses it. |
| `nombre_original` | TEXT NOT NULL | ≤ 255 characters. Display only and always rendered as text. Never used as a path. |
| `tamano_declarado`, `sha256_declarado` | INTEGER NOT NULL, TEXT NOT NULL | Sent by the client at start |
| `tamano`, `sha256` | INTEGER NULL, TEXT NULL | Verified from the **finalized** object. Set only on `subiendo → disponible`. |
| `tipo_detectado` | TEXT NULL | `application/pdf` or `application/vnd.google-earth.kmz`, from magic bytes, not from the client |
| `clave_temporal` | TEXT NOT NULL | Staging key the upload credential may write. Server-only. |
| `clave_final` | TEXT NULL | Immutable key, set once at finalization (§2.4). Server-only. |
| `subida_vence_en` | TEXT NOT NULL | Expiry of the issued upload credential |
| `completar_antes_de` | TEXT NOT NULL | Completion deadline (credential expiry plus grace, §2.5) |
| `error_codigo`, `error_mensaje` | TEXT NULL | For `fallido` |
| `iniciado_en`, `iniciado_por`, `terminado_en`, `terminado_por` | TEXT; actors → `team_user(id)` | `terminado_*` is NULL while `subiendo` |

Indexes: `(archivo_id, numero)` unique; `(estado, completar_antes_de)` for lazy expiry and sweeps; `(iniciado_por, estado)` for the per-user cap on pending uploads; `(inventory_id)`. `UNIQUE (archivo_id, id)` is the target of the pointer FK.

Immutability is enforced in `server/repo/` by guarding every `UPDATE archivo_version` with `WHERE estado = 'subiendo'` and checking `rowcount`. A test asserts that no code path updates a terminal row (§6, M-13). Database triggers are not proposed, because they would differ between SQLite and Postgres.

### 1.4 `archivo_intento` and `geometria` — KMZ processing results [P]

`archivo_intento`: one parser run over one finalized KMZ version. It is inserted only **after** the parser returns, in one transaction with its outcome, so it is born terminal and has no "running" state.

| Column | Type / null | Meaning |
|---|---|---|
| `id` | TEXT PK | |
| `archivo_version_id` | TEXT NOT NULL → `archivo_version(id)` | Must be a `disponible` KMZ version (checked by the repo) |
| `numero` | INTEGER NOT NULL; `UNIQUE (archivo_version_id, numero)` | |
| `seleccion_json` | TEXT NULL | Candidate indices passed to `procesar_kmz`. NULL for the first run. |
| `resultado` | TEXT NOT NULL, CHECK IN (`listo`, `requiere_seleccion`, `rechazado`, `error_interno`) | B-1 states [A], plus `error_interno` for a caught unexpected exception. A process killed mid-run leaves no row (§2.5). |
| `resultado_json` | TEXT NOT NULL | `avisos`, `ignorados`, `candidatos`, `error`, without the geometry. Bounded by B-1's limits (500 candidates ≈ 113 KB measured). |
| `analizador` | TEXT NOT NULL | Parser identity, for example the `server/kmz.py` content hash, so results stay reproducible |
| `geometria_id` | TEXT NULL | Set when `resultado='listo'` |
| `creado_en`, `creado_por` | TEXT NOT NULL | |

`geometria`: an immutable normalized body. It is created only from a `listo` attempt.

| Column | Type / null | Meaning |
|---|---|---|
| `id` | TEXT PK | Immutable geometry ID; the renderer's `options.geometrias` key [A] |
| `archivo_id`, `archivo_version_id`, `inventory_id` | TEXT NOT NULL; FK to the version; `UNIQUE (archivo_id, id)` as the target of the pointer FK | Supplies `archivo_version_id` in the descriptor [A] |
| `intento_id` | TEXT NOT NULL UNIQUE → `archivo_intento(id)` | One geometry per successful attempt. Two selections of the same file give two geometries. |
| `geojson` | TEXT NOT NULL | MultiPolygon, positions `[lon, lat]`, exactly as B-1 returned them. Never simplified or rounded. |
| `bbox_oeste`, `bbox_sur`, `bbox_este`, `bbox_norte` | REAL NOT NULL | GeoJSON `[west, south, east, north]` [A] |
| `punto_lon`, `punto_lat` | REAL NOT NULL | `punto_interior` [A]. **Never copied into X/Y**, which ARA stores as X = latitude, Y = longitude. |
| `partes`, `huecos`, `vertices` | INTEGER NOT NULL | Optional body metadata [A] |
| `area_aproximada_m2` | REAL NULL | Labelled as calculated. Never written into Superficie or HA [A]. |
| `utilizable` | INTEGER NOT NULL CHECK IN (0, 1) | B-1's separate Mexico eligibility result [A] |
| `bytes_geojson`, `sha256_geojson` | INTEGER NOT NULL, TEXT NOT NULL | Used to plan bounded delivery (§4.3) and to check chunked bodies |
| `creado_en` | TEXT NOT NULL | |

### 1.5 `archivo_evento` — append-only attachment audit [P]

| Column | Meaning |
|---|---|
| `id` TEXT PK; `archivo_id` NOT NULL; `inventory_id` NOT NULL | |
| `archivo_version_id`, `intento_id`, `geometria_id` NULL | What the event concerns |
| `accion` TEXT NOT NULL, CHECK IN (`subida_iniciada`, `version_disponible`, `version_fallida`, `subida_cancelada`, `subida_expirada`, `procesado`, `version_actual_cambiada`, `capa_activada`, `decision_superada`, `retirado`) | |
| `revision` INTEGER NULL; `UNIQUE (archivo_id, revision)` | Set only by events that increment `archivo.revision`. This mirrors `inventory_event`'s one event per version. Informational events have NULL, which both databases allow more than once under UNIQUE. |
| `base_id` TEXT NULL → A-1's base table | The terrain's work base **at event time**, so history can be reconstructed after a transfer (contract §2.3). This is the only dependency on A-1's schema. |
| `actor_id` NOT NULL → `team_user(id)`; `actor_name`; `at`; `details_json` (no keys or URLs) | Same pattern as `inventory_event` |

Core attachments move with the terrain [A], so their history is visible to whoever is currently authorized on that terrain. No redaction is needed for core columns. Custom-column redaction is A's and does not apply here.

### 1.6 Idempotency [P]

Upload start takes `Idempotency-Key` and reuses `inventory_operation_result` with `operation = 'archivos.iniciar'`. The request hash covers actor, terrain, column, `archivo_id`, `expected_revision`, name, size and SHA-256, so no new table is needed. A replay returns the same version ID, **with a newly issued upload credential** if the version is still `subiendo` (§3.3). Completion, cancellation and processing retries are idempotent by version ID (§2.3). Decisions (`activar`, `retirar`) are idempotent through `expected_revision`: a replayed decision finds the revision already moved, gets 409 with the current state, and the client sees its own decision applied.

### 1.7 Summaries in the terrain DTO (R4, refined) [P]

A adds two read-only fields to `repo._dto` through **one** batch helper per page, `resumenes_de_archivos(conn, inventory_ids)`. It is bounded per row: a count plus at most the 5 most recent PDFs, and the KMZ state.

- `ubicacion = {modo, xy, geometria}` exactly as in contract §4 [A]. `geometria` is the descriptor of the live KMZ attachment's `geometria_activa_id` when that geometry is `utilizable`, otherwise null. A computes `modo` with the existing `location_state` plus "descriptor present".
- `archivos = {"core:archivos": {...}, "core:kmz": {...}, "revision_max": n}`. Each summary carries `archivo_id`, `revision`, current version name/size/date, `pendientes` (the caller's own `subiendo` versions only), `ultima_falla` (code plus Spanish message of the newest failed or rejected attempt that did not become current), and for KMZ `estado_capa` ∈ `activa`, `sin_capa`, `requiere_seleccion`, `no_utilizable`. `revision_max` lets the grid notice a change cheaply on refresh, without push. See `examples/01-terreno-con-resumen.json`.
- The public catalog never includes `ubicacion.geometria` or `archivos`. A's allowlist test must cover both [A: contract §2, no public files or geometry].

---

## 2. Lifecycle and concurrent actions [P]

### 2.1 Three state machines, kept apart

```
archivo_version.estado (upload)        archivo_intento.resultado (parser, born terminal)
  subiendo ──completar──▶ disponible     listo | requiere_seleccion | rechazado | error_interno
     │  ├──verificación falla──▶ fallido
     │  ├──cancelar / retirar──▶ cancelado
     │  └──plazo vencido──────▶ expirado
     (every arrow: UPDATE … WHERE id=? AND estado='subiendo', rowcount = 1)

archivo (decisions; each one: UPDATE … SET revision = revision + 1 …
         WHERE id=? AND revision=? AND retirado_en IS NULL, rowcount = 1)
  · cambiar version_actual   (PDF completion or "usar esta versión")
  · activar capa             (KMZ: version_actual + geometria_activa together)
  · retirar                  (sets retirado_*; cancels its subiendo versions)
```

### 2.2 Transitions

| Action | Precondition | Effect, in one transaction unless stated | Replay |
|---|---|---|---|
| **Start upload** | Capability and scope (§3). Terrain not archived. Type, size and name within limits. For a replacement, `archivo_id` and `expected_revision` are given, and the revision must equal the current one and the file must not be retired; otherwise 409. For a new KMZ, there must be no live KMZ attachment, otherwise 409 `kmz_existente`; the client then replaces. Caller has fewer than 5 pending uploads. | Insert `archivo` (new file, revision 1) if needed; insert version `subiendo` with `revision_base = revision`; insert event `subida_iniciada`. **Commit, then** issue the credential for `clave_temporal` (§2.4). | Same `Idempotency-Key` returns the same version |
| **Upload bytes** | Credential still valid. On the local backend: session, initiator, `subiendo`, before `subida_vence_en`. | Writes the **staging** object only | Re-PUT overwrites staging, which is harmless before finalization |
| **Complete** | Initiator; current scope; `subiendo`; before `completar_antes_de` | §2.4 finalization. Then, for a PDF, a conditional decision `version_actual := v` if `archivo.revision = revision_base`. For a KMZ, synchronous processing (§2.5) and then a conditional layout activation. | Terminal version: returns its stored outcome (200, same body) |
| **Cancel** | Initiator (or an administrator); `subiendo` | Version → `cancelado`; event. If the attachment has no current version and nothing else pending, it is retired in the same transaction as `sin_contenido`, which frees the one-live-KMZ slot. | Already `cancelado`: 200. Other terminal state: 409 `subida_terminada`. |
| **Expire** | `subiendo` and `now > completar_antes_de` | Same as cancel, with `expirado`. It is applied **lazily** whenever the version or its terrain's files are read or written. There is no background worker [A: review]. | Idempotent |
| **Retry processing** | `disponible` KMZ version with no `listo` or `requiere_seleccion` attempt (missing because the process died, or `error_interno`) | Runs the parser again (§2.5) | A second concurrent retry gets 409 `procesamiento_en_curso` (advisory lock, §2.6) or the newest attempt |
| **Activate** ("usar esta versión" / choose layout) | `archivos.subir`; `expected_revision`; not retired; the version is `disponible` and belongs to this attachment. KMZ: either a `listo` attempt with `utilizable=1`, or a `seleccion` that the parser then turns into one. | **This is the commit point (§2.3)** | `expected_revision` stale → 409 with the current summary |
| **Retire** | `archivos.retirar`; `expected_revision` | Sets `retirado_*`, `revision+1`, and turns every `subiendo` version of the file into `cancelado`. Nothing is deleted. KMZ: the terrain loses its active descriptor and falls back to X/Y, or to unplaced. | Stale → 409; already retired → 409 `archivo_retirado` with its state |

### 2.3 Commit point for activating a layout

The layout becomes active in exactly **one statement inside one transaction**:

```
UPDATE archivo
   SET version_actual_id = :v, geometria_activa_id = :g,
       revision = revision + 1, actualizado_en = :now, actualizado_por = :actor
 WHERE id = :archivo AND revision = :esperada AND retirado_en IS NULL
```

It is followed by `INSERT archivo_evento(accion='capa_activada', revision = :esperada + 1)`. `:g` must be a geometry of this attachment with `utilizable = 1`, checked in the same transaction before the update. Only a `rowcount` of 1 commits the pointer.

- For an **explicit choice**, `:esperada` is the client's `expected_revision`.
- For **automatic activation on completion**, `:esperada` is the version's `revision_base`. That activation happens only for a KMZ whose first run is `listo`, `utilizable`, from a single candidate, and only under decision D3.

If the update affects 0 rows, the attempt and geometry rows still commit as history. The pointer does not move, a `decision_superada` event is recorded, and the response says `aplicada: false` with `motivo` set to `superada` or `retirado`.

The descriptor that A serializes is read from `geometria_activa_id` **after** that commit. Nothing else ever writes the pointer.

### 2.4 Finalization keeps bytes immutable even while an upload credential is still valid

A credential is only ever issued for `clave_temporal`, for example `temporal/<version_id>`. The final key is `final/<version_id>/<nonce>`, with a fresh random nonce chosen by the server at each completion attempt. No credential is ever issued for that key. Completion does the following, **in this order**:

1. Load the version. If it is terminal, return its stored outcome.
2. **Copy server-side** staging → final key. This uses the provider's copy (or a local file copy), so no bytes pass through the function response.
3. **Read the final object**, streamed and bounded by the type's limit. Compute size and SHA-256 and check the magic bytes: `%PDF-` within the first 1,024 bytes, or a ZIP local-file header for KMZ.
4. If the size or SHA-256 differs from what was declared, or the magic bytes are wrong, delete **that** final object and set the version to `fallido` (`contenido_no_coincide` / `tipo_no_admitido`).
5. Otherwise, in one transaction: `UPDATE archivo_version SET estado='disponible', clave_final=:k, tamano, sha256, tipo_detectado … WHERE id=? AND estado='subiendo'`, plus event `version_disponible`.

Because the bytes are verified **after** the copy and **from the final key**, a write through a still-valid credential cannot change finalized content. Such a write can only touch the staging object, which nothing reads once the version is terminal. If two completions race, each copies to its own nonce key, only one compare-and-set wins, and the loser deletes its own copy or leaves it for the orphan sweep. The final key is never written twice.

### 2.5 Synchronous, bounded KMZ processing

After step 5 commits, the same request reads the final object (≤ 20 MiB, B-1 `MAX_KMZ_BYTES`) and calls `procesar_kmz(datos, None)`. It then inserts the attempt (and the geometry when `listo`) and runs the conditional activation (§2.3) in one transaction.

B-1's measured worst case is budget exhaustion at 13.7 s on Python 3.9 in this container. The function's `maxDuration` is 120 s. **Hosted timing is not measured** and is a hosted acceptance check (§6, H-3).

If the process dies after step 5, the version is `disponible` with no attempt. The summary then shows `procesamiento: "pendiente"` and the client offers "Reintentar", which calls **Retry processing**. Nothing is ever left in a "processing" state that someone must clear.

The choose-layout request runs `procesar_kmz(datos, seleccion)` synchronously in the same way.

### 2.6 Race outcomes (each is a required test on SQLite and disposable Postgres)

| Race | Outcome |
|---|---|
| **Late completion** (started at revision r, and another decision committed r+1 first) | The bytes become `disponible`; for a KMZ, the attempt and geometry are stored. The pointer compare-and-set fails, so the response is `aplicada:false, motivo:"superada"`. The newer decision stands. The person may later choose this version explicitly with the current `expected_revision`. |
| **Duplicate completion** (double click, retry after timeout, two tabs) | One `subiendo → disponible` compare-and-set wins. The other returns the stored outcome (or 409 `subida_terminada` if the outcome was a failure), and its extra copy is deleted. The parser runs only after the winning finalization. A rare concurrent duplicate parse is harmless: the parser is pure and the pointer is guarded. |
| **Two concurrent replacements** A and B, both from revision r | Whichever **completion commits first** becomes current (r+1). The other is `superada`, is kept in history and does not overwrite. This is *first committed decision wins*, not *last writer wins*. |
| **Retirement during upload or processing** | Retirement cancels `subiendo` versions, so a later completion gets 409 `subida_cancelada`. A completion already past finalization fails the pointer compare-and-set (`retirado_en IS NULL`), so the response is `motivo:"retirado"`. A retired file is never resurrected. |
| **Failed replacement** (verification failure, `rechazado`, `requiere_seleccion`, `error_interno`, or `utilizable=0`) | No decision is made, so the pointers keep the **last usable layout** [A: contract §3/§4]. The summary shows `ultima_falla`. An unusable geometry stays in history and cannot be activated (422 `geometria_no_utilizable`). |
| **Cancel vs complete** | Ordered by the `estado` compare-and-set. The loser gets 409 `subida_terminada` with the winner's state. |
| **Two concurrent processing retries** | Postgres: `pg_try_advisory_xact_lock(hash(version_id))`. SQLite: write transactions are already serialized, and the second run finds the first attempt. Either way, the loser returns the newest attempt or 409 `procesamiento_en_curso`. |
| **Selection racing a replacement** | The selection carries `expected_revision`, so a replacement that committed first makes it 409, and the person sees the new file. |

### 2.7 Storage and database partial failures

The invariant is this: **the database only names objects that were verified first; objects the database does not name are garbage; garbage is deleted only by sweeps; nothing a terminal version names is ever deleted in this release.**

| Failure | Recovery |
|---|---|
| Credential issuance fails after the start commit | 503 `almacen_no_disponible`. The version stays `subiendo` and expires (§2.2). A replay with the same `Idempotency-Key` tries issuance again. |
| Copy or read fails at completion (storage outage) | 503, retryable. The version stays `subiendo`. A partial final object, if any, is unnamed garbage. |
| Database commit fails after the copy | The final object is unnamed garbage, and a retry copies again under a new nonce. |
| Parser or attempt transaction fails after finalization | The version stays `disponible` without an attempt; recover with Retry processing (§2.5). |
| A final object goes missing later (provider loss) | Open/download returns 503 `contenido_no_disponible` and is logged as an integrity incident. There is no automatic repair. Backup alignment is release requirement R-6 (§5.4). |
| Staging objects of terminal versions; orphan finals | Swept by an admin-run maintenance command (`scripts/`, later), and opportunistically at upload start for the same terrain. Lifecycle rules on the bucket can expire `temporal/`. A sweep deletes only `temporal/*` of terminal or expired versions and `final/<v>/*` keys not equal to the version's `clave_final`, older than one hour. |

---

## 3. Authorization at each operation

### 3.1 Rules carried over [A]

- Capabilities: `archivos.ver`, `archivos.subir`, `archivos.retirar` (PR #10 §3.3, contract §2).
- Every route resolves its attachment, version, attempt or geometry ID **to its terrain** and calls `auth.require_terreno(request, terreno_id, capacidad)`.
- No session gives 401, a missing capability gives 403, and an unknown or out-of-scope resource gives a **non-disclosing 404**.
- Grant revocation and transfer are checked **on every request**. Lists and history are filtered before serialization. UI hiding is not access control.

### 3.2 Operation matrix [P]

| Operation | Capability | Scope resolved from | Additional rule |
|---|---|---|---|
| List a terrain's attachments / summaries | `archivos.ver` | terrain | Pending uploads are shown only to their initiator (others see "subida en curso" without details) |
| Version history, attempts, events | `archivos.ver` | attachment → terrain | Retired files are included; history is preserved |
| Start upload | `archivos.subir` | terrain | Terrain is not archived (409 `terreno_archivado`). Base archived or out of scope → 404. |
| Local byte upload | — (session) | version → terrain | Initiator only, `subiendo`, before expiry. Cloud: the storage credential is the authority (§3.3). |
| Complete | `archivos.subir` | version → terrain, **re-checked now** | Initiator only (D5) |
| Cancel | `archivos.subir` | version → terrain | Initiator, or an administrator |
| Retry processing, choose layout, "usar esta versión" | `archivos.subir` | attachment → terrain | `expected_revision` |
| Retire | `archivos.retirar` | attachment → terrain | `expected_revision` |
| Open / download a PDF or KMZ | `archivos.ver` | version → terrain | Only `disponible` versions. Issues a new short-lived read grant (§3.3). |
| Geometry descriptors | (inside A's scoped listing) | terrain | Never on public routes |
| Geometry bodies (batch or chunks) | `archivos.ver` | **each** geometry → terrain | Each ID is authorized individually (§4.3) |

### 3.3 Already-issued grants versus new access [P]

| Grant | Lifetime | What it can do | After revocation, transfer or retirement |
|---|---|---|---|
| Upload credential (signed PUT for `temporal/<v>`) | **15 minutes** (D5 default), with size and content type bound where the provider supports it | Write the staging object only | It stays technically valid until expiry and **cannot be recalled**. Its bytes are never finalized: completion re-checks scope, so a person who lost access gets 404, and retirement cancels the version. The documented revocation window is the credential lifetime. |
| Read grant (signed GET for `final/<v>/<n>`, or a local stream) | **60 seconds** (D5 default) | Read one finalized object, once or more until expiry | Cannot be recalled within the 60 s. Copies already downloaded cannot be recalled [A: contract §2.3]. |
| New grants | — | — | Every issuance is a fresh request that passes `require_terreno` at that moment. **No new grant is issued after scope loss** [A]. |

Upload start returns the upload credential in a transient `subida` object. It is the only place a credential appears. It is never stored in `archivo_version`, events, logs or the summary DTO, and it is never echoed by list or history routes. The examples use the placeholder `"<credencial-temporal-omitida>"`.

On logout or when `alcance` changes, the client aborts uploads (`api.abortPrivate`) and clears its geometry cache and upload jobs. Late callbacks from an old session are ignored, because jobs are keyed by version ID and session generation.

### 3.4 Transfer or grant revocation during an upload [P]

1. The admin moves the terrain to base Y, or revokes the operator's grant on X, while that operator's PDF is `subiendo`.
2. The operator's PUT to storage may still succeed until the credential expires (§3.3).
3. Their completion gets **404** (non-disclosing). The version stays `subiendo` and then expires. The staging object is swept.
4. Users of base Y see a pending upload by another person, without details. They can upload their own replacement, and their decisions do not depend on the orphaned upload.
5. If access is restored before `completar_antes_de`, the initiator may complete it. The compare-and-set rules still apply, so it cannot overwrite a newer decision.

### 3.5 Public visibility and history [A, restated]

None of these routes is added to `auth.PUBLIC_API`. No file operation changes public content or publication state. A boundary-only terrain keeps the existing X/Y publication blocker until the owner decides public policy separately. Retirement preserves versions, attempts, geometries and events.

---

## 4. Routes and integration requests

### 4.1 Routes [P]

The handlers live in B's `server/api/archivos.py`, and A registers them and their capabilities. Bodies are JSON unless stated otherwise. The error shape is the existing `{"error": "<es>", "detalle": {"code": "…"}}`.

| Method & path | Capability | Request | Response (examples) |
|---|---|---|---|
| `GET /api/inventario/terrenos/:id/archivos` | ver | `?retirados=1` optional | Attachments + current versions + summaries (`01`) |
| `GET /api/archivos/:aid/historial` | ver | `?antes=<numero>&limite≤50` | Versions, attempts and events, paginated |
| `POST /api/inventario/terrenos/:id/archivos/subidas` | subir | `Idempotency-Key`; `{columna_id, archivo_id?, expected_revision?, nombre, tamano, sha256}`; body ≤ 4 KB | `201 {version, archivo, subida:{metodo, url, encabezados, vence_en}}` (`02`) |
| `PUT /api/archivos/subidas/:vid/contenido` | session | Raw bytes, `Content-Length` ≤ type limit. **Local and fake backends only.** | `204` |
| `POST /api/archivos/subidas/:vid/completar` | subir | `{}` | `200 {version, intento?, archivo, aplicada, motivo?}` (`03`, `04`) |
| `POST /api/archivos/subidas/:vid/cancelar` | subir | `{}` | `200 {version}` |
| `POST /api/archivos/versiones/:vid/procesar` | subir | `{}` | `200 {intento, archivo, aplicada, motivo?}` |
| `POST /api/archivos/:aid/activar` | subir | `{version_id, expected_revision, seleccion?: [int…]}` | `200 {archivo, intento?, aplicada:true}`, or 409 / 422 (`05`) |
| `POST /api/archivos/:aid/retirar` | retirar | `{expected_revision}` | `200 {archivo}` (`06`) |
| `GET /api/archivos/versiones/:vid/contenido?modo=ver\|descargar` | ver | — | Local: a stream with `Content-Disposition` (inline or attachment, RFC 6266 `filename*`), `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`, `Cache-Control: private, no-store`. Cloud: `303` to a 60-second read grant. No JSON body ever carries the URL. |
| `POST /api/geometrias/cuerpos` | ver (per ID) | `{ids: [≤ 50 geometry IDs]}`; body ≤ 8 KB | §4.3 (`07`) |
| `GET /api/geometrias/:gid/cuerpo?trozo=n` | ver | — | §4.3 |

`POST` is used for retire, so it can carry `expected_revision`, matching A's `…/archivar`. The batch geometry read is a `POST` so a long ID list never sits in a URL or in access logs.

### 4.2 Conflict, idempotency and error codes [P]

| HTTP | `code` | When | Client behaviour |
|---|---|---|---|
| 401 | `unauthenticated` | No session | Existing flow |
| 403 | `forbidden` (+ `capacidad`) | Missing capability (A's dispatcher) | Hide action |
| 404 | `not_found` | Unknown **or** out of scope; never distinguished | Remove from view |
| 409 | `archivo_conflicto` + `revision_actual` + `archivo` | Stale `expected_revision` | Show the current state; let the person redo the action |
| 409 | `kmz_existente` | A new KMZ while a live one exists | Offer replace |
| 409 | `archivo_retirado`, `terreno_archivado` | Write on a retired file or an archived terrain | Read-only |
| 409 | `subida_terminada`, `subida_cancelada`, `subida_expirada` | Completing or cancelling a non-`subiendo` version | Stop the job; show its terminal state |
| 409 | `procesamiento_en_curso` | Concurrent retry | Re-read |
| 409 | `idempotency_conflict` | Key reused with a different body | Bug; new key |
| 413 | `archivo_demasiado_grande` (+ `limite`) | Declared or actual size over the limit | Message |
| 415 | `tipo_no_admitido` | Extension, declared or magic-byte type is not PDF/KMZ for the column | Message |
| 422 | `validation_failed` (+ `fields`), `contenido_no_coincide`, `seleccion_invalida`, `geometria_no_utilizable` | Bad input; size/hash mismatch (the version becomes `fallido`); B-1 selection errors; activating an unusable geometry | Message (B-1's Spanish text) |
| 429 | `demasiadas_subidas` | Caller has 5 pending uploads | Wait |
| 503 | `almacen_no_disponible`, `contenido_no_disponible` | Storage outage or a missing final object | Retry later; the state is unchanged |

Completion and processing answer **200 with `aplicada:false`** when the bytes or the attempt were stored but a newer decision stood. That is a successful request with a different outcome, not an error.

### 4.3 Bounded geometry delivery [P]

The descriptor and body stay separate [A]. Lists carry descriptors only, and bodies are fetched by immutable ID.

- **Batch** `POST /api/geometrias/cuerpos`: at most 50 IDs. The server authorizes **each** ID against its terrain. IDs that are unknown, out of scope or no longer active for any visible terrain go into `no_disponibles`, a single list with no reason given, so nothing is disclosed (decision D4). Bodies are packed in request order using the stored `bytes_geojson` until a **2,000,000-byte** budget would be exceeded. The rest go into `pendientes`, and the client asks for them next.
- **Large bodies**: any body with `bytes_geojson` > 1,000,000 is never put in a batch. It is listed in `por_trozos` with `{id, trozos, bytes, sha256}`. The client fetches `GET /api/geometrias/:gid/cuerpo?trozo=0…n-1`. Each chunk is ≤ 1,000,000 bytes of the **stored GeoJSON text**, split at byte offsets. The client concatenates the chunks, checks the SHA-256 (Web Crypto) and parses. Nothing is simplified, rounded or dropped [A: acceptance limits].
- **Why chunking is needed.** B-1 measured a full-limit result at about 2.8 MB of JSON. A 100,000-position body written with 15–17 significant digits can approach about 4 MB, close to the 4.5 MB function response limit. Every response here stays at or below about 2 MB plus envelope. Vercel lists streaming as a way around the response limit, but this proposal does not depend on streaming through the Python adapter.
- **Cancellation:** one `AbortController` per map render generation. A new filter, view or session aborts outstanding body requests. Server work per request is a bounded read, so an abort leaves nothing persistent.
- **Cache and invalidation:** bodies are immutable per ID, so the client keeps an in-memory `Map` keyed by geometry ID. That `Map` is what goes to `render(…, {geometrias})`. It is cleared on logout or `alcance` change, and an ID is evicted on 404 or `no_disponible`. The HTTP response carries `Cache-Control: private, no-store`, so no private geometry survives logout in the disk cache. A replaced or retired layout produces a **new descriptor ID or none**, so the stale body is simply never looked up. Unused IDs are evicted by an LRU bounded at 50 MB of estimated text.
- **Rendering cost is not solved by transport.** The disclosed extreme-multipart limit (one large part plus 19,999 small parts takes 1.5–3.3 s per view change) remains integration and release requirement R-5 (§6.4).

### 4.4 A-owned changes, order and acceptance checks [P]

| # | Owner, after | Change | Acceptance check |
|---|---|---|---|
| **P1** | A, after A-1 merges (independent of A-2) | **Attachment prerequisite migration**: the next schema version after A-1, recomputed from main when A lands it. Expected 10 at today's main, but **no number is reserved for parked PR #6**. Tables §1.2–§1.5, constraints and indexes, on SQLite and Postgres. No change to existing tables. | Upgrade A-1's schema on SQLite and disposable Postgres. Existing data is unchanged and a re-run is idempotent. Constraint tests: CHECK for column and type; one live KMZ (partial unique); a pointer to another attachment's version or geometry is rejected; no cascade (deleting a referenced terrain, user or version fails); two NULL `archivo_evento.revision` rows are allowed, duplicate non-NULL revisions are rejected. |
| **P2** | A, A-2 | `require_terreno` and the `archivos.*` capabilities exist (already in A-2's plan) | The A-2 tests already planned |
| **P3** | A, after B-3b is reviewed | Register §4.1 routes in `server/app.py` and the capability table, pointing at B's handlers. Raise the PUT body ceiling **only for `…/contenido`**, if D2 picks a PDF limit above 25 MiB. | Route-table test; every route has a capability; no session 401, missing capability 403, out of scope 404 for each route |
| **P4** | A, after P3 | `repo._dto` adds `ubicacion` and `archivos` through B's single batch helper. Public allowlist excludes both. | One extra query per page (query-count test); public catalog unchanged |
| **P5** | A, after P4 | `web/lib/inventario.js`: `t.geometria = registro.ubicacion.geometria ?? null`; `ubicado` from B's `ubicacionDe` [A] | A boundary-only terrain leaves the unplaced list; XY-only behaviour unchanged |
| **P6** | A, with B-4 | `app.js`: geometry loader (§4.3) into `render(…, {geometrias})`; mount `ArchivoCelda` and `ArchivoDetalle`; clear caches on logout and `alcance` change | Joint local milestone (§6.2) |

**No circular dependency:**
- P1 needs only A-1, because of the `base_id` FK in events.
- B-3 is built and tested **against a stacked draft of P1**, with its handlers called directly by tests. It does not need `app.py`.
- P3 registers routes only after the B-3 handlers exist.
- B-4 widgets develop against the fake backend and recorded responses.
- P4–P6 are the later integration PR, and they hold back none of the prerequisites.

---

## 5. Storage and release decisions still open

### 5.1 Provider-neutral interface (B's `server/almacen.py`) [P]

```
emitir_subida(clave_temporal, tamano, tipo, vence_en) -> {metodo, url, encabezados}
copiar(origen, destino)                      # server-side; no bytes through the function
leer(clave, limite) -> iterator[bytes]       # streamed, stops at limite
tamano_de(clave) -> int | None
emitir_lectura(clave, nombre, modo, vence_en) -> url    # cloud only
borrar(clave)                                # only temporal/* and orphan finals
listar(prefijo) -> iterator[(clave, tamano, fecha)]     # sweeps
```

Backends:
- `local`: files under `datos/archivos/` (git-ignored). The local server streams downloads. The PUT goes through `server/app.py` within today's 25 MiB `MAX_BODY`.
- `falso`: in memory, for tests, with fault injection (copy fails, read fails, object missing, staging overwritten after finalization).
- Later, **one** cloud backend chosen under D1.

**Python floor.** The local and fake backends use only the standard library, so the app keeps running on macOS Python 3.9. A cloud SDK would be a **cloud-only** dependency, declared like `psycopg` in `pyproject.toml` with a version marker, and proposed before it is added [A: AGENTS.md].

### 5.2 Cloud candidates (no purchase, provisioning, credential or environment change was made)

**Verification note.** This container's network policy blocks direct fetches of `vercel.com` and `docs.aws.amazon.com` (WebFetch failed with `ENOTFOUND`). The facts below come from official pages surfaced through web search on 2026-10-07, not from reading them in full. Before a choice, each must be confirmed by reading the page itself, and the "to verify" items by a spike in an isolated store.

| Fact | Source |
|---|---|
| Function request **and** response payload limit is 4.5 MB. An oversized request returns 413; an oversized response returns `FUNCTION_RESPONSE_PAYLOAD_TOO_LARGE`. No setting raises it. Large files should go directly to storage; streaming is listed for large responses. | [Function limits](https://vercel.com/docs/functions/limitations), [response error](https://vercel.com/docs/errors/function_response_payload_too_large), [bypass guide](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions) |
| **Vercel Private Blob is generally available** (changelog update dated June 30, 2026), on all plans. Private stores require authentication for every read and write. Signed URLs give time-limited access to one blob for a configured operation, capped at 7 days. Functions on Vercel can authenticate with short-lived OIDC tokens instead of a static read-write token. Private storage requires `@vercel/blob` ≥ 2.3 or **the Python SDK ≥ 0.5.0**. | [GA changelog](https://vercel.com/changelog/vercel-private-blob-is-now-generally-available), [private storage](https://vercel.com/docs/vercel-blob/private-storage), [signed URLs](https://vercel.com/docs/vercel-blob/vercel-signed-urls) |
| S3 conditional writes: `If-None-Match: *` on PutObject returns 412 when the key exists, and may return 409 under concurrency. AWS states it can be used with presigned URLs. | [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) |
| R2 presigned URLs work only on the S3 API domain, with expiry from 1 s to 7 days. Browser use needs CORS `AllowedHeaders` for every signed header. | [R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/) |

| Option | Fit with this proposal | To verify before choosing (spike, isolated store only) |
|---|---|---|
| **Vercel Private Blob** | Same vendor as hosting; OIDC means no static secret in the environment; signed PUT/GET; server-side `copy`. | The exact Python package and version, and its runtime Python on Vercel. That the Python SDK can issue a signed **PUT** bound to pathname, max size and content type, and a signed GET with a download filename. Server-side copy and streamed private `get` from Python. Overwrite default (`allowOverwrite`). CORS for browser PUT. |
| **S3-compatible (AWS S3 / R2)** | Mature presign and copy; S3 conditional writes; bucket lifecycle and versioning. | A library rather than handwritten signing [A: review]. Bound `Content-Length` and type in the presigned PUT. `response-content-disposition` on GET. R2 conditional-header support. Static keys in Vercel env vars, versus Vercel's OIDC. |
| Postgres `bytea` (Neon) | Only for files well under 4.5 MB. Needs chunked upload and download, and grows the database and its backups. | Not recommended |

**Recommendation:** keep the interface neutral and build B-3 against `local` and `falso`. **Vercel Private Blob is the leading candidate** for single-vendor hosting without static secrets, but only if the spike confirms the Python signed-PUT and copy path. Otherwise use S3-compatible storage with a maintained library. **This is not approval to build or provision either one** (D1).

Finalization (§2.4) does not depend on conditional writes or object versioning. It uses only copy, read and delete, which every candidate has. Conditional writes and bucket versioning are optional defence in depth.

### 5.3 How PDFs and KMZ flow without oversized bodies through the function

- **PDF opening and download.** The browser asks the app (`GET …/contenido`). The app authorizes, then answers with a stream (local) or a `303` to a 60-second read grant (cloud). The bytes go storage → browser, and the browser's own PDF viewer opens it in a new tab with `noopener`. No PDF is rendered or parsed on the server beyond the magic-byte check.
- **Upload.** Browser → storage directly, using the credential. Only the small start and completion requests pass through the function.
- **KMZ processing.** Inside the completion function: a server-side copy, then a server-side streamed read of ≤ 20 MiB. That is an outbound request from the function, not the function's request or response body. Parsing uses B-1's ≤ 59 MiB peak, as measured. The response carries the summary and attempt, **never the body**.
- **Geometry to the map.** §4.3, with chunks ≤ 1 MB.

### 5.4 Release requirements carried forward [P]

| ID | Requirement |
|---|---|
| R-1 | Separate stores or prefixes with **separate credentials** for local tests, Preview and Production. No public access. CORS limited to the app's origins. |
| R-2 | Lifecycle rule for `temporal/` (expire after 1 day). No lifecycle rule on `final/`. |
| R-3 | Hosted timing for the slowest B-1 cases within `maxDuration`, plus response sizes (H-3, H-4). |
| R-4 | Documented revocation windows: 15 minutes for upload, 60 seconds for read (or the decided values). |
| R-5 | A measured, bounded display strategy with an explicit deferred-outline status for the extreme-multipart case, **before hosted employee rollout** [A: B-2 acceptance]. It does not redesign B-2 here and never silently simplifies. |
| R-6 | Storage backup and versioning aligned with the Neon backup schedule, so database rows and objects can be restored together. Restore drill in Preview. |
| R-7 | Real company KMZ samples (5–10, shared privately, never committed) before geography acceptance [A: B-1 acceptance]. |

---

## 6. Acceptance matrix and next PR split

### 6.1 Local and disposable-database matrix (B-3, with P1)

Every row runs on SQLite **and** on the disposable Postgres in CI, with fictional files and the `falso` backend unless noted.

| ID | Scenario | Expected |
|---|---|---|
| M-1 | New PDF: start → upload → complete | `disponible`; `version_actual` set; revision 2; events; `inventory_terrain.version` unchanged |
| M-2 | Single-polygon KMZ on a blank terrain (`local` backend) | Attempt `listo`, geometry `utilizable`, layout active (D3 default); descriptor bbox equals body bbox |
| M-3 | KMZ with 3 lots → `requiere_seleccion` → `activar` with `[0, 2]` | One multipart geometry, activated with `expected_revision` |
| M-4 | Bad selections `[0, 0]`, `[0.0]`, `[]`, `[9]` | 422 `seleccion_invalida`, pointers unchanged, nothing raised |
| M-5 | Replacement rejected (`rechazado`) / `utilizable=0` / size mismatch | The previous layout is still active; `ultima_falla` shown; activating the unusable one → 422 |
| M-6 | Late completion after another decision | `aplicada:false, motivo:"superada"`; newer pointer intact; bytes in history |
| M-7 | Duplicate completion (sequential and concurrent threads) | One finalization; same response body; exactly one final key named by the database |
| M-8 | Two concurrent replacements | First committed wins; second `superada`; neither overwrites the other |
| M-9 | Retire during `subiendo` and during processing | 409 `subida_cancelada` / `motivo:"retirado"`; never resurrected; X/Y fallback |
| M-10 | Staging overwritten after finalization (simulated still-valid credential) | Finalized SHA-256 and bytes unchanged; downloads return the original |
| M-11 | Fault injection: copy fails, read fails, database fails after copy, process "dies" after finalization | 503 and retry, or Retry processing; no database reference to an unverified object; orphan sweep removes only garbage |
| M-12 | Pointer integrity | Activating another attachment's geometry, or an unusable one, is rejected (FK or transaction) |
| M-13 | Immutability | No repository path updates a terminal version, attempt or geometry (test of the guarded updates) |
| M-14 | Expiry | A version past `completar_antes_de` becomes `expirado` lazily; completion → 409; a cancelled first upload frees the KMZ slot |
| M-15 | Idempotent start | Same key → same version; same key with a different body → 409 |
| M-16 | Limits | PDF at the limit and one byte over; KMZ at 20 MiB and one byte over; wrong magic bytes → 415; 6th pending upload → 429 |

### 6.2 Scope, revocation and route matrix (after P2/P3)

| ID | Scenario | Expected |
|---|---|---|
| S-1 | Every §4.1 route: no session / no capability / out of scope | 401 / 403 / 404 |
| S-2 | Mixed batch of geometry IDs (own base, other base, unknown, retired) | Only own-base bodies; the rest in one undifferentiated `no_disponibles` |
| S-3 | Revoke the grant between start and completion | Completion 404; the version expires; staging swept |
| S-4 | Transfer the terrain while a KMZ is `subiendo` | Source-only user: 404. Destination user sees the pending upload without details and can replace. |
| S-5 | Read grant after revocation | No new grant (404); an existing grant expires within 60 s (documented) |
| S-6 | Public catalog | No `ubicacion.geometria`, `archivos`, keys or URLs |
| S-7 | Logout during upload and geometry loading | Requests aborted; caches cleared; late callbacks ignored |

### 6.3 Smallest local integration (joint milestone, after P4–P6)

On the local server with SQLite and then disposable Postgres, an operator granted only base X:
1. Create a blank terrain.
2. Upload a fictional PDF, then open it.
3. Upload a single-polygon fictional KMZ, then reload.
4. The listing has `ubicacion.modo = "geometria"` with blank X/Y. The body loads through the batch route, and the map draws the outline (browser test with real mouse input).
5. Replace the KMZ with a rejected file. The old outline stays.
6. Retire the KMZ. The terrain becomes unplaced.
7. A user of base Y gets 404 throughout.

### 6.4 Hosted checks (separate evidence, after D1 and owner-authorized provisioning)

| ID | Check |
|---|---|
| H-1 | Direct browser PUT to the isolated Preview store, CORS, size and type binding |
| H-2 | 303 → read grant opens a PDF, expires on time, and has the right `Content-Disposition` |
| H-3 | Slowest B-1 cases (budget exhaustion, a 100k-vertex body) complete within `maxDuration`, with timing recorded |
| H-4 | Largest body delivered in chunks ≤ 1 MB, with each response size recorded |
| H-5 | Revocation windows observed as documented |
| H-6 | Restore drill (R-6) |
| H-7 | R-5 display strategy measured on the hosted build |

### 6.5 Next PR split [P]

| Order | PR | Owner | Depends on |
|---|---|---|---|
| 1 | A-1 schema foundation (in progress) | A | — |
| 2 | **P1** attachment prerequisite migration | A | A-1 merged; this contract consolidated |
| 3 | **B-3a** `server/almacen.py` (`local`, `falso`) + `server/repo/archivos.py` state machine; M-1…M-16 | B | Stacked on the P1 draft; merges after P1 |
| 4 | A-2 roles, grants, `require_terreno` (P2) | A | A-1 |
| 5 | **B-3b** `server/api/archivos.py` handlers; batch and chunk geometry routes | B | B-3a, A-2 |
| 6 | **P3** route registration | A | B-3b reviewed |
| 7 | **B-4** `ArchivoCelda`, `ArchivoDetalle`, `subidas.js`, geometry loader module | B | B-3b (fake backend for development) |
| 8 | **P4–P6** DTO, adapter, app mount; joint milestone §6.3 | A with B | P3, B-4, A's grid |
| 9 | Cloud storage backend + H-1…H-7 | B, owner provisions | D1 decided; owner authorizes an isolated store |
| 10 | Extreme-multipart display strategy (R-5) | B | Before hosted rollout |

B-3a and B-3b can start once this contract is frozen and the P1 draft exists. No step waits on a later one.

---

## 7. Genuine unresolved decisions

| # | Decision | Recommended default | Blocks |
|---|---|---|---|
| **D1** | Cloud storage provider | Neutral interface now. Spike Vercel Private Blob first in an isolated store, with S3-compatible as the fallback (§5.2). Owner authorizes the spike and provisioning. | Hosted uploads only (step 9). Not B-3 or the local milestone. |
| **D2** | File size limits | PDF ≤ 25 MiB (the local body limit; no global raise), KMZ ≤ 20 MiB (B-1). Revisit after real samples. A higher PDF limit needs P3 to raise the limit for `…/contenido` only. | B-3a constants, P3 |
| **D3** | Does uploading a single-polygon KMZ count as the explicit selection? | **Yes**: an upload into the KMZ cell is the operator's explicit choice when there is exactly one valid, usable candidate. Several candidates always need the chooser. Unusable geometry is never activated. Both paths go through the same compare-and-set and are audited as `capa_activada` with the uploader as actor. | B-3a state machine, B-4 UX. Contract §4's "explicitly selected" needs this reading confirmed. |
| **D4** | Batch geometry with unauthorized IDs | Per-ID: return the authorized bodies and an undifferentiated `no_disponibles` list. The alternative is to fail the whole batch with 404. | B-3b route contract |
| **D5** | Grant lifetimes and who completes | Upload credential 15 minutes, completion deadline 60 minutes, read grant 60 seconds. Only the initiator may complete; the initiator or an administrator may cancel. | B-3a/B-3b constants; release note R-4 |

**Proposed defaults, not decisions:**
- 5 pending uploads per user.
- History page of 50.
- 50 IDs and 2 MB per geometry batch; 1 MB chunks.
- Retired files are not restorable in this release. Restoring a retired KMZ would be a new upload; a restore decision can come with A's archive policy.

---

## 8. Files in this PR

- `reports/team-b-attachments-contract-2026-10-07/REPORT.md`: this proposal.
- `reports/team-b-attachments-contract-2026-10-07/examples/*.json`: small fictional request and response examples. Each ID is a fictional placeholder, and every credential is replaced by `"<credencial-temporal-omitida>"`.

**Checks run:** the example JSON parses (`python3 -m json.tool` on each file). No application test is affected, because no application file changed. `./verificar.sh` was not run: this container has no `zsh`, and the PR adds only Markdown and JSON under `reports/`. CI runs on the PR.
