"""Manual ICP PFM ratio calculation and atomic update of one work JSON section."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models import IcpImportWorkState
from services.performance_query_service import find_active_performance_control

METHOD_RATIOS = {"W311": "Se/Pb", "M104": "Pb/Cu"}


class IcpPfmConflictError(ValueError):
    pass


def work_token(work):
    return hashlib.sha256(json.dumps(work, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _number(value, label):
    text = str(value if value is not None else "").strip()
    if not text or len(text) > 80:
        raise ValueError(label + "必須為有效數值。")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(label + "必須為有效數值。")
    if not number.is_finite() or (number and abs(number.adjusted()) > 50):
        raise ValueError(label + "必須為有限且合理的數值。")
    return number


def load_icp_pfm_control(form):
    method = str(form.get("method_code") or "").strip().upper()
    monitor = METHOD_RATIOS.get(method)
    if not monitor:
        raise ValueError("此方法尚未設定 ICP 比值性能查核。")
    text = str(form.get("analysis_start_date") or "").strip()
    analysis_date = None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            analysis_date = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            pass
    if analysis_date is None:
        raise ValueError("請先在基本資料設定有效的分析起始日期。")
    control = find_active_performance_control(
        session_factory=SessionLocal, instrument_id=form.get("instrument_id"),
        monitor_item=monitor, performance_type="SIGNAL_RATIO", analysis_date=analysis_date,
    )
    numerator, denominator = monitor.split("/")
    if (str(control.get("numerator_item") or "").strip().upper() != numerator.upper()
            or str(control.get("denominator_item") or "").strip().upper() != denominator.upper()):
        raise ValueError("正式管制設定的分子與分母不符合目前方法，尚無法判定。")
    for field in ("numerator_wavelength_nm", "denominator_wavelength_nm"):
        if _number(control.get(field), "正式設定波長") <= 0:
            raise ValueError("正式設定波長必須大於零。")
    lower = _number(control.get("lower_limit"), "管制下限")
    upper = _number(control.get("upper_limit"), "管制上限")
    if lower > upper:
        raise ValueError("正式管制下限不可大於上限。")
    snapshot = {key: str(value) if isinstance(value, (Decimal, float)) else value
                for key, value in control.items()}
    snapshot.update(method_code=method, analysis_date=analysis_date.isoformat())
    return snapshot


def calculate_icp_pfm(control, numerator_signal, denominator_signal, actor):
    numerator = _number(numerator_signal, "分子感應值")
    denominator = _number(denominator_signal, "分母感應值")
    if numerator < 0 or denominator <= 0:
        raise ValueError("分子感應值不得小於零，分母感應值必須大於零。")
    lower = _number(control.get("lower_limit"), "管制下限")
    upper = _number(control.get("upper_limit"), "管制上限")
    if lower > upper:
        raise ValueError("管制下限不可大於上限。")
    user_id = str(actor.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("尚未取得登入操作者。")
    with localcontext() as context:
        context.prec = 200
        ratio = numerator / denominator
        # Compare the exact products, never the rounded display ratio.
        passed = lower * denominator <= numerator <= upper * denominator
        display = format(ratio, ".6f")
    return {
        "source_type": "MANUAL", "date_source": "ANALYSIS_START_DATE",
        "analysis_date": control["analysis_date"], "method_code": control["method_code"],
        "instrument_id": control["instrument_id"],
        "numerator_signal": str(numerator), "denominator_signal": str(denominator),
        "ratio": str(ratio), "ratio_display": display,
        "result": "PASS" if passed else "FAIL", "control": control,
        "entered_by_user_id": user_id,
        "entered_by_employee_id": str(actor.get("employee_id") or "").strip(),
        "entered_by_name": str(actor.get("employee_name") or "").strip(),
        "entered_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
    }


def save_icp_pfm(work_key, expected_token, pfm):
    """Update only the PFM section; reject a stale whole-work snapshot."""
    db = SessionLocal()
    try:
        row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == work_key).first()
        if row is None:
            raise IcpPfmConflictError("目前工作已不存在，請重新開啟。")
        original_json = row.state_json
        work = json.loads(original_json)
        if work_token(work) != expected_token:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存 PFM。")
        previous = work.get("pfm_manual")
        pfm = dict(pfm)
        form = work.get("form_data") or {}
        try:
            form_day = datetime.strptime(str(form.get("analysis_start_date") or "").strip().replace("/", "-"), "%Y-%m-%d").date().isoformat()
        except ValueError:
            raise ValueError("工作分析起始日期格式錯誤。")
        if (str(form.get("instrument_id") or "").strip() != pfm.get("instrument_id")
                or str(form.get("method_code") or "").strip().upper() != pfm.get("method_code")
                or form_day != pfm.get("analysis_date")):
            raise ValueError("PFM 與目前工作基本資料不一致。")
        work["pfm_manual"] = pfm
        pending_json = json.dumps(work, ensure_ascii=False)
        result = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key,
            IcpImportWorkState.state_json == original_json,
        ).values(state_json=pending_json))
        if result.rowcount != 1:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存 PFM。")
        # The successful work CAS also serializes SQLite writers before history lookup.
        from services.icp_pfm_history_service import sync_icp_pfm_history
        pfm["history_event_id"] = sync_icp_pfm_history(db, work_key, pfm, previous)
        final = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key,
            IcpImportWorkState.state_json == pending_json,
        ).values(state_json=json.dumps(work, ensure_ascii=False)))
        if final.rowcount != 1:
            raise IcpPfmConflictError("工作資料已更新，本次 PFM 與歷程均未儲存。")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise IcpPfmConflictError("PFM 歷程已由其他工作更新，本次未儲存，請重新載入後再確認。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
