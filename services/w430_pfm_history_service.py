"""Explicit W430 PFM save; caller owns the transaction."""
from models import PerformanceMeasurementHistory
from services.performance_history_service import _find_existing_pfm_event, _parse_pfm_datetime


def save_w430_pfm_history(db, results):
    if not results or any(r.get("status") not in {"PASS", "FAIL"} for r in results):
        raise ValueError("請先取得完整 PFM 判定，再儲存。")
    count = 0
    for item in results:
        control = item["control"]
        candidate = {
            "instrument_id": control["instrument_id"], "method_code": "W430",
            "monitor_item": control["monitor_item"], "performance_type": control["performance_type"],
            "sample_id": item["sample_id"],
            "analysis_datetime": _parse_pfm_datetime(item["analysis_datetime"]),
            "measured_value": float(item["signal"]), "signal_field": "ABSORBANCE",
            "control_import_id": control["import_id"], "control_id": control["control_id"],
            "reference_value": control.get("reference_value"), "lower_limit": control["lower_limit"],
            "upper_limit": control["upper_limit"], "unit": control.get("unit") or "", "status": item["status"],
        }
        event = _find_existing_pfm_event(db, candidate)
        if event is None:
            db.add(PerformanceMeasurementHistory(**candidate, message="W430 UV TXT；使用實際測定日期時間。"))
            db.flush()
        count += 1
    return count
