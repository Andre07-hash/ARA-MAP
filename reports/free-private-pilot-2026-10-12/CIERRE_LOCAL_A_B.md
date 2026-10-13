# Cierre local A/B y preparación de la prueba alojada

**Hito posterior completado:** A `31b6a1d` ya integra B `071d7d0` y tiene CI verde. No repetir las tareas de integración de este registro; seguir la [propuesta de prueba alojada](PRUEBA_ALOJADA_PARA_AUTORIZAR.md).

12 de octubre de 2026, hora de México. El reporte de B usa fecha 13 de octubre en su nombre; se conserva esa ruta como referencia, sin cambiar la fecha local de esta decisión. Continúa el [plan de entrega](../../PLAN_DE_ENTREGA.md): portal privado, KMZ por terreno existente, PDF, recuperación, sin pagos ni ampliación de alcance.

## Estado y evidencia

| Equipo | SHA revisado | Resultado |
| --- | --- | --- |
| A / #31 | `69ae72dfd7b31c6596eb85109f4c4c091ebcde59` | Integra B `770cc83` por `65f3f26`. [CI 38335097876](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38335097876): JS aprobado, Python/Postgres en curso al consultar |
| B / #32 | `071d7d05c985167c9ea3efac5d8ac6eb2b3819a6` | [CI exacto 38334388640](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38334388640) aprobado; corrige fábrica remota, agrega regresión y rechazo al inicio si la fábrica no construye |

A reporta 30 comprobaciones API con proceso alojado y almacén local, recuperación con herramientas reales, 41/41 recorridos de Chrome sobre el launcher local y pruebas del SDK contra proveedor simulado. El recorrido en navegador sobre `server.hosted` y los proveedores reales siguen pendientes. No se presenta la ejecución sobre `server.app` como prueba de Render.

La única corrección posterior al script completo reportada por A es orden de imports, con ruff vuelto a ejecutar limpio. Eso no requiere repetir todos los recorridos anteriores. La siguiente integración sí requiere las pruebas afectadas y los checks normales del candidato. La CI sigue omitiendo pruebas que requieren el SDK; conservar los resultados locales con el lock instalado y no ampliar credenciales para resolver esa limitación.

El árbol `web/` de A sigue idéntico a `4670df7`: `2db407fea780732c173caa56bde824e064d33259`.

## Error de fábrica: cerrado de forma enfocada

El supervisor extrajo el código B del SHA exacto a un directorio temporal, sin modificar la aplicación ni usar proveedores reales, y ejecutó `tests.test_recuperacion` con base remota deshabilitada:

- 19 pruebas: 14 aprobadas, 5 omitidas por requerir Postgres.
- Se sustituyó únicamente `_almacen_de` por la función de `770cc83` y se ejecutó la nueva regresión del contrato real: falló con `AttributeError: 'function' object has no attribute 'leer'`, como debía.
- La versión corregida construye la fábrica, conserva salida 2 para configuración/SDK ausente y evita exponer credenciales.

Se acepta **esta corrección para integración**, no el comportamiento del proveedor real. No pedir a B que vuelva a corregir el mismo defecto.

También se ejecutaron las cinco pruebas de `tests.test_restaurar_archivos` del SHA A `69ae72d`: cinco aprobadas. No se ejecutaron independientemente aquí las suites completas ni los ensayos Postgres/navegador reportados por los equipos.

## Una secuencia de recuperación para el operador

A y B añadieron caminos de carga en paralelo. Para cerrar el piloto, la guía de A conserva la secuencia que ya ensayó:

1. Dump consistente y referencias obtenidas desde la base restaurada de ese dump.
2. `scripts/verificar_archivos.py` de B para verificar/exportar esos archivos.
3. `scripts/restaurar_archivos.py` de A para cargarlos en un destino nuevo.
4. `scripts/verificar_archivos.py --restauracion` para verificar íntegramente el destino contra el manifiesto y contra la base restaurada.

La salida «ya estaban» del cargador de A sólo comprueba el tamaño en caso de colisión; **no equivale a coincidencia de SHA**. Por eso la verificación final de tamaño/SHA es obligatoria y su fallo impide declarar recuperado el destino. No permitir sobrescritura para resolver conflictos.

B añadió `--cargar-exportacion`, que sí escribe en el destino; no describir toda la herramienta como incondicionalmente de sólo lectura. Sin esa opción, los caminos de verificar/exportar mantienen su carácter de lectura del almacén. Esa opción adicional no se usa en la secuencia operativa elegida para este piloto. No invertir otra ronda en quitarla, unificar implementaciones ni crear una tercera: una futura limpieza puede ir al backlog. No se autoriza ninguna ejecución sobre almacenes reales por documentar este procedimiento.

## Prompt de continuidad para A

Continúa en #31 desde `69ae72dfd7b31c6596eb85109f4c4c091ebcde59`.

1. Revisa e integra mediante merge local ordinario B `071d7d05c985167c9ea3efac5d8ac6eb2b3819a6`, CI verde. Incluye la corrección de fábrica y su regresión; `770cc83` ya es ancestro, no lo dupliques. El cambio también comprueba que la fábrica pueda construirse antes de iniciar una subida nueva, fuera de la transacción de escritura y después de la autorización inicial; conserva replay y reverificación.
2. Mantén obligatorias las aserciones de configuración/permisos y añade al cierre la comprobación de fábrica no construible sin pendiente nuevo. Verifica el camino `--almacen-entorno` con el contrato real y proveedor simulado/local de prueba, incluyendo exportación/restauración en el candidato integrado. Reporta ese resultado como simulado.
3. Usa la secuencia de recuperación elegida arriba. No cambies a la opción de carga de B ni refactorices por duplicación. El verificador final es obligatorio antes de considerar íntegro el destino.
4. Ejecuta las pruebas afectadas y checks normales. Conserva evidencia SDK local con el lock; no repitas campañas de rendimiento o los 41 recorridos intactos sólo por el cambio de importación anterior. La prueba de navegador contra la entrada alojada sigue siendo necesaria en el candidato final.
5. Publica SHA candidato, CI, pendientes reales y checklist concreto para la ejecución autorizada en Render/Neon/Supabase. Con ese candidato, el siguiente trabajo es la prueba alojada, no otra fase de desarrollo. No afirmar que el KMZ particular del propietario está corregido sin haberlo reproducido; un fallo vigente del flujo obligatorio se corrige si aparece durante la aceptación.

No tocar frontend, cambiar proveedor, volver al protocolo anterior, ampliar alcance, crear recursos/cuentas, cambiar secretos, habilitar pagos, desplegar, importar datos reales ni hacer merge de PR/main por este mensaje.

## Prompt de continuidad para B

La corrección de fábrica de `071d7d0` está verificada: pruebas de recuperación aprobadas y control negativo contra `770cc83` detectado. A recibe ese SHA para integración. No hace falta otro cambio para ese defecto.

Actualiza el cuerpo de #32, que aún describe `770cc83`, para reflejar el head y sus límites. Es una actualización de comunicación, no requisito para que A empiece a integrar. Mantén los pasos de prueba del proveedor listos y apoya la integración si aparece un fallo concreto. No iniciar funcionalidades, otros proveedores ni otro mecanismo de restauración.

Para el piloto, A conservará su cargador y utilizará tu herramienta para exportación/verificación. Explica que `--cargar-exportacion` es un modo de escritura opcional que queda fuera de esa guía; no describes su ejecución como de sólo lectura. No hace falta retirarlo ni refactorizarlo ahora.

Sin cambios a la rama de A, recursos, cuentas, secretos, pagos, despliegue, datos reales ni merge de PR/main. Los fallos reales de Supabase se atienden durante la prueba autorizada con la corrección mínima necesaria.

## Lo que todavía separa este candidato de la entrega

Integración del último SHA de B; candidato exacto verificado; configuración y despliegue autorizados en cuentas gratuitas; recorrido del empleado en navegador sobre el servicio alojado, archivos completos, permisos, persistencia y restauración real. Sigue aplicando el presupuesto de capacidad y la disponibilidad limitada del piloto. El backlog permanece aplazado.
