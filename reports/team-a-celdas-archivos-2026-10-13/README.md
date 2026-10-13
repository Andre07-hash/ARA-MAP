# Equipo A — «Elegir PDF…» / «Elegir KMZ…» en la tabla

13 de octubre de 2026. Rama `claude/sleepy-sagan-5prqyv`, desde
`codex/team-a-free-pilot-v1` en `31b6a1dba827b57d448a2aeb62ad10c05db09afc`
(sin commits posteriores en esa rama al empezar). Sin despliegue, sin datos
reales, sin cambios de API, esquema, almacenamiento, límites ni permisos.

## Qué cambia

- Las celdas «Archivos» y «KMZ» conservan su resumen («1 PDF», «Contorno
  activo»…) y muestran un botón «Elegir PDF…» / «Elegir KMZ…», también sin
  archivos. El botón abre el selector de esa fila y corre la misma subida del
  detalle (`subida.js`, el cliente, el turno y el tope de cinco subidas de la
  fábrica). Debajo aparece la fase, el progreso, los errores y, cuando aplica,
  «Reintentar» / «Cancelar». Al terminar, la tabla refresca el resumen de esa
  fila (`onCambio`).
- El botón aparece sólo si la fila es editable según la regla central de la
  tabla (`filaEditable`: modo de consulta, base propia archivada, terreno
  archivado). El contrato `mount(...)` no cambia.
- Clics, doble clic y teclas de los controles no llegan a la fila: no abren
  editor ni disparan otra acción.
- Elegir, procesar, activar, versiones, historial y retiro siguen en el
  detalle (⋯), que no cambia. Un KMZ con varios contornos dice en la celda
  «Varios contornos: elige en el detalle (⋯). Nada se activó.»

**Regla existente que no se tocó:** al completar, el servidor activa un KMZ
cuyo único contorno es válido (igual que desde el detalle). Con varios
contornos no activa nada. Cambiar eso es un cambio de API/flujo; queda para
decisión del propietario.

Archivos: `web/components/archivos/celda.js` (nuevo), `index.js`,
`detalle.js` (sólo exporta dos tablas de texto), `web/styles/archivos.css`,
`web/styles/tabla.css`, `tests/e2e/tabla-elegir.mjs` (nuevo),
`tests/e2e/recorrido-completo.mjs` (lee el resumen de la celda sin el texto
del botón), `tests/e2e/README.md`.

## Evidencia (local, SQLite desechable, Chromium; no Postgres ni entorno publicado)

- `node tests/e2e/tabla-elegir.mjs`: 12/12. Administrador y operador cargan
  PDF y KMZ desde celdas vacías y con archivos; cada archivo queda en su fila
  (comprobado en el servidor); KMZ de varios contornos sin activación hasta
  elegir y activar en el detalle; reemplazo inválido conserva el contorno;
  selector cancelado no envía nada; Enter/Espacio abren el selector y ni
  F2, letras ni doble clic abren editor; sin botones en terreno archivado ni
  en base archivada (vista de la base y tabla maestra); sin errores de página.
- `node tests/e2e/recorrido-completo.mjs` (recorrido existente con widgets
  reales): 41/41 con este cambio y 41/41 en la base, en corridas paralelas.
  Una corrida anterior, simultánea con otra prueba de navegador y con una
  versión intermedia de la celda, dio 39/41 (R3-B1 y R3-B5, subidas en el
  detalle en «fallido»); ambos pasan aislados y en las corridas completas
  posteriores. Se anota por transparencia.
- `node --test tests/js/*.test.mjs`: 211/211.
- `python3 -m unittest discover -s tests -t .`: 1447 pruebas, 1 falla
  ambiental (`test_packaging`: el Python de este contenedor trae openpyxl; falla
  igual en la base), 297 omitidas (Postgres sin URL de prueba).
- `verificar.sh` requiere zsh, que no existe en este contenedor; se corrieron
  sus pasos por separado. No se corrió ruff/mypy (`--todo`).

Capturas: [administrador](01-administrador-botones-en-tabla.png),
[operador](02-operador-botones-en-tabla.png) (datos ficticios).

## Sin verificar

Postgres, Render/Supabase/Neon, Safari/Firefox y un lector de pantalla real.
Si la base de una fila se archiva en otra sesión, la tabla abierta lo sabe al
refrescar sus bases (igual que las celdas de texto); el servidor rechaza la
subida de todos modos.
