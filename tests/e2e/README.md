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
guardado. También respuestas perdidas después de que el servidor
registró o guardó (con doble clic en «Reintentar»), un envío que no responde,
Tabla / Mapa durante la subida y 503/429 simulados. Retiene peticiones con `page.route` para controlar el momento.
Levanta y borra su propio servidor desechable con datos ficticios.

```bash
cd tests/e2e && npm ci
node tabla-subidas.mjs                      # SUBIDAS_CAPTURAS=carpeta para capturas
```

## Ensayos repetidos y concurrentes de archivos (#51)

Sin navegador: el servidor real sobre una carpeta desechable, HTTP real y una
sesión por cuenta ficticia. 20 ciclos con PDF y KMZ pequeños, 2 y 5 sesiones a la
vez, un PDF de 25 MiB y un KMZ de 20 MiB simultáneos y un byte de más, y
reinicios con SIGKILL. Compara cada archivo por SHA-256, el listado de cada
terreno con lo esperado y el almacén (sin temporales). Escribe tiempos, fallos
y memoria del servidor.

```bash
python3 tests/e2e/ensayo_archivos.py --salida /tmp/ensayo.json
MALLOC_ARENA_MAX=2 python3 tests/e2e/ensayo_archivos.py --fases grandes,sesiones --limite-memoria-mb 512
```

## Elegir PDF/KMZ desde las celdas de la tabla

Botones «Elegir PDF…» y «Elegir KMZ o KML…» de la tabla con los widgets reales:
administrador y operador, asociación a la fila, selección y activación
explícitas del KMZ, reemplazo inválido, selector cancelado, teclado y filas
sin permiso. Levanta y borra su propio servidor desechable.

```bash
cd tests/e2e && npm ci
node tabla-elegir.mjs                       # ELEGIR_CAPTURAS=carpeta para capturas
```

## Posición de la tabla al terminar una subida

45 filas en una ventana de 1100 × 650 px, con desplazamiento real en las dos
direcciones. Mide en píxeles el lienzo de la tabla y la página. Comprueba que
no se mueven al terminar un PDF elegido lejos del inicio con el foco que vuelve
del selector, que un KML retenido mientras la persona se desplaza termina en su
posición nueva, que una subida sin revalidación no recarga la página y que un
KMZ subido desde el detalle (operador) no mueve nada al cerrarlo, con el foco
de vuelta en la fila y las flechas funcionando. Levanta y borra su propio
servidor desechable.

```bash
cd tests/e2e && npm ci
node tabla-posicion.mjs                     # POSICION_CAPTURAS=carpeta para capturas
```

## KMZ y KML en la misma columna

KML directo en la columna «KMZ / KML», en tabla y detalle: contorno único
activado y dibujado en el mapa, KML sin contorno y `.kml` que en realidad es un
KMZ conservan el contorno anterior, KMZ que reemplaza a un KML en el mismo
historial, varios contornos con elección y activación explícitas (operador),
subida desde el detalle ante la recarga por foco, descarga del original y, como
regresión, apertura de un PDF desde su contador. Levanta y borra su propio
servidor desechable.

```bash
cd tests/e2e && npm ci
node tabla-kml.mjs                          # KML_CAPTURAS=carpeta para capturas
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
