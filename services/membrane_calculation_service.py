"""E202/E230 calculations. User-supplied method text takes precedence over old XLS formulas."""
from decimal import Decimal, ROUND_HALF_UP
from math import log10, isfinite
import re


def count(value):
    value = str(value or '').strip().upper() if value != 0 else '0'
    if value == 'TNTC':
        return None
    if not re.fullmatch(r'[0-9]{1,9}', value):
        raise ValueError('X、Y 請填非負整數或 TNTC；未測定請刪除該稀釋列。')
    return int(value)


def rounded(value, minimum):
    value = Decimal(value)
    if value < minimum:
        return '<' + str(minimum)
    if value < 100:
        return str(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    q = value.quantize(Decimal(1).scaleb(value.adjusted()-1), rounding=ROUND_HALF_UP)
    exp = q.adjusted()
    return format(q.scaleb(-exp), '.1f') + 'E+' + str(exp)


def duplicate(x, y, upper):
    upper = float(upper)
    if not isfinite(upper) or upper < 0:
        raise ValueError('DUP 管制上限無效。')
    a, b = (x+1, y+1) if x == 0 or y == 0 else (x, y)
    r = abs(log10(a)-log10(b))
    exempt = x < 20 and y < 20
    return dict(r=r, display=format(r, '.4f'), upper=upper, exempt=exempt,
                passed=exempt or r <= upper,
                status='兩皿均小於20，免管制' if exempt else ('通過' if r <= upper else '超出管制上限，須重新分析'))


def tntc_result(lines, reason):
    factors = sorted(p['factor'] for p in lines)
    return dict(report='TNTC', density=None,
                factor=factors[0] if len(factors) == 1 else None,
                factors=factors, reason=reason,
                dup=dict(r=None, display='-', status='TNTC無法定量，DUP不適用',
                         applicable=False, passed=None, exempt=False),
                needs_review=False)


def calculate_sample(method, lines, upper):
    if method not in {'E202', 'E230'}:
        raise ValueError('不支援此方法。')
    parsed = []
    factors = set()
    for line in lines:
        try:
            factor = int(str(line.get('factor', '')))
        except ValueError:
            raise ValueError('請選擇有效的稀釋倍數。')
        if factor not in {1,10,100,1000,10000,100000,1000000} or factor in factors:
            raise ValueError('稀釋倍數不符或重複。')
        factors.add(factor)
        parsed.append(dict(factor=factor, x=count(line.get('x')), y=count(line.get('y'))))
    if not parsed:
        raise ValueError('請至少填寫一組二重複數據。')
    reason = ''
    if method == 'E230':
        if len(parsed) != 1 or parsed[0]['factor'] != 1:
            raise ValueError('E230 以兩皿各100 mL原液計算，不套用 E202 的稀釋選皿規則。')
        chosen = parsed[0]
        reason = '兩皿各100 mL，取平均'
        if chosen['x'] is None or chosen['y'] is None:
            return tntc_result([chosen], '培養皿含TNTC，無法定量')
    else:
        original = next((p for p in parsed if p['factor'] == 1), None)
        if original and original['x'] == original['y'] == 0:
            chosen = original
            reason = '原液兩皿均無菌落'
        else:
            both = [p for p in parsed if p['x'] is not None and p['y'] is not None and 20 <= p['x'] <= 80 and 20 <= p['y'] <= 80]
            any_in_range = [p for p in parsed if any(v is not None and 20 <= v <= 80 for v in (p['x'],p['y']))]
            if len(both) == 1:
                chosen, reason = both[0], '唯一一組兩皿均在20～80'
            elif len(both) > 1:
                raise ValueError('多個稀釋度兩皿均在20～80；現有規定未能唯一選定，請依SOP確認後處理。')
            elif len(any_in_range) == 1:
                chosen, reason = any_in_range[0], '唯一一組有一皿在20～80'
            elif len(any_in_range) > 1:
                raise ValueError('多個稀釋度有菌落數在20～80；請依SOP確認選皿方式。')
            else:
                values = [v for p in parsed for v in (p['x'],p['y']) if v is not None]
                if not values:
                    return tntc_result(parsed, '各已測稀釋度均為TNTC，無可定量數據')
                target = 20 if all(v < 20 for v in values) else 80
                distance = min(abs(v-target) for v in values)
                candidates = [p for p in parsed if any(v is not None and abs(v-target) == distance for v in (p['x'],p['y']))]
                if len(candidates) != 1:
                    raise ValueError('多個稀釋度同樣接近{}，請依SOP確認選皿方式。'.format(target))
                chosen = candidates[0]
                reason = '排除TNTC後，菌落數最接近{}'.format(target)
        if chosen['x'] is None or chosen['y'] is None:
            return tntc_result([chosen], '選定稀釋度含TNTC，無法定量')
    x, y = chosen['x'], chosen['y']
    density = Decimal(x+y) / 2 if method == 'E230' else Decimal(5) * chosen['factor'] * (x+y)
    # E230: zero colonies -> <1; a positive 0.5 rounds to 1 per supplied method text.
    report = '<1' if method == 'E230' and x == y == 0 else rounded(density, 0 if method == 'E230' else 10)
    return dict(density=str(density), report=report, factor=chosen['factor'], x=x, y=y,
                reason=reason, dup=duplicate(x,y,upper), needs_review=False)
