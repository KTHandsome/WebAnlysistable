"""W427 LIMS Excel via the unchanged shared template writer; no commits."""
import os
from exports.lims_excel_exporter import build_lims_excel
from exports.w427_lims_mapper import build_w427_lims_export_data
from services.w427_record_service import _validate
from services.w427_pdf_export_service import load_w427_record_snapshot


def build_w427_lims_excel(template_path, form, control, method, analysis, preview, user):
    _validate(analysis)
    if not os.path.isfile(template_path):
        raise ValueError("找不到 LIMS Excel 範本：resources/lims/lims匯入表格.xlsx。")
    user = dict(user or {})
    data = build_w427_lims_export_data(form, control, method, analysis, preview,
        analyst=str(user.get("employee_name") or ""))
    return build_lims_excel(template_path=template_path, export_data=data,
        analyst_id=str(user.get("employee_id") or ""), analyst_name=str(user.get("employee_name") or ""),
        analysis_method=str(control.get("EM_NO") or ""))


def export_w427_record_excel(db, record, template_path):
    state, form, control, method, report, analysis = load_w427_record_snapshot(db, record)
    user = {"employee_id":record.analyst_employee_id or "", "employee_name":record.analyst_name or ""}
    return build_w427_lims_excel(template_path,form,control,method,analysis,state["preview"],user)
