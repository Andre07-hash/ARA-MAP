# ARA Map — Claude Code

Las reglas del proyecto están en AGENTS.md, compartidas con los demás agentes.

@AGENTS.md

## Trabajo actual

- Lee `docs/DESARROLLO.md`. Parte de `origin/main` actualizado y abre un PR
  pequeño contra `main` por cada cambio solicitado.
- El producto vigente es https://ara-map-piloto.onrender.com/, en Render +
  Neon + Supabase Storage privado. Las antiguas asignaciones A/B son historia.
- Las ramas creadas desde Claude Code usan el prefijo `claude/`.
- Los plugins personales son opcionales; no son un requisito para desarrollar,
  probar o abrir PRs. No supongas que otros developers tienen los tuyos.
- La salida de `/graphify` (`graphify-out/`) es local y está en `.gitignore`.
- Los ajustes personales van en `.claude/settings.local.json`, que no se sube.
  Lo que deba aplicar a todos va en `.claude/settings.json`, por PR.
- Aplica «Pruebas proporcionales y diagnóstico» de `AGENTS.md`: ante un fallo,
  lee los logs y reproduce primero los tests fallidos. No ejecutes toda la
  suite para identificar cuáles fallaron ni repitas suites completas por rutina.
- No necesitas secretos del sitio para probar localmente. El permiso de GitHub
  y los accesos a los proveedores son cosas distintas.
