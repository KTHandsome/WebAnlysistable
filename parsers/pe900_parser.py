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
    document_lines = []

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

        document_lines.extend(page_lines)

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
                        "sequence_no":current_sequence_no,

                        "sample_id":"",

                        "analysis_datetime": "",

                        "signal":None,

                        "analyte":"",

                        "wavelength":None
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
                r"Sample\s+ID\s*:?\s*(.*?)"
                r"\s+Date\s+Collected\s*:\s*"
                r"(\d{1,2}/\d{1,2}/\d{4})"
                r"\s+(\d{1,2}:\d{2}:\d{2})"
                r"\s*(AM|PM)",
                clean_line,
                flags=re.IGNORECASE
            )

            if sample_match:

                current_row["sample_id"] = (
                    sample_match.group(1).strip()
                )

                from datetime import datetime

                collected_text = (
                    sample_match.group(2)
                    + " "
                    + sample_match.group(3)
                    + " "
                    + sample_match.group(4).upper()
                )

                collected_datetime = datetime.strptime(
                    collected_text,
                    "%m/%d/%Y %I:%M:%S %p"
                )

                current_row["analysis_datetime"] = (
                    collected_datetime.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

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

    apply_calibration_summary_signals(results, document_lines)

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

# Numeric IDs in the PE900 calibration report identify concentration standards.
_PE900_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"


def _pe900_number(text):
    import math
    if not re.fullmatch(_PE900_NUMBER, str(text).strip()):
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def _pe900_half_unit(text):
    from decimal import Decimal
    return float(Decimal(10) ** Decimal(str(text)).as_tuple().exponent) / 2.0


def apply_calibration_summary_signals(rows, lines):
    """Use the printed calibration table, never subtract STD0 a second time.

    A table belongs to the preceding sequence block, including across pages.
    Missing/ambiguous standards raise ValueError rather than silently fitting
    the pre-auto-zero Mean. Non-standard rows keep their existing Mean signal.
    """
    import math
    sequence = None
    table = None
    summaries = []
    header = re.compile(r"Calibration\s+data\s+for\s+([A-Za-z][A-Za-z0-9]*)\s+(" + _PE900_NUMBER + r")", re.I)
    coefficients = re.compile(r"Correlation\s+Coef\.?\s*:\s*(" + _PE900_NUMBER + r")\s+Slope\s*:\s*(" + _PE900_NUMBER + r")\s+Intercept\s*:\s*(" + _PE900_NUMBER + r")", re.I)
    for line in lines:
        match = re.search(r"Sequence\s+No\.?\s*:?\s*(\d+)", line, re.I)
        if match:
            if table is not None:
                raise ValueError("PE900 檢量線摘要表不完整，請確認標準點與方程式。")
            sequence = int(match.group(1))
        match = header.search(line)
        if match:
            if table is not None or sequence is None:
                raise ValueError("PE900 檢量線摘要表缺少明確的量測序列關聯。")
            if not re.search(r"Equation:\s*Linear,\s*Calculated\s+Intercept", line, re.I):
                raise ValueError("PE900 目前僅支援一次線性回歸（計算截距），請確認報表。")
            table = dict(anchor=sequence, analyte=match.group(1), wavelength=float(match.group(2)), points=[])
            continue
        if table is None:
            continue
        match = coefficients.search(line)
        if match:
            table['coefficients'] = match.groups()
            summaries.append(table)
            table = None
            continue
        tokens = line.split()
        if tokens and _pe900_number(tokens[0]) is not None:
            # ID, Mean Signal, Entered Conc, Calculated Conc, SD, RSD, Residual.
            if len(tokens) != 7 or any(_pe900_number(v) is None for v in tokens[:5]):
                raise ValueError("PE900 檢量線摘要列格式不完整，未採用猜測值。")
            point = dict(id=float(tokens[0]), signal=float(tokens[1]), concentration=float(tokens[2]), signal_text=tokens[1])
            if point['id'] != point['concentration']:
                raise ValueError("PE900 標準名稱與摘要表設定濃度不一致。")
            table['points'].append(point)
    if table is not None:
        raise ValueError("PE900 檢量線摘要表未結束，請確認完整 PDF。")
    numeric_rows = [r for r in rows if _pe900_number(r['sample_id']) is not None]
    used = set()
    previous_anchor = -1
    for summary in summaries:
        points = summary['points']
        if len(points) < 2 or len({p['id'] for p in points}) != len(points):
            raise ValueError("PE900 檢量線摘要標準點不足或重複。")
        candidates = [r for r in numeric_rows if previous_anchor < r['sequence_no'] <= summary['anchor']]
        if len(candidates) != len(points):
            raise ValueError("PE900 檢量線摘要與標準量測筆數不一致，請確認完整檔案。")
        assigned = []
        for point in points:
            matches = [r for r in candidates if _pe900_number(r['sample_id']) == point['id']
                       and str(r.get('analyte', '')).upper() == summary['analyte'].upper()
                       and r.get('wavelength') == summary['wavelength']]
            if len(matches) != 1 or matches[0]['sequence_no'] in used:
                raise ValueError("PE900 檢量線摘要無法唯一配對標準點／元素／波長。")
            row = matches[0]
            # Nonzero Mean must agree with the summary within its printed precision.
            # STD0 intentionally differs after the instrument's auto-zero.
            if point['concentration'] != 0 and not math.isclose(row['signal'], point['signal'], rel_tol=0, abs_tol=_pe900_half_unit(point['signal_text']) + 1e-12):
                raise ValueError("PE900 非零標準點 Mean 與檢量線摘要不一致。")
            assigned.append((row, point))
        # Check the independently fitted curve against printed coefficients with
        # a bound derived from rounding each printed signal, not exact equality.
        xs = [p['concentration'] for p in points]
        ys = [p['signal'] for p in points]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        ssx = sum((x - mean_x) ** 2 for x in xs)
        ssy = sum((y - mean_y) ** 2 for y in ys)
        if ssx <= 0 or ssy <= 0:
            raise ValueError("PE900 檢量線摘要無有效變化，無法回歸。")
        cross = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        slope = cross / ssx
        intercept = mean_y - slope * mean_x
        r_value = cross / math.sqrt(ssx * ssy)
        printed_r, printed_a, printed_b = summary['coefficients']
        errors = [_pe900_half_unit(p['signal_text']) for p in points]
        slope_error = sum(abs(x - mean_x) * e for x, e in zip(xs, errors)) / ssx
        intercept_error = sum(errors) / len(errors) + abs(mean_x) * slope_error
        if (abs(slope - float(printed_a)) > slope_error + _pe900_half_unit(printed_a) + 1e-12
                or abs(intercept - float(printed_b)) > intercept_error + _pe900_half_unit(printed_b) + 1e-12):
            raise ValueError("PE900 摘要標準點與儀器斜率／截距不一致，請確認報表。")
        # Correlation changes with rounded signals too; bound its possible change
        # through the perturbation norm of the centered y vector.
        perturbation = math.sqrt(sum(e * e for e in errors))
        correlation_error = 2 * perturbation / max(math.sqrt(ssy) - perturbation, 1e-15)
        if abs(r_value - float(printed_r)) > correlation_error + _pe900_half_unit(printed_r) + 1e-12:
            raise ValueError("PE900 摘要標準點與儀器相關係數不一致。")
        for row, point in assigned:
            row['original_mean_signal'] = row['signal']
            row['signal'] = point['signal']
            row['signal_source'] = 'PE900_CALIBRATION_MEAN_SIGNAL'
            row['instrument_calibration_concentration'] = point['concentration']
            row['instrument_calibration_slope'] = float(printed_a)
            row['instrument_calibration_intercept'] = float(printed_b)
            row['instrument_calibration_r'] = float(printed_r)
            used.add(row['sequence_no'])
        previous_anchor = summary['anchor']
    if any(r['sequence_no'] not in used for r in numeric_rows):
        raise ValueError("PE900 標準點缺少完整檢量線摘要表，未使用歸零前 Mean 計算。")
