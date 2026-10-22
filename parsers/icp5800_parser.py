import math
import re

import pdfplumber


ROW_PATTERN = re.compile(
    r"^(.+?)\s+"
    r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})\s+"
    r"([A-Z][a-z]?)(\*)?\s+"
    r"\(([\d.]+)\s+nm\)\s*"
    r"(.*?)\s+mg/L\s+"
    r"(\S+)\s+(\S+)\s*$"
)


def parse_number(text):
    text = str(text or "").strip()

    if not text:
        return None

    value = float(text)

    if not math.isfinite(value):
        raise ValueError("數值不是有限數字：" + text)

    return value

def parse_concentration(text):
    text = str(text or "").strip()

    if not text:
        return None, ""

    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:[Ee][+-]?\d+)?)"
        r"(?:\s+(.*))?",
        text
    )

    if not match:
        raise ValueError("無法辨識濃度：" + text)

    return (
        parse_number(match.group(1)),
        match.group(2) or ""
    )

def parse_dilution_label(sample_label):
    label = str(sample_label or "").strip()

    result = {
        "base_label": label,
        "label_dilution_factor": 1.0,
        "dilution_elements": [],
        "label_warning": "",
    }

    if "*" not in label:
        return result

    match = re.fullmatch(
        r"(.+?)\s*\*\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*\(([A-Za-z]+)\)\s*",
        label
    )

    if not match:
        result["label_warning"] = "稀釋標記格式需確認"
        return result

    factor = parse_number(match.group(2))

    element_text = match.group(3)
    elements = re.findall(
        r"[A-Z][a-z]?",
        element_text
    )

    if (
        factor <= 0
        or not elements
        or "".join(elements) != element_text
    ):
        result["label_warning"] = "稀釋倍數或金屬標記需確認"
        return result

    result.update({
        "base_label": match.group(1).strip(),
        "label_dilution_factor": factor,
        "dilution_elements": elements,
    })

    return result

def parse_sample_variant(base_label):
    """
    解析一般樣品與溶解態樣品標記。

    例如：
    G12013026001
    G12013026001(D-Fe)
    G12013026001(D-Mn)

    不修改儀器實際量測元素。
    """
    label = str(base_label or "").strip()

    result = {
        "base_label": label,
        "pdf_sample_tag": "",
        "analyte_variant": "TOTAL_OR_UNSPECIFIED",
        "variant_element": "",
        "variant_warning": "",
    }

    match = re.fullmatch(
        r"([A-Z]\d{11})\s*\(\s*D-(Fe|Mn)\s*\)",
        label,
        re.IGNORECASE
    )

    if match:
        element = match.group(2).capitalize()

        result.update({
            "base_label": match.group(1).upper(),
            "pdf_sample_tag": "D-" + element.upper(),
            "analyte_variant": "DISSOLVED",
            "variant_element": element,
        })

    elif re.search(r"\(\s*D-", label, re.IGNORECASE):
        result["variant_warning"] = (
            "溶解態樣品標記格式需確認"
        )

    return result

def classify_icp_label(base_label):
    label = str(base_label or "").strip()
    upper_label = label.upper()

    if upper_label == "BLANK":
        return "STANDARD"

    if re.fullmatch(r"STANDARD\s+\d+", upper_label):
        return "STANDARD"

    if re.fullmatch(r"RINSEBK(?:\(\d+\))?", upper_label):
        return "RINSE"

    # 先移除品管名稱末尾的濃度提醒，
    # 例如 ICV(0.01)、MS-1(0.005)。
    qc_label = re.sub(
        r"\(\d+(?:\.\d+)?\)$",
        "",
        upper_label
    ).strip()

    for role in (
        "ICBK", "ICV", "CCBK", "CCV",
        "BK", "QC", "DUP", "MSD", "MS"
    ):
        if re.fullmatch(
            re.escape(role) + r"(?:-\d+[A-Z]*|\d+)?",
            qc_label
        ):
            return role

    # 目前依提供檔案的樣品編號格式辨識。
    if re.fullmatch(r"[A-Z]\d{11}", upper_label):
        return "SAMPLE"

    return "UNKNOWN"

def parse_icp5800_pdf(pdf_source):
    rows = []
    errors = []

    with pdfplumber.open(pdf_source) as pdf:
        page_count = len(pdf.pages)

        first_page_text = (
            pdf.pages[0].extract_text() or ""
        ) if page_count else ""

        if not re.search(
            r"ICP-OES\s+5800",
            first_page_text,
            re.IGNORECASE
        ):
            raise ValueError(
                "檔案未辨識為 ICP5800 報表，"
                "請確認選定儀器與 PDF 格式。"
            )

        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            if not text.strip():
                errors.append(
                    f"第 {page_no} 頁沒有可讀取的文字。"
                )
                continue

            for line in text.splitlines():
                if not re.search(r"\bnm\s*\)", line):
                    continue

                match = ROW_PATTERN.match(line)

                if not match:
                    errors.append(
                        f"第 {page_no} 頁無法解析：{line}"
                    )
                    continue

                (
                    label,
                    measured_at,
                    element,
                    marker,
                    wavelength,
                    concentration,
                    intensity,
                    rsd,
                ) = match.groups()

                try:
                    concentration_value, concentration_flag = (
                        parse_concentration(concentration)
                    )

                    row = {
                        "sequence": len(rows) + 1,
                        "source_page": page_no,
                        "sample_label": label.strip(),
                        "measured_at": measured_at,
                        "element": element,
                        "element_marker": marker or "",
                        "wavelength": wavelength,
                        "instrument_concentration_text": concentration.strip(),
                        "signal_text": intensity.strip(),
                        "rsd_text": rsd.strip(),
                        "instrument_concentration": (
                            concentration_value
                        ),
                        "instrument_concentration_flag": (
                            concentration_flag
                        ),
                        "concentration_unit": "mg/L",
                        "signal": parse_number(intensity),
                        "rsd": parse_number(rsd),
                        "source_line": line,
                    }
                except ValueError as exc:
                    errors.append(
                        f"第 {page_no} 頁：{exc}；{line}"
                    )
                    continue

                row.update(
                    parse_dilution_label(
                    row["sample_label"]
                    )
                )

                # 解析溶解態標記，保留原始 sample_label
                row.update(
                    parse_sample_variant(
                    row["base_label"]
                    )
                )

                if row["variant_warning"] and not row["label_warning"]:
                   row["label_warning"] = row["variant_warning"]

                row["role"] = classify_icp_label(
                   row["base_label"]
                )

                row["lims_keepid"] = (
                    row["base_label"]
                    if row["role"] == "SAMPLE"
                    and not row["label_warning"]
                    else ""
                )

                if row["label_warning"]:
                   row["element_applicability"] = "REVIEW"
                   row["element_applicability_note"] = (
                   row["label_warning"]
                )

                elif (
                   row["variant_element"]
                   and row["element"] != row["variant_element"]
                ):
                   row["element_applicability"] = "NOT_TARGET"
                   row["element_applicability_note"] = (
                      "非溶解態標記指定金屬"
                    )

                elif row["analyte_variant"] == "DISSOLVED":
                     row["element_applicability"] = "APPLICABLE"
                     row["element_applicability_note"] = (
                         "溶解態指定金屬"
                    )  

                elif (
                    row["dilution_elements"]
                    and row["element"]
                    not in row["dilution_elements"]
                ):
                    row["element_applicability"] = "NOT_TARGET"
                    row["element_applicability_note"] = (
                        "非本次重測指定金屬"
                    )

                else:
                    row["element_applicability"] = "APPLICABLE"
                    row["element_applicability_note"] = (
                        "指定金屬"
                        if row["dilution_elements"]
                        else "未限定金屬"
                    )

                rows.append(row)

    if errors:
        raise ValueError(
            "PDF 解析未完成：\n"
            + "\n".join(errors[:10])
        )

    if not rows:
        raise ValueError("PDF 沒有可辨識的金屬量測資料。")

    return {
        "parser_type": "ICP5800_PDF",
        "page_count": page_count,
        "rows": rows,
    }