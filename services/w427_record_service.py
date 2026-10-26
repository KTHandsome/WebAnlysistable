"""W427 formal writer. The caller owns the single transaction."""
import json
import math
from copy import deepcopy
from models import AnalysisWorkState, PerformanceMeasurementHistory, PerformanceAnalysisLink
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository
from services.analysis_record_service import save_analysis_record
from services.qaqc_export_service import validate_qaqc_export_ready
from services.w427_draft_service import load_w427_draft, save_w427_draft, _source_label
from services.w427_pfm_history_service import save_w427_pfm_history
from services.performance_history_service import _parse_pfm_datetime


def apply_w427_remarks(analysis, remarks):
    if not isinstance(remarks, dict):
        raise ValueError("批次備註格式無效。")
    batches = analysis.get("qaqc", {}).get("qaqc_3a_results", [])
    allowed = set()
    for batch in batches:
        key = str(batch.get("batch_date") or "") + "|" + str(batch["batch_no"])
        if key in allowed:
            raise ValueError("批次識別重複，請確認資料。")
        allowed.add(key)
        batch["remark_key"] = key
    if set(remarks) - allowed:
        raise ValueError("批次資料已變更，請重新載入。")
    for batch in batches:
        value = remarks.get(batch["remark_key"], "")
        if not isinstance(value, str) or len(value) > 200:
            raise ValueError("批次備註不可超過 200 字。")
        batch["batch_remark"] = value.strip()
    return analysis


def w427_remarks(analysis):
    return {b["remark_key"]:b.get("batch_remark", "")
            for b in analysis.get("qaqc", {}).get("qaqc_3a_results", []) if "remark_key" in b}


def _validate(analysis):
    cal = analysis.get("calibration", {})
    samples = analysis.get("samples", {})
    if cal.get("calibration_error") or samples.get("sample_error"):
        raise ValueError(cal.get("calibration_error") or samples["sample_error"])
    value = (cal.get("calibration_result") or {}).get("r")
    if type(value) not in (float, int) or not math.isfinite(value) or value <= .995:
        raise ValueError("檢量線須符合 r > 0.995，尚未送審。")
    rows = samples.get("sample_qaqc_rows", [])
    if not any(r.get("role") == "SAMPLE" for r in rows):
        raise ValueError("尚無可送審的一般樣品。")
    for row in rows:
        for field in ("sample_concentration", "qaqc_concentration", "measured_concentration"):
            value = row.get(field)
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError(str(row.get("sample_id") or "樣品") + " 尚無有效濃度，請確認原樣配對。")
    warnings = analysis.get("qaqc", {}).get("qaqc_warnings", [])
    if any("角色" in w or "缺少同批次原樣" in w or "開始／結束查核不完整" in w for w in warnings):
        raise ValueError("QA/QC 原樣配對或前後查核尚未完整，請確認後再儲存。")
    ready, error = validate_qaqc_export_ready(analysis.get("qaqc", {}).get("qaqc_3a_results", []), True)
    if not ready:
        raise ValueError(str(error).replace("不可匯出", "不可儲存正式分析紀錄"))
    results = analysis.get("prm_results") or []
    if len(results) != 2 or any(r.get("status") not in {"PASS", "FAIL"} for r in results):
        raise ValueError("請先完成兩項 UV 儀器性能查核判定。")


def _link_pfm(db, analysis_id, results):
    save_w427_pfm_history(db, results)
    for seq, item in enumerate(results, 1):
        control = item["control"]
        event = db.query(PerformanceMeasurementHistory).filter(
            PerformanceMeasurementHistory.instrument_id == control["instrument_id"],
            PerformanceMeasurementHistory.monitor_item == control["monitor_item"],
            PerformanceMeasurementHistory.performance_type == control["performance_type"],
            PerformanceMeasurementHistory.analysis_datetime == _parse_pfm_datetime(item["analysis_datetime"]),
        ).one()
        db.add(PerformanceAnalysisLink(performance_id=event.id, analysis_id=analysis_id, prm_sequence_no=seq))


def submit_w427_record(db, user, work_id, revision, original, preview, analysis, form, control, method, report):
    _validate(analysis)
    actor = str((user or {}).get("user_id") or "").strip()
    if not actor:
        raise PermissionError("尚未取得登入者。")
    saved = save_w427_draft(db, actor, work_id, revision, original, preview, analysis,
                            form, control, method, report)
    bundle = load_w427_draft(db, work_id, actor)
    flat = {"calibration_result":deepcopy(analysis["calibration"]["calibration_result"]),
            "calibration_rows":deepcopy(analysis["calibration"]["calibration_rows"]),
            "sample_qaqc_rows":deepcopy(analysis["samples"]["sample_qaqc_rows"]),
            "qaqc_results":deepcopy(analysis["qaqc"]["qaqc_3a_results"]),
            "prm_rows":[], "prm_results":[], "confirmed_wavelength":880.0,
            "uploaded_filename":_source_label(bundle["state"])[:255]}
    for row in flat["sample_qaqc_rows"]:
        row["remark"] = str(row.get("interpretation") or "")[:500]
    if bundle["formal_analysis_id"]:
        flat["formal_analysis_id"] = bundle["formal_analysis_id"]
    result = save_analysis_record(form, control, method, report, flat, user, db=db, strict_work_identity=True)
    analysis_id = result["analysis_id"]
    snapshot = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == analysis_id).one()
    state = deepcopy(bundle["state"])
    state["formal_analysis_id"] = analysis_id
    snapshot.state_json = json.dumps(state, ensure_ascii=False)
    db.query(PerformanceAnalysisLink).filter(PerformanceAnalysisLink.analysis_id == analysis_id).delete(synchronize_session=False)
    _link_pfm(db, analysis_id, analysis["prm_results"])
    db.flush()
    result["revision"] = AnalysisWorkDraftRepository(db).submit_draft(
        work_id, bundle["owner_user_id"], "W427", saved["revision"], analysis_id)
    result["work_id"] = work_id
    return result
