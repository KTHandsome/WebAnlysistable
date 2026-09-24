import re
from PyPDF2 import PdfReader


def parse_pe900_pdf(pdf_path):
    """
    解析 PE900 PDF。

    擷取：
    1. Sequence 編號
    2. Sample ID
    3. Mean 的 BlnkCorr Signal
    4. Analyte
    5. Wavelength

    PE900 PDF 的文字物件順序可能與畫面順序不同，
    因此不可單純依 extract_text() 的輸出順序
    配對 Sequence 與 Mean。

    本版本先依 PDF 座標重建頁面閱讀順序，
    再依 Sequence 的實際視覺順序配對資料。

    同時支援：
    1. Sequence 資料跨頁
    2. Mean 出現在下一頁頁首
    """

    reader = PdfReader(
        pdf_path
    )

    rows_by_sequence = {}

    current_sequence_no = None

    analyte = ""
    wavelength = None

    # ========================================
    # 逐頁依 PDF 座標重建文字順序
    # ========================================

    for page in reader.pages:

        page_lines = (
            extract_page_lines_by_position(
                page
            )
        )

        for line in page_lines:

            clean_line = (
                line.strip()
            )

            if not clean_line:
                continue

            # --------------------------------
            # Sequence No.
            # --------------------------------

            sequence_match = re.search(
                r"Sequence\s+No\.?\s*:?\s*(\d+)",
                clean_line,
                flags=re.IGNORECASE
            )

            if sequence_match:

                current_sequence_no = int(
                    sequence_match.group(1)
                )

                if (
                    current_sequence_no
                    not in rows_by_sequence
                ):

                    rows_by_sequence[
                        current_sequence_no
                    ] = {
                        "sequence_no":
                            current_sequence_no,

                        "sample_id":
                            "",

                        "signal":
                            None,

                        "analyte":
                            "",

                        "wavelength":
                            None
                    }

                continue

            # 還沒找到任何 Sequence，
            # 不解析 Sequence 所屬資料
            if current_sequence_no is None:
                continue

            current_row = (
                rows_by_sequence[
                    current_sequence_no
                ]
            )

            # --------------------------------
            # Sample ID
            # --------------------------------

            sample_match = re.search(
                r"Sample\s+ID\s*:?\s*"
                r"(.*?)"
                r"\s+Date\s+Collected\s*:",
                clean_line,
                flags=re.IGNORECASE
            )

            if sample_match:

                sample_id = (
                    sample_match.group(1)
                    .strip()
                )

                current_row[
                    "sample_id"
                ] = sample_id

                continue

            # --------------------------------
            # Analyte / Wavelength
            # --------------------------------

            analyte_match = re.search(
                r"Analyte\s*:?\s*"
                r"([A-Za-z][A-Za-z0-9]*)"
                r"\s+"
                r"(\d+(?:\.\d+)?)",
                clean_line,
                flags=re.IGNORECASE
            )

            if analyte_match:

                analyte = (
                    analyte_match.group(1)
                    .strip()
                )

                try:

                    wavelength = float(
                        analyte_match.group(2)
                    )

                except ValueError:

                    wavelength = None

                current_row[
                    "analyte"
                ] = analyte

                current_row[
                    "wavelength"
                ] = wavelength

                continue

            # --------------------------------
            # Mean
            #
            # 取 Mean 列最後一個數字，
            # 即 BlnkCorr Signal。
            #
            # 例如：
            #
            # Mean: 0.6174 0.6174 0.0117
            #
            # → 0.0117
            #
            # 檢量線：
            #
            # Mean: [0.25] 0.0047
            #
            # → 0.0047
            # --------------------------------

            if re.search(
                r"\bMean\s*:",
                clean_line,
                flags=re.IGNORECASE
            ):

                signal = (
                    extract_mean_blnkcorr_signal(
                        clean_line
                    )
                )

                if signal is not None:

                    # 同一 Sequence 正常只採用
                    # 第一筆視覺上的 Mean。
                    #
                    # 避免頁尾 / 頁首文字重複
                    # 或其他摘要資料覆蓋原值。
                    if (
                        current_row[
                            "signal"
                        ]
                        is None
                    ):

                        current_row[
                            "signal"
                        ] = signal

    # ========================================
    # 補上全域 Analyte / Wavelength
    #
    # 某些跨頁 Sequence 的 Analyte 文字
    # 可能與 Sequence 分頁，因此以本次分析
    # 已取得值補齊。
    # ========================================

    results = []

    for sequence_no in sorted(
        rows_by_sequence.keys()
    ):

        row = (
            rows_by_sequence[
                sequence_no
            ]
        )

        if (
            not row.get(
                "analyte"
            )
            and analyte
        ):

            row[
                "analyte"
            ] = analyte

        if (
            row.get(
                "wavelength"
            )
            is None
            and wavelength is not None
        ):

            row[
                "wavelength"
            ] = wavelength

        # Sequence 必須有 Sample ID
        if not str(
            row.get(
                "sample_id",
                ""
            )
            or ""
        ).strip():

            continue

        # Signal 沒解析成功不可偷偷帶錯值，
        # 直接略過，讓測試能明確發現問題。
        if row.get(
            "signal"
        ) is None:

            continue

        results.append(
            row
        )

    return results


def multiply_pdf_matrices(
    matrix_a,
    matrix_b
):
    """
    合併 PDF Text Matrix 與
    Current Transformation Matrix。

    PyPDF2 visitor_text 傳入的 tm
    不一定是頁面最終絕對座標，
    必須與 cm 合併後才能取得
    實際 X / Y 位置。
    """

    a, b, c, d, e, f = matrix_a
    g, h, i, j, k, l = matrix_b

    return [
        a * g + b * i,
        a * h + b * j,
        c * g + d * i,
        c * h + d * j,
        e * g + f * i + k,
        e * h + f * j + l
    ]

def extract_page_lines_by_position(
    page
):
    """
    依 PDF 文字座標重建頁面閱讀順序。

    PyPDF2 一般 extract_text() 的物件輸出順序
    不一定等於人眼看到的上下順序。

    這裡使用 visitor_text：
    1. 取得文字
    2. 取得 X / Y 座標
    3. 相近 Y 視為同一行
    4. 同一行依 X 由左至右排列
    """

    fragments = []

    def visitor_text(
        text,
        cm,
        tm,
        font_dict,
        font_size
    ):

        if not text:
            return

        try:

            absolute_matrix = (
                multiply_pdf_matrices(
                    tm,
                    cm
                )
            )

            x = float(
                absolute_matrix[4]
            )

            y = float(
                absolute_matrix[5]
            )

        except (
            TypeError,
            ValueError,
            IndexError
        ):

            return

        # PyPDF2 有時一次回傳多行文字。
        # 將每一行拆開，並依字型高度向下排列。
        text_lines = (
            str(text)
            .replace(
                "\r",
                "\n"
            )
            .split(
                "\n"
            )
        )

        line_height = 10.0

        try:

            parsed_font_size = float(
                font_size
            )

            if parsed_font_size > 0:

                line_height = (
                    parsed_font_size
                    * 1.15
                )

        except (
            TypeError,
            ValueError
        ):

            pass

        for index, text_line in enumerate(
            text_lines
        ):

            text_line = (
                text_line.strip()
            )

            if not text_line:
                continue

            fragments.append(
                {
                    "x":
                        x,

                    "y":
                        y
                        - (
                            index
                            * line_height
                        ),

                    "text":
                        text_line
                }
            )

    try:

        page.extract_text(
            visitor_text=visitor_text
        )

    except Exception:

        # 若特定 PDF 不支援座標 visitor，
        # 至少保留一般文字解析能力。
        fallback_text = (
            page.extract_text()
            or ""
        )

        return [
            line.strip()
            for line in
            fallback_text.splitlines()
            if line.strip()
        ]

    if not fragments:

        fallback_text = (
            page.extract_text()
            or ""
        )

        return [
            line.strip()
            for line in
            fallback_text.splitlines()
            if line.strip()
        ]

    # ========================================
    # 依 Y 由上往下排列
    # ========================================

    fragments.sort(
        key=lambda item: (
            -item["y"],
            item["x"]
        )
    )

    grouped_lines = []

    # 同一列 PDF 文字的 Y 座標通常會有
    # 極小浮點差異，因此允許少量容差。
    y_tolerance = 2.5

    for fragment in fragments:

        matched_line = None

        for line_group in reversed(
            grouped_lines
        ):

            if abs(
                line_group["y"]
                - fragment["y"]
            ) <= y_tolerance:

                matched_line = (
                    line_group
                )

                break

            # grouped_lines 已依 Y 排序，
            # 差距過大就不用繼續往前找。
            if (
                line_group["y"]
                - fragment["y"]
                > 10
            ):

                break

        if matched_line is None:

            grouped_lines.append(
                {
                    "y":
                        fragment["y"],

                    "parts":
                        [
                            fragment
                        ]
                }
            )

        else:

            matched_line[
                "parts"
            ].append(
                fragment
            )

    # ========================================
    # 同一行依 X 左 → 右組合
    # ========================================

    result_lines = []

    for line_group in grouped_lines:

        parts = sorted(
            line_group["parts"],
            key=lambda item:
                item["x"]
        )

        texts = []

        for part in parts:

            text_value = (
                part["text"]
                .strip()
            )

            if not text_value:
                continue

            texts.append(
                text_value
            )

        if texts:

            result_lines.append(
                " ".join(
                    texts
                )
            )

    return result_lines


def extract_mean_blnkcorr_signal(
    line
):
    """
    取得單一 Mean 列的 BlnkCorr Signal。

    PE900 常見格式：

    Mean: [0.25] 0.0047

    或：

    Mean: 0.6174 0.6174 0.0117

    最後一個數字即 BlnkCorr Signal。
    """

    mean_match = re.search(
        r"\bMean\s*:\s*(.*)$",
        line,
        flags=re.IGNORECASE
    )

    if not mean_match:
        return None

    mean_text = (
        mean_match.group(1)
    )

    numbers = re.findall(
        r"[-+]?"
        r"(?:"
        r"\d+(?:\.\d*)?"
        r"|"
        r"\.\d+"
        r")",
        mean_text
    )

    if not numbers:
        return None

    try:

        return float(
            numbers[-1]
        )

    except ValueError:

        return None