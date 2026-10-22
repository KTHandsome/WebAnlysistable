from services.icp_pdf_export_service import pdf_configuration, assemble_pdf_channels
from services.icp_qaqc_service import build_icp_qaqc_view
"""ICP raw data preview and work-level manual PFM input."""
import os
import json
import secrets
from flask import Blueprint, current_app, render_template, request, session, jsonify, send_file, redirect, url_for
from auth_session import login_required, get_current_user
from analysis.icp_state_repository import load_icp_work_state
from analysis.icp_workflow import (
    build_sample_candidate_groups, load_icp_analyte_map,
    match_lims_icp_analytes, build_icp_lims_matches,
)
from analysis.icp_data_view import build_icp_data_view
from services.lims_analysis_service import get_lims_sample_analysis

from services.icp_performance_service import (
    METHOD_RATIOS, IcpPfmConflictError, work_token, load_icp_pfm_control,
    calculate_icp_pfm, save_icp_pfm,
)

from services.icp_batch_category_service import build_category_view, save_batch_categories

from services.icp_calibration_service import build_calibration_cards

from services.icp_sample_service import build_sample_view, save_sample_inputs

icp_data_bp = Blueprint("icp_data_bp", __name__)


def _load_icp_context():
    def show_error(message, status):
        return None, None, None, (message, status)
    current_key = str(session.get("icp_work_key") or "").strip()
    requested = request.args.getlist("work_key")
    if requested and (len(set(requested)) != 1 or requested[0] != current_key):
        return show_error("目前開啟的 ICP 工作已改變，請從匯入頁重新進入。", 409)
    if not current_key:
        return show_error("尚未開啟 ICP 工作，請先匯入或開啟已暫存工作。", 400)
    work = load_icp_work_state(current_key)
    if not isinstance(work, dict):
        return show_error("找不到目前的 ICP 暫存資料。", 404)
    from services.icp_record_service import check_editable
    try:
        if work.get("formal_status") not in {"SUBMITTED", "DELETED"}:
            check_editable(work, get_current_user() or {})
    except PermissionError as exc:
        return show_error(str(exc), 403)
    if work.get("formal_status") in {"SUBMITTED", "DELETED"} and request.method == "POST":
        return show_error("此工作已送審，請從分析紀錄查詢操作正式紀錄。", 409)
    form = work.get("form_data") or {}
    if not form or form != (session.get("basic_info_form") or {}):
        return show_error("分析基本資料已變更，請返回匯入頁重新確認。", 409)
    loader = current_app.extensions.get("phyon_load_basic_info_data")
    if loader is None:
        return show_error("無法讀取分析方法設定。", 503)
    _, method, error = loader(form)
    if (error or not method or method.get("ANALYSIS_MODE") != "MULTI_ANALYTE"
            or method.get("IMPORT_TYPE") != work.get("import_type")):
        return show_error("分析方法或匯入格式已變更，請返回基本資料確認。", 409)
    rows = (work.get("parsed_data") or {}).get("rows") or []
    if not rows:
        return show_error("目前工作沒有可顯示的 ICP 量測資料。", 400)
    return current_key, work, form, None




def _load_icp_channels(work, form):
    rows = (work.get("parsed_data") or {}).get("rows") or []
    groups = build_sample_candidate_groups(rows)
    from analysis.icp_batch_adoption import active_candidate_groups
    groups = active_candidate_groups(work, groups)
    matches, lookup_error = [], None
    if groups:
        try:
            mapping = load_icp_analyte_map(os.path.join(
                current_app.root_path, "data", "Phyon_ICP_Analyte_Map.csv"))
            lims_groups = []
            for keepid in sorted({group["keepid"] for group in groups}):
                lims_rows = get_lims_sample_analysis(keepid)
                matched = match_lims_icp_analytes(lims_rows, mapping)
                lims_groups.append({"keepid": keepid, "matched_rows": matched["matched_rows"]})
            matches = build_icp_lims_matches(groups, lims_groups, form.get("method_code"))
        except Exception:
            current_app.logger.exception("ICP 數據預覽 LIMS 配對查詢失敗")
            lookup_error = "LIMS 配對目前無法確認；量測資料仍可查看，採用狀態暫不判定。"
    channels = build_icp_data_view(work, matches, lookup_error)
    return channels, lookup_error


@icp_data_bp.route("/analysis/icp/data", methods=["GET"])
@login_required
def analysis_icp_data():
    current_key, work, form, error = _load_icp_context()
    if error:
        message, status = error
        return render_template("methods/icp_data.html", error_message=message,
                               channels=[], selected_channel=None,
                               active_page="analysis_method"), status
    if work.get("formal_status") in {"SUBMITTED", "DELETED"}:
        return redirect(url_for("analysis_record_detail", analysis_id=work.get("formal_analysis_id")))
    channels, lookup_error = _load_icp_channels(work, form)
    selected = request.args.get("channel", "")
    if selected and selected not in {channel["key"] for channel in channels}:
        return render_template("methods/icp_data.html", error_message="指定的金屬與波長不在目前工作中。",
                               channels=[], selected_channel=None, active_page="analysis_method"), 400
    channel = next((item for item in channels if item["key"] == selected), channels[0] if channels else None)
    pfm_control, pfm_error = None, None
    if str(form.get("method_code") or "").strip().upper() in METHOD_RATIOS:
        try:
            pfm_control = load_icp_pfm_control(form)
        except Exception as exc:
            pfm_error = str(exc)
            current_app.logger.warning("ICP PFM 管制查詢失敗：%s", exc)
    else:
        pfm_error = "此方法尚未設定 ICP 比值性能查核。"
    saved_pfm = work.get("pfm_manual") or {}
    pfm_current = bool(pfm_control and saved_pfm
                       and saved_pfm.get("control") == pfm_control)
    if "icp_pfm_csrf" not in session:
        session["icp_pfm_csrf"] = secrets.token_urlsafe(32)
    try:
        category_view = build_category_view(work, form, channel)
        category_error = None
    except ValueError as exc:
        category_view, category_error = None, str(exc)
    calibrations = build_calibration_cards(channel, category_view)
    sample_view = build_sample_view(work, channel, category_view, calibrations, lookup_error)
    icp_qaqc_view = build_icp_qaqc_view(category_view, sample_view, lookup_error)
    try:
        _, pdf_token = pdf_configuration(work, form, channels)
        pdf_error = None
    except Exception:
        current_app.logger.exception("ICP PDF 設定載入失敗")
        pdf_token, pdf_error = "", "無法載入匯出設定，請確認批次及紀錄表設定。"
    return render_template(
        "methods/icp_data.html", pdf_configuration_token=pdf_token, pdf_export_error=pdf_error,
        icp_qaqc_view=icp_qaqc_view,
        sample_view=sample_view, calibration_cards=calibrations,
        category_view=category_view, category_error=category_error,
        channels=channels, selected_channel=channel,
        form_data=form, source_filename=work.get("source_filename", ""),
        work_key=current_key, lookup_error=lookup_error, error_message=None,
        active_page="analysis_method", pfm_control=pfm_control, pfm_error=pfm_error,
        saved_pfm=saved_pfm, pfm_current=pfm_current,
        pfm_work_token=work_token(work),
        pfm_control_token=work_token(pfm_control) if pfm_control else "",
        pfm_csrf=session["icp_pfm_csrf"],
    )


@icp_data_bp.route("/analysis/icp/pfm", methods=["POST"])
@login_required
def save_manual_icp_pfm():
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入後再操作。"), 403
    # Require one explicit work key; never save through a changed session pointer.
    ids = request.form.getlist("work_key") + request.args.getlist("work_key")
    if not ids or len(set(ids)) != 1 or ids[0] != session.get("icp_work_key"):
        return jsonify(message="目前工作已改變，請重新開啟數據頁。"), 409
    current_key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        control = load_icp_pfm_control(form)
        if request.form.get("control_token") != work_token(control):
            raise IcpPfmConflictError("管制設定已變更，請重新載入後再確認 PFM。")
        pfm = calculate_icp_pfm(
            control, request.form.get("numerator_signal"),
            request.form.get("denominator_signal"), get_current_user() or {},
        )
        save_icp_pfm(current_key, request.form.get("work_token"), pfm)
        return jsonify(message="PFM 已儲存。")
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 手動 PFM 儲存失敗")
        return jsonify(message="PFM 無法儲存，請確認正式管制設定或稍後重試。"), 503


@icp_data_bp.route("/analysis/icp/batch-category", methods=["POST"])
@login_required
def save_icp_batch_category():
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 403
    ids = request.form.getlist("work_key") + request.args.getlist("work_key")
    if not ids or len(set(ids)) != 1 or ids[0] != session.get("icp_work_key"):
        return jsonify(message="目前工作已改變，請重新開啟數據頁。"), 409
    key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        channels = build_icp_data_view(work, [], None)
        channel = next((c for c in channels if c["key"] == request.form.get("channel_key")), None)
        if channel is None:
            raise ValueError("指定金屬與波長不在目前工作。")
        view = build_category_view(work, form, channel)
        if request.form.get("settings_token") != view["settings_token"]:
            raise IcpPfmConflictError("方法或管制設定已更新，請重新載入後再確認。")
        batch_ids = request.form.getlist("batch_id")
        categories = request.form.getlist("category")
        exam_nos = request.form.getlist("exam_no")
        expected_ids = {b["id"] for b in view["batches"]}
        if (not expected_ids or len(batch_ids) != len(categories) or len(batch_ids) != len(exam_nos)
                or len(batch_ids) != len(set(batch_ids)) or set(batch_ids) != expected_ids):
            raise ValueError("請完整提交全部批次，且不可重複。")
        selections = []
        for batch_id, category, exam_no in zip(batch_ids, categories, exam_nos):
            setting = next((s for s in view["catalog"].get(category, [])
                            if s["exam_no"] == exam_no and not s["error"]), None)
            if setting is None:
                raise ValueError("BATCH " + batch_id + "：請選擇此類別適用的檢測代碼。")
            selections.append({"batch_id": batch_id, "category": category, "setting": setting})
        save_batch_categories(key, request.form.get("work_token"), selections,
                              channel["key"], get_current_user() or {})
        return jsonify(message="全部批次類別與檢測設定已儲存。")
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 批次類別設定儲存失敗")
        return jsonify(message="類別設定無法儲存，請稍後再試。"), 503


@icp_data_bp.route("/analysis/icp/samples", methods=["POST"])
@login_required
def save_icp_samples():
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 403
    ids = request.form.getlist("work_key") + request.args.getlist("work_key")
    if not ids or len(set(ids)) != 1 or ids[0] != session.get("icp_work_key"):
        return jsonify(message="目前工作已改變，請重新開啟數據頁。"), 409
    key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        if request.form.get("work_token") != work_token(work):
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存。")
        channels, lookup_error = _load_icp_channels(work, form)
        if lookup_error:
            return jsonify(message="LIMS 配對目前無法確認，請稍後再儲存。"), 503
        channel = next((c for c in channels if c["key"] == request.form.get("channel_key")), None)
        if channel is None:
            raise ValueError("指定的金屬與波長不在目前工作。")
        categories = build_category_view(work, form, channel)
        calibrations = build_calibration_cards(channel, categories)
        current_view = build_sample_view(work, channel, categories, calibrations)
        if request.form.get("sample_token") != current_view["token"]:
            raise IcpPfmConflictError("方法、管制或採用量測已更新，請重新載入後再確認。")
        raw = request.form.get("rows_json", "")
        if len(raw) > 2000000:
            raise ValueError("送出的資料量過大。")
        try:
            submitted = json.loads(raw)
        except (ValueError, TypeError):
            raise ValueError("樣品輸入格式不正確。")
        if not isinstance(submitted, list) or any(not isinstance(r, dict) for r in submitted):
            raise ValueError("樣品輸入格式不正確。")
        ids = [r.get("row_id") for r in submitted]
        expected = {r["row_id"] for b in current_view["batches"] for r in b["rows"]}
        if (any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or set(ids) != expected):
            raise ValueError("樣品清單已變更或資料不完整，請重新載入。")
        editable = {"row_id", "sample_volume", "final_volume", "dilution_factor", "is_excluded"}
        if any(set(r) != editable for r in submitted):
            raise ValueError("樣品輸入欄位不正確。")
        overrides = {r["row_id"]: r for r in submitted}
        calculated = build_sample_view(work, channel, categories, calibrations, overrides=overrides)
        messages = [b["error"] for b in calculated["batches"] if b.get("error")]
        if messages:
            raise ValueError(messages[0])
        save_sample_inputs(key, request.form.get("work_token"), channel["key"], calculated, get_current_user() or {})
        return jsonify(message="樣品與品管輸入已暫存。")
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 樣品輸入暫存失敗")
        return jsonify(message="樣品資料無法暫存，請稍後重試。"), 503


@icp_data_bp.route("/analysis/icp/batch-setup", methods=["POST"])
@login_required
def save_icp_batch_setup():
    from services.icp_batch_setup_service import save_setup
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 403
    ids = request.form.getlist("work_key") + request.args.getlist("work_key")
    if not ids or len(set(ids)) != 1 or ids[0] != session.get("icp_work_key"):
        return jsonify(message="目前工作已改變，請重新開啟匯入頁。"), 409
    key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        raw = request.form.get("batches_json", "")
        if len(raw) > 2000000:
            raise ValueError("資料量過大。")
        try:
            submitted = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("批次設定格式不正確。")
        save_setup(key, request.form.get("work_token"), request.form.get("settings_token"),
                   submitted, get_current_user() or {})
        return jsonify(message="全部批次及金屬設定已儲存。")
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 批次設定儲存失敗")
        return jsonify(message="設定無法儲存，請稍後再試。"), 503


@icp_data_bp.route("/analysis/icp/export-pdf", methods=["POST"])
@login_required
def export_icp_pdf():
    csrf = str(request.form.get("csrf_token") or "")
    if not csrf or not secrets.compare_digest(csrf, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 403
    if request.form.getlist("work_key") != [session.get("icp_work_key")]:
        return jsonify(message="目前工作已改變，請重新開啟數據頁。"), 409
    key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        expected = str(request.form.get("work_token") or "")
        if expected != work_token(work):
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再匯出。")
        channels, lookup_error = _load_icp_channels(work, form)
        config, token = pdf_configuration(work, form, channels)
        if token != request.form.get("configuration_token"):
            raise IcpPfmConflictError("檢測設定或配對狀態已變更，請重新載入後再匯出。")
        bundles = assemble_pdf_channels(work, channels, request.form.getlist("channels"), config, lookup_error)
        saved_pfm = work.get("pfm_manual") or {}
        try:
            control = load_icp_pfm_control(form)
            pfm_current = bool(saved_pfm and saved_pfm.get("control") == control)
        except Exception:
            pfm_current = False
        from services.icp_pdf_renderer import build_icp_pdf
        output = build_icp_pdf(form, bundles, saved_pfm, pfm_current)
        # Never deliver an output made from a work changed during generation.
        latest = load_icp_work_state(key)
        if not isinstance(latest, dict) or work_token(latest) != expected:
            raise IcpPfmConflictError("匯出期間工作已更新，請重新載入後再匯出。")
        response = send_file(output, mimetype="application/pdf", as_attachment=True,
                             download_name="ICP_Analysis_Record.pdf", max_age=0)
        response.headers["Cache-Control"] = "no-store"
        return response
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 檢驗紀錄 PDF 匯出失敗")
        return jsonify(message="PDF 無法產生，請確認紀錄表設定與字型，或稍後重試。"), 503


@icp_data_bp.route("/analysis/icp/export-excel", methods=["POST"])
@login_required
def export_icp_excel():
    csrf = str(request.form.get("csrf_token") or "")
    if not csrf or not secrets.compare_digest(csrf, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 403
    if request.form.getlist("work_key") != [session.get("icp_work_key")]:
        return jsonify(message="目前工作已改變，請重新開啟數據頁。"), 409
    key, work, form, error = _load_icp_context()
    if error:
        return jsonify(message=error[0]), error[1]
    try:
        expected = str(request.form.get("work_token") or "")
        if expected != work_token(work):
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再匯出。")
        channels, lookup_error = _load_icp_channels(work, form)
        config, token = pdf_configuration(work, form, channels)
        if token != request.form.get("configuration_token"):
            raise IcpPfmConflictError("檢測設定或配對狀態已變更，請重新載入後再匯出。")
        from exports.icp_lims_mapper import build_icp_lims_export_data
        from exports.lims_excel_exporter import build_lims_excel
        export, analysis_method = build_icp_lims_export_data(work, channels,
            request.form.getlist("channels"), config, lookup_error)
        template = os.path.join(current_app.root_path, "resources", "lims", "lims匯入表格.xlsx")
        if not os.path.isfile(template):
            raise ValueError("找不到 LIMS Excel 範本：resources/lims/lims匯入表格.xlsx。")
        actor = get_current_user() or {}
        output = build_lims_excel(template, export,
            analyst_id=str(actor.get("employee_id") or "").strip(),
            analyst_name=str(actor.get("employee_name") or "").strip(),
            analysis_method=analysis_method)
        latest = load_icp_work_state(key)
        if not isinstance(latest, dict) or work_token(latest) != expected:
            raise IcpPfmConflictError("匯出期間工作已更新，請重新載入後再匯出。")
        response = send_file(output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True, download_name="ICP_LIMS_Import.xlsx", max_age=0)
        response.headers["Cache-Control"] = "no-store"
        return response
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP LIMS Excel 匯出失敗")
        return jsonify(message="Excel 無法產生，請確認範本或稍後重試。"), 503


@icp_data_bp.before_app_request
def protect_formal_icp_work():
    """Prevent old ICP forms from editing submitted work through another route."""
    if request.method != "POST" or not request.path.startswith("/analysis/icp/"):
        return None
    # Import always creates a new key; exports only read immutable snapshots.
    if request.path in {"/analysis/icp/import", "/analysis/icp/export-pdf", "/analysis/icp/export-excel"} or request.path.startswith("/analysis/icp/records/"):
        return None
    key = request.form.get("work_key") if request.path.endswith(("/open-work", "/delete-work")) else session.get("icp_work_key")
    work = load_icp_work_state(key) if key else None
    if not work:
        return None
    from services.icp_record_service import check_editable
    try:
        check_editable(work, get_current_user() or {})
    except (PermissionError, IcpPfmConflictError) as exc:
        # Fetch clients show this as a message window. Ordinary forms stay on their page.
        if request.path.endswith("/open-work"):
            return render_template("icp_work_message.html", message=str(exc)), 409
        return jsonify(message=str(exc)), 409
    return None


@icp_data_bp.route("/analysis/icp/save-record", methods=["POST"])
@login_required
def save_icp_record():
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_pfm_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 400
    if request.form.getlist("work_key") != [session.get("icp_work_key")]:
        return jsonify(message="目前工作已變更，請重新載入。"), 409
    from database import SessionLocal
    from services.icp_record_service import submit_icp_record
    db = SessionLocal()
    try:
        key, work, form, error = _load_icp_context()
        if error:
            return jsonify(message=error[0]), error[1]
        expected = str(request.form.get("work_token") or "")
        if expected != work_token(work):
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存。")
        channels, lookup_error = _load_icp_channels(work, form)
        configs, config_token = pdf_configuration(work, form, channels)
        if request.form.get("configuration_token") != config_token:
            raise IcpPfmConflictError("設定或 LIMS 配對已更新，請重新載入確認後再儲存。")
        control = load_icp_pfm_control(form)
        if (work.get("pfm_manual") or {}).get("control") != control:
            raise ValueError("PFM 尚未儲存或管制設定已變更，請先重新計算並儲存 PFM。")
        bundles = assemble_pdf_channels(work, channels, [c["key"] for c in channels], configs, lookup_error)
        result = submit_icp_record(db, key, expected, work, channels, configs, bundles, get_current_user() or {})
        db.commit()
        return jsonify(message="分析紀錄已儲存，狀態為待審核。", redirect_url=url_for(
            "analysis_record_detail", analysis_id=result["analysis_id"]))
    except PermissionError as exc:
        db.rollback()
        return jsonify(message=str(exc)), 403
    except IcpPfmConflictError as exc:
        db.rollback()
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        db.rollback()
        return jsonify(message=str(exc)), 400
    except Exception:
        db.rollback()
        current_app.logger.exception("ICP 正式紀錄儲存失敗")
        return jsonify(message="正式紀錄未完成儲存，暫存工作已保留；請查看服務端錯誤紀錄。"), 503
    finally:
        db.close()


@icp_data_bp.route("/analysis/icp/records/<analysis_id>/export/<kind>", methods=["POST"])
@login_required
def export_icp_formal(analysis_id, kind):
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_record_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 400
    from database import SessionLocal
    from models import AnalysisRecord
    from services.icp_record_service import load_snapshot, selected_bundles, SOURCE
    db = SessionLocal()
    try:
        record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == analysis_id).one_or_none()
        if record is None or record.source_type != SOURCE:
            return jsonify(message="查無此 ICP 正式紀錄。"), 404
        snapshot = load_snapshot(db, record)
        if request.form.get("snapshot_token") != work_token(snapshot):
            raise IcpPfmConflictError("正式紀錄已更新，請重新載入後再匯出。")
        keys = request.form.getlist("channels")
        bundles = selected_bundles(snapshot, keys)
        work = snapshot["work"]
        if kind == "pdf":
            from services.icp_pdf_renderer import build_icp_pdf
            buffer = build_icp_pdf(work["form_data"], bundles, work["pfm_manual"], True)
            mime, filename = "application/pdf", "ICP_Record.pdf"
        elif kind == "excel":
            from services.icp_record_service import frozen_lims_export
            from exports.lims_excel_exporter import build_lims_excel
            output, method = frozen_lims_export(snapshot, keys)
            template = os.path.join(current_app.root_path, "resources", "lims", "lims匯入表格.xlsx")
            buffer = build_lims_excel(template, output, analyst_id=record.analyst_employee_id,
                                      analyst_name=record.analyst_name, analysis_method=method)
            mime, filename = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "ICP_LIMS_Import.xlsx"
        else:
            raise ValueError("不支援的匯出格式。")
        # Recheck the persisted snapshot after generation; never export a stale revision silently.
        db.expire_all()
        if work_token(load_snapshot(db, record)) != work_token(snapshot):
            raise IcpPfmConflictError("匯出期間正式紀錄已更新，請重新載入。")
        response = send_file(buffer, mimetype=mime, as_attachment=True, download_name=filename)
        response.headers["Cache-Control"] = "no-store"
        return response
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 正式紀錄匯出失敗")
        return jsonify(message="無法產生匯出檔案，請查看服務端錯誤紀錄。"), 503
    finally:
        db.close()
