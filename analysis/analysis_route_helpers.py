import csv
import os

from flask import current_app


def get_analysis_state_key(method_code):

    method_code = str(
        method_code or ""
    ).strip().upper()

    if not method_code:
        raise ValueError(
            "缺少分析方法代碼，無法建立分析狀態識別碼。"
        )

    return method_code + "_CURRENT"


def get_analysis_session_key(method_code):

    method_code = str(
        method_code or ""
    ).strip().lower()

    if not method_code:
        raise ValueError(
            "缺少分析方法代碼，無法建立分析 Session 識別碼。"
        )

    return method_code + "_formal_analysis_id"


def get_analysis_page_endpoint(method_code):

    method_code = str(
        method_code or ""
    ).strip().upper()

    if not method_code:
        raise ValueError(
            "缺少分析方法代碼，無法取得分析頁面。"
        )

    method_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(method_file):
        raise ValueError(
            "尚未匯入方法設定資料。"
        )

    method_data = None

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            row_method_code = str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper()

            active = str(
                row.get("ACTIVE", "") or ""
            ).strip().upper()

            if (
                row_method_code == method_code
                and active == "Y"
            ):
                method_data = row
                break

    if method_data is None:
        raise ValueError(
            "查無分析方法 "
            + method_code
            + " 的有效方法設定。"
        )

    import_type = str(
        method_data.get("IMPORT_TYPE", "") or ""
    ).strip().upper()

    if import_type == "RA7000A_PDF":
        return "analysis_w330"

    if import_type in {
        "PE900_PDF",
        "TOC_PDF"
    }:
        return "analysis_w43401"

    raise ValueError(
        "尚未設定 IMPORT_TYPE "
        + import_type
        + " 的分析頁面。"
    )