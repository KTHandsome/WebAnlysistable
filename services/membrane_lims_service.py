"""Membrane analysis results plus one representative DUP per batch."""
from io import BytesIO
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
import re
from openpyxl import load_workbook
from exports.lims_export_model import LimsAnalysisRow, LimsQcRow, LimsExportData
from exports.lims_excel_exporter import build_lims_excel
from exports.w434_lims_mapper import _build_batch_no


def representative(rows, method):
    minimum = '<10' if method == 'E202' else '<1'
    quantified = []
    below = []
    for row in rows:
        value = str(row['result']['report']).strip()
        if value == 'TNTC':
            continue
        if value == minimum:
            below.append(row)
            continue
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:E\+[0-9]+)?',value):
            raise ValueError(row['number']+'：報告值格式無效。')
        quantified.append(row)
    return (quantified or below or [None])[0]


def build_membrane_lims(record, state, template_path):
    method = str(record.method_code or '').strip().upper()
    exam = str(record.exam_no or '').strip()
    if method not in {'E202','E230'} or not re.fullmatch(r'[A-Z]-'+method+r'[0-9]{2}',exam):
        raise ValueError('方法與LIMS項目代碼不符。')
    if state.get('membrane_format') != 1 or not state.get('membrane_batches'):
        raise ValueError('查無濾膜法正式快照。')
    expected = state['data']['samples']
    data = LimsExportData();seen=set();offset=0;duplicates=[]
    for index,batch in enumerate(state['membrane_batches'],1):
        rows=[r for r in batch['rows'] if not r.get('blank')]
        if not rows:raise ValueError('批次沒有樣品。')
        batch_no=_build_batch_no(str(record.analysis_start_date),exam,index)
        for row in rows:
            sample=str(row['number']).strip()
            if offset>=len(expected) or sample!=str(expected[offset]['number']).strip() or row.get('sid')!=expected[offset].get('sid'):
                raise ValueError('正式紀錄的樣品順序或明細不一致。')
            offset+=1
            if sample.upper() in seen or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*',sample):
                raise ValueError('樣品編號格式無效或重複。')
            seen.add(sample.upper())
            result=row['result'];value=str(result['report']).strip()
            # Validate every result, not just the representative row.
            representative([row],method)
            if result['dup'].get('passed') is False or result.get('needs_review'):
                raise ValueError(sample+'：DUP不符合，不能匯出。')
            data.analysis_rows.append(LimsAnalysisRow(sample_id=sample,exam_no=exam,result=value,batch_no=batch_no))
        chosen=representative(rows,method)
        number=None
        if chosen is None:
            remark='整批TNTC；DUP不適用'
        else:
            dup=chosen['result']['dup']
            try:
                raw=float(dup['r']);number=float(Decimal(dup['display']))
                if not isfinite(raw) or raw<0 or not isfinite(number) or number<0 or abs(raw-number)>0.000050001:
                    raise ValueError()
            except (ValueError,KeyError,TypeError,InvalidOperation):
                raise ValueError(chosen['number']+'：DUP數據無效。')
            label='第一筆實際數值' if chosen['result']['report'] not in {'<10','<1'} else '無實際數值，取第一筆未檢出'
            remark='DUP代表樣品：'+chosen['number']+'；'+label
            if dup.get('exempt'):remark+='；兩皿均小於20免管制'
        duplicates.append(number)
        data.qc_rows.append(LimsQcRow(analysis_date=str(record.analysis_start_date),
            analyst=record.analyst_employee_id or '',exam_no=exam,instrument_id='',
            duplicate_result=None,remark=remark,batch_no=batch_no))
    if offset!=len(expected) or not data.analysis_rows:
        raise ValueError('正式紀錄樣品明細不完整。')
    stream=build_lims_excel(template_path,data,analyst_id=record.analyst_employee_id or '',
        analyst_name=record.analyst_name or '',analysis_method=record.method_name or '')
    # The shared exporter rounds RPD to one decimal. Only this workbook's DUP cells
    # are written at four decimals; other methods/exporters remain unchanged.
    workbook=load_workbook(stream)
    sheet=workbook['Lims-品管數據']
    for row,value in enumerate(duplicates,5):
        sheet.cell(row,4).value=value
        sheet.cell(row,4).number_format='0.0000'
    result=BytesIO();workbook.save(result);result.seek(0);return result


def export_formal_lims(db,record):
    import json
    from flask import current_app,send_file
    from models import AnalysisWorkState
    work=db.query(AnalysisWorkState).filter_by(analysis_id=record.analysis_id).first()
    if work is None:return '查無正式紀錄快照。',404
    try:
        state=json.loads(work.state_json)
        output=build_membrane_lims(record,state,Path(current_app.root_path)/'resources'/'lims'/'lims匯入表格.xlsx')
    except FileNotFoundError:
        return '找不到LIMS匯入Excel範本。',404
    except (ValueError,KeyError,TypeError) as exc:
        return '無法匯出LIMS：'+str(exc),422
    return send_file(output,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,download_name=record.method_code+'_LIMS_'+str(record.id)+'.xlsx',max_age=0)
