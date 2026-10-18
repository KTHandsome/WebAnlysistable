from routes.home_routes import home_bp
from routes.performance_control_import_routes import performance_control_import_bp
from routes.icp_analyte_import_routes import icp_analyte_import_bp
from routes.method_instrument_import_routes import method_instrument_import_bp
from routes.instrument_settings_import_routes import instrument_settings_import_bp
from routes.report_settings_import_routes import report_settings_import_bp
from routes.method_settings_import_routes import method_settings_import_bp
from flask import (Flask,render_template,request,redirect,url_for,session,flash,send_file,jsonify)
from routes.performance_history_routes import (performance_history_bp, register_performance_history_route,)
from routes.analysis_record_routes import analysis_record_bp
from services.lims_auth_service import (validate_lims_user)
from analysis.sample_category_filter import (detect_formal_sample_category)
from analysis.performance_classifier import (split_performance_rows)
from datetime import datetime, timedelta
from parsers.pe900_parser import parse_pe900_pdf
from parsers.oi_toc_parser import parse_oi_toc_pdf
from parsers.ra7000_parser import (parse_ra7000_pdf)
from parsers.icp5800_parser import parse_icp5800_pdf
from uuid import uuid4
from routes.control_import_routes import control_import_bp
from analysis.icp_workflow import (
    build_sample_candidate_groups,
    build_icp_candidate_selections,
    load_icp_analyte_map,
    match_lims_icp_analytes,
    build_icp_lims_matches,
)

from services.lims_analysis_service import (get_lims_sample_analysis)

from calculations.w43401 import (
    calculate_calibration,
    calculate_sample_concentration
)

from analysis.analysis_batch_splitter import (filter_batches_by_exam_no, split_analysis_batches)
from analysis.qaqc_calculator import (build_qaqc_check_results)
from analysis.analysis_workflow import (recalculate_sample_rows,sync_sample_rows_to_batches)

from analysis.analysis_state import (
    save_analysis_state,
    load_analysis_state,
    clear_analysis_state,
    update_analysis_state
)

from analysis.icp_state_repository import (
    save_icp_work_state,
    load_icp_work_state,
    list_icp_work_states
)

from reports.w434_pdf import build_w434_pdf
from exports.w434_lims_mapper import (build_w434_lims_export_data)
from exports.lims_excel_exporter import (build_lims_excel)
from services.analysis_record_service import (save_analysis_record)

from auth_session import (
    can_delete_analysis,
    can_review_analysis,
    can_manage_performance_control,    
    can_view_analysis_delete_history,
    clear_current_user,
    get_current_user,
    login_required,
    set_current_user
)

from database import (SessionLocal,DATABASE_TYPE)

from services.performance_query_service import (
    find_active_performance_control,
    PerformanceControlQueryError,
)

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary,
    AnalysisDeleteHistory,
    AnalysisQaqcResult,
    AnalysisRecord,
    AnalysisReviewHistory,
    AnalysisSample,
    AnalysisWorkState,
    PerformanceMeasurementHistory
)

from services.performance_release_service import (
    release_performance_csv_to_database,
    PerformanceReleaseNeedsReview
)

from services.performance_diff_service import (compare_performance_csv)
from services.performance_trend_service import (get_performance_trend)
from services.performance_history_service import (delete_performance_links_for_analysis)
from services.performance_history_query_service import (query_performance_history)

from analysis.analysis_route_helpers import (
    get_analysis_state_key,
    get_analysis_session_key,
    get_analysis_page_endpoint,
)

import os
import csv
import io
import json
import tempfile
import math

app = Flask(__name__)
app.secret_key = "eacs-development-secret-key"

@app.template_filter("taiwan_datetime")
def taiwan_datetime(value):

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
            get_current_user(),

        "environment_label": (
            "發布環境"
            if DATABASE_TYPE == "firebird"
            else "開發環境"
        ),

        "environment_type":
            DATABASE_TYPE
    }

@app.route("/login",methods=["GET", "POST"])
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

            try:

                user = validate_lims_user(
                    user_id,
                    password
                )

                if user is None:

                    error_message = (
                        "帳號或密碼錯誤。"
                    )

                else:

                    group_id = str(
                      user.get(
                         "group_id",
                         ""
                      )
                      or ""
                    ).strip().upper()

                    permissions = []

                    if group_id in {
                       "07",
                       "ADMIN"
                    }:

                        permissions = [
                        "REVIEW_ANALYSIS",
                        "DELETE_ANALYSIS",
                        "VIEW_ANALYSIS_DELETE_HISTORY"
                    ]
                        
                    group_id = str(
                           user.get(
                           "group_id",
                               ""
                          )
                      or ""
                    ).strip().upper()

                    permissions = []

                    if group_id in {
                         "07",
                          "ADMIN"
                        }:
                      permissions = [
                        "REVIEW_ANALYSIS",
                        "DELETE_ANALYSIS",
                        "VIEW_ANALYSIS_DELETE_HISTORY",
                        "MANAGE_PERFORMANCE_CONTROL"
                    ]     
                    
                    set_current_user(
                        user_id=user.get(
                            "user_id",
                            ""
                        ),
                        employee_id=user.get(
                            "employee_id",
                            ""
                        ),
                        employee_name=user.get(
                            "employee_name",
                            ""
                        ),                        
                        group_id=group_id,
                        dept_no=user.get(
                            "dept_no",
                            ""
                        ),
                        dept_name=user.get(
                            "dept_name",
                            ""
                        ),
                        permissions=permissions
                    )

                    return redirect(
                        url_for(
                            "home"
                        )
                    )

            except Exception as ex:

                print(
                    "LIMS login error:",
                    ex
                )

                error_message = (
                    "無法連線至 LIMS，"
                    "請稍後再試。"
                )

    return render_template(
    "login.html",
    error_message=error_message,
    show_dev_login=(
        DATABASE_TYPE == "sqlite"
    )
)

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


@app.route("/dev-login",methods=["POST"])
def dev_login():

    if DATABASE_TYPE != "sqlite":
        return (
            "正式環境不允許使用測試登入。",
            403
        )

    set_current_user(
        user_id="DEV",
        employee_id="S097-06",
        employee_name="測試人員",
        group_id="04",
        group_name="分析部",
        dept_no="C",
        dept_name="分析課",
        job_title="檢驗員",
        permissions=[
            "REVIEW_ANALYSIS",
            "DELETE_ANALYSIS",
            "VIEW_ANALYSIS_DELETE_HISTORY",
            "MANAGE_PERFORMANCE_CONTROL"
        ]      
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


def get_method_analysis_mode(method_code):
    method_code = str(
        method_code or ""
    ).strip().upper()

    if not method_code:
        return "SINGLE"

    method_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(method_file):
        raise ValueError("尚未匯入方法設定資料。")

    modes = set()

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(
                row.get("ACTIVE", "") or ""
            ).strip().upper() != "Y":
                continue

            if str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper() != method_code:
                continue

            mode = str(
                row.get("ANALYSIS_MODE", "") or ""
            ).strip().upper() or "SINGLE"

            if mode not in {"SINGLE", "MULTI_ANALYTE"}:
                raise ValueError(
                    method_code + " 的分析模式設定不正確。"
                )

            modes.add(mode)

    if not modes:
        raise ValueError(
            "查無方法 " + method_code + " 的有效設定。"
        )

    if len(modes) > 1:
        raise ValueError(
            method_code + " 的 ANALYSIS_MODE 設定不一致。"
        )

    return modes.pop()

def get_instrument_import_type(form_data):
    method_code = str(
        form_data.get("method_code", "") or ""
    ).strip().upper()

    instrument_id = str(
        form_data.get("instrument_id", "") or ""
    ).strip().upper()

    relation_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Instrument.csv"
    )

    if not os.path.exists(relation_file):
        raise ValueError("尚未匯入方法－儀器關聯資料。")

    matches = []

    with open(
        relation_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if (
                str(row.get("METHOD_CODE", "") or "")
                .strip().upper() == method_code
                and str(row.get("LABPARTID", "") or "")
                .strip().upper() == instrument_id
            ):
                matches.append(row)

    if len(matches) != 1:
        raise ValueError(
            "方法－儀器關聯必須有一筆符合的設定。"
        )

    import_type = str(
        matches[0].get("IMPORT_TYPE", "") or ""
    ).strip().upper()

    if not import_type:
        raise ValueError(
            "此方法與儀器尚未設定 IMPORT_TYPE。"
        )

    return import_type

def load_basic_info_data(form_data):
    method_code = str(
        form_data.get("method_code", "") or ""
    ).strip().upper()

    try:
        analysis_mode = get_method_analysis_mode(
            method_code
        )
    except ValueError as exc:
        return {}, None, str(exc)

    if analysis_mode == "SINGLE":
        return load_control_and_method_data(form_data)

    method_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    # 基本資料階段只取方法共用設定，
    common_fields = (
        "DATA_ENTRY_MODE",
    )

    method_rows = []

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(
                row.get("ACTIVE", "") or ""
            ).strip().upper() != "Y":
                continue

            if str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper() == method_code:
                method_rows.append(row)

    method_data = {
        "METHOD_CODE": method_code,
        "ANALYSIS_MODE": "MULTI_ANALYTE",
    }

    for field in common_fields:
        values = {
            str(row.get(field, "") or "").strip().upper()
            for row in method_rows
        }

        if len(values) != 1:
            return (
                {},
                None,
                method_code + " 的 " + field + " 設定不一致。"
            )

        method_data[field] = values.pop()

    try:
        method_data["IMPORT_TYPE"] = (
            get_instrument_import_type(form_data)
        )
    except ValueError as exc:
        return {}, None, str(exc)

    return {}, method_data, None

def load_control_and_method_data(form_data):

    control_data = {}
    method_data = None

    ctrl_year = form_data.get(
        "ctrl_year",
        ""
    ).strip()

    category = form_data.get(
        "category",
        ""
    ).strip()

    exam_name = form_data.get(
        "exam_name",
        ""
    ).strip()

    method_code = form_data.get(
        "method_code",
        ""
    ).strip()

    instrument_id = form_data.get(
        "instrument_id",
        ""
    ).strip()

    selected_exam_no = form_data.get(
    "selected_exam_no",
    ""
).strip()

    if not ctrl_year:
        return {}, None, "請選擇管制年度。"

    if not exam_name:
        return {}, None, "請輸入測項名稱。"

    if not method_code:
        return {}, None, "請輸入分析方法。"

    # ========================================
    # 先載入方法設定
    # 方法設定是分析流程必要資料，
    # 不應依賴是否存在年度管制圖
    # ========================================
    method_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(
        method_file
    ):

        return (
            {},
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

        method_reader = csv.DictReader(
            f
        )

        for method_row in method_reader:

            if (
                method_row.get(
                    "ACTIVE",
                    ""
                )
                .strip()
                .upper()
                != "Y"
            ):
                continue

            if (
                method_row.get(
                    "METHOD_CODE",
                    ""
                )
                .strip()
                .upper()
                != method_code.upper()
            ):
                continue

            method_matches.append(
                method_row
            )

    if len(method_matches) == 0:

        return (
            {},
            None,
            "查無對應的方法設定。"
        )

    method_data = method_matches[0]

    method_exam_no = (
        method_data.get(
            "EXAMNO",
            ""
        )
        .strip()
    )

    method_category = str(
        method_data.get("CATEGORY_CODE", "")
        or ""
    ).strip().upper()

    effective_exam_no = selected_exam_no

    if (
        not effective_exam_no
        and method_category == category.upper()
    ):
        effective_exam_no = method_exam_no

    # ========================================
    # 再載入年度管制資料
    # 年度檔案本身不存在仍視為設定錯誤
    # ========================================
    csv_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Control_"
        + ctrl_year
        + ".csv"
    )

    if not os.path.exists(
        csv_file
    ):

        return (
            {},
            method_data,
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

        reader = csv.DictReader(
            f
        )

        for row in reader:

            if (
                row.get(
                    "CTRL_YEAR",
                    ""
                ).strip()
                != ctrl_year
            ):
                continue

            if (
                row.get(
                    "CATEGORY_CODE",
                    ""
                )
                .strip()
                .upper()
                != category.upper()
            ):
                continue

            row_exam_name = (
                row.get(
                    "EXAMNAME",
                    ""
                )
                .strip()
            )

            row_exam_alias = (
                row.get(
                    "EXALIAS",
                    ""
                )
                .strip()
            )

            row_exam_no = (
                row.get(
                    "EXAMNO",
                    ""
                )
                .strip()
            )

            if effective_exam_no:

                if (
                    row_exam_no
                    != effective_exam_no
                ):
                    continue

            else:

                if (
                    exam_name
                    != row_exam_name
                    and exam_name
                    != row_exam_alias
                ):
                    continue

            if (
                row.get(
                    "EM_NUM",
                    ""
                )
                .strip()
                .upper()
                != method_code.upper()
            ):
                continue

            base_matches.append(
                row
            )

    # ========================================
    # 找不到該測項年度管制資料
    # → 視為「無管制圖項目」
    # → 不阻止進入分析頁
    # ========================================
    if len(base_matches) == 0:

        return (
            {},
            method_data,
            None
        )

    # ========================================
    # 有管制資料時才套用儀器適用規則
    #
    # 1. 儀器專屬資料優先
    # 2. 沒有專屬資料時使用共用資料
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

            specific_matches.append(row)

    if (
        instrument_id and specific_matches
    ):

        matches = specific_matches

    else:

        matches = common_matches

    # 已確認這個項目有管制資料，
    # 但選定儀器沒有適用資料，
    # 這仍屬於設定問題，不可當成無管制項目
    if len(matches) == 0:

        if instrument_id:

            return (
                {},
                method_data,
                "此項目已有年度管制資料，"
                "但查無此儀器專屬或共用的管制資料。"
            )

        return (
            {},
            method_data,
            "此項目已有年度管制資料，"
            "但查無共用管制資料。"
        )

    if len(matches) > 1:

        # 使用者已指定測項代碼時，
        # 依 EXAMNO 精確鎖定
        if selected_exam_no:

            selected_matches = []

            for row in matches:

                if (
                    row.get(
                        "EXAMNO",
                        ""
                    )
                    .strip()
                    == selected_exam_no
                ):

                    selected_matches.append(
                        row
                    )

            if len(selected_matches) == 1:

                control_data = (
                    selected_matches[0]
                )

                return (
                    control_data,
                    method_data,
                    None
                )

        # 尚未選擇，回傳候選資料給 Basic Info
        return (
            {
                "_multiple_matches":
                    matches
            },
            method_data,
            "找到多筆符合的年度管制資料，"
            "請選擇測項代碼。"
        )

    control_data = matches[0]

    return (
        control_data,
        method_data,
        None
    )

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

register_performance_history_route(login_required)

app.register_blueprint(performance_history_bp)

# 保留舊 endpoint，供現有模板的 url_for() 使用
app.add_url_rule(
    "/performance-history",
    endpoint="performance_history",
    view_func=app.view_functions[
        "performance_history_bp.performance_history"
    ],
    methods=["GET"],
)

# 保留 Performance Trend 舊 endpoint
app.add_url_rule(
    "/analysis/performance-trend",
    endpoint="analysis_performance_trend",
    view_func=app.view_functions[
        "performance_history_bp.analysis_performance_trend"
    ],
    methods=["GET"],
)

# Analysis Record Blueprint
app.register_blueprint(analysis_record_bp)

app.register_blueprint(control_import_bp)

app.register_blueprint(method_settings_import_bp)

app.register_blueprint(report_settings_import_bp)

app.register_blueprint(instrument_settings_import_bp)

app.register_blueprint(method_instrument_import_bp)

app.register_blueprint(icp_analyte_import_bp)

app.register_blueprint(performance_control_import_bp)

app.register_blueprint(home_bp)

app.add_url_rule(
    "/",
    endpoint="home",
    view_func=app.view_functions["home_bp.home"],
    methods=["GET"]
)


app.add_url_rule(
    "/performance-control-import",
    endpoint="performance_control_import",
    view_func=app.view_functions[
        "performance_control_import_bp.performance_control_import"
    ],
    methods=["POST"]
)


app.add_url_rule(
    "/icp-analyte-import",
    endpoint="icp_analyte_import",
    view_func=app.view_functions[
        "icp_analyte_import_bp.icp_analyte_import"
    ],
    methods=["POST"]
)


app.add_url_rule(
    "/method-instrument-import",
    endpoint="method_instrument_import",
    view_func=app.view_functions[
        "method_instrument_import_bp.method_instrument_import"
    ],
    methods=["POST"]
)


app.add_url_rule(
    "/instrument-settings-import",
    endpoint="instrument_settings_import",
    view_func=app.view_functions[
        "instrument_settings_import_bp.instrument_settings_import"
    ],
    methods=["POST"]
)


app.add_url_rule(
    "/report-settings-import",
    endpoint="report_settings_import",
    view_func=app.view_functions[
        "report_settings_import_bp.report_settings_import"
    ],
    methods=["POST"]
)


app.add_url_rule(
    "/method-settings-import",
    endpoint="method_settings_import",
    view_func=app.view_functions[
        "method_settings_import_bp.method_settings_import"
    ],
    methods=["POST"]
)


# 保留舊 endpoint，相容既有 url_for 呼叫
app.add_url_rule(
    "/analysis-delete-history",
    endpoint="analysis_delete_history",
    view_func=app.view_functions[
        "analysis_record_bp.analysis_delete_history"
    ],
    methods=["GET"],
)

# 保留審核通過舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>/approve",
    endpoint="approve_analysis_record",
    view_func=app.view_functions[
        "analysis_record_bp.approve_analysis_record"
    ],
    methods=["POST"],
)

# 保留退回修正舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>/reject",
    endpoint="reject_analysis_record",
    view_func=app.view_functions[
        "analysis_record_bp.reject_analysis_record"
    ],
    methods=["POST"],
)

# 保留已審核紀錄再次退回的舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>/reopen",
    endpoint="reopen_approved_analysis_record",
    view_func=app.view_functions[
        "analysis_record_bp.reopen_approved_analysis_record"
    ],
    methods=["POST"],
)

# 保留分析紀錄明細舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>",
    endpoint="analysis_record_detail",
    view_func=app.view_functions[
        "analysis_record_bp.analysis_record_detail"
    ],
    methods=["GET"],
)

# 保留正式分析紀錄 PDF 匯出舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>/export-pdf",
    endpoint="export_analysis_record_pdf",
    view_func=app.view_functions[
        "analysis_record_bp.export_analysis_record_pdf"
    ],
    methods=["GET"],
)

# 保留正式分析紀錄 LIMS 匯出舊 endpoint
app.add_url_rule(
    "/analysis-records/<analysis_id>/export-lims",
    endpoint="export_analysis_record_lims",
    view_func=app.view_functions[
        "analysis_record_bp.export_analysis_record_lims"
    ],
    methods=["GET"],
)

# 保留正式分析紀錄列表的舊 endpoint
app.add_url_rule(
    "/analysis-records",
    endpoint="analysis_records",
    view_func=app.view_functions[
        "analysis_record_bp.analysis_records"
    ],
    methods=["GET"],
)

# ========================================
# Analysis Record Resume Endpoint 相容
# ========================================

app.add_url_rule(
    "/analysis-records/<analysis_id>/resume",
    endpoint="resume_analysis_record",
    view_func=app.view_functions[
        "analysis_record_bp.resume_analysis_record"
    ],
    methods=["POST"]
)

# ========================================
# Analysis Record Delete Endpoint 相容
# ========================================

app.add_url_rule(
    "/analysis-records/<analysis_id>/delete",
    endpoint="delete_analysis_record",
    view_func=app.view_functions[
        "analysis_record_bp.delete_analysis_record"
    ],
    methods=["POST"]
)

# ========================================
# Control Import Endpoint 相容
# ========================================

app.add_url_rule(
    "/control-import",
    endpoint="control_import",
    view_func=app.view_functions[
        "control_import_bp.control_import"
    ],
    methods=["GET", "POST"]
)

def load_method_analysis_modes():
    method_file = os.path.join(
        app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(method_file):
        return {}

    method_modes = {}

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(
                row.get("ACTIVE", "") or ""
            ).strip().upper() != "Y":
                continue

            method_code = str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper()

            mode = str(
                row.get("ANALYSIS_MODE", "") or ""
            ).strip().upper() or "SINGLE"

            if method_code:
                method_modes.setdefault(
                    method_code, set()
                ).add(mode)

    return {
        method_code: next(iter(modes))
        for method_code, modes in method_modes.items()
        if len(modes) == 1
        and modes <= {"SINGLE", "MULTI_ANALYTE"}
    }

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
    "selected_exam_no": "",
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

            "selected_exam_no": request.form.get(
                "selected_exam_no",
                ""
            ).strip(),

            "wavelength": request.form.get(
                "wavelength",
                ""
            ).strip(),
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
            ) = load_basic_info_data(
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
            next_action == "import_icp"
            and method_data
            and not error_message
            and method_data.get("ANALYSIS_MODE")
            == "MULTI_ANALYTE"
            and form_data.get("instrument_id")
        ):
            return redirect(
                url_for("analysis_icp_import")
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

        if (
            next_action == "import_w330"
            and method_data
            and form_data.get(
                "instrument_id"
            )
        ):

            return redirect(
                url_for(
                    "analysis_w330"
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
        method_analysis_modes=load_method_analysis_modes(),
        active_page="analysis_basic"
    )

@app.route(
    "/analysis/icp/import",
    methods=["GET", "POST"]
)
@login_required
def analysis_icp_import():
    form_data = session.get("basic_info_form") or {}

    if not form_data.get("instrument_id"):
        return redirect(url_for("basic_info"))

    _, method_data, error_message = (
        load_basic_info_data(form_data)
    )

    if (
        error_message
        or not method_data
        or method_data.get("ANALYSIS_MODE")
        != "MULTI_ANALYTE"
    ):
        return redirect(url_for("basic_info"))

    upload_error = None
    upload_message = None

    preview_rows = []
    parsed_row_count = 0

    channel_options = []
    selected_channel = request.args.get(
        "channel", ""
    ).strip()
    selected_role = request.args.get(
        "role", ""
    ).strip().upper()
    filtered_row_count = 0

    all_candidate_groups = []
    candidate_groups = []
    lims_match_groups = []
    lims_lookup_error = None
    icp_lims_matches = []

    # ========================================
    # ICP 已暫存工作清單
    # 僅查詢工作基本資訊，不載入 PDF JSON
    # ========================================
    icp_saved_works = list_icp_work_states(
        method_code=form_data.get("method_code", "")
    )

    if request.method == "GET":
        work_key = session.get("icp_work_key")
        saved_work = (
            load_icp_work_state(work_key)
            if work_key else None
        )

        if (
            saved_work
            and saved_work.get("form_data") == form_data
            and saved_work.get("import_type")
            == method_data.get("IMPORT_TYPE")
        ):
            saved_rows = saved_work["parsed_data"]["rows"]
                        # ========================================
            # 建立完整候選量測分組
            # ========================================
            all_candidate_groups = build_sample_candidate_groups(
                saved_rows
            )

            # ========================================
            # 還原 SQLite 中已儲存的候選選擇
            # 單筆自動預選，多筆須人工指定
            # ========================================
            saved_selections = (
                saved_work.get("candidate_selections") or {}
            )

            all_candidate_groups = build_icp_candidate_selections(
                all_candidate_groups,
                saved_selections
            )

            # 畫面篩選使用完整資料的另一份列表
            candidate_groups = all_candidate_groups
            parsed_row_count = len(saved_rows)

            channels = sorted({
                (row["element"], row["wavelength"])
                for row in saved_rows
            })

            channel_options = [
                {
                    "value": element + "|" + wavelength,
                    "label": element + "／" + wavelength + " nm",
                }
                for element, wavelength in channels
            ]

            filtered_rows = saved_rows

            if selected_channel:
                filtered_rows = [
                    row for row in filtered_rows
                    if (
                        row["element"] + "|" + row["wavelength"]
                    ) == selected_channel
                ]

            if selected_role:
                filtered_rows = [
                    row for row in filtered_rows
                    if row.get("role") == selected_role
                ]

            if selected_channel:
                candidate_groups = [
                    group for group in candidate_groups
                    if (
                        group["element"]
                        + "|"
                        + group["wavelength"]
                    ) == selected_channel
                ]

            filtered_row_count = len(filtered_rows)
            preview_rows = filtered_rows[:400]
            upload_message = saved_work["upload_message"]

        elif work_key:
            session.pop("icp_work_key", None)
            upload_message = (
                "原暫存已失效或基本資料已變更，"
                "請重新上傳 PDF。"
            )

    if request.method == "POST":
        uploaded_file = request.files.get("icp_pdf_file")

        if (
            uploaded_file is None
            or not uploaded_file.filename
        ):
            upload_error = "請選擇 ICP PDF 檔案。"

        elif not uploaded_file.filename.lower().endswith(
            ".pdf"
        ):
            upload_error = "只能上傳 PDF 檔案。"

        else:
            header = uploaded_file.stream.read(1024)
            uploaded_file.stream.seek(0)

            if b"%PDF-" not in header:
                upload_error = "檔案內容不是可辨識的 PDF。"
            else:
                import_type = method_data.get(
                    "IMPORT_TYPE", ""
                )

                if import_type != "ICP5800_PDF":
                    upload_error = (
                        "目前僅完成 ICP5800 解析程序；"
                        "ICP5110 解析程序尚未建置。"
                    )
                else:
                    try:
                        parsed_data = parse_icp5800_pdf(
                            uploaded_file.stream
                        )

                        rows = parsed_data["rows"]

                        parsed_row_count = len(rows)
                        preview_rows = rows[:400]

                        elements = sorted({
                            row["element"]
                            for row in rows
                        })

                        channels = {
                            (
                                row["element"],
                                row["wavelength"]
                            )
                            for row in rows
                        }

                        upload_message = (
                            "PDF 解析成功："
                            + str(parsed_data["page_count"])
                            + " 頁、"
                            + str(len(rows))
                            + " 筆量測資料、"
                            + str(len(elements))
                            + " 個金屬、"
                            + str(len(channels))
                            + " 組金屬／波長。金屬："
                            + "、".join(elements)
                            + "。尚未進行 LIMS 篩選或儲存。"
                        )

                        work_key = (
                            "ICP_IMPORT_" + uuid4().hex
                        )

                        save_icp_work_state(
                            work_key,
                            {
                                "form_data": dict(form_data),
                                "import_type": import_type,
                                "source_filename": (
                                    uploaded_file.filename
                                ),
                                "parsed_data": parsed_data,
                                "upload_message": (
                                    upload_message.replace(
                                        "尚未進行 LIMS 篩選或儲存。",
                                        "已暫存解析結果，"
                                        "尚未進行 LIMS 篩選或正式儲存。"
                                    )
                                ),
                            }
                        )

                        session["icp_work_key"] = work_key

                        return redirect(
                            url_for("analysis_icp_import")
                        )

                    except ValueError as exc:
                        upload_error = str(exc)

                    except Exception:
                        app.logger.exception(
                            "ICP5800 PDF 解析失敗"
                        )
                        upload_error = (
                            "PDF 讀取失敗，"
                            "請查看伺服器錯誤紀錄。"
                        )

    # ICP 適用測項對照表
    icp_analyte_map = {}

    try:
        icp_map_path = os.path.join(
            app.root_path,
            "data",
            "Phyon_ICP_Analyte_Map.csv"
        )

        if all_candidate_groups:
           icp_analyte_map = load_icp_analyte_map(
           icp_map_path
        )

    except Exception:
        app.logger.exception(
            "ICP 適用測項對照表讀取失敗"
        )

        lims_lookup_error = (
            "ICP 適用測項對照表無法讀取，"
            "目前無法確認測項配對。"
        )

    # ========================================
    # ICP LIMS 委測項目查詢
    # 不影響原始 PDF 與候選量測資料
    # ========================================
    keepids = sorted({
    str(group.get("keepid") or "").strip()
    for group in all_candidate_groups
    if str(group.get("keepid") or "").strip()
       })   

    for keepid in keepids:
        try:
            lims_rows = get_lims_sample_analysis(keepid)

            matched_result = match_lims_icp_analytes(
                lims_rows,
                icp_analyte_map
            )

            lims_match_groups.append({
                "keepid": keepid,
                "found": bool(lims_rows),
                "analysis_rows": lims_rows,
                "matched_rows": matched_result["matched_rows"],
                "unmatched_rows": matched_result["unmatched_rows"],
            })

        except Exception:
            app.logger.exception(
                "ICP LIMS 委測查詢失敗：KEEPID=%s",
                keepid
            )

            lims_lookup_error = (
                "部分樣品的 LIMS 委測資料查詢失敗，"
                "請確認資料庫連線。"
            )

            lims_match_groups.append({
                "keepid": keepid,
                "found": False,
                "analysis_rows": [],
                "lookup_error": True,
            })

    # ========================================
    # ICP PDF 與 LIMS 委測項目配對
    # ========================================
    if all_candidate_groups and not lims_lookup_error:

        icp_lims_matches = build_icp_lims_matches(
        all_candidate_groups,
        lims_match_groups,
        form_data.get("method_code", "")
    )

        # ========================================
        # 還原使用者已暫存的委測決定
        # ========================================
        work_key = session.get("icp_work_key")

        saved_work = (
            load_icp_work_state(work_key)
            if work_key else None
        )

        saved_decisions = (
            saved_work.get("lims_decisions") or {}
            if saved_work
            else {}
        )

        for item in icp_lims_matches:

            decision_key = "{}|{}".format(
                str(item.get("keepid") or "").strip().upper(),
                str(item.get("examno") or "").strip().upper()
            )

            saved = saved_decisions.get(decision_key)

            if not saved:
                continue

            saved_decision = str(
                saved.get("decision") or ""
            ).strip().upper()

            # 重新驗證目前的配對狀態
            status = item.get("status")

            if status == "METHOD_MATCHED":
                allowed = {"ACCEPT", "REJECT", "PENDING"}

            elif status == "CROSS_METHOD_REVIEW":
                allowed = {"REJECT", "PENDING"}

            else:
                allowed = {"REJECT"}

            if saved_decision in allowed:
                item["user_decision"] = saved_decision
                item["user_reason"] = str(
                    saved.get("reason") or ""
                )

    return render_template(
        "methods/icp_import.html",
        icp_saved_works=icp_saved_works,
        form_data=form_data,
        method_data=method_data,
        upload_error=upload_error,
        upload_message=upload_message,
        preview_rows=preview_rows,
        parsed_row_count=parsed_row_count,
        channel_options=channel_options,
        selected_channel=selected_channel,
        selected_role=selected_role,
        filtered_row_count=filtered_row_count,
        candidate_groups=candidate_groups,
        lims_match_groups=lims_match_groups,
        lims_lookup_error=lims_lookup_error,
        icp_lims_matches=icp_lims_matches,
        active_page="analysis_basic"
    )

# ========================================
# ICP LIMS 委測項目使用者決定
# ========================================
@app.route(
    "/analysis/icp/lims-decision",
    methods=["POST"]
)
@login_required
def save_icp_lims_decision():

    work_key = session.get("icp_work_key")
    saved_work = (
        load_icp_work_state(work_key)
        if work_key else None
    )

    if not saved_work:
        return "ICP 暫存資料不存在，請重新匯入 PDF。", 400

    form_data = session.get("basic_info_form") or {}

    _, method_data, error_message = load_basic_info_data(
        form_data
    )

    if (
        error_message
        or not method_data
        or method_data.get("ANALYSIS_MODE") != "MULTI_ANALYTE"
        or saved_work.get("form_data") != form_data
        or saved_work.get("import_type")
        != method_data.get("IMPORT_TYPE")
    ):
        return "分析基本資料已變更，請重新確認。", 400

    # ========================================
    # 1. 讀取批次提交的使用者決定
    #
    # 前端欄位格式：
    # decisions[KEEPID|EXAMNO] = ACCEPT / PENDING / REJECT
    # ========================================
    submitted = {}

    for field_name, field_value in request.form.items():

        if not (
            field_name.startswith("decisions[")
            and field_name.endswith("]")
        ):
            continue

        decision_key = field_name[
            len("decisions["):-1
        ].strip().upper()

        parts = decision_key.split("|")

        if len(parts) != 2:
            return "委測項目識別格式不正確。", 400

        keepid, examno = parts

        if not keepid or not examno:
            return "委測項目識別不得為空白。", 400

        decision = str(
            field_value or ""
        ).strip().upper()

        if decision not in (
            "ACCEPT",
            "PENDING",
            "REJECT"
        ):
            return "使用者決定不合法。", 400

        submitted[decision_key] = decision

    if not submitted:
        return "沒有收到任何委測項目決定。", 400

    # ========================================
    # 2. 重新建立完整 PDF 候選資料
    # 不受目前畫面篩選條件影響
    # ========================================
    parsed_data = saved_work.get("parsed_data") or {}
    parsed_rows = parsed_data.get("rows") or []

    all_candidate_groups = build_sample_candidate_groups(
        parsed_rows
    )

    if not all_candidate_groups:
        return "目前沒有可供配對的 ICP 候選資料。", 400

    all_keepids = sorted({
        str(group.get("keepid") or "").strip().upper()
        for group in all_candidate_groups
        if group.get("keepid")
    })

    # ========================================
    # 3. 重新查詢 LIMS 委測項目
    # ========================================
    try:
        analyte_map = load_icp_analyte_map(
            os.path.join(
                app.root_path,
                "data",
                "Phyon_ICP_Analyte_Map.csv"
            )
        )

        lims_match_groups = []

        for keepid in all_keepids:

            lims_rows = get_lims_sample_analysis(
                keepid
            )

            if not lims_rows:
                return (
                    "LIMS 查無樣品 {} 的委測資料，"
                    "本次未儲存任何決定。".format(keepid),
                    400
                )

            matched_result = match_lims_icp_analytes(
                lims_rows,
                analyte_map
            )

            lims_match_groups.append({
                "keepid": keepid,
                "matched_rows": (
                    matched_result["matched_rows"]
                ),
            })

        matches = build_icp_lims_matches(
            all_candidate_groups,
            lims_match_groups,
            form_data.get("method_code", "")
        )

    except Exception:
        app.logger.exception(
            "ICP 批次委測決定驗證失敗"
        )
        return (
            "無法重新驗證 ICP PDF 與 LIMS 委測資料。",
            503
        )

    # ========================================
    # 4. 建立後端可信任的配對索引
    # ========================================
    valid_matches = {}

    for item in matches:

        keepid = str(
            item.get("keepid") or ""
        ).strip().upper()

        examno = str(
            item.get("examno") or ""
        ).strip().upper()

        if not examno:
            continue

        key = "{}|{}".format(
            keepid, examno
        )

        if key in valid_matches:
            return (
                "發現重複的 LIMS 委測識別，"
                "本次未儲存任何決定。",
                400
            )

        valid_matches[key] = item

    # ========================================
    # 5. 驗證所有提交資料
    # 任一筆不合法，整批拒絕
    # ========================================
    for decision_key, decision in submitted.items():

        target = valid_matches.get(
            decision_key
        )

        if target is None:
            return (
                "委測項目 {} 不存在於目前配對資料，"
                "本次未儲存任何決定。".format(
                    decision_key
                ),
                400
            )

        status = target.get("status")

        if status == "METHOD_MATCHED":
            allowed = {
                "ACCEPT",
                "PENDING",
                "REJECT"
            }

        elif status == "CROSS_METHOD_REVIEW":
            allowed = {
                "PENDING",
                "REJECT"
            }

        else:
            allowed = {
                "REJECT"
            }

        if decision not in allowed:
            return (
                "委測項目 {} 的決定不符合配對限制，"
                "本次未儲存任何決定。".format(
                    decision_key
                ),
                400
            )

    # ========================================
    # 6. 驗證舊有暫存決定
    # 防止未提交的舊狀態繞過限制
    # ========================================
    old_decisions = (
        saved_work.get("lims_decisions") or {}
    )

    if not isinstance(old_decisions, dict):
        return "既有委測決定資料格式異常。", 400

    new_decisions = {}

    for key, value in old_decisions.items():

        if key not in valid_matches:
            continue

        if not isinstance(value, dict):
            continue

        decision = str(
            value.get("decision") or ""
        ).strip().upper()

        status = valid_matches[key].get("status")

        if status == "METHOD_MATCHED":
            allowed = {"ACCEPT", "PENDING", "REJECT"}
        elif status == "CROSS_METHOD_REVIEW":
            allowed = {"PENDING", "REJECT"}
        else:
            allowed = {"REJECT"}

        if decision in allowed:
            new_decisions[key] = {
                "decision": decision,
                "reason": "",
            }

    # ========================================
    # 7. 套用本次所有使用者決定
    # ========================================
    for key, decision in submitted.items():

        new_decisions[key] = {
            "decision": decision,
            "reason": "",
        }

    # ========================================
    # 8. 通過驗證後一次寫入 SQLite
    # ========================================

    # 從原有工作狀態建立新資料，
    # 不直接修改原本的 parsed_data。
    updated_work = dict(saved_work)

    updated_work["lims_decisions"] = new_decisions

    try:
        saved_ok = save_icp_work_state(
            work_key,
            updated_work
        )

    except Exception:
        app.logger.exception(
            "ICP LIMS 批次決定寫入 SQLite 失敗"
        )
        return (
            "ICP 批次決定儲存失敗，請稍後重試。",
            500
        )

    if not saved_ok:
        return "ICP 批次決定儲存失敗。", 500

    return redirect(
        url_for(
            "analysis_icp_import",
            tab="lims"
        )
    )

# ========================================
# ICP 候選量測：整批儲存選取結果
# ========================================
@app.route(
    "/analysis/icp/candidate-selection",
    methods=["POST"]
)
@login_required
def save_icp_candidate_selection():

    work_key = session.get("icp_work_key")

    saved_work = (
        load_icp_work_state(work_key)
        if work_key else None
    )

    if not saved_work:
        return "ICP 工作不存在，請重新開啟。", 400

    form_data = session.get("basic_info_form") or {}

    _, method_data, error_message = load_basic_info_data(
        form_data
    )

    if (
        error_message
        or not method_data
        or method_data.get("ANALYSIS_MODE") != "MULTI_ANALYTE"
        or saved_work.get("form_data") != form_data
        or saved_work.get("import_type")
        != method_data.get("IMPORT_TYPE")
    ):
        return "分析基本資料已變更，請重新確認。", 400

    # 1. 從已保存的 PDF 重新建立完整候選分組
    parsed_rows = (
        (saved_work.get("parsed_data") or {}).get("rows")
        or []
    )

    groups = build_icp_candidate_selections(
        build_sample_candidate_groups(parsed_rows)
    )

    if not groups:
        return "沒有可選取的候選量測。", 400

    valid_groups = {}

    for group in groups:
        key = group["selection_key"]

        if key in valid_groups:
            return "候選量測分組識別重複。", 400

        valid_groups[key] = group

    # 2. 讀取本次提交的選取結果
    submitted = {}

    for field_name in request.form.keys():

        if not (
            field_name.startswith("selections[")
            and field_name.endswith("]")
        ):
            continue

        # 防止同一欄位名稱重複提交
        values = request.form.getlist(field_name)

        if len(values) != 1:
            return "候選量測欄位重複。", 400

        key = field_name[len("selections["):-1]

        group = valid_groups.get(key)

        if group is None:
            return "候選量測群組不存在。", 400

        candidates = group.get("candidates") or []

        if len(candidates) <= 1:
            return "單筆候選不需要人工選取。", 400

        value = str(values[0] or "").strip()

        if not value:
            # 空白代表維持尚未選擇或清除舊選擇
            submitted[key] = None
            continue

        matches = [
            candidate
            for candidate in candidates
            if str(candidate.get("sequence")) == value
        ]

        if len(matches) != 1:
            return "選取的候選量測不存在或不唯一。", 400

        submitted[key] = matches[0]["sequence"]

    if not submitted:
        return "沒有收到候選量測選取資料。", 400

    # 3. 保留其他未顯示群組的有效選擇
    old_selections = (
        saved_work.get("candidate_selections") or {}
    )

    if not isinstance(old_selections, dict):
        return "原有候選選取資料格式錯誤。", 400

    new_selections = {}

    for key, value in old_selections.items():

        group = valid_groups.get(key)

        if group is None or not isinstance(value, dict):
            continue

        candidates = group.get("candidates") or []

        if len(candidates) <= 1:
            continue

        sequence = value.get("sequence")

        if sum(
            str(candidate.get("sequence")) == str(sequence)
            for candidate in candidates
        ) == 1:
            new_selections[key] = {
                "sequence": sequence
            }

    # 4. 套用本次選擇
    for key, sequence in submitted.items():

        if sequence is None:
            new_selections.pop(key, None)
        else:
            new_selections[key] = {
                "sequence": sequence
            }

    # 5. 通過全部驗證後一次寫入 SQLite
    updated_work = dict(saved_work)

    updated_work["candidate_selections"] = new_selections

    try:
        save_icp_work_state(work_key, updated_work)

    except Exception:
        app.logger.exception(
            "ICP 候選倍數批次儲存失敗"
        )
        return "候選倍數儲存失敗。", 500

    return redirect(
        url_for(
            "analysis_icp_import",
            tab="candidates"
        )
    )

# ========================================
# ICP：開啟已暫存工作
# ========================================
@app.route(
    "/analysis/icp/open-work",
    methods=["POST"]
)
@login_required
def open_icp_saved_work():

    work_key = str(
        request.form.get("work_key") or ""
    ).strip()

    if not work_key.startswith("ICP_IMPORT_"):
        return "ICP 工作識別格式不正確。", 400

    saved_work = load_icp_work_state(work_key)

    if not saved_work:
        return "找不到指定的 ICP 工作。", 404

    saved_form_data = saved_work.get("form_data")

    if not isinstance(saved_form_data, dict):
        return "ICP 工作基本資料格式不正確。", 400

    if not (
        (saved_work.get("parsed_data") or {}).get("rows")
    ):
        return "ICP 工作缺少 PDF 解析資料。", 400

    # 恢復這份工作原本的分析基本資料，
    # 避免被目前畫面的其他分析方法影響。
    session["basic_info_form"] = dict(
        saved_form_data
    )

    session["icp_work_key"] = work_key

    return redirect(
        url_for(
            "analysis_icp_import",
            tab="candidates"
        )
    )

@app.route(
    "/analysis/manual",
    methods=["GET", "POST"]
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

    manual_rows = []
    error_message = None

    # ========================================
    # 手動資料送出
    # ========================================

    if request.method == "POST":

        try:

            row_count = int(
                request.form.get(
                    "row_count",
                    "0"
                )
            )

        except ValueError:

            row_count = 0

        if row_count < calibration_count:

            error_message = (
                "資料列數不可少於檢量線點數 "
                + str(calibration_count)
                + " 筆。"
            )

        preview_rows = []

        if error_message is None:

            for index in range(
                row_count
            ):

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
                        "signal_"
                        + str(index),
                        ""
                    )
                    .strip()
                )

                manual_rows.append(
                    {
                        "sample_id":
                            sample_id,

                        "signal":
                            signal_text
                    }
                )

                if not sample_id:

                    error_message = (
                        "第 "
                        + str(index + 1)
                        + " 筆資料尚未輸入樣品編號。"
                    )

                    break

                if not signal_text:

                    error_message = (
                        "第 "
                        + str(index + 1)
                        + " 筆資料尚未輸入訊號值。"
                    )

                    break

                try:

                    signal = float(
                        signal_text
                    )

                except ValueError:

                    error_message = (
                        "第 "
                        + str(index + 1)
                        + " 筆訊號值格式不正確。"
                    )

                    break

                preview_rows.append(
                    {
                        "sequence_no":
                            index + 1,

                        "sample_id":
                            sample_id,

                        "signal":
                            signal,

                        "analyte":
                            str(
                                method_data.get(
                                    "ANALYTE_DISPLAY",
                                    ""
                                )
                                or ""
                            ).strip(),

                        "wavelength":
                            None
                    }
                )

        # ========================================
        # 第一階段先支援 W434
        #
        # UI / 原始資料結構仍維持通用，
        # 後續其他方法再接各自 calculator。
        # ========================================

        if (
            error_message is None
            and preview_rows
        ):

            method_code = str(
                form_data.get(
                    "method_code",
                    ""
                )
                or ""
            ).strip().upper()

            supported_manual_methods = {
                 "W434",
                 "W341"
               }

            if method_code not in supported_manual_methods:

                  error_message = (
                     "目前此分析方法尚未支援"
                     "手動分析資料建立。"
            )

        if (
            error_message is None
            and preview_rows
        ):

            preview_rows = (
                classify_analysis_rows(
                    preview_rows,
                    method_data
                )
            )
             
            # ========================================
            # Manual 與 PDF Import 共用相同 Batch 邏輯
            # ========================================

            included_batches = []
            excluded_rows = []

            if control_data:

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

            (    
               calibration_rows,
               sample_qaqc_rows
               ) = split_analysis_rows(
            preview_rows
            )   

            try:

                calibration_result = (
                    calculate_calibration(
                        preview_rows
                    )
                )

            except ValueError as ex:

                error_message = (
                    "檢量線計算失敗："
                    + str(ex)
                )

        # ========================================
        # 檢量線成功
        # → 建立與匯入模式相同的 W434_CURRENT
        # ========================================

        if (
            error_message is None
            and preview_rows
            and calibration_result
        ):

            analysis_state_key = (
               get_analysis_state_key(
                method_code
              )
            )

            existing_state = (
              load_analysis_state(
                analysis_state_key
              )
              or {}
            )

            analysis_session_key = (
               get_analysis_session_key(
                  method_code
              )
            )

            formal_analysis_id = str(
                existing_state.get(
                    "formal_analysis_id",
                    ""
                )
                or session.get(
                    analysis_session_key,
                    ""
                )
                or ""
            ).strip()

            # ------------------------------------
            # 手動模式沒有儀器檔波長
            # 直接使用 Basic Info 的人工波長
            # ------------------------------------

            basic_wavelength_text = str(
                form_data.get(
                    "wavelength",
                    ""
                )
                or ""
            ).strip()

            confirmed_wavelength = None
            wavelength_warning = None

            if basic_wavelength_text:

                try:

                    confirmed_wavelength = float(
                        basic_wavelength_text
                    )

                except ValueError:

                    wavelength_warning = (
                        "基本資料的波長格式不正確："
                        + basic_wavelength_text
                    )

            else:

                wavelength_warning = (
                    "基本資料尚未填寫有效波長。"
                )

            # ------------------------------------
            # QDL
            # ------------------------------------

            qdl_value = None

            qdl_source = str(
                method_data.get(
                    "QDL_SOURCE",
                    ""
                )
                or ""
            ).strip().upper()

            qdl_multiplier_text = str(
                method_data.get(
                    "QDL_MULTIPLIER",
                    ""
                )
                or ""
            ).strip()

            if (
                qdl_source
                == "FIRST_NONZERO_CALIBRATION_X"
            ):

                first_nonzero_x = None

                for row in calibration_rows:

                    x_value = row.get(
                        "calibration_x"
                    )

                    if (
                        x_value is not None
                        and x_value > 0
                    ):

                        first_nonzero_x = (
                            x_value
                        )

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

            # ------------------------------------
            # 樣品 / QAQC 預設欄位
            # ------------------------------------

            spike_field_by_role = {
              "ICV": "ICV_SPIKE_CONC",
              "QC": "QC_SPIKE_CONC",
              "CCV": "CCV_SPIKE_CONC",
              "MS": "MS_SPIKE_CONC",
              "MSD": "MS_SPIKE_CONC"
            }

            (
              sample_volume_default,
              final_volume_default
               ) = get_method_volume_defaults(
              method_data
            )

            for row in sample_qaqc_rows:

                row[
                    "sample_volume"
                ] = sample_volume_default

                row[
                    "final_volume"
                ] = final_volume_default

                row[
                    "dilution_factor"
                ] = 1

                role = str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip().upper()

                field_name = (
                    spike_field_by_role.get(
                        role
                    )
                )

                if field_name:

                    row[
                        "spike_concentration"
                    ] = (
                        method_data.get(
                            field_name,
                            ""
                        )
                        .strip()
                    )

                else:

                    row[
                        "spike_concentration"
                    ] = ""  

                row[
                    "remark"
                ] = ""

                row[
                    "is_excluded"
                ] = False

                row[
                    "exclusion_reason"
                ] = ""

            sample_qaqc_rows = (
                recalculate_sample_rows(
                    rows=sample_qaqc_rows,
                    calibration_result=calibration_result,
                    calculate_concentration=
                        calculate_sample_concentration
                )
            )

            included_batches = (
                 sync_sample_rows_to_batches(
                 sample_rows=sample_qaqc_rows,
                 included_batches=included_batches
                )
            )

          
            # ========================================
            # Manual QA/QC 檢核
            # ========================================

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

         
            save_analysis_state(
                analysis_state_key,
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
                        qaqc_results,

                    "qdl_value":
                        qdl_value,

                    "instrument_analyte":
                        "",

                    "instrument_wavelength":
                        None,

                    "confirmed_wavelength":
                        confirmed_wavelength,

                    "wavelength_warning":
                        wavelength_warning,

                    # 手動輸入沒有來源檔案
                    # 正式儲存時因此會辨識為 MANUAL
                    "uploaded_filename":
                        None,

                    "formal_analysis_id":
                        formal_analysis_id
                }
            )

            return redirect(
                url_for(
                    "analysis_w43401",
                    saved="1"
                )
            )

    # ========================================
    # GET 或驗證失敗
    # ========================================

    if not manual_rows:

        manual_rows = [
            {
                "sample_id": "",
                "signal": ""
            }
            for _ in range(
                calibration_count
            )
        ]

    return render_template(
        "analysis/manual_entry.html",
        active_page="analysis_method",
        form_data=form_data,
        control_data=control_data,
        method_data=method_data,
        calibration_count=calibration_count,
        manual_rows=manual_rows,
        error_message=error_message
    )

def separate_toc_tic_rows(rows):
    analysis_rows = []
    tic_rows = []

    for row in rows:
        sample_id = str(
            row.get("sample_id", "") or ""
        ).strip().upper()

        if sample_id in {"TIC", "TIC-SPK"}:
            tic_row = dict(row)

            tic_row["role"] = (
                "TIC"
                if sample_id == "TIC"
                else "TIC_SPK"
            )

            tic_row["spike_concentration"] = (
                3.0
                if sample_id == "TIC-SPK"
                else None
            )

            tic_row["apply_volume_factor"] = False
            tic_row["sample_prep_factor"] = 1.0
            tic_row["dilution_factor"] = 1.0

            tic_rows.append(tic_row)
        else:
            analysis_rows.append(row)

    return analysis_rows, tic_rows

def calculate_toc_tic_result(tic_rows, calibration_result):
    result = {
        "removal_percent": None,
        "passed": None
    }

    if not tic_rows or not calibration_result:
        return result

    recalculate_sample_rows(
        rows=tic_rows,
        calibration_result=calibration_result,
        calculate_concentration=calculate_sample_concentration
    )

    tic = next(
        (row for row in tic_rows if row.get("role") == "TIC"),
        None
    )
    tic_spk = next(
        (row for row in tic_rows if row.get("role") == "TIC_SPK"),
        None
    )

    if tic is None or tic_spk is None:
        return result

    tic_conc = tic.get("measured_concentration")
    tic_spk_conc = tic_spk.get("measured_concentration")
    spike = tic_spk.get("spike_concentration")

    if tic_conc is None or tic_spk_conc is None or spike is None:
        return result

    spike = float(spike)

    if spike <= 0:
        return result

    removal_percent = (
        (spike + tic_conc - tic_spk_conc)
        / spike
        * 100.0
    )

    result["removal_percent"] = removal_percent
    result["passed"] = removal_percent > 90.0

    return result

def classify_analysis_rows(preview_rows, method_data):

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
            or (
                sample_id_upper.startswith("BK")
                and sample_id_upper[2:].isdigit()
            )
        ):
            role = "BK"

        elif (
            sample_id_upper == "QC"
            or sample_id_upper.startswith("QC-")
            or (
                sample_id_upper.startswith("QC")
                and sample_id_upper[2:].isdigit()
            )
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
            or (
                sample_id_upper.startswith("CCV")
                and sample_id_upper[3:].isdigit()
            )
            or sample_id_upper == "1CCV1"
        ):
            role = "CCV"

        elif (
            sample_id_upper.endswith("MSD")
            and detect_formal_sample_category(
                sample_id_upper[:-3]
            ) is not None
        ):
            role = "MSD"

        elif (
            sample_id_upper.endswith("DUP")
            and detect_formal_sample_category(
                sample_id_upper[:-3]
            ) is not None
        ):
            role = "DUP"

        elif (
            sample_id_upper.endswith("MS")
            and detect_formal_sample_category(
                sample_id_upper[:-2]
            ) is not None
        ):
            role = "MS"

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

def get_method_volume_defaults(
    method_data
):

    sample_volume = float(
        method_data.get(
            "SAMPLE_VOLUME_DEFAULT",
            ""
        )
    )

    final_volume = float(
        method_data.get(
            "FINAL_VOLUME_DEFAULT",
            ""
        )
    )

    return (
        sample_volume,
        final_volume
    )


def validate_qaqc_export_ready(
    qaqc_results,
    has_control_data=True
):

    # ========================================
    # 無管制圖項目
    # 不執行 QA/QC 管制判定，
    # 直接允許正式儲存 / 匯出
    # ========================================
    if not has_control_data:

        return (
            True,
            ""
        )

    # ========================================
    # 有管制圖，但尚未產生 QA/QC 判定
    # 仍然屬於不完整資料，不可放行
    # ========================================
    if not qaqc_results:

        return (
            False,
            "已有年度管制資料，"
            "但尚未完成 QA/QC 判定，"
            "不可匯出。"
        )

    invalid_batches = []

    for batch in qaqc_results:

        batch_no = str(
            batch.get(
                "batch_no",
                ""
            )
            or ""
        ).strip()

        batch_label = (
            "Batch "
            + batch_no
            if batch_no
            else "未識別批次"
        )

        batch_remark = str(
            batch.get(
                "batch_remark",
                ""
            )
            or ""
        ).strip()

        batch_invalid_items = []

        # ========================================
        # 3A：ICV / QC / CCV
        # ========================================
        for row in batch.get(
            "rows",
            []
        ):

            status = str(
                row.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                role = str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                sample_id = str(
                    row.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip()

                batch_invalid_items.append(
                    role
                    + (
                        " / "
                        + sample_id
                        if sample_id
                        else ""
                    )
                    + "："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 3B：重複分析精密度
        # ========================================
        precision = batch.get(
            "precision"
        )

        if precision:

            status = str(
                precision.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                batch_invalid_items.append(
                    "重複分析精密度："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 3C：MS / MSD 回收率
        # ========================================
        for row in batch.get(
            "spike_recovery",
            []
        ):

            status = str(
                row.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                role = str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                batch_invalid_items.append(
                    role
                    + " 回收率："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 此批次若有超限，
        # 必須有批次備註才可放行
        # ========================================
        if batch_invalid_items:

            if not batch_remark:

                invalid_batches.append(
                    batch_label
                    + " 尚有 QA/QC 超限，"
                    + "但未填寫批次備註：\n"
                    + "\n".join(
                        batch_invalid_items
                    )
                )

    if invalid_batches:

        return (
            False,
            "QA/QC 有超限批次尚未填寫備註，"
            "不可匯出：\n"
            + "\n".join(
                invalid_batches
            )
        )

    return (
        True,
        ""
    )

def redirect_metal_analysis_error(
    error_message,
    method_code
):

    analysis_state_key = (
        get_analysis_state_key(
            method_code
        )
    )

    analysis_state = (
        load_analysis_state(
            analysis_state_key
        )
    )

    analysis_endpoint = (
        get_analysis_page_endpoint(
            method_code
        )
    )

    redirect_args = {
        "error_message":
            error_message
    }

    if analysis_state:

        redirect_args[
            "saved"
        ] = "1"

    return redirect(
        url_for(
            analysis_endpoint,
            **redirect_args
        )
    )

@app.route(
    "/analysis/update-batch-remarks",
    methods=["POST"]
)
@login_required
def update_batch_remarks():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not method_code:

        return (
            "尚未找到目前分析方法。",
            400
        )

    analysis_state_key = (
        get_analysis_state_key(
            method_code
        )
    )

    analysis_state = (
        load_analysis_state(
            analysis_state_key
        )
        or {}
    )

    included_batches = (
        analysis_state.get(
            "included_batches",
            []
        )
    )

    qaqc_results = (
        analysis_state.get(
            "qaqc_results",
            []
        )
    )

    if not included_batches:

        return (
            "尚未找到分析批次資料。",
            400
        )

    remark_map = {}

    for batch in included_batches:

        batch_no = batch.get(
            "batch_no"
        )

        if batch_no is None:
            continue

        remark = (
            request.form.get(
                "batch_remark_"
                + str(batch_no),
                ""
            )
            .strip()
        )

        batch[
            "batch_remark"
        ] = remark

        remark_map[
            str(batch_no)
        ] = remark

    # QA/QC 顯示資料也同步帶入
    for batch in qaqc_results:

        batch_no = batch.get(
            "batch_no"
        )

        if batch_no is None:
            continue

        batch[
            "batch_remark"
        ] = remark_map.get(
            str(batch_no),
            ""
        )

    analysis_state[
        "included_batches"
    ] = included_batches

    analysis_state[
        "qaqc_results"
    ] = qaqc_results

    save_analysis_state(
        analysis_state_key,
        analysis_state
    )

    analysis_endpoint = (
       get_analysis_page_endpoint(
        method_code
       )
    )

    return redirect(
      url_for(
          analysis_endpoint,
          saved="1"
      )
    )

def split_analysis_rows(rows):

    calibration_rows = []
    sample_qaqc_rows = []

    for row in rows:

        if row.get("role") == "STANDARD":
            calibration_rows.append(row)
        else:
            sample_qaqc_rows.append(row)

    return calibration_rows, sample_qaqc_rows

@app.route(
    "/analysis/w330",
    methods=["GET", "POST"]
)
@login_required
def analysis_w330():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    if not form_data:

        return redirect(
            url_for(
                "basic_info"
            )
        )

    import_error = None
    uploaded_filename = None

    ra7000_data = None

    calibration_rows = []
    calibration_result = None
    sample_qaqc_rows = []
    included_batches = []
    control_data = None
    method_data = None
    load_error = None
    qdl_value = None
    qaqc_results = []
    prm_results = []
    sample_data_saved = False

    if form_data:

     (
        control_data,
        method_data,
        load_error
     ) = load_control_and_method_data(
        form_data
     )

    if (
    request.method == "GET"
    and request.args.get("saved") == "1"
):

      saved_state = load_analysis_state(
        "W330_CURRENT"
    )

      if saved_state:

        ra7000_data = saved_state.get(
            "ra7000_data"
             )

        calibration_rows = saved_state.get(
            "calibration_rows",
            []
        )

        calibration_result = saved_state.get(
            "calibration_result"
        )

        sample_qaqc_rows = saved_state.get(
            "sample_qaqc_rows",
            []
        )

        sample_data_saved = saved_state.get(
               "sample_data_saved",
              False
        )         

        included_batches = saved_state.get(
            "included_batches",
            []
        )

        qaqc_results = saved_state.get(
            "qaqc_results",
            []
        )

        prm_results = saved_state.get(
             "prm_results",
            []
        )

        qdl_value = saved_state.get(
            "qdl_value"
        )

        uploaded_filename = saved_state.get(
            "uploaded_filename"
        )
    

    if request.method == "POST":

        pdf_file = request.files.get(
            "ra7000_pdf"
        )

        if (
            pdf_file is None
            or pdf_file.filename == ""
        ):

            import_error = (
                "請先選擇 RA-7000A PDF 檔案。"
            )

        elif not pdf_file.filename.lower().endswith(
            ".pdf"
        ):

            import_error = (
                "只能匯入 PDF 檔案。"
            )

        else:

            uploaded_filename = (
                pdf_file.filename
            )

            temp_path = None

            try:

                fd, temp_path = (
                    tempfile.mkstemp(
                        suffix=".pdf"
                    )
                )

                os.close(
                    fd
                )

                pdf_file.save(
                    temp_path
                )

                ra7000_data = (
                    parse_ra7000_pdf(
                        temp_path
                    )
                )

                calibration_rows = []

                for index, row in enumerate(
                    ra7000_data.get(
                        "standards",
                        []
                    ),
                    start=1
                ):

                    calibration_rows.append(
                        {
                            "sequence_no":
                                index,

                            "sample_id":
                                (
                                    "STD"
                                    + str(index - 1)
                                ),

                            "signal":
                                row.get(
                                    "area"
                                ),

                            "role":
                                "STANDARD",

                            "calibration_x":
                                row.get(
                                    "std_concentration"
                                )
                        }
                    )

                calibration_result = (
                    calculate_calibration(
                        calibration_rows
                    )
                )

                # ========================================
                # W330 QDL
                # 與 W434 使用相同方法設定邏輯
                # ========================================

                if method_data and calibration_rows:

                      qdl_source = str(
                         method_data.get(
                        "QDL_SOURCE",
                      ""
                      )
                      or ""
                      ).strip().upper()

                      qdl_multiplier_text = str(
                         method_data.get(
                         "QDL_MULTIPLIER",
                         ""
                         )
                         or ""
                         ).strip()

                      if (
                             qdl_source
                             == "FIRST_NONZERO_CALIBRATION_X"
                         ):

                             first_nonzero_x = None

                             for row in calibration_rows:

                                  x_value = row.get(
                                  "calibration_x"
                                  )

                                  if (
                                     x_value is not None
                                     and x_value > 0
                                ):

                                     first_nonzero_x = (
                                     x_value
                                    )

                                     break

                             if first_nonzero_x is not None:

                                 try:

                                     qdl_multiplier = float(
                                        qdl_multiplier_text
                                            )

                                     qaqc_conc_factor = float(
                                        method_data.get(
                                             "QAQC_CONC_FACTOR",
                                                 ""
                                             )
                                            )

                                     qdl_value = (
                                        first_nonzero_x
                                        * qdl_multiplier
                                        * qaqc_conc_factor
                                        )

                                 except ValueError:

                                  qdl_value = None

                # ========================================
                # W330 SMP TABLE
                # → 轉為金屬分析共用 sample_qaqc_rows
                # ========================================

                (
                   sample_volume_default,
                   final_volume_default
                   ) = get_method_volume_defaults(
                   method_data
                )

                if (
                      ra7000_data
                       and calibration_result
                ):

                      raw_sample_rows = (
                        ra7000_data.get(
                          "samples",
                         []
                         )
                     )

                      # ========================================
                      # Hg PFM 原始資料暫存
                      # ========================================
                      hg_pfm_rows = []

                      for raw_row in raw_sample_rows:

                        signal = raw_row.get(
                        "area"
                         )
                        
                        measured_concentration = None
                        sample_concentration = None
                        calculated_concentration = None                      
                        qaqc_concentration = None 

                        sample_id = str(
                                raw_row.get(
                                  "sample_name",
                                   ""
                                )
                              or ""
                             ).strip()

                        sample_id_upper = (
                                 sample_id.upper()
                            )

                        # ========================================
                        # Hg PFM 原始訊號分流
                        # 不參與樣品濃度及 QA/QC 計算
                        # ========================================

                        if sample_id_upper in {"PFM", "PERFORMANCE"}:

                           hg_pfm_rows.append({
                             "sample_id": sample_id,
                             "analysis_datetime": raw_row.get(
                             "measure_datetime"
                              ),
                             "signal": raw_row.get("area"),
                             "signal_field": "AREA",
                             "analyte": "Hg",
                             "sequence_no": raw_row.get("row_no")
                              })

                           continue

                        # --------------------------------
                        # 共用 QA/QC Role 判斷
                        # --------------------------------

                        role = "SAMPLE"
 
                        if (
                               sample_id_upper == "ICBK"
                             or sample_id_upper.startswith(
                              "ICBK-"
                              )
                        ):
                           role = "ICBK"

                        elif (
                              sample_id_upper == "ICV"
                             or sample_id_upper.startswith(
                              "ICV-"
                              )
                        ):
                         role = "ICV"

                        elif (
                               sample_id_upper == "BK"
                             or sample_id_upper.startswith(
                                "BK-"
                              )
                        ):
                         role = "BK"

                        elif (
                               sample_id_upper == "QC"
                               or sample_id_upper.startswith(
                                "QC-"
                              )
                        ):
                         role = "QC"

                        elif (
                               sample_id_upper == "CCBK"
                               or sample_id_upper.startswith(
                                 "CCBK-"
                                )
                        ):
                         role = "CCBK"

                        elif (
                               sample_id_upper == "CCV"
                                or sample_id_upper.startswith(
                               "CCV-"
                             )
                        ):
                         role = "CCV"

                        elif (
                                sample_id_upper == "DUP"
                                or sample_id_upper.startswith(
                               "DUP-"
                               )
                         ):
                           role = "DUP"

                        elif (
                                 sample_id_upper == "MSD"
                                  or sample_id_upper.startswith(
                                 "MSD-"
                                   )
                         ):
                           role = "MSD"

                        elif (
                                   sample_id_upper == "MS"
                                  or sample_id_upper.startswith(
                                 "MS-"
                                   )
                        ):
                          role = "MS"

                        # --------------------------------
                        # W330 濃度計算基準
                        #
                        # ICV / CCV：
                        #   為檢量線確認 / 查核溶液，
                        #   直接使用最終 100 mL 溶液的
                        #   檢量線反算濃度，不再乘 100/50。
                        #
                        # 其他 SAMPLE / QC / DUP / MS / MSD：
                        #   視同樣品，
                        #   換算回原 50 mL 樣品濃度。
                        # --------------------------------

                        if signal is not None:

                             try:

                                 calc_sample_volume = (
                                    sample_volume_default
                                 )

                                 calc_final_volume = (
                                    final_volume_default
                                 )

                                 result = (
                                         calculate_sample_concentration(
                                         signal=signal,
                                         slope=calibration_result[
                                         "slope"
                                         ],
                                         intercept=calibration_result[
                                         "intercept"
                                         ],
                                         sample_volume=
                                         calc_sample_volume,
                                         final_volume=
                                         calc_final_volume,
                                         dilution_factor=1.0
                                          )
                                        )

                                 measured_concentration = (
                                     result.get(
                                     "measured_concentration"
                                      )
                                 )

                                 sample_concentration = (
                                      result.get(
                                      "sample_concentration"
                                       )
                                 )

                                 calculated_concentration = (
                                        result.get(
                                      "calculated_concentration"
                                       )
                                 )

                                 if role in {
                                     "ICV",
                                     "CCV"
                                     }:
                                         qaqc_concentration = (
                                         measured_concentration
                                        )
                                 else:
                                       qaqc_concentration = (
                                           sample_concentration
                                        ) 

                             except ValueError:

                                 calculated_concentration = None

                        sample_qaqc_rows.append(
                           {
                               "sequence_no":
                                raw_row.get(
                                 "row_no"
                               ),

                             "sample_id":
                              sample_id,

                             "signal":
                             signal,

                             "role":
                               role,

                            "sample_volume":
                               sample_volume_default,

                            "final_volume":
                             final_volume_default,

                            "dilution_factor":
                            1.0,
            
                            "spike_concentration":
                            "",

                            "measured_concentration":
                             measured_concentration,

                            "sample_concentration":
                             sample_concentration,

                            "calculated_concentration":
                             calculated_concentration,

                            "qaqc_concentration":
                             qaqc_concentration, 

                            "remark":
                                (
                                 raw_row.get(
                                  "note"
                                )
                                  or ""
                               ),

                             "is_excluded":
                                  False
                          }
                       ) 

                      # ========================================
                      # Hg PFM V2.1 管制標準配對與判定
                      # 使用 RA-7000A 原始 AREA
                      # ========================================

                      hg_pfm_results = []

                      for pfm_row in hg_pfm_rows:

                          result = {
                                    "sample_id": pfm_row.get("sample_id"),
                                    "analysis_datetime": pfm_row.get(
                                    "analysis_datetime"
                                   ),
                                    "signal": pfm_row.get("signal"),
                                    "signal_field": pfm_row.get("signal_field"),
                                    "status": "UNDETERMINED",
                                    "message": "",
                                    "control": None
                          }

                          try:
                              from datetime import datetime
                              import math

                              signal = float(pfm_row.get("signal"))

                              if not math.isfinite(signal):
                                 raise ValueError(
                                 "Hg PFM AREA 不是有效數值。"
                              )

                              raw_datetime = str(
                                 pfm_row.get("analysis_datetime") or ""
                              ).strip()

                              analysis_date = datetime.strptime(
                              raw_datetime,
                              "%Y/%m/%d %H:%M"
                              ).date()

                              instrument_id = str(
                              form_data.get("instrument_id") or ""
                              ).strip()

                              if not instrument_id:
                                 raise ValueError(
                                 "Hg PFM 尚未選擇儀器。"
                              )

                              control = find_active_performance_control(
                                  session_factory=SessionLocal,
                                  instrument_id=instrument_id,
                                  monitor_item="Hg",
                                  performance_type="CAL_HIGH_SIGNAL",
                                  analysis_date=analysis_date
                               )

                              lower_limit = float(control["lower_limit"])
                              upper_limit = float(control["upper_limit"])

                              if not (
                                 math.isfinite(lower_limit)
                                 and math.isfinite(upper_limit)
                                 and lower_limit <= upper_limit
                              ):
                                 raise ValueError(
                                 "Hg PFM 管制上下限設定異常。"
                              )

                              passed = lower_limit <= signal <= upper_limit

                              result["status"] = (
                                "PASS" if passed else "FAIL"
                              )

                              result["control"] = control

                              result["message"] = (
                              "符合管制標準"
                                if passed
                                    else "超出管制標準"
                                 )

                          except (
                                 ValueError,
                                  TypeError,
                                 KeyError,
                                 PerformanceControlQueryError
                          ) as ex:

                            result["message"] = str(ex)

                          hg_pfm_results.append(result)

                      # ========================================
                      # W330 QA/QC 預設添加濃度
                      # 與 W434 使用相同方法設定
                      # ========================================

                      if method_data and sample_qaqc_rows:

                         spike_field_by_role = {
                         "ICV": "ICV_SPIKE_CONC",
                         "QC": "QC_SPIKE_CONC",
                         "CCV": "CCV_SPIKE_CONC",
                         "MS": "MS_SPIKE_CONC",
                         "MSD": "MS_SPIKE_CONC"
                         }

                         for row in sample_qaqc_rows:

                          role = str(
                              row.get(
                               "role",
                                ""
                               )
                               or ""
                            ).strip().upper()

                          field_name = (
                             spike_field_by_role.get(
                               role
                              )
                            )

                          if field_name:

                             row[
                               "spike_concentration"
                              ] = str(
                           method_data.get(
                            field_name,
                           ""
                            )
                            or ""
                            ).strip()

                      # ========================================
                      # W330 D / W 分析類別過濾
                      # 沿用 TOC 已驗證的共用批次篩選
                      # ========================================

                      if sample_qaqc_rows:

                          selected_exam_no = ""

                          if control_data:
                             selected_exam_no = str(
                             control_data.get("EXAMNO") or ""
                          ).strip()

                          if not selected_exam_no and method_data:
                             selected_exam_no = str(
                             method_data.get("EXAMNO") or ""
                          ).strip()

                          if not selected_exam_no:
                             raise ValueError(
                             "W330 缺少 EXAMNO，無法確認 D/W 分析類別。"
                             )

                          (
                             sample_qaqc_rows,
                             excluded_rows,
                             included_batches
                             ) = filter_batches_by_exam_no(
                             sample_qaqc_rows,
                             selected_exam_no
                             )

                          pre_batch_rows = [] 

                      qaqc_conc_factor = 1.0

                      if method_data:

                         try:

                              qaqc_conc_factor = float(
                               method_data.get(
                                "QAQC_CONC_FACTOR",
                                "1"
                                )
                                or "1"
                               )

                         except (
                                     TypeError,
                                       ValueError
                                   ):

                                 qaqc_conc_factor = 1.0   

                      # ========================================
                      # W330 QA/QC 計算單位正規化
                      # 畫面濃度：ug/L
                      # QA/QC 管制資料：mg/L
                      # ========================================

                      qaqc_batches = []

                      for batch in included_batches:

                          qaqc_batch = batch.copy()

                          qaqc_rows = []

                          for row in batch.get(
                            "rows",
                              []
                          ):

                           qaqc_row = row.copy()

                           concentration = (
                             qaqc_row.get(
                             "calculated_concentration"
                             )
                           )

                           try:

                                if concentration not in {
                                    None,
                                    ""
                                 }:

                                    qaqc_row[
                                     "calculated_concentration"
                                  ] = (
                                     float(concentration)
                                    * qaqc_conc_factor
                                   )

                           except (
                                   TypeError,
                                   ValueError
                                  ):

                               pass

                           qaqc_concentration = (
                              qaqc_row.get(
                               "qaqc_concentration"
                                    )
                               )

                           try:

                               if qaqc_concentration not in {
                                       None,
                                       ""
                                }:

                                   qaqc_row[
                                      "qaqc_concentration"
                                      ] = (
                                       float(
                                        qaqc_concentration
                                       )
                                     * qaqc_conc_factor
                                       )

                           except (
                                   TypeError,
                                    ValueError
                                   ):

                                       pass                             

                           qaqc_rows.append(
                              qaqc_row
                           )

                          qaqc_batch[
                               "rows"
                                ] = qaqc_rows

                          qaqc_batches.append(
                                qaqc_batch
                                ) 

                      # ========================================
                      # W330 QA/QC 檢核
                      # ========================================

                      qaqc_results = []

                      if (
                                 qaqc_batches
                              and control_data
                      ):

                          qaqc_results = (
                                build_qaqc_check_results(
                                qaqc_batches,
                                control_data,
                                cc_relative_error_limit=20.0,
                                qdl_value=qdl_value
                                  )
                          )                            

                          save_analysis_state(
                              "W330_CURRENT",
                               {                                                                         
                                   "ra7000_data":ra7000_data,
                                   "prm_rows":hg_pfm_rows,
                                   "prm_results":hg_pfm_results, 
                                   "calibration_rows":calibration_rows,
                                   "calibration_result":calibration_result,
                                   "sample_qaqc_rows":sample_qaqc_rows,
                                   "included_batches":included_batches,
                                   "qaqc_results":qaqc_results,
                                    "qdl_value":qdl_value,
                                    "uploaded_filename":uploaded_filename
                              }
                          )
                            

            except Exception as ex:

                import_error = (
                    "RA-7000A PDF 解析失敗："
                    + str(ex)
                )

            finally:

                if (
                    temp_path
                    and os.path.exists(
                        temp_path
                    )
                ):

                    os.remove(
                        temp_path
                    )

    return render_template(
    "methods/w330.html",
    active_page="analysis_method",
    form_data=form_data,
    import_error=import_error,
    uploaded_filename=uploaded_filename,
    ra7000_data=ra7000_data,
    calibration_rows=calibration_rows,
    calibration_result=calibration_result,
    sample_qaqc_rows=sample_qaqc_rows,
    sample_data_saved=sample_data_saved,
    control_data=control_data,
    method_data=method_data,
    qdl_value=qdl_value,
    calibration_unit=(
    method_data.get(
        "DISPLAY_CONC_UNIT",
        ""
    )
    if method_data
    else ""
    ),
    calibration_signal_label="AREA",
    show_calibration_error=False,
    included_batches=included_batches,
    qaqc_3a_results=qaqc_results,
    prm_results=(
    hg_pfm_results
    if request.method == "POST"
    and "hg_pfm_results" in locals()
    else prm_results
    ),
)

@app.route("/analysis/w43401", methods=["GET", "POST"])
@login_required
def analysis_w43401():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    current_method_code = str(
        form_data.get(
            "method_code"
            ""
        )
        or ""
    ).strip().upper()

    if not current_method_code:
        current_method_code = "W434"

    current_exam_name = str(
    form_data.get(
        "exam_name",
        ""
        )
        or ""
    ).strip()

    if current_exam_name:
        current_analysis_name = (
        current_method_code
        + " "
        + current_exam_name
        + "分析"
    )
    else:
        current_analysis_name = (
        current_method_code
        + " 分析"
    )

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_session_key = (
        get_analysis_session_key(
            current_method_code
        )
    )

    existing_state = load_analysis_state(
        analysis_state_key
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
                analysis_session_key,
                ""
            )
            or ""
        ).strip()

    if formal_analysis_id:

        session[
            analysis_session_key
        ] = formal_analysis_id
    
    preview_rows = []
    prm_rows = []    
    prm_results = []
    calibration_rows = []
    sample_qaqc_rows = []
    toc_tic_rows = []   
    toc_tic_result = None     
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
            analysis_state_key
        )

        if saved_state:

            return render_template(
                "methods/w43401.html",
                active_page="analysis_method",
                current_analysis_name=current_analysis_name,
                current_analysis_url="/analysis/w43401",
                analysis_version="1.00",
                error_message=request.args.get(
                      "error_message"
                ),
                preview_rows=saved_state.get(
                    "preview_rows",
                    []
                ),

                prm_rows=saved_state.get(
                    "prm_rows",
                    []
                ),

                prm_results=saved_state.get(
                    "prm_results",
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

                toc_tic_rows=saved_state.get(
                    "toc_tic_rows", []
                ),

                toc_tic_result=saved_state.get(
                    "toc_tic_result"
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

                show_calibration_error=False,

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

                import_type = str(
                    (method_data or {}).get(
                        "IMPORT_TYPE",
                        ""
                    )
                    or ""
                ).strip().upper()

                if import_type == "TOC_PDF":
                    import math

                    reagent_blank_text = request.form.get(
                        "reagent_blank", ""
                    ).strip()

                    if not reagent_blank_text:
                        raise ValueError(
                            "請先輸入 Reagent Blank。"
                        )

                    try:
                        reagent_blank = float(
                            reagent_blank_text
                        )
                    except ValueError:
                        raise ValueError(
                            "Reagent Blank 必須是數字。"
                        )

                    if (
                        not math.isfinite(reagent_blank)
                        or reagent_blank < 0
                    ):
                        raise ValueError(
                            "Reagent Blank 必須是非負有限數值。"
                        )

                    preview_rows = parse_oi_toc_pdf(temp_path)

                    # ==========================================
                    # PRM Performance 原始資料分流
                    # PERFORMANCE / PFM
                    #
                    # PRM 不參與檢量線、TIC、樣品及 QA/QC 計算
                    # ==========================================
                    prm_rows, preview_rows = (
                        split_performance_rows(preview_rows)
                    )

                    # ==========================================
                    # TOC PRM ACTIVE 管制標準配對與判定
                    # 不影響一般分析資料處理
                    # ==========================================
                    from datetime import datetime
                    import math

                    prm_results = []

                    category = str(
                        form_data.get("category", "") or ""
                    ).strip().upper()

                    instrument_id = str(
                        form_data.get("instrument_id", "") or ""
                    ).strip()

                    exam_name = str(
                        form_data.get("exam_name", "") or ""
                    ).strip().upper()

                    for prm_row in prm_rows:

                        result = {
                            "sample_id": prm_row.get("sample_id"),
                            "analysis_datetime": prm_row.get(
                                "analysis_datetime"
                            ),
                            "signal": prm_row.get("signal"),
                            "signal_field": prm_row.get("signal_field"),
                            "status": "UNDETERMINED",
                            "message": "",
                            "control": None,
                        }

                        try:
                            # 僅處理 TOC 原始 Area Counts
                            if str(
                                prm_row.get("analyte", "")
                            ).strip().upper() != "TOC":
                                raise ValueError(
                                    "PRM 測項不是 TOC。"
                                )

                            if prm_row.get(
                                "signal_field"
                            ) != "AREA_COUNTS":
                                raise ValueError(
                                    "PRM 訊號不是 AREA_COUNTS。"
                                )

                            signal = float(
                                prm_row.get("signal")
                            )

                            if not math.isfinite(signal):
                                raise ValueError(
                                    "PRM Area 不是有效數值。"
                                )

                            if category not in ("D", "W", "G"):
                                raise ValueError(
                                    "Basic Info 檢測類別不是 D/W/G。"
                                )

                            if not instrument_id:
                                raise ValueError(
                                    "Basic Info 尚未選擇儀器。"
                                )

                            # PDF 日期字串例如：
                            # 2026/10/13  下午05:12:
                            raw_datetime = str(
                                prm_row.get(
                                    "analysis_datetime", ""
                                ) or ""
                            ).strip()

                            date_text = raw_datetime.split()[0]

                            analysis_date = datetime.strptime(
                                date_text,
                                "%Y/%m/%d"
                            ).date()

                            # PRM V2：
                            # 儀器性能查核不依樣品檢測類別 D/G/W 區分
                            monitor_item = "TOC"

                            control = find_active_performance_control(
                                session_factory=SessionLocal,
                                instrument_id=instrument_id,
                                monitor_item=monitor_item,
                                performance_type="CAL_HIGH_SIGNAL",
                                analysis_date=analysis_date,
                            )

                            lower_limit = control.get("lower_limit")
                            upper_limit = control.get("upper_limit")

                            if (
                                lower_limit is None
                                or upper_limit is None
                            ):
                                raise ValueError(
                                    "管制標準缺少上下限。"
                                )

                            lower_limit = float(lower_limit)
                            upper_limit = float(upper_limit)

                            if not (
                                math.isfinite(lower_limit)
                                and math.isfinite(upper_limit)
                                and lower_limit <= upper_limit
                            ):
                                raise ValueError(
                                    "管制上下限設定異常。"
                                )

                            passed = (
                                lower_limit <= signal <= upper_limit
                            )

                            result["status"] = (
                                "PASS" if passed else "FAIL"
                            )
                            result["control"] = control
                            result["message"] = (
                                "符合管制標準"
                                if passed
                                else "超出管制標準"
                            )

                        except (
                            ValueError,
                            TypeError,
                            PerformanceControlQueryError,
                        ) as ex:

                            result["message"] = str(ex)

                        prm_results.append(result)

                    # 清洗紀錄不參與檢量線及樣品計算
                    preview_rows = [
                       row
                       for row in preview_rows
                       if str(
                               row.get("sample_id", "") or ""
                             ).strip().upper() != "WASH"
                       ]

                    preview_rows, toc_tic_rows = (
                        separate_toc_tic_rows(preview_rows)
                    )
                    
                elif import_type == "PE900_PDF":
                    preview_rows = parse_pe900_pdf(
                        temp_path
                    )
                else:
                    raise ValueError(
                        "尚未支援的 PDF 匯入格式："
                        + import_type
                    )

                if preview_rows and method_data:

                  preview_rows = classify_analysis_rows(
                  preview_rows,
                  method_data
                    )


                if preview_rows and method_data:

                    selected_exam_no = ""

                    if control_data:

                        selected_exam_no = (
                            control_data.get(
                                "EXAMNO",
                                ""
                            )
                            .strip()
                        )

                    if not selected_exam_no:

                        selected_exam_no = (
                            method_data.get(
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
                        preview_rows,
                        reagent_blank=(
                            reagent_blank
                            if import_type == "TOC_PDF"
                            else 0.0
                        )
                    )

                  except ValueError as ex:

                   import_error = (
                           "檢量線計算失敗："
                                + str(ex)
                             )  

                if len(preview_rows) == 0:
                    import_error = (
                        "PDF 已讀取，但未解析到分析資料。"
                    )

            except Exception as ex:

                import_error = (
                    "PDF解析失敗："
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

        role = str(
            row.get(
            "role",
            ""
            )
           or ""
        ).strip().upper()

        field_name = (
           spike_field_by_role.get(
           role
           )
        )

        if field_name:

          row[
               "spike_concentration"
          ] = (
            method_data.get(
            field_name,
            ""
            )
          .strip()
        )

        else:

            row[
               "spike_concentration"
            ] = ""

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

    (
       sample_volume_default,
        final_volume_default
       ) = get_method_volume_defaults(
       method_data
    )

    sample_dilution_default = 1.0

    try:

        sample_dilution_default = float(
            method_data.get(
                "SAMPLE_DILUTION_DEFAULT",
                "1"
            )
            or "1"
        )

    except (
        TypeError,
        ValueError
    ):

        sample_dilution_default = 1.0

    apply_volume_factor = (
         str(
        method_data.get(
            "APPLY_VOLUME_FACTOR",
            "Y"
        )
        or "Y"
    )
    .strip()
    .upper()
    == "Y"
    )

    for row in sample_qaqc_rows:

        role = str(
        row.get(
            "role",
            ""
        )
        or ""
        ).strip().upper()

        if role in {
           "ICBK",
           "ICV",
           "CCBK",
           "CCV"
        }:

           row[
            "sample_volume"
           ] = sample_volume_default

           row[
            "final_volume"
           ] = sample_volume_default

           row[
            "dilution_factor"
           ] = 1.0

        else:

           row[
            "sample_volume"
           ] = sample_volume_default

           row[
            "final_volume"
           ] = final_volume_default

           row[
            "dilution_factor"
           ] = sample_dilution_default

        row[
        "apply_volume_factor"
        ] = apply_volume_factor

        row["sample_prep_factor"] = (
            1.0
            if role in {
                "ICBK",
                "ICV",
                "CCBK",
                "CCV"
            }
            else float(
                method_data.get(
                    "SAMPLE_PREP_FACTOR",
                    "1"
                )
                or "1"
            )
        )        

        row["remark"] = ""
        row["is_excluded"] = False
        row["exclusion_reason"] = ""
        row["calculated_concentration"] = None

    recalculation_rows = [
        row
        for row in sample_qaqc_rows
        if row.get("role") in simple_roles
    ]

    recalculate_sample_rows(
    rows=recalculation_rows,
    calibration_result=calibration_result,
    calculate_concentration=
        calculate_sample_concentration
    )


    included_batches = (
    sync_sample_rows_to_batches(
        sample_rows=sample_qaqc_rows,
        included_batches=included_batches
       )
    )

    
    # ========================================
    # Manual QA/QC 檢核
    # ========================================

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

    toc_tic_result = calculate_toc_tic_result(
        toc_tic_rows,
        calibration_result
    )

    if (
        request.method == "POST"
        and preview_rows
    ):

        save_analysis_state(
            analysis_state_key,
            {
                "preview_rows":
                    preview_rows,

                "prm_rows":
                    prm_rows,

                "prm_results":
                    prm_results,

                "calibration_rows":
                    calibration_rows,

                "calibration_result":
                    calibration_result,

                "sample_qaqc_rows":
                    sample_qaqc_rows,

                "toc_tic_rows": toc_tic_rows,

                "toc_tic_result": toc_tic_result,

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
                   formal_analysis_id,
                   
                    
            }
        )

    # 尚未載入任何分析資料時，
    # 不保留前一次 Working State 的波長確認顯示
    if (
        not preview_rows
        and not sample_qaqc_rows
    ):
        confirmed_wavelength = None
        wavelength_warning = None
        instrument_wavelength = None

    return render_template(
        "methods/w43401.html",
        active_page="analysis_method",
        current_analysis_name=current_analysis_name,
        current_analysis_url="/analysis/w43401",
        analysis_version="1.00",
        preview_rows=preview_rows,
        prm_rows=prm_rows,
        prm_results=prm_results,
        calibration_rows=calibration_rows,
        sample_qaqc_rows=sample_qaqc_rows,
        toc_tic_rows=toc_tic_rows,
        toc_tic_result=toc_tic_result,    
        sample_data_saved=False,
        import_error=import_error,
        error_message=request.args.get(
            "error_message"
        ),
        uploaded_filename=uploaded_filename,
        method_data=method_data,
        control_data=control_data,
        report_data=report_data,
        calibration_result=calibration_result,
        show_calibration_error=False,
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

def confirm_w434_wavelength():

    choice = request.form.get(
        "choice",
        ""
    ).strip().lower()

    form_data = session.get(
        "basic_info_form"
    ) or {}

    current_method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not current_method_code:
        current_method_code = "W434"

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_state = load_analysis_state(
        analysis_state_key
    )

    if not analysis_state:

        return (
            "尚未找到 "
            + current_method_code
            + " 分析資料。",
            400
        )

    if not form_data:

        return (
            "尚未找到基本資料。",
            400
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
        analysis_state_key,
        analysis_state
    )

    return "", 204

@app.route(
    "/analysis/w43401/update-calibration",
    methods=["POST"]
)
@login_required
def update_w434_calibration():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    current_method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not current_method_code:
        current_method_code = "W434"

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_state = load_analysis_state(
        analysis_state_key
    )

    if not analysis_state:

        return redirect_metal_analysis_error(
            "尚未找到 "
            + current_method_code
            + " 分析資料，請重新匯入 PDF。",
            current_method_code
        )

    preview_rows = analysis_state.get(
        "preview_rows",
        []
    )

    calibration_rows = analysis_state.get(
        "calibration_rows",
        []
    )

    sample_qaqc_rows = analysis_state.get(
        "sample_qaqc_rows",
        []
    )

    included_batches = analysis_state.get(
        "included_batches",
        []
    )

    qdl_value = analysis_state.get(
        "qdl_value"
    )

    if not calibration_rows:

        return (
            "尚未找到檢量線資料。",
            400
        )

    try:

        calibration_count = int(
            request.form.get(
                "calibration_count",
                "0"
            )
        )

    except ValueError:

        return (
            "檢量線筆數格式錯誤。",
            400
        )

    if calibration_count <= 0:

        return (
            "檢量線筆數不可為 0。",
            400
        )

    calibration_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in calibration_rows
    }

    updated_calibration_rows = []

    for index in range(
        calibration_count
    ):

        sequence_key = (
            request.form.get(
                "calibration_sequence_"
                + str(index),
                ""
            )
            .strip()
        )

        signal_text = (
            request.form.get(
                "calibration_signal_"
                + str(index),
                ""
            )
            .strip()
        )

        if (
            sequence_key
            not in calibration_map
        ):

            return (
                "第 "
                + str(index + 1)
                + " 筆檢量線找不到原始 Sequence。",
                400
            )

        try:

            signal = float(
                signal_text
            )

        except ValueError:

            return (
                "第 "
                + str(index + 1)
                + " 筆檢量線測定值格式錯誤。",
                400
            )

        row = calibration_map[
            sequence_key
        ]

        row[
            "signal"
        ] = signal

        updated_calibration_rows.append(
            row
        )

    # ========================================
    # 同步回 preview_rows
    # ========================================

    updated_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in updated_calibration_rows
    }

    for preview_row in preview_rows:

        sequence_key = str(
            preview_row.get(
                "sequence_no",
                ""
            )
        )

        updated_row = (
            updated_map.get(
                sequence_key
            )
        )

        if updated_row is None:
            continue

        preview_row[
            "signal"
        ] = updated_row.get(
            "signal"
        )

    # ========================================
    # 重新計算檢量線
    # ========================================

    try:
        previous_calibration = (
            analysis_state.get("calibration_result") or {}
        )

        reagent_blank = float(
            previous_calibration.get("reagent_blank", 0.0)
        )

        calibration_result = calculate_calibration(
            preview_rows,
            reagent_blank=reagent_blank
        )

    except ValueError as ex:

        return redirect(
            url_for(
                "analysis_w43401",
                saved="1",
                error_message=(
                    "檢量線重新計算失敗："
                    + str(ex)
                )
            )
        )

    # ========================================
    # 重新計算樣品濃度
    # ========================================

    sample_qaqc_rows = (
        recalculate_sample_rows(
            rows=sample_qaqc_rows,
            calibration_result=calibration_result,
            calculate_concentration=
                calculate_sample_concentration
        )
    )

    # ========================================
    # 同步最新資料回 Batch
    # ========================================

    latest_row_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in sample_qaqc_rows
    }

    for batch in included_batches:

        for batch_row in batch.get(
            "rows",
            []
        ):

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

            if latest_row is not None:

                batch_row.update(
                    latest_row
                )

    # ========================================
    # 重新計算 QA/QC
    # ========================================

    form_data = session.get(
        "basic_info_form"
    )

    qaqc_results = []

    if form_data:

        (
            control_data,
            method_data,
            load_error
        ) = load_control_and_method_data(
            form_data
        )

        if (
            not load_error
            and included_batches
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

    # ========================================
    # 儲存 Working State
    # ========================================

    analysis_state[
        "preview_rows"
    ] = preview_rows

    analysis_state[
        "calibration_rows"
    ] = updated_calibration_rows

    analysis_state[
        "calibration_result"
    ] = calibration_result

    toc_tic_rows = analysis_state.get(
        "toc_tic_rows",
        []
    )

    analysis_state["toc_tic_result"] = (
        calculate_toc_tic_result(
            toc_tic_rows,
            calibration_result
        )
    )

    analysis_state["toc_tic_rows"] = toc_tic_rows

    analysis_state[
        "sample_qaqc_rows"
    ] = sample_qaqc_rows

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
        analysis_state_key,
        analysis_state
    )

    return redirect(
        url_for(
            "analysis_w43401",
            saved="1"
        )
    )

@app.route(
    "/analysis/update-samples",
    methods=["POST"]
)
@login_required
def update_analysis_samples():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    current_method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not current_method_code:
        current_method_code = "W434"

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_state = load_analysis_state(
        analysis_state_key
    )

    if not analysis_state:

        return (
            "尚未找到 "
            + current_method_code
            + " 分析資料。",
            400
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

    (
      sample_volume_default,
      final_volume_default
      ) = get_method_volume_defaults(
       method_data
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
                str(
                sample_volume_default
                )
            )
            .strip()
        )

        final_volume_text = (
            request.form.get(
                "final_volume_"
                + str(index),
                str(
                final_volume_default
                )
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

        updated_rows.append(
            row
        )

    updated_rows = (
        recalculate_sample_rows(
            rows=updated_rows,
            calibration_result=calibration_result,
            calculate_concentration=
                calculate_sample_concentration
        )
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
    for row in updated_rows
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


    qaqc_results = []

    if (
         included_batches
          and control_data
    ):

         qaqc_conc_factor = 1.0

         if method_data:

            try:

                qaqc_conc_factor = float(
                method_data.get(
                    "QAQC_CONC_FACTOR",
                    "1"
                )
                or "1"
            )

            except (
            TypeError,
            ValueError
        ):
              qaqc_conc_factor = 1.0

    qaqc_batches = []

    for batch in included_batches:

        qaqc_batch = batch.copy()
        qaqc_rows = []

        for row in batch.get(
            "rows",
            []
        ):

            # 已刪除的樣品或 QA/QC
            # 不參與有效 QA/QC 判定
            if row.get("is_excluded", False):
                continue

            qaqc_row = row.copy()

            for field_name in {
                "calculated_concentration",
                "qaqc_concentration"
            }:

                value = qaqc_row.get(
                    field_name
                )

                if value in {
                    None,
                    ""
                }:
                    continue

                try:

                    qaqc_row[
                        field_name
                    ] = (
                        float(value)
                        * qaqc_conc_factor
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    pass

            qaqc_rows.append(
                qaqc_row
            )

        qaqc_batch[
            "rows"
        ] = qaqc_rows

        qaqc_batches.append(
            qaqc_batch
        )

    qaqc_results = (
        build_qaqc_check_results(
            qaqc_batches,
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
        analysis_state_key,
        analysis_state
    )

    if current_method_code == "W330":

      return redirect(
        url_for(
            "analysis_w330",
            saved="1"
        )
    )

    return redirect(
    url_for(
        "analysis_w43401",
        saved="1"
    )
)

@app.route("/analysis/save-record",methods=["POST"])
@login_required
def save_analysis_record_route():

    form_data = session.get(
    "basic_info_form"
       ) or {}

    current_method_code = str(
        form_data.get(
        "method_code",
        ""
       )
       or ""
       ).strip().upper()

    if not form_data:

      return redirect(
        url_for(
            "basic_info"
        )
    )

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_session_key = (
        get_analysis_session_key(
        current_method_code
        )
    )       

    analysis_endpoint = (
        get_analysis_page_endpoint(
        current_method_code
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

      return redirect_metal_analysis_error(
        load_error,
        current_method_code
    )

    (
        report_data,
        report_error
    ) = load_report_setting(
        method_data
    )

    if report_error:

        return redirect_metal_analysis_error(
            report_error,
            current_method_code
        )

    analysis_state = load_analysis_state(
    analysis_state_key
    )

    if not analysis_state:

        return redirect_metal_analysis_error(
            "尚未找到 "
            + current_method_code
            + " 分析資料，"
            "請先完成分析資料匯入或建立。",
            current_method_code
        )

    form_data = session.get(
        "basic_info_form"
    )

    qaqc_results = (
    analysis_state.get(
        "qaqc_results",
        []
    )
)

    qaqc_ready, qaqc_error = (
        validate_qaqc_export_ready(
            qaqc_results,
            has_control_data=bool(
                control_data
            )
        )
    )

    if not qaqc_ready:

      return redirect_metal_analysis_error(
        qaqc_error.replace(
            "不可匯出",
            "不可儲存正式分析紀錄"
        ),
        current_method_code
    )

    current_user = (
        get_current_user()
        or {}
    )

    try:

        save_result = (
            save_analysis_record(
                form_data=form_data,
                control_data=control_data,
                method_data=method_data,
                report_data=report_data,
                analysis_state=analysis_state,
                current_user=current_user
            )
        )

    except ValueError as ex:

        return redirect(
            url_for(
                analysis_endpoint,
                saved="1",
                error_message=str(ex)
            )
        )

    except Exception as ex:

        return redirect(
            url_for(
                analysis_endpoint,
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
    analysis_session_key
] = save_result[
    "analysis_id"
]

    save_analysis_state(
    analysis_state_key,
    analysis_state
    )

    return redirect(
        url_for(
            analysis_endpoint,
            saved="1",
            formal_saved="1"
        )
    )

@app.route("/analysis/w330/export-pdf")
@app.route("/analysis/w43401/export-pdf")
@login_required
def export_w434_pdf():

    form_data = session.get(
    "basic_info_form"
    ) or {}

    current_method_code = str(
    form_data.get(
        "method_code",
        ""
    )
    or ""
).strip().upper()

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

    current_method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    if load_error:

        return redirect_metal_analysis_error(
            load_error,
            current_method_code
        )

    (
        report_data,
        report_error
    ) = load_report_setting(
        method_data
    )

    if report_error:

        return redirect_metal_analysis_error(
            report_error,
            current_method_code
        )

    analysis_state = load_analysis_state(
    analysis_state_key
    )

    if not analysis_state:

       return redirect_metal_analysis_error(
        "尚未找到 "
        + current_method_code
        + " 分析結果，"
        "請先完成分析資料。",
        current_method_code
    ) 

    qaqc_results = (
    analysis_state.get(
        "qaqc_results",
        []
    )
)

    qaqc_ready, qaqc_error = (
    validate_qaqc_export_ready(
        qaqc_results,
        has_control_data=bool(
            control_data
        )
    )
)

    if not qaqc_ready:

      return redirect_metal_analysis_error(
        qaqc_error,
        current_method_code
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
    current_method_code
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

@app.route("/analysis/w330/export-lims")
@app.route("/analysis/w43401/export-lims")
@login_required
def export_w434_lims():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    if not form_data:

       return redirect(
        url_for(
            "basic_info"
        )
    )

    current_method_code = str(
       form_data.get(
        "method_code",
        ""
        )
       or ""
    ).strip().upper()

    analysis_state_key = (
        get_analysis_state_key(
        current_method_code
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

        return redirect_metal_analysis_error(
            load_error,
            current_method_code
        )

    analysis_state = load_analysis_state(
    analysis_state_key
    )

    if not analysis_state:

        return redirect_metal_analysis_error(
            "尚未找到 "
            + current_method_code
            + " 分析結果，"
            "請先完成分析資料。",
            current_method_code
        )
    qaqc_results = (
    analysis_state.get(
        "qaqc_results",
        []
    )
)

    qaqc_ready, qaqc_error = (
    validate_qaqc_export_ready(
        qaqc_results,
        has_control_data=bool(
            control_data
        )
    )
)

    if not qaqc_ready:

      return redirect_metal_analysis_error(
        qaqc_error,
        current_method_code
    )
    
    export_data = (
        build_w434_lims_export_data(
            form_data=form_data,
            control_data=control_data,
            method_data=method_data,
            analysis_state=analysis_state,
            analyst=""
        )
    )

    if not export_data.qc_rows:

      return redirect_metal_analysis_error(
        "目前沒有可匯出的 LIMS 品管資料。",
        current_method_code
    )

    if not export_data.analysis_rows:

      return redirect_metal_analysis_error(
        "目前沒有可匯出的正式樣品資料。",
        current_method_code
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

# ========================================
# ICP 適用測項 CSV 匯入
# ========================================

# ========================================
# Performance 年度管制 CSV 匯入
# 第一階段：檔案與欄位驗證
# 尚不寫入正式 CSV
# ========================================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)