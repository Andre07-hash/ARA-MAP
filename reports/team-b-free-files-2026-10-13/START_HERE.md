# Equipo B — F0-B: ciclo de archivos y recuperación (13 de octubre de 2026)

Rama `codex/team-b-free-files-v1`, PR draft #32. Commits aditivos sobre la primera entrega
`9380ecc`. Sin force push, merge, recursos, secretos, despliegue ni datos reales.

## Entregas en esta rama

| SHA | Contenido | CI |
| --- | --- | --- |
| `9380ecc` | Adaptador Supabase, fábrica y pruebas de contrato (primera entrega) | 38325006198 verde |
| `770cc83` | Ciclo de archivos con almacén ausente o fallando; verificador/exportador y manifiesto v1 | 38331150339 verde |
| `81f4803` | Un inicio también se rechaza si la fábrica no construye el almacén (SDK ausente); corrección de `--almacen-entorno`; carga de exportación al destino de restauración | ver PR |
| (este reporte) | Ensayo de restauración con `pg_dump`/`pg_restore`, guion de prueba del proveedor y este contrato | ver PR |

## Integración para A

Merge local ordinario del SHA más reciente publicado en esta rama. La fábrica,
las variables y la dependencia no cambian respecto de `9380ecc`:
`configurar_almacen(fabrica_desde_entorno(os.environ))`, `storage3==2.32.0` con
`httpx==0.28.1`. No hay cambios de frontend, rutas, DTO ni esquema.

Cambios de comportamiento que el ensayo de A debe afirmar:

1. **Inicio autorizado sin almacén:** `503 almacen_no_configurado`, `reintentar: false`,
   sin fila nueva en `archivo_version`. Esto incluye una fábrica instalada que no puede
   construir el almacén (SDK ausente). La repetición con la misma `Idempotency-Key`
   sigue devolviendo 200 con el resultado guardado.
2. **Autorización antes del almacén en todas las rutas de bytes:** una cuenta sin alcance,
   quien no inició la subida o un id inexistente reciben 404; una sesión muerta, 401. Esto
   se cumple con o sin almacén. El almacén sólo se construye cuando quien llama ya está
   autorizado.
3. **Fallos del almacén:** siempre 503, nunca 401/403. `almacen_no_configurado` cuando falta
   configuración; `almacen_no_disponible` con el `reintentar` del proveedor (caída: `true`;
   credencial rechazada, bucket inexistente o cuota: `false`). El estado del proveedor queda
   sólo en el log del servidor, saneado.
4. **Escritura final incierta:** se borra sólo el nonce propio del intento, y sólo si la base
   prueba que no está referenciado; si no puede probarse, el objeto se conserva. En ambos
   casos se informa `limpieza_pendiente: true`. Una colisión o un fallo confirmado no borran
   nada. El reintento usa un nonce nuevo. Cancelar no necesita almacén: responde
   `limpieza_pendiente: true`.

Plazos, lease, límite de pendientes, privacidad del pendiente, verificación de tamaño, SHA y
firma, y la geometría activa no cambian. Las pruebas de servicio y de HTTP lo cubren en
SQLite y en Postgres.

## Contrato de recuperación

### Comandos

```bash
# Respaldo (diario): las referencias salen de la base RESPALDADA, no del listado del bucket.
pg_dump --format=custom --no-owner --no-privileges --file piloto-<fecha>.dump "$PILOTO_DB"
createdb ara_respaldo_tmp
pg_restore --no-owner --no-privileges --dbname ara_respaldo_tmp piloto-<fecha>.dump
export RESPALDO_URL=postgresql://.../ara_respaldo_tmp            # nunca en la línea de comandos
python3 scripts/verificar_archivos.py --url-env RESPALDO_URL --almacen-entorno \
    --exportar /carpeta/privada/archivos                          # incremental

# Ensayo de restauración en destino desechable (base y bucket nuevos y vacíos).
pg_restore --no-owner --no-privileges --dbname "$RESTAURADA_DB" piloto-<fecha>.dump
python3 scripts/verificar_archivos.py --manifiesto /carpeta/privada/archivos/manifiesto.json \
    --almacen-local DESTINO   |  --almacen-entorno   (con variables del bucket DESTINO) \
    --restauracion --cargar-exportacion /carpeta/privada/archivos
export RESTAURADA_URL=...
python3 scripts/verificar_archivos.py --url-env RESTAURADA_URL --almacen-entorno --restauracion
```

Las opciones `--sqlite RUTA`, `--json` y `--presupuesto BYTES` también existen (el presupuesto
por omisión es 700 000 000). Códigos de salida: `0` todo verificado; `1` problemas de
integridad o un listado incompleto; `2` error de uso o de configuración. Sólo
`--cargar-exportacion` escribe, y sólo en el almacén destino. El resto únicamente lee:
`SELECT` en una transacción de sólo lectura, más `leer`, `tamano_de` y `listar`.

### Manifiesto v1 (`manifiesto.json`)

```text
formato    "ara-map.manifiesto-archivos"
version    1
creado_en  ISO-8601 UTC
finales[]  clave, tamano, sha256, version_id, archivo_id, inventory_id, tipo (pdf|kmz),
           estado, numero, actual, retirado, geometrias, eventos
pendientes[] version_id, archivo_id, inventory_id, tipo, numero, clave_temporal,
           tamano_declarado, sha256_declarado, iniciado_en, subida_vence_en, completar_antes_de
```

`finales` incluye cada `archivo_version` con `clave_final`, también las versiones superadas y
las de archivos retirados, porque son historial. Obligatorios en cada final: `clave`, `tamano`,
`sha256`, `tipo`, `version_id` y `archivo_id`. El verificador ignora las claves que no conoce.
Nunca incluye nombres de archivo originales. La definición completa está en
`server/recuperacion.py`.

### Exportación

La carpeta de exportación contiene `manifiesto.json` y cada objeto en la ruta de su clave
(`final/<id>/<nonce>`). Cada objeto se lee acotado y se comprueban su tamaño y su SHA-256
contra el manifiesto. Sólo los bytes verificados aparecen en la carpeta, de forma atómica.
Una copia local que ya coincide se vuelve a hashear y no se descarga otra vez; así se ahorra
el egreso gratuito. Una copia local corrupta se reemplaza y se reporta.

### Reporte

El reporte (`--json`) trae `correcto`, `conteos` (`ok`, `ausente`, `tamano_distinto`,
`sha_distinto`, `ilegible`) y `problemas[]` con clave, versión y tipo. También trae
`no_referenciados[]`, que son huérfanos: se reportan y nunca se borran. Además incluye
`staging[]` y `pendientes[]` con `staging_presente`, que no son error: tras restaurar se
cancelan o se reinician. `bytes` trae referenciados, no referenciados, staging, retenidos
contra el presupuesto y leídos del almacén. Con exportación se añade `exportacion`; con carga,
`carga` (`cargados`, `ya_presentes`, `problemas[]` con `copia_local_invalida` o
`conflicto_en_destino`).

A sigue siendo responsable de: congelar escrituras o fijar otro límite consistente al tomar
el `pg_dump`, de restablecer sesiones y leases tras restaurar, y de la guía del operador.

## Evidencia

Todo lo siguiente es **local**: SQLite, Postgres 16 desechable y almacenes en carpeta o en
memoria. No es evidencia de Supabase ni de Render.

- `evidencia/ensayo-restauracion-postgres.txt`: `ensayo_restauracion.py` corre la secuencia
  completa: datos sintéticos por el ciclo real (tres versiones de KMZ con geometría e
  historial, un PDF, un pendiente sin staging y un huérfano), `pg_dump` y `pg_restore` a otra
  base, exportación con referencias de la base restaurada, export incremental con 0 bytes
  leídos, carga en un bucket nuevo y verificación de la base restaurada contra el bucket
  restaurado. Después detecta un objeto faltante y uno corrupto. Las filas restauradas son
  iguales a las de origen.
- Suite: `python3 -m unittest discover` en verde, salvo
  `test_the_system_python_has_no_openpyxl_of_its_own`, que falla porque este contenedor trae
  openpyxl en el Python del sistema (no tiene relación con el cambio). Las suites de archivos,
  recuperación y adaptador pasan también contra Postgres desechable (284 pruebas). ruff y mypy
  están limpios en `server/` y `tests/`. No se probó con Python 3.9 de macOS. CI corre
  Python + Postgres.

## Pendiente en el proveedor real (no probado; los mocks no cuentan)

`prueba_proveedor.py` está listo y sólo debe ejecutarse con autorización, contra un bucket
privado **de prueba**, con la credencial que usará el host. Escribe únicamente claves con un
id aleatorio de la corrida y las borra al terminar. Comprueba:

1. reemplazo de staging y lectura inmediata (sin caché vieja) y `tamano_de`;
2. creación sin sobrescritura: la segunda copia termina en `ColisionError`, y si el mapeo
   difiere se reporta el código real;
3. carrera de dos creaciones con un solo ganador;
4. lectura acotada, objeto ausente y listado;
5. que no haya lectura anónima, ni por ruta pública ni por ruta privada;
6. que una credencial rechazada sea un fallo no reintentable, no un 401/403 de la aplicación;
7. con `--grandes`, ida y vuelta de 20 MiB y 25 MiB con SHA idéntico y tiempo. Esto consume
   unos 90 MiB de cuota y egreso.

Siguen pendientes para la prueba en el host (A, tras la autorización): transferencias
completas de 20/25 MiB a través de Render, cuota llena o proyecto pausado, y respaldo y
restauración contra el bucket real. Si aparece una diferencia concreta (por ejemplo, otro
código para el duplicado), B propone la corrección mínima en `server/almacen_supabase.py`.
