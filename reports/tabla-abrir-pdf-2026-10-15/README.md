# Abrir PDF desde la celda de la tabla (issue #48)

15 de octubre de 2026. Rama `claude/compassionate-lovelace-ycq06u`, desde
`origin/main` en `ef5066e`. Sin cambios de API, esquema, almacenamiento,
despliegue ni datos. Capturas con datos y cuentas ficticias
(`tests/e2e/tabla-abrir-pdf.mjs`, `ABRIR_CAPTURAS=…`).

## Qué cambia

- **«1 PDF»** es un botón con aspecto de enlace: abre ese PDF guardado en una
  pestaña nueva, sin pasar por el detalle.
- **Varios PDF** («3 PDF»): el contador abre una lista pequeña con los nombres
  (como texto). Elegir uno lo abre en una pestaña nueva. Si el resumen sólo
  trae los cinco adjuntos más recientes («22 adjuntos PDF»), la lista se pide
  al pulsar a la ruta autorizada existente, por páginas («Cargar más»).
- Sin PDF, subidas sin terminar, vencidas o rechazadas: texto, no enlace, y no
  aparecen en la lista. Un PDF guardado con un reemplazo fallido sigue
  abriéndose (su versión guardada).
- «Elegir PDF…», la subida, el KMZ y el detalle no cambian de comportamiento.

## Cómo abre

`web/components/archivos/abrirPdf.js` es el flujo único que ahora usan la
celda y los botones «Abrir» / «Abrir guardada» del detalle:

1. La pestaña se reserva en el mismo clic (compatible con bloqueadores de
   ventanas emergentes) y se separa de la aplicación (`opener = null`).
2. Los bytes llegan por la descarga autenticada de siempre
   (`cliente.descargar`: límite de tamaño, versión y SHA-256 comprobados).
   Nada de URLs públicas, firmadas ni del bucket.
3. Si falla o se cancela, la pestaña reservada se cierra: no quedan pestañas
   vacías. Si el navegador la bloqueó, la celda ofrece «Abrir el PDF» como
   enlace normal.
4. La URL temporal (`blob:`) se revoca a los 60 s o al terminar la sesión; no
   al repintar la tabla, para no romper una pestaña que todavía carga.

Lista y descarga se piden sólo al pulsar. Un segundo clic durante la descarga
no abre otra pestaña. Cerrar la lista (Escape, «Cerrar» o un clic fuera)
cancela también la apertura elegida en ella y cierra su pestaña reservada:
el PDF no aparece después. Desmontar la celda, cambiar de vista o de cuenta,
perder la sesión o recargar la página cancelan lo pendiente y descartan
respuestas atrasadas. Un 404 se comprueba con la lista del terreno (misma
regla del detalle): si el terreno sigue, se avisa y se actualiza el resumen;
si no, la tabla lo revalida y quita la fila.

«Borrar» (`/api/archivos/:id/borrar`) elimina el adjunto y todas sus
versiones. Un enlace dibujado antes del borrado recibe el 404 real del
servidor desechable (la prueba no intercepta la descarga): no se abre nada,
la pestaña reservada se cierra, la fila sigue y su resumen pasa a «Sin PDF»
(o de «3 PDF» a «2 PDF» desde la lista).

## Capturas

- `01-enlace-1-pdf.png`: enlaces «1 PDF», «3 PDF», «22 adjuntos PDF» junto a
  textos sin enlace.
- `02-selector-varios-pdf.png`: lista de tres PDF (un nombre con `<b>` se
  muestra como texto).
- `03-selector-paginado.png`: lista autorizada más allá del resumen reciente.
- `04-pestana-bloqueada.png`: aviso y enlace cuando el navegador bloquea la
  pestaña.

## Límites

- El nombre propio de una versión guardada anterior a una subida fallida del
  mismo adjunto no viene en el resumen ni en la lista: se muestra como «PDF
  guardado (versión anterior)» con la nota de lo que pasó.
- Verificado en Chromium (Playwright). Sin prueba manual en Safari/Firefox ni
  en el sitio publicado.
