"""Report whether automatic assistance is configured, and what is missing.

    python3 scripts/estado_ia.py

Prints settings by name only -- never the key's value -- and exits 0 when
assistance is fully configured, 1 otherwise. Does not contact any provider.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.asistente import ia  # noqa: E402

config, faltan = ia.configuracion()
if config is None:
    print("Asistencia automática: APAGADA. El asistente de importación funciona con detección y preguntas.")
    for motivo in faltan:
        print(f"  - Falta: {motivo}")
    raise SystemExit(1)

print("Asistencia automática: configurada.")
print(f"  proveedor={config.proveedor} modelo={config.modelo or '-'} clave={'definida' if config.clave else '-'}")
print(f"  límite mensual=US${config.limite_mensual_usd:g} · entrada=US${config.costo_entrada_mtok:g}/Mtok · "
      f"salida=US${config.costo_salida_mtok:g}/Mtok")
print(f"  tiempo máximo={config.tiempo_s:g}s · muestras por columna={config.muestras} · "
      f"consultas por hora={config.max_por_hora}")
if config.proveedor == "simulado":
    print("  AVISO: 'simulado' es una tabla de palabras clave para demostraciones, no un modelo.")
