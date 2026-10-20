# Desarrollo de ARA Map

## Base única

El sitio https://ara-map-piloto.onrender.com/ es el producto definitivo.
`main` contiene el trabajo aceptado y es la rama de publicación en Render.
El despliegue es manual; auto-deploy queda apagado.

Se trabaja directamente con developers Claude Code. No hay tareas ni
responsabilidades vigentes divididas en Team A / Team B. Los reportes de esas
entregas son antecedentes: no repetirlas ni volver a fusionar sus candidatos.

## Llegar al código vigente

Para una copia nueva:

```bash
git clone https://github.com/Andre07-hash/ARA-MAP.git
cd ARA-MAP
git switch main
git pull --ff-only origin main
git switch -c claude/descripcion-del-cambio
```

En una copia existente, revisa primero `git status`, conserva el trabajo sin
publicar y ejecuta `git fetch origin`. Con el checkout limpio, cambia a `main`,
actualízalo con `git pull --ff-only origin main` y crea la rama del cambio.
No uses `reset --hard` ni fuerces pushes para resolver una copia atrasada.
Si tienes trabajo sobre la antigua rama del piloto, publícalo en una rama propia
y compara su diff contra `origin/main` antes de abrir el PR.

Lee `AGENTS.md` y la tarea vigente del propietario. Los antiguos protocolos
`COORDINATION.md`, checkpoints y PRs históricos no activan nuevas tareas.

## Entorno local independiente

Python 3.9+; JavaScript ES modules sin build ni framework. Node.js para las
pruebas. Render usa Python 3.12.15 y `requirements-hosted.txt`.
No necesitas acceso a Render, Neon ni Supabase para una mejora local.

Comprueba que no tengas variables `ARA_MAP_DATABASE_URL` o `DATABASE_URL`
que dirijan el proceso a una base alojada. En una terminal de desarrollo:

```bash
unset ARA_MAP_DATABASE_URL DATABASE_URL ARA_MAP_READ_ONLY
python3 scripts/cuentas.py --sqlite /tmp/ara-dev.db crear dev_admin "Admin local" --rol admin
python3 scripts/cuentas.py --sqlite /tmp/ara-dev.db crear dev_operador "Operador local"
ARA_MAP_DB=/tmp/ara-dev.db python3 -m server.app
```

Las contraseñas se piden de forma oculta (mínimo general: 12 caracteres).
Elige otra ruta de SQLite si `/tmp/ara-dev.db` ya contiene trabajo que quieres
conservar; no borres ni recrees una base existente para seguir este ejemplo.

Abre `http://localhost:8420`. Con el administrador local crea una base de trabajo
y concede acceso a `dev_operador`. Crea filas ficticias y adjunta PDF/KMZ de
prueba. El almacén local pertenece a este entorno, no a Supabase.

**Dos recorridos distintos:** importar Excel/CSV alimenta bases heredadas.
Para cargar muchas filas de la tabla maestra usa «Importar Excel» del menú ⋯
(administradores) o `scripts/cargar_maestra.py`.
Para probar un cambio pequeño suelen bastar unas filas creadas en la interfaz.

## Comprobar el cambio

Ejecuta las pruebas afectadas y la verificación normal antes de subir:

```bash
./verificar.sh
```

Si la máquina no tiene zsh, ejecuta sus comprobaciones equivalentes:

```bash
python3 -m unittest discover -s tests -t .
node --test tests/js/*.test.mjs
```

En macOS también se comprueba la suite con `/usr/bin/python3`. Si cuentas con
`.venv-dev`, `./verificar.sh --todo` añade ruff, mypy y cobertura; las pruebas
de navegador se ejecutan por separado según `tests/e2e/README.md`.

GitHub Actions verifica JavaScript y Python con Postgres 16 desechable.
Los tests que requieren el SDK de Supabase pueden omitirse en CI porque el
workflow actual sólo instala psycopg. Para cambios del adaptador o recuperación,
instala `requirements-hosted.txt` en un entorno local de pruebas y ejecuta los
tests pertinentes; no atribuyas una omisión de CI a evidencia del proveedor.

Pruebas de navegador: sólo las pertinentes al cambio. No repetir investigaciones
de memoria ni recorridos extensos por un cambio menor sin una razón concreta.
Reporta SHA, comandos, resultados y lo que no verificaste. Datos siempre ficticios.

## Entregar un cambio pequeño

1. Una rama propia desde `origin/main`; un objetivo por PR.
2. Sube la rama y abre el PR contra **`main`**, con el problema, el comportamiento
   resultante y las pruebas. Nunca hagas push directo a `main`.
3. Corrige hallazgos que puedan romper el uso, permisos o datos; espera CI verde.
4. El responsable integra lo revisado (jp7ao también puede fusionar sus propios
   PRs con CI en verde; ver `AGENTS.md`) y, con autorización de publicación para
   esa tarea, despliega manualmente el SHA exacto desde `main` en Render.
5. Comprueba en el sitio el recorrido afectado. Para cambios del operador,
   incluye su rol. Una comprobación alojada no certifica todos los flujos.

No fuerces pushes sobre ramas ajenas. No recrees cuentas, infraestructura o datos
para publicar mejoras. Mantén el hosting gratuito, sin tarjeta, pagos ni extras.

## Permisos y bloqueos

Un colaborador de GitHub con permiso **Write** puede subir ramas y abrir PRs.
No necesita usar la cuenta del propietario. Su sesión o token también debe
autorizar operaciones de escritura sobre este repositorio; un error al subir
puede proceder de esa autenticación aunque la membresía sea correcta.
Editar workflows puede exigir permisos adicionales de la credencial usada.

GitHub no concede acceso a Render, Neon o Supabase. El responsable conserva
esos accesos y ejecuta las operaciones alojadas. No copies `.env.local`,
`.cloud-access.txt`, contraseñas, cookies, tokens ni conexiones entre developers.

Si algo falla, entrega el comando o acción, el error saneado, la rama, el SHA
y tu usuario de GitHub. No adjuntes secretos. Distingue una copia atrasada,
un permiso de GitHub y un acceso a proveedores que la tarea realmente necesite.

## Límites vigentes

Conserva las reglas de KMZ, permisos por fila, Tabla / Mapa y fondos existentes.
El fallo del mapa de «Base Terrenos 09.26 copy» sigue pendiente por decisión
del propietario. Catálogo público, optimizaciones avanzadas y rediseños generales
quedan fuera de las tareas actuales salvo una indicación nueva.

Los cambios de cuentas se guardan en la base alojada, no en GitHub. Actualizar
o clonar código no recrea esos cambios; tampoco deben ejecutarse scripts de
preparación histórica para «sincronizar» las cuentas del sitio.
