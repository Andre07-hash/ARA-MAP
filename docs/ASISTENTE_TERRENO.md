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
| `ARA_MAP_CHAT_LIMITE_MENSUAL_USD` | límite aprobado por el propietario (propuesto: `5`) |
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

## Prueba real con Claude (pendiente)

Requiere clave y límite autorizados por el propietario. En un entorno aislado:

```bash
unset ARA_MAP_DATABASE_URL DATABASE_URL
export ARA_MAP_CHAT_HABILITADO=1 ARA_MAP_CHAT_MODELO=claude-haiku-5-5 \
  ARA_MAP_CHAT_COSTO_ENTRADA_USD_MTOK=0.10 ARA_MAP_CHAT_COSTO_SALIDA_USD_MTOK=0.50 \
  ARA_MAP_CHAT_LIMITE_MENSUAL_USD=5
read -rs ARA_MAP_CHAT_CLAVE && export ARA_MAP_CHAT_CLAVE   # sin eco ni historial
ARA_MAP_DB=/tmp/ara-asistente.db python3 -m server.app
```

Crear un administrador y un terreno ficticios, probar las cuatro acciones y
revisar en `uso_ia` estado, tokens y costo. No registrar prompts ni respuestas.

## Pruebas

`tests/test_asistente_terreno.py` y `tests/test_asistente_busqueda.py` (SQLite
y, con `ARA_MAP_TEST_DATABASE_URL`, Postgres desechable) usan un transporte
simulado del adaptador real: sin red, sin clave, sin gasto. Las e2e conectadas
(`tests/e2e/tabla-asistente.mjs` con `ASISTENTE_CONECTADO=1` y
`tests/e2e/tabla-asistente-maestra.mjs`) usan el servidor real con el
proveedor ficticio de `tests/e2e/asistente_servidor.py`. Nada de esto
demuestra que una llamada real funcione.
