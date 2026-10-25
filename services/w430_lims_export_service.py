"""Reuse the existing template/model/Excel writer; never commit export requests."""
import os
from exports.lims_excel_exporter import build_lims_excel
from exports.w430_lims_mapper import build_w430_lims_export_data
from services.w430_record_service import _validate
from services.w430_pdf_export_service import load_w430_record_snapshot


def build_w430_lims_excel(template_path, form, control, method, analysis, preview, user):
    _validate(analysis)
    if not os.path.isfile(template_path):
        raise ValueError("找不到 LIMS Excel 範本：resources/lims/lims匯入表格.xlsx。")
    data = build_w430_lims_export_data(form, control, method, analysis, preview,
                                      analyst=str(user.get("employee_name") or ""))
    return build_lims_excel(template_path=template_path, export_data=data,
                            analyst_id=str(user.get("employee_id") or ""),
                            analyst_name=str(user.get("employee_name") or ""),
                            analysis_method=str(control.get("EM_NO") or ""))


def export_w430_record_excel(db, record, template_path):
    state, form, control, method, report, analysis = load_w430_record_snapshot(db, record)
    user = {"employee_id":record.analyst_employee_id or "", "employee_name":record.analyst_name or ""}
    return build_w430_lims_excel(template_path, form, control, method, analysis, state.get("preview"), user)
