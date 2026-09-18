from analysis.sample_category_filter import (
    detect_formal_sample_category,
    get_analysis_category
)


def is_ccv_row(row):

    role = (
        row.get(
            "role",
            ""
        )
        .strip()
        .upper()
    )

    return role == "CCV"


def is_icv_row(row):

    role = (
        row.get(
            "role",
            ""
        )
        .strip()
        .upper()
    )

    return role == "ICV"

def is_icbk_row(row):

    role = (
        row.get(
            "role",
            ""
        )
        .strip()
        .upper()
    )

    return role == "ICBK"


def is_ccbk_row(row):

    role = (
        row.get(
            "role",
            ""
        )
        .strip()
        .upper()
    )

    return role == "CCBK"


def detect_batch_category(rows):

    categories = set()

    for row in rows:

        if (
            row.get(
                "role",
                ""
            )
            .strip()
            .upper()
            != "SAMPLE"
        ):
            continue

        sample_category = (
            detect_formal_sample_category(
                row.get(
                    "sample_id",
                    ""
                )
            )
        )

        if sample_category:

            categories.add(
                sample_category
            )

    if len(categories) == 1:
        return next(iter(categories))

    if len(categories) == 0:
        return None

    return "MIXED"


def split_analysis_batches(rows):

    if not rows:
        return [], []

    pre_batch_rows = []

    icv_index = None
    icbk_index = None

    for index, row in enumerate(rows):

        if (
            icbk_index is None
            and is_icbk_row(row)
        ):
            icbk_index = index

        if is_icv_row(row):

            icv_index = index
            break

    # 找不到 ICV 時，不強行切批
    if icv_index is None:

        return [], rows.copy()

    # 第一批若有 ICBK，
    # ICBK 屬於第一批，不屬於全域前置資料
    if (
        icbk_index is not None
        and icbk_index < icv_index
    ):

        first_batch_start_index = (
            icbk_index
        )

    else:

        first_batch_start_index = (
            icv_index
        )

    # 此處只留下真正位於第一批之前的資料，
    # 例如 STANDARD
    pre_batch_rows = rows[
        :first_batch_start_index
    ]

    batches = []

    batch_start_index = (
        first_batch_start_index
    )

    batch_no = 1

    last_ccbk_index = None

    last_ccv_index = None

    for index in range(
        first_batch_start_index,
        len(rows)
    ):

        row = rows[index]

        if is_ccbk_row(row):

            last_ccbk_index = index

        if not is_ccv_row(row):
            continue

        batch_rows = rows[
            batch_start_index:
            index + 1
        ]

        batches.append(
            {
                "batch_no": batch_no,

                "start_check":
                    rows[
                        batch_start_index
                    ],

                "end_check":
                    row,

                "rows":
                    batch_rows,

                "batch_category":
                    detect_batch_category(
                        batch_rows
                    )
            }
        )

        last_ccv_index = index


        # 下一批應從前一批的 CCBK 開始，
        # 使 CCBK + CCV 同時成為相鄰兩批的
        # 邊界品質管制資料。
        if (
            last_ccbk_index is not None
            and last_ccbk_index
            > batch_start_index
        ):

            batch_start_index = (
                last_ccbk_index
            )

        else:

            # 若資料異常缺少 CCBK，
            # 至少退回以 CCV 作為下一批起點
            batch_start_index = index

        last_ccbk_index = None

       

        batch_no += 1

    # 只有最後一個 CCV 後面真的還有資料，
    # 才建立未完成批次。
    if (
        last_ccv_index is not None
        and last_ccv_index < len(rows) - 1
    ):

        trailing_rows = rows[
            batch_start_index:
        ]

        batches.append(
            {
                "batch_no": batch_no,

                "start_check":
                    rows[
                        batch_start_index
                    ],

                "end_check":
                    None,

                "rows":
                    trailing_rows,

                "batch_category":
                    detect_batch_category(
                        trailing_rows
                    ),

                "incomplete":
                    True
            }
        )

    return (
        batches,
        pre_batch_rows
    )


def filter_batches_by_exam_no(
    rows,
    selected_exam_no
):

    selected_category = (
        get_analysis_category(
            selected_exam_no
        )
    )

    if selected_category is None:

        return rows.copy(), [], []

    (
        batches,
        pre_batch_rows
    ) = split_analysis_batches(
        rows
    )

    # 無法切批時，先不破壞原始資料
    if not batches:

        return rows.copy(), [], []

    included_rows = (
        pre_batch_rows.copy()
    )

    excluded_rows = []

    included_batches = []

    added_sequence_numbers = set()

    # 前置資料先登記
    for row in included_rows:

        sequence_no = row.get(
            "sequence_no"
        )

        added_sequence_numbers.add(
            sequence_no
        )

    for batch in batches:

        batch_category = (
            batch.get(
                "batch_category"
            )
        )

        # 無正式樣品或混合類別：
        # 先保留，不自動刪除
        should_include = (
            batch_category
            in {
                None,
                "MIXED",
                selected_category
            }
        )

        if should_include:

            included_batches.append(
                batch
            )

            for row in batch["rows"]:

                sequence_no = (
                    row.get(
                        "sequence_no"
                    )
                )

                # CCV 可能同時存在於兩批，
                # 畫面只保留一筆
                if (
                    sequence_no
                    in added_sequence_numbers
                ):
                    continue

                included_rows.append(
                    row
                )

                added_sequence_numbers.add(
                    sequence_no
                )

        else:

            for row in batch["rows"]:

                excluded_row = (
                    row.copy()
                )

                excluded_row[
                    "exclude_reason"
                ] = (
                    "分析批次類別 "
                    + str(
                        batch_category
                    )
                    + " 與目前分析類別 "
                    + selected_category
                    + " 不符"
                )

                excluded_row[
                    "batch_no"
                ] = batch[
                    "batch_no"
                ]

                excluded_rows.append(
                    excluded_row
                )

    return (
        included_rows,
        excluded_rows,
        included_batches
    )
