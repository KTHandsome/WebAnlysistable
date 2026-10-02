import re

from PyPDF2 import PdfReader


def parse_ra7000_pdf(
    pdf_path
):
    """
    解析 Nippon Instruments RA-7000A PDF。

    第一階段擷取：
    1. 分析日期時間
    2. UNIT 儀器資訊
    3. Calibration a / b / r
    4. STD TABLE
    5. SMP TABLE

    此 Parser 只負責儀器原始資料解析，
    不進行 W330 濃度或 QA/QC 計算。
    """

    reader = PdfReader(
        pdf_path
    )

    page_texts = []

    for page in reader.pages:

        page_text = (
            page.extract_text()
            or ""
        )

        page_texts.append(
            page_text
        )

    full_text = "\n".join(
        page_texts
    )

    analysis_datetime = (
        extract_analysis_datetime(
            full_text
        )
    )

    unit_text = (
        extract_unit_text(
            full_text
        )
    )

    calibration = (
        extract_calibration(
            full_text
        )
    )

    standards = []
    samples = []

    table_mode = None

    # ========================================
    # 逐頁解析
    #
    # table_mode 不在每頁重設，
    # 因為 SMP TABLE 會從第 1 頁延續至第 2 頁。
    # ========================================

    for page_text in page_texts:

        lines = (
            page_text
            .replace(
                "\r",
                "\n"
            )
            .splitlines()
        )

        for raw_line in lines:

            line = (
                " ".join(
                    raw_line
                    .strip()
                    .split()
                )
            )

            if not line:
                continue

            line_upper = (
                line.upper()
            )

            # --------------------------------
            # STD TABLE 開始
            # --------------------------------

            if "STD TABLE" in line_upper:

                table_mode = (
                    "STD"
                )

                continue

            # --------------------------------
            # SMP TABLE 開始
            # --------------------------------

            if "SMP TABLE" in line_upper:

                table_mode = (
                    "SMP"
                )

                continue

            # --------------------------------
            # STD 資料
            # --------------------------------

            if table_mode == "STD":

                row = (
                    parse_std_row(
                        line
                    )
                )

                if row is not None:

                    standards.append(
                        row
                    )

                continue

            # --------------------------------
            # SMP 資料
            # --------------------------------

            if table_mode == "SMP":

                row = (
                          parse_sample_row(
                         line,
                         expected_row_no=(
                           len(samples) + 1
                         )
                        )
                      )

                if row is not None:

                    samples.append(
                        row
                    )

    # ========================================
    # 最基本完整性檢查
    # ========================================

    if not standards:

        raise ValueError(
            "RA-7000A PDF 未解析到 STD TABLE 資料。"
        )

    if not samples:

        raise ValueError(
            "RA-7000A PDF 未解析到 SMP TABLE 資料。"
        )

    return {
        "analysis_datetime":
            analysis_datetime,

        "unit":
            unit_text,

        "calibration":
            calibration,

        "standards":
            standards,

        "samples":
            samples
    }


def extract_analysis_datetime(
    text
):
    """
    例如：

    DATE 2026/09/15 09:56
    """

    match = re.search(
        r"\bDATE\s+"
        r"(\d{4}/\d{2}/\d{2})"
        r"\s+"
        r"(\d{2}:\d{2})",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return ""

    return (
        match.group(1)
        + " "
        + match.group(2)
    )


def extract_unit_text(
    text
):
    """
    例如：

    UNIT RA-7000A[SN:231040042]
         + SANPRA 3 (UNIT A)[SN:231070020]
    """

    match = re.search(
        r"(?m)^UNIT\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return ""

    return (
        match.group(1)
        .strip()
    )


def extract_calibration(
    text
):
    """
    Calibration 圖中的：

    a
    b
    r

    若 PDF 文字層沒有提供，
    對應欄位就回傳 None。
    """

    return {
        "a":
            extract_calibration_value(
                text,
                "a"
            ),

        "b":
            extract_calibration_value(
                text,
                "b"
            ),

        "r":
            extract_calibration_value(
                text,
                "r"
            )
    }


def extract_calibration_value(
    text,
    field_name
):
    """
    支援例如：

    a = 4.91817E-01
    b = 2.46624E-01
    r = 0.9982
    """

    pattern = (
        r"(?<![A-Za-z0-9])"
        + re.escape(
            field_name
        )
        + r"\s*=\s*"
        r"([-+]?"
        r"(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:[Ee][-+]?\d+)?)"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    try:

        return float(
            match.group(1)
        )

    except ValueError:

        return None


def parse_std_row(
    line
):
    """
    RA-7000A STD TABLE：

    No.
    SMP NO.
    STD ug/L
    SVOL mL
    CVOL mL
    DVOL mL
    STD ng
    AREA
    MEAS ng
    DEV %
    MEAS TIME
    NOTE
    """

    tokens = line.split()

    date_index = (
        find_date_token_index(
            tokens
        )
    )

    if date_index is None:
        return None

    # 日期前應有：
    #
    # No SMP STD SVOL CVOL DVOL
    # STD_ng AREA MEAS DEV
    #
    prefix = (
        tokens[:date_index]
    )

    if len(prefix) != 10:
        return None

    try:

        row_no = int(
            prefix[0]
        )

        smp_no = int(
            prefix[1]
        )

        std_concentration = float(
            prefix[2]
        )

        svol = float(
            prefix[3]
        )

        cvol = float(
            prefix[4]
        )

        dvol = float(
            prefix[5]
        )

        std_ng = float(
            prefix[6]
        )

        area = float(
            prefix[7]
        )

        meas_ng = float(
            prefix[8]
        )

        dev_text = (
            prefix[9]
        )

        if dev_text == "-":

            dev_percent = None

        else:

            dev_percent = float(
                dev_text
            )

    except ValueError:

        return None

    measure_date = (
        tokens[date_index]
    )

    measure_time = ""

    if len(tokens) > (
        date_index + 1
    ):

        measure_time = (
            tokens[
                date_index + 1
            ]
        )

    note = ""

    if len(tokens) > (
        date_index + 2
    ):

        note = " ".join(
            tokens[
                date_index + 2:
            ]
        )

    return {
        "row_no":
            row_no,

        "smp_no":
            smp_no,

        "std_concentration":
            std_concentration,

        "svol":
            svol,

        "cvol":
            cvol,

        "dvol":
            dvol,

        "std_ng":
            std_ng,

        "area":
            area,

        "meas_ng":
            meas_ng,

        "dev_percent":
            dev_percent,

        "measure_datetime":
            (
                measure_date
                + " "
                + measure_time
            ).strip(),

        "note":
            note
    }

def parse_sample_row(
    line,
    expected_row_no
):
    """
    解析 RA-7000A SMP TABLE。

    RA-7000A PDF 文字層可能出現：

    121ICBK 5.000 5.0005.000 ...

    實際代表：

    No.      = 1
    SMP NO.  = 21
    NAME     = ICBK
    SVOL     = 5.000
    CVOL     = 5.000
    DVOL     = 5.000
    """

    line = (
        line.strip()
    )

    # ========================================
    # 先找最後面的日期時間
    # ========================================

    datetime_match = re.search(
        r"(\d{4}/\d{2}/\d{2})"
        r"\s+"
        r"(\d{2}:\d{2})",
        line
    )

    if not datetime_match:
        return None

    measure_datetime = (
        datetime_match.group(1)
        + " "
        + datetime_match.group(2)
    )

    data_part = (
        line[
            :datetime_match.start()
        ]
        .strip()
    )

    note = (
    line[
        datetime_match.end():
    ]
    .strip()
     )

    if note.upper() in {
    "NO.SMP",
    "NO. SMP",
    "SMP TABLE"
    }:
      note = ""

    # ========================================
    # 開頭可能為：
    #
    # 121ICBK
    # 222ICV
    # 1030D17041726001
    #
    # 前面數字 = No. + SMP NO.
    # ========================================

    prefix_match = re.match(
        r"^(\d+)(.*)$",
        data_part
    )

    if not prefix_match:
        return None

    number_prefix = (
        prefix_match.group(1)
    )

    remainder = (
        prefix_match.group(2)
        .strip()
    )

    expected_row_text = str(
        expected_row_no
    )

    if not number_prefix.startswith(
        expected_row_text
    ):
        return None

    smp_no_text = (
        number_prefix[
            len(expected_row_text):
        ]
    )

    if not smp_no_text:
        return None

    try:

        smp_no = int(
            smp_no_text
        )

    except ValueError:

        return None

    # ========================================
    # 找出 NAME
    #
    # NAME 後面接第一個數值
    # ========================================

    name_match = re.match(
        r"^(.*?)"
        r"\s+"
        r"([-+]?\d+(?:\.\d+)?)"
        r"(.*)$",
        remainder
    )

    if not name_match:
        return None

    sample_name = (
        name_match.group(1)
        .strip()
    )

    if not sample_name:
        return None

    numeric_text = (
        name_match.group(2)
        + name_match.group(3)
    )

    # ========================================
    # 直接抓所有浮點數
    #
    # 即使：
    # 5.0005.000
    #
    # 也會抓成：
    # 5.000
    # 5.000
    # ========================================

    numeric_match = re.search(
            r"^"
            r"(\d+\.\d{3})"
            r"\s*"
            r"(\d+\.\d{3})"
            r"\s*"
            r"(\d+\.\d{3})"
            r"\s+"
            r"(\d+\.\d{6})"
            r"\s+"
            r"(\d+\.\d{4})"
            r"\s+"
            r"(\d+\.\d{3})"
            r"$",
            numeric_text.strip()
        )

    if not numeric_match:
        return None

    try:

        svol = float(
            numeric_match.group(1)
        )

        cvol = float(
            numeric_match.group(2)
        )

        dvol = float(
            numeric_match.group(3)
        )

        area = float(
            numeric_match.group(4)
        )

        meas_ng = float(
            numeric_match.group(5)
        )

        concentration = float(
            numeric_match.group(6)
        )

    except ValueError:

        return None

    return {
        "row_no":
            expected_row_no,

        "smp_no":
            smp_no,

        "sample_name":
            sample_name,

        "svol":
            svol,

        "cvol":
            cvol,

        "dvol":
            dvol,

        "area":
            area,

        "meas_ng":
            meas_ng,

        "concentration":
            concentration,

        "measure_datetime":
            measure_datetime,

        "note":
            note
    }

def find_date_token_index(
    tokens
):
    """
    找 yyyy/MM/dd 所在欄位。
    """

    for index, token in enumerate(
        tokens
    ):

        if re.fullmatch(
            r"\d{4}/\d{2}/\d{2}",
            token
        ):

            return index

    return None