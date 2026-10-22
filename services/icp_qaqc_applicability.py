"""Match nominal QA/QC label concentrations to each batch method setting."""
import re
from decimal import Decimal, InvalidOperation

SPIKE_FIELDS = {
    "ICV": "ICV_SPIKE_CONC", "CCV": "CCV_SPIKE_CONC", "QC": "QC_SPIKE_CONC",
    "MS": "MS_SPIKE_CONC", "MSD": "MS_SPIKE_CONC",
}
DEFAULTS = {role: Decimal("0.05" if role in {"MS", "MSD"} else "0.1") for role in SPIKE_FIELDS}
LABEL = re.compile(
    r"^(ICV|CCV|QC|MSD|MS)(?:-?\d+[A-Z]*)?\s*"
    r"(?:\(\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*\))?$",
    re.IGNORECASE,
)


def positive_decimal(value):
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() and result > 0 else None


def spike_selection(row, method):
    role = str(row.get("role") or "").strip().upper()
    if role not in SPIKE_FIELDS:
        return None
    label = str(row.get("base_label") or row.get("sample_label") or row.get("sample_id") or "").strip()
    match = LABEL.fullmatch(label)
    result = {"matches": None, "reference": None, "target": None, "error": ""}
    if match is None or match.group(1).upper() != role:
        result["error"] = "品管標籤添加濃度無法確認：" + label
        return result
    reference = positive_decimal(match.group(2)) if match.group(2) is not None else DEFAULTS[role]
    target = positive_decimal(method.get(SPIKE_FIELDS[role]))
    if reference is None:
        result["error"] = "品管標籤添加濃度無效：" + label
        return result
    result["reference"] = format(reference, "f")
    if target is None:
        result["error"] = "方法添加濃度未設定或無效：" + SPIKE_FIELDS[role]
        return result
    result.update(target=format(target, "f"), matches=reference == target)
    return result
