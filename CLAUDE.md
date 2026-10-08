# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Verificar sin zsh (Linux, sesiones en la nube)

`./verificar.sh` usa `#!/bin/zsh`. Donde no hay zsh, correr sus partes por
separado y decir en el reporte que se corrieron así:

```bash
python3 -m unittest discover -s tests -t .       # suite de Python
<python3.9> -m unittest discover -s tests -t .   # compatibilidad, si /usr/bin/python3 no es 3.9
node --test tests/js/*.test.mjs                  # JavaScript
ruff check server/ tests/ && mypy server/        # parte de --todo (sin cobertura)
```

Una prueba suelta:

```bash
python3 -m unittest tests.test_importer.NombreDeClase.test_metodo
node --test tests/js/geo.test.mjs
```

Falla conocida del entorno, no regresión:
`tests.test_packaging.CleanMachine.test_the_system_python_has_no_openpyxl_of_its_own`
falla en máquinas cuyo `/usr/bin/python3` ya trae openpyxl (muchas imágenes de
Linux). En la Mac del equipo pasa.

## Pruebas de navegador

`tests/e2e/` sólo necesita `playwright-core`: `cd tests/e2e && npm install`.
Sin Chrome instalado, indicar el binario con `CHROMIUM=/ruta/al/chrome`; en las
sesiones en la nube Chromium está bajo `/opt/pw-browsers/`.
