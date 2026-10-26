import csv
import os

from flask import current_app


def load_control_and_method_data(form_data):
    # W427 has distinct report bases under one method; never select its first CSV row.
    if str(form_data.get("method_code") or "").strip().upper() == "W427":
        from services.w427_setting_service import load_w427_settings
        return load_w427_settings(form_data)


    control_data = {}
    method_data = None

    ctrl_year = form_data.get(
        "ctrl_year",
        ""
    ).strip()

    category = form_data.get(
        "category",
        ""
    ).strip()

    exam_name = form_data.get(
        "exam_name",
        ""
    ).strip()

    method_code = form_data.get(
        "method_code",
        ""
    ).strip()

    instrument_id = form_data.get(
        "instrument_id",
        ""
    ).strip()

    selected_exam_no = form_data.get(
    "selected_exam_no",
    ""
).strip()

    if not ctrl_year:
        return {}, None, "請選擇管制年度。"

    if not exam_name:
        return {}, None, "請輸入測項名稱。"

    if not method_code:
        return {}, None, "請輸入分析方法。"

    # ========================================
    # 先載入方法設定
    # 方法設定是分析流程必要資料，
    # 不應依賴是否存在年度管制圖
    # ========================================
    method_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(
        method_file
    ):

        return (
            {},
            None,
            "尚未匯入方法設定資料。"
        )

    method_matches = []

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        method_reader = csv.DictReader(
            f
        )

        for method_row in method_reader:

            if (
                method_row.get(
                    "ACTIVE",
                    ""
                )
                .strip()
                .upper()
                != "Y"
            ):
                continue

            if (
                method_row.get(
                    "METHOD_CODE",
                    ""
                )
                .strip()
                .upper()
                != method_code.upper()
            ):
                continue

            method_matches.append(
                method_row
            )

    if len(method_matches) == 0:

        return (
            {},
            None,
            "查無對應的方法設定。"
        )

    method_data = method_matches[0]

    method_exam_no = (
        method_data.get(
            "EXAMNO",
            ""
        )
        .strip()
    )

    method_category = str(
        method_data.get("CATEGORY_CODE", "")
        or ""
    ).strip().upper()

    effective_exam_no = selected_exam_no

    if (
        not effective_exam_no
        and method_category == category.upper()
    ):
        effective_exam_no = method_exam_no

    # ========================================
    # 再載入年度管制資料
    # 年度檔案本身不存在仍視為設定錯誤
    # ========================================
    csv_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Control_"
        + ctrl_year
        + ".csv"
    )

    if not os.path.exists(
        csv_file
    ):

        return (
            {},
            method_data,
            "尚未匯入 "
            + ctrl_year
            + " 年管制資料。"
        )

    base_matches = []

    with open(
        csv_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f
        )

        for row in reader:

            if (
                row.get(
                    "CTRL_YEAR",
                    ""
                ).strip()
                != ctrl_year
            ):
                continue

            if (
                row.get(
                    "CATEGORY_CODE",
                    ""
                )
                .strip()
                .upper()
                != category.upper()
            ):
                continue

            row_exam_name = (
                row.get(
                    "EXAMNAME",
                    ""
                )
                .strip()
            )

            row_exam_alias = (
                row.get(
                    "EXALIAS",
                    ""
                )
                .strip()
            )

            row_exam_no = (
                row.get(
                    "EXAMNO",
                    ""
                )
                .strip()
            )

            if effective_exam_no:

                if (
                    row_exam_no
                    != effective_exam_no
                ):
                    continue

            else:

                if (
                    exam_name
                    != row_exam_name
                    and exam_name
                    != row_exam_alias
                ):
                    continue

            if (
                row.get(
                    "EM_NUM",
                    ""
                )
                .strip()
                .upper()
                != method_code.upper()
            ):
                continue

            base_matches.append(
                row
            )

    # ========================================
    # 找不到該測項年度管制資料
    # → 視為「無管制圖項目」
    # → 不阻止進入分析頁
    # ========================================
    if len(base_matches) == 0:

        return (
            {},
            method_data,
            None
        )

    # ========================================
    # 有管制資料時才套用儀器適用規則
    #
    # 1. 儀器專屬資料優先
    # 2. 沒有專屬資料時使用共用資料
    # ========================================
    specific_matches = []
    common_matches = []

    for row in base_matches:

        row_instrument = (
            row.get(
                "LABPARTID",
                ""
            )
            .strip()
        )

        if row_instrument == "":

            common_matches.append(
                row
            )

        elif (
            instrument_id
            and row_instrument.upper()
            == instrument_id.upper()
        ):

            specific_matches.append(row)

    if (
        instrument_id and specific_matches
    ):

        matches = specific_matches

    else:

        matches = common_matches

    # 已確認這個項目有管制資料，
    # 但選定儀器沒有適用資料，
    # 這仍屬於設定問題，不可當成無管制項目
    if len(matches) == 0:

        if instrument_id:

            return (
                {},
                method_data,
                "此項目已有年度管制資料，"
                "但查無此儀器專屬或共用的管制資料。"
            )

        return (
            {},
            method_data,
            "此項目已有年度管制資料，"
            "但查無共用管制資料。"
        )

    if len(matches) > 1:

        # 使用者已指定測項代碼時，
        # 依 EXAMNO 精確鎖定
        if selected_exam_no:

            selected_matches = []

            for row in matches:

                if (
                    row.get(
                        "EXAMNO",
                        ""
                    )
                    .strip()
                    == selected_exam_no
                ):

                    selected_matches.append(
                        row
                    )

            if len(selected_matches) == 1:

                control_data = (
                    selected_matches[0]
                )

                return (
                    control_data,
                    method_data,
                    None
                )

        # 尚未選擇，回傳候選資料給 Basic Info
        return (
            {
                "_multiple_matches":
                    matches
            },
            method_data,
            "找到多筆符合的年度管制資料，"
            "請選擇測項代碼。"
        )

    control_data = matches[0]

    return (
        control_data,
        method_data,
        None
    )

