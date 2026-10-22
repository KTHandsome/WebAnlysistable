from services.icp_qaqc_applicability import spike_selection
from services.icp_batch_category_service import batch_check_position
"""ICP QA/QC view based on calculated active rows and explicit parent links."""
import math
import re
from analysis.qaqc_calculator import (
    calculate_relative_error, calculate_recovery, calculate_rpd,
    calculate_spike_recovery, evaluate_relative_error_status,
    evaluate_control_status, evaluate_rpd_status,
)

ICP_CC_LIMIT = 10.0


def number(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def concentration(row, factor):
    value = number(row.get("qaqc_concentration"))
    return number(value * factor) if value is not None and factor is not None else None


def limits(control, prefix):
    return {name.lower(): number(control.get(prefix + "_" + name)) for name in ("LCL", "LWL", "UWL", "UCL")}


def comparison(value, bounds):
    if value is not None:
        for boundary in bounds:
            if boundary is not None and math.isclose(value, boundary, rel_tol=1e-12, abs_tol=1e-12):
                return boundary
    return value


def recovery_status(value, bounds):
    lo, hi, lw, uw = (bounds[k] for k in ("lcl", "ucl", "lwl", "uwl"))
    if lo is None or hi is None:
        return "待設定標準"
    if lo > hi or (lw is not None and not lo <= lw <= hi) or (uw is not None and not lo <= uw <= hi) or (lw is not None and uw is not None and lw > uw):
        return "待設定標準"
    return evaluate_control_status(comparison(value, (lo, lw, uw, hi)), lo, lw, uw, hi)


def precision_status(value, control):
    uwl, ucl = number(control.get("DC_UWL")), number(control.get("DC_UCL"))
    if ucl is None or ucl < 0 or (uwl is not None and not 0 <= uwl <= ucl):
        return "待設定標準"
    return evaluate_rpd_status(comparison(value, (uwl, ucl)), uwl, ucl)


def parent_of(row, by_id):
    parent = by_id.get(row.get("parent_row_id"))
    if not parent or parent.get("role") != "SAMPLE":
        return None
    if (parent.get("batch_id") != row.get("batch_id") or
            parent.get("selection_key") != row.get("parent_identity")):
        return None
    return parent


def family(row):
    label = str(row.get("base_label") or row.get("sample_label") or row.get("sample_id") or "").strip().upper()
    match = re.match(r"^(?:DUP|MSD|MS)(?:-?(\d+[A-Z]*))?(?:\(|$)", label)
    return (match.group(1) or str(row.get("batch_id"))) if match else None


def missing(role, reason):
    return {"role": role, "sample_id": "—", "status": "無法判定", "reason": reason,
            "spike": None, "value": None, "metric": None, "calculation_name": "—", "bounds": {}}


def build_icp_qaqc_view(category_view, sample_view, lookup_error=None):
    if not category_view or not sample_view:
        return {"batches": [], "ready": False}
    settings = {b["id"]: b for b in category_view["batches"]}
    results = []
    for batch in sample_view["batches"]:
        setting = settings.get(batch["id"]) or {}
        if setting.get("is_excluded"):
            continue
        config = setting.get("setting") or {}
        method, control = config.get("method") or {}, config.get("control") or {}
        factor = number(method.get("QAQC_CONC_FACTOR") or 1)
        if factor is not None and factor <= 0:
            factor = None
        active = [r for r in batch["rows"] if not r.get("is_excluded")
                  and (spike_selection(r, method) or {}).get("matches") is not False]
        by_id = {r["row_id"]: r for r in active}
        a, b, c = [], [], []
        for row in active:
            role = row.get("role")
            if role not in {"ICV", "QC", "CCV"}:
                continue
            value = concentration(row, factor)
            spike = number(method.get(role + "_SPIKE_CONC"))
            if spike is not None and spike <= 0:
                spike = None
            relative = role in {"ICV", "CCV"}
            selection = spike_selection(row, method)
            metric = number((calculate_relative_error if relative else calculate_recovery)(value, spike))
            if selection and selection["error"]:
                metric = None
            bounds = {"limit": ICP_CC_LIMIT} if relative else limits(control, "QC")
            status = evaluate_relative_error_status(comparison(metric, (-ICP_CC_LIMIT, ICP_CC_LIMIT)), ICP_CC_LIMIT) if relative else recovery_status(metric, bounds)
            if metric is None:
                status = "無法判定"
            a.append({"role": role, "sample_id": row["sample_id"], "sequence": row["source_sequence"],
                      "check_position": batch_check_position(row, batch["id"]) or "批內查核",
                      "spike": spike, "value": value, "metric": metric, "bounds": bounds,
                      "calculation_name": "相對誤差" if relative else "回收率", "status": status,
                      "reason": selection["error"] if selection and selection["error"] else ("添加濃度或計算濃度無效" if metric is None else "")})
        if not any(r["role"] == "QC" for r in a):
            item = missing("QC", "本批沒有有效的 QC 查核資料。")
            item["check_position"] = "批內查核"
            a.append(item)
        for position in ("起始查核", "結束查核"):
            if not any(r.get("check_position") == position and r["role"] in {"ICV", "CCV"} for r in a):
                item = missing("ICV / CCV", "本批缺少" + position + "的 ICV／CCV。")
                item["check_position"] = position
                a.append(item)
        boundary_errors = []
        for position in ("起始查核", "結束查核"):
            if not any(r.get("role") in {"ICBK", "CCBK"} and batch_check_position(r, batch["id"]) == position for r in active):
                boundary_errors.append("本批缺少" + position + "的 ICBK／CCBK。")
        for dup in [r for r in active if r.get("role") == "DUP"]:
            parent = parent_of(dup, by_id)
            value = concentration(dup, factor)
            original = concentration(parent, factor) if parent else None
            qdl = number((dup.get("calculation") or {}).get("qdl"))
            item = {"source": "DUP", "sample_a": parent["sample_id"] if parent else dup.get("parent_sample_id", "—"),
                    "sample_b": dup["sample_id"], "value_a": original, "value_b": value,
                    "parent_sample": parent["sample_id"] if parent else dup.get("parent_sample_id", "—"),
                    "rpd": None, "qdl": qdl, "uwl": number(control.get("DC_UWL")),
                    "ucl": number(control.get("DC_UCL")), "status": "無法判定", "reason": ""}
            if not parent:
                item["reason"] = "原樣未採用或關聯不完整，不重新配給其他樣品。"
            elif value is None or original is None or qdl is None or qdl <= 0:
                item["reason"] = "原樣、DUP 濃度或 QDL 無效。"
            elif value >= qdl:
                item["rpd"] = number(calculate_rpd(original, value))
                item["status"] = precision_status(item["rpd"], control)
            else:
                item["source"] = "MS / MSD"
                pairs = {role: [r for r in active if r.get("role") == role
                               and parent_of(r, by_id) is parent and family(dup) is not None and family(r) == family(dup)
                               and not (spike_selection(r, method) or {}).get("error")]
                         for role in ("MS", "MSD")}
                item["reason"] = "DUP < QDL，改採同原樣、同組 MS／MSD。"
                if len(pairs["MS"]) == 1 and len(pairs["MSD"]) == 1:
                    ms, msd = pairs["MS"][0], pairs["MSD"][0]
                    item.update(sample_a=ms["sample_id"], sample_b=msd["sample_id"],
                                value_a=concentration(ms, factor), value_b=concentration(msd, factor))
                    item["rpd"] = number(calculate_rpd(item["value_a"], item["value_b"]))
                    item["status"] = precision_status(item["rpd"], control)
                else:
                    item["reason"] += "缺少完整配對或存在多筆量測，請先確認採用資料。"
            if item["rpd"] is None:
                item["status"] = "無法判定"
            b.append(item)
        if not b:
            b.append({"source": "DUP", "parent_sample": "—", "sample_a": "—", "sample_b": "—", "value_a": None,
                      "value_b": None, "rpd": None, "qdl": None,
                      "uwl": number(control.get("DC_UWL")), "ucl": number(control.get("DC_UCL")),
                      "status": "無法判定", "reason": "本批沒有有效的 DUP 資料。"})
        for row in [r for r in active if r.get("role") in {"MS", "MSD"}]:
            parent = parent_of(row, by_id)
            original = concentration(parent, factor) if parent else None
            value = concentration(row, factor)
            spike = number(method.get("MS_SPIKE_CONC"))
            if spike is not None and spike <= 0:
                spike = None
            selection = spike_selection(row, method)
            metric = number(calculate_spike_recovery(value, original, spike)) if parent else None
            if selection and selection["error"]:
                metric = None
            bounds = limits(control, "SPIKE")
            c.append({"role": row["role"], "sample_id": row["sample_id"], "sequence": row["source_sequence"],
                      "original_sample_id": parent["sample_id"] if parent else row.get("parent_sample_id", "—"),
                      "original_value": original, "spike": spike, "value": value, "metric": metric,
                      "bounds": bounds, "status": recovery_status(metric, bounds) if metric is not None else "無法判定",
                      "reason": selection["error"] if selection and selection["error"] else ("原樣關聯、濃度或添加濃度無效。" if metric is None else "")})
        for role in sorted({"MS", "MSD"} - {r["role"] for r in c}):
            item = missing(role, "本批沒有有效的 " + role + " 資料。")
            item.update(original_sample_id="—", original_value=None)
            c.append(item)
        blocked = batch.get("error") or lookup_error or " ".join(boundary_errors)
        statuses = [r["status"] for r in a + b + c]
        ready = not blocked and all(s in {"合格", "警告", "超出管制"} for s in statuses)
        status = "待確認" if not ready else ("超出管制" if "超出管制" in statuses else "警告" if "警告" in statuses else "合格")
        digits = str(method.get("UI_CONCENTRATION_DECIMALS") or "6").strip()
        places = int(digits) if digits.isdigit() and int(digits) <= 12 else 6
        results.append({"number": batch["number"], "category": batch["category"], "exam_no": batch["exam_no"],
                        "a": a, "b": b, "c": c, "ready": ready, "status": status,
                        "error": blocked, "digits": places,
                        "unit": method.get("DISPLAY_CONC_UNIT") or "mg/L"})
    return {"batches": results, "ready": bool(results) and all(b["ready"] for b in results)}
