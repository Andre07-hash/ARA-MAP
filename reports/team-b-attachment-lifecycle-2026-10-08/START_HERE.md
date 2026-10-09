# Team B packet 1B — local/fake attachment lifecycle handback

Date: 2026-10-08  
Repository: `Andre07-hash/ARA-MAP`  
Branch: `claude/team-b/attachment-lifecycle`  
Draft PR base: `claude/integration/round-1-baseline`  
Status: implementation and local verification complete; draft PR/CI recorded in §12 after push

This packet implements the attachment domain core. It does not authorize or
include a merge, deployment, provider, real account, real company data, HTTP
route, UI, background worker or later packet.

## 1. Exact inputs and heads

The required fetch was performed before work and again before handback. The
observed inputs did not move.

| Input | Exact commit |
|---|---|
| Packet instruction | `f3fd0f05c0ba9f28bd8b3e7321f374368027e784` |
| Fetched `origin/main` | `09452fd26d38319567dce28a89db100ea61c739a` |
| A-1 schema 9 | `24073dc43a2d9f6bafa6b42b35f1967e151ba7e9` |
| P1/schema 10 | `edf9bcd1dc51e74a627d54d5ce01d37113206055` |
| Corrected P2 | `5d0844cfd678c2f7ec55ddb4b364275482d1a801` |
| B-1 KMZ parser | `efc362818ba64618dbfc23556db8678cde525336` |
| B-3S local/fake storage | `c375a1dda404cc2bc5689fe0c0e5c6d5ad545d53` |
| B-2 + E1 drawing | `eed9a4cb404406b8b261803c38947e8297a5edec` |
| Published integration baseline | `1407e7f7ed8d3e21fe53ec2f3cc98ef2f1f4f8eb` |
| Attachment implementation | `fe299bd55dce9bf30d865a1033c417a533561a9d` |
| Final report/measurement head | recorded in the draft PR and §12 after publication |

The branch was created directly from the published baseline. Team A's
`claude/team-a/master-record-backend` was not consumed.

The authoritative documents read at the instruction commit were:

- `reports/round-1-instructions-2026-10-08/START_HERE.md`
- `reports/round-1-instructions-2026-10-08/TEAM_B.md`
- `reports/round-1-instructions-2026-10-08/ATTACHMENT_CONTRACT.md`
- `reports/round-1-instructions-2026-10-08/P2_ACCEPTANCE.md`

## 2. Changed files and scope

| File | Purpose |
|---|---|
| `server/repo/archivos.py` | All attachment SQL, row locks, leases, immutable outcomes, pointer CAS, audit and bounded reads. |
| `server/archivos.py` | Authorization-aware orchestration over real sessions, storage, parser, clock and short transactions. |
| `tests/test_archivos.py` | Shared SQLite/Postgres lifecycle, permission, race, recovery, local/fake and parser matrix. |
| `tests/fixtures/archivos/ficticio.pdf` | Minimal fictional PDF bytes. |
| `tests/fixtures/archivos/README.md` | Fixture provenance; KMZ cases reuse accepted fictional parser fixtures. |
| `tests/test_kmz.py` | Narrow baseline-promised isolation allowance for the attachment service import only. |
| `reports/team-b-attachment-lifecycle-2026-10-08/medir_archivos.py` | Reproducible exact/near-limit local/fake measurement. |
| This file | Contract, evidence, limitations and handback. |

There are no changes to schema, migrations, authentication, database adapters,
terrain/base repositories, shared fixtures, route registration, CI,
deployment, renderer or UI. Attachment writes never update
`inventory_terrain.version`, its update stamps, cell content or
`inventory_event`.

## 3. Frozen public service signatures

These are domain functions for packet 2B handlers, not HTTP handlers:

```python
iniciar(
    sesion, terreno_id, *, tipo, nombre_original, tamano_declarado,
    sha256_declarado, idempotency_key, bd=None, reloj=None,
) -> dict

escribir_temporal(
    sesion, version_id, bloques, almacen, *, bd=None, reloj=None,
) -> dict

completar(
    sesion, version_id, almacen, *, bd=None, reloj=None,
    procesador=procesar_kmz, ganchos=None,
) -> dict

cancelar(
    sesion, version_id, almacen=None, *, bd=None, reloj=None,
) -> dict

reprocesar(
    sesion, version_id, almacen, *, seleccion=None, idempotency_key,
    bd=None, reloj=None, procesador=procesar_kmz, ganchos=None,
) -> dict

activar(
    sesion, archivo_id, *, version_id, expected_revision,
    idempotency_key, geometria_id=None, bd=None, reloj=None,
) -> dict

retirar(
    sesion, archivo_id, *, expected_revision, idempotency_key,
    almacen=None, bd=None, reloj=None,
) -> dict

listar(sesion, terreno_id, *, bd=None, reloj=None) -> list[dict]

historial(
    sesion, archivo_id, *, cursor=None, limite=50, bd=None,
) -> dict

resumenes_de_archivos(
    conn, inventory_ids, sesion, *, reloj=None,
) -> dict
```

`bd`, `reloj`, `procesador` and `ganchos` are injection seams for local use and
deterministic tests. A future handler passes the validated internal `Sesion`;
it must not construct one or pass a request/body identity in its place.

## 4. Lifecycle and operation matrix

### Version states

| Current state | Operation | Result |
|---|---|---|
| none/live attachment | `iniciar` | Creates a new PDF attachment or a version of the one live KMZ; version is `subiendo`. |
| `subiendo`, before +15 min | `escribir_temporal` | Atomically replaces staging bytes, bounded by the type limit. |
| `subiendo`, lease starts before +60 min | `completar` | Copies to a fresh final nonce, verifies final bytes, parses KMZ, commits one terminal outcome. |
| `subiendo`, no live lease at/after +60 min | `completar` | Persists `expirado` with audit, then returns `subida_expirada`. |
| `subiendo` | `cancelar` | Persists `cancelado`, fences/removes a lease and best-effort deletes staging. |
| `disponible`/`fallido` | `completar` | Authorized initiator replay; no copy, parser or row rewrite. |
| `disponible` KMZ | `reprocesar` | Fenced immutable `reintento`/`seleccion` attempt and optional geometry. |
| `disponible` version | `activar` | Revision-CAS pointer decision; KMZ requires a usable `listo` geometry from that exact version. |
| live attachment | `retirar` | Revision-CAS retirement, clears active descriptors, cancels pending versions and preserves finalized bytes/history. |
| retired attachment | restore | Unsupported by contract; a later upload creates a new attachment. |

### KMZ processing decision

| Parser result | Version outcome | Automatic pointer effect |
|---|---|---|
| One `listo`, usable candidate | `disponible` with immutable attempt+geometry | Activates only if attachment revision still equals `revision_base`. |
| `listo` but outside Mexico/unusable | `disponible` | No activation; previous layout remains. |
| `requiere_seleccion` | `disponible` with candidates in attempt metadata | No activation; explicit `reprocesar(seleccion=...)`, then `activar`. |
| `rechazado` | `disponible` with parser outcome | No activation; it is not mislabeled as a byte-transport failure. |
| Internal analyzer exception | `disponible` with `error_interno` | No activation. `MemoryError` propagates as a crashed worker; its lease expires. |
| Size/hash/signature mismatch | `fallido` | No activation and no final pointer. |
| Storage outage | Remains `subiendo` | Retryable; an authorized guarded release is attempted, otherwise lease expiry permits takeover. |

PDF completion uses the same attachment-revision CAS. A stale verified PDF or
KMZ remains immutable history with `aplicada=false` and reason `superada` or
`retirado`; it cannot overwrite the newer pointer.

## 5. Identity, permission and transaction behavior

- `archivos.ver`: list, history and bounded summaries.
- `archivos.subir`: start, stage, complete, parse/selection and activation.
- `archivos.retirar`: retirement.
- Only the initiating account may stage or complete. Guessing a version ID,
  including as an administrator, returns the same `404 not_found` used for an
  absent/out-of-scope resource.
- Cancellation is allowed to the initiator or a currently authorized admin.
- Normal attachment decisions refuse archived terrain/base writes according to
  P2. Reads follow P2's action-specific archived policy.
- Every public entry requires an actual `auth.Sesion`. No session returns 401;
  role denial returns 403; missing/out-of-scope is indistinguishable 404.
- A preliminary scoped read precedes slow work. Every state-writing transaction
  enters `db.escritura()` and calls `auth.reverificar_terreno()` before its
  first attachment mutation. Attachment/version locks follow that recheck.
- Storage copy/read/write and `procesar_kmz` never run in a write transaction.
- Audit uses the fresh scope's actor and current `base_id`. Storage keys,
  credentials and `Sesion.referencia` never enter results or audit JSON.

Deterministic after-slow-work tests revoke grants, transfer/archive terrain,
archive the base, deactivate/change-role/reset-credentials on the account,
logout and expire the session. In every case the final recheck refuses the old
scope with no terminal version, attempt, decision or terminal event.

The complementary "attachment boundary wins first" guarantees are inherited
from corrected P2 and run in the full suite: SQLite's `BEGIN IMMEDIATE` and
Postgres's existing workspace advisory lock plus P2 row locks make a later
administrative mutation wait or fail cleanly. This is not presented as a
row-lock-only Postgres result.

## 6. Leases, deadlines, replay and idempotency

- Upload/staging deadline: 15 minutes from start; equality is expired.
- Completion-start deadline: 60 minutes from start; equality is expired.
- Lease: 180 seconds, fenced by `trabajo_id`; equality is expired.
- A lease acquired strictly before the completion deadline can finish after
  that deadline while the lease remains live.
- A live competing lease returns `409 procesamiento_en_curso` with retry advice.
- An expired lease may be taken over. The old holder cannot finalize or remove
  the winner's object; it may only delete its own proven-unreferenced nonce.
- Completion replay reauthorizes and is initiator-only. It returns the stored
  completion attempt and original `aplicada`/`motivo_no_aplicada`, plus current
  attachment state, without rerunning the parser.
- Start, reprocess/selection, activation and retirement use durable normalized
  idempotency records scoped by actor, operation and resource. Same key/body is
  stable; a changed body returns `idempotencia_conflictiva`; another actor's
  matching text is a different scope and cannot recover the first actor's body.
- Every active decision carries `expected_revision`. Parallel replacements or
  selections have one serial winner; stale choices return
  `revision_conflictiva` or commit only superseded history.

## 7. Cleanup and failure recovery

Staging and final cleanup is best effort and always outside the database
transaction.

- Cancellation/retirement may leave an unreferenced staging object if local
  deletion fails. The durable state is still safe and reports
  `limpieza_pendiente` where the operation observes the failure.
- A copied final object is deleted only after a fresh successful database read
  proves no version references that exact key.
- If the database outcome is ambiguous, failure to establish that proof leaves
  the object in place for future safe cleanup.
- A deterministic test injects a commit acknowledgement loss after the terminal
  transaction committed. The caller observes an exception, the database row
  remains `disponible`, and the referenced final object is retained.
- A crash after copy or parse leaves a live/expiring lease and possibly the
  holder's unreferenced nonce. Takeover is safe; there is deliberately no
  destructive or scheduled orphan sweep in 1B.
- Finalized versions, attempts, geometries, events and bytes are never deleted
  by cancellation or retirement.

A future sweep must use a fresh database view, skip every referenced
`clave_final`, protect all live leases, use an age grace period, and remove
only exact unreferenced keys. That work is not authorized here.

## 8. Bounded reads and privacy

- History defaults to 50 and rejects limits above 100. Its cursor is stable on
  `(at, id)` descending.
- Summaries return at most five recent PDFs plus the live KMZ descriptor.
- A caller sees details for their own pending upload. Another authorized caller
  sees only `{estado: "subiendo", propia: false}` for that latest version—not
  filename, size, deadline or initiator.
- Batch summaries authorize every requested terrain independently and return
  missing/out-of-scope IDs together under `no_disponibles`.
- There is no `revision_max` aggregate shortcut; each attachment summary is
  replaced from its own state.
- Private DTOs contain no storage keys, credentials or session reference.
  Geometry bodies remain in the geometry table and are not placed in catalog
  summaries.

## 9. Fictional request/result/error examples

Start input at the later handler boundary:

```json
{
  "tipo": "pdf",
  "nombre_original": "avaluo-ficticio.pdf",
  "tamano_declarado": 137,
  "sha256_declarado": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "idempotency_key": "ejemplo-ficticio-1"
}
```

Safe start result (no key or session reference):

```json
{
  "archivo_id": "11111111-1111-4111-8111-111111111111",
  "version_id": "22222222-2222-4222-8222-222222222222",
  "tipo": "pdf",
  "numero": 1,
  "estado": "subiendo",
  "revision_base": 1,
  "nombre_original": "avaluo-ficticio.pdf",
  "tamano_declarado": 137,
  "subida_vence_en": "2026-10-08T12:15:00+00:00",
  "completar_antes_de": "2026-10-08T13:00:00+00:00"
}
```

Safe terminal shape, abbreviated:

```json
{
  "version": {"id": "2222...", "estado": "disponible", "aplicada": true},
  "intento": null,
  "aplicada": true,
  "motivo_no_aplicada": null,
  "archivo": {"id": "1111...", "revision": 2, "version_actual_id": "2222..."},
  "replay": false,
  "limpieza_pendiente": false
}
```

Errors use the existing `ApiError` envelope. Representative details are:

```json
{"code": "procesamiento_en_curso", "reintentar": true, "reintentar_despues_de": "..."}
{"code": "revision_conflictiva"}
{"code": "not_found"}
{"code": "almacen_no_disponible", "reintentar": true}
```

No example contains a real account, company filename, storage key, cookie,
connection string or signed URL.

## 10. SQLite/Postgres and deterministic evidence

The same 21 behavior tests run against SQLite and a disposable UTF-8 Postgres
17 schema. They use real fictional accounts, login-derived sessions, the P2
helpers, separate service connections, real `AlmacenEnMemoria`/
`AlmacenLocal`, real KMZ fixtures and the accepted parser.

Key negative controls include:

- A late holder loses after the clock advances exactly 180 seconds; takeover
  commits one terminal row and one final object.
- Completion starts one second before its deadline, crosses the deadline
  during storage work, and succeeds inside its still-live lease.
- A stale parallel replacement is retained with `superada` and cannot change
  the winner's geometry.
- Cross-version geometry substitution and stale revision activation fail
  without a decision row.
- The hook after storage copy successfully opens another `db.escritura()`;
  therefore the slow phase holds no attachment write transaction. The final
  authorization recheck occurs after this hook.
- Completion with an injected storage-copy outage remains pending and succeeds
  on a full retry.
- Overdue list projection reports `expirado` without mutating the row/event;
  an authorized completion attempt persists expiry and audit.
- Attempt and geometry mutual deferred constraints commit together in the
  required attempt-first order on both engines.

## 11. Bounded-file measurements

Reproduce from the repository root:

```bash
PYTHONPATH=. /usr/bin/python3 \
  reports/team-b-attachment-lifecycle-2026-10-08/medir_archivos.py
```

Developer machine: Apple arm64, macOS 26.6, Python 3.9.6. Times are one local
run under `tracemalloc`; they are not hosted performance claims.

| Fixture | Actual bytes | Storage | Start+stage+complete | Python peak |
|---|---:|---|---:|---:|
| Exact-limit fictional PDF | 26,214,400 | in-memory fake | 0.045 s | 50.03 MiB |
| Exact-limit fictional PDF | 26,214,400 | local filesystem | 0.067 s | 2.01 MiB |
| Near-limit fictional KMZ | 20,968,109 | in-memory fake | 0.044 s | 62.42 MiB |
| Near-limit fictional KMZ | 20,968,109 | local filesystem | 0.063 s | 42.42 MiB |

All four ended `disponible` and applied. The KMZ contains the accepted small
fictional polygon plus a ZIP-stored fictional padding member. Completion holds
at most the contract-bounded KMZ body for the pure parser; fake storage also
holds byte copies, explaining its larger peak. Storage chunks remain capped at
1 MiB. The parser's own decompressed KML/work budgets remain independently
enforced.

## 12. Verification and publication

### Developer/local evidence

| Gate | Result |
|---|---|
| Focused lifecycle, SQLite | 21 passed |
| Focused lifecycle, disposable UTF-8 Postgres 17 | 21 passed |
| Real KMZ parser regression | 95 passed |
| `ruff check server/ tests/` | passed |
| `mypy server/` | passed, 49 source files |
| `./verificar.sh` Python | 1,029 passed, 120 Postgres-only skips |
| `./verificar.sh` macOS floor | complete suite passed on Python 3.9.6 |
| `./verificar.sh` JavaScript | 98 passed |
| Full suite with disposable Postgres enabled | 1,029 passed |

The disposable Postgres cluster used UTF-8 and an isolated generated schema;
it contained only fictional test data. Existing test-suite `ResourceWarning`
messages were visible during the full run but did not fail it; no warning was
suppressed or described as a clean warning audit.

### Browser/published evidence

No browser behavior, HTTP route or deployment exists in packet 1B, so no
browser or published-environment test is claimed.

### GitHub evidence

- Draft PR: recorded after publication.
- Exact-head Actions run/checks: recorded after publication; local green is
  not represented as CI until GitHub reports it.

## 13. Limitations and later requests

### Team A / later integration requests

1. In packet 3A, mount `resumenes_de_archivos(conn, inventory_ids, sesion)`
   using the handler's existing read connection. Do not replace its per-ID
   authorization with acceptance of caller-supplied IDs or a revision-max
   token.
2. In packet 2B, register routes with the existing capability dispatcher and
   pass the real validated `Sesion`, `Idempotency-Key`, explicit
   `expected_revision` and bounded byte chunks into these functions. Do not
   duplicate SQL or authorization in the handler.
3. Any future prerequisite repair to schema/auth/parser/storage requires a
   narrow, separately reviewed finding. None is requested by this handback.

### Reserved for packet 2B

- HTTP paths, methods, request decoding and response envelopes.
- Streaming/body limits at the HTTP adapter; do not raise the global body
  limit for unrelated routes.
- Future 60-second read grants and geometry/file transport.
- Mapping `ApiError` to the existing safe HTTP error envelope.

### Known operational limitations

- No cloud provider or hosted limit/performance assertion.
- No scheduled worker, retry queue or orphan sweep.
- Local/fake copy and cleanup are synchronous request work.
- A process crash can leave an unreferenced nonce or staging object; the
  database state and live leases remain safe, but storage reclamation is later
  work under the predicates in §7.
- Postgres attachment concurrency in this baseline is additionally serialized
  by the existing workspace advisory lock. Parity proves behavior, not future
  horizontal throughput.
- Retired attachments cannot be restored in this release.
- No geometry body or file download service is exposed yet.

## 14. Stop condition

Packet 1B stops at the separate stacked draft PR for supervisory review. Do
not merge it, deploy it, provision storage, run against real accounts/data,
purchase a provider, or begin packet 2B/3B.
