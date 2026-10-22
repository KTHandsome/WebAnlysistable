"""Read-only PDF assembly from the same ICP view services as the data page."""
from copy import deepcopy
from services.icp_batch_category_service import build_category_view
from services.icp_calibration_service import build_calibration_cards
from services.icp_sample_service import build_sample_view
from services.icp_qaqc_service import build_icp_qaqc_view
from services.icp_performance_service import work_token
from services.report_setting_service import load_report_setting


def pdf_configuration(work, form, channels):
    configs = {}
    for channel in channels:
        view = build_category_view(work, form, channel)
        reports = {}
        for batch in view["batches"]:
            if batch.get("ready") and batch.get("setting"):
                report, error = load_report_setting(batch["setting"]["method"])
                reports[batch["id"]] = {"report": report, "error": error}
        configs[channel["key"]] = {"category": view, "reports": reports}
    return configs, work_token({"channels": channels, "configurations": configs})


def assemble_pdf_channels(work, channels, selected_keys, configurations, lookup_error):
    if (not selected_keys or len(selected_keys) != len(set(selected_keys))
            or any(key not in {c["key"] for c in channels} for key in selected_keys)):
        raise ValueError("請選擇目前工作中的金屬／波長，且不可重複。")
    if lookup_error:
        raise ValueError("LIMS 配對目前無法確認，請稍後再匯出。")
    bundles = []
    # Follow the left navigation order, never the order supplied by the browser.
    for channel in channels:
        if channel["key"] not in selected_keys:
            continue
        config = configurations[channel["key"]]
        category = config["category"]
        cards = build_calibration_cards(channel, category)
        samples = build_sample_view(work, channel, category, cards, lookup_error)
        if not samples.get("ready") or any(c.get("error") or not c.get("result") for c in cards):
            raise ValueError(channel["label"] + "：請先完成批次設定、檢量線及樣品關聯確認。")
        if any(b.get("warnings") for b in samples["batches"]):
            raise ValueError(channel["label"] + "：量測或設定已有提示，請確認並重新暫存後再匯出。")
        qc = build_icp_qaqc_view(category, samples, lookup_error)
        batches = []
        for batch in samples["batches"]:
            setting = next(b for b in category["batches"] if b["id"] == batch["id"])
            report = config["reports"].get(batch["id"]) or {}
            if report.get("error") or not report.get("report"):
                raise ValueError(channel["label"] + "：" + str(report.get("error") or "缺少檢驗紀錄表設定。"))
            calibration = next(c["result"] for c in cards if str(c["batch_number"]) == str(batch["number"]))
            quality = next(q for q in qc["batches"] if str(q["number"]) == str(batch["number"]))
            rows = [deepcopy(row) for row in batch["rows"] if not row.get("is_excluded")]
            if not rows:
                continue
            batches.append({"number": batch["number"], "category": batch["category"],
                            "exam_no": batch["exam_no"], "setting": setting["setting"],
                            "report": report["report"], "calibration": calibration,
                            "qaqc": quality, "rows": rows})
        if not batches:
            raise ValueError(channel["label"] + "：目前沒有可匯出的採用資料。")
        bundles.append({"key": channel["key"], "label": channel["label"],
                        "element": channel["element"], "wavelength": channel["wavelength"], "batches": batches})
    return bundles
