# Team A — P1 attachment prerequisite migration (schema 10)

Storage for terrain attachments (PDF and KMZ): the six tables Team B's
attachment repository will write. **Schema only.** No repository, authorization,
route, screen or storage provider is added, and nothing writes these tables yet.

- Instruction commit: `84b2b84a05592b9f31b860e831925990274b481b`
  (`reports/next-parallel-packets-2026-10-08/`).
- Source proposal: PR #12 at `28bf0dbbf718571e35d501a7810d7e7d882ee3dd`,
  §§1.2–1.5, 9.2, 9.4, as narrowed by the packet.
- `origin/main`: `09452fd26d38319567dce28a89db100ea61c739a`, unchanged. It does
  not contain A-1, and no other schema change exists on it.
- **Depends on A-1**, PR #14 at `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`
  (schema 9). This branch, `claude/team-a/attachment-schema`, starts at that
  commit and its PR targets `claude/team-a/schema-9`. **It must not merge before
  PR #14.** PR #14 is unchanged.
- Schema 9 → **10**. Excel PR #6 untouched; no number taken from or reserved for it.

## Schema map for Team B

Definitions: `server/db.py`, `ATTACHMENT_SCHEMA`. Postgres derives its DDL from
the same text (`postgres.archivos_sql()`). **Every table and column name is the
proposal's; nothing was renamed**, so no adapter mapping is needed. Keys are
`TEXT PRIMARY KEY NOT NULL` UUIDs; timestamps are ISO-8601 UTC text; actors
reference `team_user(id)`. No table is in `postgres.ID_TABLES`.

| Table | Columns |
|---|---|
| `archivo` | `id`, `inventory_id`, `columna_id`, `tipo`, `revision` (default 1), `version_actual_id`, `geometria_activa_id`, `retirado_en`, `retirado_por`, `retirado_motivo`, `creado_en`, `creado_por`, `actualizado_en`, `actualizado_por` |
| `archivo_version` | `id`, `archivo_id`, `inventory_id`, `numero`, `estado`, `revision_base`, `nombre_original`, `tamano_declarado`, `sha256_declarado`, `tamano`, `sha256`, `tipo_detectado`, `clave_temporal`, `clave_final`, `subida_vence_en`, `completar_antes_de`, `error_codigo`, `error_mensaje`, `aplicada`, `motivo_no_aplicada`, `iniciado_en`, `iniciado_por`, `finalizado_en`, `finalizado_por`, `terminado_en`, `terminado_por` |
| `archivo_intento` | `id`, `archivo_version_id`, `numero`, `origen`, `seleccion_json`, `resultado`, `resultado_json`, `analizador`, `geometria_id`, `creado_en`, `creado_por` |
| `geometria` | `id`, `archivo_id`, `archivo_version_id`, `inventory_id`, `intento_id`, `geojson`, `bbox_oeste`, `bbox_sur`, `bbox_este`, `bbox_norte`, `punto_lon`, `punto_lat`, `partes`, `huecos`, `vertices`, `area_aproximada_m2`, `utilizable`, `bytes_geojson`, `sha256_geojson`, `creado_en` |
| `archivo_evento` | `id`, `archivo_id`, `inventory_id`, `archivo_version_id`, `intento_id`, `geometria_id`, `accion`, `revision`, `base_id`, `actor_id`, `actor_name`, `at`, `details_json` |
| `archivo_trabajo` | `archivo_version_id` (PK), `trabajo_id`, `actor_id`, `operacion`, `inicio`, `vence_en` |

Enumerations (CHECK): `columna_id` `core:archivos`/`core:kmz`; `tipo` `pdf`/`kmz`,
paired with its column; `retirado_motivo` `usuario`/`sin_contenido`; `estado`
`subiendo`/`disponible`/`fallido`/`cancelado`/`expirado`; `motivo_no_aplicada`
`superada`/`retirado`; `origen` `completar`/`reintento`/`seleccion`; `resultado`
`listo`/`requiere_seleccion`/`rechazado`/`error_interno`; `accion` the ten values
of §1.5; `operacion` `completar`/`procesar`/`activar`. Counters `revision`,
`revision_base`, `numero` are > 0. Byte sizes and `partes`/`huecos`/`vertices`
are ≥ 0 (zero holes, and zero of the others, are storable). No byte cap,
duration or name length is in the DDL.

### Relationships

| Rule | How it is enforced |
|---|---|
| A version belongs to its attachment and that attachment's terrain | `archivo_version (archivo_id, inventory_id)` → `archivo (id, inventory_id)` |
| A geometry belongs to its version, attachment and terrain | `geometria (archivo_version_id, archivo_id, inventory_id)` → `archivo_version (id, archivo_id, inventory_id)` |
| A geometry is the result of exactly the attempt it names, and of that version | `geometria (intento_id, archivo_version_id, id)` → `archivo_intento (id, archivo_version_id, geometria_id)`; `intento_id` UNIQUE |
| An attempt's `geometria_id` is its own geometry, not another attempt's | **deferred** `fk_archivo_intento_geometria`: `(geometria_id, id, archivo_version_id)` → `geometria (id, intento_id, archivo_version_id)` |
| Only a `listo` attempt has a geometry, and it always has one | CHECK `(geometria_id IS NOT NULL) = (resultado = 'listo')` |
| The current version belongs to the attachment | **deferred** `fk_archivo_version_actual`: `(id, version_actual_id)` → `archivo_version (archivo_id, id)` |
| The active geometry belongs to **the current version** | **deferred** `fk_archivo_geometria_activa`: `(id, version_actual_id, geometria_activa_id)` → `geometria (archivo_id, archivo_version_id, id)` |
| An active geometry needs a current version and a KMZ attachment | CHECK `geometria_activa_id IS NULL OR (version_actual_id IS NOT NULL AND tipo = 'kmz')` |
| One live KMZ attachment per terrain | unique index on `archivo(inventory_id)` where `core:kmz` and not retired |
| Version and attempt numbers are unique per owner | `UNIQUE (archivo_id, numero)`, `UNIQUE (archivo_version_id, numero)` |
| One completion attempt per version | unique index on `archivo_intento(archivo_version_id)` where `origen = 'completar'` |
| An event's version, attempt and geometry belong to its attachment and terrain, and to each other | four composite keys on `archivo_evento`, plus CHECKs that an attempt or geometry reference always comes with its version (so a NULL cannot switch a key off) |
| One decision event per attachment revision; informational events repeat | `UNIQUE (archivo_id, revision)`, `revision` nullable |
| One lease per version | `archivo_trabajo.archivo_version_id` is the primary key |
| Nothing cascades | no `ON DELETE` anywhere; a referenced terrain, account, attachment, version, attempt or geometry cannot be deleted |

The three `fk_archivo_*` constraints close cycles. They are `DEFERRABLE INITIALLY
DEFERRED` on both databases and, on Postgres, added after the tables exist, the
same way as the existing `fk_inventory_*` pair. **They report at COMMIT**, not at
the statement.

### Upload state and outcome (per row, enforced by CHECK)

| `estado` | `terminado_en` | `finalizado_en/por` | `aplicada` | `motivo_no_aplicada` | `clave_final`, `tamano`, `sha256` |
|---|---|---|---|---|---|
| `subiendo` | NULL | NULL | NULL | NULL | free (normally NULL) |
| `disponible` | set | set | 0 or 1 | only with `aplicada = 0` | all three required |
| `fallido` | set | set | 0 | NULL | free |
| `cancelado`, `expirado` | set | NULL | NULL | NULL | free |

`terminado_*` means the row stopped being `subiendo`, for any reason.
`finalizado_*` means the bytes were finalized and judged; only `disponible` and
`fallido` have it. `terminado_por` and `retirado_por` may be NULL on a
terminal/retired row (lazy expiry has no natural actor) but never set on a row
that is not terminal/retired.

## Stricter than the proposal: review these

1. **Attempt ↔ geometry is mutual and exact.** The proposal had
   `geometria (intento_id, archivo_version_id)` → attempt. Here the geometry's key
   also carries its own `id` into `archivo_intento.geometria_id`, and `listo` ⇔
   `geometria_id IS NOT NULL`. Consequence for writers: insert the `listo` attempt
   **with** its `geometria_id`, then the geometry, in one transaction. A geometry
   cannot be attached to a non-`listo` attempt.
2. **`disponible` requires `clave_final`, `tamano`, `sha256`.** Stated in §1.3 as
   "set only on → disponible"; here it is a CHECK in that one direction.
   `tipo_detectado` is not required.
3. **`finalizado_en` and `finalizado_por` are set together**, and exactly for
   `disponible`/`fallido`. **`terminado_en` is set exactly when not `subiendo`.**
4. **Retirement:** `retirado_motivo` is set exactly when `retirado_en` is.
5. **An event's attempt or geometry reference requires its version reference.**
6. **Not stricter, on purpose:** `tipo_detectado`, `error_codigo` and
   `nombre_original` content; that a geometry belongs to a KMZ (only the *active*
   pointer checks the type); state of the version a lease or an attempt refers to.

If any of 1–5 contradicts the intended lifecycle, name the case and it is a
one-line change before B consumes the schema.

## What the database does not enforce (future repository obligations)

- Activation: the version is `disponible`, the geometry's attempt is `listo`
  (implied by 1 above) and `utilizable = 1`, checked in the activation
  transaction with the authorization re-check, before the pointer update.
- Decisions are compare-and-set on `archivo.revision` and `retirado_en IS NULL`;
  each inserts its event with the new revision. Attachment writes never touch
  `inventory_terrain.version`, `updated_at/by` or `inventory_event`.
- Terminal `archivo_version` rows, attempts and geometries are never updated:
  every `UPDATE archivo_version` is guarded by `estado = 'subiendo'`.
- Attempts and geometries only for KMZ versions that are `disponible`; attempts
  are inserted terminal; `origen` matches the operation.
- `archivo_evento` is append-only; `base_id` is the terrain's base at event time;
  `details_json` holds no storage key or signed URL; the actor comes from the
  session. `revision` is set only by events that moved `archivo.revision`.
- Leases: take only when none is live, fence the final commit on `trabajo_id` and
  `vence_en`, delete on completion. No cleanup job exists. Lazy expiry applies
  only without a live lease.
- `bytes_geojson`/`sha256_geojson` describe exactly the stored `geojson` text.
  A delivery envelope needs its own size/hash, elsewhere.
- Coordinates stay GeoJSON `[lon, lat]`; nothing is written to the terrain's X/Y,
  area or price.
- Size, name-length, pending-upload and duration limits.
- **SQLite and deferred keys:** `db.transaction()` is a SAVEPOINT. A deferred
  violation surfaces when the outermost one is released (the commit), not at the
  statement, and the connection must then be rolled back or closed. Writers
  should validate first and treat the constraints as the backstop.

## Backup, seed and restore

- `postgres.ATTACHMENT_TABLES` = `archivo`, `archivo_version`, `archivo_intento`,
  `geometria`, `archivo_evento`, appended to `postgres.TABLES` after every table
  they reference. Cloud backups carry them; `setup_cloud.py` seeds them in that
  order inside its single transaction, which is what lets the deferred cycles load.
- **`archivo_trabajo` is not backed up or seeded.** A restore has no leases.
- **A pending upload after a restore** is a `subiendo` row with no lease. That is
  the ordinary "no live lease" state: the next completion request may take a
  lease, and after `completar_antes_de` it expires lazily. Staged bytes are the
  storage provider's concern, not this schema's.
- A test deletes all attachment rows and reloads a backup-shaped copy table by
  table in that order, including an activated KMZ (the full cycle) and a pending
  upload, in one transaction on each database.

## Release note

- **New schema version: 10.** Additive: six tables and their indexes. No existing
  table, column or row changes.
- **Upgrade path:** 9 → 10, and directly from 7 or 8 (the step creates the
  earlier tables first). SQLite upgrades on first open after its automatic
  backup. Postgres upgrades through the existing reviewed command path as a
  release step. Re-running changes nothing.
- **Rollback:** restore the backup taken before the step. Code at schema 8 or 9
  keeps working against a schema-10 database; it ignores the new tables.
- Needs A-1 (schema 9) first. No account, provider, credential or production
  access is involved.

## Evidence

`tests/test_schema_v10.py`: one set of checks on a populated schema-9 SQLite file
and a populated schema-9 Postgres schema (accounts, a grant, a work base, two
local columns, an assigned terrain with history, a legacy base and a saved map),
all fictional. Every statement runs in a committed transaction.

A removal check was run locally on SQLite: each table constraint and unique
index of `ATTACHMENT_SCHEMA` was deleted in turn and the suite rerun. Every
removal made a test fail except four that another constraint already implies
(the two single-column enums on `archivo` covered by the column/type pair,
`estado`'s enum covered by the state checks, and `geometria.intento_id UNIQUE`
covered by the mutual attempt key). They are kept as the proposal lists them.

Tested commit, local results and the GitHub Actions run on disposable Postgres
are in the PR. Local runs skip Postgres.

## Next

Stop for review of P1. A-2/P2 authorization is not started.
