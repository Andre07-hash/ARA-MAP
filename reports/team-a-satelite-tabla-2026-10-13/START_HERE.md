# Satélite en Tabla / Mapa

Base: `c659f07210b961e5fe25e2962f33cc8d12b35495`, rama del piloto.
Alcance confirmado por el propietario: únicamente agregar satélite al mapa de
la tabla maestra y de las tablas del operador. El fallo reportado en el mapa
de una base importada queda pendiente; no se modificó ese recorrido.

## Cambio

`vistaPrevia.js` reutiliza `BasemapSwitcher` y `MapCanvas.setBasemap`.
Ofrece Claro / Satélite / Calles con los mismos proveedores y atribuciones
que el mapa anterior. Claro sigue siendo el fondo inicial. Cambiar el fondo
sólo sustituye las capas de teselas; no cambia selección, filtros, zoom ni
geometría. El fondo elegido se conserva al alternar Tabla / Mapa dentro de
la misma tabla, no tras recargar la página. El botón activo conserva el foco.

## Comprobación local

Chrome real, `server.app` mediante `tests/e2e/tabla_servidor.py`, SQLite y
almacén local desechables; cuentas y datos ficticios. Se comprobó:

- Administrador en Tabla maestra y operador en su base autorizada.
- Imagen satelital real visible y atribución presente.
- Contorno KMZ seleccionado, visible a escala sobre satélite.
- Cambios entre fondos y regreso Tabla → Mapa conservan selección y contorno.
- Satélite sigue seleccionado al volver al mapa.
- Selector activable con Espacio y Enter; el foco sigue en la opción activa.
- Sin errores ni advertencias en la consola durante el recorrido.

Las capturas `administrador.png` y `operador.png` muestran un polígono ficticio.
El fixture KMZ se cargó mediante la API del servidor local, porque la extensión
Chrome no permite seleccionar archivos locales en esta instalación. No se
modificó la configuración de la extensión.

`./verificar.sh`: exit 0, Todo en orden. Python del sistema (297 omitidas),
Python de macOS 3.9.6 y JavaScript correctos.
`node --test tests/js/*.test.mjs`: 212/212.
`node --check tests/e2e/tabla-mapa.mjs` y `git diff --check`: correctos.

Se amplió `tabla-mapa.mjs` para comprobar con ambos roles que los cambios de
fondo conservan contorno, zoom y selección y no generan peticiones de datos,
y que el fondo se conserva al alternar vistas. El script Playwright completo
no se ejecutó en esta sesión: la evidencia de navegador anterior corresponde
al recorrido manual mediante la herramienta de control de Chrome.

No probado en Render ni con Postgres local; no hay cambios de servidor,
esquema, permisos, almacenamiento ni configuración de despliegue.
