"""W427 PFM: direct absorbance; independent of reported phosphorus basis."""
import math
from datetime import datetime

MONITORS = {"PFM": "PFM_880", "CELL_CHECK": "CELL_CHECK_880"}


def evaluate_w427_performance(rows, form, lookup):
    results = []
    for role, monitor in MONITORS.items():
        matches = [r for r in rows if r.get("role") == role]
        item = {"sample_id": "PFM" if role == "PFM" else "石英槽比對",
                "analysis_datetime": "", "signal": None, "signal_field": "ABSORBANCE",
                "control": {}, "status": "UNDETERMINED", "message": ""}
        results.append(item)
        try:
            if len(matches) != 1:
                raise ValueError("{} 須恰有一筆原始量測，目前 {} 筆；請確認檔案。".format(item["sample_id"], len(matches)))
            row = matches[0]
            item.update(sample_id=row["sample_id"], analysis_datetime=row["measured_at"].replace("T", " "), signal=row["absorbance"])
            datetime.strptime(item["analysis_datetime"], "%Y-%m-%d %H:%M:%S")
            day = datetime.strptime(str(form.get("analysis_start_date") or ""), "%Y-%m-%d").date()
            control = lookup(instrument_id=form.get("instrument_id"), monitor_item=monitor,
                             performance_type="CAL_HIGH_SIGNAL", analysis_date=day)
            item["control"] = control
            if (control.get("instrument_id") != form.get("instrument_id")
                    or control.get("monitor_item") != monitor
                    or control.get("performance_type") != "CAL_HIGH_SIGNAL"
                    or control.get("unit") != "Abs"):
                raise ValueError("PFM 管制識別或單位不符，須為所選儀器的 880 nm 吸光度管制。")
            if any(control.get(k) is None for k in ("reference_value", "lower_limit", "upper_limit")):
                raise ValueError("參考值或上下限尚未完整設定。")
            reference, lower, upper, signal = (float(v) for v in
                (control["reference_value"], control["lower_limit"], control["upper_limit"], item["signal"]))
            if not all(math.isfinite(v) for v in (reference, lower, upper, signal)) or lower > upper:
                raise ValueError("PFM 數值或上下限無效。")
            item["status"] = "PASS" if lower <= signal <= upper else "FAIL"
        except Exception as exc:
            item["message"] = str(exc)
    return results
