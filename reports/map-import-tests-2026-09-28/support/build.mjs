import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.resolve(import.meta.dirname,'..'), out=path.join(root,'files');
const H=['Terreno','Precio','Superficie m2','Latitud','Longitud'];
const F=['terreno','asking_price','superficie_m2','lat','lon'];
const R=[['FICTICIO Encino',1200000,2400,19.4326,-99.1332],['FICTICIO Roble',2500000,5000,20.6736,-103.344],['FICTICIO Cedro',3750000,7500,25.6866,-100.3161],['FICTICIO Fresno',4800000,9600,20.5888,-100.3899]];
const expected=R.map(r=>Object.fromEntries(F.map((f,i)=>[f,r[i]])));
const specs=[];
function add(id,title,rows,options={}) { specs.push({id,title,rows,fields:F,expected,extension:'csv',category:'supported',...options}); }
add(1,'Excel standard control',[H,...R],{extension:'xlsx'});
add(2,'Reordered columns',[['Longitud','Terreno','Latitud','Superficie m2','Precio'],...R.map(r=>[r[4],r[0],r[3],r[2],r[1]])],{fields:['lon','terreno','lat','superficie_m2','asking_price']});
add(3,'Semicolon and decimal comma',[H,...R.map(r=>r.map((v,i)=>i===0?v:String(v).replace('.',',')))],{separator:';',decimal:'comma'});
add(4,'Title, merged banner and blank rows',[['DATOS FICTICIOS PARA PRUEBAS'],[],H,...R],{extension:'xlsx',header:1,visualHeader:3,merge:'A1:E1'});
add(5,'Instructions sheet before terrain sheet',[H,...R],{extension:'xlsx',notesFirst:true,sheet:1});
add(6,'Repeated header inside table',[H,R[0],R[1],H,R[2],R[3]]);
add(7,'Summary total row',[H,...R,['TOTAL',12250000,24500,'','']]);
add(8,'Repeated price headers: total and unit',[['Terreno','Precio','Precio','Latitud','Longitud'],...R.map(r=>[r[0],r[1],r[1]/r[2],r[3],r[4]])],{extension:'xlsx',fields:['terreno','asking_price','asking_m2','lat','lon'],expected:expected.map((r,i)=>({terreno:r.terreno,asking_price:r.asking_price,asking_m2:R[i][1]/R[i][2],lat:r.lat,lon:r.lon}))});
add(9,'English headers',[['Property name','Sale price MXN','Area sqm','Latitude','Longitude'],...R]);
add(10,'Unknown headers require mapping',[['Proyecto','Pedido','Dimension','Posicion A','Posicion B'],...R]);
add(11,'Two header rows with units',[['Terreno','Precio','Superficie','Coordenadas',null],[null,'MXN','m2','Latitud','Longitud'],...R],{extension:'xlsx',merge:'D1:E1',category:'layout_gap'});
add(12,'Transposed property cards',[['Campo',...R.map(r=>r[0])],...H.slice(1).map((h,i)=>[h,...R.map(r=>r[i+1])])],{extension:'xlsx',fields:[],category:'layout_gap'});
add(13,'Two side-by-side terrain tables',[['Terreno','Precio','Latitud','Longitud',null,'Terreno','Precio','Latitud','Longitud'],...[0,1].map(i=>[R[i][0],R[i][1],R[i][3],R[i][4],null,R[i+2][0],R[i+2][1],R[i+2][3],R[i+2][4]])],{extension:'xlsx',fields:['terreno','asking_price','lat','lon','extra','extra','extra','extra','extra'],category:'layout_gap'});
add(14,'Two valid worksheets: choose one',[H,...R.slice(0,2)],{extension:'xlsx',secondRows:[H,...R.slice(2)],expected:expected.slice(0,2)});
add(15,'Coordinates together in one cell',[['Terreno','Precio','Superficie m2','Coordenadas'],...R.map(r=>[...r.slice(0,3),`${r[3]}, ${r[4]}`])],{fields:['terreno','asking_price','superficie_m2','extra'],category:'coordinate_gap'});
function dms(v,positive,negative) {let a=Math.abs(v),d=Math.floor(a),m=Math.floor((a-d)*60),s=((a-d-m/60)*3600).toFixed(2);return `${d}°${m}'${s}"${v<0?negative:positive}`;}
add(16,'Degrees minutes seconds coordinates',[H,...R.map(r=>[...r.slice(0,3),dms(r[3],'N','S'),dms(r[4],'E','W')])],{category:'coordinate_gap'});
add(17,'Projected UTM coordinates',[['Terreno','Precio','Superficie m2','Este','Norte','Zona UTM'],...R.map((r,i)=>[...r.slice(0,3),486000+i*1000,2148000+i*1000,'14N'])],{fields:['terreno','asking_price','superficie_m2','extra','extra','extra'],expected:expected.map(r=>({...r,lat:null,lon:null})),category:'safe_limitation'});
add(18,'Mixed decimal conventions by column',[H,...R.map(r=>[r[0],r[1].toLocaleString('de-DE',{minimumFractionDigits:2}),r[2],r[3],r[4]])],{category:'number_gap'});
add(19,'USD stated in header',[['Terreno','Precio USD','Superficie m2','Latitud','Longitud'],...R],{fields:['terreno','extra','superficie_m2','lat','lon'],expected:expected.map(r=>({...r,asking_price:null})),category:'safe_limitation'});
add(20,'USD stated only in Excel number format',[H,...R],{extension:'xlsx',formats:[['B2:B5','"USD "#,##0.00']],expected:expected.map(r=>({...r,asking_price:null})),category:'currency_safety'});
add(21,'Native Excel percentage values',[['Terreno','Precio','Superficie m2','Latitud','Longitud','Afectaciones %'],...R.map((r,i)=>[...r,[0.15,0.2,0,0.05][i]])],{extension:'xlsx',fields:[...F,'afectaciones_pct'],formats:[['F2:F5','0%']],expected:expected.map((r,i)=>({...r,afectaciones_pct:[0.15,0.2,0,0.05][i]}))});
add(22,'Legitimate terrain name begins with Total',[H,...R.map((r,i)=>i===0?['Total FICTICIO Encino',...r.slice(1)]:r)],{expected:expected.map((r,i)=>i===0?{...r,terreno:'Total FICTICIO Encino'}:r),category:'row_safety'});
add(23,'Footnote below data',[H,...R,['NOTA: valores sujetos a revisión','','','','']],{category:'row_safety'});
add(24,'Leading blank rows and columns',[[],[null,null,...H],...R.map(r=>[null,null,...r])],{extension:'xlsx',fields:['extra','extra',...F],visualHeader:2});
add(25,'Decimal comma coordinates with quoted comma CSV',[H,...R.map(r=>r.map((v,i)=>i>2?String(v).replace('.',','):v))],{decimal:'comma'});
add(26,'Quotes, comma and multiline extra text',[[...H,'Notas'],...R.map((r,i)=>[...r,i===0?'Dijo "revisar", el acceso\nSegunda línea':'Sin observaciones'])],{fields:[...F,'extra']});
add(27,'UTF-16 Excel CSV export',[H,...R],{encoding:'utf16le',category:'encoding_limit'});
add(28,'Windows-1252 CSV export',[['Terreno','Precio','Superficie m2','Latitud','Longitud','Observación'],...R.map(r=>[...r,'Información de prueba'])],{encoding:'latin1',fields:[...F,'extra'],category:'encoding_limit'});
add(29,'Tab-delimited file with .csv extension',[H,...R],{separator:'\t',category:'delimiter_gap'});
add(30,'Malformed CSV quoting',[],{raw:'Terreno,Precio,Latitud,Longitud\n"FICTICIO sin cierre,1200000,19.4326,-99.1332\n',category:'reject'});
add(31,'Empty CSV',[],{raw:'',category:'reject'});
add(32,'Blank price versus real zero',[H,...R.map((r,i)=>[r[0],i===0?'':i===1?0:r[1],...r.slice(2)])],{expected:expected.map((r,i)=>({...r,asking_price:i===0?null:i===1?0:r.asking_price}))});
add(33,'Price formulas with cached results',[['Terreno','Superficie m2','Precio m2','Precio','Latitud','Longitud'],...R.map(r=>[r[0],r[2],r[1]/r[2],null,r[3],r[4]])],{extension:'xlsx',fields:['terreno','superficie_m2','asking_m2','asking_price','lat','lon'],formulas:[['D2:D5',['=B2*C2','=B3*C3','=B4*C4','=B5*C5']]],expected:expected.map((r,i)=>({...r,asking_m2:R[i][1]/R[i][2]}))});
add(34,'Table without a header row',R,{category:'layout_gap'});
add(35,'Header after 55 nonblank introduction lines',[...Array.from({length:55},(_,i)=>[`Nota ficticia ${i+1}`]),H,...R],{extension:'xlsx',header:55,visualHeader:56,category:'layout_gap'});
add(36,'UTF-8 BOM and explicit separator directive',[H,...R],{separator:';',prefix:'\uFEFFsep=;\r\n'});

function csv(rows,sep=',') { return rows.map(r=>r.map(v=>{const s=v==null?'':String(v);return /["\r\n]/.test(s)||s.includes(sep)?'"'+s.replaceAll('"','""')+'"':s;}).join(sep)).join('\r\n')+'\r\n'; }
for(const s of specs) {
 if(s.id===13)s.expected=expected.map(({superficie_m2,...r})=>r);
 if(s.id===23)s.manualExclude=[5];
 s.file=`MapTest${s.id}.${s.extension}`;
 if(s.extension==='csv') {
  const txt=s.raw??((s.prefix??'')+csv(s.rows,s.separator));
  await fs.writeFile(path.join(out,s.file),s.encoding==='utf16le'?Buffer.concat([Buffer.from([255,254]),Buffer.from(txt,'utf16le')]):Buffer.from(txt,s.encoding??'utf8'));
 } else {
  const wb=Workbook.create();
  if(s.notesFirst) {const n=wb.worksheets.add('Instrucciones');n.getRange('A1:A2').values=[['DATOS FICTICIOS'],['La tabla está en la siguiente hoja.']];n.getRange('A1:A2').format.columnWidth=48;}
  const sh=wb.worksheets.add('Terrenos');
  const width=Math.max(...s.rows.map(r=>r.length));
  const matrix=s.rows.map(r=>Array.from({length:width},(_,i)=>r[i]??null));
  sh.getRangeByIndexes(0,0,matrix.length,width).values=matrix;
  const used=sh.getUsedRange();used.format.font.name='Arial';used.format.font.size=10;used.format.columnWidth=23;used.format.rowHeight=23;
  sh.getRange('A1:A'+matrix.length).format.columnWidth=32;
  sh.showGridLines=false;
  const hr=(s.visualHeader??1)-1;
  sh.getRangeByIndexes(hr,0,1,width).format.fill='#152F75';sh.getRangeByIndexes(hr,0,1,width).format.font.color='#FFFFFF';sh.getRangeByIndexes(hr,0,1,width).format.font.bold=true;
  if(s.merge) sh.mergeCells(s.merge);
  for(const [r,f] of s.formats??[])sh.getRange(r).setNumberFormat(f);
  for(const [r,f] of s.formulas??[])sh.getRange(r).formulas=f.map(x=>[x]);
  if(s.secondRows) {const n=wb.worksheets.add('Otra tabla');n.getRangeByIndexes(0,0,s.secondRows.length,5).values=s.secondRows;n.getUsedRange().format.columnWidth=25;}
  wb.recalculate();
  const inspect=await wb.inspect({kind:'table',range:`Terrenos!A${s.id===35?54:1}:I${s.id===35?60:Math.min(matrix.length,12)}`,include:'values,formulas',tableMaxRows:12,tableMaxCols:9,maxChars:4500});
  await fs.writeFile(path.join(root,'evidence',`MapTest${s.id}-inspection.ndjson`),inspect.ndjson);
  for(let i=0;i<1+(s.notesFirst?1:0)+(s.secondRows?1:0);i++) {
   const tab=wb.worksheets.getItemAt(i);
   const range=tab.name==='Terrenos'&&s.id===35?'A54:E60':undefined;
   const img=await wb.render({sheetName:tab.name,...(range?{range}:{autoCrop:'all'}),scale:1,format:'png'});
   await fs.writeFile(path.join(root,'evidence',`MapTest${s.id}-${i}.png`),new Uint8Array(await img.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,s.file));
 }
 console.log(s.file,s.title);
}
await fs.writeFile(path.join(root,'manifest.json'),JSON.stringify(specs,null,2));
