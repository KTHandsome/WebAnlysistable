"""Read-only ICP calibration verified against each confirmed batch setting."""
import re
from decimal import Decimal, InvalidOperation, localcontext


class CalibrationError(ValueError):
    pass


def _number(value, label):
    value = str(value if value is not None else "").strip()
    if not value or len(value) > 80:
        raise CalibrationError(label + "不是有效數值。")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise CalibrationError(label + "不是有效數值。")
    if not result.is_finite() or (result and abs(result.adjusted()) > 50):
        raise CalibrationError(label + "不是有限且合理的數值。")
    return result


def _original_values(row):
    # Older imported work still contains the unmodified PDF source line.
    match = re.search(r"\)\s*(.*?)\s+mg/L\s+(\S+)\s+(\S+)\s*$", str(row.get("source_line") or ""))
    values = []
    for name, index in (("instrument_concentration_text", 1), ("signal_text", 2), ("rsd_text", 3)):
        if name in row:
            values.append(str(row[name] or "").strip())
        elif match:
            values.append(match.group(index).strip())
        else:
            raise CalibrationError("缺少標準點原始文字，請重新匯入 PDF，以確認濃度及位數。")
    return values


def _places(method, field, default):
    text = str(method.get(field) or "").strip()
    if not text:
        return default
    try:
        result = int(text)
    except ValueError:
        raise CalibrationError(field + " 格式不正確。")
    if result < 0 or result > 12:
        raise CalibrationError(field + " 必須介於 0～12。")
    return result


def calculate_channel_calibration(standards, method):
    if str(method.get("CALIBRATION_UNIT") or "").strip().lower() != "mg/l":
        raise CalibrationError("目前 ICP 檢量線只接受 mg/L 方法設定。")
    expected = [_number(v, "設定濃度") for v in str(method.get("CALIBRATION_VALUES") or "").split("|")]
    try:
        count = int(str(method.get("CALIBRATION_COUNT") or ""))
    except ValueError:
        raise CalibrationError("方法設定的標準點數不正確。")
    if (count != len(expected) or count < 2 or any(x < 0 for x in expected)
            or any(b <= a for a, b in zip(expected, expected[1:]))):
        raise CalibrationError("方法設定的濃度序列或標準點數不一致。")
    rows, excluded = [], []
    for source in standards:
        concentration, signal, rsd = _original_values(source)
        label = str(source.get("sample_label") or "").strip()
        if not concentration:
            excluded.append(label)
            continue
        x = _number(concentration, label + " 濃度")
        if label.upper() == "BLANK" and x != 0:
            raise CalibrationError("Blank 必須對應零濃度標準點。")
        y = _number(signal, label + " 平均測定值")
        spread = _number(rsd, label + " RSD")
        if x < 0 or spread < 0:
            raise CalibrationError(label + " 的濃度或 RSD 不可小於零。")
        rows.append({"sample_label": label, "concentration_text": concentration,
                     "signal_text": signal, "rsd_text": rsd, "x": x, "y": y})
    if len([row for row in rows if row["sample_label"].upper() == "BLANK"]) != 1:
        raise CalibrationError("必須有且只有一個有效的 Blank 零濃度標準點。")
    actual = [row["x"] for row in rows]
    if len(actual) != len(set(actual)):
        raise CalibrationError("PDF 有重複濃度或多組標準點，尚無法確認應採用的檢量線。")
    missing = [format(x, "f") for x in expected if x not in actual]
    extra = [format(x, "f") for x in actual if x not in expected]
    if missing or extra or len(actual) != count:
        messages = []
        if missing:
            messages.append("PDF 缺少設定濃度：" + "、".join(missing) + " mg/L")
        if extra:
            messages.append("PDF 額外採用濃度：" + "、".join(extra) + " mg/L")
        if len(actual) != count:
            messages.append("設定 " + str(count) + " 點，PDF 有濃度值的標準點為 " + str(len(actual)) + " 點")
        raise CalibrationError("；".join(messages) + "。請確認方法設定與原始資料，不自動補值。")
    by_x = {row["x"]: row for row in rows}
    points = [by_x[x] for x in expected]
    with localcontext() as context:
        context.prec = 200
        n = Decimal(len(points))
        mean_x = sum(row["x"] for row in points) / n
        mean_y = sum(row["y"] for row in points) / n
        xx = sum((row["x"] - mean_x) ** 2 for row in points)
        yy = sum((row["y"] - mean_y) ** 2 for row in points)
        xy = sum((row["x"] - mean_x) * (row["y"] - mean_y) for row in points)
        if xx == 0 or yy == 0 or xy == 0:
            raise CalibrationError("標準點無法建立有效線性回歸，請確認濃度與測定值。")
        slope = xy / xx
        intercept = mean_y - slope * mean_x
        correlation = xy / (xx * yy).sqrt()
        correlation = min(Decimal(1), max(Decimal(-1), correlation))
        digits = _places(method, "UI_CALIBRATION_BACKCALC_DECIMALS", 4)
        for row in points:
            backcalc = (row["y"] - intercept) / slope
            row["backcalc_text"] = format(backcalc, "." + str(digits) + "f")
            row["backcalc"] = float(backcalc)
            del row["x"], row["y"]
        return {"points": points, "excluded_labels": excluded,
                "slope": float(slope), "intercept": float(intercept), "r": float(correlation),
                "equation": "y = " + format(slope, ".8g") + "x "
                            + ("+ " if intercept >= 0 else "- ") + format(abs(intercept), ".8g"),
                "r_text": format(correlation, ".4f"),
                "point_count": len(points)}


def build_calibration_cards(channel, category_view):
    if not channel or not category_view:
        return []
    cards = []
    # Equal settings share the same read-only computation, but every batch is labelled.
    for batch in category_view["batches"]:
        card = {"batch_number": batch["number"], "category": batch["category"],
                "exam_no": batch["exam_no"], "result": None, "error": None}
        if not batch["ready"]:
            card["error"] = "請先確認並儲存本批次的類別與檢測設定。"
        else:
            try:
                card["result"] = calculate_channel_calibration(channel["standards"], batch["setting"]["method"])
            except CalibrationError as exc:
                card["error"] = str(exc)
        cards.append(card)
    return cards
