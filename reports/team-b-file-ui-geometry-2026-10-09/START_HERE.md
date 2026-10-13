# Packet 3B — file controls and bounded geometry client

Team B handback for supervisory review. Instructions:
`reports/round-3-instructions-2026-10-09/` at supervisor
`4682793f290718cfd49fd661ef16f2af4448fafb` (START_HERE, INTERFACES, TEAM_B).

**What this is:** B's widgets, client and geometry loader, verified in a
standalone harness against the **real C1-mounted application** (production
routes, binary transport, C1's local-disk store wiring and A's real
`peticionPrivada`). **What it is not:** the finished product screen. A's host
(table registration, detail panel, map page) consumes these components in 3A;
see SOLICITUDES_A.md.

## Heads

| What | Commit |
|---|---|
| Instructions | `4682793f290718cfd49fd661ef16f2af4448fafb` |
| Source: accepted 2B (#25) | `bf4c6a694ca95087368bb2d89325d7a240a7b676` |
| B work before C1 | `4810ee9` client, upload state machine, loader · `6519906` widgets · `fe8c710` harness + fixes |
| C1 (PR #27, frozen SHA from its description) | `49b782d147591236cc7f311c7e0de1948ad5258e` |
| Ordinary `--no-ff` merge of exact C1 | `8ee4311` (no conflicts) |
| Code head | `42085bc10f993c9a70846b5466fccad02289dd6e` (`ff2b2dc` mounted verification, `42085bc` loader fix) |
| **Candidate for A** | the final head of this PR, stated in its description, with exact-head CI |

Branch `claude/team-b/file-ui-geometry-client`; draft PR targets
`claude/integration/round-3-baseline`. #25, #23, #21 and frozen #24 are
unchanged. A's moving 3A branch was not consumed.

**C1 CI note.** PR #27's "Python and disposable Postgres" job on `49b782d`
failed at `docker pull postgres:16` (a Docker Hub timeout) before any test
ran. JavaScript passed. B consumed the frozen SHA as the packet directs. This
PR's CI runs the same suites on a tree that contains C1.

## Changed files (diff against C1: B-owned only)

| File | What |
|---|---|
| `web/lib/archivos.js` | Client for the 15 routes over the injected bridge: bounded reads, error envelope, uncertain replies, verified downloads, local file checks |
| `web/lib/cargadorGeometrias.js` | `crearCargadorGeometrias`: metadata + chunk verification, whole-body SHA-256, strict UTF-8/JSON, residency 1 + 1 + 1 |
| `web/components/archivos/index.js` | `crearWidgetsArchivos` → `{mount, mountDetalle, destroy}`; compact cell |
| `web/components/archivos/detalle.js` | Detail controls: upload, retry and cancel, paged files, versions, history and attempts, candidates, activation, downloads, retirement |
| `web/components/archivos/subida.js` | One logical upload as a DOM-free state machine (replay rules) |
| `web/components/archivos/resumen.js` | Summary → words (undefined ≠ zero), safe names |
| `web/styles/archivos.css` | Dedicated sheet (A links it, A-3) |
| `tests/js/archivos.test.mjs`, `tests/js/cargadorGeometrias.test.mjs` | 44 node tests |
| `tests/e2e/archivos_servidor.py`, `tests/e2e/archivos/` | Harness server and page (stand-in host; not the product) |
| `tests/e2e/archivos-recorridos.mjs`, `tests/e2e/archivos-medicion.mjs` | 19 browser journeys; near-limit measurement |
| this folder | Report, COMPONENTES.md (contract), SOLICITUDES_A.md, loader mutation check, evidence |

No lifecycle, server, auth, schema, dispatcher, shared API, store, router,
shell, table, renderer or geometry-helper change. No E5, worker, cloud
storage or new dependency (Playwright stays the existing optional e2e
dependency).

## Evidence (code head `42085bc`, exact archive)

Local Linux container, synthetic data, fictional accounts, loopback only.

| Check | Result |
|---|---|
| Full Python suite, SQLite, Python 3.13 | 1,230 run, 211 skipped (Postgres), 1 environmental failure |
| Full Python suite, SQLite, Python 3.9.25 | same |
| Full Python suite, disposable Postgres 16.15 | 1,230 run, 0 skipped, 1 environmental failure |
| JavaScript `node --test tests/js/*.test.mjs` | **180/180** (C1's 136 + B's 44) |
| `ruff check server/ tests/` | clean |
| `mypy server/` | clean, 54 files |
| Browser journeys, Chromium 141, **mounted mode**, real `peticionPrivada`, local disk | **19/19** (`evidencia/recorridos.json`) |
| Near-limit 100,000-vertex measurement | complete (`evidencia/medicion.json`) |
| Loader mutation check (6 injected breaks) | all detected; control passes (`evidencia/mutaciones-cargador.jsonl`) |

The environmental failure is the known
`test_the_system_python_has_no_openpyxl_of_its_own`: this container's system
Python has openpyxl. `./verificar.sh` was not run as a script (no zsh); its
components were run directly. The two `BrokenPipeError` traces in
`recorridos.log` are the server writing to PUTs that the cancellation and
expiry journeys abort on purpose.

### Browser journeys (real server, nothing mocked)

All 19 pass:
- **Files:** a PDF uploads and the cell updates through `onCambio`; the
  download is byte-identical, with its non-ASCII name; a non-PDF is refused
  before it is read.
- **KMZ:** a single-boundary KMZ activates, and only that verified body
  reaches the renderer. A multi-candidate KMZ needs an explicit choice and an
  explicit activation. A failed replacement keeps the old boundary. A valid
  replacement activates, and a retained version re-activates.
- **Sessions:** a second session reads the same files and boundary. Rapid
  selections end with one load in flight, at most one waiting and one ready
  body (8 of 9 cancelled). Another account's pending upload is generic only.
  A no-grant account gets indistinguishable 404s.
- **Controls:** read-only hides writes but keeps downloads; cancellation
  during a throttled PUT reaches the server; retirement is confirmed and
  irreversible, while retained bytes stay downloadable.
- **Expiry:** a session expiring during a throttled upload tears everything
  down through the bridge's 401 path, with zero later DOM mutations and no
  later attachment requests.
- **Pages:** no page errors in any of the three sessions.

Before C1 the same harness ran in its "arnes" mode (temporary registration,
stand-in bridge), 18/18 at `fe8c710`. That run is development evidence only;
the evidence above is mounted.

### Near-limit boundary (the accepted parser's 100,000 vertices)

| Measure | Value |
|---|---|
| KMZ (439,185 B) upload through the widget: total / completion | 8.1 s / 7.9 s (parser time, synchronous on the server) |
| Stored GeoJSON | 4,117,139 B, 8 chunks, 9 requests (metadata + chunks) |
| Load + verify (hash) + parse | 195 ms |
| Draw with the unchanged renderer | 80 ms; `zoomToScale` reaches the outline at parcel scale (zoom 19) |
| Loaded SHA-256 = server's | yes |
| Page JS heap: before / peak during load / with body ready / after `reset()` + GC | 8.1 / 25.2 / 21.9 / 8.2 MiB |

These numbers are the page's JS heap (CDP `Runtime.getHeapUsage`), not
process RSS, and they are not a total-browser budget. They do not approve the
research memory settings. The UTF-8 split-codepoint case is a separate node
transport test.

## Bugs found and fixed while testing

- **`hidden` attribute:** the component's `display` rules beat it, so the
  read-only zone and the "Cargar más" buttons stayed visible.
- **Read-only:** write controls now hide at once instead of after a list
  reload.
- **Text:** native `replaceChildren` printed "null".
- **Downloads:** object URLs revoked in the same task cancelled the save.
- **Refreshes:** a refresh from elsewhere wiped an open panel or a candidate
  choice. It now offers "La lista cambió: actualizar".
- **Loader:** selecting X, then Y, then X again reused X's cancelled promise,
  so the last selection never loaded. A node regression and a browser journey
  now cover it.

## Limits

- **Progress:** upload progress is indeterminate, because fetch exposes no
  upload bytes. Phases are real; there are no fake percentages.
- **Hashing:** the file is read into memory once (≤ 25 MiB) to hash it, then
  released. The PUT streams from the `File`.
- **Reloaded uploads:** a pending upload found after a reload needs the same
  file again. Only its size is checked locally; the server verifies the
  SHA-256 at completion. Bytes do not resume after the deadline.
- **File list:** the list is one page of the terrain's attachments (both
  kinds) filtered by kind, so a page can show fewer items of this kind;
  "Cargar más" continues.
- **Opened PDFs:** an "Abrir" URL lives until `destroy()` (the tab needs it).
- **Not validated:** screen readers. Keyboard paths and labels exist.
- **Locale:** in this container, Chromium needs a UTF-8 locale to keep a
  non-ASCII download name. The journeys set it.
- **Not run:** the browser-Postgres combined flow (A's), any hosted
  environment, and the full research, paint or memory matrices.
- **Harness only:** the summary and descriptor come from two test-only routes
  until A's DTO adds `archivos`/`ubicacion` (SOLICITUDES_A.md A-7). The map is
  the harness's three-terrain "current page".

Stopped for supervisory review. No 4B, PR or main merge, or deployment.
