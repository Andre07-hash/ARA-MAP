# Team A — integrate corrected B and close R3-A2

This supplements, not replaces, TEAM_A.md in the correction packet at
`341c83036d7a861e88a1b3d28f6e3359ada057a2`. Same draft #29 and feature branch;
no new checkpoint, no 4A. C1/#27 remains frozen.

B's corrected candidate is
`b2ac9bd176043fc4b1625b13993f8f21407dc978` (#28), exact-head CI run
38268732577 green. The supervisor closes R3-B1–B5 for this component; this
does not accept the final combined application. Merge that exact candidate
normally into your preserved #29 as already authorized. If already merged,
do not merge it again; report the merge SHA and parents.

## R3-A2 · P2 · Revalidation must update write permissions, not just files

This is separate from your nonblocking **R3-A1 summary-query batching request**.
Do not begin batching in this correction.

### Reproduction

Supervisor used a disposable archive of A's current
`0e9e2c1f6a1ee3c75ffed40734c825e78e0f38db`, with only B's five corrected
production modules from `b2ac9bd` overlaid. No application code was authored.
Actual browser, mounted server, SQLite/local disk, synthetic account and data:

1. Operator opens a terrain detail and uploads a PDF.
2. Hold completion, allow start-triggered file refreshes to settle.
3. Administrator archives the terrain through the real API.
4. Release completion. Server correctly returns **409 `terreno_archivado`**.
5. B reports the write-right loss and `onCambio`; A refreshes the record.
6. The open detail still has **visible, enabled upload controls**, and
   `data-solo-lectura="0"`. The row also stays in the default active view.

Reading the retained file/name is permitted here; this is **not** a data leak
or a demonstrated authorization bypass. The server still rejects writes.
The defect is stale editable UI after explicit server evidence of archive.
The existing row/detail teardown on a true 404 now passes independently.

Probe: `probe_archive_readonly.mjs` here. Use it on a fresh disposable
`tests/e2e/tabla_servidor.py --puerto 8484` harness in the combined exact tree:

```sh
node /path/to/packet/probe_archive_readonly.mjs /absolute/path/to/TREE http://localhost:8484
```

It deliberately archives only its own synthetic terrain. It must not run
against an ordinary installation containing real accounts/data. Its output
is diagnostic: a corrected UI may remove the row/detail from an active-only
view or retain an explicitly read-only detail where that view permits it.

### Cause, A-owned code

- `web/components/tabla/Tabla.js`, `aplicarArchivos()` (around line 575 at the
  reviewed head) copies only `archivos`/`ubicacion` from the fresh DTO, leaving
  `archived_at` and other permission-relevant state stale; `filaEditable()`
  therefore still uses the old state. `errorDeArchivo()` only toasts these
  non-404 write-right errors.
- `web/components/tabla/dialogos.js`, `abrirDetalle()` captures one constant
  `soloLectura`. Its `archivos(resumen)` update always reuses that original
  value. The open detail cannot learn the new permission state from a refresh.

### Required bounded fix

Handle write-right loss as a distinct revalidation path. Refresh only the
necessary authoritative record/base/session permission state, apply archive
visibility according to the current view, and propagate live `soloLectura`
to every affected cell/detail mount. Do not guess that all 403s are logout or
404s; retain content the user may still read. Reject/dispose obsolete responses.

Preserve the important existing safeguard: a file refresh must not overwrite
dirty core/custom editors or a newer saved terrain version with a stale DTO.
Updating permission metadata is not permission to replace whole rows blindly,
replay queued writes, or increment the terrain version for a file event.

Regression evidence: archive during upload completion (original probe), base
archive and a write-right loss/role revalidation as applicable to the actual
policy. Prove controls stop offering writes, allowed reads remain available,
404 still clears private state, and unrelated dirty cells/focus are not
overwritten. Preserve an include-archived read-only path and a live writable
control. Use synthetic data and the same established interfaces; no B-owned
code change is requested. Report any genuine additional shared-file need.

Then perform the already requested corrected combined verification: SQLite,
focused Postgres browser smoke with true same-store restart, full combined
repository checks/coverage/Python floor/exact-head CI. Reuse unchanged research,
25k timing and renderer evidence. Publish an additive correction handback on
#29 naming the consumed B head, merge, code and final heads. Stop for review;
no GitHub PR/main merge, deployment or new feature round.
