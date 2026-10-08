# Team A — A-2/P2: roles, work-base access and authorization at the write boundary

Backend only. Roles now decide what a signed-in user may do, work-base grants
decide where, and every write re-checks both inside the transaction that
saves. **This does not make the application ready for employees:** there is no
grid, no base-scoped list or create, no transfer, no attachment handler, and
the existing interface shows an operator only refusals (see "Limits").

- Instruction commit: `afd4865892972d8ebd39a31bd5b8ec6c72a74d63`
  (`reports/team-a-a2-packet-2026-10-08/START_HERE.md`).
- `origin/main`: `09452fd26d38319567dce28a89db100ea61c739a`, unchanged; it has
  none of A-1, P1 or this.
- **Stacked on P1**, PR #15 at `edf9bcd1dc51e74a627d54d5ce01d37113206055`, which
  is stacked on A-1, PR #14 at `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9`. Branch
  `claude/team-a/roles-and-bases` starts at the P1 commit and its PR targets
  `claude/team-a/attachment-schema`. Merge order: #14, #15, then this. PRs #14
  and #15 are unchanged.
- **Schema stays 10.** No migration was needed.
- The head commit and the test evidence are in the PR.

## 1. Roles and routes

`server/auth.py`, `CAPACIDADES`:

| Role | Capabilities |
|---|---|
| `operador` | `maestra.ver`, `maestra.editar`, `maestra.archivar`, `columnas.gestionar`, `archivos.ver`, `archivos.subir`, `archivos.retirar` |
| `admin` | the same, plus `maestra.global`, `bases.gestionar`, `derivados.ver`, `derivados.gestionar`, `usuarios.gestionar` |

Every route is registered with its capability (`router.add(method, path,
handler, capacidad)`), and the dispatcher checks it after authentication and
before the handler. A private route registered without one is refused to
everyone, administrators included. The anonymous allowlist, login throttling,
cookies and the unknown-path behaviour are unchanged.

| Capability | Routes | |
|---|---|---|
| (anonymous) | 6 | `GET /api/config`, `GET /api/session`, `POST /api/login`, `POST /api/logout`, `GET /api/publico/terrenos`, `GET /api/publico/terrenos/:id` |
| `maestra.global` | 2 | `GET /api/inventario/terrenos`, `POST /api/inventario/terrenos` |
| `maestra.ver` | 3 | `GET /api/inventario/terrenos/:id`, `GET …/:id/historial`, `GET /api/maestra/bases` |
| `maestra.editar` | 1 | `PATCH /api/inventario/terrenos/:id` |
| `bases.gestionar` | 6 | `POST /api/maestra/bases`, `PATCH /api/maestra/bases/:bid`, `POST …/:bid/archivar`, `POST …/:bid/restaurar`, `GET …/:bid/acceso`, `PUT …/:bid/acceso` |
| `derivados.ver` | 9 | `GET /api/bases`, `GET /api/bases/:id`, `GET /api/bases/:id/terrenos`, `GET /api/formatos`, `GET /api/mapas`, `GET /api/mapas/:id`, `GET /api/mapas/:id/terrenos`, `GET /api/carpetas`, `POST /api/exportar` |
| `derivados.gestionar` | 21 | every other legacy route: imported bases, saved maps, folders, formats, import (including the two previews) |

48 routes: 6 anonymous, 42 private. `columnas.gestionar`, `maestra.archivar`,
`archivos.*` and `usuarios.gestionar` have no route yet; the helpers already
accept them. A test walks the real route registry through the real dispatcher,
so a route added later without a capability fails it.

Status codes: **401** no valid session (missing, expired, revoked, credential
changed, account inactive); **403** `{"code": "forbidden", "capacidad": …}` the
role lacks the capability; **404** `{"code": "not_found"}` the terrain or base
is missing *or* out of the caller's scope, byte-identical in both cases;
**409** in scope but archived, `{"code": "terreno_archivado"}` or
`{"code": "base_archivada"}`; **503** `{"code": "ocupado"}` the write could not
get its turn. All in the existing `{"error", "detalle"}` envelope.

Scope rules, all in `auth._verificar`:

- Administrator: every terrain and base.
- Operator: a terrain only if it is assigned to a base that is active and
  granted to that person. Unassigned terrains are administrators'. An archived
  base is closed to operators even when granted.
- Archive state is revealed only after scope passes. Reads (`maestra.ver`,
  `archivos.ver`) may look at archived content. `maestra.editar`,
  `archivos.subir` and `archivos.retirar` get 409 on an archived terrain. Every
  non-read capability gets 409 on an archived base, administrators included,
  except `bases.gestionar` (managing and restoring it). `maestra.archivar` is
  not refused on an archived terrain, because restoring is its job; that
  workflow's own policy comes with A-3.

## 2. Work bases and grants

Fictional examples: [examples/bases-y-acceso.json](examples/bases-y-acceso.json).

| Route | Body | Returns |
|---|---|---|
| `GET /api/maestra/bases[?archivadas=1]` | — | `{bases: [base], total}`. Administrator: all active, plus archived with the flag. Operator: active bases granted to them; the flag is ignored. Filtered and counted in SQL. |
| `POST /api/maestra/bases` | `{nombre}` | `{base, usuarios: []}` |
| `PATCH /api/maestra/bases/:bid` | `{expected_version, nombre}` | `{base, usuarios}` |
| `POST …/:bid/archivar`, `…/restaurar` | `{expected_version}` | `{base, usuarios}` |
| `GET …/:bid/acceso` | — | `{base, usuarios}` |
| `PUT …/:bid/acceso` | `{expected_version, usuarios: [id, …]}` | `{base, usuarios}` |

`base` = `{id, nombre, version, archivada, archived_at, terrenos, created_at,
updated_at}`; `terrenos` counts unarchived terrains. `usuarios` entries =
`{id, login, display_name, active, granted_at}`.

- `nombre`: whitespace collapsed, 1–100 characters. No uniqueness rule.
- Every change is a compare-and-set on `version`, adds one `maestra_base_event`
  with that version (`crear`, `renombrar`, `archivar`, `restaurar`, `acceso`),
  and takes the actor from the session. A stale `expected_version` is 409
  `{"code": "conflict", "base": <current>}` and changes nothing.
- A request that changes nothing (same name, same grant set) returns the base
  as it is: no new version, no event.
- `PUT …/acceso` is the complete set. The whole request is validated first; one
  bad id rejects all of it with 422 and `detalle.usuarios = {id: reason}`:
  `no_existe`, `no_es_operador` (administrators need no grant), `inactivo` (only
  when *adding*; an inactive account that already holds a grant may stay or be
  removed). Repeated ids are one grant. There is no wildcard. Each addition and
  removal also appends a `team_user_event` (`acceso_otorgado`,
  `acceso_revocado`) naming the user and the base, so a removed grant stays on
  record.
- Archiving changes only the base row. A test compares terrains, revisions,
  terrain events, columns, grants, attachments, saved maps and the public
  catalog before and after. An archived base rejects rename (409
  `base_archivada`), still accepts grant changes, and can be restored. Archiving
  twice or restoring an active base is 409 (`base_archivada` /
  `base_no_archivada`).
- Unknown fields are 422. For these administrator-only routes validation is
  answered before existence; no operator can reach them.

## 3. Sessions, accounts and audit

`GET /api/session` and the login response, when signed in:

```json
{"authenticated": true,
 "user": {"id": "…", "display_name": "Olga Ficticia", "rol": "operador"},
 "capacidades": ["maestra.ver", "maestra.editar", "…"],
 "alcance": {"bases": [{"id": "…", "nombre": "Base Uno"}]}}
```

An administrator has `"alcance": {"bases": "todas"}`. Scope is read from the
database on every request; nothing is cached per process. The response never
carries the token, its hash, the password hash or the credential revision.

`scripts/cuentas.py` (explicit target required, as before):

```
cuentas.py --sqlite RUTA crear USUARIO "Nombre"            # operator
cuentas.py --sqlite RUTA crear USUARIO "Nombre" --rol admin
cuentas.py --url-env VARIABLE rol USUARIO admin|operador
cuentas.py --sqlite RUTA listar                            # now shows the role
```

- A real role change increments `credential_revision`: that user's open
  sessions end and the next sign-in carries the new role. Setting the role an
  account already has changes nothing and ends no session.
- Every account action writes `team_user_event` in the same transaction, with
  `actor_id` NULL and `actor_name` `CLI scripts/cuentas.py`: `cuenta_creada`,
  `rol_cambiado` (`{antes, despues}`), `contrasena_restablecida`,
  `cuenta_desactivada`, `cuenta_reactivada`.
- The command now runs inside `db.escritura()`, so an account change waits its
  turn behind a write that already checked, instead of failing.
- On Postgres it requires the target to be at the current schema and refuses
  otherwise; it never migrates.
- No account-management HTTP route exists. `usuarios.gestionar` is declared and
  unused.

## 4. The P2 interface for Team B

All in `server/auth.py` and `server/db.py`.

```python
auth.require_base(request, base_id, capacidad, conn=None) -> Alcance
auth.require_terreno(request, terreno_id, capacidad, conn=None) -> Alcance
auth.reverificar_terreno(conn, sesion, terreno_id, capacidad, *, exclusivo=False) -> Alcance
auth.reverificar_base(conn, sesion, base_id, capacidad, *, exclusivo=False) -> Alcance
auth.reverificar(conn, sesion, capacidad) -> Alcance      # no terrain or base
db.escritura(path=None)                                    # context manager -> conn
```

`require_*` are the request-start checks. They read `request.sesion`, which
only the dispatcher sets, from the cookie. `conn` reuses a connection the
handler already has open; without it they open their own.

**`auth.Sesion`** — the revalidatable session reference. A plain class with
`__slots__` (deliberately not a dataclass or tuple: the JSON encoder unpacks
those; this one encodes as its `repr`, which shows only the user id).

| Field | Type | |
|---|---|---|
| `referencia` | `str` | Identifies the `team_session` row (the SHA-256 of the token, never the token). **Internal: never in JSON, logs, audit payloads or stored results.** |
| `user_id` | `str` | |
| `display_name` | `str` | |
| `rol` | `str` | The role when the request started. Not trusted later: re-read. |
| `credential_revision` | `int` | The credential generation the session was issued under. |
| `actor` (property) | `dict` | `{"id", "display_name"}`, the audit identity. |

**`auth.Alcance`** — what one check established.

| Field | Type | |
|---|---|---|
| `sesion` | `Sesion` | The same object that was passed in. |
| `actor` | `dict` | `{"id", "display_name"}`. Use this for audit rows. |
| `rol` | `str` | As read from the database by this check. |
| `capacidad` | `str` | |
| `terreno_id` | `str \| None` | |
| `base_id` | `str \| None` | The terrain's **current** base, read by this check. NULL for an unassigned terrain. |
| `terreno_archivado`, `base_archivada` | `bool` | |

### Usage

```python
alcance = auth.require_terreno(request, terreno_id, "archivos.subir")   # request start
sesion = alcance.sesion
...  # copy, verify, parse: outside any database transaction

with db.escritura() as conn:                                            # short
    alcance = auth.reverificar_terreno(conn, sesion, terreno_id, "archivos.subir")
    ...  # attachment and version locks, then writes; alcance.actor and
    ...  # alcance.base_id for the audit row
# committed here. Any exception, the ApiError of a failed re-check included,
# rolled everything back.
```

`tests/test_roles_y_bases.py::Matriz.adjuntar` is this pattern around a
fictional `archivo` + `archivo_evento` insert, with a real session.

### What `reverificar_*` reads again, on that connection

Session (exists, belongs to that user, not revoked, not expired, same
credential revision as the account **and** as the `Sesion`) → account (active,
role) → capability → terrain (exists, current `base_id`, archived) → that base
(exists, archived) → the caller's grant on it. It raises the same 401 / 403 /
404 / 409 as `require_*`. It raises `RuntimeError` if `conn` did not come from
`db.escritura()`; a bare `db.session()` or `db.transaction()` is refused rather
than upgraded.

### The transaction boundary

- **SQLite.** `db.escritura()` opens the connection and runs `BEGIN IMMEDIATE`
  before anything is read, so the re-check and the writes share one snapshot no
  other writer can change. `db.transaction()` (a SAVEPOINT) still nests inside
  it. `COMMIT` on exit; any exception, including a deferred foreign key that
  fails at `COMMIT`, rolls back and the connection is closed.
- **Postgres.** `db.escritura()` is the existing session transaction with its
  workspace advisory lock, unchanged. Inside it the re-check reads each row
  `FOR SHARE` in the fixed order **user → session → terrain → base → grant**.
  Take attachment and version locks after it.
- **`exclusivo=True`** locks the addressed row (the terrain, or the base for
  `reverificar_base`) `FOR UPDATE` instead. Use it when the same transaction
  will update that row, so two such writers queue instead of deadlocking on a
  share-to-exclusive upgrade. Team A's terrain PATCH and base administration use
  it. Attachment writes do not update `inventory_terrain` and should leave it
  off.
- **Writers that change scope** take the same rows in the same order: account
  changes update `team_user`; logout updates `team_session`; base rename,
  archive, restore and grant replacement re-check the administrator (user,
  session), lock the base `FOR UPDATE`, then delete and insert grant rows in
  sorted user-id order. A grant replacement reads its target accounts without
  locking them. A future terrain transfer must lock the terrain, then both
  bases in id order.
- **Both orders.** A scope change that commits first is seen by the re-check,
  which denies. One that arrives after the re-check waits for that transaction
  to end.
- **Errors and retries.** Nothing is retried automatically. A lock or statement
  timeout, a deadlock, or SQLite's busy timeout raises `db.OcupadoError`; the
  transaction is rolled back with no mutation and no audit row, and HTTP
  answers 503 `{"code": "ocupado"}`. A caller that retries must repeat the whole
  block, re-check included, and must not repeat external I/O that already
  succeeded. Waits are bounded by the existing limits: SQLite's 5 s busy
  timeout; Postgres `lock_timeout` 30 s and `statement_timeout` 60 s.
- **No long work inside.** `db.escritura()` holds SQLite's only write slot and,
  on Postgres, the workspace advisory lock.

## 5. Other changes

- `PATCH /api/inventario/terrenos/:id` runs in `db.escritura()` with
  `reverificar_terreno(…, "maestra.editar", exclusivo=True)` before anything
  else, so an out-of-scope caller gets 404 whatever the body was. The new
  revision carries `tipo_terreno` and `custom_json` forward from the previous
  one and records the terrain's current `base_id`. None of the three is
  editable or returned.
- The unscoped create re-checks `maestra.global` inside its transaction.
- `GET …/:id` and `…/historial` check scope on the connection that reads.
- The legacy workspace routes are gated by the dispatcher only; their handlers
  are unchanged.
- Shared changes, as the packet allows: `Router.add`/`Route` carry `capacidad`
  and expose `routes`; `Request` carries `sesion`; the handler accepts `PUT`;
  `db.escritura`, `db.en_escritura`, `db.bloqueo`, `db.OcupadoError`,
  `postgres.es_bloqueo`.
- Tests written before roles: `tests.support.create_user` now creates an
  administrator unless told otherwise, with the reason in its docstring; the
  Postgres inventory suite names `rol="admin"`; `EqualTeamAccess` is renamed
  `AdministratorsShareTheMasterTable`. No expected status was loosened. The
  schema-8 fixture in `tests/test_schema_v9.py` is now written as schema-8 SQL,
  because today's writers name columns schema 8 does not have.

## 6. Evidence

`tests/test_roles_y_bases.py`: one matrix through the real dispatcher with real
sessions, on SQLite and disposable Postgres. Two administrators; operators with
one grant, two grants and none; two active bases and an archived one; terrains
assigned, unassigned, archived, and in the archived base.

| Area | What is shown |
|---|---|
| Routes | Every registered route is anonymous-allowlisted or names a real capability; through the dispatcher each private route is 401 anonymously, 403 for an operator when administrator-only, never 401/403 for an administrator; an undeclared private route is refused to all and its handler never runs; unknown paths stay private |
| Bases | Create, rename, archive, restore with exact versions and events; stale version; invalid bodies and unknown ids change nothing |
| Grants | Whole-set replace; duplicates; no-op; stale; a mixed bad list changes nothing; inactive accounts; exact `team_user_event` and `maestra_base_event` rows |
| Archive | Only the base row changes; public output identical; operators shut out, administrators read-only, grants manageable, restore reopens |
| Scope | Per-caller base lists; out-of-scope, unassigned, archived-base and missing terrains give the byte-identical 404, for read, history and PATCH, valid body or not; archived terrain and archived base 409 |
| Forgery | Headers, query and body fields naming a role, actor or base grant nothing; a `Sesion` built by hand, or another user's reference relabelled, is 401 |
| Sessions | Payload matches rights; no secret in it; a revoked grant applies on the next request; role change, reset, deactivation and logout end sessions |
| Preservation | PATCH keeps `base_id`, `tipo_terreno`, `custom_json`; none appears in detail, history or list |
| Command | No target refused; default operator; `--rol`; promote, verify sign-in, demote, reset; audit rows; no password or hash in output; Postgres target at an older schema refused and not migrated |
| Boundary | The documented pattern writes with the trusted actor and current base and does not touch the terrain version; a failure after authorization, and a deferred key failing at COMMIT, leave nothing; refused outside `db.escritura()`; a write that cannot get its turn is 503 with nothing written |

### Race results

Two connections, with a barrier inside the writer after its re-check and before
its first write.

**Scope change commits before the final re-check** (authorized at request
start, then the change, then the write). SQLite and Postgres: the write is
denied and nothing is written.

| Change | Write gets |
|---|---|
| Grant revoked | 404 |
| Base archived | 404 |
| Role changed | 401 |
| Account deactivated | 401 |
| Signed out | 401 |
| Password reset | 401 |
| Terrain transferred (raw fixture update) | 404 |
| Terrain archived (raw fixture update) | 409 |
| Session expired (fixture) | 401 |

**Scope change arrives after the boundary** (the writer has re-checked and
holds the boundary; the change is started; 0.4 s later it has not completed;
the writer commits; the change then completes; the next write is denied). The
first eight rows above, on both backends: the write stands, the change follows
it, the serial order is "write, then scope change".

- SQLite: the wait is `BEGIN IMMEDIATE` / the single writer.
- Postgres, `RolesPostgres`: these go through `db.escritura()` and
  `db.session()`, so **the wait observed is the workspace advisory lock**, not a
  row lock.
- Postgres, `RowLocksPostgres`: independent connections that never take the
  advisory lock, `lock_timeout` 400 ms. For grant revoked, base archived, role
  changed, account deactivated, signed out and terrain transferred: after the
  re-check, the changing statement fails with `LockNotAvailable`, and succeeds
  once the checking transaction ends; in the other order, with the change
  uncommitted, the re-check fails with `LockNotAvailable`, and after the change
  commits it returns the expected 401/404. **This is the row-lock evidence.**
  Also there: two attachment-style checks on one terrain do not block each
  other; two `exclusivo` checks on one terrain, and two administrators on one
  base, queue.

## 7. Release notes for whoever deploys

Nothing here was deployed, and no real account was touched.

**This must not be deployed before an administrator exists.** After schemas 9
and 10 every existing account is an operator with no grant. With this code that
means: no legacy workspace, no master table, no work base. Nobody could
administer anything.

Procedure, for an authorized operator, on an explicit target:

1. Back up. Apply the reviewed schema steps to reach 10 (the release step for
   PRs #14 and #15). Confirm with `scripts/esquema.py --url-env VAR --check`.
2. Before switching traffic to this code, name the administrators:
   `scripts/cuentas.py --url-env VAR rol USUARIO admin`, once per person the
   owner names. The command refuses a target that is not at schema 10. List
   with `cuentas.py --url-env VAR listar` and check the role column.
3. Deploy. Each promoted person signs in again (their old session ended) and
   `GET /api/session` shows `"rol": "admin"` and `"alcance": {"bases": "todas"}`.
4. An administrator creates the work bases and grants operators
   (`POST /api/maestra/bases`, `PUT …/acceso`).

Recovery: the same command, run by whoever holds database access. It needs no
working administrator and no web session, so a lost or demoted administrator is
restored with `rol USUARIO admin`, a lost password with `restablecer`. Every use
is in `team_user_event`. Rollback of the code is safe at schema 10: the earlier
code ignores roles.

The procedure is exercised on disposable databases with fictional accounts by
`test_the_accounts_command_sets_roles_with_audit_and_no_secrets` (SQLite) and
`test_the_accounts_command_checks_the_schema_and_never_migrates` (Postgres).

## 8. Limits and what is left

- **No frontend change.** The current interface calls the legacy workspace
  routes, which an operator is now refused. Operators have no usable screen
  until the grid packet.
- No base-scoped terrain list or create, no terrain archive/restore route, no
  transfer, no custom-column route, no attachment handler. An administrator
  cannot assign a terrain to a base through the API yet; the tests assign with
  fixture SQL. A-3 owns these.
- The admin master list still loads and filters in Python. Unchanged, and not
  the scalable master table.
- History returns what it returned before. There is no custom-field history
  projection or redaction yet; A-3 must add it before custom values or
  transfers are enabled.
- Legacy handlers still read and then write inside a deferred SQLite
  transaction. Under a concurrent `db.escritura()` such a write can fail at
  once with "database is locked" instead of waiting. That is pre-existing
  behaviour of those handlers, it rolls back cleanly, and none of them changes
  what authorization reads.
- PR #4 (hosted adapter and preview configuration) is not included or resolved.
- Local Postgres for development was run from a throwaway cluster; nothing
  hosted was used.

## Next

Stop for supervisory review. A-3 is not started.
