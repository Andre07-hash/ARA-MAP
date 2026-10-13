# Revisión del candidato combinado de A y siguiente paso

**Actualización posterior:** el defecto de fábrica está corregido en B `071d7d0`, y A `69ae72d` ya integra el ciclo de archivos de `770cc83`. Leer el [cierre local A/B](CIERRE_LOCAL_A_B.md); no reasignar los pendientes históricos de este reporte.

12 de octubre de 2026, hora de México. Mantiene el [acuerdo de entrega y backlog](../../PLAN_DE_ENTREGA.md). Revisión de código, ascendencia, CI y un reproducer aislado; no es aceptación alojada ni ejecución independiente de las suites completas de A/B.

## Avance confirmado

- A #31 está en `df7984ddee736a8a37174ec83ea039a257c3f8d5`. El adaptador B `9380ecc` está integrado y `server.hosted.configurar` conecta la fábrica desde el entorno. Dependencias directas y lock publicados: `storage3==2.32.0`, `httpx==0.28.1`, `psycopg[binary]==3.3.6`.
- Se comprobó ascendencia de `9380ecc`, #30 `bc7e421` y #28 `b2ac9bd`. No corresponde volver a integrar sus entregas.
- El árbol `web/` de A es idéntico a `4670df7`: `2db407fea780732c173caa56bde824e064d33259`. No hay rediseño del frontend.
- A reporta 24 comprobaciones con proceso real y almacén local, pruebas del adaptador con SDK y proveedor simulado, y error controlado con proveedor inalcanzable. No reporta ejecución real en Supabase/Render ni recorrido de navegador del candidato.
- [CI de A 38332804387](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38332804387): JavaScript aprobado; Python/Postgres en ejecución al consultar. Aunque termine verde, el workflow no instala el SDK alojado y sus pruebas dependientes se omiten. A reportó ejecutarlas localmente con el lock. Esto debe permanecer explícito en la evidencia.

## B publicó más trabajo del que refleja la espera de A

B #32 está ahora en `770cc8358ee42a3e71336517932ce7136c607e65`, con [CI 38331150339](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38331150339) verde. Se descubrió al consultar GitHub durante esta revisión; no se recibió aquí un handback final de B para ese SHA.

Incluye resolución diferida del almacén, comprobación pura de configuración al iniciar después de autorización/replay, traducción de errores y tratamiento de escritura incierta. También incluye `scripts/verificar_archivos.py`, `server/recuperacion.py`, consultas de referencias y pruebas. No es necesario pedir que B vuelva a implementar esos componentes. A puede revisar el SHA publicado mientras B corrige el defecto siguiente. No se declara aceptado ni integrado el nuevo head de B.

## Defecto reproducido que debe cerrar B

En `770cc83`, `server/recuperacion.py::_almacen_de` hace:

```python
almacen = modulo.fabrica_desde_entorno(os.environ)
return almacen
```

El contrato real devuelve `Callable[[], Almacen] | None`. Con configuración válida, el resultado es una **función**, no un almacén. El camino `--almacen-entorno` no puede leer ni listar sus objetos.

Reproducción independiente: se extrajo `server/` del SHA exacto a una carpeta temporal, se llamó `_almacen_de` con configuración ficticia válida y se prohibió crear sockets. Resultado:

```text
Returned type: function
Callable factory returned: True
Has leer: False
Has listar: False
Reproduced: 'function' object has no attribute 'leer'
```

No hubo acceso al proveedor, credenciales reales ni cambios de aplicación. La prueba de CLI publicada en `tests/test_recuperacion.py::test_command_reads_the_database_and_never_prints_the_url` simula una fábrica que devuelve directamente el almacén; por eso no detecta la diferencia de contrato.

**Corrección acotada para B:** comprobar `None`, ejecutar la fábrica y tratar su error de configuración/SDK como error seguro de uso del comando, sin secretos. Ajustar la prueba para devolver una fábrica como la real y añadir la regresión del camino remoto. Mantener el verificador de sólo lectura y publicar SHA/checks. No cambiar el contrato del adaptador para acomodar el error del consumidor.

## Instrucciones inmediatas para A

1. Continuar desde `df7984d` en #31. El almacenamiento ya está conectado; no repetir la primera integración.
2. Revisar B `770cc8358ee42a3e71336517932ce7136c607e65` y su corrección posterior exacta. Integrar por merge local ordinario cuando el cambio esté publicado y revisado. No esperar un reporte largo ni duplicar la corrección en A.
3. Convertir en aserciones obligatorias los dos pendientes del ensayo: inicio autorizado sin configuración responde 503 y no crea pendiente nuevo; descarga sin alcance responde 404 antes de resolver almacén. Verificar también fábrica que falla/SDK ausente → 503 seguro y tabla operativa. Mantener replay idempotente.
4. Reemplazar la copia manual del ensayo por el exportador corregido. Obtener referencias desde la copia de base restaurada del dump, para que manifiesto y respaldo correspondan. Probar la recuperación combinada.
5. Corregir la instrucción del checklist «upload the exported files with B's tool»: el verificador/exportador es de sólo lectura y no sube archivos al destino. Documentar y ensayar el método concreto del operador para cargar los bytes exportados en un bucket nuevo, conservando claves y verificándolos después. No convertir el verificador en herramienta de escritura ni iniciar un sistema nuevo de recuperación.
6. Preservar evidencia reproducible de las pruebas con SDK instalado desde el lock y reportar explícitamente sus skips en CI. No ampliar credenciales ni detener toda integración por el permiso `workflow` que faltó a la sesión. La mejora de CI se puede aplicar por la vía autorizada disponible; no describir la CI actual como cobertura del SDK.
7. Entregar candidato exacto, checks y checklist operativo listo para el ensayo alojado. El recorrido del empleado en navegador y los proveedores reales siguen pendientes; son el siguiente hito, no backlog.

## Instrucciones inmediatas para B

1. Preservar el trabajo de `770cc83` y cualquier avance local. Corregir únicamente el fallo reproducido de fábrica del exportador, con regresión del contrato real y manejo seguro de configuración ausente/fábrica fallida.
2. Publicar SHA exacto y evidencia; comunicar el contrato de manifiesto/comandos ya implementado. A revisa e integra mientras continúas con cualquier verificación pendiente del encargo.
3. Coordinar con A el paso operativo para subir la exportación a un destino nuevo. Tu verificador sigue siendo de sólo lectura; no afirmar que `--restauracion` restaura o sube bytes: verifica el destino.
4. Separar resultados locales/simulados de los que siguen pendientes en Supabase real. No reabrir proveedores, protocolo de transferencias, frontend o backlog.

## Alcance y autorización

El camino crítico se reduce a cerrar e integrar ciclo de archivos/recuperación y ejecutar las pruebas alojadas y de navegador. Las restricciones vigentes se conservan: no recursos, cuentas, secretos, pagos, despliegue, datos reales ni merge de PR/main autorizados por este seguimiento. Preparar todo lo independiente para que la autorización operativa recaiga sobre un candidato y pasos concretos.
