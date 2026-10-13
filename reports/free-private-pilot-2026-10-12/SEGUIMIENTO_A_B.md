# Continuidad A/B — integrar el almacén sin esperar al cierre completo de B

**Seguimiento posterior:** A ya integró `9380ecc` y B publicó `770cc83`. Leer la [revisión del candidato combinado](REVISION_CANDIDATO_A.md) antes de reutilizar los prompts de este registro; no repetir la integración ya realizada.

12 de octubre de 2026, hora de México. Aplicar el [acuerdo de entrega](../../PLAN_DE_ENTREGA.md) y el [contrato F0](START_HERE.md). Este seguimiento mantiene alcance, proveedores, backlog y restricciones; no inicia otra fase.

## Revisión del supervisor

- GitHub confirma A #31 en `3cba52b2d254f0a27f4df1fdca918d890ca6b17c`. [CI exacto 38326448017](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38326448017) terminó aprobado en JavaScript y Python/Postgres durante esta revisión; ya no está pendiente como en la entrega original.
- GitHub confirma B #32 en `9380ecc34af8a6b4fccdf387c066163c1dcdda59`, con ambas tareas de [CI 38325006198](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38325006198) aprobadas.
- Se inspeccionaron el adaptador, su fábrica, la taxonomía de errores y las pruebas declaradas de B. El alcance conserva los seis métodos del almacén y las rutas existentes; es entrada provisional para integración. No se ha probado aquí contra Supabase ni se otorga aceptación final del proveedor.
- Se inspeccionaron el cambio de arranque de A, su ensayo y la salida publicada. Las 23 comprobaciones usan el proceso real `server.hosted`, Postgres y **almacén local inyectado**, con llamadas por API. No son evidencia de Supabase, Render ni de una nueva prueba visual de navegador. Los dos errores conocidos aparecen como pendientes y no hacen fallar todavía ese ensayo.
- El frontend de A no presenta cambios respecto a `4670df7`; B sólo modifica el almacén y sus pruebas. No se encarga rediseño.
- El ensayo sintético satisfactorio no diagnostica por sí solo el archivo o la versión que falló en el localhost del propietario.

La dependencia que detenía a A ya está publicada. A conecta ahora el adaptador; B termina sus cambios publicados después en la misma rama. No duplicar el trabajo de ciclo de archivos ni esperar un informe final para empezar a integrar.

## Texto para transmitir a A

Continúa F0-A en `codex/team-a-free-pilot-v1`, PR #31, desde tu head `3cba52b2d254f0a27f4df1fdca918d890ca6b17c`. Lee primero `PLAN_DE_ENTREGA.md` en la rama del supervisor `codex/supervisor-completion-brief`. El objetivo sigue siendo cerrar el portal privado con KMZ/PDF duraderos; el backlog sigue aplazado.

Ya está disponible la primera entrega de B para **integración provisional local**, no aceptación alojada:

- PR #32, rama `codex/team-b-free-files-v1`.
- SHA exacto: `9380ecc34af8a6b4fccdf387c066163c1dcdda59`; CI exacto verde.
- Fábrica: `from server.almacen_supabase import fabrica_desde_entorno`; conectar mediante `configurar_almacen(fabrica_desde_entorno(os.environ))` en la configuración del servidor alojado.
- Variables: `ARA_MAP_ARCHIVOS_SUPABASE_URL`, `ARA_MAP_ARCHIVOS_SUPABASE_KEY`, `ARA_MAP_ARCHIVOS_SUPABASE_BUCKET`. Credencial sólo del servidor; bucket privado.
- Dependencia probada: `storage3==2.32.0`, con `httpx==0.28.1` en el entorno de B. A es dueño de declarar/fijar las dependencias alojadas y comprobar el arranque con su Python previsto. Mantener el SDK opcional para la ejecución local que no usa este almacén.

Comprueba el objeto y su alcance, e integra ese SHA mediante merge local ordinario en tu rama. No hagas merge de PR/main. Conserva #28 y #30 ya consumidos; no dupliques commits. Conecta el almacén, declara dependencias y variables, y publica un candidato combinado temprano después de los checks requeridos. No esperes el exportador de B para esta primera integración.

Los pendientes «inicio sin almacén crea fila» y «descarga sin permiso devuelve 503 antes de 404» pertenecen al siguiente cambio de B. No implementes una segunda solución. Mantén visibles los pendientes y, cuando integres el SHA de ciclo de archivos de B, conviértelos en aserciones obligatorias del ensayo: 503 sin insertar un pendiente nuevo para un inicio autorizado sin almacén; 404 para quien no tiene alcance, haya o no almacén. Conservar las reglas de repetición idempotente.

Reutiliza tu ensayo actual. Cuando B publique el exportador/manifiesto, sustituye la copia manual de respaldo por esa herramienta en el ensayo de restauración. No construyas un segundo exportador. Usa pruebas enfocadas y checks normales, sin repetir campañas de rendimiento ajenas al piloto.

Mientras B termina, deja preparado el procedimiento ejecutable para desplegar y probar el candidato exacto con datos ficticios. Devuelve SHA combinado, resultado de CI, qué sigue pendiente de B y qué acciones concretas necesita realizar el operador para el ensayo alojado. No declares resuelta la carga real del usuario únicamente por el KMZ sintético.

No tocar frontend salvo un defecto demostrado del flujo obligatorio; no cambiar proveedor, protocolo, esquema ni importador antiguo. Mantener la carga inicial antes del trabajo concurrente. Sin recursos, cuentas, secretos, pagos, despliegue, datos reales ni merge de PR/main autorizados por este seguimiento.

## Texto para transmitir a B

Continúa F0-B en tu misma sesión/rama `codex/team-b-free-files-v1`, PR #32, con commits aditivos sobre `9380ecc34af8a6b4fccdf387c066163c1dcdda59`. Lee `PLAN_DE_ENTREGA.md` en `codex/supervisor-completion-brief`. No se cambia el encargo ni se reinicia el trabajo.

Tu primera entrega, interfaz y dependencia ya se transmiten a A para integración provisional. A está en `3cba52b2d254f0a27f4df1fdca918d890ca6b17c`; su ensayo usa almacén local sustituto y detecta exactamente los dos pendientes que estás corrigiendo:

1. Un inicio autorizado sin almacén devuelve 200 e inserta pendiente: debe fallar como configuración no disponible antes de insertar un pendiente nuevo, conservando repeticiones idempotentes.
2. Una descarga de una cuenta sin alcance devuelve 503 cuando falta almacén: debe conservar el 404 de autorización antes de resolver/acceder al almacén.

Termina el cambio de ciclo de archivos ya en curso, incluidos configuración/SDK ausente, fallos reintentables, resultados inciertos y limpieza sólo de la clave propia tras prueba fiable de que no está referenciada. Preserva los plazos, permisos y archivos existentes. Publica ese cambio con SHA y checks en cuanto sea utilizable; no lo retengas esperando el reporte o exportador final.

En paralelo termina `scripts/verificar_archivos.py`, manifiesto v1 y ensayo de recuperación. Pasa a A temprano el contrato concreto: comandos, entradas/salidas, campos del manifiesto, selección de referencias desde el respaldo de base de datos y cómo comprobar tamaño/SHA de los bytes exportados. Mantén la copia coherente con la base respaldada; listado del bucket no sustituye el inventario de referencias. No borrar huérfanos ni montar automatización avanzada.

La comprobación en el proveedor real ya prevista sigue pendiente: acceso privado, credencial efectiva, creación sin sobrescritura, reemplazo/lectura inmediata, metadatos y transferencias completas. Prepara los pasos y distingue simulación de proveedor real; resuelve diferencias concretas si aparecen. No abrir otra investigación de proveedores ni regresar a S3, OIDC o transferencias por partes.

No cambies la rama de A ni su configuración compartida/frontend. Devuelve cada SHA publicado, CI, pasos de integración y pendientes reales. Sin recursos, cuentas, secretos, pagos, despliegue, datos reales ni merge de PR/main autorizados por este seguimiento.

## Próximo hito

Un candidato integrado con almacenamiento conectado, los dos errores cerrados y respaldo/restauración de archivos incorporado. Después corresponde ejecutar la prueba en el entorno gratuito real autorizado y cerrar las casillas del acuerdo. No hace falta terminar el backlog para esa entrega.
