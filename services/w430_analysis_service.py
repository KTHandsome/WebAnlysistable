"""Adapt W430 mass-based results to the shared single-analyte components.

No database or session writes. Original instrument values are retained.
"""
import math
from collections import defaultdict
from copy import deepcopy

from calculations.w43401 import calculate_calibration
from analysis.qaqc_calculator import build_qaqc_check_results


def _finite(value, label, positive=False):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(label + "未設定或不是數值。")
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(label + "必須為有效" + ("正數。" if positive else "數值。"))
    return number


def _optional(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def build_w430_analysis(preview, form_data, method_data, control_data):
    method = deepcopy(method_data)
    # Display defaults are local to W430 and never written to shared settings.
    for key, value in {
        "UI_CALIBRATION_X_DECIMALS": "4", "UI_SIGNAL_DECIMALS": "4",
        "UI_CONCENTRATION_DECIMALS": "4", "UI_CALIBRATION_BACKCALC_DECIMALS": "4",
    }.items():
        if not str(method.get(key) or "").strip():
            method[key] = value
    method["METHOD_CODE"] = "W430"
    state = {
        "method_data": method, "control_data": deepcopy(control_data),
        "calibration_result": None, "calibration_rows": [], "sample_qaqc_rows": [],
        "qaqc_3a_results": [], "prm_results": [], "qdl_value": None,
        "analysis_warnings": [], "analysis_error": None,
    }
    raw = deepcopy(preview["rows"])
    for row in raw:
        if row["role"] in {"PFM", "CELL_CHECK", "MAX_ABS"}:
            state["prm_results"].append({
                "sample_id": row["sample_id"], "analysis_datetime": row["measured_at"],
                "signal": row["absorbance"], "signal_field": "ABSORBANCE", "control": {},
                "status": "UNDETERMINED",
                "message": "已保留吸光度及原始 Conc；UV 查核指標與管制設定尚待確認。",
            })
    standards = [row for row in raw if row["role"] == "STANDARD"]
    if not standards:
        state["analysis_error"] = "尚無檢量線，請將標準與樣品檔一起匯入。"
        return state
    try:
        values = str(method.get("CALIBRATION_VALUES") or "").split("|")
        expected = [_finite(v, "檢量線含量") for v in values]
        count = int(method.get("CALIBRATION_COUNT") or 0)
        if count != len(expected) or count != 9:
            raise ValueError("W430 檢量線應設定 STD0～STD8 共 9 點。")
        if str(method.get("CALIBRATION_UNIT") or "").strip().lower() != "mg":
            raise ValueError("W430 檢量線單位必須為 mg。")
        indexed = {}
        for row in standards:
            name = row["sample_id"].upper()
            if name in indexed or name not in {"STD" + str(i) for i in range(count)}:
                raise ValueError("檢量線含重複或無法對應的標準名稱，未自動選取。")
            indexed[name] = row
        if len(indexed) != count:
            raise ValueError("檢量線標準點不完整。")
        for i, mass in enumerate(expected):
            row = indexed["STD" + str(i)]
            instrument_mass = row["instrument_conc"]
            if instrument_mass is None or not math.isclose(instrument_mass, mass, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(row["sample_id"] + " 的儀器 Conc 與方法設定含量不一致。")
            state["calibration_rows"].append({
                "sequence_no": row["row_id"], "sample_id": row["sample_id"],
                "role": "STANDARD", "calibration_x": mass, "signal": row["absorbance"],
            })
        calibration = calculate_calibration(state["calibration_rows"])
        slope = _finite(calibration["slope"], "檢量線斜率", positive=True)
        intercept = _finite(calibration["intercept"], "截距")
        _finite(calibration["r"], "相關係數")
        # W430 boundary is inclusive; retain the existing calculator's defaults for other methods.
        calibration["passed"] = calibration["r"] >= 0.995
        state["calibration_result"] = calibration
        volume = _finite(method.get("SAMPLE_VOLUME_DEFAULT"), "水樣體積", positive=True)
        multiplier = _finite(method.get("QDL_MULTIPLIER"), "QDL 倍率", positive=True)
        if method.get("QDL_SOURCE") != "FIRST_NONZERO_CALIBRATION_X":
            raise ValueError("W430 QDL 來源須為第一個非零檢量線點。")
        minimum = min(x for x in expected if x > 0)
        qdl = minimum * multiplier / volume * 1000.0
        state["qdl_value"] = qdl
        if not calibration["passed"]:
            state["analysis_warnings"].append("檢量線 r 未達 0.995；下列為試算結果，不能視為完成正式驗證。")
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        state["analysis_error"] = str(exc)
        return state
    by_id = {row["row_id"]: row for row in raw}
    blanks = defaultdict(list)
    for row in raw:
        if row["role"] == "SAMPLE_BLANK":
            blanks[(row["measured_at"][:10], row["batch"], row["sample_id"])].append(row)
    mdl = _optional(control_data.get("DETECT_LIMITED"))
    if mdl is None:
        state["analysis_warnings"].append("年度 MDL 未設定，樣品 ND 判讀暫不執行。")
    batches = defaultdict(list)
    for raw_row in raw:
        if raw_row["role"] not in {"SAMPLE", "SAMPLE_BLANK", "BKA", "BKB", "QC", "ICV", "CCV", "DUP", "MS", "MSD"}:
            continue
        role = raw_row["role"]
        dilution = _finite(raw_row["dilution"], "稀釋倍數", positive=True)
        mass = (raw_row["absorbance"] - intercept) / slope
        row = {
            "edit_group": raw_row["measured_at"][:10] + "|" + str(raw_row["batch"]),
            "sequence_no": raw_row["row_id"], "sample_id": raw_row["sample_id"], "role": role,
            "signal": raw_row["absorbance"], "sample_volume": volume,
            "final_volume": volume, "dilution_factor": dilution,
            "measured_concentration": mass, "calculated_concentration": None,
            "sample_concentration": None, "qaqc_concentration": None,
            "spike_concentration": None, "is_excluded": False,
            "buffer": raw_row["buffer"], "blank_mass": None, "net_mass": None,
            "method_note": "", "interpretation": "", "remark": "",
            "parent_id": raw_row["parent_id"], "blank_id": raw_row["blank_id"],
            "qdl": qdl * dilution, "batch": raw_row["batch"],
        }
        issues = list(raw_row["issues"])
        if role in {"SAMPLE", "DUP", "MS", "MSD"}:
            if role != "SAMPLE" and not raw_row.get("parent_row_id"):
                issues.append("缺少原樣品關聯。")
            if raw_row["buffer"] == "B":
                original = by_id.get(raw_row.get("parent_row_id"), raw_row)
                matches = blanks.get((original["measured_at"][:10], original["batch"], raw_row["blank_id"]), [])
                if len(matches) != 1:
                    issues.append("未取得唯一樣品 B 空白。")
                else:
                    row["blank_mass"] = (matches[0]["absorbance"] - intercept) / slope
            elif raw_row["buffer"] == "A":
                row["blank_mass"] = 0.0
            else:
                issues.append("緩衝液尚未確認。")
        elif role == "BKB":
            # Confirmed Excel rule: remove the 1.5 mg reagent contribution.
            # This correction belongs to BKB alone, never to sample A/B rows.
            row["blank_mass"] = 1.5
            if dilution != 1.0:
                issues.append("BKB 查核使用未稀釋空白（D=1），請確認原始資料。")
        else:
            row["blank_mass"] = 0.0
        if not issues and row["blank_mass"] is not None:
            row["net_mass"] = mass - row["blank_mass"]
            concentration = row["net_mass"] / volume * 1000.0 * dilution
            row.update(calculated_concentration=concentration, sample_concentration=concentration,
                       qaqc_concentration=concentration)
            if role == "SAMPLE":
                if mdl is not None and concentration < mdl * dilution:
                    row["interpretation"] = "ND"
                elif concentration < row["qdl"]:
                    row["interpretation"] = "<QDL"
            elif role in {"BKA", "BKB"} and mdl is not None:
                blank_multiplier = _finite(method.get("BLANK_MDL_MULTIPLIER"), "空白 MDL 倍率", positive=True)
                row["interpretation"] = "<{}MDL".format(format(blank_multiplier, "g")) if concentration < mdl * blank_multiplier else "空白超出管制"
        if role in {"BKA", "BKB"} and mdl is None:
            row["interpretation"] = "無法判定（MDL 未設定）"
        if role in {"ICV", "CCV", "QC", "MS", "MSD"}:
            key = {"ICV": "ICV_SPIKE_CONC", "CCV": "CCV_SPIKE_CONC", "QC": "QC_SPIKE_CONC", "MS": "MS_SPIKE_CONC", "MSD": "MS_SPIKE_CONC"}[role]
            added_mass = _optional(method.get(key))
            if added_mass is not None and added_mass > 0:
                row["spike_concentration"] = added_mass / volume * 1000.0 * dilution
        if role in {"SAMPLE", "DUP", "MS", "MSD"}:
            row["method_note"] = "緩衝液 {}；空白 {}".format(row["buffer"] or "待確認", row["blank_id"] or ("不扣除" if row["buffer"] == "A" else "待確認"))
        if issues:
            row["method_note"] += "；" + "；".join(issues)
        state["sample_qaqc_rows"].append(row)
        batches[(raw_row["measured_at"][:10], raw_row["batch"])].append(row)
    for number, (key, rows) in enumerate(sorted(batches.items()), 1):
        quality_rows = [r for r in rows if r["role"] in {"DUP", "MS", "MSD"}]
        roles = [r["role"] for r in quality_rows]
        parents = {r["parent_id"] for r in quality_rows if r["parent_id"]}
        if len(roles) != len(set(roles)) or len(parents) > 1:
            state["analysis_warnings"].append("批次 {} 有多組或不同原樣品的重複／添加資料，暫不自動產生 QA/QC 判定。".format(key[1]))
            continue
        checks = [r for r in rows if r["role"] in {"ICV", "CCV"}]
        duplicate = next((r for r in rows if r["role"] == "DUP"), None)
        threshold = duplicate["qdl"] if duplicate else qdl
        batch = {"batch_no": number, "batch_category": form_data.get("category", ""), "rows": rows,
                 "start_check": checks[0] if checks else None, "end_check": checks[-1] if checks else None}
        results = build_qaqc_check_results([batch], control_data, 15.0, threshold)
        # Existing fallback assumes a numeric DUP. Missing/ambiguous input must not appear as a valid alternative.
        if duplicate and duplicate["qaqc_concentration"] is None and results:
            results[0]["precision"] = None
        state["qaqc_3a_results"].extend(results)
    return state
