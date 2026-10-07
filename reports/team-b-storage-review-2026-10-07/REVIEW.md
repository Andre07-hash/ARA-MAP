# Review of storage core and attachment-contract refinements

## Disposition

PR #13 at **`2f4ec1d120a83eb480ea42a5753f9ffe30b568ca`** stays a draft pending the two bounded corrections below. The overall architecture and scope conform to the storage-only packet: injected local root, provider-neutral byte operations, atomic staging, collision-safe final copies and a separate fake. Nothing imports it into the application yet. No rewrite or new feature is requested.

PR #12 at **`28bf0dbbf718571e35d501a7810d7e7d882ee3dd`** answers all four requested contract clarifications at the design level. Its status is described separately below so documentation readiness is not confused with storage or integration acceptance.

## S1 — P2: reject non-regular objects without blocking on open

Location: [`server/almacen.py:348`](https://github.com/Andre07-hash/ARA-MAP/blob/2f4ec1d120a83eb480ea42a5753f9ffe30b568ca/server/almacen.py#L348), with `_ABRIR_LECTURA` at line 225.

`_abrir_objeto` opens the object using blocking `O_RDONLY` and only then runs `fstat` to reject non-regular files. If a FIFO/named pipe occupies a syntactically valid key, the open waits for a writer indefinitely, so the file-type check is never reached. Both `leer` and `copiar` use this path. This contradicts the bounded-failure contract and the documented handling of foreign filesystem entries beneath the root. It needs a non-regular on-disk entry; it is not a failure of ordinary module-created files.

**Independent reproduction on macOS:** create `temporal/fifo` with `os.mkfifo`, then invoke `leer('temporal/fifo', 1024)` or `copiar('temporal/fifo', 'final/v1/n1', 1024)` in a subprocess with no FIFO writer. Both remained blocked beyond a two-second timeout; the supervisor terminated the disposable children.

Run from a checkout of the reviewed head:

```python
import os, subprocess, sys, tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as root:
    Path(root, 'temporal').mkdir()
    os.mkfifo(Path(root, 'temporal', 'fifo'))
    for call in [
        'a.leer("temporal/fifo", 1024)',
        'a.copiar("temporal/fifo", "final/v1/n1", 1024)',
    ]:
        code = ('import sys; from server.almacen import AlmacenLocal; '
                'a=AlmacenLocal(sys.argv[1]); ' + call)
        try:
            result = subprocess.run([sys.executable, '-c', code, root],
                                    timeout=2, capture_output=True, text=True)
            print(call, result.returncode, result.stderr)
        except subprocess.TimeoutExpired:
            print(call, 'BLOCKED; child terminated')
```

**Required correction:** make the descriptor-based object open safe for a non-regular entry, then validate the opened descriptor before returning it. Retain directory-relative access, no-follow behavior and regular-file checks; a pre-open path `stat` alone would reintroduce a check/open race. Nonblocking opening where supported is one approach; the developer should choose and verify the exact portable POSIX behavior. Fail promptly with the existing storage-error surface, close descriptors, leave the source unchanged and create no final object.

**Evidence:** timeout-protected regressions for both read and copy using a real FIFO, plus the existing regular-file, symlink, missing-file and concurrency cases. The test itself must not hang CI if the defect returns. No daemon, FIFO writer or production fixture is needed.

## S2 — P2: check a chunk's byte size before allocating its copy

Location: [`server/almacen.py:155–161`](https://github.com/Andre07-hash/ARA-MAP/blob/2f4ec1d120a83eb480ea42a5753f9ffe30b568ca/server/almacen.py#L155).

`_como_bytes` calls `bytes(bloque)` before checking `MAX_BLOQUE`. An oversized bytearray or memoryview is therefore copied in full before being rejected. The resulting allocation scales with the invalid input, despite the advertised 1 MiB chunk ceiling. This affects both local and fake writes.

**Independent reproduction:** allocate a 32 MiB bytearray before starting `tracemalloc`, pass its memoryview as one chunk with `limite=1024`, and measure the write. Both backends raised `ValueError`, but each first allocated approximately **32.0 MiB** of additional Python memory. The correct rejection is too late to enforce the memory bound.

```python
import tempfile, tracemalloc
from server.almacen import AlmacenLocal, AlmacenEnMemoria

chunk = bytearray(32 * 1024 * 1024)   # excluded from the measured allocation
for cls in (AlmacenLocal, AlmacenEnMemoria):
    with tempfile.TemporaryDirectory() as root:
        store = cls(root) if cls is AlmacenLocal else cls()
        tracemalloc.start()
        try:
            store.guardar_temporal('temporal/v1', [memoryview(chunk)], 1024)
        except ValueError:
            print(cls.__name__, tracemalloc.get_traced_memory()[1] / 1048576)
        finally:
            tracemalloc.stop()
            if cls is AlmacenLocal:
                store.close()
```

**Required correction:** inspect the buffer's byte size before materializing `bytes`; reject oversized chunks without a proportional copy. For memoryviews, account for `nbytes`, not only element count, including typed/multidimensional views if they remain supported. Keep accepted bytes, bytearray and memoryview behavior consistent across backends, preserve the previous complete staging object on rejection, and clean up owned partial files.

**Evidence:** regressions for oversized bytearrays and memoryviews, including a view whose element count differs from its byte size; allocate source buffers before memory measurement. Show the rejected input does not cause an input-sized extra allocation, and retain exact-limit, normal typed-buffer round-trip and existing streaming tests. Do not weaken the test by changing the 1 MiB ceiling or excluding a previously supported buffer type without justification.

## PR #12 — design responses accepted, integration contract still pending

All four responses in §9 address the earlier review:

1. **Write-boundary authorization:** a transaction-scoped recheck with explicit synchronization against transfer, revocation, archive and session/account changes. This adds an A-owned `reverificar_terreno` helper to P2; B must not implement A's auth files. The lock/transaction design still needs A's confirmation and implementation tests, including compatibility with A's existing write order.
2. **Completion replay:** a single terminal commit stores the outcome after verification/parsing; a per-version lease separates long work from the short transaction. Replays distinguish a stable original outcome from the current attachment summary. P1 now needs the lease/outcome fields. Lease recovery and the guards for stale holders must be tested during implementation; no background worker is authorized by this design response.
3. **Summary refresh:** the misleading `revision_max` token is removed. The grid replaces/compares the bounded summary, and reads no longer mutate expiry state.
4. **Version integrity:** composite references join the geometry, attempt, file version, attachment and terrain; the active geometry/version combination is protected, including the NULL-pointer escape. Both databases still need migration and direct-SQL constraint evidence.

Full-response byte accounting and reassembly of the complete B-2 geometry body are also clarified. The supervisor parsed all **11 fictional JSON examples**. No additional documentation-only correction is requested in this review. D1–D5 and other proposed product defaults remain unresolved, and the schema/API contract is not frozen merely because the document's CI is green. The next contract consolidation must reconcile these fields and transaction boundaries with Team A's exact implementation.

## Independent verification and next step

- Fresh GitHub checks: **both jobs passed on both reviewed PR heads**. PR #12's previously running Python/disposable-Postgres job is now green.
- Full `./verificar.sh` in a disposable archive of PR #13's exact head on macOS: **745 Python tests, 29 Postgres-only skips; full system Python 3.9.6 compatibility suite; JavaScript tests — all passed**. This includes the 73 new storage tests. The team's environmental openpyxl failure did not reproduce here.
- S1 was independently reproduced for read and copy with two-second subprocess deadlines. S2 was independently measured on both backends. No application files were changed by the supervisor.
- The complete 256 MiB performance benchmark was not rerun; the suite's bounded streaming test did run. No hosted store, production account, real data or local Postgres service was used. Disposable-Postgres evidence is GitHub CI.

**Team B correction packet:** append normal commits for S1 and S2 to `claude/team-b/storage-core`, updating draft PR #13 and its report. Keep all fixes/tests in B-owned files. Run meaningful regressions plus repository checks, retain Python 3.9 compatibility, report exact tested head/CI and return for review. Preserve PRs #9, #11 and #12; no merge, deployment or new application integration.

No Team A input is needed for these two corrections. Beyond the isolated core, the repository/state machine needs A-1 and a consolidated P1 migration; handlers need A-2/P2 including the transaction-scoped recheck. The refreshed open-PR listing still contains only Team A's preparation PR #10, not an A-1 implementation PR. Unpublished work may exist, but dependent coding must use a supplied exact branch/PR commit. Team A can continue A-1 unchanged.
