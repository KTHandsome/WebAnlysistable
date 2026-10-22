"""ICP record PDF: classic A4 header, calibration, sample table and QA/QC.

Consumes calculated views only. No regression or QA/QC recalculation here.
"""
import math
import os
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                               Table, TableStyle, Spacer, PageBreak, NextPageTemplate)


def _font():
    name = "PhyonICPJhengHei"
    if name not in pdfmetrics.getRegisteredFontNames():
        path = os.environ.get("PHYON_PDF_FONT") or r"C:\Windows\Fonts\msjh.ttc"
        if not os.path.isfile(path):
            raise ValueError("找不到 PDF 中文字型，請確認 Windows 微軟正黑體字型。")
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
    return name


def number(value, places=6):
    if value is None or str(value).strip() == "":
        return "—"
    try:
        numeric = float(value)
        return format(numeric, "." + str(places) + "f") if math.isfinite(numeric) else "—"
    except (TypeError, ValueError, OverflowError):
        return "—"


def compact(value):
    if value is None or str(value).strip() == "":
        return "—"
    try:
        numeric = float(value)
        return format(numeric, ".10g") if math.isfinite(numeric) else "—"
    except (TypeError, ValueError, OverflowError):
        return str(value)


def interpretation(row):
    """Same comparisons as AnalysisInterpretation in the existing sample page."""
    cfg = row.get("calculation") or {}
    def finite(value):
        try:
            return float(value) if value is not None and math.isfinite(float(value)) else None
        except (TypeError, ValueError, OverflowError):
            return None
    concentration = finite(row.get("sample_concentration"))
    factor, mdl = finite(cfg.get("concentrationFactor")), finite(cfg.get("mdl"))
    if mdl is None:
        return "未設定 MDL"
    if concentration is None or factor is None:
        return ""
    concentration *= factor
    role = row.get("role")
    if role in {"ICBK", "BK", "CCBK"}:
        multiplier = finite(cfg.get("blankMdlMultiplier"))
        return "<" + compact(multiplier) + "MDL" if multiplier is not None and concentration < mdl * multiplier else ""
    if role in {"SAMPLE", "DUP"}:
        if concentration < mdl:
            return "ND<" + compact(mdl)
        qdl = finite(cfg.get("qdl"))
        if qdl is not None and concentration < qdl:
            return "<QDL=" + compact(qdl)
    return ""


def sample_sheets(rows):
    """Ten normal samples; QC do not count. Keep linked QC with their original.

    Independent batch QC are repeated on every sheet and labelled as shared.
    """
    normals = [r for r in rows if r.get("role") == "SAMPLE"]
    chunks = [normals[i:i + 10] for i in range(0, len(normals), 10)] or [[]]
    for chunk in chunks:
        ids = {r["row_id"] for r in chunk}
        sheet = [r for r in rows if (r.get("role") == "SAMPLE" and r["row_id"] in ids)
                 or (r.get("role") != "SAMPLE" and (not r.get("parent_row_id") or r["parent_row_id"] in ids))]
        yield sheet


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        pages = list(self._pages)
        for state in pages:
            self.__dict__.update(state)
            self.setFillColor(colors.black)
            self.setFont(self._icp_font, 7)
            self.drawCentredString(A4[0] / 2, 17, "第 {} 頁 / 共 {} 頁".format(self._pageNumber, len(pages)))
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def build_icp_pdf(form, bundles, saved_pfm, pfm_current):
    font = _font()
    width, height = A4
    usable = width - 80
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40,
                          topMargin=145, bottomMargin=55, title="ICP 檢驗紀錄", author="Phyon")
    body = ParagraphStyle("icp-body", fontName=font, fontSize=7, leading=8.5, wordWrap="CJK")
    heading = ParagraphStyle("icp-heading", parent=body, fontSize=8.5, leading=12, spaceBefore=7, spaceAfter=4, keepWithNext=True)
    def paragraph(text, style=body):
        return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), style)
    def table(headers, rows, ratios):
        values = [[paragraph(v) for v in headers]] + [[paragraph(v) for v in row] for row in rows]
        t = Table(values, colWidths=[usable * r / sum(ratios) for r in ratios], repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .35, colors.black),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        return t
    def page_header(channel, batch, sheet_no, sheet_count):
        report, setting = batch["report"], batch["setting"]
        method, control = setting["method"], setting["control"]
        def draw(c, document):
            c._icp_font = font
            c.saveState()
            c.setFillColor(colors.black)
            c.setStrokeColor(colors.black)
            c.setFont(font, 8)
            c.drawString(40, height - 30, str(report.get("COMPANY_NAME") or ""))
            c.drawRightString(width - 40, height - 30, "{} 版次：{}".format(report.get("DOC_NO") or "", report.get("REVISION") or ""))
            c.drawRightString(width - 40, height - 43, "發行日期：" + str(report.get("ISSUE_DATE") or ""))
            c.setFont(font, 12)
            c.drawCentredString(width / 2, height - 57, str(report.get("FORM_TITLE") or "檢驗紀錄表"))
            c.setFont(font, 8)
            c.drawCentredString(width / 2, height - 71, "{} / {} / BATCH {} / 第 {} 組（共 {} 組）".format(channel["label"], batch["exam_no"], batch["number"], sheet_no, sheet_count))
            c.drawString(40, height - 86, "儀器：{} {}".format(form.get("instrument_id") or "", form.get("instrument_model") or ""))
            c.drawRightString(width - 40, height - 86, "填表日期：" + str(form.get("form_date") or ""))
            c.drawString(40, height - 99, "檢驗方法：" + str(control.get("EM_NO") or method.get("METHOD_CODE") or form.get("method_code") or ""))
            c.drawRightString(width - 40, height - 99, "分析日期：{} ～ {}".format(form.get("analysis_start_date") or "", form.get("analysis_end_date") or ""))
            c.drawString(40, height - 112, "類別：{}　使用波長：{} nm".format(batch["category"], channel["wavelength"]))
            c.line(40, height - 120, width - 40, height - 120)
            c.drawString(40, 38, "審核：")
            c.drawString(40 + usable / 3, 38, "驗算：")
            c.drawString(40 + usable * 2 / 3, 38, "分析：")
            c.restoreState()
        return draw
    story, templates = [], []
    for channel in bundles:
        for batch in channel["batches"]:
            sheets = list(sample_sheets(batch["rows"]))
            for index, rows in enumerate(sheets, 1):
                name = "icp-page-" + str(len(templates))
                frame = Frame(40, 55, usable, height - 190, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
                templates.append(PageTemplate(id=name, frames=[frame], onPage=page_header(channel, batch, index, len(sheets))))
                if story:
                    story.extend([NextPageTemplate(name), PageBreak()])
                qc = batch["qaqc"]
                digits = qc.get("digits", 6)
                unit = str(qc.get("unit") or "mg/L")
                calibration = batch["calibration"]
                if saved_pfm:
                    control = saved_pfm.get("control") or {}
                    pfm = "PFM 日期：{}　{}：{}　{}".format(saved_pfm.get("analysis_date") or form.get("analysis_start_date") or "", control.get("monitor_item") or "", saved_pfm.get("ratio_display") or "", "合格" if saved_pfm.get("result") == "PASS" else "不合格")
                    pfm += "　管制：{} ～ {}".format(compact(control.get("lower_limit")), compact(control.get("upper_limit")))
                    if not pfm_current:
                        pfm += "（設定已變更或尚未確認）"
                    story.append(paragraph(pfm))
                    story.append(paragraph("PFM 感應值：分子 {} {} / 分母 {} {}".format(
                        control.get("numerator_item") or "—", compact(saved_pfm.get("numerator_signal")),
                        control.get("denominator_item") or "—", compact(saved_pfm.get("denominator_signal")))))
                else:
                    story.append(paragraph("PFM：尚未輸入"))
                story.append(paragraph("一、檢量線", heading))
                story.append(paragraph(calibration["equation"] + "　r = " + calibration["r_text"]))
                story.append(Spacer(1, 3))
                story.append(table(["樣品／標準名稱", "檢量線濃度 (mg/L)", "平均測定值", "RSD(n=3)", "回歸濃度 (mg/L)"],
                                   [[p["sample_label"], p["concentration_text"], p["signal_text"], p["rsd_text"], p["backcalc_text"]] for p in calibration["points"]], [20, 22, 23, 13, 22]))
                story.append(paragraph("二、樣品及品管分析數據", heading))
                if len(sheets) > 1:
                    story.append(paragraph("每組最多 10 個一般樣品；批次共用品管於各組重列，關聯 DUP／MS／MSD 隨原樣列出。"))
                data = []
                method = batch["setting"]["method"]
                volumes = {(compact(row.get("sample_volume")), compact(row.get("final_volume")))
                           for row in rows if not row.get("direct")}
                if len(volumes) == 1:
                    sample_volume, final_volume = next(iter(volumes))
                    story.append(paragraph("樣品體積：{} mL　定量體積：{} mL".format(sample_volume, final_volume)))
                elif volumes:
                    story.append(paragraph("本組體積設定不同，樣品體積／定量體積另列於備註（mL）。"))
                for sequence, row in enumerate(rows, 1):
                    label = str(row.get("sample_id") or "")
                    if row.get("check_position"):
                        label += "\n" + row["check_position"]
                    if row.get("parent_sample_id"):
                        label += "\n原樣：" + str(row["parent_sample_id"])
                    remark = interpretation(row)
                    if row.get("manual_adoption"):
                        remark += ("\n" if remark else "") + "採用（LIMS 未配對）"
                    if len(volumes) > 1 and not row.get("direct"):
                        remark += ("\n" if remark else "") + "體積 {}/{} mL".format(compact(row.get("sample_volume")), compact(row.get("final_volume")))
                    role = row.get("role")
                    spike_key = "MS_SPIKE_CONC" if role in {"MS", "MSD"} else str(role) + "_SPIKE_CONC"
                    spike = compact(method.get(spike_key)) if role in {"ICV", "CCV", "QC", "MS", "MSD"} else ""
                    data.append([str(sequence), label, compact(row.get("dilution_factor")), row.get("signal_text", ""),
                                 row.get("rsd_text", ""), spike, number(row.get("measured_concentration"), digits), number(row.get("sample_concentration"), digits), remark])
                story.append(table(["序號", "樣品編號", "稀釋倍數", "平均測定值", "RSD\n(n=3)", "添加濃度\n(mg/L)", "測定濃度\n(" + unit + ")", "樣品濃度\n(" + unit + ")", "備註"], data, [5, 23, 8, 13, 7, 10, 12, 12, 12]))
                story.append(paragraph("三、QA/QC 判定（本批次共用）　" + str(qc["status"]), heading))
                if qc.get("error"):
                    story.append(paragraph(qc["error"]))
                def bounds(row):
                    limits = row.get("bounds") or {}
                    if "limit" in limits:
                        return "±" + compact(limits["limit"]) + "%"
                    return "{}% ～ {}%".format(compact(limits.get("lcl")), compact(limits.get("ucl")))
                summary = []
                for q in qc["a"]:
                    summary.append(["3A " + q["role"] + "\n" + str(q.get("check_position") or ""), q["sample_id"],
                                    q.get("calculation_name", "") + " " + number(q.get("metric"), 2) + "%", bounds(q), q["status"] + ("\n" + q["reason"] if q.get("reason") else "")])
                for q in qc["b"]:
                    summary.append(["3B " + q["source"], str(q["sample_a"]) + " / " + str(q["sample_b"]),
                                    "RPD " + number(q.get("rpd"), 2) + "%", "≤ " + compact(q.get("ucl")) + "%", q["status"] + ("\n" + q["reason"] if q.get("reason") else "")])
                for q in qc["c"]:
                    summary.append(["3C " + q["role"], q["sample_id"] + "\n原樣：" + str(q.get("original_sample_id") or "—"),
                                    "回收率 " + number(q.get("metric"), 2) + "%", bounds(q), q["status"] + ("\n" + q["reason"] if q.get("reason") else "")])
                story.append(table(["項目", "樣品／配對", "結果", "判定標準", "符合性／說明"], summary, [15, 26, 17, 17, 25]))
    if not templates:
        raise ValueError("沒有可匯出的分析數據。")
    doc.addPageTemplates(templates)
    doc.build(story, canvasmaker=_NumberedCanvas)
    buffer.seek(0)
    return buffer
