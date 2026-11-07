"""W433 UV TXT import and concentration calculation (Python 3.8+)."""
import math
import re

from parsers.uv_txt_parser import parse_uv_text


def build_w433_result(standard_payload, sample_payload,
                      standard_filename="STANDARD.txt", sample_filename="SAMPLE.txt"):
    standards, _ = parse_uv_text(standard_payload, standard_filename)
    samples, _ = parse_uv_text(sample_payload, sample_filename)
    if any(abs(row["wavelength"] - 664.0) > 1e-6 for row in standards + samples):
        raise ValueError("W433 需要 664.0 nm 的 TXT。")
    points = {}
    for row in standards:
        match = re.fullmatch(r"STD([0-5])", row["sample_id"].upper())
        if not match or row["type"].upper() != "STANDARD":
            raise ValueError("標準檔僅接受 STD0～STD5。")
        index = int(match[1])
        if index in points or row["instrument_conc"] is None:
            raise ValueError("標準點重複或缺少設定濃度：" + row["sample_id"])
        points[index] = row
    if set(points) != set(range(6)):
        raise ValueError("缺少 STD0～STD5 標準點。")
    ordered = [points[i] for i in range(6)]
    x = [r["instrument_conc"] for r in ordered]
    y = [r["absorbance"] for r in ordered]
    if x[0] != 0 or any(b <= a for a, b in zip(x, x[1:])):
        raise ValueError("STD0 濃度應為零，其餘標準濃度須遞增。")
    mx, my = math.fsum(x) / 6, math.fsum(y) / 6
    xx = math.fsum((v - mx)**2 for v in x)
    yy = math.fsum((v - my)**2 for v in y)
    xy = math.fsum((a - mx)*(b - my) for a, b in zip(x, y))
    if xy <= 0 or yy <= 0:
        raise ValueError("檢量線斜率須大於零。")
    slope = xy / xx
    intercept = my - slope * mx
    groups, result = {}, []
    for row in samples:
        label = row["sample_id"].upper()
        if row["type"].upper() != "UNKNOWN":
            raise ValueError("樣品檔含非 Unknown 資料：" + label)
        if label in {"ICV", "BK", "QC", "CCV"}:
            result.append(dict(row, role=label, dilution=1.0,
                               net_absorbance=row["absorbance"], blank=None))
            continue
        match = re.fullmatch(
            r"([A-Z][0-9]{11}|DUP|MSD|MS)(?:\*(\d+(?:\.\d+)?))?\(([AB])\)?", label)
        if not match:
            raise ValueError("無法識別 W433 樣品名稱：" + label)
        name, dilution, side = match.groups()
        dilution = float(dilution or 1)
        if not math.isfinite(dilution) or dilution <= 0:
            raise ValueError("稀釋倍數必須大於零：" + label)
        key = (row["measured_at"][:10], name, dilution)
        pair = groups.setdefault(key, {})
        if side in pair:
            raise ValueError("同日 A/B 量測重複，無法唯一配對：" + label)
        pair[side] = row
    for (_, name, dilution), pair in groups.items():
        if set(pair) != {"A", "B"}:
            raise ValueError("缺少 A 或 B 量測：" + name)
        a, b = pair["A"], pair["B"]
        result.append(dict(a, sample_id=name, raw_sample_id=a["sample_id"],
                           role=name if name in {"DUP", "MS", "MSD"} else "SAMPLE",
                           dilution=dilution, blank=b,
                           net_absorbance=a["absorbance"] - b["absorbance"]))
    for row in result:
        equivalent = (row["net_absorbance"] - intercept) / slope
        row["equivalent_concentration"] = equivalent
        row["sample_concentration"] = equivalent * row["dilution"]
    result.sort(key=lambda row: (row["measured_at"], row["source_line"]))
    return {"standards": ordered, "raw_samples": samples, "rows": result,
            "calibration": {"slope": slope, "intercept": intercept,
                            "r": xy / math.sqrt(xx * yy)}}
