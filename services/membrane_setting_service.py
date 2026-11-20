import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from services.membrane_dates_service import effective_control

METHODS = {'E202', 'E230'}


def is_membrane(form):
    return str(form.get('method_code') or '').strip().upper() in METHODS


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return [{k:(v or '').strip() for k,v in row.items() if k is not None} for row in csv.DictReader(f)]


def options(root, year):
    data = Path(root)/'data'
    methods = [r for r in read_csv(data/'Phyon_Method_Settings.csv')
               if r.get('METHOD_CODE','').upper() in METHODS and r.get('ACTIVE','').upper() == 'Y'
               and r.get('DATA_ENTRY_MODE','').upper() == 'MANUAL']
    controls = read_csv(data/('Phyon_Control_'+str(year)+'.csv')) if str(year).isdigit() and len(str(year)) == 4 else []
    result = []
    for method in methods:
        found = [r for r in controls if r.get('CTRL_YEAR') == str(year)
                 and r.get('EXAMNO') == method.get('EXAMNO')
                 and r.get('CATEGORY_CODE') == method.get('CATEGORY_CODE')
                 and r.get('EM_NUM','').upper() == method.get('METHOD_CODE','').upper()]
        result.append(dict(method, control=effective_control(found[0]) if len(found) == 1 else None))
    return result


def settings(root, form):
    found = [o for o in options(root, form.get('ctrl_year',''))
             if o.get('METHOD_CODE','').upper() == form.get('method_code','').upper()
             and o.get('CATEGORY_CODE') == form.get('category') and o.get('EXAMNAME') == form.get('exam_name')
             and (not form.get('selected_exam_no') or o.get('EXAMNO') == form.get('selected_exam_no'))]
    if len(found) != 1:
        raise ValueError('請選擇唯一對應的 E202／E230 類別與測項。')
    item = found[0]
    control = item.get('control')
    if not control or control.get('DC') != '1':
        raise ValueError('查無此年度、檢項的DUP管制設定。')
    try:
        upper = Decimal(control.get('DC_UCL',''))
        if not upper.is_finite() or upper < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ValueError('DUP 管制上限 DC_UCL 未填或無效。')
    return item, control


def entry_dates(form):
    try:
        start,end,_ = [date.fromisoformat(form.get(k,'')) for k in ('analysis_start_date','analysis_end_date','form_date')]
    except ValueError:
        raise ValueError('請填妥分析起始日、分析結束日及填表日期。')
    if end < start:
        raise ValueError('分析結束日不可早於起始日。')
