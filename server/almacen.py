"""Byte storage for attachments: a local filesystem backend and an in-memory fake.

This is only the byte layer. It knows nothing about terrains, users, file
versions, upload credentials, PDF or KMZ: a future authorized service decides
which keys exist, which limits apply and which object a database row names.
Nothing here starts a server, picks a default directory or reads settings.

Keys are server-generated opaque identifiers in two namespaces:

    temporal/<id>          staging, replaceable as a whole
    final/<id>/<nonce>     write-once; never overwritten

Each segment is 1-100 characters of lowercase ASCII letters, digits, "_" and
"-", starting with a letter or digit. Lowercase only, so that a key means the
same object on the case-insensitive filesystems macOS uses by default. Original
file names never become keys.

Both backends share one observable contract (see the PR report for the frozen
signatures):

- guardar_temporal(clave, bloques, limite) -> bytes written. Streams chunks
  into a staging object and exposes it atomically: readers see the previous
  complete object or the new complete one, never a partial write. Exceeding
  `limite` or any failure keeps the previous object.
- copiar(origen, destino, limite) -> bytes copied. Copies a staging object to
  a final key that must not exist. Two copies racing for one destination give
  one winner and a ColisionError for the other; the winner's bytes are unchanged.
  The copy is a snapshot: later staging writes never reach it.
- leer(clave, limite[, bloque]) -> Lectura. Bounded streaming. An object
  larger than `limite` raises LimiteExcedidoError before any byte is returned.
- tamano_de(clave) -> int, or None when absent.
- borrar(clave) -> True if this call removed it, False if it was absent.
  Exact keys only: there is no prefix or recursive deletion.
- listar(prefijo) -> lazy iterator of Metadato. Prefix is one of "temporal/",
  "final/" or "final/<id>/". Order is unspecified. Listing never deletes.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, Union

TEMPORAL = "temporal"
FINAL = "final"

# Largest chunk a caller may hand to guardar_temporal, and largest chunk a
# Lectura may be asked to return. Keeps every operation's buffers bounded.
MAX_BLOQUE = 1024 * 1024
BLOQUE_LECTURA = 64 * 1024

_SEGMENTO = re.compile(r"[0-9a-z][0-9a-z_-]{0,99}")
_PREFIJO_PARCIAL = ".parcial-"   # never a valid segment, so never listed or read

Bloque = Union[bytes, bytearray, memoryview]


# --------------------------------------------------------------------- errors

class AlmacenError(Exception):
    """Base of every storage error. Messages never contain paths or keys."""

    codigo = "almacen"
    mensaje = "Falló el almacenamiento de archivos."

    def __init__(self, mensaje: str | None = None) -> None:
        super().__init__(mensaje or self.mensaje)


class ClaveInvalidaError(AlmacenError):
    """The key is not a well-formed key of the namespace the operation needs."""

    codigo = "clave_invalida"
    mensaje = "Identificador de archivo no válido."


class ObjetoAusenteError(AlmacenError):
    """The object does not exist."""

    codigo = "objeto_ausente"
    mensaje = "El archivo no existe en el almacenamiento."


class ColisionError(AlmacenError):
    """The final key already exists; nothing was written."""

    codigo = "colision"
    mensaje = "Ya existe un archivo con ese identificador."


class LimiteExcedidoError(AlmacenError):
    """The object or stream is larger than the caller's limit."""

    codigo = "limite_excedido"
    mensaje = "El archivo supera el tamaño permitido."

    def __init__(self, limite: int) -> None:
        super().__init__()
        self.limite = limite


class FalloAlmacenError(AlmacenError):
    """The storage itself failed, or its contents are not what this module wrote."""

    codigo = "fallo_almacen"


# ----------------------------------------------------------------- validation

def partes_de_clave(clave: object, espacio: str | None = None) -> tuple[str, ...]:
    """The segments of a valid key, optionally requiring its namespace."""
    if not isinstance(clave, str):
        raise ClaveInvalidaError()
    partes = tuple(clave.split("/"))
    forma = {TEMPORAL: 2, FINAL: 3}.get(partes[0])
    if forma is None or len(partes) != forma:
        raise ClaveInvalidaError()
    if espacio is not None and partes[0] != espacio:
        raise ClaveInvalidaError()
    if not all(_SEGMENTO.fullmatch(p) for p in partes[1:]):
        raise ClaveInvalidaError()
    return partes


def _partes_de_prefijo(prefijo: object) -> tuple[str, ...]:
    if not isinstance(prefijo, str) or not prefijo.endswith("/"):
        raise ClaveInvalidaError()
    partes = tuple(prefijo[:-1].split("/"))
    if partes in ((TEMPORAL,), (FINAL,)):
        return partes
    if len(partes) == 2 and partes[0] == FINAL and _SEGMENTO.fullmatch(partes[1]):
        return partes
    raise ClaveInvalidaError()


def _validar_limite(limite: object) -> int:
    if isinstance(limite, bool) or not isinstance(limite, int) or limite <= 0:
        raise ValueError("limite must be a positive int")
    return limite


def _validar_tamano_bloque(bloque: object) -> int:
    if isinstance(bloque, bool) or not isinstance(bloque, int) or not 0 < bloque <= MAX_BLOQUE:
        raise ValueError(f"bloque must be an int between 1 and {MAX_BLOQUE}")
    return bloque


def _como_bytes(bloque: object) -> bytes:
    if not isinstance(bloque, (bytes, bytearray, memoryview)):
        raise TypeError("each chunk must be bytes, bytearray or memoryview")
    datos = bytes(bloque)
    if len(datos) > MAX_BLOQUE:
        raise ValueError(f"chunks are limited to {MAX_BLOQUE} bytes")
    return datos


def _bloques_validos(bloques: Iterable[Bloque]) -> Iterable[Bloque]:
    if isinstance(bloques, (bytes, bytearray, memoryview, str)):
        raise TypeError("bloques must be an iterable of chunks, not a single value")
    return bloques


@dataclass(frozen=True)
class Metadato:
    """One listed object."""

    clave: str
    tamano: int
    modificado: float   # seconds since the epoch


# -------------------------------------------------------------- the interface

class Lectura:
    """A bounded stream of one object's bytes.

    Iterate it or use it as a context manager. Its resource is released when
    the bytes run out, when reading fails, on close() and on leaving a `with`
    block, so abandoning a read early never keeps a file open.
    """

    tamano: int

    def __iter__(self) -> Lectura:
        return self

    def __next__(self) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> Lectura:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Almacen(Protocol):
    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int: ...

    def copiar(self, origen: str, destino: str, limite: int) -> int: ...

    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura: ...

    def tamano_de(self, clave: str) -> int | None: ...

    def borrar(self, clave: str) -> bool: ...

    def listar(self, prefijo: str) -> Iterator[Metadato]: ...


# -------------------------------------------------------------- local backend

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_ABRIR_DIRECTORIO = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | _O_CLOEXEC
_ABRIR_LECTURA = os.O_RDONLY | os.O_NOFOLLOW | _O_CLOEXEC
_CREAR_PARCIAL = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | _O_CLOEXEC


def _soporta_dir_fd() -> bool:
    necesarios = (os.open, os.mkdir, os.stat, os.unlink, os.link)
    return all(f in os.supports_dir_fd for f in necesarios) and os.scandir in os.supports_fd


class _LecturaLocal(Lectura):
    def __init__(self, fd: int, tamano: int, limite: int, bloque: int) -> None:
        self._fd: int | None = fd
        self.tamano = tamano
        self._limite = limite
        self._bloque = bloque
        self._leidos = 0

    def __next__(self) -> bytes:
        if self._fd is None:
            raise StopIteration
        try:
            datos = os.read(self._fd, self._bloque)
        except OSError as exc:
            self.close()
            raise FalloAlmacenError() from exc
        if not datos:
            self.close()
            if self._leidos != self.tamano:     # changed in place: not written by this module
                raise FalloAlmacenError("El archivo cambió mientras se leía.")
            raise StopIteration
        self._leidos += len(datos)
        if self._leidos > self._limite:
            self.close()
            raise LimiteExcedidoError(self._limite)
        return datos

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)

    def __del__(self) -> None:
        self.close()


class AlmacenLocal:
    """Objects as files under an explicit root directory.

    Trust model: the root directory and everything above it belong to the
    application's operator. Keys may come from a compromised higher layer and
    entries below the root may have been planted by another local process, so
    every path is walked from a directory descriptor opened once on the root,
    one validated component at a time, with O_NOFOLLOW. A symbolic link
    anywhere below the root is refused instead of followed, and there is no
    check-then-open step to race. Requires POSIX *at() calls (Linux, macOS).

    Writes go to a hidden partial file in the destination directory and appear
    under their key only through an atomic rename (staging) or a hard link
    that fails if the name exists (final). Partial files left by a crashed
    process are never listed or read; nothing here removes them automatically.
    """

    def __init__(self, raiz: str | os.PathLike[str]) -> None:
        self._raiz: int | None = None
        if not _soporta_dir_fd():
            raise FalloAlmacenError("Este sistema no permite el almacenamiento local seguro.")
        try:
            self._raiz = os.open(os.fspath(raiz), os.O_RDONLY | os.O_DIRECTORY | _O_CLOEXEC)
        except OSError as exc:
            raise FalloAlmacenError("La carpeta de almacenamiento no existe o no se puede abrir.") \
                from exc

    def close(self) -> None:
        fd, self._raiz = self._raiz, None
        if fd is not None:
            os.close(fd)

    def __enter__(self) -> AlmacenLocal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    # -- directory walking

    def _raiz_fd(self) -> int:
        if self._raiz is None:
            raise FalloAlmacenError("El almacenamiento ya se cerró.")
        return self._raiz

    def _abrir_directorio(self, partes: tuple[str, ...], crear: bool) -> int | None:
        """A descriptor for root/partes, or None if missing and not `crear`."""
        try:
            actual = os.dup(self._raiz_fd())
        except OSError as exc:      # out of descriptors
            raise FalloAlmacenError() from exc
        try:
            for parte in partes:
                if crear:
                    with suppress(FileExistsError):
                        os.mkdir(parte, 0o700, dir_fd=actual)
                try:
                    siguiente = os.open(parte, _ABRIR_DIRECTORIO, dir_fd=actual)
                except FileNotFoundError:
                    if crear:
                        raise
                    os.close(actual)
                    return None
                os.close(actual)
                actual = siguiente
            return actual
        except OSError as exc:      # includes a symlink or file where a directory belongs
            os.close(actual)
            raise FalloAlmacenError() from exc

    def _abrir_objeto(self, partes: tuple[str, ...]) -> tuple[int, os.stat_result]:
        directorio = self._abrir_directorio(partes[:-1], crear=False)
        if directorio is None:
            raise ObjetoAusenteError()
        try:
            fd = os.open(partes[-1], _ABRIR_LECTURA, dir_fd=directorio)
        except FileNotFoundError:
            raise ObjetoAusenteError() from None
        except OSError as exc:      # ELOOP for a symlink, EISDIR, permissions
            raise FalloAlmacenError() from exc
        finally:
            os.close(directorio)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise FalloAlmacenError()
        except BaseException:
            os.close(fd)
            raise
        return fd, info

    # -- operations

    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int:
        partes = partes_de_clave(clave, TEMPORAL)
        _validar_limite(limite)
        bloques = _bloques_validos(bloques)
        directorio = self._abrir_directorio(partes[:-1], crear=True)
        assert directorio is not None
        parcial = _PREFIJO_PARCIAL + secrets.token_hex(16)
        publicado = False
        try:
            fd = os.open(parcial, _CREAR_PARCIAL, 0o600, dir_fd=directorio)
            try:
                total = 0
                for bloque in bloques:
                    datos = _como_bytes(bloque)
                    total += len(datos)
                    if total > limite:
                        raise LimiteExcedidoError(limite)
                    _escribir_todo(fd, datos)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(parcial, partes[-1], src_dir_fd=directorio, dst_dir_fd=directorio)
            publicado = True
            _fsync_directorio(directorio)
            return total
        except OSError as exc:
            raise FalloAlmacenError() from exc
        finally:
            if not publicado:
                _quitar(parcial, directorio)
            os.close(directorio)

    def copiar(self, origen: str, destino: str, limite: int) -> int:
        fuente_partes = partes_de_clave(origen, TEMPORAL)
        destino_partes = partes_de_clave(destino, FINAL)
        _validar_limite(limite)
        fuente, info = self._abrir_objeto(fuente_partes)
        try:
            if info.st_size > limite:
                raise LimiteExcedidoError(limite)
            directorio = self._abrir_directorio(destino_partes[:-1], crear=True)
            assert directorio is not None
            try:
                return self._copiar_en(fuente, directorio, destino_partes[-1], limite)
            finally:
                os.close(directorio)
        finally:
            os.close(fuente)

    def _copiar_en(self, fuente: int, directorio: int, nombre: str, limite: int) -> int:
        try:
            os.stat(nombre, dir_fd=directorio, follow_symlinks=False)
        except FileNotFoundError:
            pass                      # the usual case; the link below is the real check
        except OSError as exc:
            raise FalloAlmacenError() from exc
        else:
            raise ColisionError()
        parcial = _PREFIJO_PARCIAL + secrets.token_hex(16)
        try:
            fd = os.open(parcial, _CREAR_PARCIAL, 0o600, dir_fd=directorio)
            try:
                total = 0
                while True:
                    datos = os.read(fuente, BLOQUE_LECTURA)
                    if not datos:
                        break
                    total += len(datos)
                    if total > limite:
                        raise LimiteExcedidoError(limite)
                    _escribir_todo(fd, datos)
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(parcial, nombre, src_dir_fd=directorio, dst_dir_fd=directorio)
            except FileExistsError:
                raise ColisionError() from None
            _fsync_directorio(directorio)
            return total
        except OSError as exc:
            raise FalloAlmacenError() from exc
        finally:
            _quitar(parcial, directorio)

    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura:
        partes = partes_de_clave(clave)
        _validar_limite(limite)
        _validar_tamano_bloque(bloque)
        fd, info = self._abrir_objeto(partes)
        if info.st_size > limite:
            os.close(fd)
            raise LimiteExcedidoError(limite)
        return _LecturaLocal(fd, info.st_size, limite, bloque)

    def tamano_de(self, clave: str) -> int | None:
        partes = partes_de_clave(clave)
        directorio = self._abrir_directorio(partes[:-1], crear=False)
        if directorio is None:
            return None
        try:
            info = os.stat(partes[-1], dir_fd=directorio, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise FalloAlmacenError() from exc
        finally:
            os.close(directorio)
        if not stat.S_ISREG(info.st_mode):
            raise FalloAlmacenError()
        return info.st_size

    def borrar(self, clave: str) -> bool:
        partes = partes_de_clave(clave)
        directorio = self._abrir_directorio(partes[:-1], crear=False)
        if directorio is None:
            return False
        try:
            os.unlink(partes[-1], dir_fd=directorio)
        except FileNotFoundError:
            return False
        except OSError as exc:      # a directory planted at the key, permissions
            raise FalloAlmacenError() from exc
        finally:
            os.close(directorio)
        return True

    def listar(self, prefijo: str) -> Iterator[Metadato]:
        partes = _partes_de_prefijo(prefijo)
        self._raiz_fd()
        return self._listar(partes)

    def _listar(self, partes: tuple[str, ...]) -> Iterator[Metadato]:
        directorio = self._abrir_directorio(partes, crear=False)
        if directorio is None:
            return
        try:
            if partes == (FINAL,):
                for sub in _entradas(directorio, directorios=True):
                    yield from self._listar((FINAL, sub))
            else:
                for nombre in _entradas(directorio, directorios=False):
                    try:
                        info = os.stat(nombre, dir_fd=directorio, follow_symlinks=False)
                    except FileNotFoundError:
                        continue            # removed while listing
                    except OSError as exc:
                        raise FalloAlmacenError() from exc
                    if stat.S_ISREG(info.st_mode):
                        yield Metadato("/".join(partes + (nombre,)), info.st_size, info.st_mtime)
        finally:
            os.close(directorio)


def _entradas(directorio: int, directorios: bool) -> Iterator[str]:
    """Names of valid key segments in a directory, without following links."""
    try:
        with os.scandir(directorio) as entradas:
            for entrada in entradas:
                if not _SEGMENTO.fullmatch(entrada.name):
                    continue                # partial files and anything foreign
                try:
                    es_directorio = entrada.is_dir(follow_symlinks=False)
                    es_archivo = entrada.is_file(follow_symlinks=False)
                except OSError:
                    continue
                if (es_directorio if directorios else es_archivo):
                    yield entrada.name
    except OSError as exc:
        raise FalloAlmacenError() from exc


def _escribir_todo(fd: int, datos: bytes) -> None:
    vista = memoryview(datos)
    while vista:
        escritos = os.write(fd, vista)
        vista = vista[escritos:]


def _quitar(nombre: str, directorio: int) -> None:
    with suppress(OSError):
        os.unlink(nombre, dir_fd=directorio)


def _fsync_directorio(directorio: int) -> None:
    with suppress(OSError):         # not every filesystem syncs directories
        os.fsync(directorio)


# ---------------------------------------------------------------- fake backend

_OPERACIONES_CON_FALLA = ("guardar_temporal", "copiar", "leer")


class _LecturaMemoria(Lectura):
    def __init__(self, datos: bytes, bloque: int, falla_tras: int | None) -> None:
        self._datos: memoryview | None = memoryview(datos)
        self.tamano = len(datos)
        self._bloque = bloque
        self._posicion = 0
        self._entregados = 0
        self._falla_tras = falla_tras

    def __next__(self) -> bytes:
        if self._datos is None:
            raise StopIteration
        if self._falla_tras is not None and self._entregados >= self._falla_tras:
            self.close()
            raise FalloAlmacenError()
        if self._posicion >= self.tamano:
            self.close()
            raise StopIteration
        fin = self._posicion + self._bloque
        trozo = bytes(self._datos[self._posicion:fin])
        self._posicion = fin
        self._entregados += 1
        return trozo

    def close(self) -> None:
        self._datos = None

    @property
    def cerrada(self) -> bool:
        return self._datos is None


class AlmacenEnMemoria:
    """The same contract in memory, for tests of higher layers.

    It holds fictional bytes in memory and enforces the same keys, limits and
    chunk bounds as AlmacenLocal. Fault injection lives only here:
    `inyectar_falla` and `perder` have no counterpart in the local backend.
    """

    def __init__(self) -> None:
        self._objetos: dict[str, tuple[bytes, float]] = {}
        self._candado = threading.Lock()
        self._fallas: dict[str, list[int]] = {op: [] for op in _OPERACIONES_CON_FALLA}

    # -- test surface

    def inyectar_falla(self, operacion: str, tras_bloques: int = 0) -> None:
        """Make the next call of `operacion` raise FalloAlmacenError.

        guardar_temporal fails after consuming `tras_bloques` chunks; leer
        returns a Lectura that fails after yielding `tras_bloques` chunks;
        copiar fails before writing anything. One-shot, first in first out.
        """
        if operacion not in self._fallas:
            raise ValueError(f"no fault injection for {operacion!r}")
        with self._candado:
            self._fallas[operacion].append(tras_bloques)

    def perder(self, clave: str) -> None:
        """Make an object vanish without borrar, as a provider might lose it."""
        partes_de_clave(clave)
        with self._candado:
            self._objetos.pop(clave, None)

    def _tomar_falla(self, operacion: str) -> int | None:
        with self._candado:
            cola = self._fallas[operacion]
            return cola.pop(0) if cola else None

    # -- operations

    def guardar_temporal(self, clave: str, bloques: Iterable[Bloque], limite: int) -> int:
        partes_de_clave(clave, TEMPORAL)
        _validar_limite(limite)
        bloques = _bloques_validos(bloques)
        falla = self._tomar_falla("guardar_temporal")
        recibidos: list[bytes] = []
        total = 0
        for i, bloque in enumerate(bloques):
            if falla is not None and i >= falla:
                raise FalloAlmacenError()
            datos = _como_bytes(bloque)
            total += len(datos)
            if total > limite:
                raise LimiteExcedidoError(limite)
            recibidos.append(datos)
        if falla is not None:
            raise FalloAlmacenError()
        with self._candado:
            self._objetos[clave] = (b"".join(recibidos), time.time())
        return total

    def copiar(self, origen: str, destino: str, limite: int) -> int:
        partes_de_clave(origen, TEMPORAL)
        partes_de_clave(destino, FINAL)
        _validar_limite(limite)
        falla = self._tomar_falla("copiar")
        with self._candado:
            if origen not in self._objetos:
                raise ObjetoAusenteError()
            datos = self._objetos[origen][0]
            if len(datos) > limite:
                raise LimiteExcedidoError(limite)
            if destino in self._objetos:
                raise ColisionError()
            if falla is not None:
                raise FalloAlmacenError()
            self._objetos[destino] = (datos, time.time())
        return len(datos)

    def leer(self, clave: str, limite: int, bloque: int = BLOQUE_LECTURA) -> Lectura:
        partes_de_clave(clave)
        _validar_limite(limite)
        _validar_tamano_bloque(bloque)
        falla = self._tomar_falla("leer")
        with self._candado:
            if clave not in self._objetos:
                raise ObjetoAusenteError()
            datos = self._objetos[clave][0]
        if len(datos) > limite:
            raise LimiteExcedidoError(limite)
        return _LecturaMemoria(datos, bloque, falla)

    def tamano_de(self, clave: str) -> int | None:
        partes_de_clave(clave)
        with self._candado:
            objeto = self._objetos.get(clave)
        return None if objeto is None else len(objeto[0])

    def borrar(self, clave: str) -> bool:
        partes_de_clave(clave)
        with self._candado:
            return self._objetos.pop(clave, None) is not None

    def listar(self, prefijo: str) -> Iterator[Metadato]:
        partes = _partes_de_prefijo(prefijo)
        return self._listar(prefijo, partes)

    def _listar(self, prefijo: str, partes: tuple[str, ...]) -> Iterator[Metadato]:
        with self._candado:
            claves = sorted(c for c in self._objetos if c.startswith(prefijo))
        for clave in claves:
            if len(clave.split("/")) != (2 if partes[0] == TEMPORAL else 3):
                continue
            with self._candado:
                objeto = self._objetos.get(clave)
            if objeto is not None:
                yield Metadato(clave, len(objeto[0]), objeto[1])
