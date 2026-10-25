"""Validate edits to signed W430 preview; no database persistence."""
import math
from copy import deepcopy

ROLES = {"SAMPLE", "SAMPLE_BLANK", "QC", "BKA", "BKB", "ICV", "CCV", "DUP", "MS", "MSD"}


def edit_w430_preview(preview, edits):
    result = deepcopy(preview)
    source = [r for r in result["rows"] if r["role"] in ROLES]
    if not isinstance(edits, list) or len(edits) != len(source):
        raise ValueError("樣品列數不一致，請重新匯入。")
    index = {r["row_id"]: r for r in source}
    ids = [e.get("id") for e in edits if isinstance(e, dict)]
    if len(ids) != len(source) or any(type(i) is not int for i in ids) or set(ids) != set(index):
        raise ValueError("樣品識別重複或不一致。")
    original_groups = [(r["measured_at"][:10], r["batch"]) for r in source]
    edited_groups = [(index[i]["measured_at"][:10], index[i]["batch"]) for i in ids]
    if original_groups != edited_groups:
        raise ValueError("不可跨日期或批次移動量測資料。")
    removed = set()
    for edit in edits:
        row = index[edit["id"]]
        if type(edit.get("excluded")) is not bool:
            raise ValueError("刪除狀態無效。")
        if edit["excluded"]:
            if row["role"] not in {"SAMPLE", "SAMPLE_BLANK", "QC"}:
                raise ValueError("此類查核列不可直接刪除。")
            removed.add(row["row_id"])
        if row["role"] in {"SAMPLE", "SAMPLE_BLANK", "DUP", "MS", "MSD"}:
            try:
                value = float(edit["dilution"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("稀釋倍數必須為有效正數。")
            if not math.isfinite(value) or value <= 0:
                raise ValueError("稀釋倍數必須為有效正數。")
            row["dilution"] = value
    # Removing a parent also removes its DUP/MS/MSD. Remove a paired blank only if no retained row needs it.
    removed.update(r["row_id"] for r in source if r.get("parent_row_id") in removed and r["role"] in {"DUP", "MS", "MSD"})
    def blank_key(row):
        return (row["measured_at"][:10], row["batch"], row.get("blank_id"))
    discarded = {blank_key(r) for r in source if r["row_id"] in removed and r["role"] == "SAMPLE" and r.get("blank_id")}
    retained = {blank_key(r) for r in source if r["row_id"] not in removed and r.get("blank_id") and r["role"] != "SAMPLE_BLANK"}
    for row in source:
        if row["role"] == "SAMPLE_BLANK" and (row["measured_at"][:10],row["batch"],row["sample_id"]) in discarded - retained:
            removed.add(row["row_id"])
    ordered = [index[i] for i in ids if i not in removed]
    # The common QA/QC module uses the preceding sample; reject moves that would change an established parent.
    last = {}
    for row in ordered:
        key = (row["measured_at"][:10], row["batch"])
        if row["role"] == "SAMPLE":
            last[key] = row["row_id"]
        if row["role"] in {"DUP", "MS", "MSD"} and row.get("parent_row_id") != last.get(key):
            raise ValueError("DUP／MS／MSD 必須位於所屬原樣品之後，且中間不可插入其他一般樣品。")
    result["rows"] = [r for r in result["rows"] if r["role"] not in ROLES] + ordered
    result["sample_count"] = sum(r["role"] == "SAMPLE" for r in ordered)
    result["blank_count"] = sum(r["role"] == "SAMPLE_BLANK" for r in ordered)
    return result
