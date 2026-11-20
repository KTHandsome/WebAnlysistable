import os
from datetime import timedelta

SQL = """SELECT A.SID, S.KEEPID, A.EXAMNO, A.ANAMAN, S.KEEPDATE, S.SAMPEDATE, S.SAMPETIME, S.SAMPSDATE, S.SAMPSTIME, S.KEEPTIME
FROM ANALYSIS A
JOIN SAMPLE S ON S.SID = A.SID
JOIN EMPLOY Y ON Y.EMPID = A.ANAMAN
JOIN EXAMITEM M ON M.EXAMNO = A.EXAMNO
WHERE A.EXAMNO = ?
  AND A.DONE = 0
  AND A.ANAMAN = ?
  AND S.KEEPDATE >= ?
  AND S.KEEPDATE < ?
ORDER BY S.KEEPDATE, S.KEEPID, A.SID"""


def query_samples(cursor, exam_no, employee_id, received_from, analysis_date):
    if not exam_no or not employee_id:
        raise ValueError("缺少檢驗項目代碼或分析人員。")
    if received_from > analysis_date:
        raise ValueError("收樣起日不可晚於分析日。")
    cursor.execute(SQL, (exam_no, employee_id, received_from, analysis_date + timedelta(days=1)))
    return cursor.fetchall()


def resolve_lookup_employee(user, environ, remote_addr):
    employee = str(user.get("employee_id") or "").strip()
    user_id = str(user.get("user_id") or "").strip()
    allowed = environ.get("PHYON_E215_DEV_LOOKUP_USER_ID", "").strip()
    if (environ.get("PHYON_ENABLE_DEV_LOGIN") == "1"
            and environ.get("PHYON_E215_DEV_LOOKUP") == "1"
            and remote_addr in {"127.0.0.1", "::1"}
            and allowed and user_id == allowed):
        return "A100-33", True
    return employee, False


def load_page(item, form, user, args, logger):
    from datetime import date
    from contextlib import closing
    from flask import request
    employee_id, test_lookup = resolve_lookup_employee(user, os.environ, request.remote_addr)
    page = dict(test_employee=employee_id if test_lookup else None,
                start=args.get("received_from", form["analysis_start_date"]),
                end=form["analysis_start_date"], rows=None, error=None)
    if args.get("lookup") != "1":
        return page
    try:
        start, end = date.fromisoformat(page["start"]), date.fromisoformat(page["end"])
    except ValueError:
        page["error"] = "請輸入有效的收樣起日及分析日期。"
        return page
    if not employee_id or start > end:
        page["error"] = "缺少登入者員工代碼，或收樣起日晚於分析日。"
        return page
    import pyodbc
    from services.lims_analysis_service import get_analysis_connection_string
    try:
        with closing(pyodbc.connect(get_analysis_connection_string(), timeout=5)) as conn:
            with closing(conn.cursor()) as cursor:
                rows = query_samples(cursor, item["EXAMNO"], employee_id, start, end)
        page['rows']=[]
        for r in rows:
            sample_date,sample_time=(r[7],r[8]) if r[6] is None else (r[5],r[6])
            page['rows'].append(dict(sid=r[0],number=r[1],employee=r[3],
                received=r[4].strftime('%Y-%m-%d') if r[4] else '—',
                sampled_at=timestamp(sample_date,sample_time),received_at=timestamp(r[4],r[9])))
    except (pyodbc.Error, ValueError, RuntimeError):
        logger.warning("Membrane LIMS sample lookup failed")
        page["error"] = "無法查詢 LIMS，請稍後重試或確認 LIMS 連線。"
    return page


def timestamp(day,clock):
    from datetime import date,datetime,time
    import re
    if day is None or clock is None:return ''
    try:
        if isinstance(day,datetime):day=day.date()
        if not isinstance(day,date):day=date.fromisoformat(str(day).strip()[:10])
        if isinstance(clock,datetime):clock=clock.time()
        if not isinstance(clock,time):
            text=str(clock).strip()
            if re.fullmatch(r'\d{4}',text):text=text[:2]+':'+text[2:]
            clock=time.fromisoformat(text)
        return day.isoformat()+'T'+clock.strftime('%H:%M')
    except (TypeError,ValueError):return ''
