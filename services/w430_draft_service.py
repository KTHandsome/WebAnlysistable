"""W430 drafts use the existing five-section repository and caller transaction."""
import json
from copy import deepcopy
from models import AnalysisWorkDraft, AnalysisRecord
from analysis.analysis_work_access import resolve_work_owner
from analysis.analysis_work_identity import AnalysisWorkIdentity
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError


def load_w430_draft(db, work_id, user_id, allow_submitted=False):
    draft = db.query(AnalysisWorkDraft).filter(AnalysisWorkDraft.work_id == work_id).first()
    if draft is None:
        raise ValueError("查無此 W430 分析工作。")
    owner = resolve_work_owner(db, draft, user_id, "W430")
    bundle = AnalysisWorkDraftRepository(db).load_draft(work_id, owner, "W430")
    if bundle["work_status"] != "EDITING":
        if not allow_submitted or bundle["work_status"] != "SUBMITTED":
            raise ValueError("此工作已送出待審核，目前不可修改。")
    elif bundle["formal_analysis_id"]:
        record = db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == bundle["formal_analysis_id"]).one()
        if record.status != "REJECTED":
            raise ValueError("只有退回的分析紀錄可重新修正。")
    state = bundle["state"]
    if state.get("w430_format") != 1 or not isinstance(state.get("preview"), dict):
        raise ValueError("W430 暫存內容格式不符，請先保留資料。")
    bundle["owner_user_id"] = owner
    return bundle


def save_w430_draft(db, user_id, work_id, revision, original, preview, analysis,
                    form, control, method, report):
    repo = AnalysisWorkDraftRepository(db)
    if revision is None:
        if db.query(AnalysisWorkDraft.id).filter(AnalysisWorkDraft.work_id == work_id).first():
            raise DraftConflictError("此工作已暫存，請從暫存清單重新開啟，勿重複送出。")
        identity = AnalysisWorkIdentity(work_id=work_id, owner_user_id=user_id, method_code="W430")
        repo.create_draft(identity, {"parsed_data": deepcopy(original)})
        expected = 0
    else:
        current = load_w430_draft(db, work_id, user_id)
        if current["revision"] != revision:
            raise DraftConflictError("此工作已有較新版本，請重新載入後再操作。")
        if current["state"].get("parsed_data") != original:
            raise ValueError("原始儀器資料不可覆寫。")
        user_id = current["owner_user_id"]
        expected = revision
    state = {"w430_format": 1, "parsed_data": deepcopy(original),
             "preview": deepcopy(preview), "analysis_state": deepcopy(analysis)}
    if revision is not None and current["formal_analysis_id"]:
        state["formal_analysis_id"] = current["formal_analysis_id"]
    next_revision = repo.save_work_bundle(
        work_id, user_id, "W430", expected_revision=expected,
        state=state, form_data=form, control_data=control, method_data=method, report_data=report)
    return {"work_id": work_id, "revision": next_revision}


def _work_source_label(state):
    """Human label from original sample filenames; identifiers remain internal."""
    if not isinstance(state, dict):
        return "W430 分析資料"
    preview = state.get("parsed_data") or state.get("preview") or {}
    if not isinstance(preview, dict):
        return "W430 分析資料"
    names = []
    rows = preview.get("rows") or []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or row.get("role") != "SAMPLE":
                continue
            name = str(row.get("source_file") or "").strip()
            if name and name not in names:
                names.append(name)
    if not names:
        for source in preview.get("sources") or []:
            if isinstance(source, dict):
                name = str(source.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
    if not names:
        return "W430 分析資料"
    return names[0] if len(names) == 1 else names[0] + " 等 {} 個來源檔".format(len(names))


def list_w430_drafts(db, user_id):
    rows = db.query(AnalysisWorkDraft.work_id, AnalysisWorkDraft.revision,
                    AnalysisWorkDraft.updated_at, AnalysisWorkDraft.form_data_json).filter(
        AnalysisWorkDraft.owner_user_id == user_id,
        AnalysisWorkDraft.method_code == "W430",
        AnalysisWorkDraft.work_status == "EDITING",
        AnalysisWorkDraft.formal_analysis_id.is_(None),
    ).order_by(AnalysisWorkDraft.updated_at.desc(), AnalysisWorkDraft.id.desc()).limit(50).all()
    result = []
    for work_id, revision, updated_at, content in rows:
        try:
            form = json.loads(content)
        except (TypeError, ValueError):
            form = {}
        if not isinstance(form, dict):
            form = {}
        # Read each large JSON independently; do not load all 50 working states into one list.
        state_text = db.query(AnalysisWorkDraft.state_json).filter(
            AnalysisWorkDraft.work_id == work_id,
            AnalysisWorkDraft.owner_user_id == user_id,
            AnalysisWorkDraft.method_code == "W430",
        ).scalar()
        try:
            state = json.loads(state_text or "{}")
        except (TypeError, ValueError):
            state = {}
        result.append({"work_id": work_id, "revision": revision, "updated_at": str(updated_at or ""),
                       "source_label": _work_source_label(state),
                       "instrument_id": form.get("instrument_id", ""),
                       "category": form.get("category", ""), "analysis_start_date": form.get("analysis_start_date", "")})
    return result
