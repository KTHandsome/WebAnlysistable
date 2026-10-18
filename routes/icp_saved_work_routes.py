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

