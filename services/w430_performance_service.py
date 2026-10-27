"""Read-only W430 PFM evaluation against the ACTIVE release."""
import math
from services.basic_info_validation_service import parse_basic_info_date


def apply_w430_performance(analysis, preview, form, lookup):
    results = []
    for row in preview["rows"]:
        if row["role"] not in {"MAX_ABS", "CELL_CHECK", "PFM"}:
            continue
        item = {"sample_id": row["sample_id"], "analysis_datetime": row["measured_at"],
                "signal": row["absorbance"], "signal_field": "ABSORBANCE",
                "control": {}, "status": "UNDETERMINED", "message": ""}
        results.append(item)
        try:
            if row["role"] == "PFM":
                raise ValueError("PFM 名稱尚未指定對應查核項目，請使用最大吸光值或石英槽比對。")
            day = parse_basic_info_date(form.get("analysis_start_date"), "分析起始日期")
            control = lookup(instrument_id=form.get("instrument_id"),
                             monitor_item=row["role"], performance_type="CAL_HIGH_SIGNAL",
                             analysis_date=day)
            item["control"] = control
            if any(control.get(k) is None for k in ("lower_limit", "upper_limit")):
                raise ValueError("查核上下限未完整設定。")
            lower, upper = float(control["lower_limit"]), float(control["upper_limit"])
            signal = float(row["absorbance"])
            if not all(math.isfinite(v) for v in (lower, upper, signal)) or lower > upper:
                raise ValueError("查核數值或上下限無效。")
            item["status"] = "PASS" if lower <= signal <= upper else "FAIL"
        except Exception as exc:
            item["message"] = str(exc)
    analysis["prm_results"] = results
