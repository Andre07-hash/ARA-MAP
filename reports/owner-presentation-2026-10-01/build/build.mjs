import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const ROOT='/Users/andrejasso/Desktop/ARA Map';
const SKILL='/Users/andrejasso/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations';
const BUILD=path.join(ROOT,'reports/owner-presentation-2026-10-01/build');
const OUT=path.join(ROOT,'output/presentation');
const EVIDENCE=path.join(ROOT,'reports/readiness-2026-09-30/evidence');
const {resolvePresentationFont,finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const font=resolvePresentationFont();
const C={navy:'#10266B',blue:'#234BEC',ink:'#182339',muted:'#596477',paper:'#F4F6FA',white:'#FFFFFF',amber:'#9A551B'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
function text(s,value,x,y,w,h,size=26,color=C.ink,bold=false){
 const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 a.text=value;a.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none'};return a;
}
function slide(n,title,tag='ARA MAP · DEMOSTRACIÓN'){
 const s=p.slides.add();s.background.fill=C.white;
 text(s,tag,58,27,1100,26,16,C.blue,true);
 text(s,title,58,72,1160,75,43,C.navy,true);
 text(s,'1 OCT 2026  ·  Consulta de terrenos',58,674,1000,22,15,C.muted);
 text(s,String(n).padStart(2,'0'),1162,670,60,28,19,C.muted);return s;
}
async function img(s,name,x,y,w,h){s.images.add({blob:await fs.readFile(name),contentType:'image/png',alt:path.basename(name),fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function notes(s,body,sources='READINESS_REPORT.md, revisión del 30 de septiembre de 2026.'){
 s.speakerNotes.textFrame.setText(body+'\n\nFUENTES (para consulta del presentador):\n'+sources+'\nCarpeta: reports/readiness-2026-09-30/. Capturas y cifras corresponden a esa revisión; confirmar antes de presentar.');
}

{
 const s=p.slides.add();s.background.fill=C.white;
 text(s,'ARA MAP',64,58,730,42,23,C.blue,true);
 text(s,'Los terrenos,\nen un solo mapa.',64,180,790,184,70,C.navy,true);
 text(s,'Ubicar. Consultar. Comparar.',68,403,810,65,32,C.ink);
 text(s,'Demostración para la dirección\n1 de octubre de 2026',68,570,790,72,23,C.muted);
 await img(s,path.join(ROOT,'web/assets/ara-logo.png'),913,210,285,255);
 notes(s,'0:00–0:35\n«La idea nace de una necesidad concreta: cuando un cliente pregunta por un terreno, poder encontrarlo y consultar su información sin recorrer varias hojas. ARA Map reúne esa consulta en un mapa y permite guardar y comparar las fuentes. Hoy veremos el flujo que ya funciona y acordaremos qué falta para utilizarlo de forma habitual.»\nNo abrir aún el navegador. Presentar la reunión como revisión del flujo, no entrega final sin restricciones.');
}
{
 const s=slide(2,'Del archivo a la consulta');
 const items=[['01','Cargar','Excel o CSV con\ndatos de terrenos.'],['02','Revisar','Confirmar columnas\ny resolver dudas.'],['03','Consultar','Buscar en el mapa\ny guardar vistas.'],['04','Comparar','Reunir fuentes y\nexportar a Excel.']];
 items.forEach(([num,head,body],i)=>{const x=58+i*301;text(s,num,x,224,250,80,58,C.blue);text(s,head,x,340,265,58,33,C.navy,true);text(s,body,x,420,268,106,25,C.muted);});
 text(s,'La interpretación del archivo se revisa antes de importar.',58,592,1130,45,27,C.ink);
 notes(s,'0:35–1:15\n«El proceso tiene cuatro momentos. Se carga el archivo; se revisa cómo se interpretó; se consulta y guarda el mapa; y se comparan las fuentes cuando hace falta. Si hay una columna ambigua, el asistente pide aclararla. La revisión previa es parte del control del dato.»\nNo decir que acepta cualquier archivo o cualquier distribución. La demostración no necesita importar ni escribir datos en producción. Si piden un archivo nuevo, acordar revisarlo después en un entorno de prueba.');
}
{
 const s=slide(3,'Encontrar el terreno y abrir su información');
 text(s,'Buscar',58,203,330,46,32,C.navy,true);
 text(s,'Por nombre, municipio\no dirección.',58,260,310,98,25,C.muted);
 text(s,'Consultar',58,382,325,48,32,C.navy,true);
 text(s,'Datos del terreno,\nsuperficie y ubicación.',58,439,310,97,25,C.muted);
 text(s,'Los círculos no son\nlos linderos del predio.',58,581,320,65,21,C.amber);
 await img(s,path.join(EVIDENCE,'live-populated-map.png'),392,146,834,515);
 notes(s,'1:15–3:15 · NAVEGADOR O CAPTURA\nAbrir https://ara-map-ivory.vercel.app en escritorio, ancho superior a 960 px. En Bases, abrir «Base Terrenos 09.26 Gerardo». Buscar «Marceñas» (o el registro aprobado durante el ensayo), abrir su ficha y usar «Ver a escala». También funciona el doble clic sobre un terreno del mapa. Cambiar entre Mapa y Tabla. Limpiar búsqueda y, si hay tiempo, filtrar por estado.\n«Aquí respondemos dónde está y qué información tenemos. La tabla y el mapa muestran el mismo inventario. Al acercarnos, el círculo representa la superficie registrada de manera aproximada; no sustituye un plano con los límites del predio.»\nMarceñas muestra una discrepancia de precio: decir que es un dato pendiente de revisión, no una cotización. Si falla la conexión, permanecer en esta captura y describir el mismo recorrido sin afirmar que está ocurriendo en vivo.', 'READINESS_REPORT.md, §§2–3; evidence/live-populated-map.png; evidence/live-focused.json.');
}
{
 const s=slide(4,'Volver a los mapas y comparar fuentes');
 text(s,'Guardar y organizar',58,202,325,85,31,C.navy,true);
 text(s,'Bases y mapas\norganizados en carpetas.',58,307,307,95,25,C.muted);
 text(s,'Ver cada origen',58,426,326,49,31,C.navy,true);
 text(s,'Capas en el mapa.\nUna hoja de Excel\npor fuente.',58,487,310,126,25,C.muted);
 await img(s,path.join(EVIDENCE,'live-comparison.png'),392,146,834,475);
 text(s,'«Fake 1» y «Fake 2» son datos ficticios de prueba.',403,635,820,27,17,C.amber);
 notes(s,'3:15–5:15 · NAVEGADOR O CAPTURA\nIr a Mapas guardados. Mostrar la organización existente sin crear ni mover nada. Abrir la comparación larga «Base Terrenos 09.26 Ficticia vs Base Terrenos 08.26 Ficticia vs Base Terrenos 09.26 copy». Aclarar que Fake 1 y Fake 2 son ficticios. Activar Fake 1 si está oculta y mostrar que cada capa se puede ocultar y volver a mostrar. Quitar filtros antes de exportar. Exportar Excel y mostrar sus pestañas; usar la exportación comprobada durante el ensayo si abrir Excel demora.\n«Podemos conservar vistas, organizarlas y reunir varias fuentes. Cada capa conserva su identidad. La exportación separa las fuentes en hojas, lo que permite seguir trabajando en Excel.»\nUna vista guardada es una fotografía de sus datos: no prometer que se actualiza sola. Ocultar una capa o filtrar afecta el contenido de la exportación desde la interfaz. No presentar el Excel como respaldo completo de todos los campos adicionales.', 'READINESS_REPORT.md, §§2–3, 6; evidence/live-comparison.png; evidence/live-data-and-exports.json.');
}
{
 const s=slide(5,'El mapa también revela qué falta revisar');
 text(s,'39 / 79',58,194,555,106,83,C.blue,true);
 text(s,'terrenos con ubicación',61,310,551,51,30,C.navy,true);
 text(s,'40 siguen fuera del mapa\npor falta de coordenadas utilizables.',61,402,547,104,27,C.muted);
 text(s,'Una alerta de precio',720,212,496,56,33,C.navy,true);
 text(s,'Total registrado',722,302,496,32,22,C.muted);
 text(s,'$388,689,722',719,346,490,59,42,C.ink,true);
 text(s,'Superficie × precio por m²',722,430,496,38,22,C.muted);
 text(s,'$38,657,322',719,477,490,61,42,C.amber,true);
 text(s,'Ejemplo: Marceñas. Requiere revisión; no es una cotización validada.',61,598,1148,44,22,C.amber);
 text(s,'Fuente: Base Terrenos 09.26 Gerardo · revisión del 30 de septiembre de 2026.',61,644,1148,24,16,C.muted);
 notes(s,'5:15–6:00\n«La herramienta ayuda a consultar la información y también deja visible lo que falta. En esta base hay 79 terrenos, pero solo 39 tienen ubicación utilizable. En Marceñas, el total registrado no coincide con 64,429 metros cuadrados por 600 pesos por metro cuadrado. El sistema muestra la advertencia: la empresa debe confirmar cuál dato es correcto antes de cotizar.»\nNo afirmar que la aplicación corrigió el precio ni que todos los terrenos están georreferenciados. Los 40 sin ubicación se cuentan en la base; no son 40 registros borrados. No sumar estas cifras entre bases para obtener propiedades únicas.', 'READINESS_REPORT.md, §3B; evidence/live-data-and-exports.json; evidence/live-detail.png. Cálculo: 64,429 × 600 = 38,657,400 con la superficie redondeada en pantalla; el aviso usa la superficie subyacente y muestra 38,657,322. Las cifras de la diapositiva transcriben el aviso real; no se recalculan a partir del redondeo.');
}
{
 const s=slide(6,'Qué podemos usar y qué falta cerrar');
 text(s,'El flujo ya funciona',58,201,539,51,34,C.navy,true);
 text(s,'Consulta en escritorio\nMapas guardados y carpetas\nComparaciones y Excel',58,295,550,181,29,C.ink);
 text(s,'Antes de la entrega operativa',686,201,531,88,34,C.navy,true);
 text(s,'Importaciones: moneda y selección de filas\nCelular: acceso a búsqueda y filtros\nAcceso: decidir si la consulta será privada',686,305,526,244,26,C.muted);
 text(s,'Hoy el inicio de sesión protege la edición; la consulta y la exportación son públicas.',58,565,1158,61,23,C.amber);
 text(s,'IA sin activar. La demostración utiliza detección y revisión del usuario.',58,637,1158,27,19,C.muted);
 notes(s,'6:00–7:00\n«El flujo principal está listo para una demostración preparada en computadora. Antes de entregarlo para uso habitual, quedan correcciones del importador, la búsqueda en pantallas pequeñas y una decisión de acceso. Hoy el inicio de sesión permite editar, pero consultar y descargar no exige entrar. Necesitamos confirmar si esto será un catálogo visible o una herramienta interna.»\n«La inteligencia artificial todavía no está activada. No es necesaria para este recorrido ni se está presentando como una función evaluada con un proveedor real.»\nNo decir que las correcciones locales ya están desplegadas. Si preguntan por formatos arbitrarios, responder que se validará una lista concreta de archivos y casos de uso.');
}
{
 const s=slide(7,'Acordar un piloto con criterios claros');
 const ys=[212,351,490];
 [['01','Elegir el archivo real','Definir los terrenos y las consultas que deben resolverse.'],['02','Cerrar los pendientes','Corregir importaciones, uso móvil y reglas de acceso.'],['03','Probar con quien lo utilizará','Validar los resultados antes de aceptar la primera versión.']].forEach(([n,h,b],i)=>{text(s,n,58,ys[i],94,65,43,C.blue);text(s,h,184,ys[i]+1,1025,49,33,C.navy,true);text(s,b,184,ys[i]+61,1025,54,25,C.muted);});
 text(s,'Mejora propuesta: completar datos faltantes; después, una ficha para enviar al cliente.',58,631,1155,39,22,C.blue);
 notes(s,'7:00–8:00\n«Propongo acordar un archivo real y las consultas que usaremos para aceptar la primera versión. Con ese criterio cerramos los pendientes y hacemos un piloto con la persona que lo va a usar. La mejora que priorizaría es una forma sencilla de completar ubicaciones y precios faltantes. Después tendría sentido generar una ficha para el cliente.»\n«¿Qué archivo y qué consulta usamos para aceptar la primera versión?»\nEscuchar y anotar responsables de datos, usuarios, dispositivos y privacidad. Estas mejoras son propuestas, no funciones existentes ni compromisos de fecha. Si surge el precio: ofrecer una propuesta con alcance, aceptación, soporte y costos externos por separado; no improvisar una cifra.');
}

await fs.mkdir(OUT,{recursive:true});
const candidate=path.join(BUILD,'candidate-v2.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:path.join(OUT,'ARA_Map_Propietario_2026-10-01.pptx'),pythonExecutable:'/Users/andrejasso/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:7,requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation-v2.json')});
console.log(JSON.stringify({font,final:result.finalPath??result},null,2));
