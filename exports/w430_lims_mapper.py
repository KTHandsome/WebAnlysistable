"""W430 adapter for the shared single-analyte LIMS model and result conventions."""
import math
from copy import deepcopy
from exports.w434_lims_mapper import build_w434_lims_export_data, _build_lims_result


def _number(value, label, positive=False):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(label + "未取得有效數值。")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label + "必須為有效" + ("正數。" if positive else "數值。"))
    return value


def build_w430_lims_export_data(form, control, method, analysis, preview, analyst=""):
    if str(form.get("method_code") or "").upper() != "W430":
        raise ValueError("指定工作不是 W430。")
    exam = str(control.get("EXAMNO") or "").strip()
    if not exam:
        raise ValueError("尚未取得檢測代碼。")
    groups = {}
    for row in analysis.get("sample_qaqc_rows", []):
        if not row.get("is_excluded"):
            groups.setdefault(str(row.get("edit_group") or ""), []).append(row)
    try:
        keys = sorted(groups, key=lambda k: (k.rsplit("|",1)[0], int(k.rsplit("|",1)[1])))
    except (ValueError, IndexError):
        raise ValueError("分析批次識別不完整。")
    qc = {str(b["batch_no"]): b for b in analysis.get("qaqc_3a_results", [])}
    if not keys or len(keys) != len(qc):
        raise ValueError("樣品與 QA/QC 批次不一致。")
    state = deepcopy(analysis)
    state["qaqc_results"] = deepcopy(analysis["qaqc_3a_results"])
    state["included_batches"] = [{"batch_no":i,"rows":deepcopy(groups[k])} for i,k in enumerate(keys,1)]
    settings = deepcopy(method)
    # W430's calculator has already converted mg mass to mg/L, including D and B blank subtraction.
    settings["QAQC_CONC_FACTOR"] = "1"
    export = build_w434_lims_export_data(form, control, settings, state, analyst=analyst)
    mdl = _number(control.get("DETECT_LIMITED"), "MDL", True)
    multiplier = _number(method.get("BLANK_MDL_MULTIPLIER"), "空白 MDL 倍率", True)
    source = {r["row_id"]:r for r in (preview or {}).get("rows", [])}
    normal = []
    used = set()
    for i,key in enumerate(keys,1):
        blanks = [r for r in groups[key] if r.get("role") in {"BKA","BKB"}]
        if not blanks:
            raise ValueError("Batch {} 缺少 BKA／BKB 空白試驗。".format(i))
        worst = max(_number(r.get("sample_concentration"), "空白濃度") for r in blanks)
        export.qc_rows[i-1].blank_result = "<" + format(multiplier,".10g") + "MDL" if worst < mdl*multiplier else format(worst,".6f")
        export.qc_rows[i-1].remark = str(qc[str(i)].get("batch_remark") or "")
        for row in groups[key]:
            if row.get("role") != "SAMPLE":
                continue
            raw = source.get(row.get("sequence_no")) or {}
            base_id = str(raw.get("base_id") or "").strip()
            if raw.get("role") != "SAMPLE" or not base_id:
                raise ValueError("一般樣品缺少原始 LIMS 樣品編號關聯。")
            if (base_id,exam) in used:
                raise ValueError("樣品 {} 有多筆採用結果，請先確認後再匯出。".format(base_id))
            used.add((base_id,exam))
            normal.append((base_id,row))
    if len(normal) != len(export.analysis_rows) or not normal or not export.qc_rows:
        raise ValueError("缺少完整的一般樣品或品管資料。")
    for target,(base_id,row) in zip(export.analysis_rows,normal):
        dilution = _number(row.get("dilution_factor"), "稀釋倍數", True)
        value = _number(row.get("sample_concentration"), "樣品濃度")
        qdl = _number(row.get("qdl"), "該列 QDL", True)
        target.sample_id = base_id
        target.result, target.remark = _build_lims_result(value, mdl*dilution, qdl)
    return export
