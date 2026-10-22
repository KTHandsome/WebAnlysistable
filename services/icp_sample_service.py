from services.icp_qaqc_applicability import spike_selection
"""ICP work-only sample inputs, stable source links and shared concentration calculation."""
import json
import math
import re
from copy import deepcopy
from datetime import datetime
from sqlalchemy import update
from database import SessionLocal
from models import IcpImportWorkState
from analysis.analysis_workflow import recalculate_sample_rows
from calculations.w43401 import calculate_sample_concentration
from services.icp_batch_category_service import build_batches, build_batch_memberships, batch_check_position, boundary_number
from services.icp_performance_service import work_token, IcpPfmConflictError

DIRECT = {"ICBK", "ICV", "CCBK", "CCV"}
LINKED = {"DUP", "MS", "MSD"}
QC = DIRECT | LINKED | {"BK", "QC"}


def text(v):
    return str(v if v is not None else "").strip()


def positive(v, name):
    try:
        number = float(v)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(name + "必須為有效數值。")
    if not math.isfinite(number) or number <= 0:
        raise ValueError(name + "必須為大於零的有限數值。")
    return number


def optional_number(v):
    try:
        number = float(v)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def identity(row):
    return "|".join([text(row.get("lims_keepid") or row.get("base_label")).upper(),
                     text(row.get("element")), text(row.get("wavelength")),
                     text(row.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper(),
                     text(row.get("pdf_sample_tag")).upper()])


def source_links(rows, assignments):
    """Bind each QC family to its first preceding raw original, before any filtering."""
    last, families, links = {}, {}, {}
    for row in rows:
        batch = assignments.get(text(row.get("sequence")))
        if not batch:
            continue
        role = text(row.get("role")).upper()
        if role == "SAMPLE" and row.get("element_applicability") == "APPLICABLE":
            last[batch] = row
        elif role in LINKED and row.get("element_applicability") == "APPLICABLE":
            label = text(row.get("base_label") or row.get("sample_label")).upper()
            m = re.match(r"^(?:DUP|MSD|MS)(?:-?(\d+[A-Z]*))?(?:\(|$)", label)
            family = (batch, m.group(1) or batch) if m else None
            if family not in families:
                families[family] = last.get(batch) if family else None
            parent = families.get(family)
            links[text(row.get("sequence"))] = {
                "parent_identity": identity(parent) if parent else "",
                "parent_sample_id": text(parent.get("lims_keepid") or parent.get("base_label")) if parent else "",
                "parent_source_sequence": parent.get("sequence") if parent else None,
            }
    return links


def _raw_text(row, key, fallback):
    if key in row:
        return text(row[key])
    match = re.search(r"\)\s*(.*?)\s+mg/L\s+(\S+)\s+(\S+)\s*$", text(row.get("source_line")))
    if match:
        return match.group(2 if key == "signal_text" else 3)
    return text(row.get(fallback))


def _digits(method, field, default):
    raw = text(method.get(field))
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(field + " 位數設定不正確。")
    if value < 0 or value > 12:
        raise ValueError(field + " 位數設定須介於 0～12。")
    return value


def build_sample_view(work, channel, category_view, calibrations, lookup_error=None, overrides=None):
    if not channel or not category_view:
        return {"batches": [], "ready": False, "warnings": [], "token": ""}
    _, assignments, _ = build_batches((work.get("parsed_data") or {}).get("rows") or [])
    memberships = build_batch_memberships((work.get("parsed_data") or {}).get("rows") or [])
    raw_rows = channel["rows"]
    raw_map = {text(r.get("sequence")): r for r in raw_rows}
    links = source_links(raw_rows, assignments)
    saved = (work.get("icp_sample_state") or {}).get(channel["key"], {})
    saved_rows = saved.get("rows") or {}
    source_samples = {}
    hidden, warnings = 0, []
    settings = {b["id"]: b for b in category_view["batches"]}
    cal_map = {str(c["batch_number"]): c for c in calibrations}
    buckets = {b["id"]: [] for b in category_view["batches"]}
    auto_filtered = {b["id"]: [] for b in category_view["batches"]}
    for group in channel["sample_groups"]:
        selected = group.get("selected")
        if not selected:
            hidden += 1
            continue
        source = raw_map.get(text(selected["sequence"]))
        batch_id = assignments.get(text(selected["sequence"]))
        batch = settings.get(batch_id)
        if not source or not batch or not batch["ready"]:
            hidden += 1
            continue
        # Decision is for this exact exam, never any ACCEPT on the same sample.
        accepted = not lookup_error and any(
            item.get("examno") == batch["exam_no"] and item.get("user_decision") == "ACCEPT"
            for item in group["lims_items"])
        manual = group.get("manual_adoption")
        manual_accepted = bool(not lookup_error and manual and manual.get("exam_no") == batch["exam_no"]
                               and manual.get("batch_id") == batch_id)
        if not accepted and not manual_accepted:
            hidden += 1
            continue
        row = deepcopy(source)
        row["manual_adoption"] = deepcopy(manual) if manual_accepted and not accepted else None
        row.update(row_id="S:" + group["selection_key"], sample_id=group["keepid"],
                   selection_key=group["selection_key"], source_sequence=source["sequence"],
                   batch_id=batch_id, parent_identity="", parent_sample_id="",
                   parent_source_sequence=None, parent_row_id="")
        source_samples[group["selection_key"]] = row
        buckets[batch_id].append(row)
    if lookup_error:
        warnings.append("LIMS 尚無法確認，暫不帶入一般樣品，也不開放儲存。")
    for source in raw_rows:
        role = text(source.get("role")).upper()
        if role not in QC or source.get("element_applicability") == "NOT_TARGET":
            continue
        for batch_id in memberships.get(text(source.get("sequence")), []):
            if batch_id not in buckets:
                continue
            method = ((settings[batch_id].get("setting") or {}).get("method") or {})
            selection = spike_selection(source, method)
            if selection and selection["matches"] is False:
                auto_filtered[batch_id].append({"source_sequence": source["sequence"],
                    "sample_id": source["sample_label"], "role": role,
                    "reference_spike_concentration": selection["reference"],
                    "method_spike_concentration": selection["target"]})
                continue
            row = deepcopy(source)
            row["qaqc_spike_selection"] = selection
            row["manual_adoption"] = None
            parent = links.get(text(source.get("sequence")), {})
            selected_parent = source_samples.get(parent.get("parent_identity"))
            if selected_parent and selected_parent["batch_id"] != batch_id:
                selected_parent = None
            is_boundary = boundary_number(source) is not None
            row_id = "Q:" + text(source["sequence"]) + (":B:" + batch_id if is_boundary else "")
            row.update(row_id=row_id, sample_id=source["sample_label"],
                       source_sequence=source["sequence"], batch_id=batch_id,
                       check_position=batch_check_position(source, batch_id),
                       boundary_check=is_boundary,
                       parent_identity=parent.get("parent_identity", ""),
                       parent_sample_id=parent.get("parent_sample_id", ""),
                       parent_source_sequence=parent.get("parent_source_sequence"),
                       parent_row_id=selected_parent["row_id"] if selected_parent else "")
            buckets[batch_id].append(row)
    view = []
    ready = bool(buckets) and not lookup_error
    for batch_id, source_rows in buckets.items():
        batch, cal = settings[batch_id], cal_map.get(batch_id) or {}
        item = {"id": batch_id, "number": batch["number"], "category": batch["category"],
                "exam_no": batch["exam_no"], "rows": [], "error": cal.get("error"), "warnings": [],
                "auto_filtered_qaqc": auto_filtered[batch_id]}
        if not batch["ready"] or not cal.get("result"):
            item["error"] = item["error"] or "請先完成批次設定與檢量線核對。"
            ready = False
            view.append(item)
            continue
        method, control = batch["setting"]["method"], batch["setting"]["control"]
        try:
            sample_volume = positive(method.get("SAMPLE_VOLUME_DEFAULT"), "方法取樣體積")
            final_volume = positive(method.get("FINAL_VOLUME_DEFAULT"), "方法定量體積")
            prep = positive(method.get("SAMPLE_PREP_FACTOR") or 1, "方法前處理倍率")
            factor = positive(method.get("QAQC_CONC_FACTOR") or 1, "判定濃度換算係數")
            digits = _digits(method, "UI_CONCENTRATION_DECIMALS", 6)
            apply = text(method.get("APPLY_VOLUME_FACTOR")).upper()
            if apply not in {"Y", "N"}:
                raise ValueError("方法體積倍率設定不正確。")
            mdl = optional_number(control.get("DETECT_LIMITED"))
            multiplier = optional_number(method.get("BLANK_MDL_MULTIPLIER"))
            qdl = None
            if text(method.get("QDL_SOURCE")) == "FIRST_NONZERO_CALIBRATION_X":
                xs = [positive(x, "檢量線濃度") for x in method["CALIBRATION_VALUES"].split("|") if float(x) > 0]
                qdl = min(xs) * positive(method.get("QDL_MULTIPLIER"), "QDL 倍率") * factor
            else:
                qdl = optional_number(control.get("QDL"))
            source_rows.sort(key=lambda r: int(r["source_sequence"]))
            for row in source_rows:
                selection = row.get("qaqc_spike_selection")
                if selection and selection["error"]:
                    ready = False
                    item["warnings"].append(selection["error"])
                direct = row["role"] in DIRECT
                row["binding"] = work_token({"source": row["source_sequence"], "signal": row.get("signal"),
                    "label": row.get("sample_label"), "time": row.get("measured_at"),
                    "settings": batch["setting"], "parent": row["parent_identity"]})
                previous = saved_rows.get(row["row_id"], {})
                if row.get("boundary_check") and not previous and saved_rows.get("Q:" + text(row["source_sequence"])):
                    item["warnings"].append("交界查核已依前後批次重建，請確認本批採用狀態並重新暫存。")
                if previous and previous.get("binding") != row["binding"]:
                    item["warnings"].append("量測或設定已變更，部分輸入已恢復預設，請重新儲存。")
                    previous = {}
                edit = overrides.get(row["row_id"], {}) if overrides is not None else previous
                row.update(sample_volume=sample_volume, final_volume=sample_volume if direct else final_volume,
                           dilution_factor=1.0 if direct else positive(row.get("label_dilution_factor") or 1, "PDF 稀釋倍數"),
                           sample_prep_factor=1.0 if direct else prep,
                           apply_volume_factor=apply == "Y", is_excluded=False)
                for field in ("sample_volume", "final_volume", "dilution_factor"):
                    if field in edit and not direct:
                        row[field] = positive(edit[field], row["sample_id"] + " " + field)
                if "is_excluded" in edit:
                    if type(edit["is_excluded"]) is not bool:
                        raise ValueError("排除狀態格式不正確。")
                    row["is_excluded"] = edit["is_excluded"]
                row["signal_text"] = _raw_text(row, "signal_text", "signal")
                row["rsd_text"] = _raw_text(row, "rsd_text", "rsd")
                row["sequence_no"] = row["source_sequence"]
                recalculate_sample_rows([row], cal["result"], calculate_sample_concentration)
                for field in ("measured_concentration", "sample_concentration"):
                    value = optional_number(row.get(field))
                    if value is None:
                        raise ValueError(row["sample_id"] + " 無法計算有效濃度。")
                    row[field] = value
                    row[field + "_text"] = format(value, "." + str(digits) + "f")
                row["direct"] = direct
                row["linked_count"] = sum(x.get("parent_row_id") == row["row_id"] for x in source_rows)
                row["link_error"] = row["role"] in LINKED and not row["parent_row_id"]
                if row["link_error"] and not row["is_excluded"]:
                    ready = False
                    item["warnings"].append(row["sample_id"] + " 的原樣未採用或未選定，請先回匯入頁確認原樣；不重新配給其他樣品。")
                if row["is_excluded"] and row["linked_count"]:
                    raise ValueError(row["sample_id"] + " 連結 DUP／MS／MSD，不可直接排除原樣。")
                row["calculation"] = {"slope": cal["result"]["slope"], "intercept": cal["result"]["intercept"],
                    "applyVolume": row["apply_volume_factor"], "prep": row["sample_prep_factor"],
                    "direct": direct, "digits": digits, "concentrationFactor": factor,
                    "mdl": mdl, "qdl": qdl, "blankMdlMultiplier": multiplier}
                item["rows"].append(row)
            # Keep source order for checks and normal samples; attach linked QC immediately below parent.
            linked = [r for r in item["rows"] if r["parent_row_id"]]
            order = []
            for row in item["rows"]:
                if row not in linked:
                    order.append(row)
                    order.extend(r for r in linked if r["parent_row_id"] == row["row_id"])
            item["rows"] = order
            item["warnings"] = sorted(set(item["warnings"]))
        except ValueError as exc:
            item["error"] = str(exc)
            ready = False
        view.append(item)
    flat = [r for b in view for r in b["rows"]]
    if hidden:
        warnings.append("未採用、待確認或尚未選定量測的一般樣品不列入計算表。")
    return {"batches": view, "ready": ready, "warnings": warnings,
            "token": work_token([{k: r.get(k) for k in ("row_id", "binding")} for r in flat])}


def save_sample_inputs(work_key, expected_token, channel_key, sample_view, actor):
    if not sample_view["ready"]:
        raise ValueError("請先處理批次設定、檢量線或原樣關聯提示，尚不可儲存。")
    if not text(actor.get("user_id")):
        raise ValueError("尚未取得登入操作者。")
    rows = {}
    for batch in sample_view["batches"]:
        for row in batch["rows"]:
            rows[row["row_id"]] = {k: row[k] for k in ("binding", "source_sequence", "sample_volume",
                "final_volume", "dilution_factor", "is_excluded", "parent_identity", "parent_sample_id", "parent_source_sequence", "manual_adoption")}
    payload = {"rows": rows, "auto_filtered_qaqc": {b["id"]: b.get("auto_filtered_qaqc", []) for b in sample_view["batches"]},
               "updated_by": text(actor["user_id"]),
               "updated_at_utc": datetime.utcnow().isoformat(timespec="seconds")}
    db = SessionLocal()
    try:
        record = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == work_key).first()
        if record is None:
            raise IcpPfmConflictError("工作已不存在。")
        original = record.state_json
        work = json.loads(original)
        if work_token(work) != expected_token:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存。")
        work.setdefault("icp_sample_state", {})[channel_key] = payload
        result = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key, IcpImportWorkState.state_json == original,
        ).values(state_json=json.dumps(work, ensure_ascii=False)))
        if result.rowcount != 1:
            raise IcpPfmConflictError("工作資料已更新，請重新載入後再儲存。")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
