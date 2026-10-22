"""Batch categories and exact exam settings for an existing ICP work."""
import csv
import json
import os
import re
from copy import deepcopy
from datetime import datetime
from flask import current_app
from sqlalchemy import update
from database import SessionLocal
from models import IcpImportWorkState
from services.icp_performance_service import work_token, IcpPfmConflictError


def text(value):
    return str(value if value is not None else "").strip()


def build_batches(rows):
    """Identify sample batches; use build_batch_memberships for shared check pairs."""
    channels, batches, assignments, warnings = {}, {}, {}, []
    for row in rows:
        key = text(row.get("element")) + "|" + text(row.get("wavelength"))
        channels.setdefault(key, []).append(row)
    for key, channel_rows in channels.items():
        active = None
        for row in channel_rows:
            role = text(row.get("role")).upper()
            label = text(row.get("base_label") or row.get("sample_label")).upper()
            label = re.sub(r"\(\d+(?:\.\d+)?\)$", "", label).strip()
            number = re.fullmatch(r"(?:CCBK|CCV)-?(\d+)", label)
            target = active
            if role == "ICBK":
                active = target = 1
            elif role == "CCBK" and number:
                active = target = int(number.group(1)) + 1
            elif role == "CCV" and number:
                target = int(number.group(1))
            elif role in {"CCBK", "CCV"}:
                warnings.append(key + " 的 " + label + " 無法確認批次編號。")
                target = None
            if target is None or role in {"STANDARD", "RINSE", "PFM", "PRM"}:
                continue
            batch = batches.setdefault(str(target), {
                "id": str(target), "number": target, "labels": set(), "sample_ids": set(),
                "has_start": False, "has_end": False,
            })
            batch["has_start"] = batch["has_start"] or role in {"ICBK", "CCBK"}
            batch["has_end"] = batch["has_end"] or role == "CCV"
            if role == "SAMPLE":
                batch["sample_ids"].add(text(row.get("lims_keepid") or row.get("base_label")))
            assignments[str(row.get("sequence"))] = str(target)
    result = []
    for batch in sorted(batches.values(), key=lambda b: b["number"]):
        if not batch["sample_ids"] and not batch["has_end"]:
            continue  # Final CCBK alone is not an additional sample batch.
        batch["sample_count"] = len(batch.pop("sample_ids"))
        batch.pop("labels")
        result.append(batch)
    if not result:
        warnings.append("尚未辨識到 ICBK／CCBK／CCV 批次，無法設定類別。")
    return result, assignments, sorted(set(warnings))


def boundary_number(row):
    role = text(row.get("role")).upper()
    if role not in {"CCBK", "CCV"}:
        return None
    label = text(row.get("base_label") or row.get("sample_label")).upper()
    label = re.sub(r"\(\d+(?:\.\d+)?\)$", "", label).strip()
    match = re.fullmatch(r"(?:CCBK|CCV)-?(\d+)", label)
    return int(match.group(1)) if match else None


def build_batch_memberships(rows):
    """CCBK n / CCV n belong to both batch n and actual batch n+1."""
    batches, assignments, _ = build_batches(rows)
    valid = {b["id"] for b in batches}
    memberships = {}
    for row in rows:
        sequence = text(row.get("sequence"))
        number = boundary_number(row)
        if number is not None:
            memberships[sequence] = [str(n) for n in (number, number + 1) if str(n) in valid]
        else:
            primary = assignments.get(sequence)
            memberships[sequence] = [primary] if primary in valid else []
    return memberships


def batch_check_position(row, batch_id):
    role = text(row.get("role")).upper()
    if role in {"ICBK", "ICV"}:
        return "起始查核"
    number = boundary_number(row)
    if number is not None:
        if text(batch_id) == str(number):
            return "結束查核"
        if text(batch_id) == str(number + 1):
            return "起始查核"
    return ""


def _read_csv(path):
    if not os.path.isfile(path):
        raise ValueError("尚未匯入設定檔：" + os.path.basename(path))
    with open(path, encoding="utf-8-sig", newline="") as source:
        return [{k: text(v) for k, v in row.items() if k is not None}
                for row in csv.DictReader(source)]


def category_catalog(form, element):
    root = os.path.join(current_app.root_path, "data")
    year, method = text(form.get("ctrl_year")), text(form.get("method_code")).upper()
    if not re.fullmatch(r"\d{4}", year):
        raise ValueError("管制年度格式不正確。")
    controls = _read_csv(os.path.join(root, "Phyon_Control_" + year + ".csv"))
    methods = _read_csv(os.path.join(root, "Phyon_Method_Settings.csv"))
    candidates = {}
    for row in controls:
        if row.get("CTRL_YEAR") != year or row.get("EM_NUM", "").upper() != method:
            continue
        cat, exam = row.get("CATEGORY_CODE", ""), row.get("EXAMNO", "")
        if not cat or not exam:
            continue
        settings = [m for m in methods if m.get("ACTIVE", "").upper() == "Y"
                    and m.get("METHOD_CODE", "").upper() == method
                    and m.get("EXAMNO") == exam
                    and m.get("ANALYTE_DISPLAY", "").upper() in
                    {element.upper(), "D-" + element.upper()}]
        if not settings:
            continue
        candidates.setdefault((cat, exam), {"controls": [], "methods": settings})["controls"].append(row)
    output = {}
    instrument = text(form.get("instrument_id")).upper()
    for (cat, exam), bundle in sorted(candidates.items()):
        rows = bundle["controls"]
        specific = [r for r in rows if r.get("LABPARTID", "").upper() == instrument and instrument]
        usable = specific or [r for r in rows if not r.get("LABPARTID")]
        if not usable:
            continue
        if len(usable) != 1 or len(bundle["methods"]) != 1:
            output.setdefault(cat, []).append({"exam_no": exam, "label": exam + "（設定重複，請先處理）",
                                               "error": "同一檢測代碼存在多筆設定，不可自動選取。"})
            continue
        control, setting = usable[0], bundle["methods"][0]
        output.setdefault(cat, []).append({
            "exam_no": exam, "label": exam + " " + control.get("EXAMNAME", ""),
            "control": control, "method": setting,
            "calibration_values": setting.get("CALIBRATION_VALUES", ""),
            "error": "",
        })
    return output


def build_category_view(work, form, channel, include_excluded=False):
    batches, assignments, warnings = build_batches((work.get("parsed_data") or {}).get("rows") or [])
    catalog = category_catalog(form, channel["element"]) if channel else {}
    saved = work.get("batch_categories") or {}
    view = []
    for batch in batches:
        item = dict(batch)
        stored = saved.get(batch["id"]) or {}
        item["category"] = stored.get("category", "")
        selection = (stored.get("channels") or {}).get(channel["key"], {}) if channel else {}
        item["is_excluded"] = (stored.get("is_excluded") is True or stored.get("category") == "__EXCLUDE__"
                               or selection.get("is_excluded") is True)
        if item["is_excluded"] and not include_excluded:
            continue
        item["exam_no"] = "__EXCLUDE__" if item["is_excluded"] else selection.get("exam_no", "")
        current = next((x for x in catalog.get(item["category"], [])
                        if x["exam_no"] == item["exam_no"] and not x["error"]), None)
        item["setting"] = current
        item["ready"] = item["is_excluded"] or bool(current and selection.get("settings_token") == work_token(current))
        view.append(item)
    return {"batches": view, "catalog": catalog, "warnings": warnings,
            "settings_token": work_token(catalog), "channel_key": channel["key"] if channel else "",
            "ready": bool(view) and all(b["ready"] for b in view)}


def save_batch_categories(work_key, expected_token, selections, channel_key, actor):
    user_id = text(actor.get("user_id"))
    if not user_id:
        raise ValueError("尚未取得登入操作者。")
    db = SessionLocal()
    try:
        row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == work_key).first()
        if row is None:
            raise IcpPfmConflictError("目前工作已不存在。")
        original = row.state_json
        work = json.loads(original)
        if work_token(work) != expected_token:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再設定類別。")
        batches, _, _ = build_batches((work.get("parsed_data") or {}).get("rows") or [])
        submitted_ids = [item["batch_id"] for item in selections]
        if (not batches or len(submitted_ids) != len(set(submitted_ids))
                or set(submitted_ids) != {b["id"] for b in batches}):
            raise ValueError("請一次提交目前工作的全部批次，且不可重複。")
        saved = work.setdefault("batch_categories", {})
        for item in selections:
            batch_id, category, setting = item["batch_id"], item["category"], item["setting"]
            entry = saved.get(batch_id) or {}
            # A category belongs to the entire batch, including all metal channels.
            if entry.get("category") != category:
                entry = {"category": category, "channels": {}}
            entry.setdefault("channels", {})[channel_key] = {
                "exam_no": setting["exam_no"], "settings_token": work_token(setting),
                "control_data": deepcopy(setting["control"]), "method_data": deepcopy(setting["method"]),
            }
            entry.update(updated_by=user_id, updated_at_utc=datetime.utcnow().isoformat(timespec="seconds"))
            saved[batch_id] = entry
        result = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key, IcpImportWorkState.state_json == original,
        ).values(state_json=json.dumps(work, ensure_ascii=False)))
        if result.rowcount != 1:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再設定類別。")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
