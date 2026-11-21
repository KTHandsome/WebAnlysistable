"""Validation shared by E215 formal submission and PDF export (Python 3.8)."""
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation


def _batch_dates(fields, prefix):
    try:
        if not all(isinstance(v, str) for v in fields[3:6]) or len(fields) != 6:
            raise ValueError("Invalid date fields")
        for value in fields[4:6]:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?", value):
                raise ValueError("Expected local date and time")
        sampling = date.fromisoformat(fields[3])
        start = datetime.fromisoformat(fields[4])
        end = datetime.fromisoformat(fields[5])
        if start.tzinfo is not None or end.tzinfo is not None:
            raise ValueError('Expected local datetime')
    except (ValueError, TypeError, IndexError):
        raise ValueError(prefix + '採樣日期或培養起迄日期／時間未填或格式錯誤。')
    # e215-sampling-date-order-v1
    if sampling > start.date():
        raise ValueError(prefix + '採樣日期不可晚於培養起始日期。')
    duration = end - start
    if not timedelta(hours=18) <= duration <= timedelta(hours=22):
        hours = duration.total_seconds() / 3600
        raise ValueError(prefix + '培養時間須介於 18～22 小時（含上下限），目前為 {:g} 小時。'.format(hours))
    return sampling, start


def _below_one(value):
    text = str(value).strip().replace('＜', '<').replace('＞', '>')
    try:
        if text.startswith('<'):
            bound = Decimal(text[1:].strip())
            return bound.is_finite() and Decimal(0) < bound <= Decimal(1)
        number = Decimal(text)
        return number.is_finite() and Decimal(0) <= number < Decimal(1)
    except (InvalidOperation, ValueError):
        return False


def validate_batches(batches, include_ecoli=False):
    target = 'E. coli' if include_ecoli else 'Coliform'
    if not batches:
        raise ValueError('查無可驗證的 E215 批次資料。')
    for index, batch in enumerate(batches, 1):
        prefix = '批次 {}：'.format(index)
        sampling, start = _batch_dates(batch.get('fields', []), prefix)
        rows = batch.get('rows') or []
        if not rows or rows[0].get('sample_id') != '實驗室空白':
            raise ValueError(prefix + '缺少實驗室空白。')
        blank = rows[0]
        selected = [line for line in blank.get('lines', []) if line.get('selected') is True]
        if len(selected) != 1:
            raise ValueError(prefix + '實驗室空白：請選取一個報告倍數。')
        outputs = [output for output in selected[0].get('outputs', []) if output.get('analyte') == target]
        if len(outputs) != 1 or not _below_one(outputs[0].get('adjusted', '')):
            raise ValueError(prefix + '實驗室空白：{} 選定倍數的結果必須小於 1 MPN/100 mL。'.format(target))
        for row in rows[1:]:
            name = str(row.get('sample_id') or '未填樣品編號')
            try:
                text = row.get('time', '')
                if not isinstance(text, str) or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?', text):
                    raise ValueError('Invalid sampling time')
                sampled = time.fromisoformat(text)
            except (TypeError, ValueError):
                raise ValueError(prefix + name + '：請填寫有效的採樣時間。')
            if sampling == start.date() and start <= datetime.combine(sampling, sampled):
                raise ValueError(prefix + name + '：同日採樣時，培養起始時間必須晚於採樣時間。')
