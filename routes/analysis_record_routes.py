import json

import os

from flask import (
    Blueprint,
    render_template,
    send_file,
    current_app,
    request,
    redirect, 
    url_for,
    session
)

from analysis.analysis_state import load_analysis_state

from analysis.analysis_state import save_analysis_state

from analysis.analysis_route_helpers import (
    get_analysis_state_key,
    get_analysis_session_key,
    get_analysis_page_endpoint,
)

from database import SessionLocal

from auth_session import (
    login_required,
    can_delete_analysis,
    can_view_analysis_delete_history,
    can_review_analysis,
    get_current_user,
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

from datetime import datetime

analysis_record_bp = Blueprint(
    "analysis_record_bp",
    __name__,
)

def can_resume_analysis_record(record):
    """
    原分析員或具審核權限者可恢復退回紀錄。
    """

    user = get_current_user()

    if not user:
        return False

    current_user_id = str(
        user.get("user_id") or ""
    ).strip()

    analyst_user_id = str(
        record.analyst_user_id or ""
    ).strip()

    if (
        current_user_id
        and analyst_user_id
        and current_user_id == analyst_user_id
    ):
        return True

    return can_review_analysis()

def has_resume_work_conflict(method_code, analysis_id):
    """
    檢查 Resume 是否可能覆蓋其他分析工作。

    True：存在衝突，禁止恢復。
    False：未偵測到衝突。
    """

    method_code = str(method_code or "").strip().upper()
    analysis_id = str(analysis_id or "").strip()

    # ========================================
    # 檢查目前 Session 是否已有其他分析工作
    # ========================================

    current_form = session.get("basic_info_form")

    if current_form:

        if not isinstance(current_form, dict):
            return True

        current_method = str(
            current_form.get("method_code") or ""
        ).strip().upper()

        current_formal_id = str(
            current_form.get("formal_analysis_id")
            or session.get(
             get_analysis_session_key(method_code)
            )
            or ""
        ).strip()

        # 目前基本資料屬於其他分析方法
        if current_method and current_method != method_code:
            return True

        # 目前基本資料明確屬於其他正式分析紀錄
        if current_formal_id and current_formal_id != analysis_id:
            return True

        # 無正式 ID 的基本資料可能是尚未完成的新工作。
        # 不直接覆寫。
        if not current_formal_id:
            return True

    # ICP 匯入工作使用另一套 SQLite 暫存機制。
    # 若目前 Session 指向 ICP 工作，先阻擋恢復。
    if session.get("icp_work_key"):
        return True

    state_key = get_analysis_state_key(method_code)
    session_key = get_analysis_session_key(method_code)

    current_id = str(
        session.get(session_key) or ""
    ).strip()

    # Session 已指向其他正式分析紀錄。
    if current_id and current_id != analysis_id:
        return True

    existing_state = load_analysis_state(state_key)

    if existing_state is not None:

        # 狀態資料異常時，不允許直接覆寫。
        if not isinstance(existing_state, dict):
            return True

        state_id = str(
            existing_state.get("formal_analysis_id") or ""
        ).strip()

        # 全域記憶體有工作，但無法確認屬於本次恢復紀錄。
        # 包含尚未正式儲存的新分析工作。
        if state_id != analysis_id:
            return True

    return False

@analysis_record_bp.route(
    "/analysis-records",
    methods=["GET"],
)
@login_required
def analysis_records():

    filter_names = [
        "ctrl_year",
        "category",
        "status",
        "exam_name",
        "method_code",
        "instrument_id",
        "analyst_name",
        "analysis_date_start",
        "analysis_date_end",
    ]

    search_data = {
        name: request.args.get(name, "").strip()
        for name in filter_names
    }

    db = SessionLocal()

    try:
        query = db.query(AnalysisRecord)

        # 精確比對
        for field in (
            "ctrl_year",
            "category",
            "status",
            "instrument_id",
        ):
            value = search_data[field]

            if value:
                query = query.filter(
                    getattr(AnalysisRecord, field) == value
                )

        # 部分文字比對
        for field in (
            "exam_name",
            "method_code",
            "analyst_name",
        ):
            value = search_data[field]

            if value:
                query = query.filter(
                    getattr(AnalysisRecord, field).contains(value)
                )

        # 分析日期：查詢期間與分析期間有交集即可
        start_date = search_data["analysis_date_start"]
        end_date = search_data["analysis_date_end"]

        if start_date and end_date:
            query = query.filter(
                AnalysisRecord.analysis_start_date <= end_date,
                AnalysisRecord.analysis_end_date >= start_date,
            )

        elif start_date:
            query = query.filter(
                AnalysisRecord.analysis_end_date >= start_date
            )

        elif end_date:
            query = query.filter(
                AnalysisRecord.analysis_start_date <= end_date
            )

        records = (
            query
            .order_by(
                AnalysisRecord.created_at.desc(),
                AnalysisRecord.id.desc(),
            )
            .all()
        )

        return render_template(
            "analysis_records.html",
            records=records,
            search_data=search_data,
            can_delete_analysis=can_delete_analysis(),
            can_view_delete_history=(
                can_view_analysis_delete_history()
            ),
            active_page="analysis_records",
        )

    finally:
        db.close()


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

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/approve",
    methods=["POST"],
)
@login_required
def approve_analysis_record(analysis_id):

    if not can_review_analysis():
        return "您沒有分析紀錄審核權限。", 403

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

        if record.status != "UNDER_REVIEW":
            return "只有待審核紀錄可以執行審核通過。", 400

        current_user = get_current_user() or {}
        previous_status = record.status

        record.status = "APPROVED"

        record.reviewer_user_id = str(
            current_user.get("user_id", "") or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get("employee_id", "") or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get("employee_name", "") or ""
        ).strip()

        record.reviewed_at = datetime.utcnow()

        record.review_comment = request.form.get(
            "review_comment", ""
        ).strip()

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,
            action="APPROVE",
            from_status=previous_status,
            to_status="APPROVED",
            reviewer_user_id=record.reviewer_user_id,
            reviewer_employee_id=record.reviewer_employee_id,
            reviewer_name=record.reviewer_name,
            comment=record.review_comment,
        )

        db.add(review_history)
        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id,
            )
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/reject",
    methods=["POST"],
)
@login_required
def reject_analysis_record(analysis_id):

    if not can_review_analysis():
        return "您沒有分析紀錄審核權限。", 403

    review_comment = request.form.get(
        "review_comment", ""
    ).strip()

    if not review_comment:
        return "退回修正時必須填寫退回原因。", 400

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

        if record.status != "UNDER_REVIEW":
            return "只有待審核紀錄可以退回修正。", 400

        current_user = get_current_user() or {}
        previous_status = record.status

        record.status = "REJECTED"

        record.reviewer_user_id = str(
            current_user.get("user_id", "") or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get("employee_id", "") or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get("employee_name", "") or ""
        ).strip()

        record.reviewed_at = datetime.utcnow()
        record.review_comment = review_comment

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,
            action="REJECT",
            from_status=previous_status,
            to_status="REJECTED",
            reviewer_user_id=record.reviewer_user_id,
            reviewer_employee_id=record.reviewer_employee_id,
            reviewer_name=record.reviewer_name,
            comment=record.review_comment,
        )

        db.add(review_history)
        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id,
            )
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/reopen",
    methods=["POST"],
)
@login_required
def reopen_approved_analysis_record(analysis_id):

    # 只有具有審核權限的人員可以再次退回
    if not can_review_analysis():
        return "您沒有分析紀錄審核權限。", 403

    review_comment = request.form.get(
        "review_comment", ""
    ).strip()

    if not review_comment:
        return "再次退回修正時必須填寫原因。", 400

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

        if record.status != "APPROVED":
            return (
                "只有已審核紀錄可以再次退回修正。",
                400
            )

        current_user = get_current_user() or {}
        previous_status = record.status

        record.status = "REJECTED"

        record.reviewer_user_id = str(
            current_user.get("user_id", "") or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get("employee_id", "") or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get("employee_name", "") or ""
        ).strip()

        record.reviewed_at = datetime.utcnow()
        record.review_comment = review_comment

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,
            action="REOPEN_AFTER_APPROVAL",
            from_status=previous_status,
            to_status="REJECTED",
            reviewer_user_id=record.reviewer_user_id,
            reviewer_employee_id=record.reviewer_employee_id,
            reviewer_name=record.reviewer_name,
            comment=record.review_comment,
        )

        db.add(review_history)
        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id,
            )
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/resume",
    methods=["POST"]
)
@login_required
def resume_analysis_record(analysis_id):

    db = SessionLocal()

    try:
        record = db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == analysis_id
        ).first()

        if record is None:
            return "查無此分析紀錄。", 404

        if record.status != "REJECTED":
            return "只有退回修正的分析紀錄可以重新進入修正。", 400

        # 原分析員或具審核權限者
        if not can_resume_analysis_record(record):
            return "沒有權限恢復此分析紀錄。", 403

        method_code = str(
            record.method_code or ""
        ).strip().upper()

        # 先檢查衝突，不覆寫現有工作
        if has_resume_work_conflict(method_code, analysis_id):
            return (
                "目前已有其他分析工作，"
                "請先完成或處理目前工作，再恢復退回紀錄。",
                409
            )

        try:
            analysis_endpoint = get_analysis_page_endpoint(
                method_code
            )
        except ValueError as ex:
            return str(ex), 400

        work_state = db.query(AnalysisWorkState).filter(
            AnalysisWorkState.analysis_id == analysis_id
        ).first()

        if work_state is None:
            return "此分析紀錄沒有可恢復的原分析工作資料。", 400

        try:
            analysis_state = json.loads(
                work_state.state_json or "{}"
            )

            form_data = json.loads(
                work_state.form_data_json or "{}"
            )

        except (json.JSONDecodeError, TypeError):
            return "原分析工作資料格式異常，無法恢復。", 500

        if not isinstance(analysis_state, dict) or not analysis_state:
            return "原分析工作資料內容為空白，無法恢復。", 400

        if not isinstance(form_data, dict) or not form_data:
            return "原分析基本資料內容為空白，無法恢復。", 400

    finally:
        db.close()

    # ========================================
    # 通過驗證後，才恢復原正式分析紀錄
    # ========================================

    analysis_state["formal_analysis_id"] = analysis_id
    form_data["method_code"] = method_code

    save_analysis_state(
        get_analysis_state_key(method_code),
        analysis_state
    )

    session["basic_info_form"] = form_data

    session[
        get_analysis_session_key(method_code)
    ] = analysis_id

    return redirect(
        url_for(analysis_endpoint, saved="1")
    )