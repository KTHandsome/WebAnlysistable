"""Read-only W427 formal PDF export from immutable five-section snapshots."""
import json
from models import AnalysisWorkState
from services.w427_pdf_renderer import build_w427_pdf


def load_w427_record_snapshot(db, record):
    if str(record.method_code or "").strip().upper() != "W427":
        raise ValueError("指定紀錄不是 W427。")
    row = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == record.analysis_id).first()
    if row is None or str(row.method_code or "").upper() != "W427":
        raise ValueError("缺少 W427 正式分析快照。")
    values = []
    for field in ("state_json", "form_data_json", "control_data_json", "method_data_json", "report_data_json"):
        try:
            value = json.loads(getattr(row, field) or "{}")
        except (ValueError, TypeError):
            raise ValueError("正式快照格式異常，未匯出檔案。")
        if not isinstance(value, dict) or not value:
            raise ValueError("正式快照不完整：" + field)
        values.append(value)
    state, form, control, method, report = values
    if (state.get("w427_format") != 1 or state.get("formal_analysis_id") != record.analysis_id
            or str(form.get("method_code") or "").upper() != "W427"
            or str(method.get("METHOD_CODE") or "").upper() != "W427"
            or str(form.get("instrument_id") or "") != str(record.instrument_id or "")
            or str(control.get("EXAMNO") or "") != str(record.exam_no or "")
            or str(form.get("selected_exam_no") or "") != str(record.exam_no or "")
            or str(form.get("category") or "") != str(record.category or "")
            or str(form.get("analysis_start_date") or "") != record.analysis_start_date.isoformat()
            or str(form.get("analysis_end_date") or "") != record.analysis_end_date.isoformat()):
        raise ValueError("W427 正式快照與紀錄識別不一致。")
    if (method.get("CALIBRATION_UNIT") != "mg P/L"
            or not method.get("DISPLAY_CONC_UNIT")
            or str(report.get("REPORT_CODE") or "") != str(method.get("REPORT_CODE") or "")):
        raise ValueError("正式快照的單位或報表代碼不一致。")
    analysis = state.get("analysis_state")
    if (not isinstance(analysis, dict) or not analysis.get("calibration", {}).get("calibration_result")
            or not analysis.get("samples", {}).get("sample_qaqc_rows")
            or not analysis.get("qaqc", {}).get("qaqc_3a_results")):
        raise ValueError("正式分析快照缺少檢量線、樣品或 QA/QC。")
    if not isinstance(state.get("preview"), dict):
        raise ValueError("正式快照缺少原始樣品對應資料。")
    return state, form, control, method, report, analysis


def export_w427_record_pdf(db, record):
    state, form, control, method, report, analysis = load_w427_record_snapshot(db, record)
    return build_w427_pdf(report, method, control, form, analysis)
