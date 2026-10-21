# Logo por cuenta (esquema 11)

## Qué cambia

- «Bases y accesos» → «Cuentas» → «Nueva cuenta» tiene el selector **Logo**
  (ARA / Dewa). ARA está elegido por omisión.
- La elección se guarda en la cuenta (`team_user.marca`). El servidor la lee de
  la cuenta autenticada en cada `/api/login` y `/api/session`; el nombre visible
  no interviene. Sin sesión se ve ARA.
- Sustituye la regla fija de PR #81 («tyrag» → Dewa por login). La migración
  conserva lo que cada cuenta veía: `tyrag` queda en Dewa y las demás en ARA.
- Roles y permisos no cambian: sólo un administrador (`usuarios.gestionar`)
  crea cuentas.

## Paso de release (para quien despliega)

Es un cambio de esquema: 10 → 11. `server/hosted.py` no arranca si la base no
está en la versión que espera el código, así que el orden importa:

1. Comprobar la versión actual (sólo informa):
   `python3 scripts/esquema.py --url-env <VARIABLE_CON_LA_URL> --check`
   Debe decir 10.
2. Inmediatamente antes de desplegar el SHA fusionado, aplicar la migración:
   `python3 scripts/esquema.py --url-env <VARIABLE_CON_LA_URL>`
   Guarda un respaldo en `workspace_backup`, añade la columna
   `team_user.marca` (`'ara'` por omisión, sólo `'ara'` o `'dewa'`) y, en el
   mismo paso, marca `dewa` la cuenta `tyrag`. Es idempotente: volver a
   ejecutarlo no cambia nada ni sobrescribe una elección guardada.
3. Desplegar en Render el SHA de `main` que contiene este cambio.

Entre los pasos 2 y 3 el código anterior sigue atendiendo (no lee la columna
nueva), pero un reinicio suyo se negaría a arrancar con el esquema 11: no dejar
pasar tiempo entre ambos pasos.

El esquema nunca se migra desde el servidor ni desde un PR. Nadie del desarrollo
ejecutó la migración sobre la base del sitio.

## Pruebas

- `tests/test_schema_v11.py`: SQLite y Postgres desechable; la cuenta `tyrag`
  queda en Dewa, las demás en ARA, los roles intactos, dos migraciones no cambian
  nada, una elección posterior no se sobrescribe y la columna rechaza otro valor.
- `tests/test_roles_y_bases.py`: el administrador crea cuentas con Dewa o con el
  valor por omisión; un operador recibe 403 con cualquier logo; valores no
  admitidos dan 422; el logo sigue a la cuenta en inicios de sesión nuevos, al
  cambiar de cuenta y al cerrar sesión, nunca al nombre visible.
- Recorrido en navegador (Chromium, SQLite desechable, datos ficticios): ARA por
  omisión, flechas del teclado entre opciones, creación con cada logo, recarga,
  cambio de cuenta, otro dispositivo, sesión eliminada y operador sin acceso.
