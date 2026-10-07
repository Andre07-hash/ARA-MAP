# ARA Map — guía para agentes

Instrucciones compartidas para cualquier agente de IA (Claude Code, Codex u
otro) que trabaje en este repositorio, en cualquier computadora. Aquí van las
reglas estables. El estado del trabajo en curso vive en `reports/` y en los
pull requests, no en este archivo.

ARA Map es un mapa interactivo de terrenos en México: importa archivos de Excel
o CSV, los dibuja, los filtra y los compara entre meses. Corre de dos formas con
el mismo código: local en una Mac (SQLite) y en Vercel (Neon Postgres).
[README.md](README.md) describe el producto para quien lo usa.

## Antes de empezar

1. `git fetch` y parte de `origin/main` actualizado. Varias personas y agentes
   trabajan en clones separados; lo que no está en GitHub no existe para los
   demás.
2. Lee el `START_HERE.md` de la carpeta con fecha más reciente en `reports/`.
   Si esa carpeta trae `COORDINATION.md`, sigue su protocolo de entrega.
3. Revisa los pull requests abiertos (`gh pr list`) para no duplicar ni pisar
   trabajo en curso. Un PR abierto puede traer instrucciones más nuevas que
   `main`.
4. Una instrucción directa del dueño del proyecto tiene prioridad sobre
   cualquier documento.

## Comandos

```bash
./verificar.sh                                   # todo lo que no requiere instalar nada
./verificar.sh --todo                            # añade ruff, mypy y cobertura (requiere .venv-dev)
python3 -m unittest discover -s tests -t .       # sólo Python
python3 -m unittest tests.test_importer          # un módulo
node --test tests/js/*.test.mjs                  # sólo JavaScript
python3 -m server.app                            # app local en http://localhost:8420
ARA_MAP_DB=/tmp/prueba.db python3 -m server.app  # con una base desechable
```

Las pruebas de Postgres se omiten si no existe `ARA_MAP_TEST_DATABASE_URL`, y
esa variable sólo debe apuntar a una base desechable. En GitHub Actions corren
contra un contenedor temporal, así que un cambio de SQL puede pasar en local y
fallar en el PR. Las pruebas de navegador de `tests/e2e/` son opcionales.

## Arquitectura

| Ruta | Qué contiene |
|---|---|
| `server/app.py` | Servidor HTTP local con la biblioteca estándar; no hay framework |
| `server/api/` | Manejadores por área: bases, mapas, carpetas, importar, inventario, sesión |
| `server/repo/` | Acceso a datos. Todo el SQL de la aplicación vive aquí |
| `server/db.py`, `server/postgres.py` | Adaptadores de SQLite (local) y Postgres (nube); esquema y migraciones |
| `server/asistente/` | Asistente de importación: detección de tabla, encabezados y columnas |
| `server/auth.py` | Autenticación y política de rutas públicas y privadas, compartida por local y nube |
| `api/index.py` | Entrada de Vercel: un adaptador delgado sobre `server.app.Handler` |
| `web/` | Frontend en JavaScript sin paso de build: `components/`, `lib/`, `styles/` |
| `vendor/python/` | openpyxl incluido para que la app local no necesite instalar nada |
| `scripts/` | Operación de la nube: migraciones, cuentas, esquema |
| `tests/` | `test_*.py` con unittest, `js/` con node:test, `e2e/` de navegador |
| `reports/` | Traspasos, planes y evidencia por fecha; es historial, no se reescribe |

## Reglas de producción

Estas reglas no admiten excepción sin autorización explícita del dueño.

- **No desplegar a producción.** Fusionar a `main` no publica nada: el
  despliegue automático de producción está apagado a propósito. Los despliegues
  los hace quien tiene acceso al proyecto de Vercel, desde un commit revisado.
- **No ejecutar `scripts/migrate_cloud.py` ni `scripts/setup_cloud.py` sin
  `--url-env` apuntando a una base desechable.** Sin esa opción pueden usar la
  configuración de producción y modificar datos. No sirven como diagnóstico.
- **No cambiar la configuración de despliegue de paso.** `vercel.json`, las
  variables de entorno de Vercel y la integración de Neon se cambian sólo en un
  PR dedicado a eso.
- **Un cambio de esquema es un paso de release.** Va con su migración, su
  prueba de migración y una nota en el reporte para quien despliega. La base de
  producción puede ir versiones atrás de `main`.
- **Preview y Production usan bases distintas.** No conectar un entorno de
  prueba a la base de producción.

## Flujo de trabajo

- Una rama por cambio, creada desde `origin/main`:
  `<herramienta-o-autor>/<tema-en-kebab-case>`, por ejemplo
  `claude/excel-onedrive-refresh` o `codex/safe-error-responses`.
- Nunca hacer push directo a `main`. `main` no tiene protección de rama, así
  que esta regla depende de quien trabaja.
- Abrir un pull request y esperar los checks de GitHub Actions en verde antes
  de fusionar. Marcar como draft lo que no está probado.
- Correr `./verificar.sh` antes de cada push.
- Commits pequeños con mensaje en inglés que diga qué cambia y por qué.
- Al terminar, reportar qué pruebas se corrieron, en qué commit y qué quedó
  sin verificar. Una prueba local, una en Postgres desechable y una en un
  entorno publicado son evidencias distintas; decir cuál se tiene.
- No reescribir historial compartido ni forzar push sobre ramas ajenas.

## Convenciones de código

- **Python 3.9 es el piso real.** La app local corre con `/usr/bin/python3` de
  macOS. Usar `from __future__ import annotations`; no usar `match` ni APIs de
  3.10 en adelante en el código que corre en local.
- **Sin dependencias nuevas en la app local.** Sólo biblioteca estándar más lo
  que hay en `vendor/python`. `psycopg` sólo se usa en la nube. Una dependencia
  nueva se propone antes de agregarla.
- **Sin paso de build en el frontend.** Módulos ES servidos tal cual, sin npm,
  bundler ni framework. Leaflet está en `web/vendor/`.
- El SQL va en `server/repo/`, y debe funcionar en SQLite y en Postgres.
- Tipos completos en `server/` (mypy con `disallow_untyped_defs`), ruff con
  línea de 100 y cobertura mínima de 80 %.
- Comentarios y docstrings en inglés. Los nombres del dominio y todo el texto
  de la interfaz van en español (`terrenos`, `carpetas`, `inventario`).
- Cada cambio de comportamiento llega con su prueba. Para un bug, primero la
  prueba que lo reproduce.
- El estado del frontend se reemplaza, no se muta (`web/lib/store.js`).

## Trampas del dominio

- En los archivos de ARA, **X es la latitud e Y la longitud**, al revés de la
  convención de GIS. Nunca intercambiarlas en silencio.
- **Nada se convierte ni se calcula.** Precio total y precio por m² son datos
  distintos, igual que m² y hectáreas. Un precio que falta queda sin precio, no
  en cero.
- **Los precios son en pesos (MXN).** Una columna en otra moneda se conserva
  como dato adicional y no puede usarse como precio.
- **Los datos se guardan como vienen.** La validación avisa; no bloquea ni
  corrige.
- **Un mapa guardado es una copia congelada**, no un espejo de su base.
- La columna `ID` del Excel es el número de fila, no un identificador estable.
  La identidad de un terreno es nombre + estado + municipio + superficie.
- Un terreno sin coordenadas válidas no se dibuja; nunca se coloca a la
  adivina.

## Datos y secretos

- Tratar el repositorio como público: no subir datos reales de terrenos,
  clientes ni contactos. Las pruebas usan datos ficticios o sintéticos.
- Nunca poner en commits, PRs ni reportes: contraseñas, cadenas de conexión,
  tokens, códigos OAuth, cookies de sesión ni URLs de descarga preautenticadas.
- `.env*`, `.cloud-access.txt`, `.vercel/` y `datos/` están en `.gitignore` y
  así deben quedarse.
- No imprimir valores de variables de entorno en la salida ni en los reportes.

## Skills compartidas

`.agents/skills/` trae las skills de Neon (`neon`, `neon-postgres`), fijadas en
`skills-lock.json`. Consultarlas antes de tocar la base en la nube.
