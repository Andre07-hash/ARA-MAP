# Pruebas end-to-end

Opcionales: **no hacen falta para usar ARA Map**. La aplicación no depende de
Node ni de npm. Esto sirve para verificar los flujos principales en un navegador
real. Requiere Google Chrome instalado.

Las pruebas crean por sí mismas las bases y el mapa de comparación que
necesitan, y los borran al terminar. Aun así conviene apuntarlas a una base de
datos desechable, para no tocar la tuya:

```bash
# 1. Levanta la aplicación contra una base de datos temporal
ARA_MAP_DB=/tmp/ara-e2e.db python3 -m server.app

# 2. En otra terminal
cd tests/e2e
npm install
npm test
```

Para otra dirección: `ARA_URL=http://localhost:8421 npm test`.

Para guardar una captura de cada comprobación que falle: `E2E_SHOTS=/ruta/a/carpeta npm test`.

## Contornos KMZ en el mapa (B-2)

Estas dos pruebas **no necesitan la aplicación ni una base de datos**: sirven la
raíz del repositorio en un puerto local y abren `contornos.html`, que usa el
`createMapCanvas` real con el Leaflet incluido y datos ficticios
(`tests/js/fixtures/geometria/contornos.json`).

```bash
cd tests/e2e
npm install
node contornos.mjs              # comprobaciones con clics reales del ratón
node contornos-medicion.mjs     # tiempos y memoria (opcional: archivos de límite)
```

`CHROMIUM=/ruta/a/chrome` usa ese binario en lugar del canal `chrome`.
`CONTORNOS_EVIDENCIA=/ruta` guarda capturas y un resumen JSON.

## Tabla / Mapa

Selector «Tabla / Mapa» de la tabla de empleados con los widgets, el cargador
y el mapa reales: entrada del administrador, conjunto completo más allá de la
página, filtros, contorno activo al tocar un círculo, respuestas atrasadas,
alcance del operador, estados de error y vacío, y alternancia repetida. Datos
ficticios al volumen del piloto (111 terrenos). Levanta y borra su propio
servidor desechable.

```bash
cd tests/e2e && npm ci
node tabla-mapa.mjs                         # MAPA_CAPTURAS=carpeta para capturas
```

## Mapa de las tablas: filtros, leyenda y ficha

Pantalla Mapa de Tabla / Mapa con filtros a la izquierda, leyenda por precio
por m² sobre el mapa y ficha de solo lectura a la derecha: los filtros del mapa
no tocan la consulta ni la página de la tabla, Limpiar/Actualizar y el cambio
de vista, columnas personalizadas de la base de cada terreno (desde una base y
desde la maestra), contorno activo sin X/Y, monedas mezcladas, fondos, teclado,
cajón en pantalla estrecha y alcance del operador. También el espacio del
mapa (#40): una fila delgada arriba, sin franjas ni pie, «Encuadrar todo» junto
al zoom, Tipo de terreno como filtro local y la nota de filtros heredados de la
tabla (archivados incluidos), en escritorio y a 390 px. Levanta y borra su propio
servidor desechable con datos ficticios.

```bash
cd tests/e2e && npm ci
node tabla-mapa-paneles.mjs                 # MAPA_CAPTURAS=carpeta para capturas
```

## Abrir PDF desde la celda de la tabla (#48)

«1 PDF» abre ese PDF guardado en una pestaña nueva con los mismos bytes; con
varios, el contador abre una lista pequeña (también más allá de los cinco
recientes del resumen y con «Cargar más»). Sin PDF, subidas sin terminar,
vencidas o rechazadas no son enlaces; un PDF guardado junto a un reemplazo
vencido sigue abriéndose. Administrador, operador y modo de solo consulta;
teclado sin editor ni cambio de selección; clics repetidos, pestaña bloqueada,
documento y terreno borrados, cambio de vista, recarga y sesión perdida sin
pestañas vacías. «Elegir PDF…», el «Abrir» del detalle y el KMZ siguen igual.
Levanta y borra su propio servidor desechable con datos ficticios.

```bash
cd tests/e2e && npm ci
node tabla-abrir-pdf.mjs                    # ABRIR_CAPTURAS=carpeta para capturas
```

## Subidas PDF ante recargas de la tabla

Una subida de PDF no se interrumpe al recuperar foco o visibilidad, con una
recarga que ya estaba en vuelo, al crear otra fila, con Actualizar, filtros o
páginas; cambiar de vista, cerrar el detalle (botón, Escape o fondo) y cerrar
sesión preguntan antes. Reintentar, cancelar, sesión terminada y otra cuenta,
descarga con los mismos bytes y estados de subidas vencidas con y sin un PDF
guardado. Retiene peticiones con `page.route` para controlar el momento.
Levanta y borra su propio servidor desechable con datos ficticios.

```bash
cd tests/e2e && npm ci
node tabla-subidas.mjs                      # SUBIDAS_CAPTURAS=carpeta para capturas
```

## Elegir PDF/KMZ desde las celdas de la tabla

Botones «Elegir PDF…» y «Elegir KMZ…» de la tabla con los widgets reales:
administrador y operador, asociación a la fila, selección y activación
explícitas del KMZ, reemplazo inválido, selector cancelado, teclado y filas
sin permiso. Levanta y borra su propio servidor desechable.

```bash
cd tests/e2e && npm ci
node tabla-elegir.mjs                       # ELEGIR_CAPTURAS=carpeta para capturas
```

## Tabla de empleados (2A)

Recorridos integrados: servidor real, sesiones reales, Chrome real. Cada
corrida necesita un servidor **nuevo**; `tabla_servidor.py` levanta uno con una
base SQLite temporal y cuentas ficticias, y lo borra al cerrar.

```bash
python3 tests/e2e/tabla_servidor.py --puerto 8433          # terminal 1
cd tests/e2e && npm ci
ARA_URL=http://localhost:8433 node tabla-integrada.mjs [carpeta-de-capturas]
```

Medición local (25,000 terrenos sintéticos, 3,000 en una base, cinco sesiones):

```bash
python3 tests/e2e/tabla_servidor.py --puerto 8434 --registros 25000   # terminal 1
ARA_URL=http://localhost:8434 node tests/e2e/tabla-medicion.mjs [salida.json]
```
