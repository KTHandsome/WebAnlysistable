from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file
)

from datetime import datetime, timedelta

from parsers.pe900_parser import parse_pe900_pdf

from calculations.w43401 import (
    calculate_calibration,
    calculate_sample_concentration
)

from analysis.analysis_batch_splitter import (
    filter_batches_by_exam_no
)

from analysis.qaqc_calculator import (
    build_qaqc_check_results
)

from analysis.analysis_state import (
    save_analysis_state,
    load_analysis_state,
    clear_analysis_state
)

from reports.w434_pdf import build_w434_pdf

from exports.w434_lims_mapper import (
    build_w434_lims_export_data
)

from exports.lims_excel_exporter import (
    build_lims_excel
)

from services.analysis_record_service import (
    save_w434_analysis_record
)

from auth_session import (
    clear_current_user,
    get_current_user,
    login_required,
    set_current_user
)

from database import SessionLocal

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary,
    AnalysisQaqcResult,
    AnalysisRecord,
    AnalysisReviewHistory,
    AnalysisSample,
    AnalysisWorkState
)

import os
import csv
import io
import json
import tempfile

app = Flask(__name__)
app.secret_key = "eacs-development-secret-key"

@app.template_filter(
    "taiwan_datetime"
)
def taiwan_datetime(
    value
):

    if value is None:
        return ""

    local_value = (
        value
        + timedelta(
            hours=8
        )
    )

    return local_value.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

@app.context_processor
def inject_current_user():

    return {
        "current_user":
            get_current_user()
    }

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    error_message = None

    if request.method == "POST":

        user_id = request.form.get(
            "user_id",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not user_id:

            error_message = (
                "請輸入帳號。"
            )

        elif not password:

            error_message = (
                "請輸入密碼。"
            )

        else:

            error_message = (
                "目前非公司環境，"
                "尚未啟用 LIMS 帳號驗證。"
            )

    return render_template(
        "login.html",
        error_message=error_message
    )


@app.route(
    "/dev-login",
    methods=["POST"]
)
def dev_login():

    set_current_user(
        user_id="DEV",
        employee_id="A11503-03",
        employee_name="測試人員",
        group_id="04",
        group_name="分析部",
        dept_no="C",
        dept_name="分析課",
        job_title="檢驗員"
    )

    return redirect(
        url_for(
            "home"
        )
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )

@app.route("/")
def home():

    if get_current_user() is None:
        return redirect(
            url_for("login")
        )

    return redirect(
        url_for("basic_info")
    )


def load_control_and_method_data(form_data):

    control_data = None
    method_data = None
    error_message = None

    ctrl_year = form_data.get("ctrl_year", "").strip()
    category = form_data.get("category", "").strip()
    exam_name = form_data.get("exam_name", "").strip()
    method_code = form_data.get("method_code", "").strip()
    instrument_id = form_data.get("instrument_id", "").strip()

    if not ctrl_year:
        return None, None, "請選擇管制年度。"

    if not exam_name:
        return None, None, "請輸入測項名稱。"

    if not method_code:
        return None, None, "請輸入分析方法。"

    csv_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Control_" + ctrl_year + ".csv"
    )

    if not os.path.exists(csv_file):

        return (
            None,
            None,
            "尚未匯入 "
            + ctrl_year
            + " 年管制資料。"
        )

    base_matches = []

    with open(
        csv_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if row.get("CTRL_YEAR", "").strip() != ctrl_year:
                continue

            if (
                row.get("CATEGORY_CODE", "").strip().upper()
                != category.upper()
            ):
                continue

            if row.get("EXAMNAME", "").strip() != exam_name:
                continue

            if (
                row.get("EM_NUM", "").strip().upper()
                != method_code.upper()
            ):
                continue

            base_matches.append(row)

    if len(base_matches) == 0:

        return (
            None,
            None,
            "查無符合條件的年度管制資料。"
        )

    # ========================================
    # 年度管制資料的儀器適用規則
    #
    # 1. 若有該 LABPARTID 的專屬管制資料，優先使用
    # 2. 若沒有專屬資料，回退使用 LABPARTID 空白的共用資料
    # ========================================

    specific_matches = []
    common_matches = []

    for row in base_matches:

        row_instrument = (
            row.get(
                "LABPARTID",
                ""
            )
            .strip()
        )

        if row_instrument == "":

            common_matches.append(
                row
            )

        elif (
            instrument_id
            and row_instrument.upper()
            == instrument_id.upper()
        ):

            specific_matches.append(
                row
            )

    if instrument_id and specific_matches:

        matches = specific_matches

    else:

        matches = common_matches

    if len(matches) == 0:

        if instrument_id:

            return (
                None,
                None,
                "查無此儀器專屬或共用的年度管制資料。"
            )

        return (
            None,
            None,
            "查無共用的年度管制資料。"
        )

    if len(matches) > 1:

        if instrument_id and specific_matches:

            return (
                None,
                None,
                "找到多筆相同儀器的年度管制資料，"
                "請檢查管制資料設定。"
            )

        return (
            None,
            None,
            "找到多筆共用年度管制資料，"
            "請檢查管制資料設定。"
        )

    control_data = matches[0]
    
    method_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(method_file):

        return (
            control_data,
            None,
            "尚未匯入方法設定資料。"
        )

    method_matches = []

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        method_reader = csv.DictReader(f)

        for method_row in method_reader:

            if (
                method_row.get("ACTIVE", "")
                .strip()
                .upper()
                != "Y"
            ):
                continue

            if (
                method_row.get("METHOD_CODE", "")
                .strip()
                .upper()
                != method_code.upper()
            ):
                continue

            method_matches.append(method_row)

    if len(method_matches) == 0:

        return (
            control_data,
            None,
            "已找到年度管制資料，但查無對應的方法設定。"
        )

    if len(method_matches) > 1:

        return (
            control_data,
            None,
            "找到多筆有效方法設定，請檢查 Phyon_Method_Settings.csv。"
        )

    method_data = method_matches[0]

    return control_data, method_data, None

def load_report_setting(method_data):

    if not method_data:
        return None, "尚未載入方法設定資料。"

    report_code = (
        method_data.get(
            "REPORT_CODE",
            ""
        )
        .strip()
    )

    if not report_code:
        return None, "方法設定缺少 REPORT_CODE。"

    report_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Report_Settings.csv"
    )

    if not os.path.exists(report_file):

        return (
            None,
            "尚未匯入報表設定資料。"
        )

    matches = []

    with open(
        report_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if (
                row.get("ACTIVE", "")
                .strip()
                .upper()
                != "Y"
            ):
                continue

            if (
                row.get("REPORT_CODE", "")
                .strip()
                .upper()
                != report_code.upper()
            ):
                continue

            matches.append(row)

    if len(matches) == 0:

        return (
            None,
            "查無 REPORT_CODE = "
            + report_code
            + " 的有效報表設定。"
        )

    if len(matches) > 1:

        return (
            None,
            "REPORT_CODE = "
            + report_code
            + " 找到多筆有效報表設定，"
            + "請檢查 Phyon_Report_Settings.csv。"
        )

    return matches[0], None

def load_instrument_options(form_data):

    method_code = form_data.get(
        "method_code",
        ""
    ).strip()

    if not method_code:
        return []

    relation_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Instrument.csv"
    )

    instrument_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Instrument_Settings.csv"
    )

    if not os.path.exists(relation_file):
        return []

    if not os.path.exists(instrument_file):
        return []

    # ========================================
    # 先取得此方法允許使用的 LABPARTID
    # ========================================
    allowed_labpartids = set()

    with open(
        relation_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            row_method_code = (
                row.get(
                    "METHOD_CODE",
                    ""
                )
                .strip()
                .upper()
            )

            if row_method_code != method_code.upper():
                continue

            labpartid = (
                row.get(
                    "LABPARTID",
                    ""
                )
                .strip()
            )

            if labpartid:
                allowed_labpartids.add(
                    labpartid.upper()
                )

    if not allowed_labpartids:
        return []

    # ========================================
    # 再到 Instrument Settings 取得完整儀器資料
    # ========================================
    instrument_options = []

    with open(
        instrument_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            labpartid = (
                row.get(
                    "LABPARTID",
                    ""
                )
                .strip()
            )

            if not labpartid:
                continue

            if labpartid.upper() not in allowed_labpartids:
                continue

            instrument_options.append(
                {
                    "LABPARTID":
                        labpartid,

                    "PARTNAME":
                        row.get(
                            "PARTNAME",
                            ""
                        ).strip(),

                    "BRAND":
                        row.get(
                            "BRAND",
                            ""
                        ).strip(),

                    "MODAL":
                        row.get(
                            "MODAL",
                            ""
                        ).strip()
                }
            )

    instrument_options.sort(
        key=lambda x: x["LABPARTID"].upper()
    )

    return instrument_options

@app.route("/analysis-records")
@login_required
def analysis_records():

    ctrl_year = request.args.get(
        "ctrl_year",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    exam_name = request.args.get(
        "exam_name",
        ""
    ).strip()

    method_code = request.args.get(
        "method_code",
        ""
    ).strip()

    instrument_id = request.args.get(
        "instrument_id",
        ""
    ).strip()

    analyst_name = request.args.get(
        "analyst_name",
        ""
    ).strip()

    analysis_date_start = request.args.get(
        "analysis_date_start",
        ""
    ).strip()

    analysis_date_end = request.args.get(
        "analysis_date_end",
        ""
    ).strip()

    db = SessionLocal()

    try:

        query = db.query(
            AnalysisRecord
        )

        # ========================================
        # 管制年度
        # ========================================

        if ctrl_year:

            query = query.filter(
                AnalysisRecord.ctrl_year
                == ctrl_year
            )

        # ========================================
        # 檢測類別
        # ========================================

        if category:

            query = query.filter(
                AnalysisRecord.category
                == category
            )

        # ========================================
        # 狀態
        # ========================================

        if status:

            query = query.filter(
                AnalysisRecord.status
                == status
            )

        # ========================================
        # 測項
        # ========================================

        if exam_name:

            query = query.filter(
                AnalysisRecord.exam_name
                .contains(
                    exam_name
                )
            )

        # ========================================
        # 方法
        # ========================================

        if method_code:

            query = query.filter(
                AnalysisRecord.method_code
                .contains(
                    method_code
                )
            )

        # ========================================
        # 儀器
        # ========================================

        if instrument_id:

            query = query.filter(
                AnalysisRecord.instrument_id
                == instrument_id
            )

        # ========================================
        # 分析人員
        # ========================================

        if analyst_name:

            query = query.filter(
                AnalysisRecord.analyst_name
                .contains(
                    analyst_name
                )
            )

        # ========================================
        # 分析日期
        # ========================================

        # ========================================
        # 分析日期區間
        #
        # 查詢條件與紀錄期間只要有交集
        # 就視為符合
        # ========================================

        if (
             analysis_date_start
             and analysis_date_end
        ):

             query = query.filter(
             AnalysisRecord.analysis_start_date
              <= analysis_date_end,
             AnalysisRecord.analysis_end_date
             >= analysis_date_start
        )
        elif analysis_date_start:

             query = query.filter(
             AnalysisRecord.analysis_end_date
             >= analysis_date_start
        )
        elif analysis_date_end:

            query = query.filter(
            AnalysisRecord.analysis_start_date
             <= analysis_date_end
            )          

        records = (
            query
            .order_by(
                AnalysisRecord.created_at.desc(),
                AnalysisRecord.id.desc()
            )
            .all()
        )

        search_data = {
            "ctrl_year":
                ctrl_year,

            "category":
                category,

            "status":
                status,

            "exam_name":
                exam_name,

            "method_code":
                method_code,

            "instrument_id":
                instrument_id,

            "analyst_name":
                analyst_name,

            "analysis_date_start":
                analysis_date_start,

            "analysis_date_end":
                analysis_date_end
        }

        return render_template(
            "analysis_records.html",
            records=records,
            search_data=search_data,
            active_page="analysis_records"
        )

    finally:

        db.close()

@app.route(
    "/analysis-records/<analysis_id>"
)
@login_required
def analysis_record_detail(
    analysis_id
):

    db = SessionLocal()

    try:

        record = (
            db.query(
                AnalysisRecord
            )
            .filter(
                AnalysisRecord.analysis_id
                == analysis_id
            )
            .first()
        )

        if record is None:

            return (
                "查無此分析紀錄。",
                404
            )

        samples = (
             db.query(
                 AnalysisSample
             )
            .filter(
                 AnalysisSample.analysis_id
              == analysis_id
            )
            .order_by(
                AnalysisSample.display_order,
                AnalysisSample.id
              )
           .all()
         )

        qaqc_results = (
            db.query(
               AnalysisQaqcResult
            )
           .filter(
               AnalysisQaqcResult.analysis_id
              == analysis_id
            )
           .order_by(
            AnalysisQaqcResult.display_order,
            AnalysisQaqcResult.id
            )
            .all()
        )

        calibration_summary = (
            db.query(
                AnalysisCalibrationSummary
            )
            .filter(
                AnalysisCalibrationSummary.analysis_id
                == analysis_id
            )
            .first()
        )

        calibration_points = (
            db.query(
                AnalysisCalibrationPoint
            )
            .filter(
                AnalysisCalibrationPoint.analysis_id
                == analysis_id
            )
            .order_by(
                AnalysisCalibrationPoint.display_order,
                AnalysisCalibrationPoint.id
            )
            .all()
        )

        review_history = (
            db.query(
                AnalysisReviewHistory
            )
            .filter(
                AnalysisReviewHistory.analysis_id
                == analysis_id
            )
            .order_by(
                AnalysisReviewHistory.created_at,
                AnalysisReviewHistory.id
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
            active_page="analysis_records"
        )
    finally:

        db.close()


@app.route(
    "/analysis-records/<analysis_id>/approve",
    methods=["POST"]
)
@login_required
def approve_analysis_record(
    analysis_id
):

    db = SessionLocal()

    try:

        record = (
            db.query(
                AnalysisRecord
            )
            .filter(
                AnalysisRecord.analysis_id
                == analysis_id
            )
            .first()
        )

        if record is None:

            return (
                "查無此分析紀錄。",
                404
            )

        if (
            record.status
            != "UNDER_REVIEW"
        ):

            return (
                "只有待審核紀錄可以執行審核通過。",
                400
            )

        current_user = (
            get_current_user()
            or {}
        )

        previous_status = (
            record.status
        )

        record.status = (
            "APPROVED"
        )

        record.reviewer_user_id = str(
            current_user.get(
                "user_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get(
                "employee_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get(
                "employee_name",
                ""
            )
            or ""
        ).strip()

        record.reviewed_at = (
    datetime.utcnow()
)

        record.review_comment = (
            request.form.get(
                "review_comment",
                ""
            ).strip()
        )

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,

            action="APPROVE",

            from_status=previous_status,

            to_status="APPROVED",

            reviewer_user_id=(
                record.reviewer_user_id
            ),

            reviewer_employee_id=(
                record.reviewer_employee_id
            ),

            reviewer_name=(
                record.reviewer_name
            ),

            comment=(
                record.review_comment
            )
        )

        db.add(
            review_history
        )

        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id
            )
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


@app.route(
    "/analysis-records/<analysis_id>/reject",
    methods=["POST"]
)
@login_required
def reject_analysis_record(
    analysis_id
):

    review_comment = (
        request.form.get(
            "review_comment",
            ""
        ).strip()
    )

    if not review_comment:

        return (
            "退回修正時必須填寫退回原因。",
            400
        )

    db = SessionLocal()

    try:

        record = (
            db.query(
                AnalysisRecord
            )
            .filter(
                AnalysisRecord.analysis_id
                == analysis_id
            )
            .first()
        )

        if record is None:

            return (
                "查無此分析紀錄。",
                404
            )

        if (
            record.status
            != "UNDER_REVIEW"
        ):

            return (
                "只有待審核紀錄可以退回修正。",
                400
            )

        current_user = (
            get_current_user()
            or {}
        )

        previous_status = (
            record.status
        )

        record.status = (
            "REJECTED"
        )

        record.reviewer_user_id = str(
            current_user.get(
                "user_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get(
                "employee_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get(
                "employee_name",
                ""
            )
            or ""
        ).strip()

        record.reviewed_at = (
    datetime.utcnow()
)

        record.review_comment = (
            review_comment
        )

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,

            action="REJECT",

            from_status=previous_status,

            to_status="REJECTED",

            reviewer_user_id=(
                record.reviewer_user_id
            ),

            reviewer_employee_id=(
                record.reviewer_employee_id
            ),

            reviewer_name=(
                record.reviewer_name
            ),

            comment=(
                record.review_comment
            )
        )

        db.add(
            review_history
        )       

        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id
            )
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()

@app.route(
    "/analysis-records/<analysis_id>/reopen",
    methods=["POST"]
)
@login_required
def reopen_approved_analysis_record(
    analysis_id
):

    review_comment = (
        request.form.get(
            "review_comment",
            ""
        ).strip()
    )

    if not review_comment:

        return (
            "再次退回修正時必須填寫原因。",
            400
        )

    db = SessionLocal()

    try:

        record = (
            db.query(
                AnalysisRecord
            )
            .filter(
                AnalysisRecord.analysis_id
                == analysis_id
            )
            .first()
        )

        if record is None:

            return (
                "查無此分析紀錄。",
                404
            )

        if (
            record.status
            != "APPROVED"
        ):

            return (
                "只有已審核紀錄"
                "可以再次退回修正。",
                400
            )

        current_user = (
            get_current_user()
            or {}
        )

        previous_status = (
            record.status
        )

        record.status = (
            "REJECTED"
        )

        record.reviewer_user_id = str(
            current_user.get(
                "user_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_employee_id = str(
            current_user.get(
                "employee_id",
                ""
            )
            or ""
        ).strip()

        record.reviewer_name = str(
            current_user.get(
                "employee_name",
                ""
            )
            or ""
        ).strip()

        record.reviewed_at = (
            datetime.utcnow()
        )

        record.review_comment = (
            review_comment
        )

        review_history = AnalysisReviewHistory(
            analysis_id=record.analysis_id,

            action="REOPEN_AFTER_APPROVAL",

            from_status=previous_status,

            to_status="REJECTED",

            reviewer_user_id=(
                record.reviewer_user_id
            ),

            reviewer_employee_id=(
                record.reviewer_employee_id
            ),

            reviewer_name=(
                record.reviewer_name
            ),

            comment=(
                record.review_comment
            )
        )

        db.add(
            review_history
        )

        db.commit()

        return redirect(
            url_for(
                "analysis_record_detail",
                analysis_id=analysis_id
            )
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()       

@app.route(
    "/analysis-records/<analysis_id>/resume",
    methods=["POST"]
)
@login_required
def resume_analysis_record(
    analysis_id
):

    db = SessionLocal()

    try:

        record = (
            db.query(
                AnalysisRecord
            )
            .filter(
                AnalysisRecord.analysis_id
                == analysis_id
            )
            .first()
        )

        if record is None:

            return (
                "查無此分析紀錄。",
                404
            )

        if (
            record.status
            != "REJECTED"
        ):

            return (
                "只有退回修正的分析紀錄"
                "可以重新進入修正。",
                400
            )

        if (
            record.method_code
            != "W434"
        ):

            return (
                "目前只支援 W434 "
                "退回紀錄重新進入修正。",
                400
            )

        work_state = (
            db.query(
                AnalysisWorkState
            )
            .filter(
                AnalysisWorkState.analysis_id
                == analysis_id
            )
            .first()
        )

        if work_state is None:

            return (
                "此分析紀錄沒有可恢復的"
                "原分析工作資料。",
                400
            )

        try:

            analysis_state = json.loads(
                work_state.state_json
                or "{}"
            )

            form_data = json.loads(
                work_state.form_data_json
                or "{}"
            )

        except json.JSONDecodeError:

            return (
                "原分析工作資料格式異常，"
                "無法恢復。",
                500
            )

        if not analysis_state:

            return (
                "原分析工作資料內容為空白，"
                "無法恢復。",
                400
            )

        if not form_data:

            return (
                "原分析基本資料內容為空白，"
                "無法恢復。",
                400
            )

    finally:

        db.close()

    # ========================================
    # 確保恢復後仍然指向原正式紀錄
    # 避免重新儲存時產生另一筆 AnalysisRecord
    # ========================================

    analysis_state[
        "formal_analysis_id"
    ] = analysis_id

    save_analysis_state(
        "W434_CURRENT",
        analysis_state
    )

    session[
        "basic_info_form"
    ] = form_data

    session[
        "w434_formal_analysis_id"
    ] = analysis_id

    return redirect(
        url_for(
            "analysis_w43401",
            saved="1"
        )
    )

@app.route("/basic-info", methods=["GET", "POST"])
@login_required
def basic_info():

    control_data = None
    method_data = None
    error_message = None
    instrument_options = []

    default_form_data = {
    "ctrl_year": "2026",
    "category": "W",
    "exam_name": "",
    "method_code": "",
    "instrument_id": "",
    "instrument_model": "",
    "analysis_start_date": "",
    "analysis_end_date": "",
    "form_date": "",
    "wavelength": ""
}

    form_data = session.get(
        "basic_info_form",
        default_form_data.copy()
    )

    if request.method == "POST":

        form_data = {
            "ctrl_year": request.form.get(
                "ctrl_year",
                ""
            ).strip(),

            "category": request.form.get(
                "category",
                ""
            ).strip(),

            "exam_name": request.form.get(
                "exam_name",
                ""
            ).strip(),

            "method_code": request.form.get(
                "method_code",
                ""
            ).strip(),

            "instrument_id": request.form.get(
                "instrument_id",
                ""
            ).strip(),

            "instrument_model": "",

            "analysis_start_date": request.form.get(
                "analysis_start_date",
                ""
            ).strip(),

            "analysis_end_date": request.form.get(
                "analysis_end_date",
                ""
            ).strip(),

            "form_date": request.form.get(
                "form_date",
                ""
            ).strip(),

            "wavelength": request.form.get(
                "wavelength",
                ""
            ).strip()
        }

        next_action = (
            request.form.get(
                "next_action",
                ""
            )
            .strip()
        )

        instrument_options = (
            load_instrument_options(
                form_data
            )
        )

        # 若只有一台適用儀器，
        # 第一次查詢後直接自動選定。
        if (
            not form_data.get(
                "instrument_id"
            )
            and len(
                instrument_options
            ) == 1
        ):

            form_data[
                "instrument_id"
            ] = instrument_options[0][
                "LABPARTID"
            ]

        selected_instrument = None

        for option in instrument_options:

            if (
                option.get(
                    "LABPARTID",
                    ""
                ).strip()
                == form_data.get(
                    "instrument_id",
                    ""
                ).strip()
            ):

                selected_instrument = option
                break

        if selected_instrument:

            form_data[
                "instrument_model"
            ] = (
                selected_instrument.get(
                    "MODAL",
                    ""
                )
                .strip()
            )

        session[
            "basic_info_form"
        ] = form_data

        if form_data.get(
            "instrument_id"
        ):

            (
                control_data,
                method_data,
                error_message
            ) = load_control_and_method_data(
                form_data
            )

        else:

            control_data = None
            method_data = None

            if instrument_options:

                error_message = (
                    "請選擇儀器後繼續。"
                )
        if (
            next_action == "manual_entry"
            and method_data
            and form_data.get(
                "instrument_id"
            )
        ):

            return redirect(
                url_for(
                    "manual_analysis_entry"
                )
            )

        if (
            next_action == "import_w434"
            and method_data
            and form_data.get(
                "instrument_id"
            )
        ):

            return redirect(
                url_for(
                    "analysis_w43401"
                )
            )

    else:

        instrument_options = (
            load_instrument_options(
                form_data
            )
        )

        if (
            form_data.get(
                "ctrl_year"
            )
            and form_data.get(
                "exam_name"
            )
            and form_data.get(
                "method_code"
            )
            and form_data.get(
                "instrument_id"
            )
        ):

            (
                control_data,
                method_data,
                error_message
            ) = load_control_and_method_data(
                form_data
            )

    return render_template(
        "basic_info.html",
        control_data=control_data,
        method_data=method_data,
        error_message=error_message,
        form_data=form_data,
        instrument_options=instrument_options,
        active_page="analysis_basic"
    )

@app.route(
    "/analysis/manual",
    methods=["GET"]
)
@login_required
def manual_analysis_entry():

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return redirect(
            url_for(
                "basic_info"
            )
        )

    (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if load_error:

        return redirect(
            url_for(
                "basic_info"
            )
        )

    entry_mode = str(
        method_data.get(
            "DATA_ENTRY_MODE",
            ""
        )
        or ""
    ).strip().upper()

    if entry_mode not in {
        "MANUAL",
        "BOTH"
    }:

        return (
            "此分析方法未開放手動輸入。",
            400
        )

    try:

        calibration_count = int(
            method_data.get(
                "CALIBRATION_COUNT",
                "0"
            )
        )

    except ValueError:

        calibration_count = 0

    if calibration_count <= 0:

        return (
            "方法設定的檢量線點數無效。",
            400
        )

    return render_template(
        "analysis/manual_entry.html",
        active_page="analysis_method",
        form_data=form_data,
        control_data=control_data,
        method_data=method_data,
        calibration_count=calibration_count
    )

def classify_w434_rows(preview_rows, method_data):

    calibration_count = int(
        method_data.get("CALIBRATION_COUNT", "0")
    )

    calibration_values_text = (
        method_data.get("CALIBRATION_VALUES", "")
        .strip()
    )

    calibration_values = []

    if calibration_values_text:

        calibration_values = [
            float(value.strip())
            for value in calibration_values_text.split("|")
            if value.strip() != ""
        ]

    classified_rows = []

    for index, row in enumerate(preview_rows):

        sample_id = row["sample_id"].strip()
        sample_id_upper = sample_id.upper()

        role = "SAMPLE"
        calibration_x = None

        # 前 CALIBRATION_COUNT 筆視為檢量線標準點
        if index < calibration_count:

            role = "STANDARD"

            if index < len(calibration_values):
                calibration_x = calibration_values[index]

        elif (
             sample_id_upper == "ICBK"
             or sample_id_upper.startswith("ICBK-")
             ):
             role = "ICBK"

        elif (
             sample_id_upper == "ICV"
             or sample_id_upper.startswith("ICV-")
             ):
             role = "ICV"

        elif (
             sample_id_upper == "BK"
             or sample_id_upper.startswith("BK-")
             ):
             role = "BK"

        elif (
             sample_id_upper == "QC"
             or sample_id_upper.startswith("QC-")
             ):
             role = "QC"

        elif sample_id_upper.startswith("MDL-"):
             role = "MDL"

        elif (
             sample_id_upper == "CCBK"
             or sample_id_upper.startswith("CCBK-")
             ):
             role = "CCBK"

        elif (
             sample_id_upper == "CCV"
             or sample_id_upper.startswith("CCV-")
             ):
             role = "CCV"

        elif (
             sample_id_upper == "DUP"
             or sample_id_upper.startswith("DUP-")
             or (
             sample_id_upper.startswith("DUP")
             and sample_id_upper[3:].isdigit()
                )
             ):
             role = "DUP"     

        elif (
             sample_id_upper == "MSD"
             or sample_id_upper.startswith("MSD-")
             ):
             role = "MSD"

        elif (
             sample_id_upper == "MS"
             or sample_id_upper.startswith("MS-")
             ):
             role = "MS"

        classified_rows.append(
         {
          "sequence_no": row["sequence_no"],
          "sample_id": sample_id,
          "signal": row["signal"],

          "analyte": row.get(
            "analyte",
            ""
            ),

          "wavelength": row.get(
            "wavelength"
           ),

         "role": role,
         "calibration_x": calibration_x
          }
        )

    return classified_rows

def split_analysis_rows(rows):

    calibration_rows = []
    sample_qaqc_rows = []

    for row in rows:

        if row.get("role") == "STANDARD":
            calibration_rows.append(row)
        else:
            sample_qaqc_rows.append(row)

    return calibration_rows, sample_qaqc_rows

@app.route("/analysis/w43401", methods=["GET", "POST"])
@login_required
def analysis_w43401():

    existing_state = load_analysis_state(
        "W434_CURRENT"
    )

    existing_formal_analysis_id = ""

    if existing_state:

        existing_formal_analysis_id = str(
            existing_state.get(
                "formal_analysis_id",
                ""
            )
            or ""
        ).strip()

    formal_analysis_id = (
        existing_formal_analysis_id
    )

    if not formal_analysis_id:

        formal_analysis_id = str(
            session.get(
                "w434_formal_analysis_id",
                ""
            )
            or ""
        ).strip()

    if formal_analysis_id:

        session[
            "w434_formal_analysis_id"
        ] = formal_analysis_id   
    
    preview_rows = []
    calibration_rows = []
    sample_qaqc_rows = []
    excluded_rows = []
    included_batches = []
    qaqc_3a_results = []
    import_error = None
    uploaded_filename = None
    method_data = None
    control_data = None
    report_data = None
    calibration_result = None
    qdl_value = None
    load_error = None
    confirmed_wavelength = None
    wavelength_warning = None
    form_data = session.get(
    "basic_info_form"
    )

    if form_data:

     (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if (
        method_data
        and not load_error
    ):

        (
            report_data,
            report_error
        ) = load_report_setting(
            method_data
        )

        if report_error:
            load_error = report_error

    # ========================================
    # 儲存分析資料後重新顯示既有分析狀態
    # 不重新執行 PDF 匯入 / 初始化流程
    # ========================================
    if (
        request.method == "GET"
        and request.args.get("saved") == "1"
    ):

        saved_state = load_analysis_state(
            "W434_CURRENT"
        )

        if saved_state:

            return render_template(
                "methods/w43401.html",
                active_page="analysis_method",
                current_analysis_name="W434 砷分析",
                current_analysis_url="/analysis/w43401",
                analysis_version="1.00",
                error_message=request.args.get(
                      "error_message"
                ),
                preview_rows=saved_state.get(
                    "preview_rows",
                    []
                ),

                calibration_rows=saved_state.get(
                    "calibration_rows",
                    []
                ),

                sample_qaqc_rows=saved_state.get(
                    "sample_qaqc_rows",
                    []
                ),

               sample_data_saved=saved_state.get(
                     "sample_data_saved",
                      False
                ),

                import_error=None,

                uploaded_filename=saved_state.get(
                    "uploaded_filename"
                ),

                method_data=method_data,
                control_data=control_data,
                report_data=report_data,

                calibration_result=saved_state.get(
                    "calibration_result"
                ),

                qdl_value=saved_state.get(
                    "qdl_value"
                ),

                confirmed_wavelength=saved_state.get(
                    "confirmed_wavelength"
                ),

                wavelength_warning=saved_state.get(
                    "wavelength_warning"
                ),

                instrument_wavelength=saved_state.get(
                    "instrument_wavelength"
                ),

                basic_wavelength=(
                    form_data.get(
                        "wavelength",
                        ""
                    ).strip()
                    if form_data
                    else ""
                ),

                qaqc_3a_results=saved_state.get(
                    "qaqc_results",
                    []
                )
            )

    if load_error:
        import_error = load_error

    if request.method == "POST":

        pdf_file = request.files.get("pe900_pdf")

        if pdf_file is None or pdf_file.filename == "":
            import_error = "請先選擇 PDF 檔案。"

        elif not pdf_file.filename.lower().endswith(".pdf"):
            import_error = "只能匯入 PDF 檔案。"

        else:

            uploaded_filename = pdf_file.filename
            temp_path = None

            try:

                fd, temp_path = tempfile.mkstemp(
                    suffix=".pdf"
                )

                os.close(fd)

                pdf_file.save(temp_path)

                preview_rows = parse_pe900_pdf(
                    temp_path
                )

                if preview_rows and method_data:

                  preview_rows = classify_w434_rows(
                  preview_rows,
                  method_data
                    )


                if preview_rows and control_data:

                 selected_exam_no = (
                 control_data.get(
                 "EXAMNO",
                 ""
                 )
                 .strip()
                  )

                 (
                   preview_rows,
                   excluded_rows,
                   included_batches
                 ) = filter_batches_by_exam_no(
                   preview_rows,
                   selected_exam_no
                 )

                if preview_rows:

                  (
                     calibration_rows,
                    sample_qaqc_rows
                    ) = split_analysis_rows(
                     preview_rows
                  )

                if method_data and calibration_rows:

                    qdl_source = (
                      method_data.get(
                      "QDL_SOURCE",
                      ""
                      )
                      .strip()
                      .upper()
                     )

                    qdl_multiplier_text = (
                        method_data.get(
                        "QDL_MULTIPLIER",
                        ""
                        ).strip()
                   )

                    if qdl_source == "FIRST_NONZERO_CALIBRATION_X":

                        first_nonzero_x = None

                        for row in calibration_rows:

                          x_value = row.get(
                          "calibration_x"
                           )

                          if (
                             x_value is not None
                             and x_value > 0
                              ):
                               first_nonzero_x = x_value
                               break

                        if first_nonzero_x is not None:

                            try:

                              qdl_multiplier = float(
                              qdl_multiplier_text
                              )

                              qdl_value = (
                               first_nonzero_x
                               * qdl_multiplier
                               )

                            except ValueError:

                             qdl_value = None    

                if preview_rows:

                  try:

                    calibration_result = calculate_calibration(
                    preview_rows
                   )

                  except ValueError as ex:

                   import_error = (
                           "檢量線計算失敗："
                                + str(ex)
                             )  

                if len(preview_rows) == 0:
                    import_error = (
                        "PDF 已讀取，但未解析到 PE900 資料。"
                    )

            except Exception as ex:

                import_error = (
                    "PE900 PDF 解析失敗："
                    + str(ex)
                )

            finally:

                if (
                    temp_path
                    and os.path.exists(temp_path)
                ):
                    os.remove(temp_path)

        # 套用 QA/QC 預設添加濃度
        if method_data and sample_qaqc_rows:

              spike_field_by_role = {
                "ICV": "ICV_SPIKE_CONC",
                 "QC": "QC_SPIKE_CONC",
                "CCV": "CCV_SPIKE_CONC",
                 "MS": "MS_SPIKE_CONC",
                 "MSD": "MS_SPIKE_CONC"
             }

    for row in sample_qaqc_rows:

        row["spike_concentration"] = ""

        role = (
            row.get(
                "role",
                ""
            )
            .strip()
            .upper()
        )

        field_name = (
            spike_field_by_role.get(
                role
            )
        )

        if field_name:

            row["spike_concentration"] = (
                method_data.get(
                    field_name,
                    ""
                ).strip()
            )

            if calibration_result and sample_qaqc_rows:

               simple_roles = {
    "ICBK",
    "ICV",
    "BK",
    "QC",
    "MDL",
    "CCBK",
    "CCV",
    "MS",
    "MSD",
    "DUP",
    "SAMPLE"
               }

    for row in sample_qaqc_rows:

        row["sample_volume"] = 25
        row["final_volume"] = 50
        row["dilution_factor"] = 1
        row["remark"] = ""
        row["is_excluded"] = False
        row["exclusion_reason"] = ""
        row["calculated_concentration"] = None

        if row.get("role") not in simple_roles:
            continue

        try:

            result = calculate_sample_concentration(
                signal=row["signal"],
                slope=calibration_result["slope"],
                intercept=calibration_result["intercept"],
                sample_volume=row["sample_volume"],
                final_volume=row["final_volume"],
                dilution_factor=row["dilution_factor"]
            )

            row["calculated_concentration"] = (
                result["calculated_concentration"]
            )

        except ValueError:
            row["calculated_concentration"] = None

    if (
        included_batches
        and control_data
        and sample_qaqc_rows
    ):

        qaqc_3a_results = (
         build_qaqc_check_results(
        included_batches,
        control_data,
        cc_relative_error_limit=20.0,
        qdl_value=qdl_value
          )
      )

    instrument_analyte = ""
    instrument_wavelength = None

    for row in preview_rows:

        if not instrument_analyte:

            instrument_analyte = (
                row.get(
                    "analyte",
                    ""
                )
                .strip()
            )

        if instrument_wavelength is None:

            instrument_wavelength = row.get(
                "wavelength"
            )

        if (
            instrument_analyte
            and instrument_wavelength is not None
        ):

            break

    # ========================================
    # 波長確認邏輯
    #
    # Basic Info = 人工輸入值
    # Instrument = 儀器原始檔實際值
    # ========================================
    basic_wavelength_text = ""

    if form_data:

        basic_wavelength_text = (
            form_data.get(
                "wavelength",
                ""
            )
            .strip()
        )

    basic_wavelength = None

    if basic_wavelength_text:

        try:

            basic_wavelength = float(
                basic_wavelength_text
            )

        except ValueError:

            wavelength_warning = (
                "基本資料的波長格式不正確："
                + basic_wavelength_text
            )

    # ----------------------------------------
    # 儀器檔有解析到波長
    # ----------------------------------------
    if instrument_wavelength is not None:

        if basic_wavelength is not None:

            # 193.7 與 193.70 視為相同
            if abs(
                basic_wavelength
                - instrument_wavelength
            ) <= 0.001:

                confirmed_wavelength = (
                    instrument_wavelength
                )

            else:

                confirmed_wavelength = None

                wavelength_warning = (
                    "基本資料波長 "
                    + format(
                        basic_wavelength,
                        ".2f"
                    )
                    + " nm 與儀器原始資料 "
                    + format(
                        instrument_wavelength,
                        ".2f"
                    )
                    + " nm 不一致，請確認。"
                )

        elif not basic_wavelength_text:

            confirmed_wavelength = None

            wavelength_warning = (
                "基本資料尚未填寫波長；"
                "儀器原始資料解析為 "
                + format(
                    instrument_wavelength,
                    ".2f"
                )
                + " nm，請確認。"
            )

    # ----------------------------------------
    # 儀器檔沒有波長
    # → 若人工已有有效值，使用人工值
    # ----------------------------------------
    else:

        if basic_wavelength is not None:

            confirmed_wavelength = (
                basic_wavelength
            )

        elif not wavelength_warning:

            wavelength_warning = (
                "基本資料與儀器原始資料"
                "皆未取得有效波長。"
            )

    if (
        request.method == "POST"
        and preview_rows
    ):

        save_analysis_state(
            "W434_CURRENT",
            {
                "preview_rows":
                    preview_rows,

                "calibration_rows":
                    calibration_rows,

                "calibration_result":
                    calibration_result,

                "sample_qaqc_rows":
                    sample_qaqc_rows,

                "sample_data_saved":
                 False,    

                "included_batches":
                    included_batches,

                "qaqc_results":
                    qaqc_3a_results,

                "qdl_value":
                    qdl_value,

                "instrument_analyte":
                    instrument_analyte,

                "instrument_wavelength":
                    instrument_wavelength,

                "confirmed_wavelength":
                    confirmed_wavelength,

                "wavelength_warning":
                    wavelength_warning,

                "uploaded_filename":
                    uploaded_filename,

                "formal_analysis_id":
                   formal_analysis_id
                    
            }
        )

    return render_template(
        "methods/w43401.html",
        active_page="analysis_method",
        current_analysis_name="W434 砷分析",
        current_analysis_url="/analysis/w43401",
        analysis_version="1.00",
        preview_rows=preview_rows,
        calibration_rows=calibration_rows,
        sample_qaqc_rows=sample_qaqc_rows,
        sample_data_saved=False,
        import_error=import_error,
        uploaded_filename=uploaded_filename,
        method_data=method_data,
        control_data=control_data,
        report_data=report_data,
        calibration_result=calibration_result,
        qdl_value=qdl_value,
        confirmed_wavelength=confirmed_wavelength,
        wavelength_warning=wavelength_warning,
        instrument_wavelength=instrument_wavelength,
        basic_wavelength=(
                            form_data.get(
                                           "wavelength",
                                            ""
                                         ).strip()
                             if form_data
                             else ""
                             ),
        qaqc_3a_results=qaqc_3a_results    
        )

@app.route(
    "/analysis/w43401/confirm-wavelength",
    methods=["POST"]
)
@login_required
def confirm_w434_wavelength():

    choice = request.form.get(
        "choice",
        ""
    ).strip().lower()

    analysis_state = load_analysis_state(
        "W434_CURRENT"
    )

    if not analysis_state:

        return (
            "尚未找到 W434 分析資料。",
            400
        )

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return (
            "尚未找到基本資料。",
            400
        )

    instrument_wavelength = (
        analysis_state.get(
            "instrument_wavelength"
        )
    )

    basic_wavelength_text = (
        form_data.get(
            "wavelength",
            ""
        )
        .strip()
    )

    if choice == "instrument":

        if instrument_wavelength is None:

            return (
                "儀器原始資料沒有有效波長。",
                400
            )

        confirmed_wavelength = float(
            instrument_wavelength
        )

        analysis_state[
            "confirmed_wavelength"
        ] = confirmed_wavelength

        analysis_state[
            "wavelength_warning"
        ] = None

        analysis_state[
            "wavelength_source"
        ] = "INSTRUMENT"

        # 使用者已明確確認採用儀器值，
        # 同步回 Basic Info session
        form_data["wavelength"] = format(
            confirmed_wavelength,
            ".2f"
        )

        session[
            "basic_info_form"
        ] = form_data

    elif choice == "basic":

        if not basic_wavelength_text:

            return (
                "基本資料沒有可保留的波長。",
                400
            )

        try:

            confirmed_wavelength = float(
                basic_wavelength_text
            )

        except ValueError:

            return (
                "基本資料波長格式不正確。",
                400
            )

        analysis_state[
            "confirmed_wavelength"
        ] = confirmed_wavelength

        analysis_state[
            "wavelength_warning"
        ] = None

        analysis_state[
            "wavelength_source"
        ] = "BASIC"

    else:

        return (
            "未知的波長確認方式。",
            400
        )

    save_analysis_state(
        "W434_CURRENT",
        analysis_state
    )

    return "", 204

@app.route(
    "/analysis/w43401/update-samples",
    methods=["POST"]
)
@login_required
def update_w434_samples():

    analysis_state = load_analysis_state(
        "W434_CURRENT"
    )

    if not analysis_state:

        return (
            "尚未找到 W434 分析資料，請先匯入儀器 PDF。",
            400
        )

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return (
            "尚未找到分析基本資料。",
            400
        )

    (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if load_error:

        return (
            load_error,
            400
        )

    preview_rows = analysis_state.get(
        "preview_rows",
        []
    )

    included_batches = analysis_state.get(
        "included_batches",
        []
    )

    qdl_value = analysis_state.get(
        "qdl_value"
    )

    sample_qaqc_rows = analysis_state.get(
        "sample_qaqc_rows",
        []
    )

    calibration_result = analysis_state.get(
        "calibration_result"
    )

    if not sample_qaqc_rows:

        return (
            "尚未找到樣品及 QA/QC 資料。",
            400
        )

    if not calibration_result:

        return (
            "尚未取得有效檢量線，無法重新計算。",
            400
        )

    try:

        row_count = int(
            request.form.get(
                "row_count",
                "0"
            )
        )

    except ValueError:

        return (
            "樣品資料筆數格式錯誤。",
            400
        )

    row_map = {}

    for row in sample_qaqc_rows:

        sequence_key = str(
            row.get(
                "sequence_no",
                ""
            )
        )

        row_map[sequence_key] = row

    updated_rows = []

    for index in range(row_count):

        source_sequence = (
            request.form.get(
                "source_sequence_"
                + str(index),
                ""
            )
            .strip()
        )

        if source_sequence not in row_map:
            continue

        row = row_map[source_sequence]

        sample_id = (
            request.form.get(
                "sample_id_"
                + str(index),
                ""
            )
            .strip()
        )

        signal_text = (
            request.form.get(
                "sample_signal_"
                + str(index),
                ""
            )
            .strip()
        )

        dilution_text = (
            request.form.get(
                "dilution_factor_"
                + str(index),
                "1"
            )
            .strip()
        )

        sample_volume_text = (
            request.form.get(
                "sample_volume_"
                + str(index),
                "25"
            )
            .strip()
        )

        final_volume_text = (
            request.form.get(
                "final_volume_"
                + str(index),
                "50"
            )
            .strip()
        )

        spike_concentration = (
            request.form.get(
                "spike_concentration_"
                + str(index),
                ""
            )
            .strip()
        )

        remark = (
            request.form.get(
                "remark_"
                + str(index),
                ""
            )
            .strip()
        )

        is_excluded = (
            request.form.get(
                "is_excluded_"
                + str(index)
            )
            == "1"
        )

        exclusion_reason = (
            request.form.get(
                "exclusion_reason_"
                + str(index),
                ""
            )
            .strip()
        )

        try:

            display_order = int(
                request.form.get(
                    "display_order_"
                    + str(index),
                    str(index + 1)
                )
            )

            signal = float(
                signal_text
            )

            dilution_factor = float(
                dilution_text
            )

            sample_volume = float(
                sample_volume_text
            )

            final_volume = float(
                final_volume_text
            )

        except ValueError:

            return (
                "第 "
                + str(index + 1)
                + " 筆樣品含有無效的數值。",
                400
            )

        if dilution_factor <= 0:

            return (
                "第 "
                + str(index + 1)
                + " 筆稀釋倍數必須大於 0。",
                400
            )

        if sample_volume <= 0:

            return (
                "第 "
                + str(index + 1)
                + " 筆取樣體積必須大於 0。",
                400
            )

        if final_volume <= 0:

            return (
                "第 "
                + str(index + 1)
                + " 筆最終定量體積必須大於 0。",
                400
            )

        row["sample_id"] = sample_id
        row["signal"] = signal
        row["sample_volume"] = sample_volume
        row["final_volume"] = final_volume
        row["dilution_factor"] = dilution_factor
        row["spike_concentration"] = (
            spike_concentration
        )
        row["remark"] = remark
        row["is_excluded"] = is_excluded
        row["exclusion_reason"] = (
            exclusion_reason
        )
        row["display_order"] = display_order

        try:

            result = calculate_sample_concentration(
                signal=signal,
                slope=calibration_result["slope"],
                intercept=calibration_result["intercept"],
                sample_volume=sample_volume,
                final_volume=final_volume,
                dilution_factor=dilution_factor
            )

            row["calculated_concentration"] = (
                result[
                    "calculated_concentration"
                ]
            )

        except ValueError:

            row[
                "calculated_concentration"
            ] = None

        updated_rows.append(
            row
        )

    updated_rows.sort(
        key=lambda row: row.get(
            "display_order",
            9999
        )
    )

    updated_row_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in updated_rows
    }

    for preview_row in preview_rows:

        sequence_key = str(
            preview_row.get(
                "sequence_no",
                ""
            )
        )

        updated_row = (
            updated_row_map.get(
                sequence_key
            )
        )

        if updated_row is None:
            continue

        preview_row[
            "sample_id"
        ] = updated_row.get(
            "sample_id",
            ""
        )

        preview_row[
            "signal"
        ] = updated_row.get(
            "signal"
        )

        preview_row[
            "sample_volume"
        ] = updated_row.get(
            "sample_volume"
        )

        preview_row[
            "final_volume"
        ] = updated_row.get(
            "final_volume"
        )

        preview_row[
            "dilution_factor"
        ] = updated_row.get(
            "dilution_factor"
        )

        preview_row[
            "spike_concentration"
        ] = updated_row.get(
            "spike_concentration",
            ""
        )

        preview_row[
            "calculated_concentration"
        ] = updated_row.get(
            "calculated_concentration"
        )

        preview_row[
            "remark"
        ] = updated_row.get(
            "remark",
            ""
        )

        preview_row[
            "display_order"
        ] = updated_row.get(
            "display_order"
        )

        preview_row[
            "is_excluded"
        ] = updated_row.get(
            "is_excluded",
            False
        )

        preview_row[
            "exclusion_reason"
        ] = updated_row.get(
            "exclusion_reason",
            ""
        )


    analysis_state[
        "preview_rows"
    ] = preview_rows    

    analysis_state[
        "sample_qaqc_rows"
    ] = updated_rows

    latest_row_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in preview_rows
    }

    for batch in included_batches:

        batch_rows = batch.get(
            "rows",
            []
        )

        for batch_row in batch_rows:

            sequence_key = str(
                batch_row.get(
                    "sequence_no",
                    ""
                )
            )

            latest_row = (
                latest_row_map.get(
                    sequence_key
                )
            )

            if latest_row is None:
                continue

            batch_row.update(
                latest_row
            )

        start_check = batch.get(
            "start_check"
        )

        if start_check:

            sequence_key = str(
                start_check.get(
                    "sequence_no",
                    ""
                )
            )

            latest_row = (
                latest_row_map.get(
                    sequence_key
                )
            )

            if latest_row is not None:
                start_check.update(
                    latest_row
                )

        end_check = batch.get(
            "end_check"
        )

        if end_check:

            sequence_key = str(
                end_check.get(
                    "sequence_no",
                    ""
                )
            )

            latest_row = (
                latest_row_map.get(
                    sequence_key
                )
            )

            if latest_row is not None:
                end_check.update(
                    latest_row
                )

    for debug_batch in included_batches:
        print(
            "BATCH",
            debug_batch.get("batch_no"),
            "| category =",
            debug_batch.get("batch_category"),
            "| rows =",
            [
                (
                    row.get("role"),
                    row.get("sample_id")
                )
                for row in debug_batch.get(
                    "rows",
                    []
                )
            ]
        )

    qaqc_results = []

    if (
        included_batches
        and control_data
    ):

        qaqc_results = (
            build_qaqc_check_results(
                included_batches,
                control_data,
                cc_relative_error_limit=20.0,
                qdl_value=qdl_value
            )
        )

    analysis_state[
        "preview_rows"
    ] = preview_rows

    analysis_state[
        "included_batches"
    ] = included_batches

    analysis_state[
        "qaqc_results"
    ] = qaqc_results

    
    analysis_state[
    "sample_data_saved"
] = True

    save_analysis_state(
        "W434_CURRENT",
        analysis_state
    )

    return redirect(
        url_for(
            "analysis_w43401",
            saved="1"
        )
    )

@app.route(
    "/analysis/w43401/save-record",
    methods=["POST"]
)
@login_required
def save_w434_record():

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return (
            "尚未建立分析基本資料。",
            400
        )

    (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if load_error:

        return (
            load_error,
            400
        )

    analysis_state = load_analysis_state(
        "W434_CURRENT"
    )

    if not analysis_state:

        return (
            "尚未找到 W434 分析資料，請先匯入儀器 PDF。",
            400
        )

    form_data = session.get(
        "basic_info_form"
    )

    current_user = (
        get_current_user()
        or {}
    )

    try:

        save_result = (
            save_w434_analysis_record(
                form_data=form_data,
                control_data=control_data,
                method_data=method_data,
                analysis_state=analysis_state,
                current_user=current_user
            )
        )

    except ValueError as ex:

        return redirect(
            url_for(
                "analysis_w43401",
                saved="1",
                error_message=str(ex)
            )
        )

    except Exception as ex:

        return redirect(
            url_for(
                "analysis_w43401",
                saved="1",
                error_message=(
                    "建立正式分析紀錄失敗："
                    + str(ex)
                )
            )
        )

    analysis_state[
        "formal_analysis_id"
    ] = save_result[
        "analysis_id"
    ]

    session[
    "w434_formal_analysis_id"
] = save_result[
    "analysis_id"
]

    save_analysis_state(
        "W434_CURRENT",
        analysis_state
    )

    return redirect(
        url_for(
            "analysis_w43401",
            saved="1",
            formal_saved="1"
        )
    )

@app.route("/analysis/w43401/export-pdf")
@login_required
def export_w434_pdf():

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return (
            "尚未建立分析基本資料。",
            400
        )

    (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if load_error:

        return (
            load_error,
            400
        )

    (
        report_data,
        report_error
    ) = load_report_setting(
        method_data
    )

    if report_error:

        return (
            report_error,
            400
        )

    analysis_state = load_analysis_state(
        "W434_CURRENT"
    )

    if not analysis_state:

        return (
            "尚未找到 W434 分析結果，請先匯入並解析 PE900 PDF。",
            400
        ) 

    pdf_buffer = build_w434_pdf(
    report_data,
    method_data,
    control_data,
    form_data,
    analysis_state
    )

    analyte_display = (
        method_data.get(
            "ANALYTE_DISPLAY",
            ""
        )
        .strip()
    )

    if not analyte_display:
        analyte_display = "Analysis"

    download_name = (
        "W434_"
        + analyte_display
        + "_Analysis_Record.pdf"
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name
    )

@app.route("/analysis/w43401/export-lims")
@login_required
def export_w434_lims():

    form_data = session.get(
        "basic_info_form"
    )

    if not form_data:

        return (
            "尚未建立分析基本資料。",
            400
        )

    (
        control_data,
        method_data,
        load_error
    ) = load_control_and_method_data(
        form_data
    )

    if load_error:

        return (
            load_error,
            400
        )

    analysis_state = load_analysis_state(
        "W434_CURRENT"
    )

    if not analysis_state:

        return (
            "尚未找到 W434 分析結果，請先完成分析資料。",
            400
        )

    export_data = (
        build_w434_lims_export_data(
            form_data=form_data,
            control_data=control_data,
            analysis_state=analysis_state,
            analyst=""
        )
    )

    if not export_data.qc_rows:

        return (
            "目前沒有可匯出的 LIMS 品管資料。",
            400
        )

    if not export_data.analysis_rows:

        return (
            "目前沒有可匯出的正式樣品資料。",
            400
        )

    template_path = os.path.join(
        app.root_path,
        "resources",
        "lims",
        "lims匯入表格.xlsx"
    )

    if not os.path.exists(
        template_path
    ):

        return (
            "找不到 LIMS Excel 範本。",
            500
        )

    analysis_method = (
        control_data.get(
            "EM_NO",
            ""
        )
        .strip()
    )

    user_data = get_current_user() or {}

    analyst_id = (
    user_data.get(
        "employee_id",
        ""
    )
    .strip()
)

    analyst_name = (
    user_data.get(
        "employee_name",
        ""
    )
    .strip()
)   

    excel_buffer = build_lims_excel(
    template_path=template_path,
    export_data=export_data,
    analyst_id=analyst_id,
    analyst_name=analyst_name,
    analysis_method=analysis_method
)

    exam_no = (
        control_data.get(
            "EXAMNO",
            ""
        )
        .strip()
    )

    if not exam_no:
        exam_no = "LIMS"

    download_name = (
        exam_no
        + "_LIMS_Import.xlsx"
    )

    return send_file(
        excel_buffer,
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        as_attachment=True,
        download_name=download_name
    )

@app.route("/control-import", methods=["GET", "POST"])
@login_required
def control_import():

    success_message = None
    error_message = None

    if request.method == "POST":

        ctrl_year = request.form.get("ctrl_year", "").strip()
        uploaded_file = request.files.get("csv_file")

        if not ctrl_year:

            error_message = "請選擇年度。"

        elif uploaded_file is None or uploaded_file.filename == "":

            error_message = "請選擇 CSV 檔案。"

        elif not uploaded_file.filename.lower().endswith(".csv"):

            error_message = "只能匯入 CSV 檔案。"

        else:

            try:

                # 先把上傳檔案讀入記憶體，
                # 驗證成功後才真正寫入 data 資料夾
                file_bytes = uploaded_file.read()

                try:
                    csv_text = file_bytes.decode("utf-8-sig")

                except UnicodeDecodeError:
                    error_message = "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                    csv_text = None

                if csv_text is not None:

                    reader = csv.DictReader(
                        io.StringIO(csv_text)
                    )

                    # Phyon 管制資料必要欄位
                    required_columns = {
                        "CTRL_YEAR",
                        "CATEGORY_CODE",
                        "EXAMNO",
                        "EXAMNAME",
                        "EXALIAS",
                        "EM_NUM",
                        "EM_NO",
                        "LABPARTID",
                        "CTRL_UNIT",
                        "DETECT_LIMITED",
                        "DC_UWL",
                        "DC_UCL",
                        "QC_UWL",
                        "QC_UCL",
                        "QC_LWL",
                        "QC_LCL",
                        "SPIKE_UWL",
                        "SPIKE_UCL",
                        "SPIKE_LWL",
                        "SPIKE_LCL"
                    }

                    actual_columns = set(
                        reader.fieldnames or []
                    )

                    missing_columns = (
                        required_columns - actual_columns
                    )

                    if missing_columns:

                        error_message = (
                            "CSV 格式不正確，缺少必要欄位："
                            + ", ".join(
                                sorted(missing_columns)
                            )
                        )

                    else:

                        rows = list(reader)

                        if len(rows) == 0:

                            error_message = (
                                "CSV 沒有任何管制資料。"
                            )

                        else:

                            invalid_year_rows = []

                            for index, row in enumerate(
                                rows,
                                start=2
                            ):

                                row_year = (
                                    row.get(
                                        "CTRL_YEAR",
                                        ""
                                    ).strip()
                                )

                                if row_year != ctrl_year:

                                    invalid_year_rows.append(
                                        index
                                    )

                            if invalid_year_rows:

                                error_message = (
                                    "CSV 年度與選擇年度不一致。"
                                    "目前選擇："
                                    + ctrl_year
                                    + " 年；錯誤資料列："
                                    + ", ".join(
                                        map(
                                            str,
                                            invalid_year_rows[:10]
                                        )
                                    )
                                )

                            else:

                                data_folder = os.path.join(
                                    app.root_path,
                                    "data"
                                )

                                os.makedirs(
                                    data_folder,
                                    exist_ok=True
                                )

                                save_name = (
                                    "Phyon_Control_"
                                    + ctrl_year
                                    + ".csv"
                                )

                                save_path = os.path.join(
                                    data_folder,
                                    save_name
                                )

                                # 驗證成功才正式儲存
                                with open(
                                    save_path,
                                    "wb"
                                ) as f:

                                    f.write(file_bytes)

                                success_message = (
                                    ctrl_year
                                    + " 年管制資料匯入成功，"
                                    + "共 "
                                    + str(len(rows))
                                    + " 筆。"
                                )

            except Exception as ex:

                error_message = (
                    "匯入管制資料失敗："
                    + str(ex)
                )

    return render_template(
        "control_import.html",
        success_message=success_message,
        error_message=error_message,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

@app.route("/method-settings-import", methods=["POST"])
@login_required
def method_settings_import():

    uploaded_file = request.files.get("method_csv_file")

    method_success_message = None
    method_error_message = None

    if uploaded_file is None or uploaded_file.filename == "":

        method_error_message = "請選擇方法設定 CSV 檔案。"

    elif not uploaded_file.filename.lower().endswith(".csv"):

        method_error_message = "只能匯入 CSV 檔案。"

    else:

        try:

            file_bytes = uploaded_file.read()

            try:
                csv_text = file_bytes.decode("utf-8-sig")

            except UnicodeDecodeError:

                csv_text = None
                method_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "VERSION",
                    "EFFECTIVE_DATE",
                    "CATEGORY_CODE",
                    "EXAMNO",
                    "EXAMNAME",
                    "METHOD_CODE",
                    "ANALYTE_DISPLAY",
                    "REPORT_CODE",
                    "MAX_SAMPLE_PER_BATCH",
                    "CALIBRATION_COUNT",
                    "CALIBRATION_VALUES",
                    "CALIBRATION_UNIT",
                    "DATA_ENTRY_MODE",
                    "IMPORT_TYPE",
                    "SIGNAL_FIELD",
                    "ICV_SPIKE_CONC",
                    "QC_SPIKE_CONC",
                    "CCV_SPIKE_CONC",
                    "MS_SPIKE_CONC",
                    "BLANK_MDL_MULTIPLIER",
                    "QDL_SOURCE",
                    "QDL_MULTIPLIER",
                    "ACTIVE"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns - actual_columns
                )

                if missing_columns:

                    method_error_message = (
                        "方法設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(missing_columns)
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        method_error_message = (
                            "方法設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            exam_no = row.get(
                                "EXAMNO",
                                ""
                            ).strip()

                            method_code = row.get(
                                "METHOD_CODE",
                                ""
                            ).strip()

                            analyte_display = row.get(
                                "ANALYTE_DISPLAY",
                                ""
                            ).strip()

                            report_code = row.get(
                                "REPORT_CODE",
                                ""
                            ).strip()
                            

                            max_sample_text = row.get(
                                "MAX_SAMPLE_PER_BATCH",
                                ""
                            ).strip()

                            calibration_count_text = row.get(
                                "CALIBRATION_COUNT",
                                ""
                            ).strip()

                            calibration_values_text = row.get(
                                "CALIBRATION_VALUES",
                                ""
                            ).strip()

                            data_entry_mode = row.get(
                                 "DATA_ENTRY_MODE",
                                 ""
                            ).strip().upper()

                            import_type = row.get(
                                "IMPORT_TYPE",
                                ""
                            ).strip().upper()

                            signal_field = row.get(
                                "SIGNAL_FIELD",
                                ""
                            ).strip().upper()


                            blank_mdl_multiplier_text = row.get(
                               "BLANK_MDL_MULTIPLIER",
                               ""
                            ).strip()

                            qdl_source = row.get(
                               "QDL_SOURCE",
                               ""
                            ).strip().upper()

                            qdl_multiplier_text = row.get(
                               "QDL_MULTIPLIER",
                               ""
                            ).strip()                         

                            active = row.get(
                                "ACTIVE",
                                ""
                            ).strip().upper()

                            # EXAMNO
                            if not exam_no:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：EXAMNO 不可空白。"
                                )

                            # METHOD_CODE
                            if not method_code:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：METHOD_CODE 不可空白。"
                                )

                            # ANALYTE_DISPLAY
                            if not analyte_display:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ANALYTE_DISPLAY 不可空白。"
                                )    

                            # REPORT_CODE
                            if not report_code:

                                validation_errors.append(
                                     "第 "
                                     + str(row_index)
                                     + " 列：REPORT_CODE 不可空白。"
                                )    

                            # MAX_SAMPLE_PER_BATCH
                            try:

                                max_sample_per_batch = int(
                                    max_sample_text
                                )

                                if max_sample_per_batch <= 0:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：MAX_SAMPLE_PER_BATCH 必須大於 0。"
                                    )

                            except ValueError:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：MAX_SAMPLE_PER_BATCH 必須是整數。"
                                )

                            # CALIBRATION_COUNT
                            try:

                                calibration_count = int(
                                    calibration_count_text
                                )

                                if calibration_count <= 0:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：CALIBRATION_COUNT 必須大於 0。"
                                    )

                            except ValueError:

                                calibration_count = None

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_COUNT 必須是整數。"
                                )

                            # CALIBRATION_VALUES
                            calibration_values = []

                            if not calibration_values_text:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_VALUES 不可空白。"
                                )

                            else:

                                raw_values = (
                                    calibration_values_text.split("|")
                                )

                                for value in raw_values:

                                    value = value.strip()

                                    try:

                                        calibration_values.append(
                                            float(value)
                                        )

                                    except ValueError:

                                        validation_errors.append(
                                            "第 "
                                            + str(row_index)
                                            + " 列：CALIBRATION_VALUES 含有非數字資料："
                                            + value
                                        )

                            if (
                                calibration_count is not None
                                and len(calibration_values) > 0
                                and len(calibration_values)
                                != calibration_count
                            ):

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_COUNT = "
                                    + str(calibration_count)
                                    + "，但 CALIBRATION_VALUES 實際有 "
                                    + str(len(calibration_values))
                                    + " 個。"
                                )

                                                            # DATA_ENTRY_MODE
                            allowed_data_entry_modes = {
                                "MANUAL",
                                "IMPORT",
                                "BOTH"
                            }

                            if data_entry_mode not in allowed_data_entry_modes:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：DATA_ENTRY_MODE 只能是 MANUAL、IMPORT 或 BOTH。"
                                )

                            # IMPORT_TYPE / SIGNAL_FIELD
                            # 只有 IMPORT 或 BOTH 才必須設定匯入格式
                            if data_entry_mode in {"IMPORT", "BOTH"}:

                                allowed_import_types = {
                                    "PE900_PDF"
                                }

                                if import_type not in allowed_import_types:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：IMPORT_TYPE 不支援："
                                        + import_type
                                    )

                                allowed_signal_fields = {
                                    "BLNKCORR_SIGNAL_MEAN"
                                }

                                if signal_field not in allowed_signal_fields:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：SIGNAL_FIELD 不支援："
                                        + signal_field
                                    )


                            # ACTIVE
                            if active not in {
                                "Y",
                                "N"
                            }:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ACTIVE 只能是 Y 或 N。"
                                )                           
  
                            # QA/QC 預設添加濃度
                            spike_fields = [
                               "ICV_SPIKE_CONC",
                               "QC_SPIKE_CONC",
                               "CCV_SPIKE_CONC",
                               "MS_SPIKE_CONC"
                            ]
                            for field_name in spike_fields:

                               value_text = row.get(
                               field_name,
                                ""
                               ).strip()
                               if value_text == "":
                                 continue

                               try:
                                  value = float(value_text)

                               except ValueError:

                                validation_errors.append(
                                  "第 "
                                  + str(row_index)
                                  + " 列："
                                  + field_name
                                  + " 必須為數字。"
                                 )

                                continue

                               if value < 0:

                                 validation_errors.append(
                                  "第 "
                                  + str(row_index)
                                  + " 列："
                                  + field_name
                                  + " 不可小於 0。"
                                 )

                            # Blank MDL 倍數
                            if blank_mdl_multiplier_text == "":

                               validation_errors.append(
                               "第 "
                               + str(row_index)
                               + " 列：BLANK_MDL_MULTIPLIER 不可空白。"
                               )

                            else:

                               try:
                                   blank_mdl_multiplier = float(
                                   blank_mdl_multiplier_text
                                  )

                                   if blank_mdl_multiplier <= 0:

                                     validation_errors.append(
                                      "第 "
                                      + str(row_index)
                                      + " 列：BLANK_MDL_MULTIPLIER 必須大於 0。"
                                       )

                               except ValueError:

                                   validation_errors.append(
                                    "第 "
                                   + str(row_index)
                                    + " 列：BLANK_MDL_MULTIPLIER 必須為數字。"
                                    )


                            # QDL 來源
                            allowed_qdl_sources = {
                                 "FIRST_NONZERO_CALIBRATION_X",
                                 "LIMS_QDL"
                                  }

                            if qdl_source not in allowed_qdl_sources:

                               validation_errors.append(
                                "第 "
                                + str(row_index)
                                + " 列：QDL_SOURCE 不支援："
                                + qdl_source
                                 )


                            # QDL 倍數
                            if qdl_multiplier_text == "":

                                validation_errors.append(
                                "第 "
                                 + str(row_index)
                                 + " 列：QDL_MULTIPLIER 不可空白。"
                                  )

                            else:

                                try:
                                    qdl_multiplier = float(
                                    qdl_multiplier_text
                                     )

                                    if qdl_multiplier <= 0:

                                         validation_errors.append(
                                          "第 "
                                         + str(row_index)
                                             + " 列：QDL_MULTIPLIER 必須大於 0。"
                                          )

                                except ValueError:

                                     validation_errors.append(
                                     "第 "
                                      + str(row_index)
                                        + " 列：QDL_MULTIPLIER 必須為數字。"
                                       )
                            
                if validation_errors:

                            method_error_message = (
                                "方法設定 CSV 驗證失敗："
                                + "<br>"
                                + "<br>".join(
                                    validation_errors[:20]
                                )
                            )

                else:

                            data_folder = os.path.join(
                                app.root_path,
                                "data"
                            )

                            os.makedirs(
                                data_folder,
                                exist_ok=True
                            )

                            save_path = os.path.join(
                                data_folder,
                                "Phyon_Method_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(file_bytes)

                            method_success_message = (
                                "方法設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )
  
        except Exception as ex:
           method_error_message = (
                "方法設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=method_success_message,
        method_error_message=method_error_message,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

@app.route("/report-settings-import", methods=["POST"])
@login_required
def report_settings_import():

    uploaded_file = request.files.get(
        "report_csv_file"
    )

    report_success_message = None
    report_error_message = None

    if (
        uploaded_file is None
        or uploaded_file.filename == ""
    ):

        report_error_message = (
            "請選擇報表設定 CSV 檔案。"
        )

    elif not uploaded_file.filename.lower().endswith(
        ".csv"
    ):

        report_error_message = (
            "只能匯入 CSV 檔案。"
        )

    else:

        try:

            file_bytes = uploaded_file.read()

            try:

                csv_text = file_bytes.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError:

                csv_text = None

                report_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "VERSION",
                    "EFFECTIVE_DATE",
                    "REPORT_CODE",
                    "COMPANY_NAME",
                    "FORM_TITLE",
                    "DOC_NO",
                    "REVISION",
                    "ISSUE_DATE",
                    "ACTIVE",
                    "REMARK"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns
                    - actual_columns
                )

                if missing_columns:

                    report_error_message = (
                        "報表設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(
                                missing_columns
                            )
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        report_error_message = (
                            "報表設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []
                        report_keys = set()

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            version = row.get(
                                "VERSION",
                                ""
                            ).strip()

                            effective_date = row.get(
                                "EFFECTIVE_DATE",
                                ""
                            ).strip()

                            report_code = row.get(
                                "REPORT_CODE",
                                ""
                            ).strip()

                            company_name = row.get(
                                "COMPANY_NAME",
                                ""
                            ).strip()

                            form_title = row.get(
                                "FORM_TITLE",
                                ""
                            ).strip()

                            doc_no = row.get(
                                "DOC_NO",
                                ""
                            ).strip()

                            revision = row.get(
                                "REVISION",
                                ""
                            ).strip()

                            issue_date = row.get(
                                "ISSUE_DATE",
                                ""
                            ).strip()

                            active = row.get(
                                "ACTIVE",
                                ""
                            ).strip().upper()

                            if not version:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：VERSION 不可空白。"
                                )

                            if not effective_date:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：EFFECTIVE_DATE 不可空白。"
                                )

                            else:

                                try:

                                    from datetime import datetime

                                    datetime.strptime(
                                        effective_date,
                                        "%Y-%m-%d"
                                    )

                                except ValueError:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：EFFECTIVE_DATE 必須為 yyyy-MM-dd。"
                                    )

                            if not report_code:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：REPORT_CODE 不可空白。"
                                )

                            if not company_name:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：COMPANY_NAME 不可空白。"
                                )

                            if not form_title:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：FORM_TITLE 不可空白。"
                                )

                            if not doc_no:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：DOC_NO 不可空白。"
                                )

                            if not revision:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：REVISION 不可空白。"
                                )

                            if not issue_date:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ISSUE_DATE 不可空白。"
                                )

                            if active not in {
                                "Y",
                                "N"
                            }:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ACTIVE 只能是 Y 或 N。"
                                )

                            if report_code and version:

                                report_key = (
                                    report_code.upper(),
                                    version.upper()
                                )

                                if report_key in report_keys:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：REPORT_CODE + VERSION 重複："
                                        + report_code
                                        + " / "
                                        + version
                                    )

                                else:

                                    report_keys.add(
                                        report_key
                                    )

                        if validation_errors:

                            report_error_message = (
                                "報表設定 CSV 驗證失敗："
                                + "<br>"
                                + "<br>".join(
                                    validation_errors[:20]
                                )
                            )

                        else:

                            data_folder = os.path.join(
                                app.root_path,
                                "data"
                            )

                            os.makedirs(
                                data_folder,
                                exist_ok=True
                            )

                            save_path = os.path.join(
                                data_folder,
                                "Phyon_Report_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(
                                    file_bytes
                                )

                            report_success_message = (
                                "報表設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )

        except Exception as ex:

            report_error_message = (
                "報表設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=report_success_message,
        report_error_message=report_error_message,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

@app.route("/instrument-settings-import", methods=["POST"])
@login_required
def instrument_settings_import():

    uploaded_file = request.files.get(
        "instrument_csv_file"
    )

    instrument_success_message = None
    instrument_error_message = None

    if (
        uploaded_file is None
        or uploaded_file.filename == ""
    ):

        instrument_error_message = (
            "請選擇儀器設定 CSV 檔案。"
        )

    elif not uploaded_file.filename.lower().endswith(
        ".csv"
    ):

        instrument_error_message = (
            "只能匯入 CSV 檔案。"
        )

    else:

        try:

            file_bytes = uploaded_file.read()

            try:

                csv_text = file_bytes.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError:

                csv_text = None

                instrument_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "LABPARTID",
                    "PARTID",
                    "PARTNAME",
                    "SERIALNO",
                    "MODAL",
                    "PROPERTYNO",
                    "PARTTYPE",
                    "PARTALIAS",
                    "DESCRIPTION",
                    "STATUS",
                    "BRAND",
                    "FACNAME",
                    "LOCATION",
                    "DEPT",
                    "DEPTNAME"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns
                    - actual_columns
                )

                if missing_columns:

                    instrument_error_message = (
                        "儀器設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(
                                missing_columns
                            )
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        instrument_error_message = (
                            "儀器設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []
                        labpartid_set = set()

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            labpartid = (
                                row.get(
                                    "LABPARTID",
                                    ""
                                )
                                .strip()
                            )

                            if not labpartid:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：LABPARTID 不可空白。"
                                )

                                continue

                            labpartid_key = (
                                labpartid.upper()
                            )

                            if (
                                labpartid_key
                                in labpartid_set
                            ):

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：LABPARTID 重複："
                                    + labpartid
                                )

                            else:

                                labpartid_set.add(
                                    labpartid_key
                                )

                        if validation_errors:

                            instrument_error_message = (
                                "儀器設定 CSV 驗證失敗："
                                + "<br>"
                                + "<br>".join(
                                    validation_errors[:20]
                                )
                            )

                        else:

                            data_folder = os.path.join(
                                app.root_path,
                                "data"
                            )

                            os.makedirs(
                                data_folder,
                                exist_ok=True
                            )

                            save_path = os.path.join(
                                data_folder,
                                "Phyon_Instrument_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(
                                    file_bytes
                                )

                            instrument_success_message = (
                                "儀器設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )

        except Exception as ex:

            instrument_error_message = (
                "儀器設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=instrument_success_message,
        instrument_error_message=instrument_error_message,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

@app.route("/method-instrument-import", methods=["POST"])
@login_required
def method_instrument_import():

    uploaded_file = request.files.get(
        "method_instrument_csv_file"
    )

    method_instrument_success_message = None
    method_instrument_error_message = None

    if (
        uploaded_file is None
        or uploaded_file.filename == ""
    ):

        method_instrument_error_message = (
            "請選擇方法－儀器關聯 CSV 檔案。"
        )

    elif not uploaded_file.filename.lower().endswith(
        ".csv"
    ):

        method_instrument_error_message = (
            "只能匯入 CSV 檔案。"
        )

    else:

        try:

            file_bytes = uploaded_file.read()

            try:

                csv_text = file_bytes.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError:

                csv_text = None

                method_instrument_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "METHOD_CODE",
                    "LABPARTID"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns
                    - actual_columns
                )

                if missing_columns:

                    method_instrument_error_message = (
                        "方法－儀器關聯 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(
                                missing_columns
                            )
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        method_instrument_error_message = (
                            "方法－儀器關聯 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []
                        relation_keys = set()

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            method_code = (
                                row.get(
                                    "METHOD_CODE",
                                    ""
                                )
                                .strip()
                            )

                            labpartid = (
                                row.get(
                                    "LABPARTID",
                                    ""
                                )
                                .strip()
                            )

                            if not method_code:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：METHOD_CODE 不可空白。"
                                )

                            if not labpartid:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：LABPARTID 不可空白。"
                                )

                            if (
                                method_code
                                and labpartid
                            ):

                                relation_key = (
                                    method_code.upper(),
                                    labpartid.upper()
                                )

                                if (
                                    relation_key
                                    in relation_keys
                                ):

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：METHOD_CODE + LABPARTID 重複："
                                        + method_code
                                        + " / "
                                        + labpartid
                                    )

                                else:

                                    relation_keys.add(
                                        relation_key
                                    )

                        if validation_errors:

                            method_instrument_error_message = (
                                "方法－儀器關聯 CSV 驗證失敗："
                                + "<br>"
                                + "<br>".join(
                                    validation_errors[:20]
                                )
                            )

                        else:

                            data_folder = os.path.join(
                                app.root_path,
                                "data"
                            )

                            os.makedirs(
                                data_folder,
                                exist_ok=True
                            )

                            save_path = os.path.join(
                                data_folder,
                                "Phyon_Method_Instrument.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(
                                    file_bytes
                                )

                            method_instrument_success_message = (
                                "方法－儀器關聯匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )

        except Exception as ex:

            method_instrument_error_message = (
                "方法－儀器關聯匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=method_instrument_success_message,
        method_instrument_error_message=method_instrument_error_message,
        active_page="control"
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)