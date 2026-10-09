"""Reproduce bounded local/fake attachment measurements with fictional bytes."""

from __future__ import annotations

import hashlib
import io
import json
import platform
import tempfile
import time
import tracemalloc
import uuid
import zipfile
from pathlib import Path

from server import archivos, auth, db
from server.almacen import MAX_BLOQUE, AlmacenEnMemoria, AlmacenLocal
from tests.support import TEST_PASSWORD

ROOT = Path(__file__).resolve().parents[2]
KML = ROOT / "tests" / "fixtures" / "kmz" / "poligono_simple.kml"


def chunks(data: bytes):
    view = memoryview(data)
    for offset in range(0, len(view), MAX_BLOQUE):
        yield view[offset:offset + MAX_BLOQUE]


def kmz_near_limit() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("doc.kml", KML.read_bytes())
        archive.writestr("relleno-ficticio.bin", bytes(archivos.KMZ_MAX - 4096))
    return output.getvalue()


def fixture(database: Path):
    with db.session(database) as conn:
        user = auth.create_user(conn, "medicion", "Medición Ficticia", TEST_PASSWORD,
                                iterations=1000, rol="admin")
        now = db.now()
        terrain = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO inventory_terrain (id, version, created_at, created_by, updated_at,"
            " updated_by) VALUES (?, 1, ?, ?, ?, ?)",
            (terrain, now, user["id"], now, user["id"]))
        token, _, _ = auth.login(conn, "medicion", TEST_PASSWORD)
        session = auth.sesion_de_token(conn, token)
    return session, terrain


def measure(name: str, kind: str, data: bytes, local: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "measure.db"
        session, terrain = fixture(database)
        store = AlmacenLocal(root) if local else AlmacenEnMemoria()
        try:
            tracemalloc.start()
            started_at = time.perf_counter()
            started = archivos.iniciar(
                session, terrain, tipo=kind, nombre_original=f"{name}.{kind}",
                tamano_declarado=len(data), sha256_declarado=hashlib.sha256(data).hexdigest(),
                idempotency_key=name, bd=database)
            archivos.escribir_temporal(session, started["version_id"], chunks(data), store,
                                       bd=database)
            result = archivos.completar(session, started["version_id"], store, bd=database)
            elapsed = time.perf_counter() - started_at
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        finally:
            close = getattr(store, "close", None)
            if close:
                close()
        return {"case": name, "storage": "local" if local else "fake",
                "bytes": len(data), "elapsed_seconds": round(elapsed, 3),
                "tracemalloc_peak_mib": round(peak / 1024 / 1024, 2),
                "state": result["version"]["estado"], "applied": result["aplicada"]}


def main() -> None:
    pdf = b"%PDF-1.4\n" + bytes(archivos.PDF_MAX - len(b"%PDF-1.4\n"))
    kmz = kmz_near_limit()
    rows = [measure(f"{kind}-max-{backend}", kind, data, backend == "local")
            for kind, data in (("pdf", pdf), ("kmz", kmz))
            for backend in ("fake", "local")]
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                      "measurements": rows}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
