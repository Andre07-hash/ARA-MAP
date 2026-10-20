"""tabla_servidor.py with the terrain assistant on and a FICTIONAL provider.

    python3 tests/e2e/asistente_servidor.py --puerto 8491 --carpeta /tmp/ara-asistente \
        [--registro /tmp/ara-asistente/enviado.jsonl]

Everything tabla_servidor.py does (disposable database, fictional accounts),
plus fictional ARA_MAP_CHAT_* values and the REAL Anthropic adapter
(server/asistente/terreno.py) whose HTTPS transport is replaced by one that
never connects: it checks the request goes to the fixed endpoint, appends the
request body to --registro (one JSON object per line) and answers with a
fixed, fictional Messages API body. No key, no network, nothing billed.
Answers from here are NOT from Claude; they only prove the wiring.

Used by tests/e2e/tabla-asistente.mjs with ASISTENTE_CONECTADO=1.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FICTICIO = {
    "ARA_MAP_CHAT_HABILITADO": "1",
    "ARA_MAP_CHAT_MODELO": "modelo-ficticio",
    "ARA_MAP_CHAT_CLAVE": "clave-ficticia-sin-valor",
    "ARA_MAP_CHAT_LIMITE_MENSUAL_USD": "5",
    "ARA_MAP_CHAT_COSTO_ENTRADA_USD_MTOK": "0.10",
    "ARA_MAP_CHAT_COSTO_SALIDA_USD_MTOK": "0.50",
    "ARA_MAP_CHAT_MAX_POR_HORA": "1000",
}
RESPUESTA = ("Respuesta del proveedor ficticio de pruebas, no de Claude. "
             "<b>Sin formato</b> [enlace](https://ejemplo.invalid).")


def transporte_ficticio(registro: Path | None) -> Any:
    from server.asistente.terreno import ProveedorAnthropic
    candado = threading.Lock()

    def transporte(peticion: Any, tiempo: float) -> bytes:
        if peticion.full_url != ProveedorAnthropic.URL:
            raise RuntimeError("endpoint inesperado")
        if registro is not None:
            with candado, registro.open("a", encoding="utf-8") as f:
                # Decoded, so a search finds the text as written (the wire is ASCII-escaped).
                f.write(json.dumps(json.loads(peticion.data), ensure_ascii=False) + "\n")
        return json.dumps({
            "id": "msg_ficticio", "type": "message", "role": "assistant",
            "model": FICTICIO["ARA_MAP_CHAT_MODELO"],
            "content": [{"type": "text", "text": RESPUESTA}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 400, "output_tokens": 40},
        }).encode()
    return transporte


def main() -> None:
    registro = None
    if "--registro" in sys.argv:
        i = sys.argv.index("--registro")
        registro = Path(sys.argv[i + 1])
        del sys.argv[i:i + 2]
    os.environ.update(FICTICIO)
    from server.asistente import terreno
    terreno.fijar_proveedor(terreno.ProveedorAnthropic(transporte_ficticio(registro)))
    import tabla_servidor
    tabla_servidor.main()


if __name__ == "__main__":
    main()
