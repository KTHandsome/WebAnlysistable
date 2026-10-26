"""W427 PFM history. Caller owns commit/rollback; existing common event identity is retained."""
import math
from models import PerformanceMeasurementHistory
from services.performance_history_service import _find_existing_pfm_event, _parse_pfm_datetime


def save_w427_pfm_history(db, results):
    expected = {"PFM_880", "CELL_CHECK_880"}
    if (len(results) != 2 or {r.get("control", {}).get("monitor_item") for r in results} != expected
            or any(r.get("status") not in {"PASS", "FAIL"} for r in results)):
        raise ValueError("請先取得完整兩項 PFM 判定，再儲存。")
    for item in results:
        control = item["control"]
        signal = float(item["signal"])
        if not math.isfinite(signal):
            raise ValueError("PFM 吸光度無效。")
        candidate = {
            "instrument_id": control["instrument_id"], "method_code": "W427",
            "monitor_item": control["monitor_item"], "performance_type": control["performance_type"],
            "sample_id": item["sample_id"], "analysis_datetime": _parse_pfm_datetime(item["analysis_datetime"]),
            "measured_value": signal, "signal_field": "ABSORBANCE",
            "control_import_id": control["import_id"], "control_id": control["control_id"],
            "reference_value": control["reference_value"], "lower_limit": control["lower_limit"],
            "upper_limit": control["upper_limit"], "unit": control["unit"], "status": item["status"],
        }
        if _find_existing_pfm_event(db, candidate) is None:
            db.add(PerformanceMeasurementHistory(**candidate,
                message="W427 UV TXT；880 nm 吸光度直接判定；管制版次：" + str(control.get("control_version") or "")))
            db.flush()
    return len(results)
