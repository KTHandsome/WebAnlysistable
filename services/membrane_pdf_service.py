"""E202/E230 portrait records, using the saved report header and calculated snapshot."""
from io import BytesIO
from decimal import Decimal
from datetime import datetime, date
from xml.sax.saxutils import escape
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle

FONT='MSung-Light'


def roc(value, stamp=False):
    try:
        d=datetime.fromisoformat(value) if stamp else date.fromisoformat(value)
        result='{:03d}.{:02d}.{:02d}'.format(d.year-1911,d.month,d.day)
        return result+d.strftime(' %H:%M') if stamp else result
    except (ValueError,TypeError):
        return str(value or '-')


def build_membrane_pdf(batches, report, method, method_name, analyst='', preview=False, status=''):
    if method not in {'E202','E230'}:
        raise ValueError('不支援此方法。')
    keys=('COMPANY_NAME','FORM_TITLE','DOC_NO','REVISION','ISSUE_DATE')
    company,title,doc,rev,issue=[str(report.get(k) or '').strip() for k in keys]
    if not all((company,title,doc,rev,issue)):
        raise ValueError('報表設定缺少公司、表名、文件編號、版次或發行日期。')
    if re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',rev):rev=format(Decimal(rev),'.2f')
    font=UnicodeCIDFont(FONT);font.encodingName='UniCNS-UCS2-H';pdfmetrics.registerFont(font)
    style=ParagraphStyle('mf-cell',fontName=FONT,fontSize=9,leading=12,alignment=1,wordWrap='CJK')
    meta_style=ParagraphStyle('mf-meta',parent=style,fontSize=10,leading=14,alignment=0)
    para=lambda value:Paragraph(escape(str(value if value is not None else '-')).replace('\n','<br/>'),style)
    width,height=A4;left=24;usable=width-48
    sample_dates=any('sampled_at' in r for b in batches for r in b['rows'] if not r.get('blank'))
    widths=[85,63,63,32,29,26,31,31,26,65,40,56] if sample_dates else [88,37,37,42,36,42,42,37,67,54,65]
    widths[-1]+=usable-sum(widths)
    headings=['樣品編號','採樣\n時間','檢驗\n時間','稀釋\n倍數','體積\n(mL)','X\n培養皿','Y\n培養皿','選用\n倍數','報告值\nCFU/100 mL','DUP差異','符合性']
    if sample_dates:headings=['樣品編號','採樣日期\n時間','收檢日期\n時間']+headings[2:]
    def meta_grid(batch):
        per_sample=any('sampled_at' in r for r in batch['rows'] if not r.get('blank'))
        left_values=['檢驗方法：'+str(method_name),'培養基：'+batch['medium'],
                     '培養溫度：'+batch['temperature']+' ℃','','']
        fields=[('採樣日期：','sampling_date',False),
                ('接受樣品日期：','received_at',True),
                ('檢驗分析日期：','inspection_date',False),
                ('培養起始日期：','start',True),
                ('培養終止日期：','end',True)]
        if per_sample:
            fields=[x for x in fields if x[1] not in {'sampling_date','received_at'}]
        meta=[]
        for left_value,(label,key,has_time) in zip(left_values,fields):
            value=roc(batch[key],has_time)
            day,_,clock=value.partition(' ') if has_time else (value,'','')
            meta.append([Paragraph(escape(left_value),meta_style),Paragraph(escape(label),meta_style),
                         Paragraph(escape(day.replace('.','/')),meta_style),
                         Paragraph('/時間：' if has_time else '',meta_style),Paragraph(escape(clock),meta_style)])
        mt=Table(meta,colWidths=[usable*.48,95,68,45,usable*.52-208])
        mt.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return mt
    pages=[]
    # 22 raw rows/page; merged sample fields repeat on continuation pages.
    for batch_no,batch in enumerate(batches,1):
        _,mh=meta_grid(batch).wrap(usable,height)
        capacity=height-77-mh-10-100-(42 if sample_dates else 34)
        current=[];spans=[];heights=[]
        for row in batch['rows']:
            r=row['result'];dup=r['dup'];lines=row['lines']
            if not lines:raise ValueError('正式紀錄缺少原始數據。')
            compliance='不適用' if dup.get('applicable') is False else ('通過（免管制）' if dup.get('exempt') else ('通過' if dup.get('passed') else '不符合'))
            if sample_dates:compliance=compliance.replace('（免管制）','\n免管制')
            raw=[]
            for line in lines:
                selected=r.get('factor') is not None and int(line['factor'])==r['factor']
                if sample_dates:
                    def shown(value):return roc(value,True).replace('.','/').replace(' ','\n') if value else '-'
                    raw.append([row['number'],shown(row.get('sampled_at')),shown(row.get('received_at')),row.get('inspection') or '-',line['factor'],100 if method=='E230' else 10,line['x'],line['y'],'是' if selected else '-',r['report'],dup['display'],compliance])
                else:
                    raw.append([row['number'],row.get('time') or '-',row.get('inspection') or '-',line['factor'],100 if method=='E230' else 10,line['x'],line['y'],'是' if selected else '-',r['report'],dup['display'],compliance])
            while raw:
                n=min(len(raw),22-len(current))
                if n==0:
                    pages.append((batch_no,batch,current,spans,heights));current=[];spans=[];heights=[];continue
                merged=(0,1,2,3,9,10,11) if sample_dates else (0,1,2,8,9,10)
                # Reduce the chunk until wrapped identifiers/results fit above the footer.
                while n:
                    block=[[para(v) for v in values] for values in raw[:n]]
                    row_h=24
                    for col in merged:
                        _,h=block[0][col].wrap(widths[col]-8,1000)
                        row_h=max(row_h,(h+8)/n)
                    if sum(heights)+row_h*n <= capacity:break
                    n-=1
                if not n:
                    if not current:raise ValueError('表頭或樣品資料過長，超過頁面可列印範圍。')
                    pages.append((batch_no,batch,current,spans,heights));current=[];spans=[];heights=[];continue
                first=len(current)+1
                for col in merged:
                    if n>1:spans.append(('SPAN',(col,first),(col,first+n-1)))
                current.extend(block);heights.extend([row_h]*n);raw=raw[n:]
        if current:pages.append((batch_no,batch,current,spans,heights))
    if not pages:raise ValueError('沒有可匯出的檢驗紀錄。')
    out=BytesIO();pdf=Canvas(out,pagesize=A4);pdf.setTitle(title)
    def fit(text,x,y,size=10,right=False,max_width=usable):
        text=str(text);size=min(size,size*max_width/max(1,pdfmetrics.stringWidth(text,FONT,size)))
        pdf.setFont(FONT,size)
        if right:pdf.drawRightString(x,y,text)
        else:pdf.drawString(x,y,text)
    for page_no,(batch_no,batch,rows,spans,heights) in enumerate(pages,1):
        fit(company,left,height-26,max_width=usable*.60)
        fit(doc+'  版次：'+rev,width-left,height-26,right=True,max_width=usable*.38)
        fit('發行日期：'+issue,width-left,height-41,right=True,max_width=usable*.38)
        pdf.setFont(FONT,min(15,15*usable/max(1,pdfmetrics.stringWidth(title,FONT,15))))
        pdf.drawCentredString(width/2,height-64,title)
        mt=meta_grid(batch)
        _,mh=mt.wrap(usable,height);top=height-77-mh-10;mt.drawOn(pdf,left,top+10)
        table=Table([[Paragraph(escape(v).replace('\n','<br/>'),style) for v in headings]]+rows,colWidths=widths,rowHeights=[42 if sample_dates else 34]+heights)
        table.setStyle(TableStyle(spans+[
            ('FONTNAME',(0,0),(-1,-1),FONT),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),2 if sample_dates else 4),('RIGHTPADDING',(0,0),(-1,-1),2 if sample_dates else 4),
            ('GRID',(0,0),(-1,-1),.45,black),('BOX',(0,0),(-1,-1),.85,black)]))
        _,th=table.wrap(usable,height)
        if top-th<100:raise ValueError('表頭或樣品資料過長，超過頁面可列印範圍。')
        table.drawOn(pdf,left,top-th)
        fit('DUP 管制上限：'+str(report.get('_DC_UCL','-'))+'；兩皿均小於20免管制；TNTC不適用。',left,78,size=9)
        fit('審核：',left,52,size=10)
        fit('驗算：',left+usable/3,52,size=10)
        fit('檢驗員：',left+usable*2/3,52,size=10)
        pdf.setFont(FONT,9)
        pdf.drawCentredString(width/2,25,'第 {} 頁 / 共 {} 頁'.format(page_no,len(pages)))
        if preview:
            fit('預覽｜非正式紀錄',width-left,height-55,size=8,right=True,max_width=150)
        pdf.showPage()
    pdf.save();out.seek(0);return out


def export_formal_pdf(db, record):
    import json
    from flask import send_file
    from models import AnalysisWorkState
    work=db.query(AnalysisWorkState).filter_by(analysis_id=record.analysis_id).first()
    if work is None:return '查無正式紀錄快照。',404
    try:
        state=json.loads(work.state_json);report=json.loads(work.report_data_json);control=json.loads(work.control_data_json)
        if state.get('membrane_format')!=1:raise ValueError('正式紀錄格式不符。')
        report=dict(report,_DC_UCL=control.get('DC_UCL','-'))
        pdf=build_membrane_pdf(state['membrane_batches'],report,record.method_code,record.method_name,
            record.analyst_name,status=record.status)
    except (ValueError,KeyError,TypeError) as exc:
        return '無法匯出檢驗紀錄表：'+str(exc),422
    return send_file(pdf,mimetype='application/pdf',as_attachment=True,
        download_name=record.method_code+'_'+str(record.id)+'.pdf',max_age=0)
