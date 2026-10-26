"""W427 import, snapshot drafts and explicit PFM history using caller transactions."""
import os
import secrets
import hmac
import json
from copy import deepcopy
from functools import partial
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import Blueprint, render_template, request, session, current_app, jsonify, redirect, url_for, send_file
from auth_session import login_required, get_current_user
from database import SessionLocal
from analysis.analysis_work_identity import create_work_identity
from analysis.analysis_work_draft_repository import DraftConflictError
from services.performance_query_service import find_active_performance_control
from services.w427_performance_service import evaluate_w427_performance
from services.w427_pfm_history_service import save_w427_pfm_history
from services.w427_setting_service import load_w427_settings
from services.w427_calibration_service import build_w427_calibration
from services.w427_sample_service import build_w427_samples
from services.w427_qaqc_service import build_w427_qaqc
from services.w427_sample_edit_service import edit_w427_samples
from services.w427_draft_service import load_w427_draft, save_w427_draft, list_w427_drafts
from services.report_setting_service import load_report_setting
from services.w427_record_service import submit_w427_record, apply_w427_remarks, w427_remarks
from services.basic_info_service import get_instrument_import_type
from parsers.w427_txt_parser import build_w427_preview, MAX_FILE_BYTES

w427_import_bp = Blueprint("w427_import_bp", __name__)


def _serializer(salt):
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


def _decode(salt, value, owner, csrf):
    try:
        payload = _serializer(salt).loads(value, max_age=7200)
    except (BadSignature, SignatureExpired):
        raise ValueError("頁面已失效，請重新載入暫存工作，或重新匯入未暫存資料。")
    if not isinstance(payload, dict) or payload.get("owner") != owner or payload.get("csrf") != csrf:
        raise PermissionError("登入者已變更或此工作不屬於目前登入者，請重新開啟。")
    form = payload.get("form")
    if not isinstance(form, dict) or str(form.get("method_code") or "").strip().upper() != "W427":
        raise ValueError("分析方法不符，請重新開啟。")
    return payload


def _check_form(form, control=None):
    exam = control.get("EXAMNO") if control else form.get("selected_exam_no")
    if request.form.get("exam_no") != exam or request.form.get("instrument_id") != form.get("instrument_id"):
        raise ValueError("分析基本資料不一致，請重新開啟。")


def _evaluate(preview, form, method, control, pfm=None):
    calibration = build_w427_calibration(preview, method)
    samples = build_w427_samples(preview, calibration["calibration_result"], calibration["method_data"], control)
    qaqc = build_w427_qaqc(preview, samples, calibration["calibration_result"], samples["method_data"], control)
    results = (evaluate_w427_performance(preview["performance_rows"], form,
               partial(find_active_performance_control, SessionLocal)) if pfm is None else deepcopy(pfm))
    return apply_w427_remarks({"calibration":calibration, "samples":samples, "qaqc":qaqc, "prm_results":results}, {})


@w427_import_bp.route("/analysis/w427/import", methods=["GET", "POST"])
@login_required
def import_w427():
    form = dict(session.get("basic_info_form") or {})
    control, method, report, error = {}, {}, {}, None
    preview = original = None
    analysis = {}
    work_id = revision = None
    status, notice = 200, ""
    pfm_token = preview_token = import_token = None
    works = []
    settings_ready = False
    submitted, formal_analysis_id = False, None
    action = request.form.get("action", "import") if request.method == "POST" else "load"
    owner = str((get_current_user() or {}).get("user_id") or "").strip()
    token = session.get("w427_import_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["w427_import_csrf"] = token
    try:
        if not owner:
            raise PermissionError("尚未取得登入者帳號，請重新登入。")
        if request.method == "POST":
            if not hmac.compare_digest(request.form.get("csrf_token", ""), token):
                raise ValueError("頁面驗證失效，請重新開啟。")
        if action == "save_pfm":
            payload = _decode("w427-pfm-v1", request.form.get("pfm_token", ""), owner, token)
            form = payload["form"]
            _check_form(form)
            checked = evaluate_w427_performance(payload["rows"], form, partial(find_active_performance_control, SessionLocal))
            if checked != payload["results"]:
                raise ValueError("PFM 管制設定已變更，請重新匯入確認。")
            with SessionLocal() as db:
                try:
                    count = save_w427_pfm_history(db, checked)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            return jsonify(message="PFM 已儲存（{} 筆；相同紀錄不重複新增）。".format(count))
        with SessionLocal() as db:
            works = list_w427_drafts(db, owner)
        if action in {"recalculate_samples", "save_draft", "submit_record", "export_pdf", "export_excel"}:
            payload = _decode("w427-draft-v1", request.form.get("preview_token", ""), owner, token)
            form, method, control, report = (deepcopy(payload[k]) for k in ("form", "method", "control", "report"))
            _check_form(form, control)
            work_id, revision = payload["work_id"], payload["revision"]
            current = None
            if revision is not None:
                with SessionLocal() as db:
                    current = load_w427_draft(db, work_id, owner)
                if current["revision"] != revision:
                    raise DraftConflictError("此頁面已不是最新版本，請重新載入後再操作。")
                for name, value in (("form_data",form), ("method_data",method),
                                    ("control_data",control), ("report_data",report)):
                    if current[name] != value:
                        raise ValueError("工作設定快照不一致，請重新載入。")
                if current["state"]["parsed_data"] != payload["original"]:
                    raise ValueError("原始儀器資料不可覆寫。")
            preview, original = payload["preview"], payload["original"]
            settings_ready = True
            analysis = _evaluate(preview, form, method, control, payload["pfm"])
            apply_w427_remarks(analysis, payload.get("remarks", {}))
            try:
                edits = json.loads(request.form.get("edits", ""))
            except (ValueError, TypeError):
                raise ValueError("樣品編輯資料格式無效。")
            edited = edit_w427_samples(preview, edits)
            evaluated = _evaluate(edited, form, method, control, payload["pfm"])
            if evaluated["samples"]["sample_error"]:
                raise ValueError(evaluated["samples"]["sample_error"])
            apply_w427_remarks(evaluated, json.loads(request.form.get("batch_remarks", "{}")))
            preview, analysis = edited, evaluated
            if action == "export_excel":
                from services.w427_lims_export_service import build_w427_lims_excel
                actor = dict(get_current_user() or {})
                if current and current["formal_analysis_id"]:
                    from models import AnalysisRecord
                    with SessionLocal() as db:
                        record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == current["formal_analysis_id"]).one()
                        actor = {"employee_id":record.analyst_employee_id, "employee_name":record.analyst_name}
                template_path = os.path.join(current_app.root_path,"resources","lims","lims匯入表格.xlsx")
                output = build_w427_lims_excel(template_path,form,control,method,analysis,preview,actor)
                return send_file(output,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    as_attachment=True,download_name="W427_LIMS_Import.xlsx")
            if action == "export_pdf":
                from services.w427_record_service import _validate
                from services.w427_pdf_renderer import build_w427_pdf
                _validate(analysis)
                output = build_w427_pdf(report, method, control, form, analysis)
                return send_file(output, mimetype="application/pdf", as_attachment=True,
                                 download_name="W427_Analysis_Record.pdf")
            if action == "submit_record":
                with SessionLocal() as db:
                    try:
                        submit_w427_record(db, get_current_user() or {}, work_id, revision, original,
                                           preview, analysis, form, control, method, report)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                return redirect(url_for("w427_import_bp.import_w427", work_id=work_id, formal_saved="1"), code=303)
            if action == "save_draft":
                with SessionLocal() as db:
                    try:
                        saved = save_w427_draft(db, owner, work_id, revision, original, preview,
                                               analysis, form, control, method, report)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                return redirect(url_for("w427_import_bp.import_w427", work_id=saved["work_id"], saved="1"), code=303)
            notice = "計算已更新，尚未暫存本次修改。"
        elif action == "load" and request.args.get("work_id"):
            with SessionLocal() as db:
                bundle = load_w427_draft(db, request.args["work_id"], owner, allow_submitted=True)
            form, method, control, report = (bundle[k] for k in ("form_data", "method_data", "control_data", "report_data"))
            work_id, revision = bundle["work_id"], bundle["revision"]
            preview, original = bundle["state"]["preview"], bundle["state"]["parsed_data"]
            analysis = _evaluate(preview, form, method, control, bundle["state"]["analysis_state"].get("prm_results", []))
            apply_w427_remarks(analysis, w427_remarks(bundle["state"]["analysis_state"]))
            submitted = bundle["work_status"] == "SUBMITTED"
            formal_analysis_id = bundle["formal_analysis_id"]
            settings_ready = True
            notice = "已暫存分析資料。" if request.args.get("saved") == "1" else "已載入暫存分析資料。"
            if submitted:
                notice = "已儲存分析紀錄並送審；本工作已移出暫存清單，目前不可修改。"
        elif action in {"load", "import"}:
            if action == "import":
                payload = _decode("w427-import-v1", request.form.get("import_token", ""), owner, token)
                form = payload["form"]
                _check_form(form)
            if str(form.get("method_code") or "").strip().upper() != "W427":
                raise ValueError("請先在基本資料選擇 W427，或從暫存清單恢復工作。")
            control, method, setting_error = load_w427_settings(form)
            if setting_error:
                raise ValueError(setting_error)
            # Store a canonical basic form in this work; never overwrite the session's active tab.
            form["method_code"] = "W427"
            form["selected_exam_no"] = control["EXAMNO"]
            if not form.get("instrument_id") or get_instrument_import_type(form) != "UV_TXT":
                raise ValueError("請選擇已關聯 W427／UV_TXT 的儀器。")
            report, report_error = load_report_setting(method)
            if report_error:
                raise ValueError(report_error)
            settings_ready = True
            if action == "import":
                uploads = [f for f in request.files.getlist("uv_files") if f.filename]
                if not uploads or len(uploads) > 20:
                    raise ValueError("請選擇 1～20 個 TXT 檔案。")
                files = [(f.filename.replace("\\", "/").split("/")[-1], f.stream.read(MAX_FILE_BYTES + 1)) for f in uploads]
                preview = build_w427_preview(files, str(form["category"]).upper())
                original = deepcopy(preview)
                work_id = create_work_identity(owner, "W427").work_id
                analysis = _evaluate(preview, form, method, control)
                notice = "已匯入並計算，尚未暫存分析工作。"
        else:
            raise ValueError("不支援的操作。")
    except PermissionError as exc:
        error, status = str(exc), 403
    except DraftConflictError as exc:
        error, status = str(exc), 409
    except ValueError as exc:
        error, status = str(exc), 400
    except Exception:
        current_app.logger.exception("W427 分析工作處理失敗")
        error, status = "無法完成 W427 操作，本次未完成儲存；請查看 Server 訊息。", 500
    if action in {"save_pfm", "export_pdf", "export_excel"}:
        return jsonify(message=error), status
    if settings_ready:
        import_token = _serializer("w427-import-v1").dumps({"owner":owner,"csrf":token,"form":form})
    calibration = analysis.get("calibration", {})
    samples = analysis.get("samples", {})
    qaqc = analysis.get("qaqc", {})
    prm_results = analysis.get("prm_results", [])
    if preview is not None and analysis and not submitted:
        if all(r["status"] in {"PASS", "FAIL"} for r in prm_results) and prm_results:
            pfm_token = _serializer("w427-pfm-v1").dumps({"owner":owner, "csrf":token, "form":form,
                "results":prm_results, "rows":[{k:r[k] for k in ("role", "sample_id", "measured_at", "absorbance")}
                                               for r in preview["performance_rows"]]})
        if not samples.get("sample_error") and samples.get("sample_qaqc_rows") and status in {200, 400}:
            preview_token = _serializer("w427-draft-v1").dumps({"owner":owner, "csrf":token, "form":form,
                "method":method, "control":control, "report":report, "work_id":work_id, "revision":revision,
                "preview":preview, "original":original, "pfm":prm_results, "remarks":w427_remarks(analysis)})
    return render_template("methods/w427_import.html", active_page="analysis_method", form_data=form,
        method_data=samples.get("method_data", method), control_data=control, error_message=error,
        preview=preview, csrf_token=token, import_token=import_token, draft_works=works,
        work_id=work_id, work_revision=revision, work_submitted=submitted,
        formal_analysis_id=formal_analysis_id, prm_results=prm_results,
        pfm_token=pfm_token, preview_token=preview_token, work_notice=notice,
        calibration_result=calibration.get("calibration_result"), calibration_rows=calibration.get("calibration_rows", []),
        calibration_error=calibration.get("calibration_error", ""), calibration_warnings=calibration.get("calibration_warnings", []),
        sample_qaqc_rows=samples.get("sample_qaqc_rows", []), sample_warnings=samples.get("sample_warnings", []),
        sample_error=samples.get("sample_error", ""), qdl_value=samples.get("qdl_value"), analysis_mdl=samples.get("mdl"),
        sample_config=samples.get("sample_config", {}), qaqc_3a_results=qaqc.get("qaqc_3a_results", []),
        qaqc_warnings=qaqc.get("qaqc_warnings", [])), status
