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
