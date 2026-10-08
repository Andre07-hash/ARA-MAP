# Team B handoff: state after the October 8, 2026 session

This note lets a new Claude Code session continue Team B's work on `Andre07-hash/ARA-MAP`. Treat it as working notes, not a report. Read `AGENTS.md` and `CLAUDE.md` first.

## How Team B work arrives

The owner relays supervisor "packets": an instruction commit on `codex/supervisor-completion-brief`, plus file paths. Read them without switching branches:

```bash
git fetch origin codex/supervisor-completion-brief
git show <commit>:<path>
```

**Standing rules from the packets:**
- No merge, deploy, provisioning or B-3 unless a packet says so.
- Never push to `main`.
- No real company data, credentials or secrets.
- Python 3.9 is the minimum version.
- No new application dependencies and no frontend build step.
- X is latitude and Y is longitude.
- Team A owns schema, auth, routes, shared API/store/router, `web/lib/inventario.js`, the app shell and CI.

**Commit trailer:**

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WuhVbALyXv5igAiMiv9xTB
```

PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, followed by the session URL.

## Team B PRs and their status

| PR | Branch | Head | Status |
|---|---|---|---|
| #9 B-1 KMZ parser | — | `efc3628` | accepted (input) |
| #11 B-2 map boundaries | `claude/team-b/map-boundaries` | `5d8e2dc` | accepted (input) |
| #12 attachments contract | `claude/team-b/attachments-contract` | `28bf0db` | §9 responses accepted; D1–D5 open |
| #13 B-3S storage core | `claude/team-b/storage-core` | `c375a1d` | S1/S2 fixed; awaiting review |
| #16 display investigation | `claude/team-b/display-strategy` | `9da0ab1` | corrections **accepted as research** (supervisor `7a71c93`). **Keep unchanged.** |
| #18 CLAUDE.md verification notes | `claude/claude-md-verificacion` | `b28db07` | draft |
| #19 E1 boundary ring drawing | `claude/team-b/boundary-path-drawing` | `eed9a4c` (impl `496233e`) | **accepted** (supervisor `7a71c93`). **Keep unchanged.** |

### What the last two deliveries established

**Long-task measurement (F1).**
- Synchronous work run directly in `page.evaluate` is never reported by the Long Tasks API in Chromium 141.
- So measured phases must start in a page task (`await new Promise(r => setTimeout(r, 0))`), count tasks that *overlap* `[t0, t1]`, and drain with `takeRecords()`.
- Negative controls run first.

**Paint comparison (F2).**
- Masks must carry the real canvas size: 1440×768 at DPR 1 and 2880×1536 at DPR 2 for a 1200×640 map.
- Helpers are in `reports/team-b-display-strategy-2026-10-08/pintura.mjs`.

**E1 mechanism.**
- One `Path2D` built from SVG path data (`M…L…Z`), used only with Leaflet 1.9.4, its Canvas renderer, `Path2D` and integer positions. Leaflet's `_fillStroke` is used through a context proxy.
- `lineTo(first)` is not stroke-identical at ring seams.
- A `Path2D` per ring merged with `addPath` loses two-point rings beyond about 1,000 rings.
- Result: 252/252 RGBA-identical captures against B-2.

**E4 memory.**
- Worker copies are now bounded (F3).
- Bitmaps were not bounded: **849 MB** measured for six heavy outlines at DPR 2.
- That led to the current packet.

## Current task (in progress): bounded-memory E4 investigation

**Packet:** instruction `7a71c93c1c1be68dc5ac992ae6ae801cde1d9cd5`, files `reports/team-b-e1-review-2026-10-08/START_HERE.md` and `TEAM_B_MEMORY.md`. Read them in full.

**In short:**
- Prototype only.
- Branch `claude/team-b/display-memory-budget`, created from PR #16 head `9da0ab1`.
- Open a **draft PR targeting `claude/team-b/display-strategy`**.
- Work only under `reports/team-b-display-memory-budget-2026-10-08/`.
- Use 64 MiB and 128 MiB budgets, shared across maps.
- Every managed allocation is admitted before it is made.
- Explicit fallbacks, multiple maps, resize, DPR 1 and 2, failure modes, and the evidence matrix are all listed in the packet.

**Branch state:** pushed, with head `87d4bd1` and the earlier commit `779c4c4`. **No draft PR has been opened yet.**

### What is built (the "E5" prototype)

| File | Role |
|---|---|
| `prototipo/presupuesto.js` | Shared byte ledger with categories `preparado`, `copia` and `raster`. Tracks peak, relievers (called before refusing), release notifications, and `anunciarPorConfirmar` (bytes whose release awaits a worker acknowledgement). |
| `prototipo/registro.js` | Per-map registry of prepared bodies. One reservation per body; owners are the cache and layer pins; unpinned bodies are evicted LRU by a reliever. |
| `prototipo/preparar.js` | PR #16 copy with a `reservar(bytes)` hook placed before allocation, returning true, false or `"esperar"`. |
| `prototipo/planificador.js` | Capped jobs (2 hold memory at once). Each job owns its reservation and hands it to the registry when loaded. The slice yield is injectable for tests. |
| `prototipo/trabajador.js` | Module worker. Draws one combined raster per request, using Leaflet's canvas transform (scale then translate) and the same path and style sequence as `CapaContorno`. Simulates failures with `?simular=sinOffscreen|error|silencio`. |
| `prototipo/cliente.js` | Worker client. Copies are reserved before posting and released on acknowledgement; pins; an LRU reliever; failures (`constructor`, `sinOffscreen`, `error`, `sinRespuesta` watchdog) release everything. |
| `prototipo/e5.js` | `CapaContornoE5`, `CapaBitmap` and the per-map controller. Details below. |
| `prototipo/derivar.py` | Derives `prototipo/MapCanvas.js` (strategy `e5`) and `MapCanvas.diff` from PR #16's derived `prototipo/MapCanvas.js`. Run `python3 -I prototipo/derivar.py ../team-b-display-strategy-2026-10-08/prototipo/MapCanvas.js`. |
| `servidor.mjs`, `pagina.html` | Static server mounting `/b2/`, `/e1/`, `/proto/` (PR #16 folder), `/mem/` and `/casos/`; full-viewport page. Query options `?impl=e5|e3|e4|e1|b2&mib=&mapas=2&simular=&plazo=`; `window.__m5` holds a `sinteticos({n, posiciones, paso, ligeros, xy})` generator. |
| `pruebas/memoria.test.mjs` | **13/13 pass.** Covers the ledger, registry, planner (cap, cancel mid-preparation, `sin_memoria`, waiting), client (acknowledgement accounting, pins, refused post, eviction while posted and while awaiting acknowledgement, early and late cancel, reset, all four failures). |
| `memoria.mjs` | Scenario driver with an audit comparing the ledger to `byteLength`, bitmap width × height × 4 and worker counters, plus a per-frame sampler. Scenarios: `matriz`, `cambio`, `dos-mapas`, `visitas`, `rafaga`, `pequeno`, `fallos`, `reinicio`. |
| `pintura-e5.mjs` | Paint comparison of E5 against E3 (expected **RGBA-identical**), E4, E1 and B-2 at DPR 1 and 2. Also 40 real clicks compared with E3, and hit testing of unavailable outlines. **Not yet run.** |

**The controller in `e5.js`:**
- **Light views draw directly.** If the outlines visible together are light (at most 2,000 rings and 20,000 positions), every outline draws directly.
- **Otherwise one image is shared.** A single bitmap at the real canvas size holds every visible outline, in renderer order, with its current style. It is drawn 1:1 at the back.
- **Admission order:**
  1. Refuse with `demasiado_grande` when the image could never fit the whole budget.
  2. Admit worker copies, pinning each one as it is admitted.
  3. Reserve the raster. If it doesn't fit, release the old image first.
  4. If it still doesn't fit, `sin_memoria`.
  5. Wait instead whenever releases are pending acknowledgement.
- **One request in flight per map.** An obsolete reply is closed and never painted.
- **On worker failure,** outlines that are light on their own are drawn directly while the running total stays light; the rest get `sin_trabajador`. A new worker is tried on the next `render()`.
- **Wording:** transient states say "Cargando contorno…"; unavailable reasons are in `AVISOS_E5` in `derivar.py`.
- **Hit testing follows paint.**

### Bugs fixed in `87d4bd1`; the browser evidence has NOT been rerun since

1. **Churn under a tight budget, which crashed the page.** Copies were admitted before the image-size check, and copies of the same request evicted each other. Now the size is checked first and each copy is pinned as it is admitted. Probed at 4, 16, 1 and 12 MiB with a scratch script: the results were stable.
2. **No decision on moves or resizes.** Leaflet registers `this._updatePaths` as the renderer's `update` listener in `onAdd`, so overriding the method did nothing. Now `renderer.off("update", …)` runs before the wrapper is installed and `renderer.on("update", …)` after. The old `cambio` run had passed while it kept an image for the first view (canvas 2160×1200, bitmap 2880×1536). The audit now also flags an image that doesn't match its area, outlines claiming a non-current image, and a held stale image.

### Earlier scenario results, from **before** fix 2, so they need rerunning

- The `pequeno` and `fallos` results were captured in `mem-sub.txt` in the old session's scratch directory, which is not in the repository. They are lost: rerun them.
- An early smoke test of six outlines at 64 MiB and 1200×640 showed:
  - one 4.42 MB combined image;
  - ledger equal to actual holdings, with prepared bytes equal to `byteLength`, worker bytes equal to copy reservations, and the bitmap equal to its reservation.

### Next steps

1. **Rerun the scenarios in small pieces.** The owner interrupted a long rerun, so ask before long runs, run in the background, and write output to a file, not a pipe.

   ```bash
   W=$(mktemp -d)
   git archive 5d8e2dcc125a688dbba38a260d5d7eca88a6d223 | (mkdir -p $W/b2 && tar -x -C $W/b2)
   git archive eed9a4cb404406b8b261803c38947e8297a5edec | (mkdir -p $W/e1 && tar -x -C $W/e1)
   git archive efc362818ba64618dbfc23556db8678cde525336 | (mkdir -p $W/b1 && tar -x -C $W/b1)
   python3 -I reports/team-b-display-strategy-2026-10-08/generar_casos.py $W/b1 $W/casos
   (cd tests/e2e && npm install)                      # playwright-core
   export B2_DIR=$W/b2 E1_DIR=$W/e1 CASOS_DIR=$W/casos
   export CHROMIUM=/opt/pw-browsers/chromium-1194/chrome-linux/chrome   # cloud sessions
   D=reports/team-b-display-memory-budget-2026-10-08
   node --test $D/pruebas/*.test.mjs
   EVIDENCIA=$D/evidencia node $D/memoria.mjs cambio > /tmp/mem.txt 2>&1   # then: pequeno, fallos, reinicio, rafaga, dos-mapas, visitas, matriz (24 runs)
   EVIDENCIA=$D/evidencia node $D/pintura-e5.mjs > /tmp/pintura.txt 2>&1
   ```

   - The manifest SHA-256s are in `reports/team-b-display-strategy-2026-10-08/evidencia/casos-manifest.json`.
   - **Never use `pkill -f` with a pattern that matches your own command.** It killed the shell twice in this session. Kill by PID.
2. **Fix whatever fails.** The check of whether a selection has been painted (`PINTAR` in `memoria.mjs`) may need adjusting. If E5 is not RGBA-identical to E3, investigate it; do not relax the comparison.
3. **Write `tiempos-e5.mjs`.** Run timing controls first, as in PR #16's `banco.mjs` and `control-tarea-cdp.mjs`. Compare E5, E4 and E3 on time to the final visible contour and on input responsiveness (longest overlapping task during real drags and wheel), with 3 repetitions.
4. **Write `REPORT.md`.** Cover:
   - exact SHAs: instruction `7a71c93`; inputs B-2 `5d8e2dc`, E1 `eed9a4c`, B-1 `efc3628` and PR #16 `9da0ab1`; the prototype commit; the head;
   - the admission policy and peak definition (displayed image plus replacement both reserved; worker copies counted until acknowledged);
   - managed versus external memory (caller GeoJSON, JS objects, Leaflet's canvas, GPU);
   - raw-body references: queued preparation jobs hold the caller's `geometrias` Map and descriptor;
   - failure behaviour, results tables, tradeoffs (for example, a selection change waits for a re-raster while the old image is shown) and the remaining product decisions;
   - the browser gap: only Chromium 141 is installed in the container.
5. **Run the repository checks.** There is no zsh, so run `verificar.sh`'s parts separately:

   ```bash
   python3 -m unittest discover -s tests -t .   # also with Python 3.9
   node --test tests/js/*.test.mjs
   ruff check server/ tests/ <folder>
   mypy server/
   ```

   The one known failure is environmental: the openpyxl test, because the system Python ships openpyxl.
6. **Commit, push, and open the draft PR** with base `claude/team-b/display-strategy`. Return the exact heads and CI. Stop for supervisory review. Keep PRs #16 and #19 unchanged.
