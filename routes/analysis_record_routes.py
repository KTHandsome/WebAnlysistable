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

from analysis.analysis_state import (
     load_analysis_state,
     save_analysis_state
)

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


from services.performance_history_service import (
    delete_performance_links_for_analysis,
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

def get_resume_work_conflict_reason(method_code, analysis_id):
    """Explain the existing conservative check without changing its decisions."""
    method_code = str(method_code or "").strip().upper()
    analysis_id = str(analysis_id or "").strip()

    # ICP's separate work lifecycle has not yet been integrated here.
    if session.get("icp_work_key"):
        return '目前 session 仍保留 ICP 工作編號，舊版檢查因此攔阻；尚未確認該 ICP 工作是否已正式儲存。'

    current_form = session.get("basic_info_form")
    if current_form is not None and not isinstance(current_form, dict):
        return '目前基本資料格式異常，無法確認工作是否已儲存。'
    current_form = current_form or {}
    current_method = str(current_form.get("method_code") or "").strip().upper()
    if current_form and not current_method:
        return '目前基本資料缺少分析方法，無法確認工作身分。'

    user = get_current_user() or {}
    user_id = str(user.get("user_id") or "").strip()
    if not user_id:
        return '尚未取得登入者帳號，無法確認目前工作。'

    db = SessionLocal()
    try:
        methods = {method_code}
        if current_method:
            methods.add(current_method)

        for candidate_method in methods:
            state = load_analysis_state(get_analysis_state_key(candidate_method))
            if state is not None and not isinstance(state, dict):
                return '目前分析暫存格式異常，無法比對正式紀錄。'
            form = current_form if candidate_method == current_method else None

            # No state and no active form will be overwritten for this method.
            if not state and not form:
                continue

            state_id = str((state or {}).get("formal_analysis_id") or "").strip()
            session_id = str(
                session.get(get_analysis_session_key(candidate_method)) or ""
            ).strip()
            form_id = str((form or {}).get("formal_analysis_id") or "").strip()
            identifiers = {value for value in (state_id, session_id, form_id) if value}
            if len(identifiers) != 1:
                return '目前分析狀態、session 或基本資料的正式紀錄編號缺漏或不一致。'
            formal_id = next(iter(identifiers))

            record = db.query(AnalysisRecord).filter(
                AnalysisRecord.analysis_id == formal_id
            ).first()
            snapshot = db.query(AnalysisWorkState).filter(
                AnalysisWorkState.analysis_id == formal_id
            ).first()
            if record is None or snapshot is None:
                return '目前工作所關聯的正式紀錄或分析快照不存在。'
            if str(record.analyst_user_id or "").strip() != user_id:
                return '目前工作屬於其他分析員，現有衝突檢查尚未允許切換。'
            if str(record.method_code or "").strip().upper() != candidate_method:
                return '目前工作與正式紀錄的分析方法不一致。'
            if str(snapshot.method_code or "").strip().upper() != candidate_method:
                return '目前工作與分析快照的分析方法不一致。'

            try:
                saved_state = json.loads(snapshot.state_json)
                saved_form = json.loads(snapshot.form_data_json)
            except (TypeError, ValueError):
                return '目前已儲存快照的 JSON 格式無法讀取。'
            if not isinstance(saved_state, dict) or not isinstance(saved_form, dict):
                return '目前已儲存快照內容格式異常。'
            if str(saved_state.get("formal_analysis_id") or "").strip() != formal_id:
                return '目前已儲存快照的正式紀錄關聯不一致。'

            if state:
                # Only this system-managed field may differ in representation.
                live_content = dict(state)
                saved_content = dict(saved_state)
                live_content.pop("formal_analysis_id", None)
                saved_content.pop("formal_analysis_id", None)
                if live_content != saved_content:
                    return '目前分析數據與已儲存快照不同，請先保留尚未儲存的修改。'

            if form is not None and form != saved_form:
                return '目前基本資料與已儲存快照不同，請先保留尚未儲存的修改。'

        return ""
    finally:
        db.close()

def has_resume_work_conflict(method_code, analysis_id):
    """Compatibility wrapper for callers that expect a boolean."""
    return bool(get_resume_work_conflict_reason(method_code, analysis_id))

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
                if field == "category":
                    from sqlalchemy import or_, and_
                    index_token = json.dumps({"category": value}, ensure_ascii=False)
                    match = db.query(AnalysisWorkState.id).filter(
                        AnalysisWorkState.analysis_id == AnalysisRecord.analysis_id,
                        AnalysisWorkState.state_json.contains(index_token, autoescape=True)).exists()
                    query = query.filter(or_(AnalysisRecord.category == value,
                        and_(AnalysisRecord.source_type == "ICP_IMPORT", match)))
                else:
                    query = query.filter(getattr(AnalysisRecord, field) == value)

        # 部分文字比對
        for field in (
            "exam_name",
            "method_code",
            "analyst_name",
        ):
            value = search_data[field]

            if value:
                if field == "exam_name":
                    from sqlalchemy import or_, and_
                    match = db.query(AnalysisWorkState.id).filter(
                        AnalysisWorkState.analysis_id == AnalysisRecord.analysis_id,
                        AnalysisWorkState.report_data_json.contains(value, autoescape=True)).exists()
                    query = query.filter(or_(AnalysisRecord.exam_name.contains(value, autoescape=True),
                        and_(AnalysisRecord.source_type == "ICP_IMPORT", match)))
                else:
                    query = query.filter(getattr(AnalysisRecord, field).contains(value))

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

        if record.source_type == "ICP_IMPORT":
            from services.icp_record_service import load_snapshot
            snapshot = load_snapshot(db, record)
            selected = request.args.get("channel") or snapshot["bundles"][0]["key"]
            channel = next((c for c in snapshot["bundles"] if c["key"] == selected), None)
            if channel is None:
                return "指定的金屬與波長不在此正式紀錄中。", 400
            history = db.query(AnalysisReviewHistory).filter(
                AnalysisReviewHistory.analysis_id == analysis_id
            ).order_by(AnalysisReviewHistory.created_at, AnalysisReviewHistory.id).all()
            return render_template("analysis_record_detail.html", record=record,
                icp_snapshot=snapshot, icp_channel=channel, review_history=history,
                active_page="analysis_records")

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

        w427_report_unit = None
        if str(record.method_code or "").strip().upper() == "W427":
            work = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == analysis_id).one()
            try:
                w427_report_unit = json.loads(work.method_data_json)["DISPLAY_CONC_UNIT"]
            except (ValueError, TypeError, KeyError):
                return "W427 正式紀錄設定快照無效，請保留資料並查明原因。", 400
        return render_template(
            "analysis_record_detail.html",
            record=record, w427_report_unit=w427_report_unit,
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

        if str(record.method_code or "").strip().upper() == "W427":
            from services.w427_pdf_export_service import export_w427_record_pdf
            try:
                output = export_w427_record_pdf(db, record)
            except ValueError as exc:
                return str(exc), 400
            return send_file(output, mimetype="application/pdf", as_attachment=True,
                             download_name="W427_Analysis_Record.pdf")

        if str(record.method_code or "").strip().upper() == "W430":
            from services.w430_pdf_export_service import export_w430_record_pdf
            try:
                pdf_buffer = export_w430_record_pdf(db, record)
            except ValueError as exc:
                return str(exc), 400
            return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True,
                             download_name="W430_Sulfate_Analysis_Record.pdf")

        if record.source_type == "ICP_IMPORT":
            from services.icp_record_service import load_snapshot
            snapshot = load_snapshot(db, record)
            import secrets
            from services.icp_performance_service import work_token
            session.setdefault("icp_record_csrf", secrets.token_urlsafe(32))
            return render_template("icp_record_export.html", record=record, snapshot=snapshot, snapshot_token=work_token(snapshot),
                export_kind="pdf", active_page="analysis_records")

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

        if str(record.method_code or "").strip().upper() == "W427":
            from services.w427_lims_export_service import export_w427_record_excel
            template_path = os.path.join(current_app.root_path,"resources","lims","lims匯入表格.xlsx")
            try:
                output = export_w427_record_excel(db,record,template_path)
            except ValueError as exc:
                return str(exc), 400
            return send_file(output,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,download_name="W427_LIMS_Import.xlsx")

        if str(record.method_code or "").strip().upper() == "W430":
            from services.w430_lims_export_service import export_w430_record_excel
            template_path = os.path.join(current_app.root_path,"resources","lims","lims匯入表格.xlsx")
            try:
                excel_buffer = export_w430_record_excel(db, record, template_path)
            except ValueError as exc:
                return str(exc), 400
            return send_file(excel_buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name="W430_LIMS_Import.xlsx")

        if record.source_type == "ICP_IMPORT":
            from services.icp_record_service import load_snapshot
            snapshot = load_snapshot(db, record)
            import secrets
            from services.icp_performance_service import work_token
            session.setdefault("icp_record_csrf", secrets.token_urlsafe(32))
            return render_template("icp_record_export.html", record=record, snapshot=snapshot, snapshot_token=work_token(snapshot),
                export_kind="excel", active_page="analysis_records")

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

        if record.source_type == "ICP_IMPORT":
            from services.icp_record_service import resume_icp_record
            from services.icp_performance_service import IcpPfmConflictError
            current_key = str(session.get("icp_work_key") or "")
            if current_key:
                from analysis.icp_state_repository import load_icp_work_state
                current = load_icp_work_state(current_key)
                if current and current.get("formal_analysis_id") != analysis_id and current.get("formal_status") not in {"SUBMITTED", "DELETED"}:
                    return "目前有其他 ICP 暫存工作，請先完成或處理目前工作，再進入修正。", 409
            try:
                key, work = resume_icp_record(db, record, get_current_user() or {}, can_review_analysis())
                db.commit()
            except PermissionError as exc:
                db.rollback()
                return str(exc), 403
            except (ValueError, IcpPfmConflictError) as exc:
                db.rollback()
                return str(exc), 409
            session["icp_work_key"] = key
            session["basic_info_form"] = dict(work["form_data"])
            return redirect(url_for("icp_data_bp.analysis_icp_data", work_key=key))

        # Stage 35G: managed drafts must not bypass revision checks.
        # Resume permissions will be integrated in the next web substep.
        from sqlalchemy import inspect
        from models import AnalysisWorkDraft
        managed_draft = None
        managed_drafts = []
        if inspect(db.connection()).has_table(AnalysisWorkDraft.__tablename__):
            managed_drafts = db.query(AnalysisWorkDraft).filter(
                AnalysisWorkDraft.formal_analysis_id == analysis_id
            ).limit(2).all()
            if len(managed_drafts) > 1:
                return "此正式紀錄關聯多筆工作，請先查明關聯，無法自動恢復。", 409
            managed_draft = managed_drafts[0] if managed_drafts else None
        if managed_draft is not None:
            from analysis.analysis_work_access import (
                resolve_work_owner, add_work_actor_history,
            )
            from analysis.analysis_work_draft_repository import (
                AnalysisWorkDraftRepository, DraftConflictError,
            )
            if method_code not in {"W434", "W430", "W427"}:
                return "此方法尚未接入新版工作恢復流程。", 400
            actor = get_current_user() or {}
            actor_id = str(actor.get("user_id") or "").strip()
            try:
                owner_id = resolve_work_owner(db, managed_draft, actor_id, method_code)
                repo = AnalysisWorkDraftRepository(db)
                bundle = repo.load_draft(managed_draft.work_id, owner_id, method_code)
                work_id = bundle["work_id"]
                if bundle["work_status"] == "SUBMITTED":
                    next_revision = repo.resume_draft(
                        work_id, owner_id, method_code, bundle["revision"]
                    )
                    add_work_actor_history(
                        db, analysis_id, "RESUME_DRAFT", work_id,
                        next_revision, "REJECTED",
                    )
                    db.commit()
                elif bundle["work_status"] != "EDITING":
                    return "此工作狀態不可進入修正。", 409
                # Existing EDITING work is reopened without reverting its edits.
                endpoint = {"W430":"w430_import_bp.import_w430", "W427":"w427_import_bp.import_w427"}.get(method_code, "analysis_w43401")
                return redirect(url_for(endpoint, saved="1", work_id=work_id))
            except PermissionError as exc:
                db.rollback()
                return str(exc), 403
            except (DraftConflictError, ValueError) as exc:
                db.rollback()
                return str(exc), 409
            except Exception:
                db.rollback()
                raise

        # 先檢查衝突，不覆寫現有工作
        conflict_reason = get_resume_work_conflict_reason(method_code, analysis_id)
        if conflict_reason:
            return (
                "無法進入修正：" + conflict_reason,
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

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>/delete",
    methods=["POST"]
)
@login_required
def delete_analysis_record(analysis_id):

    if not can_delete_analysis():
        return "您沒有分析紀錄刪除權限。", 403

    delete_reason = request.form.get(
        "delete_reason", ""
    ).strip()

    if not delete_reason:
        return "刪除分析紀錄時必須填寫刪除原因。", 400

    db = SessionLocal()

    try:
        record = db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == analysis_id
        ).first()

        if record is None:
            return "查無此分析紀錄。", 404

        current_user = get_current_user() or {}

        delete_history = AnalysisDeleteHistory(
            analysis_id=record.analysis_id,
            record_id=record.id,
            exam_name=record.exam_name,
            method_code=record.method_code,
            analyst_name=record.analyst_name,
            record_status=record.status,
            deleted_by_user_id=str(
                current_user.get("user_id", "") or ""
            ).strip(),
            deleted_by_employee_id=str(
                current_user.get("employee_id", "") or ""
            ).strip(),
            deleted_by_name=str(
                current_user.get("employee_name", "") or ""
            ).strip(),
            delete_reason=delete_reason
        )

        db.add(delete_history)

        if record.source_type == "ICP_IMPORT":
            from models import IcpImportWorkState
            from services.icp_record_service import load_snapshot, dumps
            from sqlalchemy import update
            snap = load_snapshot(db, record)
            original_work = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == snap["work_key"]).one_or_none()
            if original_work is not None:
                old_json = original_work.state_json
                work = json.loads(old_json)
                work["formal_status"] = "DELETED"
                changed = db.execute(update(IcpImportWorkState).where(
                    IcpImportWorkState.work_key == snap["work_key"], IcpImportWorkState.state_json == old_json
                ).values(state_json=dumps(work)))
                if changed.rowcount != 1:
                    raise ValueError("工作已更新，本次刪除未完成。")


        # 先刪除子表，保留原有順序
        for model in (
            AnalysisReviewHistory,
            AnalysisWorkState,
            AnalysisQaqcResult,
            AnalysisSample,
            AnalysisCalibrationPoint,
            AnalysisCalibrationSummary,
        ):
            db.query(model).filter(
                model.analysis_id == analysis_id
            ).delete(synchronize_session=False)

        # PFM V2.1 關聯清理，使用同一個 DB Session
        if record.source_type == "ICP_IMPORT":
            # ICP manual events exist independently before formal submission.
            # Removing a formal record must not remove that measurement history.
            from models import PerformanceAnalysisLink
            db.query(PerformanceAnalysisLink).filter(
                PerformanceAnalysisLink.analysis_id == analysis_id
            ).delete(synchronize_session=False)
        else:
            delete_performance_links_for_analysis(
                db=db,
                analysis_id=analysis_id
            )

        db.delete(record)
        db.commit()

        return redirect(url_for("analysis_records"))

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()