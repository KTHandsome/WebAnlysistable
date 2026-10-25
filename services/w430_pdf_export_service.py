"""Read only formal W430 snapshots. Never load current CSV or recalculate results."""
import json
from models import AnalysisWorkState
from services.w430_pdf_renderer import build_w430_pdf


def load_w430_record_snapshot(db, record):
    if str(record.method_code or "").strip().upper() != "W430":
        raise ValueError("指定紀錄不是 W430。")
    row = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == record.analysis_id).first()
    if row is None or str(row.method_code or "").upper() != "W430":
        raise ValueError("缺少 W430 正式分析快照。")
    values = []
    for field in ("state_json", "form_data_json", "control_data_json", "method_data_json", "report_data_json"):
        try:
            value = json.loads(getattr(row, field) or "{}")
        except (TypeError, ValueError):
            raise ValueError("正式分析快照格式異常，未完成匯出。")
        if not isinstance(value, dict) or not value:
            raise ValueError("正式分析快照不完整：" + field)
        values.append(value)
    state, form, control, method, report = values
    if (state.get("w430_format") != 1 or state.get("formal_analysis_id") != record.analysis_id
            or str(form.get("method_code") or "").upper() != "W430"
            or str(method.get("METHOD_CODE") or "").upper() != "W430"
            or str(form.get("instrument_id") or "") != str(record.instrument_id or "")):
        raise ValueError("W430 快照與正式紀錄不一致。")
    if (str(method.get("CALIBRATION_UNIT") or "").strip().lower() != "mg"
            or str(report.get("REPORT_CODE") or "") != str(method.get("REPORT_CODE") or "")):
        raise ValueError("正式快照的含量單位或報表代碼不一致。")
    analysis = state.get("analysis_state")
    if (not isinstance(analysis, dict) or not analysis.get("calibration_result")
            or not analysis.get("sample_qaqc_rows") or not analysis.get("qaqc_3a_results")):
        raise ValueError("正式分析快照缺少檢量線、樣品或 QA/QC。")
    return state, form, control, method, report, analysis


def export_w430_record_pdf(db, record):
    state, form, control, method, report, analysis = load_w430_record_snapshot(db, record)
    return build_w430_pdf(report, method, control, form, analysis)
