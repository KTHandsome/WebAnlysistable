"""UV CSV-formatted TXT import and W430 preview, Python 3.8 compatible."""
import csv
import io
import math
import re
from collections import defaultdict
from datetime import datetime


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_ROWS = 20000
HEADER = ["Sample ID", "Type", "Date", "Time", "Conc"]
ROLE_NAMES = {
    "STANDARD": "檢量線", "PFM": "性能查核", "SAMPLE": "樣品",
    "SAMPLE_BLANK": "樣品 B 空白", "BKA": "A 液空白",
    "BKB": "B 液空白", "ICV": "ICV", "CCV": "CCV", "QC": "QC",
    "DUP": "重複", "MS": "添加", "MSD": "添加重複",
    "CELL_CHECK": "石英槽比對", "MAX_ABS": "最大吸光值",
    "INSTRUMENT_BLANK": "儀器 BLANK", "UNKNOWN": "待辨識",
}


def _number(value, label, optional=False):
    if not value.strip() and optional:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + "不是有效數值。")
    if not math.isfinite(result):
        raise ValueError(label + "必須為有限數值。")
    return result


def parse_uv_text(payload, filename):
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise ValueError(filename + "：檔案為空或超過 5 MB。")
    text = None
    for encoding in ("utf-8-sig", "cp950"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or "\x00" in text:
        raise ValueError(filename + "：請提供 UTF-8 或 CP950 的 UV TXT。")
    rows, header, wave = [], None, None
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        for fields in reader:
            line = reader.line_num
            fields = [value.strip().lstrip("\ufeff") for value in fields]
            if not fields or not any(fields):
                continue
            if fields[0] == "Sample ID":
                if len(fields) != 6 or fields[:5] != HEADER:
                    raise ValueError("第 {} 行欄位不符合 UV 格式。".format(line))
                match = re.fullmatch(r"WL(\d+(?:\.\d+)?)", fields[5], re.I)
                if not match:
                    raise ValueError("第 {} 行缺少 WL 波長。".format(line))
                wave = _number(match.group(1), "波長")
                header = fields
                continue
            if header is None or len(fields) != 6:
                raise ValueError("第 {} 行缺少標題或欄位數不正確。".format(line))
            if not fields[0]:
                raise ValueError("第 {} 行缺少 Sample ID。".format(line))
            try:
                measured = datetime.strptime(fields[2] + " " + fields[3], "%Y/%m/%d %H:%M:%S")
            except ValueError:
                raise ValueError("第 {} 行日期時間格式不正確。".format(line))
            rows.append({
                "source_file": filename, "source_line": line,
                "sample_id": fields[0], "type": fields[1],
                "measured_at": measured.strftime("%Y-%m-%d %H:%M:%S"),
                "instrument_conc": _number(fields[4], "Conc", optional=True),
                "instrument_conc_text": fields[4],
                "absorbance": _number(fields[5], "吸光度"),
                "absorbance_text": fields[5], "wavelength": wave,
            })
            if len(rows) > MAX_ROWS:
                raise ValueError("資料列超過上限。")
    except (csv.Error, ValueError) as exc:
        raise ValueError(filename + "：" + str(exc))
    if not rows:
        raise ValueError(filename + "：沒有量測資料。")
    return rows, encoding


def _identify(row):
    label = row["sample_id"].upper()
    row.update(role="UNKNOWN", batch="", dilution=1.0, base_id="",
               buffer="", blank_id="", parent_id="", issues=[])
    if label == "PFM":
        row["role"] = "PFM"
    elif re.fullmatch(r"STD\d+", label) or row["type"].upper() == "STANDARD":
        row["role"] = "STANDARD"
    elif label in ("石英槽比對", "最大吸光值", "BLANK"):
        row["role"] = {"石英槽比對": "CELL_CHECK", "最大吸光值": "MAX_ABS", "BLANK": "INSTRUMENT_BLANK"}[label]
    else:
        sample = re.fullmatch(r"([A-Z]\d{11})(?:\*(\d+(?:\.\d+)?))?(B)?", label)
        qc = re.fullmatch(r"(BKA|BKB|ICV|CCV|QC|DUP|MSD|MS)(?:[_-](\d+))?(?:\*(\d+(?:\.\d+)?))?", label)
        if sample:
            row.update(role="SAMPLE_BLANK" if sample.group(3) else "SAMPLE", base_id=sample.group(1))
            row["dilution"] = float(sample.group(2) or 1)
        elif qc:
            row.update(role=qc.group(1), batch=qc.group(2) or "", dilution=float(qc.group(3) or 1))
        else:
            row["issues"].append("名稱待確認；未列為一般樣品。")
    if row["dilution"] <= 0 or not math.isfinite(row["dilution"]):
        raise ValueError(row["sample_id"] + "：稀釋倍數必須大於 0。")
    row["role_label"] = ROLE_NAMES[row["role"]]


def build_w430_preview(files):
    """Combine complete files, preserving every raw row and warning on ambiguity."""
    if not files or len(files) > 20:
        raise ValueError("請選擇 1～20 個 TXT 檔案。")
    if sum(len(payload) for _, payload in files) > MAX_TOTAL_BYTES:
        raise ValueError("匯入檔案合計不可超過 20 MB。")
    rows, sources = [], []
    for filename, payload in files:
        if not filename.lower().endswith(".txt"):
            raise ValueError("僅支援 TXT 檔案。")
        parsed, encoding = parse_uv_text(payload, filename)
        rows.extend(parsed)
        sources.append({"name": filename, "encoding": encoding, "count": len(parsed)})
    if len(rows) > MAX_ROWS:
        raise ValueError("資料列合計超過上限。")
    if any(abs(row["wavelength"] - 420.0) > 0.00001 for row in rows):
        raise ValueError("W430 預期 420.0 nm；檔案包含其他波長，請確認是否選錯檔案。")
    rows.sort(key=lambda row: (row["measured_at"], row["source_file"], row["source_line"]))
    warnings, seen = [], set()
    current_batch, current_day, parent = "1", None, None
    for index, row in enumerate(rows, 1):
        _identify(row)
        row["row_id"] = index
        signature = tuple(row[k] for k in ("sample_id", "type", "measured_at", "instrument_conc_text", "absorbance_text", "wavelength"))
        if signature in seen:
            row["issues"].append("疑似重複量測，已保留，請勿重複採用。")
        seen.add(signature)
        if row["role"] in ("STANDARD", "PFM", "CELL_CHECK", "MAX_ABS", "INSTRUMENT_BLANK"):
            continue
        day = row["measured_at"][:10]
        if current_day != day:
            current_day, current_batch, parent = day, "1", None
        if row["batch"] and row["batch"] != current_batch:
            current_batch, parent = row["batch"], None
        row["batch"] = current_batch
        if row["role"] == "SAMPLE":
            parent = row
        elif row["role"] in ("DUP", "MS", "MSD"):
            if parent is None:
                row["issues"].append("同批次尚無可配對原樣品。")
            else:
                row["parent_id"] = parent["sample_id"]
                row["parent_row_id"] = parent["row_id"]
                if "*" not in row["sample_id"]:
                    row["dilution"] = parent["dilution"]
                elif row["dilution"] != parent["dilution"]:
                    row["issues"].append("稀釋倍數與原樣品不同，需確認空白適用性。")
    blanks = defaultdict(list)
    for row in rows:
        if row["role"] == "SAMPLE_BLANK":
            key = (row["measured_at"][:10], row["batch"], row["base_id"], row["dilution"])
            blanks[key].append(row)
    samples = {row["row_id"]: row for row in rows if row["role"] == "SAMPLE"}
    used_blanks = set()
    for row in rows:
        if row["role"] != "SAMPLE":
            continue
        key = (row["measured_at"][:10], row["batch"], row["base_id"], row["dilution"])
        candidates = blanks.get(key, [])
        if len(candidates) == 1:
            row.update(buffer="B", blank_id=candidates[0]["sample_id"])
            used_blanks.add(candidates[0]["row_id"])
        elif len(candidates) > 1:
            row["issues"].append("存在多筆同名空白，暫不指定緩衝液。")
        else:
            row["buffer"] = "A"
            if any(k[:3] == key[:3] for k in blanks):
                row["buffer"] = ""
                row["issues"].append("有同樣品但不同稀釋倍數的空白，需人工確認。")
    for row in rows:
        if row["role"] in ("DUP", "MS", "MSD") and row.get("parent_row_id"):
            original = samples[row["parent_row_id"]]
            row.update(buffer=original["buffer"], blank_id=original["blank_id"])
        if row["role"] == "SAMPLE_BLANK" and row["row_id"] not in used_blanks:
            row["issues"].append("尚無唯一配對樣品。")
        if row["issues"]:
            warnings.append(row["sample_id"] + "：" + "；".join(row["issues"]))
    standards = [r for r in rows if r["role"] == "STANDARD"]
    if not standards:
        warnings.append("尚未匯入檢量線；本次僅預覽，請重新選取所需檔案一起匯入。")
    if len({r["sample_id"].upper() for r in standards}) != len(standards):
        warnings.append("有重複標準點或多組檢量線，未自動合併或挑選。")
    if len({r["measured_at"][:10] for r in rows}) > 1:
        warnings.append("檔案包含不同測定日期，請確認檢量線與樣品是否適用；未計算結果。")
    return {"rows": rows, "sources": sources, "warnings": warnings,
            "standards": standards, "pfm_rows": [r for r in rows if r["role"] == "PFM"],
            "sample_count": len(samples), "blank_count": sum(r["role"] == "SAMPLE_BLANK" for r in rows)}
