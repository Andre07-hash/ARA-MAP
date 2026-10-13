# Proyecto definitivo — transición del 13 de octubre de 2026

El propietario confirmó que el portal de Render es el producto definitivo y
autorizó normalizar el repositorio y su publicación. Se abandona el formato
de equipos A/B para trabajar directamente con developers por cambios pequeños.

## Estado de partida comprobado

- `main`: `09452fd26d38319567dce28a89db100ea61c739a`, rama predeterminada.
- Rama publicada `codex/team-a-free-pilot-v1`:
  `7848b46789d811c0a0b138b882dbab146010f44a`.
- El piloto incluye a `main` y está 112 commits adelante, sin commits exclusivos
  de `main`. La transición conserva ese historial; no reimplementa entregas.
- PR #33, #34 y #35 fusionados. CI del SHA publicado: runs 38482594142 y
  38483511613 completados con éxito.
- Render: servicio `srv-db74ir49v7es73af0u70`, deploy
  `dep-db7bp2rbc2fs73ejg2tg`, mismo SHA, «Deploy succeeded | Live».
- Colaborador `jp7ao`: permiso Write en GitHub. No se ha proporcionado el error
  concreto del developer; su autenticación local y los accesos a proveedores
  no quedan verificados por esa membresía.

## Alcance de la transición

Adoptar el historial aceptado en `main` mediante PR. Actualizar `README.md`,
`AGENTS.md`, `CLAUDE.md` y `docs/DESARROLLO.md` para indicar el producto vigente,
desarrollo local separado, entrega por PR y publicación manual.
`render.yaml` declara `branch: main` y mantiene el plan Free y auto-deploy off.
Alinear también la rama en el servicio Render existente y publicar el SHA de
`main` comprobado. No cambiar código de aplicación, esquema, datos, cuentas,
almacén, credenciales ni planes.

Los reportes históricos se conservan; sus encabezados de «pendiente» no revocan
publicaciones posteriores. Las antiguas ramas no son la base de cambios nuevos.
Los PRs históricos cuyo head ya sea ancestro de `main` pueden cerrarse como
entregas incorporadas; los trabajos no incorporados no se descartan.

## Evidencia y cierre

La aplicación se conserva exactamente respecto de `7848b46`: verificar el diff
por rutas de aplicación y pruebas. Ejecutar la verificación normal previa al
push y CI del PR; después comprobar CI y árbol del commit integrado antes de
publicar. Registrar SHA, PR y deploy final en el cierre del PR y en el reporte
de supervisión. No presentar esto como una nueva certificación de recuperación
o todos los permisos alojados.

El mapa de la base importada sigue pendiente, sin diagnóstico ni corrección.
