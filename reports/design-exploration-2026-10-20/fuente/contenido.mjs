// The report's text, written once and rendered both as README.md and as the
// comparison page (index.html). Spanish, as the deliverable.

export const META = {
  titulo: "ARA Map · Exploración de diseño",
  fecha: "20 de octubre de 2026",
  commit: "6b208660b17bb3d3823742499d6062d5558018e5",
  commitCorto: "6b20866",
  commitTitulo: "Merge pull request #64 from Andre07-hash/claude/tabla-filtro-tipos-varios",
  rama: "claude/vigilant-galileo-s6ogeo",
  skill: "dickwu/apple-design-skill @ 914b6a3",
};

export const VERIFICACION = {
  hecho: [
    "Leí AGENTS.md, CLAUDE.md, docs/DESARROLLO.md y README.md de la base vigente, y el código de web/ (app.js, Tabla.js, mapaPaneles.js, dialogos.js, tabla.js, tokens.css) y server/auth.py (roles y capacidades).",
    "Ejecuté la app local con el servidor desechable de pruebas (tests/e2e/tabla_servidor.py): SQLite temporal en el scratchpad, cuentas ficticias de administración (ada) y de operación (olga, omar).",
    "Sembré por la API y la interfaz 54 terrenos ficticios en 2 bases de trabajo y 2 sin asignar, 4 columnas personalizadas (opción, fecha, texto) y 11 archivos PDF/KMZ/KML, incluido un KML con 2 contornos.",
    "Recorrí con Chromium (Playwright) tabla, mapa, selección, detalle (⋯), edición de una celda con guardado lento simulado, selección múltiple, columnas, bases heredadas, catálogo y anchos de 1440, 1024 y 390 px, como administradora y como operadora. Las capturas están en actual/.",
  ],
  noHecho: [
    "No toqué el sitio publicado, Render, Neon ni Supabase. Ninguna captura procede de producción.",
    "Los mosaicos de los mapas base no cargaron en el entorno aislado: en las capturas actuales el mapa aparece sin fondo. No evalué la legibilidad sobre Satélite.",
    "No probé con lector de pantalla, con teléfonos reales ni con usuarios. Las afirmaciones sobre uso son hipótesis.",
    "No modifiqué código funcional. Los mockups son HTML/CSS estáticos aparte de la app.",
  ],
};

export const CONTEXTO = {
  hipotesis: `La computadora es el entorno principal. Lo sostienen: una tabla de 14 columnas básicas más las de cada base, edición tipo hoja de cálculo con flechas, Enter/F2, Tab y Esc (Tabla.js), el origen en Excel («Registro Análisis»), los KMZ que se producen en herramientas de escritorio, el lanzador «ARA Map.command» para macOS y unas pruebas de navegador que corren a 1500 × 900. La app ya tiene reglas responsive, pero a 390 px la cabecera y los seis controles de filtro ocupan la primera pantalla y la tabla exige desplazamiento horizontal. Supongo que en el teléfono se consulta (buscar, ubicar, abrir un PDF) y se corrige poco. Falta confirmarlo con usuarios: ¿hay visitas de campo? ¿se suben fotos JPG desde el teléfono?`,
  roles: [
    ["Administración", "Tabla maestra (todas las bases y «Sin asignar»); crea, renombra y borra bases; concede accesos; transfiere terrenos; usa las herramientas heredadas (bases importadas, mapas guardados, formatos, importar y exportar); borra terrenos publicados."],
    ["Operación", "Sólo las bases que tiene concedidas. Ve, edita y borra terrenos no publicados; gestiona las columnas de su base; sube y borra archivos. No ve la tabla maestra ni las herramientas."],
    ["Visitante", "Catálogo público, sin datos privados."],
    ["Sólo lectura", "Modo de instalación (ARA_MAP_READ_ONLY): se puede leer y descargar, no escribir."],
  ],
  tareas: {
    frecuentes: ["Filtrar y buscar terrenos de una base", "Capturar y corregir datos celda por celda", "Adjuntar PDF/JPG y KMZ/KML", "Ver en el mapa la distribución por Asking $/m²", "Revisar un terreno: datos, ubicación y archivos"],
    delicadas: ["Borrar un terreno (borra también sus archivos)", "Transferir terrenos entre bases", "Elegir el contorno cuando un KMZ trae varios", "Resolver un conflicto de edición", "No interrumpir una subida", "Borrar una columna de la base o cambiar accesos"],
  },
  relacion: `Tabla / Mapa es un conmutador dentro de la misma vista. El mapa reúne todos los terrenos de la consulta, no sólo la página, y comparte la selección. Los filtros de la tabla (Buscar, Estado, Municipio, Tipo, Ordenar) acotan ese conjunto; en el mapa quedan ocultos tras «Filtros de la tabla (N)». El mapa tiene además filtros propios (superficie, Asking price, Asking $/m², «Solo con ubicación») que no llegan a la tabla y se borran al salir. La ficha del mapa es de sólo lectura. El detalle (⋯) es un diálogo modal con los datos en sólo lectura, los archivos y las acciones Historial, Transferir y Borrar. Sólo se edita en las celdas.`,
  guardado: `Se guarda por celda y con versión. Los estados son «guardando», «sin guardar», «en conflicto» y «sin confirmar». Una respuesta perdida se comprueba con el servidor antes de reenviar. El resultado aparece en el pie de la ventana («Guardado · Superficie · versión 3»). La app avisa antes de salir si hay cambios o subidas sin terminar.`,
};

export const DIAGNOSTICO = [
  {
    titulo: "Dos sistemas de filtros que no se hablan",
    evidencia: "La tabla filtra por Buscar, Estado, Municipio, Tipo y Ordenar. El mapa tiene otro riel con Buscar, Estado, Municipio, Tipo, Superficie, Asking price, Asking $/m² y «Solo con ubicación». En el mapa, los filtros de la tabla quedan tras «Filtros de la tabla (1)», y los del mapa se borran al salir de la vista (mapaPaneles.js). Con «Apaseo» buscado en la tabla, el mapa muestra 1 terreno de 1 (captura 16).",
    tarea: "Encontrar y comparar",
    consecuencia: "No se sabe qué conjunto está a la vista. El precio sólo se puede filtrar en el mapa, y al buscar un terreno desaparece su entorno.",
    cambio: "Un solo modelo de filtros para todas las vistas, visible como chips y con el alcance en palabras («22 de 48 · 20 en el mapa · 2 sin ubicación»).",
    actual: "16-admin-mapa-seleccion.png",
  },
  {
    titulo: "Tres versiones del terreno y ninguna completa",
    evidencia: "La fila es editable. El detalle (⋯) es un modal con datos en sólo lectura, archivos y acciones. La ficha del mapa dice «Ficha de solo lectura. Para editar, subir, activar o retirar archivos usa la tabla» (captura 58).",
    tarea: "Revisar y corregir un terreno",
    consecuencia: "Para corregir algo visto en el mapa hay que volver a la tabla, encontrar la fila, desplazarse a la derecha y editar la celda.",
    cambio: "Una sola ficha editable, la misma en la tabla y en el mapa, con datos, ubicación, archivos, columnas de la base e historial.",
    actual: "58-ficha-abajo.png",
  },
  {
    titulo: "Archivos y ubicación al final de la fila",
    evidencia: "PDF y KMZ son las columnas 13 y 14, después de X e Y (capturas 11 y 12). Cada fila repite «Elegir PDF o JPG…» y «Elegir KMZ o KML…»: 96 botones en 48 filas. La tabla no dice si un terreno saldrá como punto, como contorno o no saldrá.",
    tarea: "Saber qué falta y adjuntar archivos",
    consecuencia: "Para saber si hay PDF o contorno hay que desplazarse en horizontal. Los botones repetidos meten ruido en todas las filas.",
    cambio: "Ubicación (forma + texto) y documentos junto al nombre. Las acciones de subida pasan a la ficha, al menú de la fila y a arrastrar el archivo.",
    actual: "12-admin-tabla-scroll-derecha.png",
  },
  {
    titulo: "El estado de guardado está lejos y dura poco",
    evidencia: "«(guardando)» aparece en la celda y «Guardado · Superficie · versión 3» en el pie, a unos 600 px de la celda (capturas 52 y 53). El saludo «Hola, Ada Ficticia» tapa ese pie al entrar.",
    tarea: "Saber si lo capturado quedó guardado",
    consecuencia: "Quien edita varias celdas seguidas no tiene un lugar fijo que le confirme que todo quedó guardado. La HIG desaconseja poner información crítica en la parte inferior de la ventana (layout.md › Desktop).",
    cambio: "Un indicador fijo en la barra superior («Todo guardado», «Guardando 1 cambio», «1 conflicto · Revisar») además del estado de la celda.",
    actual: "53-guardado.png",
  },
  {
    titulo: "«Base» significa dos cosas",
    evidencia: "El menú «Bases» lleva a los archivos Excel heredados (vacío; captura 20), mientras las bases de trabajo están en el selector «Vista» y en «Bases y accesos». «Tabla maestra» aparece activa aunque se esté viendo una base concreta. Los encabezados mezclan «Asking price», «Asking $/m2», «HA», «X» e «Y», y algunos muestran el tipo técnico («Etapa · opcion», sin acento).",
    tarea: "Orientarse y saber dónde se está",
    consecuencia: "La palabra principal del dominio tiene dos significados, y la navegación no dice en qué base se trabaja.",
    cambio: "La base actual como título del espacio de trabajo, las herramientas heredadas aparte y unidades escritas igual en todas partes (m², MXN, X = latitud).",
    actual: "20-admin-bases-heredadas.png",
  },
  {
    titulo: "En ancho reducido, la primera pantalla son sólo controles",
    evidencia: "A 390 px, la cabecera, seis controles de filtro y cuatro botones ocupan cerca de 560 px. La tabla aparece al final y se desplaza en horizontal (captura 40). El mapa sí se adapta con un botón «Filtros» (captura 41).",
    tarea: "Consultar un terreno desde el teléfono",
    consecuencia: "Antes de ver un solo terreno hay que desplazarse. La tabla no se puede leer sin moverla de lado.",
    cambio: "Renglones de dos líneas, filtros como chips y ficha a pantalla completa, con las mismas funciones (layout.md › Size classes).",
    actual: "40-movil-tabla.png",
  },
  {
    titulo: "Contraste insuficiente y significados sólo de color",
    evidencia: "--ink-muted (#868280) sobre papel da 3.50:1, por debajo de 4.5:1, y se usa en 30 reglas para texto pequeño: textos de ayuda, «Sin archivos», tipo de columna y «guardando». El marcador «sin dato» #9a9892 da 2.42:1 sobre el mapa claro y el primer tono de la rampa #6da7ec, 2.10:1. Los bordes de los controles dan 1.65:1. La fila seleccionada se distingue sólo por una barra de 3 px.",
    tarea: "Leer, distinguir y ubicar la selección",
    consecuencia: "Texto auxiliar difícil de leer, marcadores que se confunden con el fondo y una selección fácil de perder.",
    cambio: "ink-3 #6b6764 (5.18:1), rampa desde #4384d4 (3.20:1), «sin precio» como anillo hueco #5b5754 (5.99:1), bordes de control #8d8984 (3.21:1) y la selección marcada con fondo, barra y peso.",
    actual: "14-admin-mapa.png",
  },
];

export const CONSERVAR = [
  "Edición tipo hoja de cálculo con teclado y guardado por celda con versión. Un conflicto nunca sobrescribe, y «sin confirmar» comprueba con el servidor antes de reenviar.",
  "El mapa reúne todo el conjunto de la consulta, no sólo la página, y la selección viaja entre Tabla y Mapa.",
  "La ubicación es honesta: la ficha dice si el terreno se dibuja por contorno o por X/Y, y la leyenda cuenta los que quedan fuera.",
  "Un dato faltante queda vacío, nunca en cero, y el precio lleva «MXN» explícito.",
  "El autollenado m² ⇄ HA y precio ⇄ $/m² sólo actúa sobre celdas vacías.",
  "Con varios contornos candidatos se elige de forma explícita, y un KMZ inválido conserva el contorno anterior.",
  "Las subidas en curso están protegidas y la app avisa antes de salir.",
  "El cromo es acromático y el color pertenece a los datos (tokens.css). Es el punto de vista del producto y las tres direcciones lo mantienen.",
  "La selección múltiple abarca páginas («Seleccionar los 48 terrenos de esta vista»).",
  "Fondos Claro, Satélite y Calles, y «Encuadrar todo».",
];

export const DIRECCIONES = [
  {
    id: "A", nivel: "Evolución", nombre: "Hoja con ficha",
    idea: "La tabla sigue en el centro. Una ficha lateral, única y editable, acompaña a Tabla y a Mapa, y un solo modelo de filtros sirve a las dos vistas.",
    beneficia: "A operadoras y operadores que capturan y corrigen a diario, y a administración cuando revisa una base.",
    organiza: "Cabecera con la base como título → barra con búsqueda, Filtros, Tabla|Mapa y Agregar → chips con el alcance → tabla o mapa, con la ficha a la derecha.",
    conserva: "La tabla, el conmutador Tabla / Mapa, la edición por celda y la selección compartida.",
    cambia: "Los filtros (unificados y en chips), el orden (desde el encabezado), la ficha (una y editable), dónde se ven ubicación y archivos, y el estado de guardado (arriba).",
    elimina: "El riel de filtros propio del mapa, el detalle modal (⋯), la ficha de sólo lectura, los botones «Elegir…» de cada celda y los controles «Ordenar por» y «Descendente».",
    ventaja: "Casi no hay que aprender nada nuevo y se puede entregar en PRs pequeños.",
    riesgo: "Sigue mostrando una cosa a la vez, tabla o mapa, y la ficha resta 384 px a la tabla.",
    rasgo: "La ficha que viaja: el mismo terreno, igual y editable, en la tabla y en el mapa.",
    pantallas: ["A1-tabla", "A2-mapa", "A3-ficha-edicion", "A4-estrecho", "A5-estados"],
    recorrido: [
      "En «Bajío Industrial 2026», Filtros → Estado: Guanajuato y Querétaro; Tipo: Industrial y Comercial. Los chips dicen «22 de 48».",
      "Clic en el encabezado «Asking $/m²» para ordenar de mayor a menor. Con las flechas se llega a «Polígono Apaseo…» y Espacio abre la ficha.",
      "«Ver en mapa» (M) cambia a Mapa con los mismos filtros, la misma selección y la misma ficha. El mapa se acerca al contorno y los otros 19 terrenos dibujados siguen a la vista.",
      "En la ficha: «Abrir» abre ficha-tecnica.pdf en otra pestaña y «Descargar» baja el KMZ. Si hace falta, se corrige el precio ahí mismo.",
      "«Tabla» (T) vuelve a la fila seleccionada, con la misma posición, el mismo orden y la ficha abierta.",
    ],
    validar: "Validar si la ficha lateral resta demasiadas columnas en pantallas de 1280 px, si la búsqueda debe filtrar o sólo saltar al resultado y si se entiende el orden desde el encabezado.",
  },
  {
    id: "B", nivel: "Reorganización", nombre: "Mesa dividida",
    idea: "Ver y comparar en lista y mapa a la vez. Las bases son lugares en una barra lateral, y la hoja de cálculo completa pasa a un modo «Hoja» para la edición masiva.",
    beneficia: "A quien analiza y selecciona terrenos comparando precio y ubicación, y a administración cuando salta entre bases.",
    organiza: "Barra lateral con las bases → lista de dos líneas (520 px) y mapa. Una tarjeta de resumen aparece sobre el mapa y la ficha editable se abre en el panel de la lista.",
    conserva: "La tabla completa (como «Hoja»), la edición por campo con versión y la selección múltiple.",
    cambia: "La navegación (barra lateral), la lista y el mapa simultáneos, y la ficha como formulario con anterior/siguiente.",
    elimina: "El conmutador Tabla / Mapa para consultar y el selector «Vista».",
    ventaja: "La relación entre fila y lugar es inmediata, y se edita sin perder el contexto espacial.",
    riesgo: "Hay dos modos que aprender (Lista y mapa / Hoja). La lista muestra 6 datos, no 14, y la disposición necesita 1280 px o más.",
    rasgo: "El resaltado cruzado: al pasar por un renglón se señala su marcador, y al revés.",
    pantallas: ["B1-lista-y-mapa", "B2-mapa-seleccion", "B3-ficha-edicion", "B4-estrecho", "B5-hoja-archivos"],
    recorrido: [
      "Barra lateral → «Bajío Industrial 2026». Se aplican los filtros con chips; la lista y el mapa muestran los mismos 22.",
      "Al pasar el puntero por los renglones se señalan los marcadores. Un clic en «Polígono Apaseo…» lo selecciona, el mapa se acerca y aparece la tarjeta.",
      "En la tarjeta: Asking price, $/m², superficie, la fuente de la ubicación y «Abrir» para el PDF, sin cambiar de pantalla.",
      "«Abrir ficha» lleva el formulario al panel de la lista mientras el mapa sigue mostrando el contorno. Se corrige un dato y J pasa al siguiente terreno.",
      "«‹ 22 terrenos» regresa a la lista, en la misma posición y con los mismos filtros y selección.",
    ],
    validar: "Validar si 6 datos por renglón bastan para decidir, si el ancho mínimo (1280 px) cubre los equipos reales y si «Hoja» se descubre cuando hace falta editar en masa.",
  },
  {
    id: "C", nivel: "Exploración", nombre: "Atlas de expedientes",
    idea: "El mapa es la mesa de trabajo. Cada terreno es un expediente con su estado de completitud (datos, precio, ubicación y PDF), y el trabajo se organiza por lo que falta.",
    beneficia: "A quien completa el inventario o prepara visitas, y a la consulta desde el teléfono.",
    organiza: "Mapa a pantalla completa con controles flotantes → panel de expedientes con la tira de completitud → tarjeta → página del expediente. La Hoja es un cajón que sube sobre el mapa.",
    conserva: "La Hoja (como cajón), la edición con versión y todas las reglas de ubicación.",
    cambia: "El punto de entrada (el mapa), los «pendientes» como filtros predefinidos, el expediente con su actividad unificada y la búsqueda con comandos ⌘K.",
    elimina: "La tabla como pantalla inicial.",
    ventaja: "Hace visible el trabajo pendiente y le da a ARA una identidad cartográfica propia.",
    riesgo: "Es la de mayor curva de aprendizaje y costo. Quien captura en masa puede sentir la tabla como secundaria. Las capas translúcidas sobre Leaflet exigen cuidar contraste y rendimiento, y hacen falta consultas nuevas: pendientes del lado del servidor por encima de 5000 terrenos e historiales unidos.",
    rasgo: "La tira de expediente: Datos · Precio · Ubicación · PDF.",
    pantallas: ["C1-atlas", "C2-expediente-mapa", "C3-expediente-pagina", "C4-estrecho", "C5-hoja-error"],
    recorrido: [
      "⌘K → «Apaseo» → Enter selecciona el terreno y acerca el mapa sin quitar de la vista a los demás.",
      "La tarjeta del expediente muestra la tira (todo completo), los datos clave y los archivos («Abrir» para el PDF).",
      "«Abrir expediente» lleva a la página del terreno, con su mapa pequeño, documentos y actividad. Ahí se corrige el precio.",
      "Esc o «Atlas» vuelve al mismo encuadre, con los mismos pendientes y filtros. J/K recorre los 22 sin salir del expediente.",
      "Para capturar en serie: «Sin precio» → H abre la Hoja con esos 2 terrenos.",
    ],
    validar: "Validar si se entiende el concepto de «pendientes», el rendimiento y la legibilidad de las capas translúcidas sobre Satélite, si el cajón Hoja basta para la captura masiva y si el atlas sirve de verdad en el teléfono.",
  },
];

export const CRITERIOS = [
  ["Claridad", "Alta. Cada cosa tiene un lugar y se nombra igual en todas partes.", "Alta para comparar y media para editar, porque hay dos modos.", "Alta sobre qué falta; menor sobre dónde está la tabla."],
  ["Esfuerzo en tareas frecuentes", "Corregir desde el mapa ya no exige cambiar de vista. La captura masiva sigue igual.", "Comparar cuesta lo mínimo. Editar en masa obliga a pasar a «Hoja».", "Completar pendientes cuesta lo mínimo. Capturar en masa obliga a abrir el cajón."],
  ["Continuidad entre vistas", "Filtros, selección y ficha idénticos en Tabla y Mapa.", "No hay cambio de vista para consultar. La ficha abre sin quitar el mapa.", "El mapa es permanente y el expediente tiene dirección propia."],
  ["Densidad útil (1440 × 900)", "La mayor: unas 21 filas y 9 columnas con la ficha abierta.", "14 renglones con 6 datos cada uno, más el mapa.", "9 renglones con 5 datos y su estado. La Hoja completa, bajo demanda."],
  ["Accesibilidad prevista", "Mismos tokens y sin translucidez. Tabla con navegación por teclado.", "Mismos tokens. Exige una ruta de teclado clara entre la lista y el mapa.", "Necesita un modo opaco con «Reducir transparencia» y medir el contraste sobre Satélite."],
  ["Curva de aprendizaje", "Baja.", "Media.", "Alta."],
  ["Complejidad de implementación", "Media. Reutiliza Tabla.js, la cola de guardado y mapaPaneles. Lo más difícil es unificar los filtros: hoy los rangos de precio y superficie sólo filtran el mapa.", "Media-alta. Disposición nueva, lista virtualizada, resaltado sincronizado y Leaflet en un panel redimensionable.", "Alta. Otro punto de entrada, cajón, rutas de expediente, pendientes, historial unificado y ⌘K."],
];

export const RECOMENDACION = {
  eleccion: "A · Hoja con ficha, con tres rescates",
  razones: [
    "El trabajo diario de ARA es capturar y corregir en tabla. Así nació (Excel) y así está construida la edición por teclado. A resuelve las fricciones que más pesan (filtros, ficha, archivos, guardado y contraste) sin quitar ese modelo mental.",
    "Se puede entregar en PRs pequeños e independientes, como pide AGENTS.md, y cada paso deja la app mejor que antes.",
    "Ninguna de sus piezas depende de una capacidad de negocio nueva.",
  ],
  rescates: [
    "De B: anterior/siguiente (J/K) en la ficha para recorrer el conjunto filtrado, y elegir contorno con vista previa de cada candidato (B5).",
    "De C: los «pendientes» como filtros predefinidos dentro del mismo modelo de filtros (Sin precio, Sin ubicación, Sólo punto X/Y, Sin PDF), y la tira de expediente como columna opcional.",
    "De B, como exploración: una tercera opción «Tabla + mapa» en el conmutador para pantallas de 1600 px o más.",
  ],
  riesgos: [
    "La ficha de 384 px reduce las columnas visibles. Debe poder cerrarse y cambiar de ancho, y la app debe recordar las columnas elegidas.",
    "Para unificar los filtros hay que decidir si los rangos (precio, superficie) se aplican en el servidor o sobre el conjunto reunido, como hoy en el mapa.",
    "Editar desde la ficha suma una segunda superficie de edición. Debe usar la misma cola por terreno y los mismos estados de celda.",
  ],
  orden: [
    "Contraste y tokens (bajo riesgo, sin cambiar la disposición)",
    "Estado de guardado en la barra superior",
    "Columnas Ubicación y PDF junto al nombre, y menú de la fila",
    "Ficha única, primero de lectura, en tabla y mapa",
    "Edición desde la ficha",
    "Filtros unificados con chips",
    "Renglones de dos líneas en ancho reducido",
  ],
};

export const A11Y = {
  contraste: [
    ["Texto principal --ink #1d1b19 / papel #f7f6f3", "15.89:1"],
    ["Texto secundario --ink-2 #55524f / papel", "7.18:1"],
    ["Texto auxiliar --ink-3 #6b6764 / papel (hoy #868280: 3.50:1)", "5.18:1"],
    ["--ink-3 / fondo de fila seleccionada #e8e5df", "4.46:1 → usar --ink-2 en filas seleccionadas"],
    ["Error #b42f2f / #fbeaea", "5.33:1"],
    ["Aviso #7a5b16 / #fbf3e3", "5.71:1"],
    ["Correcto #2f7d32 / #eaf4ea", "4.54:1"],
    ["Blanco / botón principal #1d1b19", "17.17:1"],
    ["Primer tono de la rampa #4384d4 / mapa claro #ecebe6 (hoy #6da7ec: 2.10:1)", "3.20:1"],
    ["Anillo «sin precio» #5b5754 / mapa claro (hoy #9a9892: 2.42:1)", "5.99:1"],
    ["Borde de controles #8d8984 / #fdfdfc (hoy 1.65:1)", "3.21:1"],
  ],
  foco: "El foco es un anillo de 2 px en --ink con un halo blanco de 3 px, visible sobre papel y sobre Satélite. En la tabla, la celda enfocada lleva un contorno interior de 2 px. El outline nunca se quita. El orden de Tab es cabecera → barra → chips → contenido → ficha, y se conserva «Saltar al contenido».",
  teclado: "Atajos: / buscar · T/M Tabla o Mapa (A) · flechas, Enter/F2 y Esc en la tabla (como hoy) · Espacio abre la ficha · J/K siguiente y anterior · Esc cierra la ficha · ⌘K comandos y H Hoja (C). Los atajos de una letra no actúan dentro de un campo de texto y se pueden desactivar (WCAG 2.1.4).",
  lector: "La tabla es un grid ARIA con aria-rowcount y aria-rowindex. La ficha es una región con nombre. Los marcadores tienen nombre accesible y la lista ofrece una alternativa al mapa. El guardado se anuncia con aria-live («Guardado: Superficie»).",
  movimiento: "Transiciones de 200 ms o menos que respetan prefers-reduced-motion (ya existe en tokens.css). En C, las capas translúcidas pasan a opacas con prefers-reduced-transparency o sin soporte de backdrop-filter.",
  tamanos: "Cuerpo de 13 px (el predeterminado de macOS, HIG typography). Mínimo de 11 px, sólo en etiquetas en mayúsculas. Controles de 28 px de alto en escritorio (HIG accessibility: 28 × 28 pt) y de 40 a 44 px en táctil. Con zoom del 200 % la ficha pasa a pantalla completa.",
  responsive: "A partir de 1280 px, la disposición completa. Entre 1024 y 1279 px, la ficha se superpone en lugar de quedar al lado (A) y la lista y el mapa se reparten al 50 % (B). Por debajo de 768 px, renglones y ficha a pantalla completa (A), mapa con hoja deslizable (B) o atlas (C).",
  limite: "Son especificaciones de diseño. Un mockup estático no demuestra accesibilidad funcional; eso se verifica en el prototipo y en la implementación.",
};

export const DECISIONES = [
  "¿Qué dirección refinamos? ¿A con los rescates propuestos u otra combinación?",
  "Vocabulario: ¿conservamos «Asking price» y «Asking $/m²» del Excel del equipo o pasamos a «Precio» y «Precio por m²»? ¿«HA» o «Hectáreas»? ¿Escribimos «X (latitud)» e «Y (longitud)» en los encabezados?",
  "Filtros: ¿los rangos de precio y superficie deben filtrar también la tabla? Hoy sólo filtran el mapa, y cambiarlo afecta al servidor o a cómo se reúne el conjunto.",
  "Búsqueda: ¿debe filtrar, como hoy, o saltar al terreno y dejar el resto a la vista?",
  "Teléfono: ¿quién lo usa y para qué? ¿Hay visitas de campo? ¿Se suben fotos JPG desde el teléfono?",
  "¿Siguen en uso las herramientas heredadas (bases importadas, mapas guardados, formatos)? Si no, se pueden ocultar más.",
  "¿Podemos hacer una sesión de 30 minutos con una operadora y una administradora sobre un prototipo navegable?",
  "¿Se mantiene sólo el modo claro? tokens.css lo decidió por la legibilidad del mapa; ninguna propuesta lo cambia.",
];
