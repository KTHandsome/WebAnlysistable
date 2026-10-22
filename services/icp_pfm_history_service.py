"""Manual ICP PFM events in the caller's transaction; no formal analysis link.

The day is stored at midnight solely to fit the existing DateTime event key.
It is a date-only value, never a claimed instrument measurement time.
"""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from models import IcpImportWorkState, PerformanceMeasurementHistory, PerformanceAnalysisLink
from services.performance_history_service import _compare_pfm_event
from services.icp_performance_service import calculate_icp_pfm, IcpPfmConflictError, METHOD_RATIOS

DATE_MESSAGE = "ICP 手動 PFM；日期來源：基本資料分析起始日，未提供實際測定時間。"


def _stored_number(value, required=False):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError("PFM 歷程缺少必要數值。")
        return None
    try:
        with localcontext() as context:
            context.prec = 200
            original = Decimal(str(value))
            if not original.is_finite() or abs(original) >= Decimal("1000000000000"):
                raise ValueError("PFM 數值超出歷程欄位可儲存範圍。")
            stored = original.quantize(Decimal("0.00000001"))
            if original and not stored:
                raise ValueError("PFM 數值小於歷程欄位可儲存精度。")
            return float(stored)
    except InvalidOperation:
        raise ValueError("PFM 歷程數值格式錯誤。")


def _candidate(pfm):
    control = pfm.get("control") or {}
    method = str(pfm.get("method_code") or "").strip().upper()
    if (method not in METHOD_RATIOS or pfm.get("source_type") != "MANUAL" or pfm.get("date_source") != "ANALYSIS_START_DATE"
            or str(control.get("monitor_item") or "").upper() != str(METHOD_RATIOS.get(method) or "").upper()
            or control.get("performance_type") != "SIGNAL_RATIO"):
        raise ValueError("ICP PFM 來源或管制項目不一致。")
    actor = {"user_id": pfm.get("entered_by_user_id")}
    verified = calculate_icp_pfm(control, pfm.get("numerator_signal"), pfm.get("denominator_signal"), actor)
    if (Decimal(str(pfm.get("ratio"))) != Decimal(verified["ratio"])
            or pfm.get("result") != verified["result"]
            or method != verified["method_code"]
            or pfm.get("instrument_id") != verified["instrument_id"]
            or pfm.get("analysis_date") != verified["analysis_date"]):
        raise ValueError("ICP PFM 儲存內容與計算結果不一致。")
    try:
        day = datetime.strptime(str(pfm["analysis_date"]), "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("ICP PFM 分析日期格式錯誤。")
    return {"instrument_id": verified["instrument_id"], "method_code": method,
            "monitor_item": str(control["monitor_item"]), "performance_type": "SIGNAL_RATIO",
            "sample_id": "PFM", "analysis_datetime": day,
            "measured_value": _stored_number(verified["ratio"], True), "signal_field": "SIGNAL_RATIO",
            "control_import_id": control.get("import_id"), "control_id": control.get("control_id"),
            "reference_value": _stored_number(control.get("reference_value")),
            "lower_limit": _stored_number(control.get("lower_limit"), True),
            "upper_limit": _stored_number(control.get("upper_limit"), True),
            "unit": str(control.get("unit") or ""), "status": verified["result"]}


def _other_work_references(db, work_key, event_id):
    rows = db.query(IcpImportWorkState.work_key, IcpImportWorkState.state_json).filter(
        IcpImportWorkState.work_key != work_key,
        IcpImportWorkState.state_json.contains('"history_event_id"'),
    ).all()
    for other_key, content in rows:
        try:
            stored = json.loads(content)
        except (TypeError, ValueError):
            raise IcpPfmConflictError("其他 PFM 工作資料格式異常，尚不可覆寫歷程。")
        if (stored.get("pfm_manual") or {}).get("history_event_id") == event_id:
            return True
    return False


def sync_icp_pfm_history(db, work_key, pfm, previous):
    """Reuse identical daily events; edit only an exclusively owned work event."""
    candidate = _candidate(pfm)
    event = db.query(PerformanceMeasurementHistory).filter(
        PerformanceMeasurementHistory.instrument_id == candidate["instrument_id"],
        PerformanceMeasurementHistory.monitor_item == candidate["monitor_item"],
        PerformanceMeasurementHistory.performance_type == candidate["performance_type"],
        PerformanceMeasurementHistory.analysis_datetime == candidate["analysis_datetime"],
    ).with_for_update().first()
    if event is None:
        event = PerformanceMeasurementHistory(**candidate, message=DATE_MESSAGE)
        db.add(event)
        db.flush()
        return event.id
    current = {key: getattr(event, key) for key in candidate}
    if _compare_pfm_event(current, candidate) == "MATCH":
        return event.id
    owned = (isinstance(previous, dict) and previous.get("history_event_id") == event.id
             and event.message == DATE_MESSAGE)
    if owned:
        owned = _compare_pfm_event(current, _candidate(previous)) == "MATCH"
    linked = db.query(PerformanceAnalysisLink.id).filter(
        PerformanceAnalysisLink.performance_id == event.id).first()
    if not owned or linked or _other_work_references(db, work_key, event.id):
        raise IcpPfmConflictError("同一儀器、PFM 項目及分析日期已有不同紀錄，或紀錄已共用；本次未儲存，請先確認原紀錄。")
    for key, value in candidate.items():
        setattr(event, key, value)
    db.flush()
    return event.id
