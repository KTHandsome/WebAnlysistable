"""W427 drafts: five-section snapshots, caller-owned transaction, immutable raw data."""
import json
from copy import deepcopy
from sqlalchemy.exc import IntegrityError
from models import AnalysisWorkDraft, AnalysisRecord
from analysis.analysis_work_access import resolve_work_owner
from analysis.analysis_work_identity import AnalysisWorkIdentity
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError


def load_w427_draft(db, work_id, user_id, allow_submitted=False):
    draft = db.query(AnalysisWorkDraft).filter(AnalysisWorkDraft.work_id == work_id).first()
    if draft is None:
        raise ValueError("查無此 W427 分析工作。")
    owner = resolve_work_owner(db, draft, user_id, "W427")
    bundle = AnalysisWorkDraftRepository(db).load_draft(work_id, owner, "W427")
    if bundle["work_status"] != "EDITING":
        if not allow_submitted or bundle["work_status"] != "SUBMITTED":
            raise ValueError("此工作已送出，目前不可修改。")
    elif bundle["formal_analysis_id"]:
        record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == bundle["formal_analysis_id"]).one()
        if record.status != "REJECTED":
            raise ValueError("只有退回的分析紀錄可重新修正。")
    bundle["owner_user_id"] = owner
    state = bundle["state"]
    if (state.get("w427_format") != 1 or not isinstance(state.get("preview"), dict)
            or not isinstance(state.get("parsed_data"), dict)
            or not isinstance(state.get("analysis_state"), dict)):
        raise ValueError("W427 暫存內容格式不符，請先保留資料。")
    if (bundle["form_data"].get("method_code") != "W427"
            or bundle["method_data"].get("METHOD_CODE") != "W427"):
        raise ValueError("暫存工作的分析方法不一致。")
    return bundle


def save_w427_draft(db, user_id, work_id, revision, original, preview, analysis,
                    form, control, method, report):
    repo = AnalysisWorkDraftRepository(db)
    if revision is None:
        if db.query(AnalysisWorkDraft.id).filter(AnalysisWorkDraft.work_id == work_id).first():
            raise DraftConflictError("此工作已暫存，請重新載入，勿重複送出。")
        identity = AnalysisWorkIdentity(work_id=work_id, owner_user_id=user_id, method_code="W427")
        try:
            repo.create_draft(identity, {"parsed_data":deepcopy(original)})
        except IntegrityError as exc:
            raise DraftConflictError("建立暫存工作發生衝突，請重新載入後再操作。") from exc
        expected = 0
    else:
        if type(revision) is not int or revision < 0:
            raise ValueError("工作版本格式無效，請重新載入。")
        current = load_w427_draft(db, work_id, user_id)
        if current["revision"] != revision:
            raise DraftConflictError("此頁面已不是最新版本，請重新載入後再操作。")
        if current["state"]["parsed_data"] != original:
            raise ValueError("原始儀器資料不可覆寫。")
        for name, value in (("form_data",form), ("control_data",control),
                            ("method_data",method), ("report_data",report)):
            if current[name] != value:
                raise ValueError("工作設定快照不一致，請重新載入。")
        user_id = current["owner_user_id"]
        expected = revision
    state = {"w427_format":1, "parsed_data":deepcopy(original), "preview":deepcopy(preview),
             "analysis_state":deepcopy(analysis)}
    if revision is not None and current["formal_analysis_id"]:
        state["formal_analysis_id"] = current["formal_analysis_id"]
    next_revision = repo.save_work_bundle(work_id, user_id, "W427", expected_revision=expected,
        state=state, form_data=form, control_data=control, method_data=method, report_data=report)
    return {"work_id":work_id, "revision":next_revision}


def _source_label(state):
    preview = state.get("parsed_data", {}) if isinstance(state, dict) else {}
    if not isinstance(preview, dict):
        return "W427 分析資料"
    names = []
    for row in preview.get("rows", []):
        if isinstance(row, dict) and row.get("role") == "SAMPLE":
            name = str(row.get("source_file") or "").strip()
            if name and name not in names:
                names.append(name)
    if not names:
        for source in preview.get("sources", []):
            if isinstance(source, dict):
                name = str(source.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
    if not names:
        return "W427 分析資料"
    return names[0] if len(names) == 1 else names[0] + " 等 {} 個來源檔".format(len(names))


def list_w427_drafts(db, user_id):
    rows = db.query(AnalysisWorkDraft.work_id, AnalysisWorkDraft.updated_at,
                    AnalysisWorkDraft.form_data_json).filter(
        AnalysisWorkDraft.owner_user_id == user_id, AnalysisWorkDraft.method_code == "W427",
        AnalysisWorkDraft.work_status == "EDITING", AnalysisWorkDraft.formal_analysis_id.is_(None),
    ).order_by(AnalysisWorkDraft.updated_at.desc(), AnalysisWorkDraft.id.desc()).limit(50).all()
    result = []
    for work_id, updated_at, content in rows:
        try:
            form = json.loads(content)
        except (TypeError, ValueError):
            form = {}
        if not isinstance(form, dict):
            form = {}
        # Materialize one large state at a time (Firebird Text conversion stays in the model).
        text = db.query(AnalysisWorkDraft.state_json).filter(
            AnalysisWorkDraft.work_id == work_id, AnalysisWorkDraft.owner_user_id == user_id,
            AnalysisWorkDraft.method_code == "W427").scalar()
        try:
            state = json.loads(text or "{}")
        except (TypeError, ValueError):
            state = {}
        result.append({"work_id":work_id, "updated_at":str(updated_at or ""),
            "source_label":_source_label(state), "category":form.get("category", ""),
            "exam_name":form.get("exam_name", ""), "exam_no":form.get("selected_exam_no", ""),
            "instrument_id":form.get("instrument_id", ""),
            "analysis_start_date":form.get("analysis_start_date", "")})
    return result
