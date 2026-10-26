"""Adapt W427 mg P/L rows to the shared single-analyte QA/QC rules."""
from copy import deepcopy
import math
from analysis.qaqc_calculator import build_qaqc_check_results
from services.w427_sample_service import number


# Existing single UV convention; shown explicitly in the table (not ICP +/-10%).
CC_RELATIVE_ERROR_LIMIT = 15.0


def _limits(control, prefix, precision=False):
    keys = [prefix + "_UCL"] if precision else [prefix + "_LCL", prefix + "_UCL"]
    try:
        values = [number(control.get(k), k, False) for k in keys]
        if precision and values[0] < 0:
            return False
        if not precision and values[0] > values[1]:
            return False
        for suffix in ("LWL", "UWL"):
            raw = control.get(prefix + "_" + suffix)
            if str(raw or "").strip():
                warning = number(raw, prefix + "_" + suffix, False)
                if precision:
                    if not 0 <= warning <= values[0]:
                        return False
                elif not values[0] <= warning <= values[1]:
                    return False
        if not precision and all(str(control.get(prefix + "_" + k) or "").strip() for k in ("LWL", "UWL")):
            if float(control[prefix + "_LWL"]) > float(control[prefix + "_UWL"]):
                return False
        return True
    except (ValueError, TypeError):
        return False


def _unknown(reason):
    return {"source":"", "source_name":"無法判定", "sample_id_a":"", "sample_id_b":"",
            "value_a":None, "value_b":None, "rpd":None, "uwl":None, "ucl":None,
            "status":"無法判定", "reason":reason}


def build_w427_qaqc(preview, samples, calibration, method, control):
    output = {"qaqc_3a_results":[], "qaqc_warnings":[]}
    if samples.get("sample_error") or not calibration:
        return output
    try:
        factor = number(method.get("RESULT_CONVERSION_FACTOR"), "結果換算係數")
        qdl_p = number(samples["qdl_value"], "QDL") / factor
        slope = number(calibration["slope"], "斜率")
        intercept = number(calibration["intercept"], "截距", False)
        confirmed = str(control.get("CONFIRMED") or "").strip() == "1"
        rows = deepcopy(samples["sample_qaqc_rows"])
        for row in rows:
            # Keep this adapter's units homogeneous; do not change block 2 output.
            row["calculated_concentration"] = row["qaqc_concentration"]
            row["sample_concentration"] = row["qaqc_concentration"]
        for batch in preview["batches"]:
            group = batch["date"] + "|" + batch["number"]
            selected = [r for r in rows if r["edit_group"] == group]
            checks = [r for r in selected if r["role"] in {"ICV", "CCV", "QC"}]
            opening = batch.get("opening")
            if opening and opening["row_id"] not in {r["sequence_no"] for r in checks}:
                d = number(opening["dilution"], "開始查核稀釋倍數")
                volume_factor = (number(method["FINAL_VOLUME_DEFAULT"], "定量體積") /
                                 number(method["SAMPLE_VOLUME_DEFAULT"], "取樣體積")) if method["APPLY_VOLUME_FACTOR"] == "Y" else 1.0
                basis = volume_factor * number(method["SAMPLE_PREP_FACTOR"], "前處理倍率") * d
                value = (number(opening["absorbance"], "開始查核吸光度", False) - intercept) / slope * basis
                spike = number(method[opening["role"] + "_SPIKE_CONC"], "開始查核添加濃度") * basis
                if not math.isfinite(value) or not math.isfinite(spike):
                    raise ValueError("開始查核計算超出可用數值範圍。")
                checks.insert(0, {"sequence_no":opening["row_id"], "role":opening["role"],
                    "sample_id":opening["sample_id"], "qaqc_concentration":value,
                    "calculated_concentration":value, "spike_concentration":spike})
            parent_ids = []
            for r in selected:
                if r["role"] in {"DUP", "MS", "MSD"} and r.get("parent_row_id") not in parent_ids:
                    parent_ids.append(r.get("parent_row_id"))
            if not parent_ids:
                parent_ids = [None]
            for index, parent_id in enumerate(parent_ids):
                original = next((r for r in selected if r["role"] == "SAMPLE" and r["sequence_no"] == parent_id), None)
                children = [r for r in selected if r["role"] in {"DUP", "MS", "MSD"} and r.get("parent_row_id") == parent_id]
                duplicates = [r for r in children if r["role"] == "DUP"]
                valid_group = original is not None and all(sum(r["role"] == role for r in children) <= 1 for role in ("DUP", "MS", "MSD"))
                valid_rows = [original] + children if valid_group else []
                cc = [r for r in checks if r["role"] in {"ICV", "CCV"}]
                label = batch["number"]
                if len(parent_ids) > 1:
                    label += "／" + (original["sample_id"] if original else "未配對原樣")
                definition = {"batch_no":label, "batch_category":batch["category"],
                    "rows":checks + valid_rows, "start_check":cc[0] if cc else None,
                    "end_check":cc[-1] if len(cc) > 1 else None}
                threshold = qdl_p * (duplicates[0]["dilution_factor"] if duplicates else 1.0)
                result = build_qaqc_check_results([definition], control, CC_RELATIVE_ERROR_LIMIT, threshold)[0]
                result["batch_date"] = batch["date"]
                if not valid_group:
                    result["precision"] = _unknown("缺少同批次原樣或同一原樣有重複 QA/QC 角色，無法配對判定。")
                    output["qaqc_warnings"].append("Batch " + label + "：" + result["precision"]["reason"])
                elif not duplicates or duplicates[0]["qaqc_concentration"] is None:
                    result["precision"] = _unknown("缺少有效 DUP，無法進行重複分析判定。")
                if not result["spike_recovery"]:
                    output["qaqc_warnings"].append("Batch " + label + "：無完整 MS／MSD 添加回收率資料。")
                elif {r["role"] for r in result["spike_recovery"]} != {"MS", "MSD"}:
                    output["qaqc_warnings"].append("Batch " + label + "：MS／MSD 資料不完整，僅顯示可配對的結果。")
                for check in result["rows"]:
                    if not confirmed or (check["role"] == "QC" and not _limits(control, "QC")):
                        check["status"] = "待設定標準"
                if result["precision"] and (not confirmed or not _limits(control, "DC", True)):
                    result["precision"].update(status="待設定標準", reason="年度管制尚未確認或精密度管制值缺漏／無效。")
                for spike in result["spike_recovery"]:
                    if not confirmed or not _limits(control, "SPIKE"):
                        spike["status"] = "待設定標準"
                if index:
                    result["rows"] = []  # One shared CC/QC table per batch.
                output["qaqc_3a_results"].append(result)
            if len([r for r in checks if r["role"] in {"ICV", "CCV"}]) < 2:
                output["qaqc_warnings"].append("Batch " + batch["number"] + "：開始／結束查核不完整，請確認 ICV／CCV。")
        if not confirmed:
            output["qaqc_warnings"].append("年度管制尚未確認，QA/QC 數值僅供檢視，不宣告合格。")
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        output["qaqc_3a_results"] = []
        output["qaqc_warnings"].append("QA/QC 無法完成判定：" + str(exc))
    return output
