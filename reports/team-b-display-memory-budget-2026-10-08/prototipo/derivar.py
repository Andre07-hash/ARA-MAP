"""Derive prototipo/MapCanvas.js (strategy "e5") from PR #16's derived prototype.

    python3 -I derivar.py <pr16-prototype-MapCanvas.js>

Input: reports/team-b-display-strategy-2026-10-08/prototipo/MapCanvas.js at
9da0ab1 (itself the accepted B-2 renderer plus the E1-E4 prototype edits,
derived by that folder's derivar.py). It is read, never modified. The edits
below (each must match exactly once) add strategy "e5" and leave e1-e4 as
they were; e1-e4 modules are imported from that folder's /proto/ mount.
Writes MapCanvas.js and the replayable MapCanvas.diff next to this script.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

EDICIONES: list[tuple[str, str]] = [
    # Imports: e1-e4 modules from PR #16's folder; e5 modules from here.
    ('import { crearClases } from "./capa.js";\n'
     'import { prepararAhora } from "./preparar.js";\n'
     'import { crearCache, crearPlanificador } from "./planificador.js";\n'
     'import { crearClienteRaster } from "./raster.js";\n',
     'import { crearClases } from "/proto/prototipo/capa.js";\n'
     'import { prepararAhora } from "/proto/prototipo/preparar.js";\n'
     'import { crearCache, crearPlanificador } from "/proto/prototipo/planificador.js";\n'
     'import { crearClienteRaster } from "/proto/prototipo/raster.js";\n'
     '// E5 (memory-budget investigation): shared budget, registry, capped planner, worker client, controller.\n'
     'import { crearPresupuesto } from "./presupuesto.js";\n'
     'import { crearRegistro } from "./registro.js";\n'
     'import { crearPlanificador as crearPlanificadorE5 } from "./planificador.js";\n'
     'import { crearCliente } from "./cliente.js";\n'
     'import { crearClasesE5, crearControlador } from "./e5.js";\n'),
    ('let PRESUPUESTO_TRABAJADOR;                      // F3: undefined = raster.js default\n',
     'let PRESUPUESTO_TRABAJADOR;                      // F3: undefined = raster.js default\n'
     '/* E5: ONE budget shared by every map created on the page (two maps compete),\n'
     ' * plus test-only failure simulation and the unanswered-request deadline. */\n'
     'let PRESUPUESTO_E5 = null;\n'
     'let SIMULAR_E5 = null;\n'
     'let PLAZO_E5_MS = 8000;\n'
     'let mapasE5 = 0;\n'
     'export function configurarE5({ presupuesto = null, bytes = 64 * 1024 * 1024, simular = null, plazoMs = 8000 } = {}) {\n'
     '  PRESUPUESTO_E5 = presupuesto ?? crearPresupuesto(bytes);\n'
     '  SIMULAR_E5 = simular;\n'
     '  PLAZO_E5_MS = plazoMs;\n'
     '  return PRESUPUESTO_E5;\n'
     '}\n'),
    # Wording: one employee-facing phrase for every transient state (supervisor's
    # direction), and a reason for each unavailable state (proposals).
    ('const NO_PINTADO = new Set(["dibujando", "sin_memoria"]);\n',
     'const NO_PINTADO = new Set(["dibujando", "sin_memoria", "demasiado_grande", "sin_trabajador"]);\n'
     '/* E5: states where the outline is not available (explicit, never pending). */\n'
     'const NO_DISPONIBLE_E5 = new Set(["sin_memoria", "demasiado_grande", "sin_trabajador"]);\n'
     'const AVISOS_E5 = {\n'
     '  cargando: "Cargando contorno…",\n'
     '  preparando: "Cargando contorno…",\n'
     '  dibujando: "Cargando contorno…",\n'
     '  sin_memoria: "Contorno no disponible: no hay memoria para dibujarlo ahora",\n'
     '  demasiado_grande: "Contorno no disponible: la ventana es demasiado grande para dibujarlo",\n'
     '  sin_trabajador: "Contorno no disponible: falló el dibujo; se reintentará al actualizar el mapa",\n'
     '};\n'),
    ('  const cache = crearCache(undefined, { alExpulsar: (id) => raster?.expulsado(id) });\n'
     '  let reinicioTrabajador = null;                 // F3: resolves when the worker confirms\n'
     '  const planificador = crearPlanificador();\n',
     '  const E5 = ESTRATEGIA === "e5";\n'
     '  if (E5) Object.assign(AVISOS, AVISOS_E5);\n'
     '  const duenoE5 = E5 ? `mapa-${++mapasE5}` : null;\n'
     '  const presupuestoE5 = E5 ? (PRESUPUESTO_E5 ?? configurarE5()) : null;\n'
     '  const registro = E5 ? crearRegistro(presupuestoE5, duenoE5) : null;\n'
     '  const { CapaContornoE5, CapaBitmap } = crearClasesE5(L, CapaContorno);\n'
     '  // E5: the registry is the cache; the planner reserves before allocating.\n'
     '  const cache = E5\n'
     '    ? { obtener: (d) => registro.obtener(d), guardar() {}, vaciar: () => registro.vaciar(),\n'
     '        contiene: () => false, get bytes() { return registro.bytesReservados(); },\n'
     '        get tamano() { return registro.tamano; } }\n'
     '    : crearCache(undefined, { alExpulsar: (id) => raster?.expulsado(id) });\n'
     '  let reinicioTrabajador = null;                 // F3: resolves when the worker confirms\n'
     '  const planificador = E5\n'
     '    ? crearPlanificadorE5({ registro, presupuesto: presupuestoE5,\n'
     '                            alPreparar: (d, r, reserva) => registro.guardar(d, r, reserva) })\n'
     '    : crearPlanificador();\n'),
    ('  map.fitBounds(MEXICO_BOUNDS);\n'
     '  L.control.zoom({ position: "topright" }).addTo(map);\n',
     '  map.fitBounds(MEXICO_BOUNDS);\n'
     '  L.control.zoom({ position: "topright" }).addTo(map);\n'
     '  const controlador = E5 ? crearControlador({\n'
     '    L, map, CapaBitmap, presupuesto: presupuestoE5, dueno: duenoE5,\n'
     '    crearCliente: (o) => crearCliente({ presupuesto: presupuestoE5, dueno: duenoE5, simular: SIMULAR_E5,\n'
     '                                       plazoMs: PLAZO_E5_MS, ...o }),\n'
     '    alEstado: (capa, estado) => capa._avisarE5?.(estado),\n'
     '  }) : null;\n'),
    ('    generacion += 1;\n'
     '    contornoLayer.clearLayers();\n'
     '    markerLayer.clearLayers();\n'
     '    byId = new Map();\n',
     '    generacion += 1;\n'
     '    // E5: the old entries\' layers stop pinning their prepared bodies; a failed worker is retried.\n'
     '    if (E5) {\n'
     '      for (const e of byId.values()) if (e.contorno?._ctl) registro.soltar(e.contorno._id);\n'
     '      controlador.reintentar();\n'
     '    }\n'
     '    contornoLayer.clearLayers();\n'
     '    markerLayer.clearLayers();\n'
     '    byId = new Map();\n'),
    ('    if (!filas.length) { cache.vaciar(); if (raster) reinicioTrabajador = raster.olvidarTodo(); }\n',
     '    if (!filas.length) {\n'
     '      cache.vaciar();\n'
     '      if (raster) reinicioTrabajador = raster.olvidarTodo();\n'
     '      if (controlador) reinicioTrabajador = controlador.vaciar();\n'
     '    }\n'),
    ('      } else capa = new CapaContorno(c, opciones);\n',
     '      } else if (E5) {\n'
     '        registro.fijar(descriptor.id);              // pinned for this entry\'s lifetime\n'
     '        capa = new CapaContornoE5(c, opciones, { id: descriptor.id, controlador });\n'
     '        capa._avisarE5 = (estado) => alDibujo(entrada, terreno, estado);\n'
     '      } else capa = new CapaContorno(c, opciones);\n'),
    ('    if (entry.estadoContorno === "sin_memoria") {\n'
     '      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo,\n'
     '               motivo: "sin_memoria" };\n',
     '    if (NO_DISPONIBLE_E5.has(entry.estadoContorno)) {\n'
     '      return { estado: "contorno_no_disponible", contorno: true, zoom, requerido, maximo,\n'
     '               motivo: entry.estadoContorno };\n'),
    ('    destruir() {\n'
     '      planificador.detener();\n'
     '      cache.vaciar();\n',
     '    destruir() {\n'
     '      planificador.detener();\n'
     '      cache.vaciar();\n'
     '      controlador?.cerrar();\n'
     '      registro?.cerrar();\n'),
    ('    _diagnostico: { planificador, cache, raster,\n',
     '    _diagnostico: { planificador, cache, raster, presupuesto: presupuestoE5, registro, controlador,\n'),
    ('  const disponible = cargado && estadoContorno !== "sin_memoria";\n',
     '  const disponible = cargado && !NO_DISPONIBLE_E5.has(estadoContorno);\n'),
]


def main(entrada: Path) -> None:
    original = entrada.read_text(encoding="utf-8")
    texto = original
    for antes, despues in EDICIONES:
        veces = texto.count(antes)
        if veces != 1:
            raise SystemExit(f"edit must match once, matched {veces}: {antes[:70]!r}")
        texto = texto.replace(antes, despues)
    cabecera = ("/* PROTOTYPE derived from PR #16's derived prototype MapCanvas.js (9da0ab1)\n"
                " * by prototipo/derivar.py, adding strategy \"e5\" (memory budget). Not\n"
                " * application code. See MapCanvas.diff for the exact changes. */\n")
    (AQUI / "MapCanvas.js").write_text(cabecera + texto, encoding="utf-8")
    diff = difflib.unified_diff(original.splitlines(keepends=True), texto.splitlines(keepends=True),
                                "a/prototipo/MapCanvas.js (PR #16)", "b/prototipo/MapCanvas.js (e5)")
    (AQUI / "MapCanvas.diff").write_text("".join(diff), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve())
