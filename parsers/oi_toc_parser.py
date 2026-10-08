"""OI TOC Reporter parser. Raw counts are never blank-corrected here."""
import re
try:
    from PyPDF2 import PdfReader
except ImportError:
    from pypdf import PdfReader

NUMBER = r"[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
DATE = r"\d{4}/\d{1,2}/\d{1,2}\s+(?:(?:上午|下午)\s*)?\d{1,2}:\d{2}:\d{2}"
START = re.compile(r"^(\d+)\s+(.+?)\s+(" + DATE + r")\s+(\d+)\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s*$")
REPEAT = re.compile(r"^(" + DATE + r")\s+(\d+)\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s*$")
AVERAGE = re.compile(r"^Avg\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s*$", re.I)

def normalize_oi_line(line):
    # This OI Win2PDF layout combines Sample ID/SP# and moves the date
    # to the end of the numeric fragment. Avg reports Area/Conc/Mass.
    moved = re.fullmatch(
        r"(?:(.+?)\s*(\d+)\s+)?(上午|下午)\s+(\d{1,2}:\d{2}:\d{2})\s+"
        r"(\d+)\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+"
        r"([-+]?(?:\d+\.\d{3}|\d+))\s*(\d{4}/\d{1,2}/\d{1,2})", line
    )
    if moved:
        sample, seq, period, clock, rep, area, mass, conc, date = moved.groups()
        prefix = (seq + " " + sample + " ") if sample else ""
        return prefix + " ".join([date, period + clock, rep, area, mass, conc])
    avg = AVERAGE.fullmatch(line)
    if avg:
        area, conc, mass = avg.groups()
        return "Avg " + " ".join([area, mass, conc])
    return line

def _number(value):
    return float(value.replace(",", ""))

def extract_oi_text_lines(page):
    lines = []

    for line in (page.extract_text() or "").splitlines():
        line = line.strip()

        match = re.fullmatch(
            r"(\d+)\s+(" + NUMBER + r")\s+("
            + NUMBER + r")\s+"
            r"([-+]?(?:\d+\.\d{3}|\d+))\s*("
            + DATE + r")\s*(.*?)",
            line
        )

        if match:
            rep, area, mass, conc, date, tail = match.groups()
            prefix = ""

            if tail:
                sample_match = re.fullmatch(
                    r"(.+?)\s*(\d+)",
                    tail
                )

                if not sample_match:
                    raise ValueError(
                        "無法辨識 OI 樣品名稱與序號：" + tail
                    )

                sample, seq = sample_match.groups()
                prefix = seq + " " + sample.strip() + " "

            lines.append(
                prefix + date + " "
                + rep + " " + area + " "
                + mass + " " + conc
            )

        elif re.fullmatch(
            "(" + NUMBER + r")\s+("
            + NUMBER + r")\s+("
            + NUMBER + ")",
            line
        ):
            # OI 平均值列順序為 Area、Conc、Mass
            lines.append("Avg " + line)

    return lines

def parse_oi_toc_pdf(pdf_path):
    """Return one row per SP#, including repeats and reported Avg.

    signal is the instrument-reported Avg Area, not a concentration.
    WASH/TIC/calibration rows are retained for later classification.
    A missing Avg raises an error instead of silently discarding a sample.
    """
    reader = PdfReader(pdf_path)
    print("DEBUG OI first page:")
    print(repr(reader.pages[0].extract_text()))
    rows = []
    current = None
    for page_no, page in enumerate(reader.pages, 1):
        for line in extract_oi_text_lines(page):
            if page_no == 1:
              print("DEBUG OI line:", repr(line))
            line = normalize_oi_line(line.strip())
            match = START.fullmatch(line)
            if match:
                seq, sample, date, rep, area, mass, conc = match.groups()
                if any(r["sequence_no"] == int(seq) for r in rows):
                    raise ValueError("Duplicate SP#: " + seq)
                current = {
                    "sequence_no": int(seq), "sample_id": sample.strip(),
                    "analyte": "TOC", "wavelength": None,
                    "signal": None, "signal_field": "AREA_COUNTS",
                    "analysis_datetime": date, "source_page": page_no,
                    "replicates": [], "instrument_mass_ug_c": None,
                    "instrument_concentration": None,
                }
                rows.append(current)
                current["replicates"].append({
                    "rep_no": int(rep), "analysis_datetime": date,
                    "area_counts": _number(area), "mass_ug_c": _number(mass),
                    "concentration": _number(conc),
                })
                continue
            if current is None:
                continue
            match = REPEAT.fullmatch(line)
            if match:
                date, rep, area, mass, conc = match.groups()
                current["replicates"].append({
                    "rep_no": int(rep), "analysis_datetime": date,
                    "area_counts": _number(area), "mass_ug_c": _number(mass),
                    "concentration": _number(conc),
                })
                continue
            match = AVERAGE.fullmatch(line)
            if match:
                if current["signal"] is not None:
                    raise ValueError("Duplicate Avg for SP#: " + str(current["sequence_no"]))
                area, mass, conc = match.groups()
                current["signal"] = _number(area)
                current["instrument_mass_ug_c"] = _number(mass)
                current["instrument_concentration"] = _number(conc)
    if not rows:
        raise ValueError("No OI TOC sample records found")
    missing = [str(r["sequence_no"]) for r in rows if r["signal"] is None]
    if missing:
        raise ValueError("Missing Avg for SP#: " + ", ".join(missing))
    return rows

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


