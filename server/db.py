"""SQLite connection, schema and migrations.

The whole application state lives in one file so the user can back it up by
copying it. The location is next to the app by default, and overridable with the
ARA_MAP_DB environment variable.
"""

from __future__ import annotations

import itertools
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .protocols import DatabaseConnection

APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = APP_ROOT / "datos" / "ara_map.db"
BACKUPS_KEPT = 10

SCHEMA_VERSION = 10

# Savepoint names only need to be unique while nested.
_savepoints = itertools.count()

SCHEMA = """
-- Folders organize bases and saved maps; they hold nothing themselves. Each
-- dashboard has its own flat set, told apart by tipo. nombre_clave is the
-- folded name, so "Cliente Norte" and "cliente  norte" cannot both exist.
-- AUTOINCREMENT so a deleted folder's id is never handed to a new one.
CREATE TABLE IF NOT EXISTS carpeta (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo           TEXT NOT NULL CHECK (tipo IN ('bases', 'mapas')),
  nombre         TEXT NOT NULL,
  nombre_clave   TEXT NOT NULL,
  creado_en      TEXT NOT NULL,
  actualizado_en TEXT NOT NULL,
  UNIQUE (tipo, nombre_clave)
);

-- AUTOINCREMENT, not a plain rowid. A plain INTEGER PRIMARY KEY is reused once
-- the highest row is deleted, and a saved map that still remembers that id
-- would silently re-attach to whatever unrelated workbook was imported next.
-- carpeta_id NULL means "Sin carpeta".
CREATE TABLE IF NOT EXISTS base (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre         TEXT NOT NULL,
  archivo_origen TEXT,
  hoja           TEXT,
  importado_en   TEXT NOT NULL,
  notas          TEXT,
  carpeta_id     INTEGER REFERENCES carpeta(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS terreno (
  id               INTEGER PRIMARY KEY,
  base_id          INTEGER NOT NULL REFERENCES base(id) ON DELETE CASCADE,
  id_origen        INTEGER,
  orden            INTEGER NOT NULL,
  terreno          TEXT NOT NULL,
  estado           TEXT,
  municipio        TEXT,
  direccion        TEXT,
  superficie_m2    REAL,
  superficie_ha    REAL,
  afectaciones_pct REAL,
  afectaciones_m2  REAL,
  asking_price     REAL,
  asking_m2        REAL,
  lat              REAL,
  lon              REAL,
  clave_dedupe     TEXT NOT NULL,
  extra_json       TEXT,
  -- The currency of asking_price/asking_m2 as imported. NULL means unknown:
  -- rows from before prices carried a currency are never relabelled.
  moneda           TEXT CHECK (moneda IN ('USD', 'MXN'))
);
CREATE INDEX IF NOT EXISTS idx_terreno_base  ON terreno(base_id);
CREATE INDEX IF NOT EXISTS idx_terreno_clave ON terreno(base_id, clave_dedupe);

CREATE TABLE IF NOT EXISTS incidencia (
  id         INTEGER PRIMARY KEY,
  terreno_id INTEGER NOT NULL REFERENCES terreno(id) ON DELETE CASCADE,
  severidad  TEXT NOT NULL,
  codigo     TEXT NOT NULL,
  mensaje    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidencia_terreno ON incidencia(terreno_id);

CREATE TABLE IF NOT EXISTS mapa (
  id             INTEGER PRIMARY KEY,
  nombre         TEXT NOT NULL,
  tipo           TEXT NOT NULL CHECK (tipo IN ('simple', 'comparacion')),
  creado_en      TEXT NOT NULL,
  actualizado_en TEXT,
  config_json    TEXT,
  -- Whether this map's title tracks its source's name. Kept out of
  -- config_json, which "Guardar vista" replaces wholesale.
  nombre_sigue_base INTEGER NOT NULL DEFAULT 0,
  carpeta_id     INTEGER REFERENCES carpeta(id) ON DELETE SET NULL
);

-- A layer records WHERE its terrains came from. base_id is deliberately not a
-- foreign key: a saved map is a frozen record and must survive the deletion of
-- the base it was taken from, so the name is kept alongside the id.
CREATE TABLE IF NOT EXISTS mapa_capa (
  mapa_id     INTEGER NOT NULL REFERENCES mapa(id) ON DELETE CASCADE,
  orden       INTEGER NOT NULL,
  base_id     INTEGER,
  -- The raw source name on its own, so renaming a source updates it without
  -- destroying the version text that distinguishes two snapshots of it.
  base_nombre TEXT    NOT NULL,
  version_etiqueta TEXT,
  color       TEXT    NOT NULL,
  visible     INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (mapa_id, orden)
);

-- The frozen terrains. One row per terrain per layer, copied at save time.
CREATE TABLE IF NOT EXISTS mapa_terreno (
  id               INTEGER PRIMARY KEY,
  mapa_id          INTEGER NOT NULL REFERENCES mapa(id) ON DELETE CASCADE,
  capa_orden       INTEGER NOT NULL,
  terreno_id       INTEGER,
  orden            INTEGER NOT NULL,
  id_origen        INTEGER,
  terreno          TEXT NOT NULL,
  estado           TEXT,
  municipio        TEXT,
  direccion        TEXT,
  superficie_m2    REAL,
  superficie_ha    REAL,
  afectaciones_pct REAL,
  afectaciones_m2  REAL,
  asking_price     REAL,
  asking_m2        REAL,
  lat              REAL,
  lon              REAL,
  clave_dedupe     TEXT NOT NULL,
  extra_json       TEXT,
  incidencias_json TEXT,
  moneda           TEXT
);
CREATE INDEX IF NOT EXISTS idx_mapa_terreno ON mapa_terreno(mapa_id, capa_orden);

-- Confirmed import formats, reused automatically when a file's headers match.
-- An import configuration, not organization: separate from carpeta. Holds the
-- header signature and what each header became -- never any cell value.
-- A changed format is a new version; the old one is marked, not overwritten.
CREATE TABLE IF NOT EXISTS formato_importacion (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre          TEXT NOT NULL,
  firma           TEXT NOT NULL,
  firma_clave     TEXT NOT NULL,
  config_json     TEXT NOT NULL,
  plan_version    INTEGER NOT NULL,
  version         INTEGER NOT NULL DEFAULT 1,
  reemplazado_por INTEGER REFERENCES formato_importacion(id) ON DELETE SET NULL,
  usos            INTEGER NOT NULL DEFAULT 0,
  creado_en       TEXT NOT NULL,
  actualizado_en  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_formato_firma ON formato_importacion(firma_clave);

-- One row per confirmed import or append: which file, which table, which
-- plan. Appending adds a row; it never rewrites the original import's.
CREATE TABLE IF NOT EXISTS importacion (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  base_id         INTEGER REFERENCES base(id) ON DELETE CASCADE,
  tipo            TEXT NOT NULL CHECK (tipo IN ('nueva', 'agregar')),
  archivo         TEXT,
  sha256          TEXT,
  hoja            TEXT,
  fila_encabezado INTEGER,
  plan_json       TEXT NOT NULL,
  formato_id      INTEGER REFERENCES formato_importacion(id) ON DELETE SET NULL,
  formato_version INTEGER,
  creado_en       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_importacion_base ON importacion(base_id);

-- Automatic-assistance usage, for the monthly spend cap. Counts and costs
-- only: no headers, samples or file content are ever recorded here.
CREATE TABLE IF NOT EXISTS uso_ia (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  creado_en      TEXT NOT NULL,
  mes            TEXT NOT NULL,
  proveedor      TEXT NOT NULL,
  modelo         TEXT,
  estado         TEXT NOT NULL,
  tokens_entrada INTEGER,
  tokens_salida  INTEGER,
  costo_usd      REAL NOT NULL,
  latencia_ms    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_uso_ia_mes ON uso_ia(mes);
"""

# v8: the shared terrain inventory and individual team accounts. Additive: no
# legacy table is touched. Ids are text UUIDs, so none of these tables is in
# postgres.ID_TABLES. Timestamps are ISO text, except the two compared against
# the clock (session expiry, login failures), which are epoch seconds.
#
# inventory_terrain <-> inventory_revision reference each other. A terrain is
# inserted with NULL pointers, then its first revision, then the draft pointer
# is set, all in one transaction. The pointer foreign keys are composite, so a
# pointer can only name a revision OF THAT SAME terrain, and deferred, so a
# restore may load the two tables in either order. Postgres cannot create the
# cycle in one statement: postgres.py strips the two "fk_inventory_" lines and
# adds those constraints after both tables exist.
INVENTORY_SCHEMA = """
-- rol arrives through V9_COLUMNS. Nothing reads it yet: until role enforcement
-- ships, every active account still has identical powers.
CREATE TABLE IF NOT EXISTS team_user (
  id                  TEXT PRIMARY KEY,
  login               TEXT NOT NULL UNIQUE,
  display_name        TEXT NOT NULL,
  password_hash       TEXT NOT NULL,
  active              INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  credential_revision INTEGER NOT NULL DEFAULT 1,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

-- Only the SHA-256 of a session token is stored. Operational, not content:
-- excluded from backups.
CREATE TABLE IF NOT EXISTS team_session (
  token_hash          TEXT PRIMARY KEY,
  user_id             TEXT NOT NULL REFERENCES team_user(id) ON DELETE CASCADE,
  credential_revision INTEGER NOT NULL,
  created_at          TEXT NOT NULL,
  expires_at          REAL NOT NULL,
  revoked_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_team_session_user ON team_session(user_id);

CREATE TABLE IF NOT EXISTS team_login_failure (
  login     TEXT NOT NULL,
  failed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_login_failure ON team_login_failure(login, failed_at);

-- One permanent identity per independently tracked terrain listing. version
-- is the concurrency counter: every change to the record increments it.
-- first_published_at survives unpublishing, telling "never published" apart
-- from "withdrawn".
CREATE TABLE IF NOT EXISTS inventory_terrain (
  id                    TEXT PRIMARY KEY,
  version               INTEGER NOT NULL,
  draft_revision_id     TEXT,
  published_revision_id TEXT,
  published_at          TEXT,
  first_published_at    TEXT,
  archived_at           TEXT,
  created_at            TEXT NOT NULL,
  created_by            TEXT NOT NULL REFERENCES team_user(id),
  updated_at            TEXT NOT NULL,
  updated_by            TEXT NOT NULL REFERENCES team_user(id),
  CONSTRAINT fk_inventory_draft FOREIGN KEY (id, draft_revision_id) REFERENCES inventory_revision(inventory_id, id) DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_inventory_published FOREIGN KEY (id, published_revision_id) REFERENCES inventory_revision(inventory_id, id) DEFERRABLE INITIALLY DEFERRED
);

-- Immutable content revisions: inserted, never updated. Field names and
-- meanings match terreno; NULL keeps meaning "unknown" (currency included).
-- contacto, notas_internas and extra_json are private and never projected.
CREATE TABLE IF NOT EXISTS inventory_revision (
  id                        TEXT PRIMARY KEY,
  inventory_id              TEXT NOT NULL REFERENCES inventory_terrain(id),
  revision_number           INTEGER NOT NULL,
  terreno                   TEXT,
  estado                    TEXT,
  municipio                 TEXT,
  direccion                 TEXT,
  superficie_m2             REAL,
  superficie_ha             REAL,
  afectaciones_pct          REAL,
  afectaciones_m2           REAL,
  asking_price              REAL,
  asking_m2                 REAL,
  moneda                    TEXT CHECK (moneda IN ('USD', 'MXN')),
  lat                       REAL,
  lon                       REAL,
  price_on_request          INTEGER NOT NULL DEFAULT 0 CHECK (price_on_request IN (0, 1)),
  availability              TEXT NOT NULL DEFAULT 'unknown'
    CHECK (availability IN ('unknown', 'available', 'negotiation', 'sold', 'withdrawn')),
  public_description        TEXT,
  contacto                  TEXT,
  notas_internas            TEXT,
  extra_json                TEXT,
  price_confirmed_at        TEXT,
  price_confirmed_by        TEXT REFERENCES team_user(id),
  availability_confirmed_at TEXT,
  availability_confirmed_by TEXT REFERENCES team_user(id),
  created_at                TEXT NOT NULL,
  created_by                TEXT NOT NULL REFERENCES team_user(id),
  UNIQUE (inventory_id, revision_number),
  UNIQUE (inventory_id, id)
);

-- Append-only history. One event per version, so a lost compare-and-set can
-- never record a second "version N".
CREATE TABLE IF NOT EXISTS inventory_event (
  id                 TEXT PRIMARY KEY,
  inventory_id       TEXT NOT NULL REFERENCES inventory_terrain(id),
  version            INTEGER NOT NULL,
  action             TEXT NOT NULL,
  actor_id           TEXT NOT NULL REFERENCES team_user(id),
  actor_name         TEXT NOT NULL,
  at                 TEXT NOT NULL,
  before_revision_id TEXT REFERENCES inventory_revision(id),
  after_revision_id  TEXT REFERENCES inventory_revision(id),
  details_json       TEXT,
  UNIQUE (inventory_id, version)
);

-- Durable Idempotency-Key results, written in the same transaction as the
-- business change they describe.
CREATE TABLE IF NOT EXISTS inventory_operation_result (
  operation       TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash    TEXT NOT NULL,
  result_json     TEXT NOT NULL,
  actor_id        TEXT NOT NULL REFERENCES team_user(id),
  created_at      TEXT NOT NULL,
  PRIMARY KEY (operation, idempotency_key)
);
"""

# v9: work bases, access grants, base-local custom columns and their audit.
# Storage only: no route, role check or screen uses these yet.
#
# Nothing here cascades. A base, account or column that anything refers to
# cannot be deleted, so removing one can never take terrains, revisions,
# retained custom values or history with it; bases and columns are archived
# or retired instead. Grants are the exception that IS deleted: a revoked
# grant survives as its team_user_event rows, which name the user and the
# base rather than the grant.
WORK_BASE_SCHEMA = """
-- A container that records are assigned to and people are granted access to.
-- version is the concurrency counter for administration, as on a terrain.
CREATE TABLE IF NOT EXISTS maestra_base (
  id          TEXT PRIMARY KEY,
  nombre      TEXT NOT NULL,
  version     INTEGER NOT NULL DEFAULT 1,
  archived_at TEXT,
  archived_by TEXT REFERENCES team_user(id),
  created_at  TEXT NOT NULL,
  created_by  TEXT NOT NULL REFERENCES team_user(id),
  updated_at  TEXT NOT NULL,
  updated_by  TEXT NOT NULL REFERENCES team_user(id)
);

CREATE TABLE IF NOT EXISTS maestra_base_acceso (
  base_id    TEXT NOT NULL REFERENCES maestra_base(id),
  user_id    TEXT NOT NULL REFERENCES team_user(id),
  granted_at TEXT NOT NULL,
  granted_by TEXT NOT NULL REFERENCES team_user(id),
  PRIMARY KEY (base_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_maestra_base_acceso_user ON maestra_base_acceso(user_id);

-- Custom columns only, each owned by one base. The fourteen core columns are
-- fixed in code and never become rows here. The API spells an id as
-- "custom:<id>"; values live in inventory_revision.custom_json under that key.
CREATE TABLE IF NOT EXISTS inventory_column (
  id            TEXT PRIMARY KEY,
  base_id       TEXT NOT NULL REFERENCES maestra_base(id),
  nombre        TEXT NOT NULL,
  tipo          TEXT NOT NULL CHECK (tipo IN ('texto', 'numero', 'opcion', 'fecha')),
  opciones_json TEXT NOT NULL DEFAULT '[]',
  orden         INTEGER NOT NULL,
  version       INTEGER NOT NULL DEFAULT 1,
  retired_at    TEXT,
  retired_by    TEXT REFERENCES team_user(id),
  created_at    TEXT NOT NULL,
  created_by    TEXT NOT NULL REFERENCES team_user(id),
  updated_at    TEXT NOT NULL,
  updated_by    TEXT NOT NULL REFERENCES team_user(id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_column_base ON inventory_column(base_id, orden);

-- Append-only account, role and grant history. base_id is set for grant
-- events. actor_id is NULL when the change came from the operator's command
-- line (scripts/cuentas.py), which has no signed-in account.
CREATE TABLE IF NOT EXISTS team_user_event (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES team_user(id),
  action       TEXT NOT NULL,
  base_id      TEXT REFERENCES maestra_base(id),
  actor_id     TEXT REFERENCES team_user(id),
  actor_name   TEXT NOT NULL,
  at           TEXT NOT NULL,
  details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_team_user_event_user ON team_user_event(user_id);
CREATE INDEX IF NOT EXISTS idx_team_user_event_base ON team_user_event(base_id);

-- Append-only history of a base (column_id NULL) and of its column
-- definitions. One event per version of each, as in inventory_event.
CREATE TABLE IF NOT EXISTS maestra_base_event (
  id           TEXT PRIMARY KEY,
  base_id      TEXT NOT NULL REFERENCES maestra_base(id),
  column_id    TEXT REFERENCES inventory_column(id),
  version      INTEGER NOT NULL,
  action       TEXT NOT NULL,
  actor_id     TEXT NOT NULL REFERENCES team_user(id),
  actor_name   TEXT NOT NULL,
  at           TEXT NOT NULL,
  details_json TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_maestra_base_event_base
  ON maestra_base_event(base_id, version) WHERE column_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_maestra_base_event_column
  ON maestra_base_event(column_id, version) WHERE column_id IS NOT NULL;
"""

# v9 columns on the v8 tables. This is their only definition: a new database
# gets them the same way an upgraded one does, so the two cannot drift. Shared
# with the Postgres upgrade.
#
# Every existing account becomes 'operador' and every existing terrain stays
# unassigned (NULL): the migration promotes nobody and invents no membership.
# inventory_revision.base_id is the base the record belonged to when that
# revision was written, so membership can be read back from history.
V9_COLUMNS = (
    ("team_user", "rol", "TEXT NOT NULL DEFAULT 'operador' CHECK (rol IN ('admin', 'operador'))"),
    ("inventory_terrain", "base_id", "TEXT REFERENCES maestra_base(id)"),
    ("inventory_revision", "base_id", "TEXT REFERENCES maestra_base(id)"),
    ("inventory_revision", "tipo_terreno", "TEXT"),
    ("inventory_revision", "custom_json", "TEXT NOT NULL DEFAULT '{}'"),
)

# After V9_COLUMNS, for the reason FOLDER_INDEXES gives below.
V9_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_inventory_terrain_base ON inventory_terrain(base_id);
"""

# v10: attachment storage (PDF and KMZ of a terrain). Storage only: nothing
# writes these tables yet. Table and column names are the ones Team B's
# attachment repository is written against; do not rename them in passing.
#
# The rows form a chain: geometria -> archivo_intento -> archivo_version ->
# archivo -> inventory_terrain. Every link is a composite foreign key that
# repeats the owner's ids, so a row cannot name a parent of another version,
# attachment or terrain. Composite keys are MATCH SIMPLE on both databases (a
# NULL column switches the whole key off), so each nullable reference that
# must not slip through that way has a CHECK beside it.
#
# Three references close cycles (an attachment points at its current version
# and active geometry; an attempt points back at its geometry). They are the
# "fk_archivo_" constraints: deferred, so they are checked at COMMIT, and on
# Postgres added after the tables exist (postgres.archivos_sql). Each must
# stay on one line, last in its table.
#
# Nothing cascades. What the database cannot see -- that an active geometry is
# usable, that its version is disponible, that terminal rows are never updated
# again -- is the job of the repository's transactions.
ATTACHMENT_SCHEMA = """
-- The decision row: one attachment in a core column of one terrain. Only this
-- row changes after creation, by compare-and-set on revision. It never touches
-- inventory_terrain.version or inventory_event.
CREATE TABLE IF NOT EXISTS archivo (
  id                  TEXT PRIMARY KEY NOT NULL,
  inventory_id        TEXT NOT NULL REFERENCES inventory_terrain(id),
  columna_id          TEXT NOT NULL CHECK (columna_id IN ('core:archivos', 'core:kmz')),
  tipo                TEXT NOT NULL CHECK (tipo IN ('pdf', 'kmz')),
  revision            INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  version_actual_id   TEXT,
  geometria_activa_id TEXT,
  retirado_en         TEXT,
  retirado_por        TEXT REFERENCES team_user(id),
  retirado_motivo     TEXT CHECK (retirado_motivo IN ('usuario', 'sin_contenido')),
  creado_en           TEXT NOT NULL,
  creado_por          TEXT NOT NULL REFERENCES team_user(id),
  actualizado_en      TEXT NOT NULL,
  actualizado_por     TEXT NOT NULL REFERENCES team_user(id),
  UNIQUE (id, inventory_id),
  CHECK ((columna_id = 'core:archivos' AND tipo = 'pdf') OR (columna_id = 'core:kmz' AND tipo = 'kmz')),
  CHECK (geometria_activa_id IS NULL OR (version_actual_id IS NOT NULL AND tipo = 'kmz')),
  CHECK ((retirado_en IS NULL) = (retirado_motivo IS NULL)),
  CHECK (retirado_por IS NULL OR retirado_en IS NOT NULL),
  CONSTRAINT fk_archivo_version_actual FOREIGN KEY (id, version_actual_id) REFERENCES archivo_version(archivo_id, id) DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_archivo_geometria_activa FOREIGN KEY (id, version_actual_id, geometria_activa_id) REFERENCES geometria(archivo_id, archivo_version_id, id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS idx_archivo_terreno ON archivo(inventory_id, columna_id);
-- One live KMZ per terrain; a replacement is a new version of that attachment.
CREATE UNIQUE INDEX IF NOT EXISTS idx_archivo_kmz_vivo
  ON archivo(inventory_id) WHERE columna_id = 'core:kmz' AND retirado_en IS NULL;

-- One upload. Immutable once estado leaves 'subiendo'.
--   terminado_*  : the row stopped being 'subiendo', whatever the reason
--                  (completed, failed, cancelled, expired).
--   finalizado_* : the bytes were finalized and judged; only 'disponible' and
--                  'fallido' have it, together with the outcome in aplicada.
-- clave_temporal and clave_final are storage keys: server-only, never in a
-- response, an event or a log.
CREATE TABLE IF NOT EXISTS archivo_version (
  id                 TEXT PRIMARY KEY NOT NULL,
  archivo_id         TEXT NOT NULL,
  inventory_id       TEXT NOT NULL,
  numero             INTEGER NOT NULL CHECK (numero > 0),
  estado             TEXT NOT NULL
    CHECK (estado IN ('subiendo', 'disponible', 'fallido', 'cancelado', 'expirado')),
  revision_base      INTEGER NOT NULL CHECK (revision_base > 0),
  nombre_original    TEXT NOT NULL,
  tamano_declarado   INTEGER NOT NULL CHECK (tamano_declarado >= 0),
  sha256_declarado   TEXT NOT NULL,
  tamano             INTEGER CHECK (tamano >= 0),
  sha256             TEXT,
  tipo_detectado     TEXT,
  clave_temporal     TEXT NOT NULL,
  clave_final        TEXT,
  subida_vence_en    TEXT NOT NULL,
  completar_antes_de TEXT NOT NULL,
  error_codigo       TEXT,
  error_mensaje      TEXT,
  aplicada           INTEGER CHECK (aplicada IN (0, 1)),
  motivo_no_aplicada TEXT CHECK (motivo_no_aplicada IN ('superada', 'retirado')),
  iniciado_en        TEXT NOT NULL,
  iniciado_por       TEXT NOT NULL REFERENCES team_user(id),
  finalizado_en      TEXT,
  finalizado_por     TEXT REFERENCES team_user(id),
  terminado_en       TEXT,
  terminado_por      TEXT REFERENCES team_user(id),
  UNIQUE (archivo_id, numero),
  UNIQUE (archivo_id, id),
  UNIQUE (id, archivo_id, inventory_id),
  FOREIGN KEY (archivo_id, inventory_id) REFERENCES archivo(id, inventory_id),
  CHECK ((aplicada IS NULL) = (estado IN ('subiendo', 'cancelado', 'expirado'))),
  CHECK (motivo_no_aplicada IS NULL OR aplicada = 0),
  CHECK (estado <> 'fallido' OR (aplicada = 0 AND motivo_no_aplicada IS NULL)),
  CHECK ((finalizado_en IS NULL) = (estado IN ('subiendo', 'cancelado', 'expirado'))),
  CHECK ((finalizado_en IS NULL) = (finalizado_por IS NULL)),
  CHECK ((terminado_en IS NULL) = (estado = 'subiendo')),
  CHECK (terminado_por IS NULL OR terminado_en IS NOT NULL),
  CHECK (estado <> 'disponible'
         OR (clave_final IS NOT NULL AND tamano IS NOT NULL AND sha256 IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_archivo_version_plazo ON archivo_version(estado, completar_antes_de);
CREATE INDEX IF NOT EXISTS idx_archivo_version_iniciador ON archivo_version(iniciado_por, estado);
CREATE INDEX IF NOT EXISTS idx_archivo_version_terreno ON archivo_version(inventory_id);

-- One parser run over one finalized KMZ version, inserted with its result:
-- there is no "running" state. A 'listo' run has exactly one geometry.
CREATE TABLE IF NOT EXISTS archivo_intento (
  id                 TEXT PRIMARY KEY NOT NULL,
  archivo_version_id TEXT NOT NULL REFERENCES archivo_version(id),
  numero             INTEGER NOT NULL CHECK (numero > 0),
  origen             TEXT NOT NULL CHECK (origen IN ('completar', 'reintento', 'seleccion')),
  seleccion_json     TEXT,
  resultado          TEXT NOT NULL
    CHECK (resultado IN ('listo', 'requiere_seleccion', 'rechazado', 'error_interno')),
  resultado_json     TEXT NOT NULL,
  analizador         TEXT NOT NULL,
  geometria_id       TEXT,
  creado_en          TEXT NOT NULL,
  creado_por         TEXT NOT NULL REFERENCES team_user(id),
  UNIQUE (archivo_version_id, numero),
  UNIQUE (id, archivo_version_id),
  UNIQUE (id, archivo_version_id, geometria_id),
  CHECK ((geometria_id IS NOT NULL) = (resultado = 'listo')),
  CONSTRAINT fk_archivo_intento_geometria FOREIGN KEY (geometria_id, id, archivo_version_id) REFERENCES geometria(id, intento_id, archivo_version_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_archivo_intento_completar
  ON archivo_intento(archivo_version_id) WHERE origen = 'completar';

-- An immutable normalized boundary, and the only result of the attempt that
-- names it: the attempt points at the geometry and the geometry at the
-- attempt, same version on both sides, so neither can claim the other's. geojson is GeoJSON, positions
-- [longitude, latitude]; punto_lon/punto_lat are never copied into the
-- terrain's X/Y. bytes_geojson and sha256_geojson describe exactly the text
-- stored in geojson, not any response that later carries it.
CREATE TABLE IF NOT EXISTS geometria (
  id                 TEXT PRIMARY KEY NOT NULL,
  archivo_id         TEXT NOT NULL,
  archivo_version_id TEXT NOT NULL,
  inventory_id       TEXT NOT NULL,
  intento_id         TEXT NOT NULL UNIQUE,
  geojson            TEXT NOT NULL,
  bbox_oeste         REAL NOT NULL,
  bbox_sur           REAL NOT NULL,
  bbox_este          REAL NOT NULL,
  bbox_norte         REAL NOT NULL,
  punto_lon          REAL NOT NULL,
  punto_lat          REAL NOT NULL,
  partes             INTEGER NOT NULL CHECK (partes >= 0),
  huecos             INTEGER NOT NULL CHECK (huecos >= 0),
  vertices           INTEGER NOT NULL CHECK (vertices >= 0),
  area_aproximada_m2 REAL,
  utilizable         INTEGER NOT NULL CHECK (utilizable IN (0, 1)),
  bytes_geojson      INTEGER NOT NULL CHECK (bytes_geojson >= 0),
  sha256_geojson     TEXT NOT NULL,
  creado_en          TEXT NOT NULL,
  UNIQUE (archivo_id, archivo_version_id, id),
  UNIQUE (id, intento_id, archivo_version_id),
  FOREIGN KEY (intento_id, archivo_version_id, id)
    REFERENCES archivo_intento(id, archivo_version_id, geometria_id),
  FOREIGN KEY (archivo_version_id, archivo_id, inventory_id)
    REFERENCES archivo_version(id, archivo_id, inventory_id)
);

-- Append-only attachment history. revision is set by the events that move
-- archivo.revision, one per revision; informational events leave it NULL and
-- may repeat. base_id is the terrain's work base when the event happened.
-- details_json never holds a storage key or a signed URL.
CREATE TABLE IF NOT EXISTS archivo_evento (
  id                 TEXT PRIMARY KEY NOT NULL,
  archivo_id         TEXT NOT NULL,
  inventory_id       TEXT NOT NULL,
  archivo_version_id TEXT,
  intento_id         TEXT,
  geometria_id       TEXT,
  accion             TEXT NOT NULL CHECK (accion IN (
    'subida_iniciada', 'version_disponible', 'version_fallida', 'subida_cancelada',
    'subida_expirada', 'procesado', 'version_actual_cambiada', 'capa_activada',
    'decision_superada', 'retirado')),
  revision           INTEGER CHECK (revision > 0),
  base_id            TEXT REFERENCES maestra_base(id),
  actor_id           TEXT NOT NULL REFERENCES team_user(id),
  actor_name         TEXT NOT NULL,
  at                 TEXT NOT NULL,
  details_json       TEXT,
  UNIQUE (archivo_id, revision),
  CHECK (intento_id IS NULL OR archivo_version_id IS NOT NULL),
  CHECK (geometria_id IS NULL OR archivo_version_id IS NOT NULL),
  FOREIGN KEY (archivo_id, inventory_id) REFERENCES archivo(id, inventory_id),
  FOREIGN KEY (archivo_version_id, archivo_id, inventory_id)
    REFERENCES archivo_version(id, archivo_id, inventory_id),
  FOREIGN KEY (intento_id, archivo_version_id) REFERENCES archivo_intento(id, archivo_version_id),
  FOREIGN KEY (archivo_id, archivo_version_id, geometria_id)
    REFERENCES geometria(archivo_id, archivo_version_id, id),
  FOREIGN KEY (geometria_id, intento_id, archivo_version_id)
    REFERENCES geometria(id, intento_id, archivo_version_id)
);
CREATE INDEX IF NOT EXISTS idx_archivo_evento_terreno ON archivo_evento(inventory_id);

-- A lease on one version while a request finalizes, parses or activates it.
-- trabajo_id is the fencing token. Coordination only: never referenced by
-- history, absent from backups (a restore must not resurrect a worker), and
-- always safe to delete once expired.
CREATE TABLE IF NOT EXISTS archivo_trabajo (
  archivo_version_id TEXT PRIMARY KEY NOT NULL REFERENCES archivo_version(id),
  trabajo_id         TEXT NOT NULL,
  actor_id           TEXT NOT NULL REFERENCES team_user(id),
  operacion          TEXT NOT NULL CHECK (operacion IN ('completar', 'procesar', 'activar')),
  inicio             TEXT NOT NULL,
  vence_en           TEXT NOT NULL
);
"""

# Kept out of SCHEMA on purpose: SCHEMA runs before the column migrations, and
# on a database from before folders these columns do not exist yet, so an index
# on them there would fail. Shared with the Postgres upgrade.
FOLDER_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_base_carpeta ON base(carpeta_id);
CREATE INDEX IF NOT EXISTS idx_mapa_carpeta ON mapa(carpeta_id);
"""


def require_rowid(cursor: sqlite3.Cursor) -> int:
    """The id of the row just inserted.

    sqlite3 types lastrowid as Optional; an INSERT that produced no id is a bug
    rather than something a caller should have to handle.
    """
    if cursor.lastrowid is None:
        raise RuntimeError("La inserción no devolvió un id.")
    return cursor.lastrowid


def db_path() -> Path:
    """Where the database lives; ARA_MAP_DB overrides the default."""
    return Path(os.environ.get("ARA_MAP_DB", DEFAULT_DB))


def now() -> str:
    """The current local time as an ISO-8601 string, to the second."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database, creating and migrating it on first use."""
    target = Path(path) if path else db_path()
    if os.environ.get("ARA_MAP_READ_ONLY") == "1":
        conn = sqlite3.connect(target.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn
    target.parent.mkdir(parents=True, exist_ok=True)

    # A schema upgrade rewrites tables. Take a copy first, so a database that
    # predates this version can always be gone back to.
    if target.exists() and _pending_upgrade(target):
        backup(target)

    conn = sqlite3.connect(target, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def _pending_upgrade(path: Path) -> bool:
    """Whether this file was written by an older schema version."""
    sonda = sqlite3.connect(path)
    try:
        return int(sonda.execute("PRAGMA user_version").fetchone()[0]) < SCHEMA_VERSION
    except sqlite3.Error:
        return False
    finally:
        sonda.close()


@contextmanager
def transaction(conn: DatabaseConnection) -> Iterator[DatabaseConnection]:
    """Group coupled statements so a failure cannot leave half of them applied.

    Connections run in autocommit, and repository functions may be called from
    inside another caller's transaction, so this uses a SAVEPOINT rather than
    BEGIN: nesting is safe.
    """
    nombre = f"sp_{next(_savepoints)}"
    conn.execute(f"SAVEPOINT {nombre}")
    try:
        yield conn
    except Exception:
        conn.execute(f"ROLLBACK TO {nombre}")
        conn.execute(f"RELEASE {nombre}")
        raise
    else:
        conn.execute(f"RELEASE {nombre}")


@contextmanager
def session(path: Path | str | None = None) -> Iterator[DatabaseConnection]:
    """Open a connection for one unit of work and close it afterwards.

    ``with connect() as conn`` does NOT do this: sqlite3's own context manager
    wraps a transaction and leaves the connection open, which leaks a handle
    per request.
    """
    from . import postgres
    if path is None and postgres.enabled():
        with postgres.session() as cloud_conn:
            yield cloud_conn
        return
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to the current schema version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    existing = _table_names(conn)

    # v1 -> v2: saved maps became frozen snapshots. The old mapa_capa cascaded
    # from base and carried no base name, so it is rebuilt, and every existing
    # map is snapshotted from the bases it currently points at.
    needs_v2 = "mapa_capa" in existing and "base_nombre" not in _columns(conn, "mapa_capa")
    legacy_capas: list[dict[str, object]] = []
    if needs_v2:
        legacy_capas = [
            dict(row)
            for row in conn.execute(
                "SELECT c.mapa_id, c.base_id, c.color, c.orden, c.visible,"
                "       COALESCE(b.nombre, 'Base eliminada') AS base_nombre"
                " FROM mapa_capa c LEFT JOIN base b ON b.id = c.base_id"
                " ORDER BY c.mapa_id, c.orden"
            )
        ]
        conn.execute("DROP TABLE mapa_capa")
        if "mapa" in existing and "actualizado_en" not in _columns(conn, "mapa"):
            conn.execute("ALTER TABLE mapa ADD COLUMN actualizado_en TEXT")

    conn.executescript(SCHEMA)
    conn.executescript(INVENTORY_SCHEMA)  # v7 -> v8, additive and idempotent
    _migrate_bases_de_trabajo(conn)
    conn.executescript(ATTACHMENT_SCHEMA)  # v9 -> v10, additive and idempotent
    # Before any snapshot below copies terrains: the copy names this column.
    _migrate_moneda(conn)

    if needs_v2:
        for capa in legacy_capas:
            conn.execute(
                "INSERT INTO mapa_capa (mapa_id, orden, base_id, base_nombre, color, visible)"
                " VALUES (:mapa_id, :orden, :base_id, :base_nombre, :color, :visible)",
                capa,
            )
        _snapshot_legacy_maps(conn)

    _migrate_base_ids(conn)
    _migrate_nombres(conn)
    _migrate_carpetas(conn)

    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _migrate_base_ids(conn: sqlite3.Connection) -> None:
    """v2 -> v3: rebuild `base` so its ids are never handed out twice.

    Existing ids are preserved, so saved layers keep pointing at the right
    source; only future inserts change behaviour.
    """
    if "base" not in _table_names(conn):
        return
    definicion = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='base'"
    ).fetchone()
    if definicion is None or "AUTOINCREMENT" in (definicion[0] or ""):
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("""
            CREATE TABLE base_v3 (
              id             INTEGER PRIMARY KEY AUTOINCREMENT,
              nombre         TEXT NOT NULL,
              archivo_origen TEXT,
              hoja           TEXT,
              importado_en   TEXT NOT NULL,
              notas          TEXT
            )
        """)
        conn.execute(
            "INSERT INTO base_v3 (id, nombre, archivo_origen, hoja, importado_en, notas)"
            " SELECT id, nombre, archivo_origen, hoja, importado_en, notas FROM base"
        )
        conn.execute("DROP TABLE base")
        conn.execute("ALTER TABLE base_v3 RENAME TO base")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_nombres(conn: sqlite3.Connection) -> None:
    """v3 -> v4: split raw source names from version text, and record whether a
    map's title follows its source.

    Additive and idempotent: columns are only added when absent, and the
    inference below runs once, when the column is created.
    """
    if "mapa" not in _table_names(conn):
        return

    nuevo_en_mapa = "nombre_sigue_base" not in _columns(conn, "mapa")
    nuevo_en_capa = "version_etiqueta" not in _columns(conn, "mapa_capa")
    if not nuevo_en_mapa and not nuevo_en_capa:
        return

    if nuevo_en_mapa:
        conn.execute(
            "ALTER TABLE mapa ADD COLUMN nombre_sigue_base INTEGER NOT NULL DEFAULT 0")
    if nuevo_en_capa:
        conn.execute("ALTER TABLE mapa_capa ADD COLUMN version_etiqueta TEXT")

    if nuevo_en_capa:
        # A legacy merged layer stored one combined string. Split it only when
        # the live source's name is unambiguously its prefix; otherwise keep the
        # whole text as the raw name and treat it as opaque provenance.
        for capa in conn.execute(
            "SELECT c.mapa_id, c.orden, c.base_nombre, b.nombre AS fuente"
            " FROM mapa_capa c LEFT JOIN base b ON b.id = c.base_id"
        ).fetchall():
            fuente = capa["fuente"]
            etiqueta = capa["base_nombre"]
            if fuente and etiqueta.startswith(f"{fuente} · "):
                conn.execute(
                    "UPDATE mapa_capa SET base_nombre = ?, version_etiqueta = ?"
                    " WHERE mapa_id = ? AND orden = ?",
                    (fuente, etiqueta[len(fuente) + 3:], capa["mapa_id"], capa["orden"]),
                )

    if nuevo_en_mapa:
        # Conservative inference: a simple map with one layer whose title still
        # equals that layer's source name was almost certainly left at the
        # default. Anything else is treated as a deliberate title.
        conn.execute("""
            UPDATE mapa SET nombre_sigue_base = 1
            WHERE tipo = 'simple'
              AND (SELECT COUNT(*) FROM mapa_capa c WHERE c.mapa_id = mapa.id) = 1
              AND nombre = (SELECT c.base_nombre FROM mapa_capa c
                            WHERE c.mapa_id = mapa.id LIMIT 1)
        """)


def _migrate_carpetas(conn: sqlite3.Connection) -> None:
    """v4 -> v5: folders. Additive and idempotent.

    The carpeta table itself comes from SCHEMA; this adds the nullable
    membership columns to tables that predate them, so every existing base and
    map starts out "Sin carpeta", and then the indexes that need those columns.
    """
    for table in ("base", "mapa"):
        if "carpeta_id" not in _columns(conn, table):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN carpeta_id INTEGER"
                " REFERENCES carpeta(id) ON DELETE SET NULL"
            )
    conn.executescript(FOLDER_INDEXES)


def _migrate_moneda(conn: sqlite3.Connection) -> None:
    """v6 -> v7: prices carry their currency. Additive and idempotent.

    Existing rows keep NULL -- unknown -- rather than being stamped with
    either currency: nothing recorded which one their amounts were in.
    """
    for table, definicion in (("terreno", "TEXT CHECK (moneda IN ('USD', 'MXN'))"),
                              ("mapa_terreno", "TEXT")):
        if "moneda" not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN moneda {definicion}")


def _migrate_bases_de_trabajo(conn: sqlite3.Connection) -> None:
    """v8 -> v9: work bases, grants, roles, custom columns. Additive and idempotent."""
    conn.executescript(WORK_BASE_SCHEMA)
    for table, column, definicion in V9_COLUMNS:
        if column not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definicion}")
    conn.executescript(V9_INDEXES)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _snapshot_legacy_maps(conn: sqlite3.Connection) -> None:
    """Freeze every pre-existing map from the bases it currently references."""
    from .repo import mapas as repo_mapas

    for (mapa_id,) in conn.execute("SELECT id FROM mapa").fetchall():
        repo_mapas.refresh_snapshot(conn, mapa_id)


def backup_dir(source: Path) -> Path:
    """Where a given database's backups live: beside it, never elsewhere.

    Deriving this from the database path rather than from a fixed constant
    keeps a test database's backups out of the real one's folder.
    """
    return source.parent / "respaldos"


def backup(path: Path | str | None = None) -> Path | None:
    """Copy the database aside before a destructive change.

    Returns the backup path, or None when there is nothing to back up yet.
    Older backups beyond BACKUPS_KEPT are pruned.
    """
    from . import postgres
    if path is None and postgres.enabled():
        postgres.backup()
        return None
    source = Path(path) if path else db_path()
    if not source.exists():
        return None

    destino = backup_dir(source)
    destino.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = destino / f"{source.stem}-{stamp}.db"

    # SQLite's own backup API, not a file copy. The database runs in WAL mode,
    # so copying the .db file alone silently leaves out everything still in the
    # write-ahead log -- a backup that looks fine and restores stale data.
    origen = sqlite3.connect(source)
    copia = sqlite3.connect(destination)
    try:
        with copia:
            origen.backup(copia)
            # Sessions and login throttling are operational state, not content:
            # a restored copy must not bring old sign-ins back to life.
            tablas = _table_names(copia)
            for operativa in ("team_session", "team_login_failure"):
                if operativa in tablas:
                    copia.execute(f"DELETE FROM {operativa}")
    finally:
        copia.close()
        origen.close()

    existing = sorted(destino.glob(f"{source.stem}-*.db"), reverse=True)
    for stale in existing[BACKUPS_KEPT:]:
        stale.unlink(missing_ok=True)

    return destination
