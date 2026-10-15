# services/performance_diff_service.py

import csv
import io
import os


# ========================================
# Performance CSV 差異比對
# ========================================

def compare_performance_csv(
    official_path,
    candidate_bytes
):
    """
    比對正式 CSV 與待發布 CSV。

    以 CONTROL_ID 作為唯一識別。

    回傳：
        official_count
        candidate_count
        added
        removed
        modified
        unchanged

    本函式只讀取資料，不寫入檔案。
    """

    # ========================================
    # 1. 解析 CSV
    # ========================================

    def parse_csv(file_bytes):

        text = file_bytes.decode("utf-8-sig")

        reader = csv.DictReader(
            io.StringIO(text)
        )

        if (
            not reader.fieldnames
            or "CONTROL_ID" not in reader.fieldnames
        ):
            raise ValueError(
                "Performance CSV 缺少 CONTROL_ID 欄位。"
            )

        result = {}

        for row_number, row in enumerate(
            reader,
            start=2
        ):

            if None in row:
                raise ValueError(
                    "第 {} 列：CSV 欄位數量不正確。"
                    .format(row_number)
                )

            control_id = str(
                row.get("CONTROL_ID") or ""
            ).strip().upper()

            if not control_id:
                raise ValueError(
                    "第 {} 列：CONTROL_ID 不可空白。"
                    .format(row_number)
                )

            if control_id in result:
                raise ValueError(
                    "第 {} 列：CONTROL_ID 重複：{}"
                    .format(row_number, control_id)
                )

            result[control_id] = {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
            }

        return result

    # ========================================
    # 2. 取得待發布資料
    # ========================================

    if not isinstance(candidate_bytes, bytes):
        raise ValueError(
            "Performance 待發布 CSV 必須為 bytes。"
        )

    candidate = parse_csv(
        candidate_bytes
    )

    # ========================================
    # 3. 取得現有正式資料
    # ========================================

    if os.path.isfile(official_path):

        with open(official_path, "rb") as f:
            official_bytes = f.read()

        official = parse_csv(
            official_bytes
        )

    else:

        # 尚未建立正式 CSV，全部視為新增
        official = {}

    # ========================================
    # 4. 比對 CONTROL_ID
    # ========================================

    official_ids = set(official)
    candidate_ids = set(candidate)

    added = sorted(
        candidate_ids - official_ids
    )

    removed = sorted(
        official_ids - candidate_ids
    )

    modified = []
    unchanged = []

    for control_id in sorted(
        official_ids & candidate_ids
    ):

        if (
            official[control_id]
            == candidate[control_id]
        ):

            unchanged.append(
                control_id
            )

        else:

            modified.append(
                control_id
            )

    # ========================================
    # 5. 回傳差異摘要
    # ========================================

    return {
        "official_count": len(official),
        "candidate_count": len(candidate),
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged
    }