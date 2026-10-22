"""ICP formal records. All writes belong to the caller's transaction."""
import json
from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from sqlalchemy import update
from models import (AnalysisRecord, AnalysisWorkState, AnalysisReviewHistory,
                    IcpImportWorkState, PerformanceAnalysisLink)
from services.icp_performance_service import work_token, IcpPfmConflictError

SOURCE = "ICP_IMPORT"
SCHEMA = "ICP_RECORD_V1"


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def actor_id(actor):
    value = str((actor or {}).get("user_id") or "").strip()
    if not value:
        raise PermissionError("尚未取得登入者帳號。")
    return value


def check_editable(work, actor):
    """Old unowned drafts remain compatible; formal work has an explicit editor."""
    user = actor_id(actor)
    if work.get("formal_status") == "SUBMITTED":
        raise IcpPfmConflictError("此工作已送出待審核，目前不可修改。")
    if work.get("formal_status") == "DELETED":
        raise IcpPfmConflictError("此正式紀錄已刪除，目前不可修改。")
    owner = str(work.get("owner_user_id") or "")
    editor = str(work.get("editor_user_id") or owner)
    if editor and user != editor:
        raise PermissionError("此工作由其他使用者處理，請從有權限的退回紀錄進入修正。")
    return user


def load_snapshot(db, record):
    row = db.query(AnalysisWorkState).filter(
        AnalysisWorkState.analysis_id == record.analysis_id).one_or_none()
    if row is None:
        raise ValueError("此 ICP 紀錄缺少正式快照。")
    snapshot = json.loads(row.state_json)
    if snapshot.get("schema") != SCHEMA or not snapshot.get("bundles"):
        raise ValueError("ICP 正式快照格式異常。")
    return snapshot


def _date(form, name):
    try:
        return datetime.strptime(str(form.get(name) or "").replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("基本資料日期格式不正確：" + name)


def _history(db, record, action, before, after, actor, comment):
    db.add(AnalysisReviewHistory(
        analysis_id=record.analysis_id, action=action, from_status=before, to_status=after,
        reviewer_user_id=actor_id(actor), reviewer_employee_id=str(actor.get("employee_id") or ""),
        reviewer_name=str(actor.get("employee_name") or ""), comment=comment))


def submit_icp_record(db, key, expected_token, work, channels, configs, bundles, actor):
    """Validate prepared views, CAS work, save frozen results and link PFM atomically."""
    user = check_editable(work, actor)
    row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == key).one_or_none()
    if row is None or work_token(json.loads(row.state_json)) != expected_token or work_token(work) != expected_token:
        raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存。")
    original = row.state_json
    if not bundles or {b["key"] for b in bundles} != {c["key"] for c in channels}:
        raise ValueError("必須完整儲存本工作所有採用的金屬與波長。")
    for bundle in bundles:
        for batch in bundle["batches"]:
            if not batch["qaqc"].get("ready"):
                raise ValueError(bundle["label"] + "：QA/QC 尚有無法判定的資料，請先確認。")
    bundles = deepcopy(bundles)
    from services.icp_pdf_renderer import interpretation
    for channel in bundles:
        for batch in channel["batches"]:
            for sample in batch["rows"]:
                sample["interpretation_text"] = interpretation(sample)
    form = deepcopy(work["form_data"])
    start, end, day = _date(form, "analysis_start_date"), _date(form, "analysis_end_date"), _date(form, "form_date")
    if end < start:
        raise ValueError("分析日期迄不可早於分析日期起。")
    formal_id = str(work.get("formal_analysis_id") or "")
    record = None
    if formal_id:
        record = db.query(AnalysisRecord).filter(AnalysisRecord.analysis_id == formal_id).with_for_update().one_or_none()
        if record is None or record.source_type != SOURCE or record.status != "REJECTED":
            raise IcpPfmConflictError("只有原本退回的 ICP 正式紀錄可以重新送審。")
        previous = load_snapshot(db, record)
        if previous.get("work_key") != key or record.analyst_user_id != work.get("owner_user_id"):
            raise PermissionError("工作與原正式紀錄的識別不一致。")
    pending = deepcopy(work)
    formal_id = formal_id or str(uuid4())
    pending.update(formal_analysis_id=formal_id, formal_status="SUBMITTED",
                   owner_user_id=work.get("owner_user_id") or user, editor_user_id=user)
    # First database write serializes the work before any record/PFM writes.
    changed = db.execute(update(IcpImportWorkState).where(
        IcpImportWorkState.work_key == key, IcpImportWorkState.state_json == original,
    ).values(state_json=dumps(pending)))
    if changed.rowcount != 1:
        raise IcpPfmConflictError("工作已由其他頁面更新，本次未儲存。")
    if record is None:
        record = AnalysisRecord(analysis_id=formal_id,
            analyst_user_id=user, analyst_employee_id=str(actor.get("employee_id") or ""),
            analyst_name=str(actor.get("employee_name") or ""))
        db.add(record)
    else:
        _history(db, record, "RESUBMIT", "REJECTED", "UNDER_REVIEW", actor, "ICP 工作修正後重新送審。")
    categories = sorted({b["category"] for c in bundles for b in c["batches"]})
    record.status = "UNDER_REVIEW"
    record.ctrl_year = str(form.get("ctrl_year") or start.year)
    record.category = categories[0] if len(categories) == 1 else "MULTI"
    record.exam_no = "ICP_MULTI"
    record.exam_name = "ICP 多金屬（{} 組金屬／波長）".format(len(bundles))
    record.method_code = str(form.get("method_code") or "")
    record.method_name = record.method_code
    record.instrument_id = str(form.get("instrument_id") or "")
    record.instrument_model = str(form.get("instrument_model") or "")
    record.form_date, record.analysis_start_date, record.analysis_end_date = day, start, end
    record.wavelength = None
    record.source_type, record.source_filename = SOURCE, str(work.get("source_filename") or "")
    record.reviewer_user_id = record.reviewer_employee_id = record.reviewer_name = record.review_comment = ""
    record.reviewed_at = None
    from services.icp_pfm_history_service import sync_icp_pfm_history
    pfm = pending.get("pfm_manual") or {}
    if not pfm:
        raise ValueError("請先計算並儲存本工作的 PFM。")
    event_id = sync_icp_pfm_history(db, key, pfm, pfm)
    if pfm.get("history_event_id") != event_id:
        raise IcpPfmConflictError("PFM 歷程關聯已變更，請先重新儲存 PFM。")
    db.flush()
    db.query(PerformanceAnalysisLink).filter(PerformanceAnalysisLink.analysis_id == formal_id).delete(synchronize_session=False)
    db.add(PerformanceAnalysisLink(analysis_id=formal_id, performance_id=event_id, prm_sequence_no=1))
    # Freeze each channel's LIMS values as well. Export never recalculates historic results.
    from dataclasses import asdict
    from exports.icp_lims_mapper import build_icp_lims_export_data
    lims_exports = {}
    for channel in channels:
        try:
            output, method = build_icp_lims_export_data(work, channels, [channel["key"]], configs)
            lims_exports[channel["key"]] = {"data": asdict(output), "method": method}
        except ValueError as exc:
            lims_exports[channel["key"]] = {"error": str(exc)}
    snapshot = {"schema": SCHEMA, "work_key": key, "work": pending, "lims_exports": lims_exports,
                "channels": deepcopy(channels), "configurations": deepcopy(configs), "bundles": deepcopy(bundles),
                "categories": categories, "search_categories": [{"category": c} for c in categories], "channel_labels": [c["label"] for c in bundles],
                "saved_by": {k: str(actor.get(k) or "") for k in ("user_id", "employee_id", "employee_name")}, "saved_at_utc": datetime.utcnow().isoformat(timespec="seconds")}
    state = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == formal_id).one_or_none()
    if state is None:
        state = AnalysisWorkState(analysis_id=formal_id)
        db.add(state)
    state.method_code, state.state_json, state.form_data_json = record.method_code, dumps(snapshot), dumps(form)
    state.control_data_json = dumps({c["key"]: {str(b["number"]): b["setting"]["control"] for b in c["batches"]} for c in bundles})
    state.method_data_json = dumps({c["key"]: {str(b["number"]): b["setting"]["method"] for b in c["batches"]} for c in bundles})
    state.report_data_json = dumps({"channel_labels": [c["label"] for c in bundles], "exam_names": sorted({str(b["setting"]["control"].get("EXAMNAME") or "") for c in bundles for b in c["batches"]}), "reports": {c["key"]: {str(b["number"]): b["report"] for b in c["batches"]} for c in bundles}})
    db.flush()
    return {"analysis_id": formal_id, "record_id": record.id, "status": record.status}


def resume_icp_record(db, record, actor, reviewer):
    user = actor_id(actor)
    if record.source_type != SOURCE or record.status != "REJECTED":
        raise ValueError("只有退回的 ICP 紀錄可以恢復修正。")
    if user != record.analyst_user_id and not reviewer:
        raise PermissionError("沒有權限恢復此分析紀錄。")
    snapshot = load_snapshot(db, record)
    key = snapshot["work_key"]
    row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == key).with_for_update().one_or_none()
    if row is None:
        raise ValueError("找不到原 ICP 工作；請先確認資料，無法自動重建。")
    original = row.state_json
    work = json.loads(original)
    if work.get("formal_analysis_id") != record.analysis_id:
        raise ValueError("ICP 工作與正式紀錄關聯不一致。")
    if work.get("formal_status") == "EDITING":
        check_editable(work, actor)
        return key, work
    if work.get("formal_status") != "SUBMITTED":
        raise ValueError("目前工作狀態不可修正。")
    work.update(formal_status="EDITING", editor_user_id=user,
                resume_nonce=uuid4().hex)
    result = db.execute(update(IcpImportWorkState).where(
        IcpImportWorkState.work_key == key, IcpImportWorkState.state_json == original,
    ).values(state_json=dumps(work)))
    if result.rowcount != 1:
        raise IcpPfmConflictError("工作已更新，請重新進入修正。")
    _history(db, record, "RESUME_ICP", "REJECTED", "REJECTED", actor, "開啟 ICP 工作修正；原分析員身分保留。")
    db.flush()
    return key, work


def selected_bundles(snapshot, keys):
    available = {c["key"] for c in snapshot["bundles"]}
    if not keys or len(keys) != len(set(keys)) or any(k not in available for k in keys):
        raise ValueError("請選擇正式紀錄中的金屬與波長，且不可重複。")
    return [deepcopy(c) for c in snapshot["bundles"] if c["key"] in keys]


def frozen_lims_export(snapshot, keys):
    from exports.lims_export_model import LimsExportData, LimsQcRow, LimsAnalysisRow
    bundles = selected_bundles(snapshot, keys)
    result, methods, batches, samples = LimsExportData(), set(), set(), set()
    for bundle in bundles:
        payload = snapshot.get("lims_exports", {}).get(bundle["key"], {})
        if payload.get("error") or not payload.get("data"):
            raise ValueError(bundle["label"] + "：" + str(payload.get("error") or "缺少 LIMS 正式匯出快照。"))
        for row in payload["data"]["qc_rows"]:
            identity = (row["batch_no"], row["exam_no"])
            if identity in batches:
                raise ValueError("同一批次、同一檢測代碼只能選擇一個波長，請調整匯出選項。")
            batches.add(identity)
            result.qc_rows.append(LimsQcRow(**row))
        for row in payload["data"]["analysis_rows"]:
            identity = (row["sample_id"], row["exam_no"])
            if identity in samples:
                raise ValueError("相同樣品與檢測代碼具有多筆結果，請調整匯出選項。")
            samples.add(identity)
            result.analysis_rows.append(LimsAnalysisRow(**row))
        methods.add(payload["method"])
    return result, "、".join(sorted(methods))
