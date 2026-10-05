# ARA Map

Mapa interactivo de los terrenos en análisis. Toma los archivos de Excel del
registro (`Base Terrenos MM.AA.xlsx`), los dibuja sobre un mapa de México y
permite guardarlos, compararlos entre meses y filtrarlos para descartar rápido
lo que no vale la pena.

La aplicación local corre en esta Mac. La versión de Vercel usa una base
compartida en Neon Postgres, accesible desde otras computadoras.

## Publicar en Vercel

Enlace: https://ara-map-ivory.vercel.app

Los visitantes pueden explorar, filtrar y exportar. Para importar, guardar mapas,
renombrar o eliminar, pulsa **Iniciar sesión** y usa la contraseña compartida de
`.cloud-access.txt`. Entrega esa contraseña a los colaboradores que deban editar.
La sesión dura 12 horas. **Cerrar sesión** vuelve al modo de consulta.

Todos los editores trabajan sobre los mismos datos, que permanecen guardados
en Neon incluso después de reiniciar o volver a desplegar la app. Recarga la
página para ver cambios de otros usuarios. La Mac puede estar apagada.

La base local y la nube son independientes: se migraron los datos locales una
vez, pero no se sincronizan automáticamente. La versión web admite archivos
Excel o CSV de hasta 4 MB. La local conserva su límite de 25 MB.

Desde esta carpeta, con la cuenta de Vercel conectada:

```bash
npx --yes vercel@59.26.0 deploy --prod --yes
```

**Antes de desplegar una versión que cambia el esquema** (carpetas: esquema 5;
asistente de importación: esquema 6), actualiza primero la base compartida; el
código nuevo consulta tablas y columnas que esta actualización agrega:

```bash
.venv-dev/bin/python scripts/migrate_cloud.py --check   # sólo informa la versión
.venv-dev/bin/python scripts/migrate_cloud.py           # respalda y actualiza
```

Para probarla antes en una base desechable (nunca en producción), indica la
variable que tiene su dirección; así no se lee `.env.local` y, si falta, se
detiene en lugar de usar la base compartida:

```bash
.venv-dev/bin/python scripts/migrate_cloud.py --url-env ARA_MAP_TEST_DATABASE_URL
```

La actualización sólo agrega (tablas, columnas e índices con `IF NOT EXISTS`),
no modifica datos, toma un respaldo antes y puede ejecutarse varias veces sin
efecto. Usa el mismo bloqueo que cada petición, así que no se intercala con una
edición en curso. Después, despliega.

Variables de producción: `DATABASE_URL` (configurada por la integración Neon)
y `ARA_MAP_EDIT_PASSWORD` (secreto de Vercel). La carpeta pública es `web/`.
La contraseña, los archivos de entorno, la base local y sus respaldos se excluyen
del despliegue. Para cambiar la contraseña, actualiza el secreto en Vercel y
vuelve a desplegar; las sesiones anteriores dejarán de ser válidas.

`scripts/setup_cloud.py` inicializa una base vacía con los datos locales y se
niega a sobrescribir datos existentes. Sólo se necesita en la primera migración;
no se ejecuta durante despliegues. Requiere `psycopg[binary]` y `python-dotenv`.
Los respaldos automáticos en nube se guardan en `workspace_backup`, conservando
los diez más recientes. Las operaciones de una sesión se confirman juntas;
los cambios concurrentes se serializan para evitar importaciones intercaladas.

## Cómo abrirlo

Doble clic en **`ARA Map.command`**. Se abre una ventana de terminal y, en unos
segundos, el navegador en `http://localhost:8420`.

Para cerrarlo: `Ctrl+C` en esa ventana, o simplemente ciérrala.

> La primera vez macOS puede pedir permiso: clic derecho sobre el archivo →
> **Abrir** → **Abrir**.

## Qué necesita

**Nada que instalar.** La librería para leer Excel viene incluida en la carpeta
(`vendor/python`), y funciona con el Python que ya trae macOS. No hace falta
pip, ni Node, ni internet.

El lanzador busca una instalación de Python 3.9 o superior; si no encuentra
ninguna te lo dice con instrucciones y **deja la ventana abierta** para que
puedas leerlas.

Para mover la aplicación a otra Mac: copia la carpeta completa. El logotipo vive
en `web/assets/ara-logo.png`, dentro de la misma carpeta, así que viaja con ella.

## Cómo se usa

### Importar una base

**Bases → Importar archivo** (o **Agregar terrenos** en una base). El
asistente de importación hace el resto:

1. **Analiza el archivo solo**: encuentra la tabla, la fila de encabezados, qué
   es cada columna y cómo están escritos los números.
2. **Pregunta sólo lo necesario**, con los nombres y valores reales del archivo:
   por ejemplo «¿Qué representa la columna «Valor»?» o «¿Cuál tabla quieres
   importar?». Un archivo claro no pregunta nada.
3. **Muestra la vista previa**: cuántos terrenos, cuántos en el mapa, cuántos
   con precio, un mapa pequeño, las filas interpretadas junto a sus valores
   originales, las que no se importan y por qué.
4. **Importas** cuando estés de acuerdo. Nada se guarda antes.

Archivos admitidos: **Excel (`.xlsx`, `.xlsm`) y CSV (`.csv`)**. Si trabajas
en Numbers, expórtalo a Excel o a CSV UTF-8 (**Archivo → Exportar a**).

**Qué entiende sin preguntar**

- Los encabezados de ARA en cualquier orden, sus variantes habituales
  (*Nombre comercial*, *Entidad*, *Valor de venta MXN*, *Área del predio (ha)*,
  *Latitud/Longitud*…) y filas de título arriba de los encabezados.
- Una **segunda hoja** de notas se ignora; si hay dos tablas de terrenos,
  pregunta cuál.
- Filas de **totales**, **notas al pie** y encabezados repetidos se listan como
  excluidas; nunca se vuelven terrenos ni desaparecen. Un totales se reconoce
  por lo que hace la fila —no ubica ni identifica nada y sus cifras son la suma
  de las demás—, no por su nombre: «Total FICTICIO Encino», con su precio y sus
  coordenadas, es un terreno. Una nota al pie tiene que ser además lo único
  escrito en su línea. Cualquier decisión se puede revertir en la vista previa.
- La **fila de encabezados** se busca en las primeras filas; si ninguna parece
  un encabezado (una página de notas antes de la tabla), sigue buscando en vez
  de quedarse con la primera.
- El **formato de números** se deduce cuando los valores lo dejan claro (una
  latitud `20,653` sólo tiene sentido con coma decimal). Si no, pregunta
  mostrando las dos lecturas: «¿«1,250» significa 1250 o 1.25?». Los números
  que Excel ya guarda como número nunca cambian.

**Salvaguardas**

- En los archivos de ARA **X es la latitud e Y la longitud** (al revés de la
  convención de GIS). Si los valores de X/Y dicen lo contrario, pregunta; nunca
  los intercambia en silencio. *Norte/Este* en metros (UTM) se conservan como
  datos adicionales: esta versión no convierte coordenadas.
- **Precio total y precio por m²** son datos distintos, igual que **m² y
  hectáreas**; nada se convierte ni se calcula. Un precio que falta queda sin
  precio, no en cero.
- Los precios se muestran en **pesos (MXN)**. Una columna marcada en otra
  moneda —en el encabezado, en cualquiera de sus celdas o en el **formato de
  celda de Excel** (`"USD "#,##0.00`, `[$€-2]#,##0.00`): `US$`, `USD`, dólares,
  `EUR`/`€`, `CAD`, `£`…— se conserva como dato adicional con su importe
  original y no se puede elegir como precio, ni a mano ni desde un formato
  guardado; no se convierte. Basta una celda. Un `$` solo, `MXN` o «pesos»
  siguen siendo pesos.
- Dos columnas que parecen el mismo dato (dos «Precio») se preguntan; las
  columnas sin encabezado o repetidas se distinguen por su posición.
- Sólo el **nombre del terreno** es obligatorio. Sin coordenadas un terreno se
  guarda pero no se dibuja; sin precio se guarda sin precio.

**Corregir y recordar**

- **Corregir interpretación** (opcional, en la vista previa) permite elegir otra
  tabla, otra fila de encabezados, el formato de números y qué es cada columna,
  incluidos «Conservar como dato adicional» y «No importar». Si el encabezado
  está más abajo de las filas que lista, se escribe **el número de fila que se
  ve en el archivo** y ARA lo traduce (las filas en blanco no descuadran la
  cuenta). Cada cambio vuelve a generar la vista previa.
- En la vista previa, cada terreno tiene **No importar** y cada fila apartada
  **Sí es un terreno: importarla**. La decisión viaja con la importación hasta
  que guardas.
- **Recordar este formato** viene marcado: al importar, el formato se guarda y
  la próxima vez que llegue un archivo con los mismos encabezados (aunque estén
  en otro orden) se aplica solo. Guarda encabezados y decisiones, **nunca
  valores**. Si el archivo tiene **columnas con el mismo nombre** (dos
  «Precio») a las que el formato dio significados distintos, pregunta cuál es
  cuál: el orden no prueba que no se hayan intercambiado. Si cancelas, no se guarda nada. **Formatos de importación** (en
  Bases) permite renombrarlos u olvidarlos sin tocar datos ya importados.

**CSV:** guárdalo como **CSV UTF-8**; otras codificaciones se rechazan con un
mensaje. El separador (coma, punto y coma o tabulación) se detecta solo, se respeta la línea
`sep=` de Excel y cada fila de datos debe tener las columnas del encabezado; si
no, se indica la línea en vez de recorrer los datos. En **Afectaciones %**,
`10%` se guarda como `0.10`. Hay una plantilla con datos ficticios en
[`web/assets/plantilla-terrenos.csv`](web/assets/plantilla-terrenos.csv).

El límite de tamaño es 25 MB en la versión local y 4 MB en la versión web.
Los números de fila de la vista previa son los del archivo (en un CSV, su
línea). Los datos se guardan **tal como vienen**: si un precio está mal, lo
verás señalado, pero el número que se guarda es el del archivo.

**Asistencia automática.** Si el administrador la configura (ver
*Asistencia automática para administradores* más abajo), el asistente la usa
solo cuando la detección no alcanza: nadie la activa ni elige nada al importar.
Recibe sólo encabezados, un resumen y hasta 3 valores cortos de las columnas no
reconocidas —nunca el archivo, datos de contacto ni notas— y su propuesta se
comprueba contra los valores del archivo antes de usarse. Sin ella, el asistente
funciona igual con detección y preguntas.

### Carpetas

**Bases** y **Mapas guardados** tienen cada una sus propias carpetas, para
ordenar por cliente, región, proyecto o periodo. Una carpeta de bases sólo
contiene bases; una de mapas, mapas simples y comparaciones. No hay subcarpetas.

- **Nueva carpeta** crea una. A la izquierda (o en el selector «Carpeta» en
  pantallas angostas) están **Todas las bases** / **Todos los mapas**,
  **Sin carpeta** y tus carpetas, cada una con cuántos elementos tiene; una
  comparación cuenta como un mapa.
- **Mover a carpeta…** en cada tarjeta cambia su carpeta o la devuelve a
  **Sin carpeta**. Mover sólo cambia dónde aparece: no toca el nombre, los
  terrenos, la foto guardada de un mapa, su vista guardada ni su fecha de
  actualización. Mover una base no mueve los mapas hechos con ella.
- Al importar una base o crear un mapa eliges su **Carpeta**. Por defecto es la
  carpeta abierta (al importar o comparar desde ella) o **Sin carpeta**.
  Agregar terrenos a una base la deja donde está.
- **Eliminar carpeta** no elimina nada de lo que contiene: sus bases o mapas
  pasan a **Sin carpeta**. Eliminar una base o un mapa deja su carpeta, aunque
  quede vacía.
- **Nueva comparación** ofrece los mapas y las bases de todas las carpetas, sin
  importar cuál esté abierta.

Las carpetas se guardan en la base de datos (la local y la compartida, cada una
con las suyas), no en el navegador. Quien sólo consulta puede recorrerlas pero
no cambiarlas.

### Agregar terrenos a una base existente

**Bases → Agregar terrenos** sobre la base que quieras. Compara lo que traes
contra lo que ya está y te dice qué es nuevo, qué está repetido y qué cambió.

La comparación revisa **todos los campos**, no sólo el precio: dirección,
superficie, afectaciones, precios y coordenadas. Para cada terreno que cambió te
muestra el **valor guardado y el del archivo**, lado a lado, y eliges cuál
conservar. Cuando el archivo sólo **completa** datos que faltaban (por ejemplo,
agrega las coordenadas de un terreno que no las tenía), la opción de usar el
dato nuevo viene marcada por defecto.

### Ver y filtrar

En **Mapa**: el color es el precio por m² y el círculo cambia de significado
según el acercamiento.

**Doble clic en un terreno** (o doble toque en pantalla táctil) lo centra y
acerca el mapa justo hasta que su círculo cubre la superficie real. Cada terreno
necesita un acercamiento distinto, según su tamaño y su latitud, así que el
cálculo es por terreno. El botón **Ver a escala** del panel de detalle hace lo
mismo desde el teclado.

Si un terreno es tan pequeño que necesitaría más acercamiento del que permite el
mapa, se acerca hasta el máximo y te lo dice, en vez de afirmar que ya está a
escala. El doble clic sobre el mapa vacío sigue acercando como siempre.

- **Alejado**, el círculo es un **símbolo**, del mismo tamaño para todos los
  terrenos: dice dónde está cada uno y, por el color, cuánto cuesta el m². El
  tamaño no significa nada todavía. Para comparar superficies, usa la **Tabla**.
- **Al acercarte**, en cuanto la escala lo permite, el círculo pasa a cubrir la
  **superficie real** del terreno sobre el mapa, centrado en su coordenada.
  Cambia de aspecto: se vuelve translúcido y con contorno de color, para que
  puedas ver el terreno debajo.

La leyenda dice en todo momento en cuál de los dos estados estás.

**Importante:** el archivo no trae los linderos, así que la forma dibujada es un
**círculo perfecto**, no el contorno real del predio. La **ubicación** y la
**superficie** sí son las del registro; la forma es una aproximación.

Haz clic en un terreno para ver toda su información.

El panel de la izquierda filtra por estado, municipio, superficie y precio.
Los filtros aplican a la vez al mapa, a la lista y a la tabla.

Con **Tabla** ves los mismos terrenos ordenables por columna — suele ser más
rápido para ordenar por `$/m²` que buscarlos en el mapa.

### Terrenos fuera del mapa

Nada se coloca en el mapa a la adivina. El panel **Fuera del mapa**, abajo a la
derecha, reúne los terrenos que no se pueden dibujar y distingue **dos problemas
distintos**:

- **Sin coordenadas:** el archivo no trae X ni Y. Busca el punto, copia las
  coordenadas al Excel y vuelve a importar.
- **Coordenadas imposibles** (marcadas en rojo con la etiqueta `X/Y`): el
  archivo sí trae valores, pero caen fuera de México o tienen X y Y invertidas.
  **No se dibujan** hasta corregirlas, y se muestran tal como vienen: la
  aplicación nunca las intercambia ni las corrige por su cuenta.

Recuerda que en estos archivos **X es la latitud** y **Y es la longitud**.

### Guardar mapas: son una foto, no un espejo

**Guardar como mapa** guarda una **copia congelada** de los terrenos tal como
están en ese momento. Si después corriges la base, el mapa guardado **no
cambia**: sigue mostrando lo que viste al guardarlo. Eso es lo que lo hace útil
para hablar con un cliente o para comparar meses.

- **Actualizar** vuelve a copiar los datos desde las bases de origen. Te pide
  confirmación, porque reemplaza lo que estaba guardado.
- **Guardar vista** guarda además los filtros, el mapa base, el encuadre y qué
  capas están visibles, para que el mapa se abra tal como lo dejaste.
- Si **borras una base**, los mapas guardados que la usaban **siguen
  funcionando**: conservan sus terrenos y marcan la capa con un aviso.

### Renombrar una base

Al renombrar una base desde **Bases → Renombrar**, el nombre nuevo aparece de
inmediato en los mapas guardados que la usan: en sus capas, en la leyenda, en
los detalles de cada terreno y en las hojas del Excel que exportes.

- Si el mapa guardado **conservaba el nombre de la base** como título, el título
  también cambia.
- Si le pusiste un **título propio** («Opciones para cliente López»), ese título
  se respeta y sólo cambia la etiqueta de la base.
- En una comparación con **dos versiones de la misma base**, las dos se
  actualizan y siguen distinguiéndose por el mapa del que vienen.
- Una capa cuya base fue **borrada** conserva su último nombre y sus datos, y
  nunca se vuelve a enlazar con otra base que se llame igual.

Renombrar es sólo un cambio de nombre: no toca los terrenos congelados ni la
fecha de la última actualización del mapa.

### Comparar mapas

**Mapas guardados → Nueva comparación** combina **dos o más mapas guardados** en
uno nuevo. Antes de guardar te muestra exactamente qué capas va a incluir.

Si combinas **dos versiones guardadas de la misma base** (por ejemplo, la foto
de agosto y la de septiembre de un mismo archivo), **se conservan las dos** y se
distinguen por el mapa del que vienen. Sólo se omite una capa cuando su
contenido es **idéntico** al de otra, y te dice con cuál.

También puedes comparar **bases** directamente, con la pestaña del mismo
diálogo.

En una comparación:

- Cada terreno se dibuja del color de su capa, y cuando está en varias capas los
  círculos aparecen **concéntricos**.
- La **tabla** añade una columna **Base** (con su color) y una columna
  **Cambio**, que dice si el terreno es **Nuevo**, **Eliminado**, **Cambiado**
  (nombrando qué campos cambiaron) o **Sin cambio**, comparado siempre contra la
  primera capa.
- Se consideran cambios el **precio, el precio por m², la superficie, las
  afectaciones, la dirección y la ubicación**: un terreno que se movió aparece
  como *Cambiado · Ubicación*, aunque sus cifras sigan iguales.
- Con **tres o más capas**, un terreno que desaparece indica **en cuáles** ya no
  está.
- La exportación de una comparación genera **una hoja de Excel por cada base**,
  en el orden de las capas y con el nombre de cada una. Así ninguna fila queda
  mezclada ni parece duplicada.

Hasta **4 capas** los colores se distinguen con seguridad. De la quinta en
adelante se permiten (hasta 8), pero se dibujan con **borde punteado** y el
diálogo te avisa, porque el color por sí solo deja de ser confiable.

## Revisión de datos

Al importar se revisa cada fila y se marca lo que parece mal. Nunca bloquea la
importación; solo avisa.

| Aviso | Qué significa |
|---|---|
| Sin coordenadas | No trae X ni Y: no se puede dibujar |
| X y Y invertidas | La latitud y la longitud parecen cambiadas; no se dibuja |
| Coordenadas fuera de México | El punto cae fuera del país; no se dibuja |
| Precio inconsistente | El precio no cuadra con `$/m² × superficie` |
| Precio en cero | El precio está en 0; probablemente falta capturarlo |
| Superficie inconsistente | Las hectáreas no corresponden a los m² |
| Valor no numérico | Texto como `SD` en una columna de números |
| Campo faltante | Falta Estado o Municipio |
| Afectación alta | Más de la mitad del terreno está afectado |
| Posible duplicado | Mismo nombre, estado y municipio que otra fila |

### El Excel de una comparación

Una comparación se exporta con **una hoja por base**, cada una con las mismas 13
columnas del archivo original y con los datos congelados de esa capa. Si una
capa quedó oculta o sin resultados por los filtros, **su hoja aparece igual pero
sólo con los encabezados**: nunca se mezclan sus filas en otra hoja.

Los nombres de hoja se adaptan a lo que Excel permite (máximo 31 caracteres, sin
`: \ / ? * [ ]`); si dos quedan iguales se numeran. El nombre guardado de la base
no se modifica, sólo la etiqueta de la hoja.

**Límite conocido:** al importar un Excel, la aplicación lee la hoja «Registro Análisis»
o la primera del archivo. Las exportaciones siguen siendo Excel. Un Excel de comparación sirve para revisar y compartir,
pero **no recrea las dos bases si lo vuelves a importar**: para eso, guarda la
hoja que te interese como archivo aparte (en Excel: clic derecho en la pestaña →
Mover o copiar → Crear una copia en un libro nuevo) e impórtala.

## Asistencia automática para administradores

Apagada mientras no se configure; el asistente funciona completo sin ella. Se
configura con variables de entorno del servidor (en Vercel, como secretos;
localmente, en el entorno de la app). Nunca en el navegador.

| Variable | Qué es |
|---|---|
| `ARA_MAP_IA_PROVEEDOR` | `openai` (o `simulado`, sólo para demostraciones locales) |
| `ARA_MAP_IA_MODELO` | Modelo elegido tras evaluarlo con archivos reales |
| `ARA_MAP_IA_CLAVE` (u `OPENAI_API_KEY`) | Clave del proveedor |
| `ARA_MAP_IA_LIMITE_MENSUAL_USD` | Límite de gasto mensual; sin él no se llama al proveedor |
| `ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK`, `ARA_MAP_IA_COSTO_SALIDA_USD_MTOK` | Precio por millón de tokens, para aplicar el límite |
| `ARA_MAP_IA_TIEMPO_S` | Espera máxima por consulta (20 s) |
| `ARA_MAP_IA_MUESTRAS` | Valores de ejemplo por columna (3; `0` = sólo encabezados y resúmenes) |
| `ARA_MAP_IA_MAX_POR_HORA` | Consultas por hora (30) |

Se hace como máximo una consulta por tabla analizada (dos por importación). Antes
de cada consulta se reserva su **costo máximo posible** —no un estimado: los
bytes de toda la petición acotan sus tokens de entrada y `ARA_MAP_IA_MAX_SALIDA`
los de salida— y si no cabe en lo que queda del mes, no se consulta. Después se
registra el uso real si el proveedor lo informa correctamente; si falta o es
inválido, se cobra la reserva completa. Todo queda en `uso_ia` sin guardar
encabezados, muestras ni contenido. Si falta configuración, se agota el
presupuesto o el proveedor falla, el asistente sigue con detección y preguntas.

## Dónde viven los datos

Todo está en un solo archivo: **`datos/ara_map.db`**, incluidas las copias
congeladas de cada mapa guardado.

Para respaldar, copia ese archivo. Para mover la aplicación a otra Mac, copia la
carpeta completa. Antes de cada importación o borrado se guarda una copia
automática en `datos/respaldos/` (se conservan las 10 más recientes).

Cuando una versión nueva cambia el formato del archivo (la de carpetas, por
ejemplo), la primera vez que se abre lo actualiza sola y guarda antes una copia
del archivo anterior en esa misma carpeta. Todo lo existente queda en
**Sin carpeta**.

## Notas

- Los precios se muestran en pesos (MXN).
- En el archivo, la columna **X es la latitud** y la **Y es la longitud**
  (al revés de lo habitual en mapas). La aplicación ya lo toma en cuenta.
- La columna `ID` del Excel es el número de fila de ese archivo, no un
  identificador estable: no sirve para relacionar un terreno entre meses. La
  aplicación usa nombre + estado + municipio + superficie para eso.

## Para desarrollo

```bash
./verificar.sh                                 # todas las comprobaciones
./verificar.sh --todo                          # añade linter, tipos y cobertura
python3 -m server.app                          # levantar sin doble clic
ARA_MAP_DB=/otra/ruta.db python3 -m server.app # usar otra base de datos
```

`verificar.sh` corre la suite con el Python del sistema y también con el que
trae macOS (`/usr/bin/python3`), que es la comprobación real de que la
aplicación funciona en una Mac sin nada instalado.

Las pruebas de navegador están en `tests/e2e/` y son opcionales.

La base de datos se migra sola al abrirla, y **antes de cualquier migración se
guarda una copia** en `datos/respaldos/`. Los mapas guardados con la versión
anterior se convierten en copias congeladas durante esa migración.
