from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(__file__).with_name('READINESS_REPORT.md')
OUT=ROOT/'output/pdf/ARA_Map_Readiness_2026-09-30.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
navy=colors.HexColor('#10266b'); blue=colors.HexColor('#2354d7'); grey=colors.HexColor('#566173')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCustom',fontName='Helvetica',fontSize=9.5,leading=13.8,spaceAfter=8,textColor=colors.HexColor('#202936')))
styles.add(ParagraphStyle(name='SmallCustom',fontName='Helvetica',fontSize=8.1,leading=11.1,spaceAfter=4))
styles.add(ParagraphStyle(name='TableCustom',fontName='Helvetica',fontSize=8.2,leading=11.4,spaceAfter=0))
styles.add(ParagraphStyle(name='SectionCustom',fontName='Helvetica-Bold',fontSize=18,leading=23,textColor=navy,spaceAfter=15))
styles.add(ParagraphStyle(name='SubCustom',fontName='Helvetica-Bold',fontSize=11.2,leading=15,textColor=navy,spaceBefore=10,spaceAfter=7))
styles.add(ParagraphStyle(name='TitleCustom',fontName='Helvetica-Bold',fontSize=27,leading=32,textColor=navy,spaceAfter=16))
width=A4[0]-94

def rich(s):
    s=s.replace('\u2014',' - ').replace('\u2013','-').replace('\u2011','-')
    s=escape(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8">\1</font>',s)
    return s

def para(s,kind='BodyCustom'):return Paragraph(rich(s),styles[kind])

def footer(canvas,doc):
    canvas.saveState();canvas.setStrokeColor(colors.HexColor('#dce3ef'));canvas.line(47,43,A4[0]-47,43)
    canvas.setFillColor(grey);canvas.setFont('Helvetica',8)
    canvas.drawString(47,29,'ARA Map | Supervisor review | 30 September 2026')
    canvas.drawRightString(A4[0]-47,29,f'{doc.page}')
    canvas.setFillColor(navy);canvas.rect(0,A4[1]-8,A4[0],8,fill=1,stroke=0);canvas.restoreState()

story=[];lines=SOURCE.read_text().splitlines();i=0;section=0
while i<len(lines):
    line=lines[i].strip()
    if not line:i+=1;continue
    if line.startswith('# '):
        story.append(para('PRESENTATION READINESS / ARA MAP','SmallCustom'))
        story.append(para(line[2:],'TitleCustom'));i+=1;continue
    if line.startswith('## '):
        if section:story.append(PageBreak())
        section+=1;story.append(para(line[3:],'SectionCustom'));i+=1;continue
    if line.startswith('### '):story.append(para(line[4:],'SubCustom'));i+=1;continue
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[:\- ]+',x) for x in row):rows.append(row)
            i+=1
        n=len(rows[0]);ratios={2:[.29,.71],3:[.25,.48,.27],4:[.49,.17,.17,.17]}[n]
        table=Table([[para(x,'TableCustom') for x in row] for row in rows],colWidths=[width*r for r in ratios],repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0fc')),('TEXTCOLOR',(0,0),(-1,0),navy),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.8,blue),('LINEBELOW',(0,1),(-1,-1),.35,colors.HexColor('#dce3ef'))]))
        story.extend([table,Spacer(1,12)]);continue
    if line.startswith('- '):story.append(para('- '+line[2:]));i+=1;continue
    text=[line];i+=1
    while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','- ')):
        text.append(lines[i].strip());i+=1
    story.append(para(' '.join(text)))

doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=47,leftMargin=47,topMargin=36,bottomMargin=58,
                      title='ARA Map - Presentation and handover readiness',author='Project advisory review')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
