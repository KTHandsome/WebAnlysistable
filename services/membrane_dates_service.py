"""Normalize legacy membrane drafts without inventing missing sample times."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def effective_control(control):
    result=deepcopy(control)
    try:
        source=result.get('DC_UCL_SOURCE',result.get('DC_UCL',''))
        value=Decimal(str(source))
        if not value.is_finite() or value<0:raise InvalidOperation()
        result['DC_UCL_SOURCE']=str(source)
        result['DC_UCL']=format(value.quantize(Decimal('.001'),rounding=ROUND_HALF_UP),'.3f')
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError('DUP管制上限無效。')
    return result

def normalize_data(data):
    if not isinstance(data,dict):raise ValueError('樣品資料格式錯誤。')
    result=deepcopy(data)
    for i,batch in enumerate(result.get('batches',[])):
        for row in result.get('samples',[])[i*10:i*10+10]:
            if 'sampled_at' not in row:
                day=batch.get('sampling_date','');clock=row.get('time','')
                row['sampled_at']=day+'T'+clock if day and clock else ''
            if 'received_at' not in row:
                row['received_at']=batch.get('received_at','')
    return result
