import re
from PyPDF2 import PdfReader


def parse_pe900_pdf(pdf_path):
    """
    解析 PE900 PDF。

    擷取：
    1. Sequence 編號
    2. Sample ID
    3. Mean 的 BlnkCorr Signal

    特別處理：
    1. Sequence 跨頁
    2. PyPDF2 將 Mean 移到同頁其他 Sequence 後方
    """

    reader = PdfReader(pdf_path)

    page_texts = []
    sequence_page_map = {}

    # ---------------------------------
    # 先取得每一頁原始文字
    # ---------------------------------
    for page_no, page in enumerate(
        reader.pages,
        start=1
    ):

        page_text = page.extract_text() or ""

        page_texts.append(
            page_text
        )

        # 登記各 Sequence 原本出現在哪一頁
        sequence_matches = re.finditer(
            r"Sequence\s+No\.?\s*:?\s*(\d+)",
            page_text,
            flags=re.IGNORECASE
        )

        for match in sequence_matches:

            sequence_no = int(
                match.group(1)
            )

            sequence_page_map[
                sequence_no
            ] = page_no

    # ---------------------------------
    # 整份 PDF 串起來
    # 保留跨頁 Sequence 的能力
    # ---------------------------------
    full_text = "\n".join(
        page_texts
    )

    # ---------------------------------
    # 解析本次分析元素與實際波長
    #
    # PE900 例如：
    # Analyte: As 193.70
    # ---------------------------------
    analyte = ""
    wavelength = None

    analyte_match = re.search(
        r"Analyte\s*:?\s*"
        r"([A-Za-z][A-Za-z0-9]*)"
        r"\s+"
        r"(\d+(?:\.\d+)?)",
        full_text,
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

    blocks = re.split(
        r"(?=Sequence\s+No\.?\s*:?\s*\d+)",
        full_text,
        flags=re.IGNORECASE
    )

    pending_rows = []

    # 某些 Mean 被 PyPDF2 移到同頁其他 block
    extra_signals_by_page = {}

    for block in blocks:

        sequence_match = re.search(
            r"Sequence\s+No\.?\s*:?\s*(\d+)",
            block,
            flags=re.IGNORECASE
        )

        sample_match = re.search(
            r"Sample\s+ID\s*:?\s*(.*?)\s+Date\s+Collected\s*:",
            block,
            flags=re.IGNORECASE | re.DOTALL
        )

        if (
            not sequence_match
            or not sample_match
        ):
            continue

        sequence_no = int(
            sequence_match.group(1)
        )

        sample_id = (
            sample_match.group(1)
            .strip()
            .splitlines()[0]
            .strip()
        )

        mean_signals = (
            extract_all_mean_blnkcorr_signals(
                block
            )
        )

        signal = None

        if mean_signals:

            # 第一筆一定先視為目前 Sequence 本身
            signal = mean_signals[0]

            # 多出的 Mean 先暫存，
            # 之後補給同頁 signal 遺失的 Sequence
            if len(mean_signals) > 1:

                page_no = (
                    sequence_page_map.get(
                        sequence_no
                    )
                )

                if page_no not in (
                    extra_signals_by_page
                ):

                    extra_signals_by_page[
                        page_no
                    ] = []

                extra_signals_by_page[
                    page_no
                ].extend(
                    mean_signals[1:]
                )

        pending_rows.append(
            {
                "sequence_no":
                    sequence_no,

                "sample_id":
                    sample_id,

                "signal":
                    signal,

                "analyte":
                    analyte,

                "wavelength":
                    wavelength
            }
        )

    # ---------------------------------
    # 修補 PyPDF2 錯置的 Mean
    # ---------------------------------
    for row in pending_rows:

        if row["signal"] is not None:
            continue

        page_no = (
            sequence_page_map.get(
                row["sequence_no"]
            )
        )

        extra_signals = (
            extra_signals_by_page.get(
                page_no,
                []
            )
        )

        if extra_signals:

            row["signal"] = (
                extra_signals.pop(0)
            )

    # ---------------------------------
    # 最終結果
    # ---------------------------------
    results = []

    for row in pending_rows:

        if row["signal"] is None:
            continue

        results.append(
            row
        )

    return results

def extract_all_mean_blnkcorr_signals(
    block
):
    """
    取得 block 內所有 Mean 的
    BlnkCorr Signal。

    可處理：
    Mean: [0.25] 0.0027

    Mean: 0.9100 0.9100 0.0172

    以及：
    %RSD: ...Mean: 0.3945 0.3945 0.0088
    """

    signals = []

    lines = block.splitlines()

    for line in lines:

        matches = list(
            re.finditer(
                r"Mean\s*:",
                line,
                flags=re.IGNORECASE
            )
        )

        if not matches:
            continue

        for index, match in enumerate(
            matches
        ):

            start = match.end()

            if index + 1 < len(matches):

                end = (
                    matches[
                        index + 1
                    ].start()
                )

                mean_text = line[
                    start:end
                ]

            else:

                mean_text = line[
                    start:
                ]

            numbers = re.findall(
                r"[-+]?(?:\d+\.\d+|\d+)",
                mean_text
            )

            if not numbers:
                continue

            try:

                signals.append(
                    float(
                        numbers[-1]
                    )
                )

            except ValueError:
                continue

    return signals