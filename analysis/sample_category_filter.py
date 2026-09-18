import re


FORMAL_SAMPLE_MIN_LENGTH = 10

SUPPORTED_SAMPLE_CATEGORIES = {
    "W",
    "D",
    "G"
}


def get_analysis_category(exam_no):

    value = (
        exam_no
        or ""
    ).strip().upper()

    if value.startswith("D-"):
        return "D"

    if value.startswith("G-"):
        return "G"

    if value.startswith("W-"):
        return "W"

    return None


def get_method_family(exam_no):

    value = (
        exam_no
        or ""
    ).strip().upper()

    if value.startswith("D-"):
        value = value[2:]

    elif value.startswith("G-"):
        value = value[2:]

    value = value.replace("-", "")

    match = re.match(
        r"^([A-Z]+\d+?)(\d{2})$",
        value
    )

    if match:

        return match.group(1)

    return value


def detect_formal_sample_category(sample_id):

    value = (
        sample_id
        or ""
    ).strip().upper()

    if len(value) <= FORMAL_SAMPLE_MIN_LENGTH:
        return None

    first_char = value[0]

    if first_char in SUPPORTED_SAMPLE_CATEGORIES:
        return first_char

    return None


def should_include_sample(
    sample_id,
    selected_exam_no
):

    selected_category = (
        get_analysis_category(
            selected_exam_no
        )
    )

    if selected_category is None:

        return True

    sample_category = (
        detect_formal_sample_category(
            sample_id
        )
    )

    # 不是正式樣品編號，例如：
    # ICBK / ICV / BK-1 / QC-1 /
    # DUP-1 / MS-1 / CCBK / CCV
    #
    # 這些不做 W / D / G 過濾
    if sample_category is None:

        return True

    return (
        sample_category
        == selected_category
    )


def filter_analysis_rows(
    rows,
    selected_exam_no
):

    included_rows = []
    excluded_rows = []

    for row in rows:

        role = (
            row.get(
                "role",
                ""
            )
            .strip()
            .upper()
        )

        sample_id = row.get(
            "sample_id",
            ""
        )

        # STANDARD 永遠保留
        if role == "STANDARD":

            included_rows.append(
                row
            )

            continue

        if should_include_sample(
            sample_id,
            selected_exam_no
        ):

            included_rows.append(
                row
            )

        else:

            excluded_row = row.copy()

            excluded_row[
                "exclude_reason"
            ] = (
                "樣品類別與目前分析類別不符"
            )

            excluded_rows.append(
                excluded_row
            )

    return (
        included_rows,
        excluded_rows
    )