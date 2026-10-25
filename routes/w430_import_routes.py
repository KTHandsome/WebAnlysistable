"""W430 import, calculations, explicit draft save/restore and independent PFM save."""
import hashlib
import hmac
import json
import os
import secrets
from functools import partial
from flask import Blueprint, current_app, render_template, request, session, jsonify, redirect, url_for, send_file
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from auth_session import login_required, get_current_user
from database import SessionLocal
from analysis.analysis_work_identity import create_work_identity
from analysis.analysis_work_draft_repository import DraftConflictError
from parsers.uv_txt_parser import MAX_FILE_BYTES, build_w430_preview
from services.basic_info_service import get_instrument_import_type
from services.method_control_service import load_control_and_method_data
from services.report_setting_service import load_report_setting
from services.performance_query_service import find_active_performance_control
from services.w430_analysis_service import build_w430_analysis
from services.w430_performance_service import apply_w430_performance
from services.w430_pfm_history_service import save_w430_pfm_history
from services.w430_sample_edit_service import edit_w430_preview
from services.w430_draft_service import load_w430_draft, save_w430_draft, list_w430_drafts
from services.w430_record_service import submit_w430_record, apply_w430_remarks

w430_import_bp = Blueprint("w430_import_bp", __name__)


def _context(form):
    return hashlib.sha256(json.dumps(form, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _serializer(salt):
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


def _decode(salt, text, user_id, token):
    try:
        payload = _serializer(salt).loads(text, max_age=7200)
    except (BadSignature, SignatureExpired):
        raise ValueError("頁面已失效，請重新載入已暫存工作，或重新匯入未暫存資料。")
    if not isinstance(payload, dict) or payload.get("owner") != user_id or payload.get("csrf") != token:
        raise PermissionError("此分析工作不屬於目前登入者，請重新開啟。")
    return payload


def _evaluate(preview, form, method, control, pfm=None):
    if (str(method.get("METHOD_CODE") or "").strip().upper() != "W430"
            or str(method.get("ANALYSIS_MODE") or "SINGLE").upper() != "SINGLE"
            or str(method.get("IMPORT_TYPE") or "").upper() != "UV_TXT"):
        raise ValueError("W430 方法必須為 W430／SINGLE／UV_TXT。")
    analysis = build_w430_analysis(preview, form, method, control)
    if pfm is None:
        apply_w430_performance(analysis, preview, form, partial(find_active_performance_control, SessionLocal))
    else:
        analysis["prm_results"] = pfm
    return analysis


@w430_import_bp.route("/analysis/w430/import", methods=["GET", "POST"])
@login_required
def import_w430():
    user_id = str((get_current_user() or {}).get("user_id") or "").strip()
    form = dict(session.get("basic_info_form") or {})
    preview = original = None
    analysis, method, control, report = {}, {}, {}, {}
    work_id, revision = None, None
    error, status, notice = None, 200, ""
    preview_token = pfm_token = None
    works = []
    submitted = False
    formal_analysis_id = None
    action = request.form.get("action", "import") if request.method == "POST" else "load"
    token = session.get("w430_import_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["w430_import_csrf"] = token
    try:
        if not user_id:
            raise PermissionError("尚未取得登入者帳號。")
        with SessionLocal() as db:
            works = list_w430_drafts(db, user_id)
        if request.method == "POST":
            if not hmac.compare_digest(request.form.get("csrf_token", ""), token):
                raise ValueError("頁面驗證失效，請重新開啟。")
        if action == "save_pfm":
            payload = _decode("w430-pfm-v2", request.form.get("pfm_token", ""), user_id, token)
            form = payload["form"]
            if not hmac.compare_digest(request.form.get("context_token", ""), _context(form)):
                raise ValueError("PFM 基本資料已變更，請重新載入。")
            checked = {}
            apply_w430_performance(checked, {"rows": payload["rows"]}, form,
                                  partial(find_active_performance_control, SessionLocal))
            if checked["prm_results"] != payload["results"]:
                raise ValueError("PFM 管制設定已變更，請重新載入確認。")
            with SessionLocal() as db:
                try:
                    count = save_w430_pfm_history(db, checked["prm_results"])
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            return jsonify(message="PFM 已儲存（{} 筆；相同紀錄不重複新增）。".format(count))
        if action in {"recalculate_samples", "save_draft", "submit_record", "export_pdf", "export_excel"}:
            payload = _decode("w430-preview-v2", request.form.get("preview_token", ""), user_id, token)
            form, method, control, report = (payload[k] for k in ("form", "method", "control", "report"))
            if not hmac.compare_digest(request.form.get("context_token", ""), _context(form)):
                raise ValueError("分析基本資料已變更，請重新載入。")
            work_id, revision = payload["work_id"], payload["revision"]
            current = None
            if revision is not None:
                with SessionLocal() as db:
                    current = load_w430_draft(db, work_id, user_id)
                if current["revision"] != revision:
                    raise DraftConflictError("此工作已有較新版本，請重新載入後再操作。")
            preview, original = payload["preview"], payload["original"]
            # Restore a usable original preview if an edit is invalid.
            analysis = _evaluate(preview, form, method, control, payload["pfm"])
            edited = edit_w430_preview(preview, json.loads(request.form.get("edits", "null")))
            preview = edited
            analysis = _evaluate(preview, form, method, control, payload["pfm"])
            apply_w430_remarks(analysis, json.loads(request.form.get("batch_remarks", "{}")))
            if action == "export_pdf":
                from services.w430_record_service import _validate
                from services.w430_pdf_renderer import build_w430_pdf
                _validate(analysis)
                pdf_buffer = build_w430_pdf(report, method, control, form, analysis)
                return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True,
                                 download_name="W430_Sulfate_Analysis_Record.pdf")
            if action == "export_excel":
                from services.w430_lims_export_service import build_w430_lims_excel
                actor = dict(get_current_user() or {})
                if current and current["formal_analysis_id"]:
                    from models import AnalysisRecord
                    with SessionLocal() as db:
                        record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == current["formal_analysis_id"]).one()
                        actor = {"employee_id":record.analyst_employee_id, "employee_name":record.analyst_name}
                template_path = os.path.join(current_app.root_path,"resources","lims","lims匯入表格.xlsx")
                excel_buffer = build_w430_lims_excel(template_path, form, control, method, analysis, preview, actor)
                return send_file(excel_buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 as_attachment=True, download_name="W430_LIMS_Import.xlsx")
            if action == "submit_record":
                with SessionLocal() as db:
                    try:
                        result = submit_w430_record(db, get_current_user() or {}, work_id, revision,
                            original, preview, analysis, form, control, method, report)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                return redirect(url_for("w430_import_bp.import_w430", work_id=work_id, formal_saved="1"), code=303)
            if action == "save_draft":
                with SessionLocal() as db:
                    try:
                        saved = save_w430_draft(db, user_id, work_id, revision, original, preview,
                                               analysis, form, control, method, report)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                return redirect(url_for("w430_import_bp.import_w430", work_id=saved["work_id"], saved="1"), code=303)
            notice = "計算已更新，尚未暫存本次修改。"
        else:
            requested_id = request.args.get("work_id")
            if requested_id:
                with SessionLocal() as db:
                    bundle = load_w430_draft(db, requested_id, user_id, allow_submitted=True)
                form, method, control, report = (bundle[k] for k in ("form_data", "method_data", "control_data", "report_data"))
                work_id, revision = bundle["work_id"], bundle["revision"]
                preview, original = bundle["state"]["preview"], bundle["state"]["parsed_data"]
                analysis = _evaluate(preview, form, method, control, bundle["state"]["analysis_state"].get("prm_results", []))
                submitted = bundle["work_status"] == "SUBMITTED"
                formal_analysis_id = bundle["formal_analysis_id"]
                apply_w430_remarks(analysis, {str(b["batch_no"]): b.get("batch_remark", "")
                    for b in bundle["state"]["analysis_state"].get("qaqc_3a_results", [])})
                notice = ("已暫存分析資料" if request.args.get("saved") == "1" else "已載入暫存分析資料") + "\u3002"
                if submitted:
                    notice = "已儲存分析紀錄並送審；本工作已移出暫存清單，目前不可修改。"
            else:
                if str(form.get("method_code") or "").strip().upper() != "W430" or not form.get("instrument_id"):
                    raise ValueError("請先選擇 W430 與 UV 儀器，或從下方清單恢復暫存工作。")
                control, method, setting_error = load_control_and_method_data(form)
                if setting_error or not method:
                    raise ValueError(setting_error or "尚未取得 W430 方法設定。")
                if get_instrument_import_type(form) != "UV_TXT":
                    raise ValueError("儀器關聯的匯入格式須為 UV_TXT。")
                report, report_error = load_report_setting(method)
                if report_error:
                    raise ValueError(report_error)
            if request.method == "POST":
                if submitted:
                    raise ValueError("此工作已送出待審核，請從基本資料建立新工作。")
                if action != "import":
                    raise ValueError("未知的操作。")
                if not hmac.compare_digest(request.form.get("context_token", ""), _context(form)):
                    raise ValueError("基本資料已變更，請重新開啟匯入頁。")
                uploads = [f for f in request.files.getlist("uv_files") if f.filename]
                if not uploads or len(uploads) > 20:
                    raise ValueError("請選擇 1～20 個 TXT 檔案。")
                files = [(f.filename.replace("\\", "/").split("/")[-1], f.stream.read(MAX_FILE_BYTES + 1)) for f in uploads]
                preview = build_w430_preview(files)
                original = preview
                work_id, revision = create_work_identity(user_id, "W430").work_id, None
                analysis = _evaluate(preview, form, method, control)
                notice = "已匯入並計算，尚未暫存分析工作。"
        if method and (str(method.get("ANALYSIS_MODE") or "SINGLE").upper() != "SINGLE"
                       or str(method.get("IMPORT_TYPE") or "").upper() != "UV_TXT"):
            raise ValueError("W430 方法必須為 SINGLE／UV_TXT。")
    except PermissionError as exc:
        error, status = str(exc), 403
    except DraftConflictError as exc:
        error, status = str(exc), 409
    except ValueError as exc:
        error, status = str(exc), 400
    except Exception:
        current_app.logger.exception("W430 工作處理失敗")
        error, status = "無法完成操作，本次操作未完成；請查看 Server 訊息。", 500
    if action == "save_pfm" and error:
        return jsonify(message=error), status
    if preview is not None and analysis and not submitted:
        preview_token = _serializer("w430-preview-v2").dumps({
            "owner": user_id, "csrf": token, "form": form, "method": method, "control": control,
            "report": report, "work_id": work_id, "revision": revision,
            "preview": preview, "original": original, "pfm": analysis.get("prm_results", [])})
        pfm_rows = [{k: r[k] for k in ("role", "sample_id", "measured_at", "absorbance")}
                    for r in preview["rows"] if r["role"] in {"MAX_ABS", "CELL_CHECK", "PFM"}]
        if pfm_rows and all(r["status"] in {"PASS", "FAIL"} for r in analysis["prm_results"]):
            pfm_token = _serializer("w430-pfm-v2").dumps({"owner":user_id, "csrf":token, "form":form,
                                                          "rows":pfm_rows,"results":analysis["prm_results"]})
    return render_template("methods/w430_import.html", active_page="analysis_method",
                           form_data=form, preview=preview, view=analysis, method_data=analysis.get("method_data", method),
                           control_data=control, error_message=error, csrf_token=token, context_token=_context(form),
                           preview_token=preview_token, pfm_token=pfm_token, draft_works=works,
                           work_id=work_id, work_revision=revision, work_notice=notice, work_submitted=submitted, formal_analysis_id=formal_analysis_id), status
