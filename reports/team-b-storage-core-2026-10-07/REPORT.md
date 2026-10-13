# Team B — B-3S: standalone local/fake storage core

Team B · October 7, 2026

| Item | Value |
|---|---|
| Instruction commit | `8aaf21f070fea929440fc3ed8300b2228f6471ee` on `codex/supervisor-completion-brief`: `reports/team-b-attachments-review-2026-10-07/START_HERE.md`, `REVIEW.md`, `TEAM_B_STORAGE_PACKET.md`, read with `git show`. The checkout was not switched. |
| Application baseline | `origin/main` = `09452fd26d38319567dce28a89db100ea61c739a`, refreshed for this work and unchanged since the packet was issued. |
| Branch / PR | `claude/team-b/storage-core` · separate draft PR |
| Proposal read | PR #12 at `ba3ad38` §2.4 (finalization) and §5.1 (interface). The four review refinements go to PR #12's own branch, not here. |
| Files | `server/almacen.py` (new), `tests/test_almacen.py` (new), this report with `medir.py` and `evidencia/` |
| Not touched | Schema, auth, repository, routes, app shell, frontend, CI, deployment, `datos/`, PRs #9, #11 and #12. No dependency, credential, service or cloud provider. |

## 1. Scope

This PR adds a byte-storage core with two backends behind one contract:
- **`AlmacenLocal`** stores objects as files under an explicitly injected root directory.
- **`AlmacenEnMemoria`** is an in-memory fake with deterministic fault injection, for testing higher layers.

Nothing imports this module yet. Importing it or constructing either backend does not choose a path, create a directory, read settings or environment variables, start a server, or issue a credential.

It deliberately does **not** contain any of the following:
- `emitir_subida` / `emitir_lectura`, URLs, signing, sessions, roles or `require_terreno`.
- PDF or KMZ interpretation, hashing policy, or active-pointer decisions.
- Product size limits or upload lifetimes. Every limit is a caller argument.
- A garbage collector, scheduled job, cleanup command or default root.
- Database tables or a stand-in for Team A's schema.

## 2. Frozen interface

```python
# server/almacen.py — Python 3.9+, standard library only

TEMPORAL = "temporal"
FINAL = "final"
MAX_BLOQUE = 1_048_576          # largest chunk accepted by guardar_temporal / returned by leer
BLOQUE_LECTURA = 65_536         # default leer chunk

Bloque = Union[bytes, bytearray, memoryview]

class Almacen(Protocol):
    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int: ...
    def copiar(self, origen: str, destino: str, limite: int) -> int: ...
    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura: ...
    def tamano_de(self, clave: str) -> int | None: ...
    def borrar(self, clave: str) -> bool: ...
    def listar(self, prefijo: str) -> Iterator[Metadato]: ...

class Lectura:                  # iterator of bytes, also a context manager
    tamano: int                 # object size, known before the first byte
    def __next__(self) -> bytes: ...
    def close(self) -> None: ...

@dataclass(frozen=True)
class Metadato:
    clave: str
    tamano: int
    modificado: float           # seconds since the epoch

class AlmacenLocal:             # implements Almacen
    def __init__(self, raiz: str | os.PathLike[str]) -> None: ...   # root must already exist
    def close(self) -> None: ...                                       # also a context manager

class AlmacenEnMemoria:         # implements Almacen; fault surface exists only here
    def inyectar_falla(self, operacion: str, tras_bloques: int = 0) -> None: ...
    def perder(self, clave: str) -> None: ...

def partes_de_clave(clave: object, espacio: str | None = None) -> tuple[str, ...]: ...
```

### 2.1 Keys

| Namespace | Form | Operations |
|---|---|---|
| Staging | `temporal/<id>` | `guardar_temporal` writes it, `copiar` reads it as the source, and `leer`, `tamano_de`, `borrar` accept it |
| Final | `final/<id>/<nonce>` | `copiar` creates it, and `leer`, `tamano_de`, `borrar` accept it. Never overwritten. |

- Each segment matches `[0-9a-z][0-9a-z_-]{0,99}`: lowercase ASCII only. That keeps a key equal to one object on macOS's default case-insensitive filesystem, matching the fake.
- Keys are opaque identifiers that the server generates (for example UUIDs). Original file names never become keys.
- `.`, `..`, empty segments, slashes at either end, backslashes, whitespace, non-ASCII characters, uppercase letters, extra or missing segments, the wrong namespace and non-`str` values all raise `ClaveInvalidaError`.
- `listar` accepts only the prefixes `"temporal/"`, `"final/"` and `"final/<id>/"`.

### 2.2 Operations and results

| Operation | Success | Failure, previous state preserved |
|---|---|---|
| `guardar_temporal(clave, bloques, limite)` | Returns bytes written. The new complete object replaces any previous one atomically, and an empty object is valid. | `LimiteExcedidoError` once the running total exceeds `limite`, without consuming further chunks. An exception raised by the caller's iterator propagates unchanged. A chunk that is not `bytes`/`bytearray`/`memoryview` → `TypeError`; a chunk whose **byte size** (`nbytes` for a memoryview) exceeds `MAX_BLOQUE` → `ValueError`, checked before any copy (§7); passing a single `bytes`/`str` instead of an iterable → `TypeError`. I/O failure → `FalloAlmacenError`. **In every failure case the previous complete object, or its absence, is unchanged.** |
| `copiar(origen, destino, limite)` | Returns bytes copied. `destino` now holds an independent snapshot of `origen`. | `ObjetoAusenteError` (no source), `LimiteExcedidoError` (source > `limite`, checked before writing), `ColisionError` (`destino` exists; nothing written and the existing object unchanged), `FalloAlmacenError`. Nothing appears at `destino` unless the copy completed. |
| `leer(clave, limite, bloque)` | A `Lectura` whose chunks are ≤ `bloque` (1…`MAX_BLOQUE`) | `ObjetoAusenteError`. `LimiteExcedidoError` **at the call**, before any byte, if the object is larger than `limite`; there is never a silently truncated read. `FalloAlmacenError` from `next()` on an I/O fault, or if the local file changed in place during the read. |
| `tamano_de(clave)` | `int`, or **`None` when absent** | `FalloAlmacenError` if something other than a regular file sits at the key |
| `borrar(clave)` | **`True` if this call removed the object, `False` if it was already absent** (idempotent) | `FalloAlmacenError` (for example a directory planted at the key). Exact keys only; prefixes are `ClaveInvalidaError`. |
| `listar(prefijo)` | A lazy iterator of `Metadato` for regular objects. Order is unspecified. | Prefix validation is eager (`ClaveInvalidaError` at the call). Listing never deletes or expires anything. |

`limite` must be a positive `int` (not `bool`), otherwise `ValueError`. `ValueError` and `TypeError` mean caller programming errors, not storage states.

### 2.3 Error types

All storage errors derive from `AlmacenError`, which has a stable `codigo` and a Spanish message containing no key, path or credential:

| Class | `codigo` | Meaning for a future service layer |
|---|---|---|
| `ClaveInvalidaError` | `clave_invalida` | Malformed key or prefix, or wrong namespace |
| `ObjetoAusenteError` | `objeto_ausente` | Object absent |
| `ColisionError` | `colision` | Final key already exists |
| `LimiteExcedidoError` (`.limite`) | `limite_excedido` | Over the caller's limit |
| `FalloAlmacenError` | `fallo_almacen` | I/O failure, or contents not written by this module (symlink, directory, in-place change) |

The underlying `OSError` is kept as `__cause__` for logs, not in the message.

### 2.4 Fake behaviour and fault surface

`AlmacenEnMemoria` has the same keys, limits, chunk bounds, results and errors. It holds fictional bytes in memory, and a lock makes each write, copy and delete atomic. `listar` iterates over a snapshot of matching keys, which is O(number of keys) in memory, unlike the local backend.

Fault injection is one-shot and first in, first out, per operation:

| Call | Effect |
|---|---|
| `inyectar_falla("guardar_temporal", tras_bloques=n)` | The next write fails with `FalloAlmacenError` after consuming `n` chunks, or at the end if there are fewer; the previous object is kept |
| `inyectar_falla("copiar")` | The next copy fails before writing anything (after the absent/limit/collision checks) |
| `inyectar_falla("leer", tras_bloques=n)` | The next `Lectura` yields `n` chunks, then fails and closes |
| `perder(clave)` | The object vanishes without `borrar`, as a provider might lose it |

`AlmacenLocal` has no such methods, and there is no flag or setting that enables a bypass in production code.

## 3. How the local backend meets the invariants

**Trust model.** The root directory and everything above it belong to the application's operator. Keys may come from a faulty higher layer, and entries **below** the root may have been planted by another local process. Therefore:

- The root is opened **once** with `O_DIRECTORY`. Every operation walks from that descriptor one validated component at a time, using `openat`/`mkdirat`/`fstatat`/`unlinkat`/`linkat`/`renameat` with **`O_NOFOLLOW`**.
- A symlink anywhere below the root (namespace directory, `final/<id>` directory or object) is refused with `FalloAlmacenError` instead of followed.
- No path string is ever joined and re-resolved, so there is no check-then-open race to win.
- The root itself may sit behind a symlink (for example `/tmp` → `/private/tmp` on macOS) because it is operator configuration.
- POSIX `*at` support is required, which Linux and macOS have. The constructor refuses with `FalloAlmacenError` where it is missing.

**Atomic staging.** Bytes stream into a hidden `.parcial-<random>` file created with `O_EXCL` in the same directory. That name never matches the key grammar, so it is never read or listed. The file is `fsync`ed and then `renameat`-ed over the key, which is atomic. Every failure path unlinks the partial file, so the old complete object, or its absence, survives. A rename installs a **new inode**, so a reader or copy that already opened the previous object keeps reading one complete snapshot.

**Final immutability.**
1. `copiar` opens the source once, reading one snapshot inode, and checks its size against the limit.
2. It streams into a hidden partial file in `final/<id>/` and `fsync`s it.
3. It publishes with **`linkat`**, which fails with `EEXIST` if the key exists. The OS guarantees exactly one winner, and the loser gets `ColisionError` with the winner's bytes untouched.
4. The final object is a separate inode, so later staging writes never change it.

A pre-check (`fstatat`) only avoids copying bytes for an obvious collision; the link is the real check.

**Verify after copy.** `leer` on the final key streams its own bytes. A caller computes size and SHA-256 from them, and nothing reuses a staging hash.

**Bounded work.** Writes take at most 1 MiB per chunk, and reads and copies move 64 KiB at a time (reads configurable up to 1 MiB). No operation buffers a whole object. Partial files from a **crashed process** remain as hidden files. They are never visible as objects, and nothing here removes them; a future sweep owns that.

## 4. Evidence

Environment: this cloud container, Linux 6.18 x86_64, 4 CPUs. CPython 3.13.16 is the system interpreter, and 3.9.25 (uv-managed) stands in for macOS's `/usr/bin/python3`. All runs used temporary roots and synthetic bytes.

| Check | Result |
|---|---|
| `python3 -m unittest tests.test_almacen` (3.13) | **73 tests OK** |
| Same on Python 3.9.25 | **73 tests OK** |
| Full suite, `python3 -m unittest discover -s tests -t .` (3.13 and 3.9) | **745 run, 29 Postgres-only skips, 1 failure**: `test_packaging…test_the_system_python_has_no_openpyxl_of_its_own`. This container's `/usr/bin/python3` has its own openpyxl, which that test requires to be absent. The failure is environmental, was disclosed in earlier Team B reports, and concerns no file in this PR. 745 = 672 existing + 73 new. |
| `node --test tests/js/*.test.mjs` | 98 pass, 0 fail (unchanged) |
| `ruff check server/ tests/` | Clean |
| `mypy server/` (strict config) | Clean, 44 files |
| `./verificar.sh` | **Not run as a script**: the container has no `zsh`. Its components were run individually as listed above. Coverage is not installed here. |
| GitHub CI | Reported in the PR once it runs |

**Test coverage of the packet's list.** Each `Contrato` test runs against both backends: 26 contract tests × 2 backends, plus 15 local-only and 6 fake-only tests.

| Packet item | Tests |
|---|---|
| Empty content; exact limit and one byte over; arbitrary binary data | `test_empty_object`, `test_exact_limit_and_one_byte_over`, `test_arbitrary_binary_bytes_round_trip` (chunk sizes 1, 7, 4096, 1 MiB) |
| Staging replacement; failed replacement keeps prior content | `test_replacement_exposes_the_new_complete_object`, `test_failed_replacement_keeps_the_previous_object` (iterator error, limit, bad chunk type, oversized chunk) |
| Copy and read faults | Local: `test_copy_fault_leaves_no_destination`, `test_read_fault_closes_the_reader`, `test_write_fault_keeps_previous_object` (patched `os.read`/`os.fsync`). Fake: `AlmacenEnMemoriaFallas` (all four injections) |
| Final immutable after a staging overwrite | `test_final_bytes_survive_later_staging_writes`, `test_existing_final_key_is_never_overwritten` |
| Simultaneous copies to one destination | `test_concurrent_copies_to_one_destination_have_one_winner`: 8 threads behind a barrier; exactly 1 winner and 7 `ColisionError`, with the winner's bytes intact. `test_collision_found_only_at_link_time_cleans_up` forces the race into the link step. |
| Replacement racing copies | `test_staging_replacement_racing_copies_gives_whole_snapshots`: 25 copies while another thread rewrites staging; every final object is one whole 256 KiB version |
| Two nonces both succeed | `test_two_nonces_may_both_succeed` |
| Early reader close | `test_early_close_releases_the_reader` (explicit `close`, `with`, exhaustion) |
| Path and symlink escapes | `test_invalid_keys_are_rejected_by_every_operation` (24 malformed keys × 6 operations), `test_symlinked_namespace_directory_is_refused`, `test_symlinked_object_is_refused`, `test_symlinked_final_directory_is_refused`, `test_directory_planted_at_a_key`. In each case the file outside the root is unchanged and unread. |
| Safe exact-key deletion | `test_delete_is_exact_and_idempotent` |
| Listing | `test_listing`, `test_listing_prefixes_are_explicit`, `test_foreign_entries_are_not_listed` |
| Streaming with bounded memory | `test_large_objects_stream_with_bounded_memory`: a 48 MiB write, copy and read with peak Python allocations under 8 MiB |
| No partial files left | `test_failures_leave_no_partial_files`, plus checks inside the fault tests |
| Constructor has no side effects | `test_constructing_creates_nothing_and_needs_an_existing_root` |

**Streaming measurement** (`medir.py 256`; output in `evidencia/medicion-python3.{13,9}.txt`). Peak Python allocations stay at about 0.13 MiB and maximum RSS grows by under 1 MiB for a 256 MiB object:

| Python | Operation | Time | Peak Python allocations |
|---|---|---:|---:|
| 3.13.16 | `guardar_temporal` 256 MiB | 1.36 s | 0.00 MiB |
| 3.13.16 | `copiar` | 1.35 s | 0.13 MiB |
| 3.13.16 | `leer` + SHA-256 | 0.25 s | 0.13 MiB |
| 3.9.25 | `guardar_temporal` | 0.28 s | 0.01 MiB |
| 3.9.25 | `copiar` | 0.33 s | 0.13 MiB |
| 3.9.25 | `leer` + SHA-256 | 0.25 s | 0.13 MiB |

Write and copy times are dominated by `fsync` and this container's disk, and they vary between runs (the 3.13 and 3.9 runs were sequential, not comparable benchmarks). These are local measurements of the streaming property only. **They make no claim about cloud storage capacity or throughput.**

## 5. Limitations

- **macOS was not run here.** The `*at` calls used are in Python's `os.supports_dir_fd` on macOS. The supervisor's macOS `./verificar.sh` run is the evidence for that platform.
- **Windows is unsupported** by `AlmacenLocal` (no `dir_fd`), and the constructor refuses explicitly. The app does not run on Windows.
- **The trust boundary is the root.** A process that can replace the root directory itself, or write inside it with the app's own privileges at the same time, is outside this module's threat model. Containment covers symlinks and directories planted below the root.
- **No GC.** Crash leftovers (hidden partial files) and empty `final/<id>/` directories remain. Directories are deliberately never removed, because removing one could race a concurrent copy into it. Cleanup belongs to the future service layer, which can prove a key is unreferenced.
- **`fsync` durability** depends on the filesystem; directory `fsync` is best effort.
- The fake's `listar` snapshots matching keys, so its memory use is proportional to the number of keys.

## 6. Handoff to the later repository packet

The later repository packet can call this interface as PR #12 §2.4 describes:
1. `guardar_temporal` serves the local upload route.
2. `copiar(temporal, final/<v>/<new nonce>, limit)` finalizes.
3. `leer(final…)` streams the final object to verify size and SHA-256.
4. A compare-and-set in the database selects which final key to reference.
5. `borrar` removes only keys that layer proves unreferenced, and `listar` feeds a future sweep.

Cloud adapters, upload and read grants, and every database or HTTP concern stay in later packets.

**Stopping for supervisory review.** Nothing merged, deployed or provisioned.

## 7. Corrections after supervisory review (S1, S2)

The review is `reports/team-b-storage-review-2026-10-07/REVIEW.md` at instruction commit `8b1484548865ee387572e3480ad3d424b9f69dc1`, reviewing head `2f4ec1d`. The baseline is still `origin/main` `09452fd26d38319567dce28a89db100ea61c739a`, unchanged. §1–§6 above describe the reviewed head. Where this section differs, it wins.

### S1 — a FIFO at a key blocked `leer` and `copiar`

**Reproduced first** at `2f4ec1d` with the review's script: both `leer("temporal/fifo", 1024)` and `copiar("temporal/fifo", …)` stayed blocked until the 2 s child deadline.

**Cause.** `_abrir_objeto` opened the entry with a blocking `O_RDONLY` and only then ran `fstat`. For a FIFO with no writer, `open` never returns.

**Fix** (`server/almacen.py`):
- Object opens (`_ABRIR_LECTURA`) and directory opens (`_ABRIR_DIRECTORIO`) now also pass **`O_NONBLOCK`**. They are still relative to the directory descriptor and still use `O_NOFOLLOW`, so there is no pre-open path `stat` and no check-then-open race.
- POSIX `open(2)` with `O_RDONLY|O_NONBLOCK` returns at once for a FIFO, and the existing `fstat` check then rejects any non-regular entry (FIFO, device, socket, directory) with `FalloAlmacenError` and closes the descriptor.
- For a regular file, `os.set_blocking(fd, True)` clears the flag before the descriptor is returned, so reads behave exactly as before.
- `O_NONBLOCK` has no effect when opening a regular file or directory on Linux or macOS.
- Nothing is created or changed: the source stays, no final object appears, and no partial file is left.

**After the fix** the same script returns `FalloAlmacenError` from both calls at once.

### S2 — an oversized chunk was copied before it was rejected

**Reproduced first** at `2f4ec1d` with the review's script: a 32 MiB `bytearray` passed as a memoryview made **both backends allocate 32.0 MiB** before raising `ValueError`.

**Cause.** `_como_bytes` called `bytes(bloque)` before comparing the size with `MAX_BLOQUE`.

**Fix.** The byte size is read from the buffer first: `nbytes` for a memoryview, whose `len()` counts elements of the first dimension, not bytes, and `len()` for `bytes`/`bytearray`. An oversized chunk is rejected without any copy. Accepted chunks behave exactly as before:
- `bytes` is passed through without a copy;
- `bytearray` is copied (at most 1 MiB);
- a memoryview is converted with `tobytes()`, which gives C-order bytes for typed, multidimensional and non-contiguous views.

Both backends use this same function. The 1 MiB ceiling is unchanged, and no buffer type was dropped.

**After the fix** the same script measures **0.0 MiB** for both backends.

### Regression tests (in `tests/test_almacen.py`; 73 → 80)

| Test | Backend | What it proves |
|---|---|---|
| `test_fifo_at_a_key_fails_promptly` | Local | Real FIFOs at `temporal/fifo` and `final/v1/fifo`. `leer`, `copiar`, `leer` of the final key and `tamano_de` each return `FalloAlmacenError`. The FIFO is unchanged, `final/v1/n1` does not exist and no partial file is left. The calls run **in a child process with a 20 s deadline**, so a regression fails the test instead of hanging CI. |
| `test_fifo_where_a_directory_belongs_fails_promptly` | Local | FIFOs at `temporal` and `final/v1`: `leer`, `guardar_temporal`, `tamano_de` and `listar` fail promptly with `FalloAlmacenError`, in a child with a deadline |
| `test_regular_objects_are_read_in_blocking_mode` | Local | A regular object's descriptor is back in blocking mode and reads in full |
| `test_oversized_chunks_are_rejected_before_copying` | Both | Rejects, with peak allocation **under 256 KiB**: a 32 MiB bytearray, its memoryview, a typed `array('I')` view of 262,145 elements and 1,048,580 bytes (element count ≤ 1 MiB < byte size), a 2-D view (`len` 2, 2 MiB) and `bytes` one byte over. Buffers are allocated before measurement. The previous staging object is kept. |
| `test_typed_and_multidimensional_views_round_trip` | Both | A typed `array('H')` view, a 2-D view and a non-contiguous view are stored as their C-order bytes, and a typed view of exactly 1 MiB is accepted |
| `test_failures_leave_no_partial_files` (extended) | Local | A rejected 2 MiB memoryview leaves no partial file |

**The new tests fail on the reviewed code.** With `server/almacen.py` reverted to `2f4ec1d` and the new tests kept:
- `test_fifo_at_a_key_fails_promptly` failed with "a storage call blocked … child terminated" after its deadline;
- `test_oversized_chunks_are_rejected_before_copying` failed for the bytearray, memoryview, typed-view and 2-D cases on **both** backends (9 failures in total);
- with the fix restored, all 80 pass.

The directory-position FIFO test also passed on the old code on Linux, because `O_DIRECTORY` already fails there before blocking. It stays as a guard for other platforms.

### Evidence at the correction head

Same container as §4 (Linux x86_64, CPython 3.13.16, plus 3.9.25 standing in for macOS's Python):

| Check | Result |
|---|---|
| `tests.test_almacen` on 3.13 and 3.9 | **80 OK** each; 5 consecutive 3.13 runs, all OK |
| Full Python suite on 3.13 and 3.9 | **752 run, 29 Postgres-only skips, 1 failure**: the same environmental `test_packaging…no_openpyxl_of_its_own`, because this container's `/usr/bin/python3` has openpyxl. The supervisor's macOS run did not reproduce it. 752 = 672 + 80. |
| JavaScript | 98 pass |
| `ruff check server/ tests/`, `mypy server/` | Clean |
| `medir.py 256` (3.13) | Unchanged: peak Python allocations ≤ 0.13 MiB for a 256 MiB write, copy and read |
| `./verificar.sh` | Not runnable here (no `zsh`); its components were run as above |
| GitHub CI | Reported in PR #13 for the correction head |

The scope is unchanged: only `server/almacen.py`, `tests/test_almacen.py` and this report were edited. There is no database or API integration, and nothing was merged, deployed or provisioned.
