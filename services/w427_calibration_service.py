"""W427 adapter for the existing single-analyte OLS calculator; no writes."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math
from calculations.w43401 import calculate_calibration


def _decimal(text, label):
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(label + "必須是有效數值。")
    if not value.is_finite() or not math.isfinite(float(value)):
        raise ValueError(label + "必須是有限數值。")
    return value


def build_w427_calibration(preview, method_data):
    method = deepcopy(method_data)
    for key in ("UI_CALIBRATION_X_DECIMALS", "UI_SIGNAL_DECIMALS"):
        if not str(method.get(key) or "").strip():
            method[key] = "4"
    state = {"method_data": method, "calibration_rows": [], "calibration_result": None,
             "calibration_error": "", "calibration_warnings": []}
    try:
        if (str(method.get("METHOD_CODE") or "").upper() != "W427"
                or method.get("CALIBRATION_UNIT") != "mg P/L"):
            raise ValueError("W427 檢量線必須使用 mg P/L，不套用報告結果換算。")
        count = int(method.get("CALIBRATION_COUNT") or 0)
        values = str(method.get("CALIBRATION_VALUES") or "").split("|")
        if count < 6 or count != len(values):
            raise ValueError("方法設定須包含空白及至少五個標準濃度，且點數與濃度清單一致。")
        expected = [_decimal(v, "檢量線設定濃度") for v in values]
        if expected[0] != 0 or any(b <= a for a, b in zip(expected, expected[1:])):
            raise ValueError("檢量線須由零點開始，濃度依序遞增。")
        standards = [row for row in preview["rows"] if row.get("role") == "STANDARD"]
        names = {"STD" + str(i) for i in range(count)}
        indexed = {}
        for row in standards:
            name = str(row.get("sample_id") or "").strip().upper()
            if name in indexed or name not in names:
                raise ValueError("標準名稱重複或無法對應方法設定，請確認 STD0～STD{}；未自動選點。".format(count - 1))
            indexed[name] = row
        if set(indexed) != names:
            missing = ", ".join("STD" + str(i) for i in range(count) if "STD" + str(i) not in indexed)
            raise ValueError("檢量線缺少 {}，請將檢量線檔與樣品檔一起匯入。".format(missing))
        ordered = []
        for i, concentration in enumerate(expected):
            name = "STD" + str(i)
            row = indexed[name]
            actual = _decimal(row.get("instrument_conc_text", ""), name + " TXT Conc.")
            if actual != concentration:
                raise ValueError("{} 的 TXT Conc.={} 與方法設定 {} mg P/L 不一致；未建立回歸。".format(
                    name, row.get("instrument_conc_text"), values[i]))
            signal = float(row["absorbance"])
            if not math.isfinite(signal):
                raise ValueError(name + " 吸光度不是有限數值。")
            ordered.append({"sequence_no": row["row_id"], "sample_id": name, "role": "STANDARD",
                            "calibration_x": float(concentration), "signal": signal})
        result = calculate_calibration(ordered)
        if (not all(math.isfinite(float(result[k])) for k in ("slope", "intercept", "r"))
                or result["slope"] <= 0
                or any(point["back_calculated_x"] is None
                       or not math.isfinite(point["back_calculated_x"]) for point in result["points"])):
            raise ValueError("檢量線斜率或回歸結果無效，請確認原始標準資料。")
        state["calibration_rows"] = ordered
        state["calibration_result"] = result
        if not result["passed"]:
            state["calibration_warnings"].append("檢量線 r 未達共用判定標準 r > 0.995，請確認原始資料。")
    except (ValueError, TypeError, OverflowError, ZeroDivisionError, ArithmeticError) as exc:
        state["calibration_error"] = str(exc)
    return state
