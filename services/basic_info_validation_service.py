"""Shared validation when leaving Basic Info for an analysis page."""
import re
from datetime import datetime

REQUIRED_FIELDS = (
    ("ctrl_year", "管制年度"),
    ("method_code", "分析方法"),
    ("instrument_id", "儀器"),
    ("form_date", "填表日期"),
    ("analysis_start_date", "分析起始日期"),
    ("analysis_end_date", "分析結束日期"),
)
DATE_FIELDS = ("form_date", "analysis_start_date", "analysis_end_date")


def parse_basic_info_date(value, label):
    text = str(value or "").strip()
    if not text:
        raise ValueError("尚未填寫「{}」。".format(label))
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
            raise ValueError()
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("「{}」格式不正確，請輸入有效日期（YYYY-MM-DD）。".format(label)) from None


def validate_basic_info_for_analysis(form, multi_analyte=False):
    errors = []
    fields = list(REQUIRED_FIELDS)
    if not multi_analyte:
        fields.insert(1, ("category", "類別"))
    parsed = {}
    for key, label in fields:
        value = str(form.get(key) or "").strip()
        if key in DATE_FIELDS:
            try:
                parsed[key] = parse_basic_info_date(value, label)
            except ValueError as exc:
                errors.append({"field": key, "message": str(exc)})
        elif not value:
            errors.append({"field": key, "message": "尚未填寫「{}」。".format(label)})
    if ("analysis_start_date" in parsed and "analysis_end_date" in parsed
            and parsed["analysis_end_date"] < parsed["analysis_start_date"]):
        errors.append({"field": "analysis_end_date", "message": "分析結束日期不得早於分析起始日期。"})
    return errors
