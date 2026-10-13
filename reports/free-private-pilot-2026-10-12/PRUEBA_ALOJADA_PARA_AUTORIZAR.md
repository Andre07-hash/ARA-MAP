# Prueba alojada autorizada — candidato y alcance

12 de octubre de 2026, hora de México. **AUTORIZADA por el propietario mediante respuesta explícita «si» a este alcance.** A ejecuta y B da soporte. Se conserva el nombre del archivo para no romper enlaces de la propuesta anterior. Continúa el [acuerdo de entrega](../../PLAN_DE_ENTREGA.md). Este registro acredita autorización, no ejecución.

## Cierre del hito local

- Candidato: `31b6a1dba827b57d448a2aeb62ad10c05db09afc`, PR draft #31, rama `codex/team-a-free-pilot-v1`.
- B integrado: `071d7d05c985167c9ea3efac5d8ac6eb2b3819a6`, por merge local `f2bf329`; ascendencia confirmada.
- [CI exacto de A 38336981960](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38336981960) aprobado en JavaScript y Python/Postgres. B conserva [CI 38334388640](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38334388640) verde.
- El supervisor revisó el delta, el checklist y la configuración Render; ejecutó la prueba `InicioConAlmacenNoConstruible` del candidato aislado: aprobada. Comprueba 503 sin pendiente nuevo, 401/404, replay 200 y conflicto de idempotencia 409.
- A reporta 1.447 pruebas Postgres, checks normales limpios, 30 comprobaciones API locales y pruebas SDK locales de exportación por entorno/carga/verificación, incluida corrupción del mismo tamaño detectada por el verificador. No se reejecutaron independientemente aquí esas suites completas.
- La CI no instala el SDK y omite esas pruebas; no sustituye la evidencia local con el lock ni la prueba real del proveedor.
- Frontend idéntico a `4670df7`, hash `2db407fea780732c173caa56bde824e064d33259`. Los 41 recorridos anteriores de Chrome son locales; falta navegador sobre el servicio alojado.

**Decisión del supervisor:** candidato apto para iniciar la prueba alojada autorizada. No se requiere otra ronda de funcionalidades o integración. No se declara aún entregable para datos de empleados.

## Autoridad documental

El [checklist de A fijado al candidato](https://github.com/Andre07-hash/ARA-MAP/blob/31b6a1dba827b57d448a2aeb62ad10c05db09afc/reports/team-a-free-pilot-2026-10-12/OPERATOR_CHECKLIST.md) es la guía operativa. Secuencia: exportador/verificador B → cargador A → verificación obligatoria de tamaño/SHA del destino. «Ya estaban» sólo comprueba tamaño; por sí solo no acepta una recuperación.

El reporte antiguo de B aún muestra su opción `--cargar-exportacion`. Es una diferencia documental conocida, fuera de la secuencia elegida. No exige un nuevo commit antes del ensayo ni reintegrar B. Se puede alinear después; el cuerpo actual de #32 y el checklist de A ya aclaran la decisión. B queda disponible para fallos concretos, sin nuevas tareas de desarrollo.

## Operaciones autorizadas por el propietario

Responsable: equipo A u operador designado por el propietario, con B como soporte de archivos. Las cuentas quedan bajo control del propietario; el acceso se concede de forma segura, sin copiar claves o contraseñas al chat ni al repositorio. No se presume que A y B comparten acceso.

1. Comprobar acceso y cupo en cuentas **Free sin tarjeta** de Render, Neon y Supabase. Si falta cuenta, crearla sólo bajo esta autorización y control del propietario. Si se exige pago/tarjeta o no hay capacidad gratuita, parar esa operación e informar el impedimento concreto; no cambiar de plan automáticamente.
2. Preparar recursos nuevos y aislados de prueba: un servicio web Render Free, un proyecto Neon con base vacía y destino separado de restauración, un proyecto Supabase Storage con bucket privado de prueba y bucket privado separado para restauración. Pueden necesitarse nombres únicos; registrar los identificadores efectivos. No reutilizar bases ni archivos reales.
3. Inicializar y comprobar esquema; configurar en el servicio las cinco variables del checklist mediante ajustes privados; crear tres cuentas ficticias (administrador, operador autorizado y operador sin concesión). No modificar cuentas existentes.
4. Desplegar manualmente el SHA exacto `31b6a1dba827b57d448a2aeb62ad10c05db09afc`, con despliegue automático desactivado, sin merge de PR/main. Registrar SHA efectivo, URL y deploy id. Un resultado distinto no se atribuye a este candidato.
5. Ejecutar los guiones preparados y el recorrido de navegador con datos ficticios: carga de 50–100 filas, edición, KMZ con selección/activación, PDF, límites completos de archivo, descarga idéntica, autorización y denegación, cambio de permisos durante finalización, conservación del contorno anterior ante reemplazo inválido.
6. Comprobar comportamiento real del almacén (privacidad, no sobrescritura, lectura tras reemplazo), despertar, memoria/duración y persistencia tras redesplegar el mismo candidato. La prueba del proveedor sólo usa el bucket de prueba y sus claves aleatorias; su limpieza sólo alcanza esos objetos de prueba.
7. Exportar respaldo de base y archivos, restaurarlo en destinos nuevos y ejecutar la verificación final y recorrido de lectura. Mantener las copias en carpeta privada externa al host efímero y al único bucket vivo. Registrar resultado, uso de almacenamiento y responsable.

Estas operaciones usan únicamente la capacidad gratuita disponible. Las pruebas grandes y sus copias consumen almacenamiento/egreso: contabilizarlos y mantenerse dentro del presupuesto, sin cargos. No implica cargar los 50–100 terrenos reales ni abrir el servicio a empleados todavía.

Los fallos concretos se reportan con paso, error saneado y versión; A/B ya tienen encargo de correcciones mínimas en ramas. Si una corrección modifica el candidato, publicar su SHA y checks antes de proponer su redespliegue; no continuar usando una rama móvil sin identificar la versión.

## Resultado esperado del ensayo

Una URL privada probada desde navegador, PDF/KMZ persistentes a los tamaños acordados, permisos correctos y respaldo restaurable. Entregar evidencia breve del proveedor real y pendientes clasificados por impacto. No bloquear por pulido documental o visual; sí por un fallo del flujo obligatorio, seguridad, integridad, recuperación o capacidad.

Después se decide la entrega al empleado, sus cuentas y la carga real. El fallo histórico de localhost permanece sin diagnóstico de archivo/build; no se considera corregido por inferencia. Se prueba un KMZ representativo del trabajo esperado y se atiende cualquier fallo reproducible del recorrido obligatorio.

## Estado de autorización

**AUTORIZADA.** El propietario respondió «si» a: autorizar al equipo A, con B como soporte, a preparar recursos gratuitos de prueba en cuentas bajo su control, configurar secretos, crear cuentas ficticias, desplegar `31b6a1d` y ejecutar las pruebas; sin tarjeta, cobros, datos reales ni merge a main. Fecha local: 12 de octubre de 2026.

Esta autorización sustituye las retenciones anteriores de operaciones externas sólo dentro de ese alcance. No volver a pedir permiso por cada paso ya aprobado. Si falta acceso, solicitar únicamente la intervención concreta del propietario (por ejemplo, iniciar sesión o completar MFA), sin pedir secretos por chat. Si una operación exige tarjeta/cargos o afecta recursos reales, detener esa operación y comunicar el impedimento. La entrega al empleado y la carga real siguen fuera de esta autorización.

## Instrucciones de ejecución para A

El propietario autorizó expresamente la prueba alojada. Continúa en tu sesión; no necesitas otra aprobación para ejecutar los pasos 1–7 de este documento dentro de sus límites. Consulta el checklist fijado al candidato. Las notas antiguas «awaiting operator release» ya quedan superadas para este ensayo.

1. Comprueba acceso a las cuentas del propietario y capacidad Free sin tarjeta. Prepara recursos nuevos de prueba y destinos separados de restauración. Si necesitas una sesión del propietario o MFA, identifica exactamente dónde; continúa entretanto los pasos independientes.
2. Configura esquema, variables privadas y tres cuentas ficticias; despliega manualmente `31b6a1dba827b57d448a2aeb62ad10c05db09afc`, con auto-deploy desactivado. Comprueba el SHA realmente desplegado y comparte URL/deploy id en cuanto estén disponibles, indicando que son de prueba.
3. Ejecuta `humo_hospedado.py`, carga sintética de 50–100 filas y recorrido del empleado en navegador. Comprueba KMZ de 20 MiB, PDF de 25 MiB, selección/activación, permisos, reemplazo inválido, persistencia al redesplegar y límites reales del host.
4. Puedes ejecutar tú el guion `prueba_proveedor.py` preparado por B contra el bucket de prueba, usando el entorno seguro disponible. Comparte con B sólo resultados saneados; no es necesario darle claves por chat ni crear otro entorno para él.
5. Ejecuta respaldo/restauración en destinos separados y verificación final de tamaño/SHA, siguiendo exportador B → cargador A → verificador B. No aceptar «ya estaban» como prueba de integridad.
6. Registra resultados reales, consumo de cuotas, URL, SHA, limitaciones y fallos concretos. No ampliar alcance, tocar frontend por pulido, comprar servicios ni cargar datos reales. Mantén la aplicación privada.

## Instrucciones de soporte para B

La prueba alojada está autorizada y A la coordina. Mantén el head `071d7d0` como referencia integrada; no abras nuevas funcionalidades ni retrases el ensayo por el documento antiguo.

Apoya a A con el guion de proveedor, interpretación de resultados saneados y correcciones mínimas si aparece una incompatibilidad real. A puede ejecutar tu guion dentro de su entorno seguro. Si operas tú, coordina antes el destino exacto y usa únicamente los recursos ficticios autorizados, sin duplicar provisión ni asumir acceso a cuentas de A. Sigue fuera de alcance cualquier recurso real, pago, secreto en chat, cambio a la rama de A o merge de PR/main.
