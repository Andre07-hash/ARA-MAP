"""Verify, without modifying anything, that the byte store holds every attachment
the database references; optionally export the verified bytes.

    python3 scripts/verificar_archivos.py --sqlite datos/ara.db --almacen-local CARPETA
    python3 scripts/verificar_archivos.py --url-env VARIABLE --almacen-entorno --json
    python3 scripts/verificar_archivos.py --url-env VARIABLE --almacen-entorno --exportar CARPETA
    python3 scripts/verificar_archivos.py --manifiesto CARPETA/manifiesto.json \
        --almacen-local DESTINO --restauracion [--cargar-exportacion CARPETA]

--url-env names an environment variable holding a Postgres URL (the URL itself
never goes on the command line and is never printed). Exit codes: 0 everything
verified, 1 integrity problems, 2 usage or configuration error. The manifest
format and the logic live in server/recuperacion.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import recuperacion  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(recuperacion.main())
