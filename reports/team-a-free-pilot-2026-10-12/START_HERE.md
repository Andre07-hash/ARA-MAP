# Team A — F0-A: free private pilot, combined candidate (provisional)

12 October 2026. Branch `codex/team-a-free-pilot-v1`, from
`4670df7348265af66c640069e5ece2a274830fa3`, under
`reports/free-private-pilot-2026-10-12/` at supervisor commit
`cbd0788ec2c1d44b9ed65fabdbb7990ddd432dcf`.

**Combined local candidate, provisional: Team B's adapter
(`9380ecc34af8a6b4fccdf387c066163c1dcdda59`) and its lifecycle and recovery
slice (`770cc8358ee42a3e71336517932ce7136c607e65`), both from PR #32, are
merged; the Supabase adapter is wired into the hosted entry point.** Nothing was
provisioned or deployed; no account, secret, payment method or real data.
**No result here comes from Supabase, Render or Neon, and none is a browser
run.** #29, #28, #30, #32, C1 and the M1 checkpoint branch are unchanged.

## What each kind of evidence is

| Evidence | What ran | What it does not show |
|---|---|---|
| API journey with a local store ([`ensayo_archivos.py`](ensayo_archivos.py), [output](evidencia/ensayo-archivos-postgres.txt)) | Real `server.hosted` process started with the deploy Python (3.12.15) and the exact lock, disposable Postgres 16, HTTP calls; bytes in the accepted local store, injected by scaffolding | Anything about the provider or the adapter |
| Adapter with a simulated provider (`tests/test_hosted_archivos.py`, B's `tests/test_almacen_supabase.py`) | Hosted handler + B's `AlmacenSupabase` + the real `storage3` SDK over B's in-memory fake of the provider | Real collision, freshness, quota, 20/25 MiB through the provider |
| Adapter wired by the entry point (one rehearsal line) | `server.hosted` with provider-shaped settings pointing at a closed local port: SDK imported, client built, unreachable provider answered as retryable 503 | A reachable provider |
| Real Supabase / Render / Neon | **Not run.** Prepared: [`humo_hospedado.py`](humo_hospedado.py), checked only against the local hosted process | — |
| Employee journey in a browser | `tests/e2e/recorrido-completo.mjs` with real Chrome on this combined tree: **41/41 journeys pass (SQLite)**. It starts the **local launcher** (`server.app`) with the local disk store | The hosted entry point, Postgres or the Supabase adapter in a browser. That run needs a deployed target or a release to do it |

## Closed by B's `770cc83`, now mandatory in the rehearsal

- With no store, an authorized upload start answers `503
  almacen_no_configurado` and creates no pending row.
- With no store, an account without access still gets 404 on a start and on
  a download: the denial comes before the store.
- A factory that cannot build the store is a storage 503, not a 500.

Both `PENDIENTE DE B` lines are gone: they are `exigir` assertions and fail
the rehearsal if they regress.

## Backup and restore now use the real tools

The rehearsal no longer copies files by hand. With the dump restored into a
second database: `scripts/verificar_archivos.py --url-env … --almacen-local …
--exportar …` (B) verifies and exports the 4 referenced final files and lists
the 1 pending upload; `scripts/restaurar_archivos.py` (A, new) uploads the
export into a fresh store; `scripts/verificar_archivos.py --manifiesto …
--restauracion` accepts the restored store; then the restored service serves
the identical 25 MiB PDF, the active boundary and the file history.

**How files reach the restore bucket:** B's tool only verifies and exports.
`scripts/restaurar_archivos.py` reads the export folder and creates each final
object at its original key through the store's own contract (stage, then
create-only copy), after checking every local file against the manifest's
size and SHA-256. It never overwrites, is safe to run twice, and uses the same
three storage variables, set to the restore bucket. 5 tests
(`tests/test_restaurar_archivos.py`). Against a real bucket it is untested.

## Open items

- **B, exporter defect (being fixed):** on `--almacen-entorno`,
  `recuperacion._almacen_de` returns the store's factory instead of the store,
  so B's tool cannot read a real bucket at this commit. Not patched here.
  `--almacen-local` is unaffected and is what the rehearsal exercises. The
  checklist's backup and restore commands for the real bucket are therefore
  not runnable until B's corrected SHA is merged.
- **CI skips the SDK-backed tests.** The workflow installs only psycopg, so
  B's SDK door in `tests/test_almacen_supabase.py` and all of
  `tests/test_hosted_archivos.py` are skipped in CI. They were run locally
  with the lock installed (results below). Installing the lock in CI is a
  one-line workflow edit this session's credential may not push; credentials
  were not widened.
- **Owner's KMZ failure on localhost:** not reproduced here. This session has
  neither the file nor the error text or the commit it was seen on, and the
  synthetic KMZ journeys passing does not show it is fixed. Needed to act: the
  file (or a synthetic one with the same structure), the message shown, and
  which build was running.
- **Not run:** anything on real Supabase/Render/Neon, and the browser
  journey against the hosted entry point (it ran against the local launcher).

## What is in this slice

| Piece | Where | State |
|---|---|---|
| Hosted entry point: `python -m server.hosted`, same origin for app and API, `0.0.0.0:$PORT`, Postgres required, never SQLite | `server/hosted.py` | Implemented; 18 tests in `tests/test_hosted.py` |
| Reviewed Render configuration: Free plan, manual deploys, health check, secret placeholders, Python 3.12.15 | `render.yaml` | Not activated; checked by tests |
| Hosted dependencies: `requirements-hosted.in` (psycopg 3.3.6 and B's tested `storage3==2.32.0`, `httpx==0.28.1`) compiled to the exact lock `requirements-hosted.txt` (23 packages). **CI still installs only psycopg, so the SDK-backed tests (B's and `tests/test_hosted_archivos.py`) are skipped there and were run locally:** the one-line workflow change (`pip install -r requirements-hosted.txt`) could not be pushed because this session's GitHub credential lacks the `workflow` scope. The local app and Python 3.9 still need none of it | repository root | Startup checked with Python 3.12.15 and the lock |
| Store wiring: `configurar_almacen(almacen_supabase.fabrica_desde_entorno(environ))`; missing or malformed settings defer to a file-only 503 | `server/hosted.py` | 20 tests in `tests/test_hosted.py`, 3 in `tests/test_hosted_archivos.py` |
| Operator load of a CSV into one work base of the editable master table, with dry run and duplicate report | `scripts/cargar_maestra.py` | Implemented; 11 tests in `tests/test_piloto_carga.py` |
| Accepted batching #30 (`bc7e421`) | merge `f81bc27` | Integrated once (was not an ancestor) |
| Local rehearsal on disposable Postgres | [`ensayo_local.py`](ensayo_local.py), [output](evidencia/ensayo-local-postgres.txt) | Passes |
| [Operator checklist](OPERATOR_CHECKLIST.md) (Free-only accounts, setup, load, backup, restore drill) | this folder | Written; B's tool usage to be filled in from B's candidate |
| [Guía de inicio](GUIA_DE_INICIO.md) (Spanish onboarding) | this folder | Written |

## Findings that change the plan

1. **The portal's Excel/CSV import does not reach the editable master table.**
   It writes only the legacy `base`/`terreno` workspace. The only writer of
   `inventory_terrain` is the single-row create. The test
   `test_the_legacy_import_never_reaches_the_master_table` proves it. The
   pilot's 50–100 rows therefore go in through the operator command above,
   which creates each row through the master table's own repository function
   (same revision, history event and idempotency row as a row made in the
   app) in one transaction.
2. **A full logical dump contains sessions.** The rehearsal restores a
   `pg_dump` and finds the session rows there; the restore step that clears
   `team_session`, `team_login_failure` and `archivo_trabajo` is necessary,
   and after it the restored service refuses the old cookie.
3. **No write freeze is needed for a consistent backup** if the database is
   dumped first and the files are exported for that dump: final files are
   written before the database refers to them and are immutable. The file
   half is B's tool and is not yet exercised.

## Hosted entry point: what it guarantees and how it was tested

Through a proxy-shaped path (plain HTTP with the public `Host`, as the
platform's TLS proxy forwards it):

- Only the configured public host is served; any other `Host` is 403.
- `X-Forwarded-*` and `Forwarded` are never read: forged values change nothing.
- A write needs `Origin: https://<that host>` exactly (or no Origin).
  `http://`, another port, a look-alike suffix and `null` are refused.
- Session cookie `Secure; HttpOnly; SameSite=Strict`; HSTS on every answer;
  `no-store` and `nosniff` kept; private routes 401; read-only mode kept.
- The accepted whole-file reader, unchanged: 20 MiB and 25 MiB bodies arrive
  whole, 25 MiB + 1 is 413, malformed or repeated lengths and
  `Transfer-Encoding` are 400, a short body does not hang.
- At most 4 requests in flight; a fifth waits up to 20 s, then `503 ocupado`.
  A silent socket is dropped after 30 s. No work is kept in process memory.
- `/healthz` answers any Host without touching the database, so a probe
  neither fails the host check nor keeps a free database awake.
- Refuses to start without Postgres, without one plain public hostname, or on
  a database whose schema version is not this code's.
- The local launcher (`python3 -m server.app`) and `vercel.json` are untouched.

Not yet proven anywhere: that Render forwards the original `Host`, real
memory use on the 512 MB instance, cold-wake time, and everything about files.

## Verification of this slice

- `./verificar.sh --todo` on the head: recorded in the PR.
- Full suite on disposable Postgres 16: recorded in the PR.
- Local rehearsal (`ensayo_local.py`, real `server.hosted` process, disposable
  Postgres, fictional accounts, 100 synthetic terrains): schema → accounts →
  base and grant in the portal → dry run / load / re-run → operator pages,
  filters, edits → ungranted operator 404 → process restart keeps session and
  data → `pg_dump` → restore into a second database → operational tables
  cleared → content tables equal → old session refused, new sign-in sees the
  edited row and its history.

## API journey with a local store, in detail

[`ensayo_archivos.py`](ensayo_archivos.py) runs the employee workflow on the
real hosted process and disposable Postgres, with the accepted local store in
a folder outside the "host" standing in for the external store (rehearsal
scaffolding only; `server/hosted.py` wires no disk store).
[Output](evidencia/ensayo-archivos-postgres.txt): 30 checks pass, none pending.

- Existing loaded row → edit a field → attach a three-contour KMZ → nothing
  activates by itself → choose one → activate → the row without X/Y is now
  located by its boundary; the geometry arrives whole and matches its SHA-256.
- An invalid replacement KMZ is not applied; the previous boundary stays active.
- A 25 MiB PDF uploads and downloads byte-identical with the private headers;
  a 20.00 MiB valid KMZ uploads and is processed; 25 MiB + 1 is refused.
- A second authorized session reads the same file and boundary; an account
  without the base gets 404 exactly as for a file that does not exist.
- Access revoked, or the terrain archived, before completion: the upload does
  not become a file.
- Process restart with the same database and store: same PDF, same boundary.
- No store configured: download answers 503 while the table, the boundary
  metadata and the geometry keep working.
- Recovery with the real tools (see above): old session refused, PDF
  identical, boundary active, file history complete, the upload left pending
  can be cancelled.

The load command is an initial-setup operation: the checklist says to run it
before employees work in the base, and records that it does not lock the base
against a concurrent administrator change.

## Next, in order

1. On B's corrected exporter SHA: ordinary merge, run the rehearsal's backup
   and restore once through `--almacen-entorno` against B's simulated
   provider if B offers one, and drop the defect note from the checklist.
2. Employee journey in a browser against the deployed pilot.
3. On the owner's release: the operator runs the checklist and
   `humo_hospedado.py` on the free providers; results go in a hosted report.

## M1 work (superseded Vercel/AWS packet)

Preserved, not continued: branch `codex/team-a-hosted-integration-v1` at
`f2dc7677dbcf631c0d1e22ca377a0d6765c1460b`. Reused here: the onboarding
guide and the runbook's structure. Not carried over: the Vercel response
guard and the OIDC handoff cases (they belong to that route only).
