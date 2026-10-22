"""Map selected ICP channels to the existing two-sheet LIMS import contract."""
import math
from exports.lims_export_model import LimsAnalysisRow, LimsExportData, LimsQcRow
from exports.w434_lims_mapper import _build_batch_no, _build_lims_result
from services.icp_calibration_service import build_calibration_cards
from services.icp_sample_service import build_sample_view
from services.icp_qaqc_service import build_icp_qaqc_view


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(label + "缺少有效數值，尚不可匯出。")
    if not math.isfinite(result):
        raise ValueError(label + "不是有限數值，尚不可匯出。")
    return result


def _one(rows, label):
    if len(rows) != 1:
        raise ValueError(label + "需要一筆明確的採用品管結果；請先確認數據頁採用資料。")
    return rows[0]


def _blank_result(rows):
    blanks = [r for r in rows if r.get("role") == "BK"]
    if not blanks:
        raise ValueError("本批沒有採用的 BK 空白試驗資料。")
    # Do not report <2MDL merely because a BK row exists.
    rendered = []
    for row in blanks:
        cfg = row["calculation"]
        value = _number(row.get("sample_concentration"), "BK 濃度") * _number(cfg.get("concentrationFactor"), "濃度換算係數")
        mdl = _number(cfg.get("mdl"), "MDL")
        multiplier = _number(cfg.get("blankMdlMultiplier"), "空白 MDL 倍率")
        if mdl <= 0 or multiplier <= 0:
            raise ValueError("MDL 或空白判定倍率必須大於零。")
        text = "<" + format(multiplier, ".10g") + "MDL" if value < mdl * multiplier else format(value, ".6f")
        rendered.append((value, text))
    return max(rendered, key=lambda item: item[0])[1]


def build_icp_lims_export_data(work, channels, selected_keys, configurations, lookup_error=None):
    allowed = {c["key"] for c in channels}
    if not selected_keys or len(set(selected_keys)) != len(selected_keys) or any(key not in allowed for key in selected_keys):
        raise ValueError("請選擇目前工作中的金屬／波長，且不可重複。")
    if lookup_error:
        raise ValueError("LIMS 委測配對目前無法確認，請稍後再匯出。")
    export = LimsExportData()
    form = work["form_data"]
    date = str(form.get("analysis_start_date") or "").strip()
    used_batches, used_results, methods = {}, set(), set()
    for channel in channels:
        if channel["key"] not in selected_keys:
            continue
        category = configurations[channel["key"]]["category"]
        cards = build_calibration_cards(channel, category)
        samples = build_sample_view(work, channel, category, cards, lookup_error)
        if not samples.get("ready") or not cards or any(c.get("error") or not c.get("result") for c in cards):
            raise ValueError(channel["label"] + "：請先完成批次、檢量線與樣品關聯確認。")
        if any(b.get("warnings") for b in samples["batches"]):
            raise ValueError(channel["label"] + "：請先處理數據頁提示並重新暫存。")
        quality = build_icp_qaqc_view(category, samples, lookup_error)
        if not quality.get("ready"):
            raise ValueError(channel["label"] + "：QA/QC 尚未完成判定，請先確認數據頁。")
        groups = {g["selection_key"]: g for g in channel["sample_groups"]}
        for batch in samples["batches"]:
            setting = next(b for b in category["batches"] if b["id"] == batch["id"])["setting"]
            control = setting["control"]
            exam = str(batch["exam_no"])
            batch_key = (str(batch["number"]), exam)
            if batch_key in used_batches:
                raise ValueError("BATCH {}／{}：{} 與 {} 使用相同檢測代碼，請只選擇一個波長。".format(batch["number"], exam, used_batches[batch_key], channel["label"]))
            used_batches[batch_key] = channel["label"]
            batch_no = _build_batch_no(date, exam, batch["number"])
            active = [row for row in batch["rows"] if not row.get("is_excluded")]
            cal = next(c["result"] for c in cards if str(c["batch_number"]) == str(batch["number"]))
            qc = next(q for q in quality["batches"] if str(q["number"]) == str(batch["number"]))
            check = _one([q for q in qc["a"] if q["role"] == "QC"], "QC")
            closing = _one([q for q in qc["a"] if q["role"] == "CCV" and q.get("check_position") == "結束查核"], "結束 CCV")
            precision = _one(qc["b"], "重複分析")
            spike = _one([q for q in qc["c"] if q["role"] == "MS"], "MS 添加分析")
            highest = max(cal["points"], key=lambda point: _number(point["concentration_text"], "檢量線濃度"))
            methods.add(str(control.get("EM_NO") or form.get("method_code") or "").strip())
            export.qc_rows.append(LimsQcRow(
                analysis_date=date, exam_no=exam, instrument_id=str(form.get("instrument_id") or "").strip(),
                max_signal=_number(highest["signal_text"], "最高標準點測定值"),
                duplicate_result=_number(precision.get("rpd"), "重複分析 RPD"),
                qc_result=_number(check.get("metric"), "QC 回收率"),
                spike_result=_number(spike.get("metric"), "MS 回收率"),
                calibration_check=_number(closing.get("metric"), "結束 CCV 相對誤差"),
                blank_result=_blank_result(active), remark=channel["label"] + "；" + qc["status"],
                batch_no=batch_no, correlation_coefficient=_number(cal.get("r"), "相關係數")))
            for row in active:
                if row.get("role") != "SAMPLE":
                    continue
                group = groups.get(row["selection_key"]) or {}
                commissioned = any(item.get("examno") == exam and item.get("user_decision") == "ACCEPT"
                                   for item in group.get("lims_items", []))
                # Work-only adoption supports QC parents; it does not create a LIMS commission.
                if not commissioned:
                    continue
                key = (str(row["sample_id"]), exam)
                if key in used_results:
                    raise ValueError("樣品 {}／{} 有多筆採用結果，請先確認量測選擇。".format(*key))
                used_results.add(key)
                cfg = row["calculation"]
                value = _number(row.get("sample_concentration"), "樣品濃度") * _number(cfg.get("concentrationFactor"), "濃度換算係數")
                mdl = control.get("DETECT_LIMITED")
                _number(mdl, "MDL")
                qdl = cfg.get("qdl")
                _number(qdl, "QDL")
                result, remark = _build_lims_result(value, mdl, qdl)
                export.analysis_rows.append(LimsAnalysisRow(sample_id=key[0], exam_no=exam,
                    result=result, actual_item="", batch_no=batch_no, remark=remark))
    if not export.qc_rows or not export.analysis_rows:
        raise ValueError("所選項目沒有完整品管資料或已確認 LIMS 委測且採用的一般樣品，尚不可匯出。")
    return export, "、".join(sorted(methods))
