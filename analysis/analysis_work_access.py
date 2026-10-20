"""Server-side actor authorization; repository ownership remains unchanged."""
from flask import has_request_context
from auth_session import get_current_user, can_review_analysis
from models import AnalysisRecord, AnalysisReviewHistory


def is_review_actor(actor_user_id):
    if not has_request_context():
        return False
    user = get_current_user() or {}
    return (bool(str(actor_user_id or "").strip())
            and str(user.get("user_id") or "").strip() == str(actor_user_id).strip()
            and can_review_analysis())


def resolve_work_owner(db, draft, actor_user_id, method_code):
    actor = str(actor_user_id or "").strip()
    owner = str(draft.owner_user_id or "").strip()
    method = str(method_code or "").strip().upper()
    if not actor or not owner or str(draft.method_code or "").strip().upper() != method:
        raise PermissionError("工作使用者或分析方法不一致。")
    linked = str(draft.formal_analysis_id or "").strip()
    if not linked:
        if actor != owner:
            raise PermissionError("尚未送審的工作僅限所有者存取。")
        return owner
    record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == linked).first()
    if (record is None or str(record.analyst_user_id or "").strip() != owner
            or str(record.method_code or "").strip().upper() != method):
        raise PermissionError("工作與原分析紀錄的所有權或方法不一致。")
    if actor != owner:
        if not is_review_actor(actor) or record.status not in {"REJECTED", "UNDER_REVIEW"}:
            raise PermissionError("沒有權限修訂或查看此工作。")
    return owner


def add_work_actor_history(db, analysis_id, action, work_id, revision, status):
    user = get_current_user() or {}
    actor = str(user.get("user_id") or "").strip()
    if not actor:
        raise PermissionError("尚未取得實際操作者。")
    db.add(AnalysisReviewHistory(
        analysis_id=analysis_id, action=action,
        from_status=status, to_status=status,
        reviewer_user_id=actor,
        reviewer_employee_id=str(user.get("employee_id") or "").strip(),
        reviewer_name=str(user.get("employee_name") or "").strip(),
        comment="work_id={}; revision={}".format(work_id, revision),
    ))
