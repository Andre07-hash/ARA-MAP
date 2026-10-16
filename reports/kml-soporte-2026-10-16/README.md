# Soporte de KML en la columna de contornos — 2026-10-16

Base: `origin/main` en `d14c608` (PR #52 fusionado). Rama
`claude/cool-brahmagupta-yp8g3p`. Sin migración, dependencia nueva ni cambio
de infraestructura.

## Qué cambia

- La columna se llama **KMZ / KML** y su botón **Elegir KMZ o KML…**, en tabla
  y detalle. El selector acepta `.kmz,.kml` (también en mayúsculas).
- Un KML usa el mismo lector, las mismas validaciones y la misma selección y
  activación que el KML dentro de un KMZ.
- Se guardan y descargan los bytes, el nombre y el formato originales. No se
  convierte ni se recomprime nada.
- Límites: KML 16 MiB (el mismo que el KML dentro de un KMZ), KMZ 20 MiB, PDF
  25 MiB, tanto en el navegador como en el servidor (al declarar, al escribir y
  al leer).
- Los mensajes dicen KML o KMZ según el archivo real. Cuando no se conoce el
  nombre, como en la subida pendiente de otra cuenta, dicen «archivo de contorno».

## Cómo se distinguen los formatos

Hay una sola ranura (`core:kmz`, tipo `kmz`) con su historial. No se renombró
nada interno.

| Momento | Qué decide el formato |
|---|---|
| Subir (`iniciar`, `contenido`) | La extensión del nombre: `.kml` es KML; cualquier otro nombre es KMZ, como antes. De ahí sale el límite. |
| Completar | Se verifican los bytes contra el formato del nombre. Un KMZ debe empezar con `PK\x03\x04`. Un KML no puede ser un ZIP y debe empezar con `<`, tras un BOM y espacios opcionales. Si no coinciden, la versión queda `fallido` con `firma_invalida` y el contorno activo no cambia. Si coinciden, se guarda el MIME en `tipo_detectado`. |
| Procesar | `procesar_contorno` elige por contenido: un ZIP va a `procesar_kmz` y lo demás a `procesar_kml`. |
| Reprocesar y descargar | `tipo_detectado` de la versión: `application/vnd.google-earth.kml+xml` o `application/vnd.google-earth.kmz`. |

Las versiones anteriores tienen `tipo_detectado` de KMZ y siguen leyéndose como
KMZ, aunque su nombre cambie. `procesar_kmz` sigue rechazando un KML suelto
(`KMZ_NO_ES_ZIP`). La recuperación de archivos copia bytes por clave con el
límite del tipo `kmz` (20 MiB), que cubre un KML. El analizador conserva
`server.kmz/v1`.

## Pruebas

| Comando | Resultado |
|---|---|
| `python3 -m unittest discover -s tests -t .` (3.13) | 1489 pruebas. Falla `test_packaging.CleanMachine` porque este contenedor trae openpyxl en `/usr/local`. Falla igual en `origin/main` y no tiene relación con el cambio. |
| Misma suite con CPython 3.9.25 | 1489 pruebas. Sólo falla la misma prueba ambiental, que revisa el `python3` del sistema |
| `ARA_MAP_TEST_DATABASE_URL=<Postgres 16 local desechable> python -m unittest tests.test_archivos tests.test_archivos_http` | 177 OK, sin omisiones |
| `node --test tests/js/*.test.mjs` | 236 OK |
| `ruff check server/ tests/`, `mypy server/` | Limpios |
| `node tests/e2e/tabla-kml.mjs` (Chromium) | 9/9 |
| `node tabla-elegir.mjs`, `node tabla-abrir-pdf.mjs`, `tabla-integrada.mjs` | En verde (regresión de textos y del flujo compartido) |

Pruebas nuevas: `tests/test_kml.py` (lector), `KmlChecks` en
`tests/test_archivos.py` (servicio, en SQLite y Postgres), dos pruebas HTTP en
`tests/test_archivos_http.py`, casos en `tests/js/archivos.test.mjs` y
`tests/e2e/tabla-kml.mjs`.

## Límites y lo no verificado

- Sólo se probó el navegador con Chromium. Este contenedor no tiene Firefox ni
  Safari, así que el selector no se verificó en esos navegadores.
- En este Chromium headless, cualquier nombre de descarga con caracteres no
  ASCII aparece como «download»; también pasa con el PDF de prueba existente.
  Por eso la prueba revisa el atributo `download` del enlace y los bytes.
- No se probó contra el sitio publicado. No se desplegó nada ni se tocaron Render, Neon,
  Supabase, cuentas o datos reales.
- Un KML con imágenes, modelos, rutas o enlaces de red sigue las reglas
  actuales: se ignora lo que no es contorno y no se descarga nada externo.

## Corrección tras la revisión del supervisor (SHA 0d795040)

**Problema.** `_verify_final` decidía si un `.kml` era XML con sólo los
primeros 256 bytes. Un KML válido con 256 o más bytes de espacio inicial
quedaba `fallido` / `firma_invalida`, aunque `procesar_kml` lo aceptaba y el
mismo documento dentro de un KMZ se activaba.

**Reproducción (ficticia).** Se toma `poligono_simple.kml`, se le quita la
declaración XML y se le anteponen 256 espacios; luego se sube como `.kml` y se
completa. Con 255 espacios pasaba y con 256 fallaba.

**Corrección.** La comprobación revisa el documento completo, que ya está leído
en memoria dentro del límite de 16 MiB. Salta el BOM y luego cualquier espacio
XML, incluidos los bytes cero de UTF-16, y exige `<`. No hay un prefijo fijo
nuevo, ni copias adicionales, ni un segundo parseo. Los 8 bytes de cabecera se
usan sólo para las firmas de PDF y ZIP, como en `main`. Se mantienen el límite,
las protecciones XML, la comprobación de formato y la conservación del contorno
anterior.

**Regresión.** `test_kml_leading_space_bom_and_encoding_never_hit_a_fixed_prefix`,
en el servicio, sobre SQLite y Postgres. Sube y completa:

- documentos con 255, 256 y 64 KiB de espacios;
- un documento con unos 280 KB de saltos de línea;
- BOM UTF-8 con espacios, y UTF-16 LE y BE con BOM y espacios;
- el mismo documento dentro de un KMZ.

También comprueba que espacios seguidos de texto, sólo espacios o espacios con
un PDF siguen dando `firma_invalida` y conservan el contorno activo.

**Textos.** Las confirmaciones de borrado de terrenos (`Tabla.js`,
`dialogos.js`) dicen ahora «sus archivos adjuntos (PDF, KMZ y KML)». La
operación no cambia.
