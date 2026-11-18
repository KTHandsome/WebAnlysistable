"""E215 manual entry metadata, independent of annual control settings."""
import csv
from datetime import date
from pathlib import Path


DATE_FIELDS = ("analysis_start_date", "analysis_end_date", "form_date")


def is_e215(form):
    return str(form.get("method_code") or "").strip().upper() == "E215"


def load_options(root):
    try:
        with (Path(root) / "data" / "Phyon_Method_Settings.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            return [
                {k: (r.get(k) or "").strip() for k in ("CATEGORY_CODE", "EXAMNAME", "EXAMNO", "REPORT_CODE")}
                for r in csv.DictReader(source)
                if is_e215({"method_code": r.get("METHOD_CODE")})
                and (r.get("ACTIVE") or "").strip().upper() == "Y"
                and (r.get("DATA_ENTRY_MODE") or "").strip().upper() == "MANUAL"
                and (r.get("EXAMNO") or "").strip()
                and (r.get("REPORT_CODE") or "").strip() == "BIO_RECORD"
            ]
    except (OSError, UnicodeError, csv.Error):
        return []


def validate_entry(form, options):
    if not is_e215(form):
        return None, "請先選擇 E215 方法。"
    matches = [
        r for r in options
        if r["CATEGORY_CODE"] == form.get("category")
        and r["EXAMNAME"] == form.get("exam_name")
    ]
    if len(matches) != 1:
        return None, "請確認類別與檢驗項目，須對應唯一一筆已啟用的 E215 手動方法。"
    item = matches[0]
    try:
        start, end, _ = (date.fromisoformat(form.get(k) or "") for k in DATE_FIELDS)
    except ValueError:
        return item, "請填妥分析起始日、分析結束日及填表日期。"
    if end < start:
        return item, "分析結束日不可早於起始日。"
    return item, None
