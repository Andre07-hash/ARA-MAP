# Asistente IA: pausa y reanudación

**PAUSADO por instrucción del propietario el 20-oct-2026 (Ciudad de México).**
Este README permite retomar con sesiones nuevas de supervisor y Claude Code.
El control compartido sigue en [issue #69](https://github.com/Andre07-hash/ARA-MAP/issues/69).

No continuar desarrollo, resolver conflictos, ensayar con API, configurar,
fusionar ni publicar este asistente hasta una nueva instrucción expresa.
Los planes anteriores de publicación urgente y los presupuestos históricos
no autorizan actividad durante la pausa. Otros cambios de ARA MAP siguen su
flujo normal. No borrar las ramas ni los PRs que conservan este avance.

## 1. Punto guardado en GitHub

Fotografía al pausar; verificar los estados actuales al retomar:

| Pieza | Rama y SHA | Estado comprobado |
| --- | --- | --- |
| main | `b2aa254d53b3abeb794d1a1bafcb06dda113fc8c` | Incluye #68, #72–#75; no incluye el asistente de terrenos |
| [#66: alternativa de un terreno](https://github.com/Andre07-hash/ARA-MAP/pull/66) | `claude/asistente-terreno-mvp` — `d0a85722218014574f6da327bc5948ee16a95b0e` | Draft, CI verde, sin integrar a main |
| [#70: búsqueda/comparación](https://github.com/Andre07-hash/ARA-MAP/pull/70) | `claude/asistente-busqueda-comparacion` — `fbd47935ebd1bc27e9262b1350def0f7c6ce69c9` | Draft, CI verde; ya incluye #66 |
| [#71: candidato más completo](https://github.com/Andre07-hash/ARA-MAP/pull/71) | `claude/candidato-68-70` — `1e84b16f676b8bdac8b0d8210c3ea8bdf506e01f` | Draft, CI verde en ese SHA; no integrado ni revisado para publicar |

**Partir preferentemente del avance de #71, después de revisarlo; no rehacerlo.**
#66 es una alternativa más pequeña, no otro PR que deba fusionarse además
de #70/#71. #67 se fusionó únicamente en la rama de #66, no en main.

La interfaz de JP7AO (#68) sí llegó a main mediante
`b84b50e4910aad5e1b6f5accb4e5281504619c91`, incluyendo `422a889`.
Luego llegaron #72 (mostrar columnas y mapa con los seleccionados), #73
(quitar copias locales « 2»), #74 (menú de Safari) y #75 (columnas por vista).
Mientras se preparaba esta nota se comprobó un punto más nuevo de #71:
`1e84b16`, que incorpora main hasta #73 (`11dff77`). Conserva el anterior
`af6624e` en su historial. Todavía no incorpora #74/#75: diverge de main,
23 commits por delante y 4 por detrás. GitHub lo mostraba fusionable al
consultarlo; eso no sustituye actualizar/revisar/probar la combinación.
No repetir la integración usando sólo el antiguo `8dd30d1`. El resto de PRs
ajenos a IA se consulta al retomar; no se pausa ni se integra de paso.

No se comprobó en esta pausa qué SHA está publicado en Render ni sus
variables. No confundir main, CI y versión publicada. No se cambió producción.
El asistente de importación preexistente en `server/asistente/ia.py` es
distinto: no desactivarlo ni rediseñarlo como parte de esta pausa.

## 2. Alcance implementado y límites

- Administrador solamente, sólo lectura, entrada desde la tabla. Preservar
  tabla/mapa maestra, permisos, foco, posición, filtros y adjuntos existentes.
- Un terreno: resumen, faltantes calculados por reglas, borrador de descripción
  y pregunta breve. Cada petición es independiente.
- Búsqueda sobre toda la maestra autorizada, incluyendo filas sin base: Claude
  propone filtros cerrados, el servidor los valida y ejecuta la consulta
  existente. Total real, diez por página, paginación sin repetir Claude.
- Comparación explícita de 2–3 terrenos: tabla factual del servidor y resumen
  de Claude separado, sin conversiones ni datos inventados o modificados.
- Aviso compacto «Próximamente» en tabla y panel; la tabla no necesita API para
  el aviso. No añadir otra entrada de IA en el mapa. El aviso sigue en #71,
  no llegó a main por fusionar #68.
- No incluye lectura de PDF/JPG/KMZ/KML, OCR, edición, herramientas autónomas,
  búsqueda web, memoria de seguimiento ni conversaciones guardadas.
- **El nuevo estilo de chat y el historial temporal se aplazaron.** No
  recuperarlos como requisito para la primera salida. Estado sólo en memoria;
  cerrar, cambiar contexto o terminar sesión descarta lo pendiente.

## 3. Reutilización y privacidad

Leer [#65](https://github.com/Andre07-hash/ARA-MAP/issues/65),
[#69](https://github.com/Andre07-hash/ARA-MAP/issues/69) y el
[contrato de búsqueda/comparación](https://github.com/Andre07-hash/ARA-MAP/issues/69#issuecomment-6299173017).
En #71 están `server/asistente/terreno.py`, `busqueda.py`,
`server/api/asistente_terreno.py`, los componentes `asistenteTerreno.js` y
`asistenteMaestra.js`, sus módulos en `web/lib/` y pruebas. Reutilizan
`server/asistente/ia.py`, `inventario.parse_query`, `repo/inventario.py`,
transporte privado y diálogos existentes. No crear otro buscador o framework.

La [nota técnica de #71 en su SHA guardado](https://github.com/Andre07-hash/ARA-MAP/blob/1e84b16f676b8bdac8b0d8210c3ea8bdf506e01f/docs/ASISTENTE_TERRENO.md)
contiene configuración, ensayo y publicación. **Sus comandos no se ejecutan
durante la pausa.** No hay migraciones ni dependencias nuevas; se conserva
Python 3.9 local y JavaScript ES modules sin framework ni build.

Al modelo sólo pueden ir, según la acción: `estado`, `municipio`,
`tipo_terreno`, `superficie_m2`, `superficie_ha`, `asking_price`, `asking_m2`,
`moneda`, `price_on_request` y `availability`. Buscar envía pregunta y esquema,
no inventario completo; comparar usa alias A/B/C. Excluir del contexto
automático nombres, IDs, base, dirección exacta, coordenadas, contactos,
notas, descripción libre, columnas personalizadas y adjuntos. La pregunta
escrita sí sale al proveedor: mantener el aviso de evitar información sensible.
Nada real ni secretos en GitHub, capturas, reportes o logs.

## 4. Correcciones y evidencia: qué no repetir

R1–R5 de #70 quedaron revisados en `111255a`: grafías/acentos/mayúsculas,
límites estrictos «más de/menos de», comparación vieja tras 404/409, detalle
tardío al cerrar y paginación con más de diez grafías. Conservar regresiones;
no reabrir investigaciones cerradas sin evidencia nueva.

#71 añade estas correcciones, reportadas por su developer:

| Commit | Cambio |
| --- | --- |
| `ad2d67e` | E1: exportar sólo en Tabla, pues el mapa tiene otros filtros; E2: descartar efectos de importación después de cerrar; invalidar conjunto del mapa bajo filtro de superficie |
| `8ab0fb9` | Quitar `null`/`false` sueltos del panel |
| `aefb54d` | Script de ensayo real, su prueba simulada y documentación |
| `e790dc0` | Combinar main de #68, conservando filtros múltiples y superficie |
| `af6624e` | Ajustar e2e a los diálogos realmente abiertos |
| `9a88556`, `44a1c15`, `1e84b16` | Ajustar prueba de selección rápida, incorporar main #72/#73 y distinguir «Columnas» de «Mostrar columnas» en otra e2e; revisar esos cambios al retomar |

El supervisor reprodujo E1/E2 en la versión anterior de #68. **No hay revisión
final conjunta de #71 sobre main actual.** Al pausar, el diff contra main
todavía contiene E1/E2 y la corrección de superficie. Si hacen falta sin IA,
encargar un PR separado a un developer; no fusionar toda la IA para obtenerlas
ni implementar cambios de app como parte de cerrar esta pausa.

| Evidencia | Límite |
| --- | --- |
| [CI de #71, `1e84b16`](https://github.com/Andre07-hash/ARA-MAP/actions/runs/39522520919) | Python con Postgres 16 desechable y JavaScript verdes; no cubre main posterior ni Claude real |
| JS en `e790dc0`, según developer | 272/272; ruff y mypy limpios |
| e2e en `aefb54d`, según developer | Tabla/posición, adjuntos, mapa, permisos, Excel y asistente pasaron con datos/proveedor ficticios, antes de traer main actualizado |
| e2e en `af6624e`, según developer | Asistente de un terreno simulado 18/18; no se repitió toda la batería conjunta |
| e2e en `1e84b16` | La descripción de #71 aún conserva la evidencia anterior; no atribuir toda esa batería al nuevo SHA sin un informe que lo respalde |
| Claude real | **Sin ejecución/resultado real registrado en GitHub**; pedir evidencia nueva si alguien dice haberlo ejecutado después |
| Producción, Firefox y Safari | No certificados por estas pruebas; las e2e no corren en CI |

`test_packaging` falló antes por openpyxl del sistema mientras CI pasaba.
Comparar entorno/main antes de atribuirle un fallo nuevo. No repetir campañas
QA de archivos/memoria ni el mapa histórico aplazado sin justificación nueva.

## 5. Clave, gasto y ensayo pendiente

No se guarda ninguna clave aquí. El propietario informó que cargó
`ARA_MAP_CHAT_CLAVE` en una Terminal de su Mac. No leer su valor ni asumir que
persista o que otra app, sesión o computadora lo herede. Al retomar, confirmar
acceso privado autorizado; nunca pedir que la pegue en un chat.

Antecedentes sujetos a confirmación antes de reactivar gasto: ensayo aislado
máximo US$1 y producción ARA MAP US$5/mes. La pausa suspende ensayos y
activación; no recargar ni ampliar planes. El límite de la app no controla
otros usos de la cuenta/clave de Anthropic.

`scripts/ensayo_claude.py` en #71 prepara SQLite y terrenos ficticios, usa
rutas/adaptador reales y tiene tope de gasto. Revisar código y aislamiento
antes de entregar el comando al propietario. `tests/test_ensayo_claude.py`
prueba su mecánica con proveedor ficticio, **no la conexión real**.
El modelo documentado era `claude-haiku-5-5`; verificar existencia, parámetros
y precios oficiales al volver, no copiar tarifas de memoria.

La contabilidad comparte `uso_ia` con importación; reserva antes de llamar y
conserva reservas inciertas. Una llamada simultánea por proceso. Dejar de
esperar en navegador no cancela el servidor ni asegura que no haya cobro.

## 6. Orden para retomar

1. Obtener instrucción expresa del propietario. Leer AGENTS.md,
   docs/DESARROLLO.md, este README y estados actuales de #65/#69/#66/#70/#71.
   Revisar checkout y conservar reportes antes de Git. Confirmar main y qué
   está publicado; no inferirlo del nombre «piloto» o del estado de un PR.
2. Un developer integrador, rama propia desde main actualizado y reutilización
   del avance #71. Mantener originales y #66 como alternativa. Resolver
   conflictos o diferencias con los cambios actuales, especialmente Safari y
   columnas por vista de #74/#75. Conservar columnas/selección del mapa de #72;
   no resucitar las copias « 2» borradas en #73 ni aceptar archivos completos
   de una rama para resolver conflictos.
3. Revisión focalizada de diferencias y correcciones. Verificar roles/sesión,
   tabla/mapa, filtros/superficie, posición, adjuntos y Excel; conservar R1–R5
   y probar E1/E2. Reutilizar evidencia de lo que no cambió.
4. Renovar acceso privado y autorización de gasto. Revisar/ejecutar el ensayo
   real aislado, sin producción, datos reales ni reintentos automáticos
   facturables. Registrar SHA, resultado y uso/costo sin secretos ni contenido
   real. Separar simulación de Claude real; corregir sólo bloqueos probados.
5. CI verde en SHA combinado final, evidencia y límites en GitHub y revisión
   del supervisor. Sólo después, con autorización concreta de salida,
   integrar/publicar manualmente un SHA revisado de main. Preparar presupuesto,
   configuración privada y recuperación antes de activar. No probar escrituras
   de negocio/importaciones en producción como parte de la validación de IA.

El supervisor investiga, revisa y prepara prompts; no implementa la app.
No hay seguimientos programados creados por esta pausa. No enviar mensajes a
otras sesiones/personas: el propietario transmite las instrucciones.

## 7. Mensaje para abrir una sesión nueva de supervisor

> Vamos a retomar el asistente IA de ARA MAP. Lee AGENTS.md,
> docs/DESARROLLO.md y reports/asistente-ia-pausa-2026-10-20/README.md en GitHub,
> además del estado actual del issue #69 y PR #71. Eres supervisor: investiga,
> revisa y prepara instrucciones para Claude Code; no implementes la app.
> Conserva el checkout local y reutiliza el avance guardado. Primero presenta
> qué cambió desde la pausa y qué falta, sin reconstruir lo terminado ni
> reabrir investigaciones cerradas sin evidencia. No activar gasto, fusionar
> ni desplegar sólo por abrir esta sesión.

El supervisor deriva de ese diagnóstico el encargo del developer, que debe
leer este mismo punto de control. Ninguna sesión nueva necesita archivos
privados, claves o capturas de sesiones anteriores para entender el avance.

## 8. Mensaje para una nueva sesión de developer, al autorizar la reanudación

> Retomamos la integración del asistente IA. Lee las instrucciones actuales
> del repositorio, este README de pausa, el issue #69 y el PR #71. Revisa
> checkout, main y PRs antes de Git. Conserva el avance original y trabaja en
> rama propia desde main actualizado, reutilizando #71 y sin añadir chat ni
> historial. Primero informa las diferencias desde el punto guardado y un
> plan pequeño de integración/pruebas para que lo revise el supervisor.
> No repitas correcciones ya verificadas ni debilites sus regresiones. Para
> Claude real, confirma acceso privado y gasto autorizado antes de llamar;
> toda evidencia compartida usa datos ficticios. Entrega PR, SHA, pruebas,
> límites y CI verde, y avisa cuando sólo falte integrar. No fusiones,
> publiques ni configures producción por iniciativa propia.
