# Validación PDF/KMZ — 2026-10-15 (issue #51)

**Veredicto: sin fallos de producto encontrados en lo verificado localmente. La
validación NO queda aprobada en su totalidad:** Safari, Firefox y el entorno
alojado (Render + Neon + Supabase) quedan **NO VERIFICADOS**, y hay cuatro
observaciones de comportamiento (O1–O4) para que el propietario decida. No se
encontró pérdida de datos, acceso ajeno, duplicados ni falsos éxitos en ningún
escenario ejecutado.

## Qué se probó

| Dato | Valor |
|---|---|
| SHA bajo prueba | `b4b6ffe2d9498de013e999223c4cb6d2c86538a9` (`origin/main`, incluye PR #50 y los arreglos de #39/#41) más sólo las pruebas y el reporte de esta rama |
| Sistema | Ubuntu 24.04.5 LTS, Linux 6.18 x86_64, 4 CPU, 16 GB, contenedor desechable |
| Python | 3.13.16 (sistema, con `openpyxl` global ajeno al repo); 3.9.25 limpio (uv), sin paquetes, como piso |
| Entorno «hosted» | venv con `requirements-hosted.txt`: psycopg 3.3.6, storage3 2.32.0, httpx 0.28.1 |
| Postgres | 16.15 local, clúster desechable en `/var/tmp`, base `ara_qa_desechable` vía `ARA_MAP_TEST_DATABASE_URL` |
| Node / Playwright | Node 22.22.0; playwright-core 1.63.0 |
| Navegador | Chromium 141.0.7390.37 (`/opt/pw-browsers/chromium`) |
| No disponible | Safari/WebKit y Firefox (no instalados; no se usó `playwright install`) |

Datos: sólo cuentas ficticias de `tests/e2e/tabla_servidor.py` y
`archivos_servidor.py` y archivos generados. Ningún registro, cuenta ni archivo
de Monica. Ningún proceso tuvo `ARA_MAP_DATABASE_URL`, `DATABASE_URL` ni
variables de Supabase: los arneses las eliminan antes de arrancar el servidor y
sólo escuchan en 127.0.0.1.

### Separación de evidencias

| Tipo | Qué cubre aquí |
|---|---|
| Local, SQLite + disco | Suites Python, navegador y ensayos repetidos |
| Local, Postgres 16 desechable | Suites Python completas, módulo nuevo, ensayos y `recorrido-completo` focalizado |
| SDK con transporte simulado | `test_almacen_supabase`: SDK `storage3` real con transporte falso. **No es Supabase real** |
| Respuestas simuladas | 503 y 429 en el navegador (marcadas «SIMULADO»); el servidor local no produce 429 |
| CI (GitHub Actions) | Python 3.12 + Postgres 16 y JavaScript sobre el commit final del PR |
| Proveedor real / publicado | **Nada.** Guion listo en [guion-alojado.md](guion-alojado.md) |

## Resultados de las suites

| Suite | Comando | Resultado |
|---|---|---|
| Python, sistema (3.13) | `python3 -m unittest discover -s tests -t .` | 1447 pruebas, **1 fallo de entorno** (abajo), 297 omitidas: 237 + 10 sin Postgres, 46 sin `storage3`, 4 sin el lock hosted. Las omitidas **no** cuentan como aprobadas |
| Python, hosted + Postgres | `ARA_MAP_TEST_DATABASE_URL=… venv/bin/python -m unittest discover -s tests -t .` | 1447, **0 omitidas**, 1 fallo (el mismo de entorno). 495 s, RSS máx. 278 MiB |
| Python 3.9 limpio | `/usr/bin/python3` → 3.9.25 sin paquetes (namespace de montaje) | 1447, OK, 297 omitidas (Postgres/SDK, cubiertas por la fila anterior) |
| Módulo nuevo `test_validacion_pdf_kmz` | ver «Pruebas añadidas» | 8/8 (4 SQLite + 4 Postgres), repetido 3 veces |
| JavaScript | `node --test tests/js/*.test.mjs` | 232/232 |
| ruff / mypy | `.venv-dev/bin/ruff check server/ tests/`; `.venv-dev/bin/mypy server/` | sin hallazgos / sin errores en 58 archivos |
| `./verificar.sh --todo` | ver «Verificación final» | ver abajo |

**Fallo de entorno, investigado:** `test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`
falla porque el contenedor trae `openpyxl 3.1.5` en
`/usr/local/lib/python3.13/dist-packages`. La prueba exige un `/usr/bin/python3`
sin paquetes (como el de macOS). Repetida en un entorno limpio —un namespace de
montaje donde `/usr/bin/python3` es CPython 3.9.25 sin paquetes— la suite
completa pasa (`OK`). Es la misma condición en `main`: esta rama no toca
empaquetado. No se borró ni modificó la prueba.

### Navegador (Chromium), servidor y base nuevos por suite

Comando: `reports/validacion-pdf-kmz-2026-10-15/correr-navegador.sh DIR [suite…]`
(confirma puertos y variables leyendo cada script; cada suite levanta su propio
`tabla_servidor.py`/`archivos_servidor.py` desechable).

| Suite | Pasada 1 | Pasadas 2–3 | Tiempo |
|---|---|---|---|
| tabla-elegir | 11/11 | 11/11, 11/11 | 10–13 s |
| tabla-subidas (con los 6 recorridos nuevos) | 20/20 | 20/20, 20/20 | ~95 s |
| tabla-abrir-pdf | 18/18 | 18/18, 18/18 | 23–25 s |
| tabla-archivos | 6/6 | — | 20 s |
| archivos-recorridos | 19/19 | — | 11 s |
| archivos-alcance | 8/8 | — | 195 s |
| tabla-identidad (`--registros 4200`) | 16/16 | — | 35 s |
| tabla-seleccion | 6/6 | — | 6 s |
| tabla-mapa | 18/18 | — | 72 s |
| tabla-mapa-paneles | 14/14 | — | 34 s |
| recorrido-completo (SQLite, todos) | 34/34 | 34/34, 34/34 | ~80 s |
| recorrido-completo (Postgres, focalizado) | 18/18 | — | 26 s |

El recorrido focalizado de Postgres **no** verifica todos los casos del
recorrido completo de SQLite: sólo los 18 que el script selecciona.

## Matriz por escenario

PASÓ = verificado aquí; NO VERIFICADO = no se pudo comprobar. «Sim.» marca
respuestas simuladas con interceptores.

| # | Escenario | Esperado | Observado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 1 | Carga normal desde celda y detalle, admin y operador | Archivo en su terreno/base; descarga con bytes, tamaño y SHA-256 iguales | Cada archivo en su fila; descargas idénticas byte a byte; otras filas sin cambios | PASÓ | `tabla-elegir` (fila B no A, operador), `recorrido-completo` (detalle, «byte por byte idéntico»), `tabla-subidas` (SHA en el navegador), ensayos (SHA-256 de cada versión, 89 por corrida) |
| 2 | PDF único, varios, listado paginado; abrir desde contador, selector y detalle | Documento correcto, sin pestañas vacías ni duplicadas | Una pestaña por apertura; lista más allá de los 5 recientes con «Cargar más»; clics repetidos = una descarga | PASÓ | `tabla-abrir-pdf` 18/18 ×3; `test_l4_listing_is_bounded_paged…` |
| 3 | KMZ uno/varios contornos; reemplazo inválido; contorno sin X/Y | Uno válido se activa; varios exigen elegir; inválido conserva el anterior; sin X/Y se ubica | Igual | PASÓ | `tabla-elegir`, `recorrido-completo` («KMZ con X/Y en blanco…», «reemplazo fallido…»), `test_archivos_http` |
| 4 | Vacíos, corruptos, extensión, nombres especiales, límites | Rechazos controlados; válido al límite se guarda; +1 byte se rechaza | PDF 25 MiB y KMZ 20 MiB válidos completan y descargan iguales; +1 declarado = 400 `tamano_invalido`; +1 real KMZ = 413 `tamano_excedido`; +1 real PDF = 413 del despachador (ver O3); nombre `Avalúo ficticio ñ #n (copia).pdf` intacto | PASÓ | módulo nuevo; ensayo fase `grandes`; `test_input_boundaries…`, `test_declared_and_actual…`, `test_kmz` (ZIP corrupto, cifrado, expansión); JS `validarArchivoLocal`; `archivos-recorridos` («no es PDF») |
| 5 | Selector, foco/pestaña, Actualizar, filtros, páginas, otra fila, Tabla/Mapa, cambio de base, recarga en vuelo | La subida sigue o se pregunta; nunca se pierde en silencio | Sigue con foco, visibilidad, recarga empezada antes del archivo, Actualizar, filtros, páginas, fila nueva y **Tabla/Mapa** (nuevo: cambia sin preguntar y la subida termina en segundo plano); cambio de base y cerrar detalle preguntan | PASÓ | `tabla-subidas` 20/20 ×3 |
| 6 | Retener registrar / enviar / completar; cortes, timeout, respuesta perdida, doble clic, retry, cancelar | Sin duplicados ni falsos éxitos | **Nuevos:** respuesta perdida tras registrar y tras completar → «incierto», «Reintentar» (doble clic) usa la misma clave y versión, un solo adjunto, bytes iguales; envío colgado → «Cancelar» lo cancela en el servidor; 503 sim. → «Reintentar» termina; 429 sim. → sin reintento, sale por cancelar (O1). Doble completar con hilos reales: una respuesta fresca y una repetición/«en curso» | PASÓ, con O1/O2 | `tabla-subidas` (nuevos), módulo nuevo (`double_click` ×3 por backend), ensayos (`doble_completar` 24 por corrida), JS `archivos*.test.mjs` |
| 7 | Recarga/cierre y reinicio del servidor LOCAL | Estado honesto; reintento con el archivo, cancelación o nueva subida | Tras SIGKILL: sesión conservada; subida sin contenido y con contenido se completan; lo completo descarga igual; corte a la mitad de un PUT de 20 MiB → `contenido_temporal_ausente` y reenvío del mismo archivo termina; recargar la página deja la subida «sin terminar» | PASÓ | ensayo fase `reinicio` ×6; `recorrido-completo` («reinicio del servidor…»); `tabla-subidas` («subida vencida…», pestaña que se va) |
| 8 | Vencimientos y leases con reloj controlado | Lo vencido no invalida lo guardado | **Nuevo:** PUT aceptado 1 s antes y rechazado en la igualdad; completar vencido en la igualdad; PDF anterior y contorno activo intactos | PASÓ | módulo nuevo; `test_l3_*`, `test_live_lease_takeover…`, `test_lease_started_before…` |
| 9 | Sesión perdida, cambio de cuenta, permisos retirados, transferencia | Sin acceso ajeno ni respuestas tardías | Revocar/transferir durante PUT y completar → 404 que limpia; otra cuenta en la ventana no recibe nada | PASÓ | `archivos-alcance` 8/8, `recorrido-completo` (R3-B1/B2/A2), `tabla-subidas`, `tabla-identidad`, `test_archivos_http` (404 idénticos) |
| 10 | Borrado real con enlace viejo | 404 real, resumen actualizado, terreno conservado | 404 `not_found` del servidor local; resumen `pdf_total 0`; el terreno sigue | PASÓ | módulo nuevo; `tabla-abrir-pdf` («documento borrado»); ensayos (`borrado_enlace_viejo` 13 por corrida) |
| — | Safari / Firefox | Selector, foco, abrir PDF, popup, cancelar | No instalados | **NO VERIFICADO** | — |
| — | Render + Neon + Supabase | Mismos recorridos con archivos ficticios | Sin destino autorizado | **NO VERIFICADO** | [guion-alojado.md](guion-alojado.md) |

## Ensayos repetidos y concurrentes

Arnés nuevo `tests/e2e/ensayo_archivos.py` (servidor real, HTTP real, sesiones
de cookie aisladas). Cada corrida: 20 ciclos secuenciales; después 2 y 5
sesiones simultáneas (4 ciclos cada una, terrenos compartidos a propósito); un
PDF de 25 MiB y un KMZ de 20 MiB simultáneos con 3 sesiones leyendo; +1 byte;
reinicios con SIGKILL. Al final: listado de cada terreno = conjunto esperado,
cada versión descargada y comparada por SHA-256, ningún objeto temporal y un
objeto final por versión guardada.

| Corrida | BD | Fallos | Versiones verificadas | Temporales / huérfanos | 5 sesiones | PDF+KMZ grandes | completar p50 / máx | RSS pico servidor |
|---|---|---|---|---|---|---|---|---|
| 1–3 | SQLite | 0, 0, 0 | 89 ×3 | 0 / 0 | 13.7–14.1 s | 2.1–2.3 s | 37–42 ms / 1.01–1.31 s | 126–151 MiB |
| 1–3 | Postgres 16 | 0, 0, 0 | 89 ×3 | 0 / 0 | 4.9–5.1 s | 1.4–1.6 s | 62–63 ms / 0.42–0.50 s | 121–162 MiB |
| 1–3, tope 512 MiB* | SQLite | 0, 0, 0 | 51 ×3 | 0 / 0 | 12.0–13.1 s | 2.1–2.2 s | 279–323 ms / 0.79–0.98 s | 126–148 MiB |

\* `prlimit --as=512MiB` con `MALLOC_ARENA_MAX=2`. **Investigado:** sin esa
variable el mismo tope produce `MemoryError` (500 y conexiones cortadas) aunque
el RSS real sólo llega a ~168 MiB: el pico de memoria **virtual** fue 736 MiB por
las arenas de glibc de los hilos (`evidencia/ensayo/as512.json`,
`grandes-sin-limite.json`). Un tope de espacio de direcciones no equivale al
límite de RSS de Render; nada de esto certifica la capacidad de Render ni un
número de usuarios.

Cada corrida contó además: 21 repeticiones de registrar con la misma clave, 24
doble-completar, 11 cancelaciones (completar tardío = 409 `subida_no_pendiente`,
descarga = 404) y 9–12 KMZ «superada» (dos sesiones subiendo KMZ al mismo
terreno: la versión queda guardada y no se activa, como dice el contrato).
Tiempos completos por operación (p50/p95/máx) en `evidencia/ensayo/*.json`.

SQLite con 5 escritores concurrentes es ~3× más lento que Postgres (p95 de
completar 0.78–0.99 s frente a 0.22 s), sin errores ni esperas agotadas. Es la
base local; el sitio usa Postgres.

## Pruebas añadidas

- `tests/test_validacion_pdf_kmz.py` (SQLite y Postgres, corre en CI): archivos
  válidos al límite y +1; vencimiento que no quita lo guardado; borrado del
  único PDF con enlace viejo; doble completar en hilos reales, 3 vueltas.
- `tests/e2e/tabla-subidas.mjs`: 6 recorridos nuevos (respuesta perdida en
  registrar y completar con doble clic, envío colgado cancelado, Tabla/Mapa
  durante la subida, 503 y 429 simulados).
- `tests/e2e/ensayo_archivos.py`: ensayos repetidos/concurrentes, reinicios y
  memoria. `python3 tests/e2e/ensayo_archivos.py --salida informe.json`.
- `reports/validacion-pdf-kmz-2026-10-15/correr-navegador.sh`: corre las suites
  de navegador de la issue, cada una con su servidor desechable.

No se cambió código de producto.

## Observaciones (no bloquean datos ni permisos; decide el propietario)

**O1 — Un 429 en el envío o al completar no ofrece «Reintentar».**
Reproducción: `tabla-subidas.mjs`, «429 SIMULADO en el envío». `subida.js`
(`fallar`, caso `default`) marca reintentable sólo `status >= 500`. La subida
queda «interrumpida», honesta y cancelable; hay que cancelar y elegir el archivo
otra vez. El servidor local no responde 429; un proxy del hosting podría.
Propuesta mínima: tratar 429 como 503 (reintentable, respetando `Retry-After`).

**O2 — Durante «Verificando…» no hay Cancelar ni Reintentar, y el cliente no
tiene plazo propio.** `paso_completar` pone `cancelable: false` y el cliente no
fija tiempo máximo a `fetch`. Si la respuesta de completar nunca llega, la celda
se queda en «Verificando el archivo…» hasta que el navegador corte la conexión
(entonces pasa a «incierto» con «Reintentar», que es seguro porque completar se
repite). Comprobado leyendo el código y con retenciones de segundos; no se
reprodujo una espera indefinida. Propuesta: tras ~2 min sin respuesta, abortar
localmente y pasar a «incierto» (no cancela nada en el servidor).

**O3 — Un PDF de 25 MiB + 1 byte enviado directamente a la API recibe 413 y la
conexión se cierra sin leer el cuerpo;** un cliente que sigue enviando ve
«conexión cortada» en lugar del 413 (ensayo fase `grandes`). La interfaz no
llega a enviarlo: lo rechaza antes de leerlo. Sin impacto en datos.

**O4 — El mensaje dice «25 MB» / «20 MB» pero el límite es 25 MiB / 20 MiB**
(26.2 / 21.0 MB). `validarArchivoLocal` divide entre 1024². Un archivo de
25.5 MB decimales se acepta aunque el texto diga 25 MB. Cosmético.

Información del contrato (no son fallos): `pdf_total` del resumen cuenta
adjuntos vivos, incluidas subidas pendientes; la interfaz distingue cuáles están
guardados (pruebas JS «a PDF counts only with a saved version»). Los archivos
`.parcial-*` de un proceso matado no se limpian solos (documentado en
`server/almacen.py`); en los cortes ensayados no quedó ninguno.

## Límites

- Safari, Firefox y el entorno alojado: NO VERIFICADOS.
- Las pruebas de navegador no corren en CI; su evidencia es de este contenedor.
- El tope de memoria es de espacio de direcciones (no hay cgroups aquí), no RSS.
- Cinco sesiones simultáneas no permiten inferir capacidad ni un máximo de
  usuarios. Ningún SLA ni ausencia total de errores se afirma.

## Verificación final

| Condición | Resultado |
|---|---|
| `./verificar.sh` en un entorno limpio: `/usr/bin/python3` = CPython 3.9.25 sin paquetes (namespace de montaje) | **Todo en orden** — 1455 pruebas OK (301 omitidas: Postgres y SDK), Python 3.9.25 OK, JavaScript OK |
| `./verificar.sh --todo` en el contenedor tal cual | 2 FALLA, ambas el test de packaging por el `openpyxl` global del contenedor (ver arriba); ruff OK, mypy OK, cobertura 95 % (mínimo 80 %) |
| Suite completa con Postgres 16 desechable y `storage3` (venv hosted, 3.13) | 1455 pruebas, **0 omitidas**, 1 fallo: el mismo de packaging (`/usr/bin/python3` del contenedor); 473 s |
| CI de GitHub Actions sobre el commit final | ver el PR |

Las cifras de esta sección incluyen las 8 pruebas nuevas (1447 → 1455).
