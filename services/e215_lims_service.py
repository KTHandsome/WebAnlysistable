"""Export selected Coliform results from the E215 formal snapshot."""
import re
from exports.lims_export_model import LimsAnalysisRow, LimsExportData
from exports.lims_excel_exporter import build_lims_excel
from exports.w434_lims_mapper import _build_batch_no


def build_coliform_lims(record, state, template_path):
    exam = str(record.exam_no or "").strip()
    data = LimsExportData()
    seen = set()
    sids = state["data"]["samples"]
    lookup = {row["sid"]: row["number"] for row in state["lookup"]["rows"]}
    offset = 0
    for index, batch in enumerate(state["e215_batches"], 1):
        batch_no = _build_batch_no(str(record.analysis_start_date), exam, index)
        for row in batch["rows"][1:]:  # formal snapshot starts each batch with its lab blank
            sample = lookup[sids[offset]].strip()
            offset += 1
            if sample != row["sample_id"] or sample in seen or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", sample):
                raise ValueError("樣品編號不符、格式無效或重複。")
            seen.add(sample)
            selected = [line for line in row["lines"] if line["selected"]]
            if len(selected) != 1:
                raise ValueError("每筆樣品須有一個選定的報告倍數。")
            values = [out["report"] for out in selected[0]["outputs"] if out["analyte"] == "Coliform"]
            if len(values) != 1 or not re.fullmatch(r"[<>]?[0-9]+(?:\.[0-9]+)?(?:E\+[0-9]+)?", values[0]):
                raise ValueError("選定的 Coliform 報告值無效。")
            data.analysis_rows.append(LimsAnalysisRow(sample_id=sample, exam_no=exam,
                result=values[0], batch_no=batch_no))
    if not data.analysis_rows or offset != len(sids):
        raise ValueError("正式紀錄樣品明細不完整。")
    return build_lims_excel(template_path, data,
        analyst_id=record.analyst_employee_id or "", analyst_name=record.analyst_name or "",
        analysis_method=record.method_name or "")
