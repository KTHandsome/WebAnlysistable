from analysis.icp_batch_adoption import context as batch_context, group_is_active, filter_lims_matches
"""Explicit work-only adoption of PDF measurements without a matching LIMS commission."""
import json
import os
import secrets
from copy import deepcopy
from datetime import datetime
from flask import current_app, request, session, jsonify, url_for
from sqlalchemy import update
from database import SessionLocal
from models import IcpImportWorkState
from analysis.icp_state_repository import load_icp_work_state
from analysis.icp_workflow import (build_sample_candidate_groups, build_icp_candidate_selections,
    load_icp_analyte_map, match_lims_icp_analytes, build_icp_lims_matches)
from services.icp_batch_category_service import build_batches, category_catalog
from services.icp_performance_service import work_token, IcpPfmConflictError


def text(v):
    return str(v if v is not None else "").strip()


def match_identity(item):
    return (text(item.get("keepid")).upper(), text(item.get("element")),
            text(item.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper(),
            text(item.get("pdf_sample_tag")).upper())


def allowed_decisions(status):
    if status == "METHOD_MATCHED":
        return {"ACCEPT", "PENDING", "REJECT"}
    if status == "CROSS_METHOD_REVIEW":
        return {"PENDING", "REJECT"}
    return {"REJECT"}


def manual_adoption_options(work, matches):
    if not isinstance(work, dict):
        return {}
    unmatched = {match_identity(m) for m in matches if m.get("status") == "NOT_COMMISSIONED"}
    if not unmatched:
        return {}
    rows = (work.get("parsed_data") or {}).get("rows") or []
    groups = build_icp_candidate_selections(build_sample_candidate_groups(rows), work.get("candidate_selections") or {})
    _, assignments, hidden = batch_context(work)
    stored = work.get("manual_adoptions") or {}
    catalogs, output = {}, {}
    for group in groups:
        if match_identity(group) not in unmatched:
            continue
        if not group_is_active(work, group, assignments, hidden):
            continue
        key = group["selection_key"]
        channel_key = text(group["element"]) + "|" + text(group["wavelength"])
        option = {"key": key, "channel_key": channel_key, "label": group["element"] + group["wavelength"] + "nm",
                  "identity": match_identity(group), "decision": "REJECT", "reason": "", "record": None,
                  "eligible": False, "error": "", "warning": "", "batch_id": "", "exam_no": "", "category": ""}
        try:
            seq = group.get("selected_sequence")
            if seq is None:
                raise ValueError("請先選定此金屬／波長的量測。")
            batch_id = assignments.get(str(seq))
            batch = (work.get("batch_categories") or {}).get(batch_id) or {}
            selected = (batch.get("channels") or {}).get(channel_key) or {}
            if not batch_id or not selected.get("exam_no"):
                raise ValueError("請先完成批次設定。")
            element = group["element"]
            if element not in catalogs:
                catalogs[element] = category_catalog(work.get("form_data") or {}, element)
            setting = next((s for s in catalogs[element].get(batch.get("category"), [])
                            if s["exam_no"] == selected["exam_no"] and not s["error"]), None)
            if setting is None or selected.get("settings_token") != work_token(setting):
                raise ValueError("批次方法設定已變更，請先重新確認並儲存。")
            variant = text(group.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper()
            display = text(setting["method"].get("ANALYTE_DISPLAY")).upper()
            if (variant == "DISSOLVED") != display.startswith("D-"):
                option["warning"] = "批次檢測設定與一般／溶解態樣品不一致；採用後依批次設定計算。"
            context = {"key": key, "channel_key": channel_key, "sequence": seq,
                       "batch_id": batch_id, "category": batch["category"],
                       "exam_no": selected["exam_no"], "settings_token": selected["settings_token"]}
            option.update(eligible=True, batch_id=batch_id, category=batch["category"],
                          exam_no=selected["exam_no"], context=context, context_token=work_token(context))
            record = stored.get(key)
            if (isinstance(record, dict) and record.get("source_type") == "MANUAL_NOT_COMMISSIONED"
                    and record.get("context_token") == option["context_token"]
                    and record.get("decision") in {"ACCEPT", "REJECT"}):
                if record["decision"] == "REJECT" or text(record.get("actor_user_id")):
                    option.update(decision=record["decision"], reason=text(record.get("reason")), record=record)
        except ValueError as exc:
            option["error"] = str(exc)
        output[key] = option
    return output


def decorate_manual_adoptions(matches, work):
    options = manual_adoption_options(work, matches)
    for item in matches:
        if item.get("status") == "NOT_COMMISSIONED":
            item["manual_options"] = [o for o in options.values() if o["identity"] == match_identity(item)]
    return options


def lims_decision_form_context(work):
    if "icp_lims_csrf" not in session:
        session["icp_lims_csrf"] = secrets.token_urlsafe(32)
    return {"csrf": session["icp_lims_csrf"], "work_key": text(session.get("icp_work_key")),
            "work_token": work_token(work) if isinstance(work, dict) else ""}


def _submitted(prefix):
    result = {}
    for name in request.form:
        if name.startswith(prefix + "[") and name.endswith("]"):
            values = request.form.getlist(name)
            key = name[len(prefix) + 1:-1]
            if not key or key in result or len(values) != 1:
                raise ValueError("提交的決定識別重複或格式不正確。")
            result[key] = text(values[0])
    return result


def validate_decisions(work, matches, submitted, manual_submitted, reasons, actor):
    matches = filter_lims_matches(work, matches)
    index = {}
    for item in matches:
        exam = text(item.get("examno")).upper()
        if not exam:
            continue
        key = text(item.get("keepid")).upper() + "|" + exam
        if key in index:
            raise ValueError("發現重複的 LIMS 委測識別，本次不儲存。")
        index[key] = item
    new_standard = {}
    for key, value in (work.get("lims_decisions") or {}).items():
        if (isinstance(value, dict) and key in index
                and value.get("decision") in allowed_decisions(index[key].get("status"))):
            new_standard[key] = deepcopy(value)
    for key, decision in submitted.items():
        if key not in index or decision not in allowed_decisions(index[key].get("status")):
            raise ValueError("委測項目 " + key + " 的決定不符合目前配對限制。")
        new_standard[key] = {"decision": decision, "reason": ""}
    options = manual_adoption_options(work, matches)
    new_manual = {key: deepcopy(o["record"]) for key, o in options.items() if o.get("record")}
    actor_id = text(actor.get("user_id"))
    if not actor_id:
        raise ValueError("尚未取得登入操作者。")
    timestamp = datetime.utcnow().isoformat(timespec="microseconds")
    audit = []
    for key, decision in manual_submitted.items():
        option = options.get(key)
        if not option or not option["eligible"] or decision not in {"ACCEPT", "REJECT"}:
            raise ValueError("採用項目已變更或尚未完成批次設定，請重新載入。")
        reason = text(reasons.get(key))
        if len(reason) > 500:
            raise ValueError("人工採用原因不可超過 500 字。")
        record = {"source_type": "MANUAL_NOT_COMMISSIONED", "decision": decision,
                  "reason": reason if decision == "ACCEPT" else "",
                  "context_token": option["context_token"], **option["context"],
                  "actor_user_id": actor_id, "actor_employee_id": text(actor.get("employee_id")),
                  "actor_name": text(actor.get("employee_name") or actor.get("name")), "updated_at_utc": timestamp}
        previous = new_manual.get(key)
        if (previous and previous.get("decision") == record["decision"]
                and previous.get("reason") == record["reason"]
                and previous.get("context_token") == record["context_token"]):
            continue
        new_manual[key] = record
        audit.append({"previous": deepcopy(previous), "current": deepcopy(record)})
    return new_standard, new_manual, audit


def _save(work_key, expected_token, standard, manual, audit):
    db = SessionLocal()
    try:
        row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == work_key).first()
        if row is None:
            raise IcpPfmConflictError("工作已不存在。")
        original = row.state_json
        work = json.loads(original)
        if work_token(work) != expected_token:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存決定。")
        work["lims_decisions"], work["manual_adoptions"] = standard, manual
        history = work.setdefault("manual_adoption_history", [])
        if not isinstance(history, list):
            raise ValueError("人工採用紀錄格式異常。")
        history.extend(audit)
        result = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key, IcpImportWorkState.state_json == original,
        ).values(state_json=json.dumps(work, ensure_ascii=False)))
        if result.rowcount != 1:
            raise IcpPfmConflictError("工作資料已更新，請重新載入。")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def handle_lims_decision_post(load_basic_info, query_lims, actor):
    try:
        csrf = text(request.form.get("csrf_token"))
        if not csrf or not secrets.compare_digest(csrf, session.get("icp_lims_csrf", "")):
            return jsonify(message="頁面驗證已失效，請重新載入後再操作。"), 403
        key = text(session.get("icp_work_key"))
        if request.form.getlist("work_key") != [key] or not key:
            raise IcpPfmConflictError("目前 ICP 工作已改變，請重新載入。")
        work = load_icp_work_state(key)
        if not isinstance(work, dict):
            raise ValueError("ICP 暫存資料不存在。")
        expected = text(request.form.get("work_token"))
        if expected != work_token(work):
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再操作。")
        form = session.get("basic_info_form") or {}
        _, method, error = load_basic_info(form)
        if (error or not method or method.get("ANALYSIS_MODE") != "MULTI_ANALYTE"
                or form != work.get("form_data") or method.get("IMPORT_TYPE") != work.get("import_type")):
            raise ValueError("分析基本資料已變更，請重新確認。")
        groups = build_sample_candidate_groups((work.get("parsed_data") or {}).get("rows") or [])
        from analysis.icp_batch_adoption import active_candidate_groups
        groups = active_candidate_groups(work, groups)
        if not groups:
            raise ValueError("目前沒有 ICP 候選量測。")
        mapping = load_icp_analyte_map(os.path.join(current_app.root_path, "data", "Phyon_ICP_Analyte_Map.csv"))
        lims = []
        for keepid in sorted({g["keepid"] for g in groups}):
            # Empty result is valid NOT_COMMISSIONED; connection exceptions still stop the entire save.
            rows = query_lims(keepid)
            matched = match_lims_icp_analytes(rows, mapping)
            lims.append({"keepid": keepid, "matched_rows": matched["matched_rows"]})
        matches = build_icp_lims_matches(groups, lims, form.get("method_code"))
        raw_submitted = _submitted("decisions")
        submitted = {k.upper(): v.upper() for k, v in raw_submitted.items()}
        if len(submitted) != len(raw_submitted):
            raise ValueError("委測識別重複，本次不儲存。")
        manual = {k: v.upper() for k, v in _submitted("manual_decisions").items()}
        if not submitted and not manual:
            raise ValueError("沒有收到任何配對決定。")
        standard, adopted, audit = validate_decisions(work, matches, submitted, manual,
                                                     _submitted("manual_reasons"), actor)
        _save(key, expected, standard, adopted, audit)
        return jsonify(message="委測決定與採用選擇已儲存。", redirect_url=url_for("analysis_icp_import", tab="lims"))
    except IcpPfmConflictError as exc:
        return jsonify(message=str(exc)), 409
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        current_app.logger.exception("ICP 委測決定／人工採用儲存失敗")
        return jsonify(message="無法重新確認 LIMS 或儲存工作，本次未完成儲存。"), 503
