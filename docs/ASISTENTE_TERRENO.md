# Asistente del terreno (MVP)

Consultas de solo lectura sobre un terreno, desde el detalle de la tabla y
sólo para administradores. Especificación y contrato HTTP: issue #65.
Servidor: `server/asistente/terreno.py` y `server/api/asistente_terreno.py`.

## Qué se envía a Claude

Sólo `estado`, `municipio`, `tipo_terreno`, `superficie_m2`, `superficie_ha`,
`asking_price`, `asking_m2`, `moneda`, `price_on_request` y `availability`,
como texto con sus unidades, más las instrucciones del servidor y, en la
acción «pregunta», el texto escrito por el administrador. Nunca el nombre, el
id, la base, la dirección, las coordenadas, contactos, notas, descripción,
columnas personalizadas, historial ni adjuntos. `faltantes` se calcula en el
servidor y no llama al modelo.

## Búsqueda y comparación en la tabla maestra (#69)

Botón «Asistente IA» de la **Tabla maestra** (sólo administradores, sólo en
vista de tabla). Contrato HTTP en el issue #69.

- **Buscar:** a Claude sólo van la pregunta y la especificación fija de
  filtros, ningún terreno. Su JSON se valida en `server/asistente/busqueda.py`
  contra una lista cerrada. Cada valor de texto se busca con todas sus
  grafías registradas (mayúsculas, acentos, plural simple); el cliente sólo
  guarda un nombre por valor pedido y el servidor vuelve a ampliar las
  grafías en cada página. «Al menos» y
  «hasta» son límites inclusivos (`>=`, `<=`); «más de» y «menos de», estrictos
  (`>`, `<`), sin redondear. Después se usan `parse_query` y `repo.listar`
  sobre todo el inventario, incluidos los terrenos sin base. Lo que no se puede ejecutar
  exactamente pide aclaración y no muestra ningún listado. Las páginas
  siguientes no vuelven a llamar al modelo.
- **Comparar 2–3:** la tabla la construye el servidor con los mismos 10
  campos, sin cálculos ni conversiones. Claude sólo escribe un resumen de las
  fichas A/B/C; si falla, la tabla se muestra con el error del resumen.
- Interpretación y resumen comparten los límites, la concurrencia y el gasto
  de arriba.

## Configuración (sólo servidor; apagado por defecto)

| Variable | Valor |
|---|---|
| `ARA_MAP_CHAT_HABILITADO` | `1` para encender; cualquier otro valor lo apaga |
| `ARA_MAP_CHAT_CLAVE` | clave de API de Anthropic (Claude Console). Nunca en el repositorio |
| `ARA_MAP_CHAT_MODELO` | `claude-haiku-5-5` (ver abajo) |
| `ARA_MAP_CHAT_COSTO_ENTRADA_USD_MTOK` | `0.10` |
| `ARA_MAP_CHAT_COSTO_SALIDA_USD_MTOK` | `0.50` |
| `ARA_MAP_CHAT_LIMITE_MENSUAL_USD` | `5`: presupuesto mensual de producción autorizado por el propietario |
| `ARA_MAP_CHAT_TIEMPO_S` | opcional, 20 por defecto, máximo 30 |
| `ARA_MAP_CHAT_MAX_SALIDA` | opcional, 600 tokens por defecto, máximo 1024 |
| `ARA_MAP_CHAT_MAX_POR_HORA` | opcional, 30 por defecto |

Sin modelo, clave, tarifas o límite, `disponible` es `false` y las acciones
del modelo responden 503 `chat_no_configurado`; `faltantes` sigue funcionando.

**Modelo y precio**, comprobados el 20-oct-2026 en
https://platform.claude.com/docs/en/about-claude/pricing: Claude Haiku 5.5,
US$0.10 / US$0.50 por millón de tokens de entrada / salida para prompts de
hasta 100 000 tokens (una consulta usa menos de 2 000). Se pide con
`thinking: disabled`, esfuerzo `low`, sin herramientas, contra el endpoint fijo
`https://api.anthropic.com/v1/messages`. Otro modelo debe aceptar
`thinking: disabled` (Opus 5.5 y Sonnet 5.5 lo rechazan) y llevar sus propias
tarifas. Revisar precios antes de cambiar de modelo.

## Límites

- Una consulta al modelo a la vez por proceso; la segunda recibe 429
  `chat_limite`, sin cola.
- Gasto: antes de llamar se reserva el costo máximo posible (bytes de entrada
  + `max_tokens` de salida) en `uso_ia` y se rechaza si no cabe en el límite
  mensual. Se liquida con el uso que informa Anthropic. `uso_ia` es la tabla
  compartida con el asistente de importación: el límite mensual y el de
  consultas por hora cuentan el uso de ambos.
- Ninguna conexión SQL queda abierta mientras responde Claude. Antes de
  entregar la respuesta se vuelven a comprobar sesión, rol y terreno; si el
  terreno cambió, se descarta con 409 `conflict`.
- Errores del proveedor: 503/504 con los códigos del contrato, sin su texto.

## Ensayo con Claude real (datos ficticios, máximo US$1)

`scripts/ensayo_claude.py` hace el ensayo completo con código versionado: base
SQLite desechable en una carpeta temporal y servidor local en `127.0.0.1`.
Antes de empezar quita del proceso cualquier variable de base alojada, así
que no puede tocar Render, Neon ni Supabase. Usa un administrador y terrenos
ficticios.

Pasos, todos por las rutas reales con el adaptador real:
1. Revisión **gratuita** del modelo con la Models API: que exista para esa
   clave y acepte `thinking: disabled`. Si falla, no se gasta nada.
2. Búsqueda con límite estricto.
3. Página siguiente, que no debe llamar al modelo.
4. Búsqueda que pide aclaración.
5. Comparación de tres terrenos.
6. Pregunta sobre un terreno.

Para el gasto, la base temporal usa `ARA_MAP_CHAT_LIMITE_MENSUAL_USD=1`, de modo
que la reserva de la app rechaza lo que pudiera pasar de US$1. Además el
script se detiene si el registro pasa de US$0.90. No hay reintentos.

La salida muestra, por paso, el estado HTTP y el código, los criterios y el uso
(tokens y costo), el modelo y el SHA. **Nunca** muestra la clave, los prompts
ni las respuestas.

Se ejecuta en la Terminal del propietario donde ya existe `ARA_MAP_CHAT_CLAVE`,
desde una copia aparte del SHA candidato, para no tocar su checkout:

```bash
cd RUTA/ARA-MAP                       # su copia del repositorio
git fetch origin claude/candidato-68-70
git worktree add --detach /tmp/ara-ensayo-claude SHA_CANDIDATO
cd /tmp/ara-ensayo-claude
export ARA_MAP_CHAT_CLAVE             # exporta la variable que ya existe; no la escribe
/usr/bin/python3 scripts/ensayo_claude.py
cd - && git worktree remove /tmp/ara-ensayo-claude
```

`tests/test_ensayo_claude.py` comprueba la mecánica del script con un
proveedor **simulado** (así lo rotula su salida). No es evidencia sobre
Claude.

## Publicación en Render (después de la revisión y con autorización)

No hay cambio de esquema: la versión es la 10 y `uso_ia` ya existe. No se
cambian `render.yaml` ni las dependencias.

1. El responsable fusiona el PR revisado a `main` y anota el SHA publicado
   antes, para poder volver a él.
2. Publicar manualmente ese SHA de `main` en Render **sin** variables
   `ARA_MAP_CHAT_*`. El asistente queda apagado y el aviso «Próximamente» se
   ve. Comprobar con un administrador y un operador: tabla, mapa,
   filtros, adjuntos y exportación/importación de Excel.
3. Para encender el asistente, en Render (*Environment*) definir:
   - `ARA_MAP_CHAT_CLAVE`, como secreto y sólo ahí;
   - `ARA_MAP_CHAT_MODELO=claude-haiku-5-5`;
   - `ARA_MAP_CHAT_COSTO_ENTRADA_USD_MTOK=0.10`;
   - `ARA_MAP_CHAT_COSTO_SALIDA_USD_MTOK=0.50`;
   - `ARA_MAP_CHAT_LIMITE_MENSUAL_USD=5`, el presupuesto mensual autorizado
     de producción, distinto del US$1 del ensayo;
   - por último, `ARA_MAP_CHAT_HABILITADO=1`.

   Render reinicia el servicio con las variables nuevas. El límite de la app
   no controla otros usos de la misma clave en Anthropic: conviene fijar
   además un límite de gasto en Claude Console.
4. Con un administrador, una búsqueda y una comparación: revisar en `uso_ia`
   los estados y el costo, sin copiar prompts ni respuestas.

**Recuperación (preparada, no ejecutada):**
- Apagar sólo la IA: `ARA_MAP_CHAT_HABILITADO=0` (o borrar la variable) en
  Render. La tabla, el mapa y Excel siguen funcionando y el aviso
  «Próximamente» permanece.
- Volver atrás todo: publicar manualmente en Render el SHA anotado en el
  paso 1. Sin migraciones de por medio, no hay que tocar la base.

## Pruebas

`tests/test_asistente_terreno.py` y `tests/test_asistente_busqueda.py` (SQLite
y, con `ARA_MAP_TEST_DATABASE_URL`, Postgres desechable) usan un transporte
simulado del adaptador real: sin red, sin clave, sin gasto. Las e2e conectadas
(`tests/e2e/tabla-asistente.mjs` con `ASISTENTE_CONECTADO=1` y
`tests/e2e/tabla-asistente-maestra.mjs`) usan el servidor real con el
proveedor ficticio de `tests/e2e/asistente_servidor.py`. Nada de esto
demuestra que una llamada real funcione.
