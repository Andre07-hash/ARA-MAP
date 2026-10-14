# Mapa de Tabla / Mapa: más espacio para el lienzo (issue #40)

Capturas antes/después con datos ficticios, servidor local desechable
(`tests/e2e/tabla_servidor.py`), Chromium y las mismas ventanas. Los mosaicos
del fondo no se descargan en las capturas (fondo liso); el mapa, la leyenda,
los selectores y los créditos son los reales.

- **Antes:** `main` en `cce7ea7`.
- **Después:** la rama de este cambio.

| Captura | Ventana | Lienzo antes | Lienzo después |
|---|---|---|---|
| `01-admin-escritorio` | 1440×900 | 1176×499 (45 %) | 1176×810 (73 %) |
| `02-admin-ficha-contorno` (ficha abierta, contorno activo) | 1440×900 | 792×499 (30 %) | 792×810 (49 %) |
| `03-admin-filtros-heredados` (Tabla: Estado = Jalisco e Incluir archivados) | 1440×900 | 1176×499 (45 %) | 1176×810 (73 %) |
| `04-admin-estrecha` | 390×844 | 390×256 (30 %) | 390×670 (79 %) |
| `05-operador-escritorio` | 1440×900 | 1176×499 (45 %) | 1176×810 (73 %) |

`despues/04b-admin-estrecha-filtros-heredados.png` muestra la nota de filtros
heredados abierta a 390 px. En ninguna captura hay desplazamiento horizontal.

## Comportamiento

- Fila superior delgada en Mapa: Vista, Tabla / Mapa y Actualizar. Buscar,
  Estado, Municipio, Tipo, Ordenar por, Descendente, Incluir archivados,
  Agregar terreno, Columnas y Bases y accesos se ocultan en Mapa sin borrar sus
  valores; siguen en Tabla.
- «Filtros de la tabla (N)» aparece sólo si la tabla filtra el conjunto
  (búsqueda, estado, municipio, tipo, archivados). Se abre con clic o teclado
  y se cierra con Escape.
- Tipo de terreno es un filtro local del panel izquierdo; «Limpiar» lo quita y
  no toca la consulta de la tabla.
- Sin franja de alcance, título, cuenta ni párrafo: la explicación queda tras
  el botón «i». Terrenos filtrados en el panel; ubicados y fuera del mapa en
  la leyenda.
- «Encuadrar todo» e «i» bajo el zoom. Avisos de carga, error con
  «Volver a intentar», conjunto incompleto y estado del contorno con
  «Reintentar» flotan arriba a la izquierda sólo cuando hay algo que decir.
- En Mapa el pie sólo aparece con una alerta o una subida sin terminar.

Sin cambios de esquema, datos, API, permisos ni infraestructura.
