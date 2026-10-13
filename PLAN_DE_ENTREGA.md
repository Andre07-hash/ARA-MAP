# ARA MAP — acuerdo de entrega y backlog

Actualizado: **12 de octubre de 2026**. Responsable del acuerdo: propietario y supervisor; equipos A y B implementan. Este es el punto de entrada para retomar el proyecto sin reconstruir las conversaciones.

**Prioridad: entregar ASAP un portal privado donde un empleado pueda editar terrenos existentes, adjuntar su KMZ, activar su polígono y conservar sus datos y archivos.** Terminar la conexión y comprobación del almacenamiento es el camino crítico. No abrir nuevas funcionalidades ni repetir fases aceptadas para alcanzar una perfección que no requiere este piloto.

Este acuerdo fija alcance, prioridades y criterios de entrega. El [paquete técnico F0](reports/free-private-pilot-2026-10-12/START_HERE.md) conserva los contratos de implementación. Las propuestas anteriores de Vercel/AWS, transferencias por partes y otros proveedores son antecedentes; no son tareas pendientes del piloto. Una instrucción posterior explícita del propietario puede cambiar este acuerdo; registrar ese cambio aquí.

## 1. Lo que vamos a entregar

- Portal **privado**, inicialmente para **50–100 terrenos**, con cuentas individuales y bases asignadas.
- Base inicialmente vacía; altas de cuentas y restablecimiento de contraseñas administrados por el operador.
- **Primero existen las filas de terrenos; después se adjunta un KMZ a cada terreno.** Crear filas automáticamente desde los polígonos de un KMZ no forma parte del encargo.
- Captura, edición, filtros e historial; PDF y KMZ con los permisos existentes; selección y activación explícita cuando corresponda.
- Mantener los límites existentes: **20 MiB por KMZ y 25 MiB por PDF**. El mapa muestra los límites de los terrenos de la página actual; esta limitación se comunica al empleado.
- Datos y archivos duraderos, acceso desde otra computadora y un respaldo que se pueda restaurar.
- **Sin tarjeta, método de pago ni exposición a cobros.** La disponibilidad de un piloto gratuito no equivale a un servicio siempre encendido.
- Conservar el frontend y el flujo aceptado. No hay un rediseño visual encargado.

## 2. Qué tenemos y qué todavía no significa “listo”

Esta es una fotografía del estado conocido al redactar el acuerdo, no una afirmación sobre futuros commits. CI verde, una entrega parcial y una prueba local no sustituyen la prueba del candidato integrado en el host real.

| Componente | Estado conocido | Lo que falta para la entrega |
| --- | --- | --- |
| Tabla maestra, cuentas, permisos, edición e historial | Implementados y con evidencia previa del núcleo aceptado de A | Reutilizar esa evidencia y comprobar el recorrido del empleado en el candidato final |
| PDF, parser KMZ, selección, activación y dibujo del polígono | Flujo existente con evidencia local; no se debe reconstruir | Conectarlo al almacenamiento duradero y probarlo desde la URL real |
| Entrada de servidor para Render | A publicó una primera entrega en #31; pruebas locales con Postgres | Integrar el adaptador de B y comprobar el comportamiento en Render |
| Carga inicial de terrenos | A preparó comando de operador con simulación, control de duplicados y ensayo de 100 filas | Usar ese camino comprobado para la tabla maestra; la importación Excel/CSV antigua escribe en otro espacio de datos |
| Adaptador de almacenamiento privado | B publicó una primera entrega en #32 con CI verde | Revisión e integración; terminar manejo esencial de fallos y herramientas de recuperación; comprobar el proveedor real |
| Respaldo y restauración | A ensayó la parte de base de datos | Completar y ensayar la recuperación conjunta de base de datos y archivos |
| Portal entregable en internet | No demostrado por estas entregas parciales | Configuración autorizada, despliegue del candidato exacto y recorrido final |

Referencias para no perder ni duplicar trabajo:

| Referencia | Commit del estado registrado | Tratamiento |
| --- | --- | --- |
| Núcleo A, [#29](https://github.com/Andre07-hash/ARA-MAP/pull/29) | `4670df7348265af66c640069e5ece2a274830fa3` | Base aceptada; preservar |
| Archivos/mapa B, [#28](https://github.com/Andre07-hash/ARA-MAP/pull/28) | `b2ac9bd176043fc4b1625b13993f8f21407dc978` | Ya integrado en A; no volver a integrarlo |
| Batching B, [#30](https://github.com/Andre07-hash/ARA-MAP/pull/30) | `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3` | Integrado una vez en #31 mediante `f81bc27`; no reasignar |
| Primera entrega A, [#31](https://github.com/Andre07-hash/ARA-MAP/pull/31) | `2177c5b77e1742905537476bddedbf49e0e3dd35` | CI exacto verde, [38324150175](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38324150175); todavía sin almacenamiento conectado |
| Primera entrega B, [#32](https://github.com/Andre07-hash/ARA-MAP/pull/32) | `9380ecc34af8a6b4fccdf387c066163c1dcdda59` | CI exacto verde, [38325006198](https://github.com/Andre07-hash/ARA-MAP/actions/runs/38325006198); no constituye aceptación independiente del adaptador |

Los avances nuevos deben actualizar este registro con su SHA y evidencia. Preservar también C1 y las ramas anteriores. La rama del supervisor contiene planificación; no confundir sus pruebas con las del código integrado de A/B.

## 3. Por qué PDF funciona localmente y el almacenamiento sigue pendiente

PDF y KMZ usan el mismo sistema de almacenamiento de archivos. En local puede guardar los bytes en el disco de la computadora. En el candidato alojado de A todavía no está conectado el almacén duradero: sus rutas de contenido responden `503 almacen_no_configurado`. Esto afecta a ambos formatos, no solamente a KMZ.

El KMZ además se procesa para producir geometría que se guarda en Postgres. Tener geometría o verla en el mapa no demuestra que el archivo original esté almacenado de forma duradera.

El fallo de KMZ que el propietario observó en localhost **todavía no tiene una causa confirmada en este registro**. Reproducirlo sobre la versión exacta y registrar el error. No atribuirlo automáticamente al almacenamiento del host ni rehacer el parser sin un fallo que lo justifique.

## 4. Ruta vigente y límites del piloto

**Render Free** sirve el frontend existente y el servidor Python desde el mismo origen; **Neon Free** conserva la base de datos, cuentas y geometría; **Supabase Free Storage privado** conserva los bytes de PDF/KMZ. El navegador continúa hablando con la aplicación y no recibe credenciales del almacén.

Esta ruta busca reutilizar las transferencias de archivo completo y reducir cambios. El cambio de plan sí tuvo coste de coordinación y dejó trabajo anterior conservado. No promete una fecha ni elimina la necesidad de verificar la integración. No volver a cambiar de proveedor salvo que aparezca un impedimento concreto para este piloto.

- El disco de Render no es el almacén definitivo. Sus pausas por inactividad y posibles suspensiones por cuota deben comunicarse; la operación no depende de que la Mac esté encendida.
- El presupuesto operativo inicial acordado es **700 MB decimales para archivos finales e historial retenido**, dejando margen para temporales y pruebas. Es un presupuesto que vigila el operador, no una cuota implementada en la aplicación.
- Contar terrenos no basta para estimar almacenamiento: inventariar tamaños reales antes de cargar datos. Cien terrenos con archivos cercanos a sus máximos no caben en el presupuesto gratuito.
- Confirmar las cuotas y condiciones de las cuentas reales antes de desplegar. Si no alcanzan o un proveedor exige tarjeta, registrar ese bloqueo específico; no activar pagos ni borrar historial para resolverlo.

Las fuentes y los límites de proveedor consultados están en el [paquete F0](reports/free-private-pilot-2026-10-12/START_HERE.md). No se garantiza capacidad ilimitada ni disponibilidad continua.

## 5. Lo absolutamente necesario antes de entregar

Estas casillas están pendientes de cierre con evidencia del candidato integrado. No significan que haya que volver a implementar las partes que ya funcionan.

- [ ] **KMZ útil para el empleado:** abrir una fila existente, subir un KMZ válido, seleccionar cuando haya varios candidatos, activar y ver el límite, incluso sin X/Y. Un reemplazo inválido conserva el límite anterior. Cerrar cualquier fallo local reproducible de este recorrido.
- [ ] **Archivos duraderos:** integrar el adaptador, configuración y dependencia de B en A. Subida y descarga de PDF/KMZ funcionan a los tamaños permitidos; los bytes descargados coinciden. Probar los fallos esenciales de permisos, transferencia interrumpida y proveedor sin corromper ni borrar lo ya guardado. Una configuración ausente no crea pendientes nuevos inútiles.
- [ ] **URL y acceso reales:** desplegar el candidato exacto en el entorno gratuito autorizado, con cuentas y bases asignadas. El empleado puede entrar, cargar/crear las filas por el camino aprobado, editar y guardar desde otra computadora. No depende del servidor local del desarrollador.
- [ ] **Recorrido integrado breve:** editar un terreno, adjuntar KMZ y PDF, activar el polígono, descargar, cerrar sesión y volver a entrar; comprobar acceso denegado fuera del alcance. Reiniciar o redesplegar y verificar que sobreviven filas, historial, geometría y archivos. Comprobar una operación cercana al límite en memoria/tiempo del host real y su despertar tras inactividad. Reutilizar pruebas previas que no cambien.
- [ ] **Recuperación mínima y entrega al operador:** respaldo consistente de base de datos y archivos referenciados, guardado fuera del host efímero y del único almacén en uso; una restauración ensayada en destino desechable verifica contenido e integridad. Puede ser manual. Entregar guía corta en español, responsable de respaldo diario y revisión de cuotas, y contacto de soporte.

**Bloquean la entrega:** KMZ/PDF o edición esencial rotos, acceso indebido, pérdida/corrupción de datos, archivos no duraderos, recuperación fallida o capacidad insuficiente para la carga prevista. Un defecto menor se registra con su impacto y solución provisional; no reabre por sí solo una fase aceptada.

No se exige automatizar operaciones ni realizar una campaña nueva de rendimiento masivo para cerrar estas casillas. Tampoco se sustituye la seguridad de archivos por una demostración visual que sólo funcione una vez.

## 6. Trabajo inmediato, en paralelo

| Responsable | Siguiente resultado necesario |
| --- | --- |
| **B** | Terminar almacenamiento privado, manejo esencial de errores del ciclo de archivos y verificación/exportación para recuperación. Publicar commits utilizables con contrato, dependencia y evidencia; no esperar un reporte perfecto para pasarlos a A |
| **A** | Integrar el SHA publicado de B después de revisión enfocada; cerrar configuración y candidato combinado. Continuar en paralelo carga inicial, acceso del empleado, guía y preparación del despliegue/restauración |
| **Supervisor** | Revisar avances contra las cinco casillas, distinguir defecto bloqueante de backlog y mantener este registro. Revisar lo entregado antes de emitir tareas nuevas |
| **Propietario / operador autorizado** | Autorizar y ejecutar las operaciones externas concretas, confirmar cuentas/recursos gratuitos, carga prevista, acceso y responsable de respaldos |

A y B son sesiones externas en computadoras y cuentas distintas. El propietario transmite los SHA, enlaces y entregas; no presuponer carpetas locales compartidas ni acceso al chat del otro. Cada equipo puede usar hasta tres agentes dentro de su capacidad existente, con archivos separados y un integrador; no comprar capacidad ni duplicar trabajo sobre el mismo archivo.

No es necesario detener a todos mientras llega una parte. A prepara e integra; B termina almacenamiento y recuperación. No hacer merges duplicados ni modificar la rama del otro equipo. Este documento no autoriza por sí mismo merges de PR/main, crear recursos/cuentas, cambiar secretos, desplegar ni cargar datos reales.

## 7. Backlog: después de la entrega

Mantener estos temas visibles para priorizarlos durante el mantenimiento mensual. Estar en esta lista no autoriza implementarlos automáticamente ni los convierte en condición de entrega.

| Tema | Tratamiento después del piloto |
| --- | --- |
| Pulido visual, textos y pequeños detalles de interacción | Corregir según uso real; mantener el frontend aceptado para la primera entrega |
| Importador Excel/CSV unificado en la tabla maestra | Mejorar la experiencia; para la carga inicial sirve el comando de operador ya preparado |
| Creación de terrenos a partir de polígonos KMZ | Sólo si el propietario la solicita; el flujo actual parte de filas existentes |
| Catálogos públicos por base y nuevas vistas/reportes | Evaluar después de que el portal privado esté funcionando |
| Registro autónomo y recuperación de contraseña por correo | Mantener cuentas administradas al inicio |
| Automatización de respaldos, alertas y operación | La primera entrega requiere recuperación comprobada, aunque sea manual |
| Alta disponibilidad, evitar pausas y ampliar capacidad | Requiere una nueva decisión de servicio/presupuesto; no incorporar cargos ahora |
| Estudios para miles de terrenos, pendiente de memoria y benchmarks amplios | Aplazados; investigar antes sólo si el piloto real presenta un fallo o falta de capacidad |
| Más polígonos simultáneos, mapa fuera de la página actual y funciones avanzadas | Evaluar con el uso del empleado; comunicar el alcance actual |
| Conexión automática Excel/OneDrive, BigQuery e importación histórica | Permanecen aplazados; conservar el trabajo anterior |
| Bloqueo de base durante carga inicial frente a archivo concurrente | Mejora posterior si la carga se hace antes de abrir el portal al trabajo concurrente; reevaluar si esa condición cambia |
| Límite de 4 MiB mostrado por la configuración del importador antiguo | No confundirlo con los adjuntos de 20/25 MiB. Corregir si afecta el flujo obligatorio; aclaración menor en otro caso |

Un tema sale del backlog y bloquea sólo si hay evidencia de que impide el flujo obligatorio, expone datos, compromete su integridad/recuperación o incumple una restricción acordada. Registrar esa evidencia y la corrección mínima; no ampliar el encargo por hipótesis.

## 8. Cómo retomar y mantener este acuerdo

1. Leer este documento antes de emitir instrucciones a A/B o retomar una sesión.
2. Pedir o leer las entregas publicadas más recientes; registrar SHA, integración y evidencia. No tratar las fotografías anteriores como estado actual.
3. Actualizar las cinco casillas sólo con evidencia y enlace a su reporte. Distinguir «implementado», «probado localmente», «probado en proveedor» y «entregado».
4. Añadir los detalles menores al backlog con impacto y responsable. Evitar asignarlos mientras retrasen el almacenamiento o la entrega esencial.
5. Registrar aquí las decisiones nuevas del propietario y el motivo. No cambiar arquitectura ni frontend silenciosamente.

**Condición final de entrega:** el empleado entra desde una URL, trabaja en su tabla, adjunta el KMZ a su terreno y ve su límite; sus cambios y archivos sobreviven al reinicio y pueden recuperarse. Después se priorizan las mejoras del mantenimiento mensual.
