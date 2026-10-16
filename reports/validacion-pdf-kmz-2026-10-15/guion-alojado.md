# Guion de comprobación alojada (Render + Neon + Supabase) — NO EJECUTADO

Estado: **validación alojada pendiente de entorno y autorización.** Este guion no
se ejecutó. No hay un destino de ensayo autorizado y la issue #51 prohíbe usar el
servicio, la base o el bucket actuales, crear recursos o cambiar planes.

La campaña local (SQLite/Postgres 16 desechables + almacén local en disco) no
certifica Render, Neon ni Supabase. Las pruebas `test_almacen_supabase` usan el
SDK `storage3` real con un **transporte falso**: no son evidencia del proveedor.

## Requisitos previos (los decide y prepara el propietario)

1. Un destino de ensayo **aislado y autorizado por escrito**: un servicio Render
   distinto del productivo, una base Neon o rama desechable y un bucket Supabase
   privado vacío, todos en planes gratuitos. Sin tarjeta, sin ampliaciones.
2. El SHA exacto a probar, revisado y con CI verde en `main` (anotarlo).
3. Cuentas ficticias creadas en esa base desechable: un administrador, un
   operador con acceso a una base de ensayo y un operador sin acceso.
   Contraseñas fuera de GitHub y de los reportes.
4. Nada de datos reales: sólo archivos generados (ver «Archivos»).

Si alguno falta, detenerse y reportar «pendiente de entorno/autorización».

## Archivos ficticios

Generarlos localmente con los mismos generadores del ensayo:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "tests/e2e")
from pathlib import Path
from ensayo_archivos import pdf_ficticio, kmz_ficticio, MiB
d = Path("/tmp/ara-alojado"); d.mkdir(exist_ok=True)
(d / "pequeno.pdf").write_bytes(pdf_ficticio("alojado"))
(d / "limite-25MiB.pdf").write_bytes(pdf_ficticio("limite", 25 * MiB))
(d / "contorno.kmz").write_bytes(kmz_ficticio(7))
(d / "limite-20MiB.kmz").write_bytes(kmz_ficticio(8, 20 * MiB))
(d / "uno-de-mas.pdf").write_bytes(pdf_ficticio("mas", 25 * MiB + 1))
EOF
sha256sum /tmp/ara-alojado/*      # anotar las huellas antes de subir
```

## Pasos (en el navegador, sobre el destino de ensayo)

Registrar para cada paso: hora, cuenta, resultado esperado/observado, duración y
cualquier mensaje. Nunca copiar cookies, URLs firmadas ni cadenas de conexión.

| # | Paso | Esperado |
|---|------|----------|
| 1 | Abrir el servicio dormido y medir el primer arranque (despertar). | Responde; anotar segundos. |
| 2 | Administrador: «Elegir PDF…» en una fila con `pequeno.pdf`. | «1 PDF»; abrir desde el contador; descargar y comparar `sha256sum` con el original. |
| 3 | Operador autorizado: `limite-25MiB.pdf` desde el detalle. | Se guarda; la descarga tiene el mismo tamaño y SHA-256. Anotar duración. |
| 4 | Operador autorizado: `limite-20MiB.kmz` y `contorno.kmz` en otra fila. | Contorno activo; la fila aparece en Mapa aunque no tenga X/Y. |
| 5 | Elegir `uno-de-mas.pdf`. | Rechazo local «supera el límite de 25 MB», sin petición al servidor. |
| 6 | Operador sin acceso: intentar abrir la URL de la fila / del archivo. | Nada visible; 404 genérico. |
| 7 | Retirar el acceso del operador mientras sube un PDF grande (otra pestaña). | La subida termina en «no disponible»; nada se guarda a su nombre. |
| 8 | Recargar la pestaña durante el envío del PDF grande. | Al volver: subida sin terminar, nunca «PDF guardado»; «Elegir de nuevo» o cancelar funcionan. |
| 9 | Reiniciar el servicio de ensayo (deploy manual del mismo SHA) y repetir 2. | Lo guardado sigue con los mismos bytes. |
| 10 | Borrar el PDF del paso 2 y abrir el enlace viejo en otra pestaña. | 404 real; la fila sigue; el contador baja. |
| 11 | Cerrar: borrar los archivos de ensayo desde la interfaz. | Bucket de ensayo sin objetos de esos terrenos. |

## Memoria y tiempos

Anotar el pico de memoria que muestre Render para el servicio de ensayo durante
los pasos 3 y 4 juntos (dos pestañas). Referencia local, no transferible: el
proceso local alcanzó 120–170 MiB de RSS con un PDF de 25 MiB y un KMZ de 20 MiB
simultáneos (ver README.md, «Ensayos»).

## Al terminar

Publicar los resultados como comentario en la issue #51 con el SHA probado,
distinguiendo «alojado de ensayo» de «producción». No tocar producción.
