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

`tests/test_asistente_terreno.py` (SQLite y, con `ARA_MAP_TEST_DATABASE_URL`,
Postgres desechable) usa un transporte simulado del adaptador real: sin red,
sin clave, sin gasto. No demuestra que una llamada real funcione.
