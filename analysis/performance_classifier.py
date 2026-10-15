
# -*- coding: utf-8 -*-
"""Phyon 共用 PRM 原始資料辨識與分流。"""

PRM_SAMPLE_IDS = frozenset({
    "PERFORMANCE",
    "PFM",
})


def is_performance_sample(sample_id):
    """依 Sample ID 精確辨識 PRM。"""

    normalized_id = str(
        sample_id if sample_id is not None else ""
    ).strip().upper()

    return normalized_id in PRM_SAMPLE_IDS


def split_performance_rows(rows):
    """
    將儀器解析資料分為 PRM 與一般分析資料。

    回傳：
        performance_rows
        analysis_rows

    保留原始欄位與順序，不修改輸入資料。
    """

    performance_rows = []
    analysis_rows = []

    for index, row in enumerate(rows, start=1):

        if not isinstance(row, dict):
            raise ValueError(
                "第 {} 筆原始資料不是 dict。".format(index)
            )

        copied_row = dict(row)

        if is_performance_sample(
            row.get("sample_id")
        ):
            performance_rows.append(copied_row)

        else:
            analysis_rows.append(copied_row)

    return performance_rows, analysis_rows
