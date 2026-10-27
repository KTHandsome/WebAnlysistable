"""W430 formal submission. Caller owns commit/rollback; no session/global state."""
import json
import math
from copy import deepcopy
from models import AnalysisRecord, AnalysisWorkState, PerformanceMeasurementHistory, PerformanceAnalysisLink
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError
from services.analysis_record_service import save_analysis_record
from services.qaqc_export_service import validate_qaqc_export_ready
from services.w430_draft_service import load_w430_draft, save_w430_draft, _work_source_label
from services.w430_pfm_history_service import save_w430_pfm_history
from services.performance_history_service import _parse_pfm_datetime


def apply_w430_remarks(analysis, remarks):
    if not isinstance(remarks, dict):
        raise ValueError("批次備註格式不符。")
    batches = analysis.get("qaqc_3a_results", [])
    allowed = {str(b["batch_no"]) for b in batches}
    if set(remarks) - allowed:
        raise ValueError("批次資料已變更，請重新載入。")
    for batch in batches:
        value = remarks.get(str(batch["batch_no"]), "")
        if not isinstance(value, str) or len(value) > 200:
            raise ValueError("批次備註不可超過 200 字。")
        batch["batch_remark"] = value.strip()
    return analysis


def _validate(analysis):
    if analysis.get("analysis_error"):
        raise ValueError(analysis["analysis_error"])
    calibration = analysis.get("calibration_result") or {}
    r = calibration.get("r")
    if not isinstance(r, (int, float)) or not math.isfinite(r) or r < 0.995:
        raise ValueError("檢量線相關係數須達 r ≥ 0.995，尚未送審。")
    rows = analysis.get("sample_qaqc_rows") or []
    if not any(row.get("role") == "SAMPLE" for row in rows):
        raise ValueError("尚無可送審的一般樣品。")
    for row in rows:
        if row.get("role") == "SAMPLE_BLANK":
            signal = row.get("signal")
            if not isinstance(signal, (int, float)) or not math.isfinite(signal):
                raise ValueError(str(row.get("sample_id") or "樣品空白") + " 尚無有效吸光度。")
            continue
        value = row.get("sample_concentration")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(str(row.get("sample_id") or "樣品") + " 尚無有效濃度，請確認原樣品與 B 空白配對。")
    # Ambiguous duplicate groups are intentionally omitted by the calculator; never submit them silently.
    if any("暫不自動產生 QA/QC 判定" in str(w) for w in analysis.get("analysis_warnings", [])):
        raise ValueError("重複／添加樣品關聯尚未完成，請先確認 QA/QC。")
    ready, error = validate_qaqc_export_ready(analysis.get("qaqc_3a_results", []), True)
    if not ready:
        raise ValueError(str(error).replace("不可匯出", "不可儲存正式分析紀錄"))
    results = analysis.get("prm_results") or []
    if not results or any(r.get("status") not in {"PASS", "FAIL"} for r in results):
        raise ValueError("請先完成 UV 儀器性能查核判定。")


def _link_pfm(db, analysis_id, results):
    save_w430_pfm_history(db, results)
    for seq, item in enumerate(results, 1):
        c = item["control"]
        event = db.query(PerformanceMeasurementHistory).filter(
            PerformanceMeasurementHistory.instrument_id == c["instrument_id"],
            PerformanceMeasurementHistory.monitor_item == c["monitor_item"],
            PerformanceMeasurementHistory.performance_type == c["performance_type"],
            PerformanceMeasurementHistory.analysis_datetime == _parse_pfm_datetime(item["analysis_datetime"]),
        ).one()
        db.add(PerformanceAnalysisLink(performance_id=event.id, analysis_id=analysis_id, prm_sequence_no=seq))


def submit_w430_record(db, user, work_id, revision, original, preview, analysis, form, control, method, report):
    _validate(analysis)
    actor_id = str((user or {}).get("user_id") or "").strip()
    if not actor_id:
        raise PermissionError("尚未取得登入者。")
    saved = save_w430_draft(db, actor_id, work_id, revision, original, preview,
                            analysis, form, control, method, report)
    bundle = load_w430_draft(db, work_id, actor_id)
    # A temporary flat adapter feeds the established formal row/QAQC writer.
    # UV PFM has its own event identities, so the AA PFM synchronizer receives no rows.
    flat = deepcopy(analysis)
    for row in flat["sample_qaqc_rows"]:
        row["remark"] = "；".join(str(row.get(k) or "").strip() for k in
                                  ("interpretation", "method_note", "remark") if row.get(k))[:500]
    flat["qaqc_results"] = deepcopy(analysis["qaqc_3a_results"])
    flat["prm_rows"], flat["prm_results"] = [], []
    flat["uploaded_filename"] = _work_source_label(bundle["state"])[:255]
    flat["confirmed_wavelength"] = 420.0
    if bundle["formal_analysis_id"]:
        flat["formal_analysis_id"] = bundle["formal_analysis_id"]
    result = save_analysis_record(form, control, method, report, flat, user,
                                  db=db, strict_work_identity=True)
    analysis_id = result["analysis_id"]
    snapshot = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == analysis_id).one()
    # Restore the exact five-section W430 bundle, including immutable TXT and B blank pairing.
    state = deepcopy(bundle["state"])
    state["formal_analysis_id"] = analysis_id
    snapshot.state_json = json.dumps(state, ensure_ascii=False)
    db.query(PerformanceAnalysisLink).filter(PerformanceAnalysisLink.analysis_id == analysis_id).delete(synchronize_session=False)
    _link_pfm(db, analysis_id, analysis["prm_results"])
    db.flush()
    result["revision"] = AnalysisWorkDraftRepository(db).submit_draft(
        work_id, bundle["owner_user_id"], "W430", saved["revision"], analysis_id)
    result["work_id"] = work_id
    return result
