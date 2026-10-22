# ARA Map — guía para agentes

Instrucciones compartidas para cualquier agente de IA (Claude Code, Codex u
otro) que trabaje en este repositorio, en cualquier computadora. Aquí van las
reglas estables. El estado del trabajo en curso vive en `reports/` y en los
pull requests, no en este archivo.

ARA Map es el portal privado definitivo para registrar terrenos, editar su
tabla y adjuntar PDF y KMZ. El sitio vigente es
https://ara-map-piloto.onrender.com/; conserva «piloto» en su dirección, pero es
el producto que se mantiene. Hosting: Render Free + Neon Postgres + Supabase
Storage privado. La ejecución local usa SQLite y archivos locales de prueba.
[README.md](README.md) describe el producto y
[docs/DESARROLLO.md](docs/DESARROLLO.md) explica cómo trabajar en él.

No hay asignaciones vigentes por «Team A / Team B». Se trabaja directamente
con developers Claude Code, por cambios pequeños y pull requests. Los reportes
anteriores se conservan como evidencia histórica, no como tareas pendientes.

## Antes de empezar

1. `git fetch` y parte de `origin/main` actualizado. Varias personas y agentes
   trabajan en clones separados; lo que no está en GitHub no existe para los
   demás.
2. Lee `docs/DESARROLLO.md` y la tarea actual del propietario. `main` es la
   base única de los cambios nuevos; Render publica desde esa rama. Los
   checkpoints y protocolos A/B de `reports/` no sustituyen estas instrucciones.
3. Revisa los pull requests abiertos (`gh pr list`) para no duplicar ni pisar
   trabajo en curso. Un PR abierto puede traer instrucciones más nuevas que
   `main`.
4. Una instrucción directa del dueño del proyecto tiene prioridad sobre
   cualquier documento.

El asistente IA de terrenos está **pausado por el propietario** y fuera de
`main`. Antes de tocar sus PRs #66/#70/#71, leer el
[punto de reanudación](reports/asistente-ia-pausa-2026-10-20/README.md) y el
[issue #69](https://github.com/Andre07-hash/ARA-MAP/issues/69). No continuar,
consumir API, fusionar ni publicar ese trabajo hasta una nueva instrucción.
Esto no pausa otros cambios de ARA MAP ni el asistente de importación existente.

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
| `server/hosted.py` | Entrada de Render: Postgres y almacenamiento externo privado |
| `api/index.py` | Adaptador histórico de Vercel; fuera del flujo de publicación actual |
| `web/` | Frontend en JavaScript sin paso de build: `components/`, `lib/`, `styles/` |
| `vendor/python/` | openpyxl incluido para que la app local no necesite instalar nada |
| `scripts/` | Operación de la nube: migraciones, cuentas, esquema |
| `tests/` | `test_*.py` con unittest, `js/` con node:test, `e2e/` de navegador |
| `reports/` | Traspasos, planes y evidencia por fecha; es historial, no se reescribe |

## Reglas de producción

Estas reglas no admiten excepción sin autorización explícita del dueño.

- **Publicación manual en Render.** Fusionar a `main` no publica nada:
  auto-deploy permanece apagado. El responsable publica un SHA revisado y con
  CI verde cuando la tarea del propietario autoriza la publicación. Tener
  permiso de escritura en GitHub no otorga acceso a Render ni a los secretos.
- **No ejecutar `scripts/migrate_cloud.py` ni `scripts/setup_cloud.py` sin
  `--url-env` apuntando a una base desechable.** Sin esa opción pueden usar la
  configuración de producción y modificar datos. No sirven como diagnóstico.
- **No cambiar infraestructura de paso.** `render.yaml`, variables de Render,
  Neon y Supabase se cambian sólo en una tarea y PR dedicados. No reabrir
  Vercel/S3/Blob ni rediseñar transferencias sin un problema concreto.
- **Sin tarjeta ni pagos.** Mantener los planes gratuitos; no contratar
  recursos, pruebas que se conviertan en pago ni ampliaciones de facturación.
- **Un cambio de esquema es un paso de release.** Va con su migración, su
  prueba de migración y una nota en el reporte para quien despliega. La base de
  producción puede ir versiones atrás de `main`.
- **Pruebas separadas de la operación real.** Usar SQLite, Postgres y archivos
  desechables. No conectar un servidor de desarrollo a la base ni al bucket
  del sitio vigente. No modificar cuentas o datos alojados sin la autorización
  concreta del propietario.

## Flujo de trabajo

- Una rama por cambio, creada desde `origin/main`:
  `<herramienta-o-autor>/<tema-en-kebab-case>`, por ejemplo
  `claude/excel-onedrive-refresh` o `codex/safe-error-responses`.
- Nunca hacer push directo a `main`. `main` no tiene protección de rama, así
  que esta regla depende de quien trabaja.
- Abrir un pull request y esperar los checks de GitHub Actions en verde antes
  de fusionar. Marcar como draft lo que no está probado.
- Quién fusiona: Andre07-hash integra los PRs. Además, jp7ao puede fusionar
  sus propios PRs a `main` sin esperarlo, con los checks en verde y la revisión
  hecha, por merge commit (`gh pr merge N --merge --delete-branch`), nunca con
  push directo. Fusionar no publica: desplegar en Render sigue siendo del
  responsable, con autorización de publicación.
- Correr `./verificar.sh` antes de cada push.
- Commits pequeños con mensaje en inglés que diga qué cambia y por qué.
- Al terminar, reportar el PR, SHA, comportamiento cambiado, pruebas afectadas
  y límites. Distinguir pruebas locales, CI y comprobación publicada.
- Revisión proporcional: bloquear acceso indebido, pérdida de datos y flujos
  esenciales rotos. Reutilizar evidencia del código que no cambió; no repetir
  suites grandes de navegador o memoria por mejoras menores sin una razón.
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
- **Nada se convierte ni se calcula**, con una excepción. Precio total y precio
  por m² son datos distintos, igual que m² y hectáreas. Un precio que falta
  queda sin precio, no en cero. Excepción autorizada por el propietario: al
  editar una celda de la tabla, se llenan solas las vacías de m² ⇄ HA y precio
  total ⇄ precio por m² (`calculados` en `web/lib/tabla.js`). Nunca sobrescriben
  un valor existente ni se aplican al importar.
- **Los precios son en pesos (MXN).** Una columna en otra moneda se conserva
  como dato adicional y no puede usarse como precio.
- **Los datos se guardan como vienen.** La validación avisa; no bloquea ni
  corrige.
- **Un mapa guardado es una copia congelada**, no un espejo de su base.
- La columna `ID` del Excel es el número de fila, no un identificador estable.
  La identidad de un terreno es nombre + estado + municipio + superficie.
- En Tabla / Mapa, un terreno con contorno activo puede aparecer sin X/Y;
  con X/Y válidas y sin contorno aparece como punto. Sin ambos no se dibuja.
- Los terrenos existen primero como filas; después se adjuntan PDF o JPG y KMZ o
  KML. PDF y JPG comparten la ranura `core:archivos` (tipo `pdf`), con la misma
  regla de `tipo_detectado` que KMZ y KML.
  Un KMZ o KML con un contorno válido se activa al completar; con varios
  candidatos se elige y activa en el detalle; uno inválido conserva el contorno
  anterior. KMZ y KML comparten la ranura `core:kmz` (tipo `kmz`); el formato
  de cada versión lo fija `tipo_detectado`, no un nombre interno nuevo.
- La importación Excel/CSV heredada no carga la tabla maestra. Las filas de la
  tabla maestra se cargan con «Importar Excel» del menú ⋯ de la tabla
  (administradores) o con `scripts/cargar_maestra.py`; ambos usan
  `server/carga_maestra.py`.
- El fallo del mapa de «Base Terrenos 09.26 copy» sigue pendiente por decisión
  del propietario. No retomarlo sin una tarea nueva.

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
