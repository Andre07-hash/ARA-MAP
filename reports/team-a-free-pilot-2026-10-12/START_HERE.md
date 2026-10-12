# Team A — F0-A: free private pilot, first hosting slice

12 October 2026. Branch `codex/team-a-free-pilot-v1`, from
`4670df7348265af66c640069e5ece2a274830fa3`, under
`reports/free-private-pilot-2026-10-12/` at supervisor commit
`cbd0788ec2c1d44b9ed65fabdbb7990ddd432dcf`.

**This is the first usable slice, not the combined candidate.** Team B's
Supabase adapter has not been relayed, so no byte store is wired: on the
hosted entry point, file content routes answer `503 almacen_no_configurado`
and everything else works. **Nothing was provisioned or deployed; no account,
secret, payment method or real data was involved. Local results are not
hosted acceptance.** #29, #28, #30, C1 and the M1 checkpoint branch are
unchanged.

## What is in this slice

| Piece | Where | State |
|---|---|---|
| Hosted entry point: `python -m server.hosted`, same origin for app and API, `0.0.0.0:$PORT`, Postgres required, never SQLite | `server/hosted.py` | Implemented; 18 tests in `tests/test_hosted.py` |
| Reviewed Render configuration: Free plan, manual deploys, health check, secret placeholders, Python 3.12.15 | `render.yaml`, `requirements-hosted.txt` | Not activated; checked by tests |
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

## Next, in order

1. On the owner's relay of B's exact adapter SHA: focused review
   (authorization before store resolution; no provider I/O under a database
   write lock), ordinary local merge, wire
   `almacen_supabase.fabrica_desde_entorno(os.environ)` in `server/hosted.py`,
   add B's pinned SDK to `requirements-hosted.txt`.
2. Combined journey with files on SQLite and disposable Postgres: full-size
   upload/download, revoked and archived scope, unavailable storage, restart.
3. Extend the rehearsal and the checklist with B's verifier/exporter.

## M1 work (superseded Vercel/AWS packet)

Preserved, not continued: branch `codex/team-a-hosted-integration-v1` at
`f2dc7677dbcf631c0d1e22ca377a0d6765c1460b`. Reused here: the onboarding
guide and the runbook's structure. Not carried over: the Vercel response
guard and the OIDC handoff cases (they belong to that route only).
