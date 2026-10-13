# ARA Map — guía de inicio del portal privado

Para quien entra por primera vez. Cinco minutos de lectura.

## 1. Entrar y salir

- Abre la dirección que te dio el operador y escribe tu usuario y contraseña.
- **Si nadie ha usado el portal en un rato, la primera página tarda cerca de un
  minuto en abrir.** Es normal en este piloto: espera, no recargues varias veces.
- Tu cuenta y tu contraseña las crea el operador. **No hay "olvidé mi
  contraseña":** si la pierdes, pídele que la restablezca.
- Después de 5 intentos fallidos la cuenta espera 15 minutos antes de aceptar
  otro intento.
- La sesión dura 12 horas. Usa **Cerrar sesión** al terminar en un equipo
  compartido.

## 2. Qué puedes hacer

| Rol | Puede |
|---|---|
| **Administrador** | Todo: crear bases de trabajo, dar y quitar accesos, ver la tabla maestra de todas las bases, archivar, restaurar y transferir terrenos. |
| **Operador** | Trabajar solo en las bases que un administrador le asignó. |

Si entras y no ves ninguna base, todavía no te han dado acceso: avisa a un
administrador. Los accesos se manejan en **Bases de trabajo y accesos**.

## 3. La tabla

- **Tabla** muestra los terrenos de la base elegida. Escribe en una celda para
  cambiarla; se guarda con Enter o al salir de la celda, y Esc lo cancela.
- **Nuevo terreno** agrega un renglón en blanco. La carga inicial de muchos
  terrenos desde un archivo la hace el operador, no el portal.
- Cada base puede tener columnas propias, que solo existen en esa base.
- Un terreno **Archivado** deja de poder editarse; **Restaurar** lo regresa.
- **Transferir a otra base…** mueve un terreno entre bases (según tu rol).
- Los datos se guardan como los escribes: nada se convierte ni se calcula.
  En los archivos de ARA, **X es la latitud e Y la longitud**.

## 4. Archivos de un terreno: PDF y KMZ

En la tabla, las columnas **Archivos** y **KMZ** tienen los botones
**Elegir PDF…** y **Elegir KMZ…** de cada renglón: el archivo queda en ese
terreno. Aparecen solo en los renglones que puedes cambiar. El detalle del
terreno (⋯) tiene los mismos botones, además de descargas, versiones,
historial y retiro.

- Tamaño máximo: **PDF 25 MB, KMZ 20 MB**. Un archivo vacío no se acepta.
- **No cierres ni recargues la pestaña** hasta que termine la subida.
- Tienes 15 minutos para que termine la subida. Si se acaba el tiempo,
  cancélala y vuelve a empezar.
- Puedes tener hasta 5 subidas pendientes a la vez.
- **Descargar** baja el archivo y lo comprueba completo antes de entregártelo;
  con archivos grandes tarda unos segundos.
- **Historial** muestra las versiones anteriores. **Retirar…** quita el
  archivo vigente sin borrar su historial.

## 5. El contorno del terreno (KMZ)

Subir un KMZ, desde la tabla o desde el detalle, da uno de estos resultados:

| El KMZ trae… | Qué pasa al terminar la subida | Qué haces tú |
|---|---|---|
| **Un solo contorno válido** | Queda como el contorno activo del terreno (si había otro, lo sustituye). La celda dice **Contorno activo**. | Nada más. |
| **Varios contornos** | No se activa nada; el contorno anterior, si había, sigue. La celda dice **KMZ sin contorno activo** y «Varios contornos: elige en el detalle (⋯)». | Abre el detalle (⋯) → **Versiones** → **Contornos** → **Elegir contornos…**, marca el correcto, **Procesar selección** y luego **Activar este contorno**. |
| **Ningún contorno utilizable** | El archivo se guarda, pero el contorno anterior se conserva. | Revisa el KMZ y súbelo de nuevo. |

El contorno se dibuja aunque el terreno no tenga X e Y.

## 6. El mapa

**Mapa de esta página** dibuja los terrenos de la página de la tabla que estás
viendo, con sus contornos. Un terreno sin coordenadas válidas y sin contorno
no aparece: nunca se coloca a la adivina.

## 7. Mensajes que puedes ver

El texto exacto en pantalla puede variar un poco.

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| Inicia sesión para continuar | La sesión terminó | Vuelve a entrar; lo que no se guardó hay que repetirlo |
| Solo lectura / sin permiso | Te quitaron el acceso, o la base o el terreno se archivó | Pregunta a un administrador |
| El sistema está ocupado | Otro cambio se está guardando | Espera unos segundos y repite |
| El almacenamiento de archivos no está disponible | Falla temporal del servicio de archivos | Intenta más tarde; si sigue, avisa al operador |
| El plazo para subir terminó | Pasaron los 15 minutos | Cancela la subida y empieza otra |
| El archivo descargado no coincide | La descarga llegó dañada | Vuelve a descargar; si se repite, avisa al operador |

## 8. A quién acudir

- **Cuenta, contraseña, acceso bloqueado:** al operador.
- **Acceso a una base:** a un administrador.

## 9. Límites de este piloto

- El espacio para archivos es limitado y compartido por todos los terrenos:
  sube solo los PDF y KMZ que hagan falta, y avisa al operador antes de subir
  muchos archivos grandes.
- El servicio puede tardar en despertar y no está garantizado las 24 horas.
- Todavía no hay catálogos públicos, cambio de contraseña por el propio
  usuario ni carga de los datos históricos.
