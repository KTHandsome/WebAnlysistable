import csv
import os

from flask import current_app
from services.method_control_service import (
    load_control_and_method_data,
)


def get_method_analysis_mode(method_code):
    method_code = str(
        method_code or ""
    ).strip().upper()

    if not method_code:
        return "SINGLE"

    method_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    if not os.path.exists(method_file):
        raise ValueError("尚未匯入方法設定資料。")

    modes = set()

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(
                row.get("ACTIVE", "") or ""
            ).strip().upper() != "Y":
                continue

            if str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper() != method_code:
                continue

            mode = str(
                row.get("ANALYSIS_MODE", "") or ""
            ).strip().upper() or "SINGLE"

            if mode not in {"SINGLE", "MULTI_ANALYTE"}:
                raise ValueError(
                    method_code + " 的分析模式設定不正確。"
                )

            modes.add(mode)

    if not modes:
        raise ValueError(
            "查無方法 " + method_code + " 的有效設定。"
        )

    if len(modes) > 1:
        raise ValueError(
            method_code + " 的 ANALYSIS_MODE 設定不一致。"
        )

    return modes.pop()


def get_instrument_import_type(form_data):
    method_code = str(
        form_data.get("method_code", "") or ""
    ).strip().upper()

    instrument_id = str(
        form_data.get("instrument_id", "") or ""
    ).strip().upper()

    relation_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Method_Instrument.csv"
    )

    if not os.path.exists(relation_file):
        raise ValueError("尚未匯入方法－儀器關聯資料。")

    matches = []

    with open(
        relation_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if (
                str(row.get("METHOD_CODE", "") or "")
                .strip().upper() == method_code
                and str(row.get("LABPARTID", "") or "")
                .strip().upper() == instrument_id
            ):
                matches.append(row)

    if len(matches) != 1:
        raise ValueError(
            "方法－儀器關聯必須有一筆符合的設定。"
        )

    import_type = str(
        matches[0].get("IMPORT_TYPE", "") or ""
    ).strip().upper()

    if not import_type:
        raise ValueError(
            "此方法與儀器尚未設定 IMPORT_TYPE。"
        )

    return import_type


def load_basic_info_data(form_data):
    method_code = str(
        form_data.get("method_code", "") or ""
    ).strip().upper()

    try:
        analysis_mode = get_method_analysis_mode(
            method_code
        )
    except ValueError as exc:
        return {}, None, str(exc)

    if analysis_mode == "SINGLE":
        return load_control_and_method_data(form_data)

    method_file = os.path.join(
        current_app.root_path,
        "data",
        "Phyon_Method_Settings.csv"
    )

    # 基本資料階段只取方法共用設定，
    common_fields = (
        "DATA_ENTRY_MODE",
    )

    method_rows = []

    with open(
        method_file,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(
                row.get("ACTIVE", "") or ""
            ).strip().upper() != "Y":
                continue

            if str(
                row.get("METHOD_CODE", "") or ""
            ).strip().upper() == method_code:
                method_rows.append(row)

    method_data = {
        "METHOD_CODE": method_code,
        "ANALYSIS_MODE": "MULTI_ANALYTE",
    }

    for field in common_fields:
        values = {
            str(row.get(field, "") or "").strip().upper()
            for row in method_rows
        }

        if len(values) != 1:
            return (
                {},
                None,
                method_code + " 的 " + field + " 設定不一致。"
            )

        method_data[field] = values.pop()

    try:
        method_data["IMPORT_TYPE"] = (
            get_instrument_import_type(form_data)
        )
    except ValueError as exc:
        return {}, None, str(exc)

    return {}, method_data, None
