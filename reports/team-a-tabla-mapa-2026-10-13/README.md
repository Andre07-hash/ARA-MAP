# Equipo A — Tabla / Mapa para administrador y operador

13 de octubre de 2026. Rama `claude/tabla-mapa`, encima del head de #33
(`claude/sleepy-sagan-5prqyv`; los botones «Elegir PDF…/KMZ…» se conservan).
Sin despliegue, sin datos reales, sin cambios de API, esquema, almacenamiento,
proveedor ni permisos del servidor.

## Qué cambia

- **Navegación.** El administrador entra a la Tabla maestra (`#/tabla/maestra`);
  «Inventario» sale del menú. `#/inventario` lleva a `#/tabla/maestra/mapa`;
  `#/inventario/<id>`, `/nuevo` y `/<id>/editar` siguen funcionando para
  administradores (no se borró ningún componente). El operador sigue sin acceso
  a esas rutas y entra a su base.
- **Selector «Tabla / Mapa»** en la barra de la tabla, para ambos roles, en
  lugar de «Mapa de esta página». El mapa ocupa el área de la tabla. La ruta lo
  recuerda (`#/tabla/<vista>/mapa`).
- **Conjunto completo.** El mapa muestra todos los terrenos de la vista y sus
  filtros, reunidos página a página (200 por página) con la misma ruta
  autorizada de la tabla (`/maestra/bases/<id>/terrenos` para el operador). Se
  conserva mientras vista y consulta no cambien: alternar o paginar no vuelve a
  descargar. «Actualizar» o una revalidación lo vuelven a reunir. Sin
  búsqueda ni filtros de campos, las escrituras de esta tabla lo actualizan en
  el lugar (sólo base y archivo deciden la pertenencia). Con búsqueda o filtro
  por estado, municipio o tipo, una edición o un alta descarta el conjunto y se
  vuelve a reunir con la consulta del servidor al mostrar el mapa: la
  pertenencia no se recalcula en el navegador. Una escritura hecha con otro
  filtro deja el conjunto marcado para reunirse otra vez. Tope de 5,000
  terrenos: si se alcanza, el mapa dice «Mapa incompleto».
- **Contornos.** Sólo se carga el cuerpo del terreno seleccionado (contorno
  ACTIVO), uno a la vez, con cancelación y descarte de respuestas atrasadas
  (comportamiento existente de `vistaPrevia.js`). Contorno activo sin X/Y: se
  ve por su punto interior. X/Y sin contorno: punto. Sin nada: «sin ubicación».
- **Se mantienen** base, filtros, página de la tabla y terreno seleccionado al
  alternar.

## Reutilización

| Pieza | Uso |
|---|---|
| `web/components/tabla/vistaPrevia.js` | El mapa: mismo selector de cuerpos, cancelación y liberación; recibe el conjunto en vez de la página. Textos actualizados; «Encuadrar todo» espera a que termine una animación (Leaflet la ignoraba). |
| `web/components/map/MapCanvas.js` | Sin cambios: mismo dibujo de puntos y contornos. |
| `web/lib/cargadorGeometrias.js` | Sin cambios. |
| `web/lib/inventario.js` `reunirPaginas` | La misma reunión de páginas de Inventario, con un tope opcional que informa `incompleto`. |
| `web/components/inventory/DatosView.js` `segment` | El mismo control segmentado de Inventario. |
| `web/lib/tabla.js` `rutaDeLista` / `consultaDeLista` | La consulta autorizada de la tabla, con la misma vista y filtros. |

## Evidencia (local: SQLite desechable, Chromium del contenedor; nada alojado)

| Prueba | Resultado |
|---|---|
| `node tests/e2e/tabla-mapa.mjs` (nueva; 111 terrenos ficticios en una base, 5 en otra) | 18/18 |
| `node tests/e2e/tabla-elegir.mjs` (#33, convivencia) | 12/12 |
| `node tests/e2e/recorrido-completo.mjs` (widgets reales; adaptado al selector) | 41/41 |
| `tests/e2e/tabla-integrada.mjs` (con `tabla_servidor.py`) | 13/13 |
| `tests/e2e/tabla-archivos.mjs` (anfitrión con dobles; adaptado) | 6/6 |
| `tests/e2e/tabla-identidad.mjs` (4,200 registros sintéticos) | 16/16 |
| `node --test tests/js/*.test.mjs` | 212/212 |

Medidas de `tabla-mapa.mjs` en este contenedor: reunir 111 terrenos ≈ 0.2 s;
seleccionar el KMZ del fixture de 100,000 vértices ≈ 1.6–1.9 s hasta cargarlo
y ≈ 1.8–2.1 s a escala; 20 alternancias Tabla/Mapa: un mapa, un cuerpo, cero
reuniones nuevas, montón JS 12.1 → 11.8 MB.

Regresiones nuevas: alcance del operador (ni filas ni contornos ni peticiones
de otra base; una base ajena por dirección cae en la suya), conjunto más allá
de la página, filtros, respuestas atrasadas al cambiar selección, filtro y
base, error y carga parcial que no se presenta como completa, escritura con
otro filtro, y limpieza inmediata del mapa al cambiar el filtro. Las dos
últimas reproducen los dos fallos que encontró la revisión independiente:
fallan con el código anterior a la corrección y pasan después.

Revisión del supervisor (misma consulta activa): editar el estado o el nombre
de un terreno para que deje de coincidir con el filtro o la búsqueda, y crear
una fila en blanco con un filtro activo, ya no lo dejan en el mapa filtrado.
Tres regresiones lo cubren; las tres fallaban antes de la corrección. Sin
filtros, la fila nueva entra al mapa sin otra reunión, y alternar sin cambios
no vuelve a reunir.

Una corrida intermedia de `recorrido-completo.mjs` falló en «R3-A2: se archiva
la base mientras un administrador sube…» (aviso de base archivada); no se
repitió en la corrida completa siguiente (41/41). Se anota como intermitente.

### No ejecutado o desfasado de antes

- `inventario-fixtures.mjs`: 7 de 11 casos fallan **igual en la base**
  (`5f642b6`): su sesión ficticia no trae `rol`. No se tocó.
- `inventario-integrado.mjs`: sus instrucciones crean cuentas operador (sin
  `--rol admin`), que no tienen Inventario desde que existen los roles; ya
  estaba desfasado. No se corrió ni se reescribió.
- `tabla-mapa-memoria.mjs`: medía el panel «Mapa de esta página»; queda con
  una nota. La medición de este diseño está en `tabla-mapa.mjs`.
- Postgres desechable, Render/Supabase/Neon, otros navegadores y lector de
  pantalla: no ejecutados aquí.

Capturas (datos ficticios): [administrador, mapa](01-administrador-mapa.png),
[administrador, contorno](02-administrador-contorno-seleccionado.png),
[operador, mapa](03-operador-mapa.png),
[administrador, tabla](04-administrador-tabla-con-selector.png),
[operador, tabla](05-operador-tabla-con-selector.png).

## Limitaciones

- Un cambio hecho por otra persona aparece en el mapa al pulsar «Actualizar»
  o en la siguiente revalidación (como en la tabla).
- Desde el mapa no se abre el detalle de un terreno; se selecciona y se vuelve
  a «Tabla». Si el terreno está en la página actual, su fila queda marcada.
- Los fixtures KMZ ficticios están en el mismo lugar; la prueba acerca el mapa
  para separar sus símbolos antes de hacer clic.
