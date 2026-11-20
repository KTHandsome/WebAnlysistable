"""Validated, reproducible membrane snapshots for the shared record repository."""
from copy import deepcopy
from services.membrane_dates_service import normalize_data
from services.membrane_calculation_service import calculate_sample, count
from services.membrane_validation_service import validate_times


def formal_state(data, method, control, linked_id=None):
    if method not in {'E202','E230'} or not data.get('samples'):
        raise ValueError('請至少加入一筆樣品。')
    data=normalize_data(data)
    validate_times(data, strict=True)
    batches, samples, names = [], [], set()
    for i, raw in enumerate(data['batches']):
        batch = deepcopy(raw)
        for key in ('medium','temperature'):
            if not str(batch.get(key) or '').strip():
                raise ValueError('批次{}：培養基及培養溫度不可空白。'.format(i+1))
        rows = [dict(batch['blank'], number='實驗室空白', sid='BLANK-'+str(i), blank=True)]
        rows += deepcopy(data['samples'][i*10:i*10+10])
        for row in rows:
            name = row.get('number','').strip()
            if not name:
                raise ValueError('請填寫樣品編號。')
            if not row.get('blank'):
                if name in names:
                    raise ValueError(name+'：樣品編號重複。')
                names.add(name)
            try:
                result = calculate_sample(method,row['lines'],control['DC_UCL'])
            except ValueError as exc:
                raise ValueError(name+'：'+str(exc)) from exc
            if row.get('blank'):
                if len(row['lines']) != 1 or str(row['lines'][0]['factor']) != '1' or any(count(row['lines'][0][k]) != 0 for k in ('x','y')):
                    raise ValueError('批次{}：實驗室空白兩皿必須皆為0，且使用原液。'.format(i+1))
            if result['dup'].get('passed') is False or result.get('needs_review'):
                raise ValueError(name+'：DUP不符合管制要求，須重新分析。')
            row['number'] = name
            row['result'] = result
            samples.append(dict(sample_id=name,role='BLANK' if row.get('blank') else 'SAMPLE',
                dilution_factor=result.get('factor'), sample_volume=100 if method=='E230' else 10,
                remark=result['report']+' CFU/100 mL；DUP '+result['dup']['display']))
        batch['rows'] = rows
        batches.append(batch)
    state = dict(membrane_format=1,data=deepcopy(data),membrane_batches=batches,sample_qaqc_rows=samples)
    if linked_id:
        state['formal_analysis_id'] = linked_id
    return state
