from flask import (
    Blueprint,
    current_app,
    redirect,
    request,
    session,
    url_for,
)

from auth_session import login_required

from analysis.icp_workflow import (
    build_icp_candidate_selections,
    build_sample_candidate_groups,
)

from analysis.icp_state_repository import (
    load_icp_work_state,
    save_icp_work_state,
)


icp_candidate_selection_bp = Blueprint(
    "icp_candidate_selection_bp",
    __name__,
)


def load_basic_info_data(form_data):
    loader = current_app.extensions[
        "phyon_load_basic_info_data"
    ]
    return loader(form_data)


@icp_candidate_selection_bp.route(
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
        current_app.logger.exception(
            "ICP 候選倍數批次儲存失敗"
        )
        return "候選倍數儲存失敗。", 500

    return redirect(
        url_for(
            "analysis_icp_import",
            tab="candidates"
        )
    )
