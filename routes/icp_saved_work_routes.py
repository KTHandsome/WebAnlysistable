from flask import (
    Blueprint,
    redirect,
    request,
    session,
    url_for,
)

from auth_session import login_required

from analysis.icp_state_repository import (
    load_icp_work_state,
)


icp_saved_work_bp = Blueprint(
    "icp_saved_work_bp",
    __name__,
)


@icp_saved_work_bp.route(
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

    from services.icp_record_service import check_editable
    from auth_session import get_current_user
    try:
        check_editable(saved_work, get_current_user() or {})
    except (ValueError, PermissionError, RuntimeError) as exc:
        return str(exc), 409

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


@icp_saved_work_bp.app_context_processor
def icp_saved_work_delete_context():
    if request.endpoint != "analysis_icp_import":
        return {}
    import secrets
    session.setdefault("icp_delete_csrf", secrets.token_urlsafe(32))
    return {"icp_delete_csrf": session["icp_delete_csrf"]}


@icp_saved_work_bp.route("/analysis/icp/delete-work", methods=["POST"])
@login_required
def delete_icp_saved_work():
    import secrets
    from flask import jsonify, current_app
    from auth_session import get_current_user
    from analysis.icp_state_repository import delete_icp_work_state
    token = str(request.form.get("csrf_token") or "")
    if not token or not secrets.compare_digest(token, session.get("icp_delete_csrf", "")):
        return jsonify(message="頁面驗證已失效，請重新載入。"), 400
    keys = request.form.getlist("work_key")
    if len(keys) != 1 or not keys[0].startswith("ICP_IMPORT_"):
        return jsonify(message="ICP 工作識別格式不正確。"), 400
    key = keys[0]
    try:
        if not delete_icp_work_state(key, get_current_user() or {}):
            return jsonify(message="此暫存工作已不存在，請重新整理清單。"), 404
        if session.get("icp_work_key") == key:
            session.pop("icp_work_key", None)
        return jsonify(message="暫存工作已刪除。", redirect_url=url_for("analysis_icp_import"))
    except PermissionError as exc:
        return jsonify(message=str(exc)), 403
    except ValueError as exc:
        return jsonify(message=str(exc)), 409
    except Exception:
        current_app.logger.exception("ICP 暫存工作刪除失敗")
        return jsonify(message="暫存工作未完成刪除，請查看服務端紀錄。"), 503
