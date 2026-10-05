import csv,hashlib,io,json,zipfile
from pathlib import Path
P=Path(__file__).resolve().parents[1]
specs=json.loads((P/'manifest.json').read_text())
results=json.loads((P/'evidence/results.json').read_text())
notes={
8:'Manual column mapping recovers all values; guided choice leaves unit price in extra data.',
12:'Transposed layout unsupported; no usable preview after guided answers.',
13:'Only the left table becomes two terrain records; the right table remains extra columns.',
15:'Combined coordinate cell remains extra data; 4/4 terrains unlocated.',
16:'DMS strings are not parsed as coordinates; 4/4 terrains unlocated.',
17:'Safe limitation: UTM remains extra data; no fabricated lat/lon.',
18:'One global decimal convention cannot preserve both column formats; price fields become null with warnings.',
19:'Safe limitation: explicit USD prices stay extra data, not MXN.',
20:'F1: Excel USD formatting lost; all four amounts committed as MXN.',
22:'F2: Total FICTICIO Encino dropped; only three terrains saved.',
23:'F5: note footer becomes a fifth terrain. API exclusion works; no browser row-exclusion control.',
27:'Known encoding limitation: clear instruction to re-export as UTF-8.',
28:'Known encoding limitation: clear instruction to re-export as UTF-8.',
29:'F3: tabs collapse into a single name field; wrong terrain names and missing values.',
30:'Expected rejection: unterminated quoted field.',
31:'Expected rejection: empty upload.',
34:'No headerless mode; first terrain becomes header and is omitted.',
35:'F4: header at row 56 absent from correction menu. Direct API correction succeeds.'}
rows=[]
for s,r in zip(specs,results):
    rows.append([s['file'],s['title'],r['status'],len(r['questions']),
                 len(r.get('stored',[])) if 'stored' in r else '',len(s['expected']),
                 notes.get(s['id'],'Matches the intended records after the listed focused questions.' if r['questions'] else 'Matches the intended records without questions.')])
headers=['File','Scenario','Guided result','Question rounds','Saved rows','Expected rows','Interpretation']
with (P/'TEST_MATRIX.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f);w.writerow(headers);w.writerows(rows)
md='# MapTest file matrix\n\nAll terrain information is fictional. PASS includes the explicitly stated safe limitations for UTM and USD headers. MISMATCH is a content comparison, not an automatic claim of a new defect. See DEVELOPER_REPORT.md for priorities and distinctions.\n\n'
md+='| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'
for row in rows:
    row=list(map(str,row));row[0]=f'[{row[0]}](files/{row[0]})'
    md+='| '+' | '.join(v.replace('|','/') for v in row)+' |\n'
(P/'TEST_MATRIX.md').write_text(md)
(P/'README.md').write_text('''# MapTest upload pack

36 files: MapTest1–MapTest36. There are 13 Excel workbooks and 23 CSV files.
All terrain names, prices and records are fictional. The coordinates are only illustrative points.

1. Open TEST_MATRIX.md to choose a scenario. MapTest1.xlsx is the baseline.
2. Use a test copy of ARA Map. Upload one file at a time from Bases → Importar archivo.
3. Leave AI disabled to reproduce this review. Turn off “Recordar este formato” when confirming and use a clean test workspace without remembered formats; otherwise previous files can influence detection.
4. Compare the preview and actual saved records with the matrix and manifest.json. Files 30 and 31 are deliberately malformed/empty. Files 27 and 28 deliberately use unsupported encodings.
5. Give DEVELOPER_REPORT.md and this entire pack to the developer. It includes reproduction scripts, evidence and five failing regression cases with two passing controls.

Do not infer that an HTTP 200 or an Importar button means values are correct. MapTest20 and MapTest22 demonstrate successful confirmations with wrong data.

The review changed no application code and used no production data or paid AI. Read the report for the exact test scope and remaining compatibility gaps.
''')
for name in ('MapTest_files.zip','MapTest_developer_packet.zip'):
    with zipfile.ZipFile(P/name,'w',compression=zipfile.ZIP_DEFLATED) as z:
        paths=(P/'files').iterdir() if name=='MapTest_files.zip' else P.rglob('*')
        for f in paths:
            rel=f.relative_to(P)
            if not f.is_file() or f.suffix=='.zip' or any(k in rel.parts for k in ('node_modules','__pycache__')):continue
            z.write(f,f.name if name=='MapTest_files.zip' else str(rel))
print('Created two ZIPs; fixture counts:',len(specs),'; workbooks:',sum(s['extension']=='xlsx' for s in specs))
with zipfile.ZipFile(P/'MapTest_files.zip') as z:
    assert len(z.namelist())==36
    assert z.testzip() is None
with zipfile.ZipFile(P/'MapTest_developer_packet.zip') as z:
    assert z.testzip() is None
print('Both ZIPs verified.')
