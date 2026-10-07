# ARA Map — Claude Code

Las reglas del proyecto están en AGENTS.md, compartidas con los demás agentes.
Este archivo las importa y añade sólo lo específico de Claude Code.

@AGENTS.md

## Específico de Claude Code

- Las ramas creadas desde Claude Code usan el prefijo `claude/`.
- Los plugins se instalan por persona, no viajan con el repositorio. El equipo
  usa Ponytail, Agent Skills y Graphify; si falta alguno, avisar en lugar de
  suponer que está.
- La salida de `/graphify` (`graphify-out/`) es local y está en `.gitignore`.
- Los ajustes personales van en `.claude/settings.local.json`, que no se sube.
  Lo que deba aplicar a todo el equipo va en `.claude/settings.json`, por PR.
