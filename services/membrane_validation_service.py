"""Per-sample chronology; shared incubation starts within 24h and lasts 22-26h."""
import re
from datetime import datetime,timedelta
from services.membrane_dates_service import normalize_data

def validate_times(data,form=None,strict=False):
    data=normalize_data(data);results=[]
    def parse(value,pattern,fmt,label,issues):
        if not isinstance(value,str) or not value:
            issues.append(label+'尚未填寫。');return None
        try:
            if not re.fullmatch(pattern,value):raise ValueError()
            return datetime.strptime(value,fmt)
        except ValueError:
            issues.append(label+'格式或日期無效。');return None
    def stamp(value,label,issues):return parse(value,r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}','%Y-%m-%dT%H:%M',label,issues)
    for i,batch in enumerate(data.get('batches',[])):
        issues=[]
        analysis=parse(batch.get('inspection_date'),r'\d{4}-\d{2}-\d{2}','%Y-%m-%d','檢驗分析日期',issues)
        start=stamp(batch.get('start'),'培養開始日期時間',issues)
        end=stamp(batch.get('end'),'培養結束日期時間',issues)
        if start and end and not timedelta(hours=22)<=end-start<=timedelta(hours=26):
            issues.append('培養開始至結束須介於22～26小時（含邊界）。')
        for row in data.get('samples',[])[i*10:i*10+10]:
            name=row.get('number') or row.get('sid') or '未命名樣品'
            sampled=stamp(row.get('sampled_at'),name+'：採樣日期時間',issues)
            received=stamp(row.get('received_at'),name+'：收檢日期時間',issues)
            clock=parse(row.get('inspection'),r'\d{2}:\d{2}','%H:%M',name+'：檢驗時間',issues)
            tested=datetime.combine(analysis.date(),clock.time()) if analysis and clock else None
            for earlier,later,message in [(sampled,received,'收檢不可早於採樣'),(received,tested,'檢驗不可早於收檢'),(tested,start,'培養開始不可早於檢驗'),(sampled,start,'培養開始不可早於採樣')]:
                if earlier and later and later<earlier:issues.append(name+'：'+message+'日期時間。')
            if sampled and start and start-sampled>timedelta(hours=24):
                issues.append(name+'：須於採樣後24小時內開始培養。')
        results.append(dict(batch=i,issues=issues,passed=not issues))
    if strict:
        errors=['批次'+str(r['batch']+1)+'：'+v for r in results for v in r['issues']]
        if errors:raise ValueError('\n'.join(errors))
    return results
