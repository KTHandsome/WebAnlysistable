"""Apply permitted edits to signed W427 batches. Original raw rows stay unchanged."""
from copy import deepcopy
from services.w427_sample_service import number


def edit_w427_samples(preview, edits):
    result = deepcopy(preview)
    # Detach working batch rows from the immutable raw-row archive.
    for batch in result["batches"]:
        batch["rows"] = deepcopy(batch["rows"])
    rows = [row for batch in result["batches"] for row in batch["rows"]]
    index = {row["row_id"]:row for row in rows}
    if not isinstance(edits, list) or len(edits) != len(rows):
        raise ValueError("樣品列數不一致，請重新匯入。")
    ids = [e.get("id") for e in edits if isinstance(e, dict)]
    if (len(index) != len(rows) or len(ids) != len(rows) or any(type(i) is not int for i in ids)
            or len(set(ids)) != len(ids) or set(ids) != set(index)):
        raise ValueError("樣品識別重複或不一致。")
    group = {row["row_id"]:(batch["date"], batch["number"]) for batch in result["batches"] for row in batch["rows"]}
    if [group[row["row_id"]] for row in rows] != [group[i] for i in ids]:
        raise ValueError("不可跨日期或批次移動樣品。")
    removed = set()
    for edit in edits:
        row = index[edit["id"]]
        if type(edit.get("excluded")) is not bool:
            raise ValueError("刪除狀態無效。")
        if edit["excluded"]:
            if row["role"] not in {"SAMPLE", "QC"}:
                raise ValueError("此查核列不可直接刪除。")
            removed.add(row["row_id"])
    removed.update(row["row_id"] for row in rows if row.get("parent_row_id") in removed)
    for edit in edits:
        row = index[edit["id"]]
        if row["row_id"] in removed:
            continue
        d = number(edit.get("dilution"), "稀釋倍數")
        if row["role"] in {"SAMPLE", "DUP", "MS", "MSD"}:
            row["dilution"] = d
        elif d != row["dilution"]:
            raise ValueError("不可修改查核列稀釋倍數。")
    for batch in result["batches"]:
        original = [row for row in batch["rows"] if row["row_id"] not in removed]
        kept = [index[i] for i in ids if group[i] == (batch["date"], batch["number"]) and i not in removed]
        def anchor_map(items):
            position = 0; locations = {}; anchors = []
            for row in items:
                if row["role"] not in {"SAMPLE", "DUP", "MS", "MSD"}:
                    anchors.append(row["row_id"]);position += 1
                else:locations[row["row_id"]] = position
            return anchors, locations
        if anchor_map(original) != anchor_map(kept):
            raise ValueError("樣品不可跨越 BK／QC／ICV／CCV 查核列移動。")
        parent = None
        for row in kept:
            if row["role"] == "SAMPLE":parent = row["row_id"]
            if row["role"] in {"DUP", "MS", "MSD"} and row.get("parent_row_id") != parent:
                raise ValueError("DUP／MS／MSD 必須緊接所屬原樣品群組，不可改配其他樣品。")
        batch["rows"] = kept
    result["sample_count"] = sum(row["role"] == "SAMPLE" for batch in result["batches"] for row in batch["rows"])
    return result
