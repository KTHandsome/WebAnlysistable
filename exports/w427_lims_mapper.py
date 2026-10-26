"""W427 adapter for the established single-analyte LIMS data model."""
from copy import deepcopy
import math
from exports.lims_export_model import LimsExportData
from exports.w434_lims_mapper import build_w434_lims_export_data, _build_batch_no, _build_lims_result


def _number(value, label, positive=False):
    if isinstance(value, bool):
        raise ValueError(label + "須為有效數值。")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(label + "未取得有效數值。")
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(label + "必須為有效" + ("正數。" if positive else "數值。"))
    return result


def _one(items, label):
    if len(items) != 1:
        raise ValueError(label + "需要一筆明確採用結果；目前 LIMS 每批品管僅能寫入一列，請先確認資料。")
    return items[0]


def build_w427_lims_export_data(form, control, method, analysis, preview, analyst=""):
    if form.get("method_code") != "W427" or method.get("METHOD_CODE") != "W427":
        raise ValueError("指定工作不是 W427。")
    exam = str(control.get("EXAMNO") or "").strip()
    if not exam or exam != str(form.get("selected_exam_no") or "").strip():
        raise ValueError("尚未取得一致的檢測代碼。")
    mdl = _number(control.get("DETECT_LIMITED"), "年度 MDL", True)
    multiplier = _number(method.get("BLANK_MDL_MULTIPLIER"), "空白 MDL 倍率", True)
    source = {r["row_id"]:r for r in (preview or {}).get("rows", [])}
    groups, quality = {}, {}
    for row in analysis.get("samples", {}).get("sample_qaqc_rows", []):
        if not row.get("is_excluded"):
            groups.setdefault(str(row.get("edit_group") or ""), []).append(row)
    for batch in analysis.get("qaqc", {}).get("qaqc_3a_results", []):
        key = str(batch.get("batch_date") or "") + "|" + str(batch["batch_no"]).split("／",1)[0]
        quality.setdefault(key, []).append(batch)
    if not groups or set(groups) != set(quality):
        raise ValueError("樣品與 QA/QC 批次不一致。")
    try:
        keys = sorted(groups, key=lambda key:(key.rsplit("|",1)[0], int(key.rsplit("|",1)[1])))
    except (ValueError, IndexError):
        raise ValueError("樣品批次識別不完整。")
    settings = deepcopy(method)
    # Final concentrations already include volume/preparation/D/species conversion.
    settings["QAQC_CONC_FACTOR"] = "1"
    result = LimsExportData()
    used, used_batches = set(), set()
    for key in keys:
        date, number = key.rsplit("|",1)
        batch = deepcopy(_one(quality[key], "Batch " + number + " 的原樣 QA/QC 組"))
        _one([r for r in batch["rows"] if r.get("role") == "QC"], "QC")
        _one([r for r in batch.get("spike_recovery", []) if r.get("role") == "MS"], "MS")
        if not batch.get("precision"):
            raise ValueError("缺少重複分析精密度。")
        closing = _one([r for r in groups[key] if r.get("role") == "CCV"], "結束 CCV")
        last = _one([r for r in batch["rows"] if r.get("role") == "CCV" and r.get("sample_id") == closing["sample_id"]], "結束 CCV 判定")
        # The common mapper selects the first CCV: give it the explicit closing CCV,
        # so G Batch2 does not export its opening CCV1 in place of closing CCV2.
        batch["rows"] = [r for r in batch["rows"] if r.get("role") != "CCV"] + [last]
        batch["batch_no"] = number
        rows = deepcopy(groups[key])
        state = {"calibration_result":analysis["calibration"]["calibration_result"],
            "sample_qaqc_rows":rows, "qaqc_results":[batch],
            "included_batches":[{"batch_no":number, "rows":rows}],
            "qdl_value":analysis["samples"]["qdl_value"]}
        data = build_w434_lims_export_data(form, control, settings, state, analyst=analyst)
        if len(data.qc_rows) != 1:
            raise ValueError("品管匯出資料不完整。")
        expected_batch = _build_batch_no(str(form.get("analysis_start_date") or ""), exam, number)
        if expected_batch in used_batches:
            raise ValueError("多個日期使用相同批號，會產生重複 LIMS 批次流水號；請分開工作後匯出。")
        used_batches.add(expected_batch)
        blanks = [r for r in rows if r.get("role") == "BK"]
        if not blanks:
            raise ValueError("Batch " + number + " 缺少 BK 空白試驗。")
        rendered = []
        for row in blanks:
            value = _number(row.get("sample_concentration"), "BK 濃度")
            limit = mdl * _number(row.get("dilution_factor"), "BK 稀釋倍數", True)
            text = "<"+format(multiplier,".10g")+"MDL" if value < limit*multiplier else format(value,".6f")
            rendered.append((value/limit, text))
        qc = data.qc_rows[0]
        qc.blank_result = max(rendered,key=lambda item:item[0])[1]
        qc.remark = str(batch.get("batch_remark") or "")
        if qc.batch_no != expected_batch:
            raise ValueError("LIMS 批次流水號不一致。")
        for value,label in [(qc.max_signal,"最高標準點吸光度"),(qc.duplicate_result,"RPD"),
                            (qc.qc_result,"QC 回收率"),(qc.spike_result,"MS 回收率"),
                            (qc.calibration_check,"結束 CCV 相對誤差"),(qc.correlation_coefficient,"r")]:
            _number(value,label)
        ordinary = [r for r in rows if r.get("role") == "SAMPLE"]
        if len(ordinary) != len(data.analysis_rows):
            raise ValueError("一般樣品匯出列數不一致。")
        for target,row in zip(data.analysis_rows,ordinary):
            raw = source.get(row.get("sequence_no")) or {}
            base_id = str(raw.get("base_id") or "").strip()
            if raw.get("role") != "SAMPLE" or not base_id or not base_id.startswith(str(form.get("category") or "")):
                raise ValueError("一般樣品缺少所選類別的原始 LIMS 樣品編號。")
            if (base_id,exam) in used:
                raise ValueError("樣品 " + base_id + " 有多筆採用結果，請先確認後再匯出。")
            used.add((base_id,exam))
            d = _number(row.get("dilution_factor"), "稀釋倍數", True)
            value = _number(row.get("sample_concentration"), "最終樣品濃度")
            qdl = _number(row.get("qdl"), "該列 QDL", True)
            target.sample_id = base_id
            target.result, target.remark = _build_lims_result(value,mdl*d,qdl)
        result.qc_rows.extend(data.qc_rows)
        result.analysis_rows.extend(data.analysis_rows)
    if not result.analysis_rows:
        raise ValueError("尚無可匯出的完整一般樣品。")
    return result
