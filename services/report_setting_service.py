import csv
import os

from flask import current_app


def load_report_setting(method_data):

    if not method_data:
        return None, "尚未載入方法設定資料。"

    report_code = (
        method_data.get(
            "REPORT_CODE",
            ""
        )
        .strip()
    )

    if not report_code:
        return None, "方法設定缺少 REPORT_CODE。"

    report_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Report_Settings.csv"
    )

    if not os.path.exists(report_file):

        return (
            None,
            "尚未匯入報表設定資料。"
        )

    matches = []

    with open(
        report_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if (
                row.get("ACTIVE", "")
                .strip()
                .upper()
                != "Y"
            ):
                continue

            if (
                row.get("REPORT_CODE", "")
                .strip()
                .upper()
                != report_code.upper()
            ):
                continue

            matches.append(row)

    if len(matches) == 0:

        return (
            None,
            "查無 REPORT_CODE = "
            + report_code
            + " 的有效報表設定。"
        )

    if len(matches) > 1:

        return (
            None,
            "REPORT_CODE = "
            + report_code
            + " 找到多筆有效報表設定，"
            + "請檢查 Phyon_Report_Settings.csv。"
        )

    return matches[0], None
