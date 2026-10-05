"""MapTest acceptance runner. Fictional files, isolated SQLite per case, AI off.

Uses the application's real analyze/prepare/confirm handlers. The manifest is
an independent oracle; question answers represent a user who knows their file.
This is handler-level testing, not a claim of production/browser acceptance.
"""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
PACK=Path(__file__).resolve().parents[1]
for key in list(os.environ):
    if key.startswith('ARA_MAP_IA_') or key in ('DATABASE_URL','ARA_MAP_DATABASE_URL','ARA_MAP_TEST_DATABASE_URL'):
        os.environ.pop(key,None)

from server.asistente import servicio
from server.asistente.borradores import borradores
from server.asistente.rejilla import Rejilla
from server.web_util import ApiError
from tests.test_asistente_api import AsistenteCase

def mismatch(actual,expected):
    issues=[]
    if len(actual)!=len(expected): issues.append({'field':'row_count','expected':len(expected),'actual':len(actual)})
    byname={r['terreno']:r for r in actual}
    for row in expected:
        if row['terreno'] not in byname:
            issues.append({'field':'missing_terrain','expected':row['terreno']});continue
        got=byname[row['terreno']]
        for key,value in row.items():
            now=got.get(key)
            if isinstance(value,(float,int)) and isinstance(now,(float,int)):
                ok=abs(value-now)<(1e-5 if key in ('lat','lon') else 1e-7)
            else: ok=value==now
            if not ok: issues.append({'terrain':row['terreno'],'field':key,'expected':value,'actual':now})
    wanted={r['terreno'] for r in expected}
    for row in actual:
        if row['terreno'] not in wanted: issues.append({'field':'unexpected_terrain','actual':row['terreno']})
    return issues

def run(spec):
    case=AsistenteCase();case.setUp()
    out={'file':spec['file'],'title':spec['title'],'category':spec['category'],'questions':[]}
    try:
        r=case.analizar(spec['file'],(PACK/'files'/spec['file']).read_bytes())
        out['initial']=r
        seen=set()
        for _ in range(24):
            if r['estado']!='preguntas':break
            p=r['preguntas'][0]
            draft=borradores.leer(r['borrador'])
            interp=servicio._interpretar(Rejilla.desempaquetar(draft.rejilla),draft.estado,servicio._formatos())
            options=next(q for q in interp.preguntas if q.id==p['id']).opciones
            desired={c.id:(spec['fields'][c.posicion] if c.posicion<len(spec['fields']) else 'extra') for c in interp.columnas}
            def score(op):
                d=op.decision
                if 'decimal' in d:return 100 if d['decimal']==spec.get('decimal','dot') else -100
                if 'hoja' in d:return 100 if d['hoja']==f"sheet:{spec.get('sheet',0)}" else -100
                if 'columnas' in d:return sum(10 if desired.get(k)==v else -6 for k,v in d['columnas'].items())
                if 'sin_campo' in d:return 5 if all(f not in spec['fields'] for f in d['sin_campo']) else -50
                return 0
            index=max(range(len(options)),key=lambda i:score(options[i]))
            signature=(p['id'],index)
            if signature in seen:out['loop']=list(signature);break
            seen.add(signature)
            out['questions'].append({'id':p['id'],'text':p['texto'],'answer':p['opciones'][index]['etiqueta'],'index':index})
            r=case.preparar(r,[{'pregunta':p['id'],'opcion':index}])
        out['guided']=r
        if r['estado']=='vista_previa':
            out['preview_mismatches']=mismatch(r['vista_previa']['filas'],spec['expected'])
            committed=case.confirmar(r,recordar_formato=False)
            out['base']=committed['base']
            out['stored']=[dict(x) for x in case.conn.execute('SELECT * FROM terreno WHERE base_id=? ORDER BY orden',(committed['base']['id'],))]
            out['stored_mismatches']=mismatch(out['stored'],spec['expected'])
            out['status']='PASS' if not out['stored_mismatches'] else 'MISMATCH'
        else:out['status']='UNRESOLVED'
        out['paid_usage_rows']=case.conn.execute('SELECT COUNT(*) FROM uso_ia').fetchone()[0]
        # A separate re-upload tests available manual recovery. Nothing is
        # changed in the input, including source numeric representations.
        if out['status']!='PASS' and spec['fields']:
            m=case.analizar(spec['file'],(PACK/'files'/spec['file']).read_bytes())
            sheet=m['interpretacion']['hoja']['id']
            patch={'columnas':{f'{sheet}/column:{i}':f for i,f in enumerate(spec['fields'])},'decimal':spec.get('decimal','dot')}
            if 'header' in spec:patch['encabezado']=spec['header']
            if 'manualExclude' in spec:patch['excluir']=spec['manualExclude']
            if spec.get('sheet') is not None:patch['hoja']=f"sheet:{spec['sheet']}"
            m=case.preparar(m,correcciones=patch)
            out['manual_correction']=patch;out['manual']=m
            if m['estado']=='vista_previa':out['manual_mismatches']=mismatch(m['vista_previa']['filas'],spec['expected'])
    except ApiError as error:
        out.update(status='REJECTED',http_status=error.status,error=error.mensaje)
    except Exception as error:
        out.update(status='CRASH',error_type=type(error).__name__,error=str(error))
    finally:
        case.tearDown();case.doCleanups()
    return out

if __name__=='__main__':
    results=[]
    for spec in json.loads((PACK/'manifest.json').read_text()):
        result=run(spec);results.append(result)
        print(spec['file'],result['status'],'questions',len(result['questions']),
              'mismatches',len(result.get('stored_mismatches',[])),result.get('error',''),flush=True)
    (PACK/'evidence'/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
