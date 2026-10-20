"""Submit one draft revision using the caller's transaction.

The caller must commit on success and roll back on any exception.
This service never commits, rolls back, or closes the supplied session.
"""

from copy import deepcopy

from analysis.analysis_work_draft_repository import (
    AnalysisWorkDraftRepository,
    DraftConflictError,
)
from models import AnalysisRecord
from services.analysis_record_service import save_analysis_record
from services.qaqc_export_service import validate_qaqc_export_ready


def submit_analysis_work(
    db,
    work_id,
    method_code,
    expected_revision,
    current_user,
):
    user = dict(current_user or {})
    user_id = str(user.get("user_id") or "").strip()
    method = str(method_code or "").strip().upper()

    if not user_id:
        raise PermissionError("尚未取得登入者帳號。")

    if not method:
        raise ValueError("尚未指定分析方法。")

    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("工作版本格式不正確。")

    repo = AnalysisWorkDraftRepository(db)
    bundle = repo.load_draft(work_id, user_id, method)

    if bundle["work_status"] != "EDITING":
        raise ValueError("此工作目前不可送審。")

    if bundle["revision"] != expected_revision:
        raise DraftConflictError("工作已更新，請重新載入後再送審。")

    form_data = bundle["form_data"]
    form_method = str(
        form_data.get("method_code") or ""
    ).strip().upper()

    if form_method != method:
        raise ValueError("基本資料與工作分析方法不一致。")

    state = deepcopy(bundle["state"])
    linked_id = str(bundle["formal_analysis_id"] or "").strip()
    state_id = str(state.get("formal_analysis_id") or "").strip()

    if state_id and state_id != linked_id:
        raise ValueError("工作狀態與 Draft 的正式紀錄關聯不一致。")

    if linked_id:
        record = db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == linked_id
        ).first()

        if record is None:
            raise ValueError("工作關聯的正式分析紀錄不存在。")

        if str(record.analyst_user_id or "").strip() != user_id:
            raise PermissionError("無權更新此正式分析紀錄。")

        if str(record.method_code or "").strip().upper() != method:
            raise ValueError("正式分析紀錄的方法不一致。")

        if record.status != "REJECTED":
            raise ValueError("只有退回的正式分析紀錄可重新送審。")

        state["formal_analysis_id"] = linked_id
    else:
        state.pop("formal_analysis_id", None)

    ready, error = validate_qaqc_export_ready(
        state.get("qaqc_results", []),
        has_control_data=bool(bundle["control_data"]),
    )

    if not ready:
        raise ValueError(
            str(error).replace("不可匯出", "不可儲存正式分析紀錄")
        )

    result = save_analysis_record(
        form_data=deepcopy(form_data),
        control_data=deepcopy(bundle["control_data"]),
        method_data=deepcopy(bundle["method_data"]),
        report_data=deepcopy(bundle["report_data"]),
        analysis_state=state,
        current_user=user,
        db=db,
    )

    next_revision = repo.submit_draft(
        work_id=bundle["work_id"],
        user_id=user_id,
        method_code=method,
        expected_revision=expected_revision,
        formal_analysis_id=result["analysis_id"],
    )

    response = dict(result)
    response["work_id"] = bundle["work_id"]
    response["revision"] = next_revision
    response["work_status"] = "SUBMITTED"
    return response
