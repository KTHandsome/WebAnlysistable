"""W427 sample adapter. OLS remains mg P/L; report species conversion is last."""
from copy import deepcopy
import math


def number(value, label, positive=True):
    if type(value) is bool:
        raise ValueError(label + "須為有效數值。")
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(label + "須為有效數值。")
    if not math.isfinite(n) or (positive and n <= 0):
        raise ValueError(label + "須為有限" + ("正數。" if positive else "數值。"))
    return n


def optional_mdl(value):
    if str(value or "").strip() == "":
        return None
    return number(value, "MDL")


def interpretation(role, concentration, mdl, qdl, multiplier):
    # Same thresholds/text as AnalysisInterpretation; blank excess is explicit.
    if mdl is None:
        return ""
    if role == "BK":
        return "<{}MDL".format(format(multiplier, ".10g")) if concentration < mdl * multiplier else "空白超出管制"
    if role in {"SAMPLE", "DUP"}:
        if concentration < mdl:
            return "ND<" + format(mdl, ".10g")
        if concentration < qdl:
            return "<QDL=" + format(qdl, ".10g")
    return ""


def build_w427_samples(preview, calibration, method_data, control):
    method = deepcopy(method_data)
    if not str(method.get("UI_CONCENTRATION_DECIMALS") or "").strip():
        method["UI_CONCENTRATION_DECIMALS"] = "4"
    state = {"method_data": method, "sample_qaqc_rows": [], "sample_warnings": [],
             "sample_error": "", "qdl_value": None, "mdl": None, "sample_config": {}}
    try:
        if not calibration:
            raise ValueError("請先取得有效檢量線，才能計算樣品。")
        slope = number(calibration["slope"], "斜率")
        intercept = number(calibration["intercept"], "截距", False)
        factor = number(method.get("RESULT_CONVERSION_FACTOR"), "結果換算係數")
        volume = number(method.get("SAMPLE_VOLUME_DEFAULT"), "取樣體積")
        final = number(method.get("FINAL_VOLUME_DEFAULT"), "定量體積")
        prep = number(method.get("SAMPLE_PREP_FACTOR"), "前處理倍率")
        apply_volume = str(method.get("APPLY_VOLUME_FACTOR") or "").upper()
        if apply_volume not in {"Y", "N"}:
            raise ValueError("APPLY_VOLUME_FACTOR 必須為 Y 或 N。")
        volume_factor = final / volume if apply_volume == "Y" else 1.0
        if method.get("QDL_SOURCE") != "FIRST_NONZERO_CALIBRATION_X":
            raise ValueError("W427 QDL 來源須為第一非零檢量線濃度。")
        positive_x = [point["x"] for point in calibration["points"] if point["x"] > 0]
        if not positive_x:
            raise ValueError("缺少非零檢量線點。")
        qdl_p = min(positive_x) * number(method.get("QDL_MULTIPLIER"), "QDL 倍率") * volume_factor * prep
        qdl = number(qdl_p * factor, "QDL 計算結果")
        mdl = optional_mdl(control.get("DETECT_LIMITED"))
        blank_multiplier = number(method.get("BLANK_MDL_MULTIPLIER"), "空白 MDL 倍率")
        digits = int(method["UI_CONCENTRATION_DECIMALS"])
        if not 0 <= digits <= 10:
            raise ValueError("樣品顯示小數位數須為 0～10。")
        state.update(qdl_value=qdl, mdl=mdl)
        state["sample_config"] = {"factor":factor, "mdl":mdl, "blankMultiplier":blank_multiplier,
                                  "decimals":digits, "parents":{}, "bases":{}}
        if mdl is None:
            state["sample_warnings"].append("年度 MDL 未設定，暫不執行 ND／MDL 判讀；空白不視為零。")
        pending = []
        for batch in preview["batches"]:
            group = batch["date"] + "|" + batch["number"]
            samples = {x["row_id"]:x for x in batch["rows"] if x["role"] == "SAMPLE"}
            for raw in batch["rows"]:
                role = raw["role"]
                if role not in {"SAMPLE", "DUP", "MS", "MSD", "BK", "QC", "ICV", "CCV"}:
                    continue
                d = number(raw["dilution"], "稀釋倍數")
                measured = (number(raw["absorbance"], "吸光度", False) - intercept) / slope
                p_base = measured * volume_factor * prep
                concentration_p = p_base * d
                concentration = concentration_p * factor
                if not all(math.isfinite(v) for v in (measured, p_base, concentration_p, concentration, qdl*d)):
                    raise ValueError(raw["sample_id"] + " 計算超過可用數值範圍。")
                row = {"sequence_no":raw["row_id"], "sample_id":raw["sample_id"], "role":role,
                       "sample_volume":volume, "final_volume":final, "signal":raw["absorbance"],
                       "dilution_factor":d, "measured_concentration":measured,
                       "calculated_concentration":concentration, "sample_concentration":concentration,
                       "qaqc_concentration":concentration_p, "spike_concentration":None,
                       "is_excluded":False, "method_note":"", "interpretation":"", "edit_group":group,
                       "batch_label":"Batch {}／{}／{}".format(batch["number"], batch["category"], batch["date"]),
                       "parent_id":raw.get("parent_id", ""), "parent_row_id":raw.get("parent_row_id"),
                       "qdl":qdl*d, "base_concentration":p_base*factor}
                if role in {"DUP", "MS", "MSD"}:
                    state["sample_config"]["parents"][str(raw["row_id"])] = raw.get("parent_row_id")
                    if raw.get("parent_row_id") not in samples:
                        row.update(calculated_concentration=None, sample_concentration=None, qaqc_concentration=None)
                        state["sample_warnings"].append(raw["sample_id"] + " 缺少同批次原樣品，暫不帶入最終濃度。")
                key = {"ICV":"ICV_SPIKE_CONC", "CCV":"CCV_SPIKE_CONC", "QC":"QC_SPIKE_CONC",
                       "MS":"MS_SPIKE_CONC", "MSD":"MS_SPIKE_CONC"}.get(role)
                if key:
                    # Base additions are mg P/L; D adjusts to the sample basis, factor 3.07 does not.
                    row["spike_concentration"] = number(method.get(key), "理論添加濃度") * volume_factor * prep * d
                    if not math.isfinite(row["spike_concentration"]):
                        raise ValueError("添加濃度超過可用數值範圍。")
                if row["calculated_concentration"] is not None:
                    row["interpretation"] = interpretation(role, concentration, mdl*d if mdl is not None else None,
                                                           row["qdl"], blank_multiplier)
                state["sample_config"]["bases"][str(raw["row_id"])] = {
                    "concentration":row["calculated_concentration"]/d if row["calculated_concentration"] is not None else None,
                    "qdl":qdl, "spike":row["spike_concentration"]/d if row["spike_concentration"] is not None else None}
                pending.append(row)
        state["sample_qaqc_rows"] = pending
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        state["sample_error"] = str(exc)
    return state
