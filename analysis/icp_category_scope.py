"""Scope a newly imported ICP work to the basic-info sample category."""
import re
from copy import deepcopy
from analysis.sample_category_filter import (
    detect_formal_sample_category, SUPPORTED_SAMPLE_CATEGORIES,
)
from services.icp_batch_category_service import build_batches, build_batch_memberships


def scope_icp_import_category(parsed_data, category):
    category = str(category or "").strip().upper()
    if category not in SUPPORTED_SAMPLE_CATEGORIES:
        raise ValueError("請先於基本資料選擇有效的樣品類別，再匯入 ICP PDF。")
    rows = parsed_data.get("rows") or []
    batches, _, warnings = build_batches(rows)
    if warnings:
        raise ValueError("無法安全依類別篩選批次：" + "；".join(warnings))
    memberships = build_batch_memberships(rows)
    categories = {batch["id"]: set() for batch in batches}
    for row in rows:
        if str(row.get("role") or "").strip().upper() != "SAMPLE":
            continue
        label = str(row.get("lims_keepid") or row.get("base_label")
                    or row.get("sample_label") or "").strip()
        detected = detect_formal_sample_category(label)
        if detected is None and re.fullmatch(r"I[0-9]{11}", label.upper()):
            detected = "I"
        member = memberships.get(str(row.get("sequence")), [])
        if not member or detected is None:
            raise ValueError("樣品 " + label + " 無法確認類別或批次，請先確認 PDF 標記。")
        for batch_id in member:
            categories[batch_id].add(detected)
    selected = set()
    for batch_id, found in categories.items():
        if category not in found:
            continue
        if found != {category}:
            raise ValueError("批次 " + batch_id + " 同時含不同類別樣品，無法自動篩選，請先確認批次。")
        selected.add(batch_id)
    if not selected:
        raise ValueError("PDF 中沒有可供 " + category + " 類使用的樣品批次。")
    kept = []
    for row in rows:
        role = str(row.get("role") or "").strip().upper()
        member = memberships.get(str(row.get("sequence")), [])
        # Calibration/performance rows are shared by the analytical run.
        if role in {"STANDARD", "PFM", "PRM"} or selected.intersection(member):
            item = deepcopy(row)
            item["import_category_batch_ids"] = sorted(selected, key=int)
            kept.append(item)
    result = deepcopy(parsed_data)
    result["source_rows"] = deepcopy(rows)
    result["rows"] = kept
    result["category_scope"] = {
        "version": 1, "category": category,
        "batch_ids": sorted(selected, key=int),
        "source_row_count": len(rows), "included_row_count": len(kept),
        "excluded_row_count": len(rows) - len(kept),
    }
    return result
