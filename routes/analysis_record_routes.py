from flask import (
    Blueprint,
    render_template,
    send_file,
    current_app,
)

import json

from database import SessionLocal

from auth_session import (
    login_required,
    can_view_analysis_delete_history,
)

from models import (
    AnalysisDeleteHistory,
    AnalysisRecord,
    AnalysisSample,
    AnalysisQaqcResult,
    AnalysisCalibrationSummary,
    AnalysisCalibrationPoint,
    AnalysisWorkState,
    AnalysisReviewHistory,
)

from exports.w434_lims_mapper import (
    build_w434_lims_export_data,
)

from exports.lims_excel_exporter import (
    build_lims_excel,
)

from reports.w434_pdf import build_w434_pdf


analysis_record_bp = Blueprint(
    "analysis_record_bp",
    __name__,
)


@analysis_record_bp.route(
    "/analysis-delete-history",
    methods=["GET"],
)
@login_required
def analysis_delete_history():

    if not can_view_analysis_delete_history():
        return (
            "您沒有查看分析刪除紀錄的權限。",
            403,
        )

    db = SessionLocal()

    try:
        records = (
            db.query(AnalysisDeleteHistory)
            .order_by(
                AnalysisDeleteHistory.deleted_at.desc(),
                AnalysisDeleteHistory.id.desc(),
            )
            .all()
        )

        return render_template(
            "analysis_delete_history.html",
            records=records,
            active_page="analysis_records",
        )

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>",
    methods=["GET"],
)
@login_required
def analysis_record_detail(analysis_id):

    db = SessionLocal()

    try:
        record = (
            db.query(AnalysisRecord)
            .filter(
                AnalysisRecord.analysis_id == analysis_id
            )
            .first()
        )

        if record is None:
            return "查無此分析紀錄。", 404

        samples = (
            db.query(AnalysisSample)
            .filter(
                AnalysisSample.analysis_id == analysis_id
            )
            .order_by(
                AnalysisSample.display_order,
                AnalysisSample.id,
            )
            .all()
        )

        qaqc_results = (
            db.query(AnalysisQaqcResult)
            .filter(
                AnalysisQaqcResult.analysis_id == analysis_id
            )
            .order_by(
                AnalysisQaqcResult.display_order,
                AnalysisQaqcResult.id,
            )
            .all()
        )

        calibration_summary = (
            db.query(AnalysisCalibrationSummary)
            .filter(
                AnalysisCalibrationSummary.analysis_id == analysis_id
            )
            .first()
        )

        calibration_points = (
            db.query(AnalysisCalibrationPoint)
            .filter(
                AnalysisCalibrationPoint.analysis_id == analysis_id
            )
            .order_by(
                AnalysisCalibrationPoint.display_order,
                AnalysisCalibrationPoint.id,
            )
            .all()
        )

        review_history = (
            db.query(AnalysisReviewHistory)
            .filter(
                AnalysisReviewHistory.analysis_id == analysis_id
            )
            .order_by(
                AnalysisReviewHistory.created_at,
                AnalysisReviewHistory.id,
            )
            .all()
        )

        return render_template(
            "analysis_record_detail.html",
            record=record,
            calibration_summary=calibration_summary,
            calibration_points=calibration_points,
            samples=samples,
            qaqc_results=qaqc_results,
            review_history=review_history,
            active_page="analysis_records",
        )

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/export-pdf",
    methods=["GET"],
)
@login_required
def export_analysis_record_pdf(analysis_id):

    db = SessionLocal()

    try:
        record = (
            db.query(AnalysisRecord)
            .filter(
                AnalysisRecord.analysis_id == analysis_id
            )
            .first()
        )

        if record is None:
            return "查無此分析紀錄。", 404

        work_state = (
            db.query(AnalysisWorkState)
            .filter(
                AnalysisWorkState.analysis_id == analysis_id
            )
            .first()
        )

        if work_state is None:
            return (
                "此正式分析紀錄沒有可供匯出的 Snapshot。",
                400
            )

        try:
            analysis_state = json.loads(
                work_state.state_json or "{}"
            )

            form_data = json.loads(
                work_state.form_data_json or "{}"
            )

            control_data = json.loads(
                work_state.control_data_json or "{}"
            )

            method_data = json.loads(
                work_state.method_data_json or "{}"
            )

            report_data = json.loads(
                work_state.report_data_json or "{}"
            )

        except json.JSONDecodeError:
            return (
                "正式分析紀錄 Snapshot 格式異常，"
                "無法重新匯出 PDF。",
                500
            )

        if not analysis_state:
            return (
                "正式分析紀錄缺少分析結果 Snapshot。",
                400
            )

        if not form_data:
            return (
                "正式分析紀錄缺少基本資料 Snapshot。",
                400
            )

        if not control_data:
            return (
                "正式分析紀錄缺少年度管制 Snapshot。",
                400
            )

        if not method_data:
            return (
                "正式分析紀錄缺少方法設定 Snapshot。",
                400
            )

        if not report_data:
            return (
                "正式分析紀錄缺少報表設定 Snapshot。",
                400
            )

        pdf_buffer = build_w434_pdf(
            report_data,
            method_data,
            control_data,
            form_data,
            analysis_state
        )

        analyte_display = str(
            method_data.get("ANALYTE_DISPLAY", "") or ""
        ).strip()

        if not analyte_display:
            analyte_display = (
                record.exam_name or "Analysis"
            )

        method_code = str(
            record.method_code or "Analysis"
        ).strip()

        download_name = (
            method_code
            + "_"
            + analyte_display
            + "_Analysis_Record.pdf"
        )

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name
        )

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/export-lims",
    methods=["GET"],
)
@login_required
def export_analysis_record_lims(analysis_id):

    db = SessionLocal()

    try:
        record = (
            db.query(AnalysisRecord)
            .filter(
                AnalysisRecord.analysis_id == analysis_id
            )
            .first()
        )

        if record is None:
            return "查無此分析紀錄。", 404

        work_state = (
            db.query(AnalysisWorkState)
            .filter(
                AnalysisWorkState.analysis_id == analysis_id
            )
            .first()
        )

        if work_state is None:
            return (
                "此正式分析紀錄沒有可供匯出的 Snapshot。",
                400
            )

        try:
            analysis_state = json.loads(
                work_state.state_json or "{}"
            )

            form_data = json.loads(
                work_state.form_data_json or "{}"
            )

            control_data = json.loads(
                work_state.control_data_json or "{}"
            )

            method_data = json.loads(
                work_state.method_data_json or "{}"
            )

        except json.JSONDecodeError:
            return (
                "正式分析紀錄 Snapshot 格式異常，"
                "無法重新匯出 LIMS Excel。",
                500
            )

        if not analysis_state:
            return (
                "正式分析紀錄缺少分析結果 Snapshot。",
                400
            )

        if not form_data:
            return (
                "正式分析紀錄缺少基本資料 Snapshot。",
                400
            )

        if not control_data:
            return (
                "正式分析紀錄缺少年度管制 Snapshot。",
                400
            )

        if not method_data:
            return (
                "正式分析紀錄缺少方法設定 Snapshot。",
                400
            )

        export_data = build_w434_lims_export_data(
            form_data=form_data,
            control_data=control_data,
            method_data=method_data,
            analysis_state=analysis_state,
            analyst=record.analyst_name or "",
        )

        if not export_data.qc_rows:
            return (
                "此正式分析紀錄沒有可匯出的 "
                "LIMS 品管資料。",
                400
            )

        if not export_data.analysis_rows:
            return (
                "此正式分析紀錄沒有可匯出的 "
                "正式樣品資料。",
                400
            )

        template_path = os.path.join(
            current_app.root_path,
            "resources",
            "lims",
            "lims匯入表格.xlsx",
        )

        if not os.path.exists(template_path):
            return "找不到 LIMS Excel 範本。", 500

        analysis_method = str(
            control_data.get("EM_NO", "") or ""
        ).strip()

        analyst_id = str(
            record.analyst_employee_id or ""
        ).strip()

        analyst_name = str(
            record.analyst_name or ""
        ).strip()

        excel_buffer = build_lims_excel(
            template_path=template_path,
            export_data=export_data,
            analyst_id=analyst_id,
            analyst_name=analyst_name,
            analysis_method=analysis_method,
        )

        exam_no = str(
            control_data.get("EXAMNO", "") or ""
        ).strip()

        if not exam_no:
            exam_no = "LIMS"

        download_name = (
            exam_no + "_LIMS_Import.xlsx"
        )

        return send_file(
            excel_buffer,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name=download_name,
        )

    finally:
        db.close()