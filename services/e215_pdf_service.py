"""E215 PDF export using report settings and saved analyte results."""
from decimal import Decimal
import re
from datetime import date, datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle

FONT = "MSung-Light"


def roc(value, with_time=False):
    try:
        parsed = datetime.fromisoformat(value) if with_time else date.fromisoformat(value)
    except (TypeError, ValueError):
        return str(value or "—")
    text = "{:03d}.{:02d}.{:02d}".format(parsed.year - 1911, parsed.month, parsed.day)
    return text + parsed.strftime("    %H:%M") if with_time else text


def build_coliform_pdf(batches, report, preview=False, include_ecoli=False):
    from services.e215_validation_service import validate_batches
    validate_batches(batches, include_ecoli=include_ecoli)
    keys = ("COMPANY_NAME", "FORM_TITLE", "DOC_NO", "REVISION", "ISSUE_DATE")
    company, title, doc_no, revision, issue_date = (str(report.get(k) or "").strip() for k in keys)
    if not all((company, title, doc_no, revision, issue_date)):
        raise ValueError("正式紀錄的報表設定缺少表頭欄位。")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", revision):
        revision = format(Decimal(revision), ".2f")
    font = UnicodeCIDFont(FONT)
    font.encodingName = "UniCNS-UCS2-H"
    pdfmetrics.registerFont(font)
    stream = BytesIO()
    pdf = Canvas(stream, pagesize=A4)
    pdf.setTitle(title)
    width, height = A4
    left, right = 24, width - 24
    pages = []
    for batch_no, batch in enumerate(batches, 1):
        current, spans = [], []
        for row in batch["rows"]:
            group = []
            analytes = [("Coliform", "大腸桿菌群", 0)]
            if include_ecoli:
                analytes.append(("E. coli", "大腸桿菌", 2))
            for analyte, label, offset in analytes:
                for line in row["lines"]:
                    output = next((x for x in line["outputs"] if x["analyte"] == analyte), None)
                    if output is None or len(line["counts"]) < offset + 2:
                        raise ValueError("正式紀錄缺少 {} 結果，請確認原始紀錄。".format(analyte))
                    group.append([row["sample_id"], label, row["time"] or "—", row["tray"],
                                  line["factor"], line["counts"][offset],
                                  line["counts"][offset+1] if row["tray"] == "97" else "—",
                                  output["adjusted"], "是" if line["selected"] else "—",
                                  output["report"] if line["selected"] and not (include_ecoli and analyte == "Coliform") else "-"])
            while group:
                n = min(len(group), 29)
                if current and len(current) + n > 29:
                    pages.append((batch_no, batch["fields"], current, spans))
                    current, spans = [], []
                first = len(current) + 1  # table row 0 is the header
                # Repeat merged identifiers and analyte labels on continuation pages.
                for col in range(4):
                    start = 0
                    for stop in range(1, n+1):
                        if stop == n or group[stop][col] != group[start][col]:
                            if stop-start > 1:
                                spans.append(("SPAN", (col, first+start), (col, first+stop-1)))
                            start = stop
                current.extend(group[:n])
                group = group[n:]
        if current:
            pages.append((batch_no, batch["fields"], current, spans))

    if not pages:
        raise ValueError("查無可匯出的正式檢驗結果。")

    def draw_field(label, value, x, y, line_end):
        pdf.drawString(x, y, label)
        label_width = pdfmetrics.stringWidth(label, FONT, 10.5)
        start = x + label_width + 5
        text = str(value or "—")
        size = min(10.5, 10.5 * (line_end - start - 4) /
                   max(1, pdfmetrics.stringWidth(text, FONT, 10.5)))
        pdf.setFont(FONT, size)
        cursor = pdf.beginText(start + 2, y)
        for index, part in enumerate(text.split("®")):
            if index:
                cursor.setFont("Helvetica", size)
                cursor.textOut("®")
            cursor.setFont(FONT, size)
            cursor.textOut(part)
        pdf.drawText(cursor)
        pdf.line(start, y - 3, line_end, y - 3)
        pdf.setFont(FONT, 10.5)

    for index, (batch_no, fields, rows, spans) in enumerate(pages, 1):
        y = height - 27
        pdf.setFont(FONT, 10.5)
        pdf.drawString(left, y, company)
        pdf.drawRightString(right, y, doc_no + "  版次：" + revision)
        pdf.drawRightString(right, y - 14, "發行日期：" + issue_date)
        pdf.setFont(FONT, 15)
        pdf.setFont(FONT, min(15, 15 * (right-left) / max(1, pdfmetrics.stringWidth(title, FONT, 15))))
        pdf.drawCentredString(width / 2, y - 36, title)
        pdf.setFont(FONT, 10.5)
        data = [
            ("檢驗方法：", fields[0], "採樣日期：", roc(fields[3])),
            ("培　養　基：", fields[1], "培養日期/時間(起)：", roc(fields[4], True)),
            ("培養溫度：", str(fields[2]) + "℃", "培養日期/時間(迄)：", roc(fields[5], True)),
        ]
        for i, (label, value, label2, value2) in enumerate(data):
            draw_field(label, value, left, y - 56 - 18*i, 279)
            draw_field(label2, value2, 318, y - 56 - 18*i, right)
        headings = ["樣品編號", "檢測項目", "採樣時間", "定量盤\n孔數", "稀釋\n倍數",
                    "大孔\n陽性數", "小孔\n陽性數", "查表值\n× 倍數",
                    "選取\n倍數", "報告值\nMPN/100 mL"]
        col_widths = [91, 64, 47, 42, 38, 40, 40, 53, 42]
        col_widths.append(right-left-sum(col_widths))
        table = Table([headings] + rows, colWidths=col_widths, rowHeights=[33]+[20]*len(rows))
        table.setStyle(TableStyle(spans + [
            ("FONTNAME", (0,0), (-1,-1), FONT),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("GRID", (0,0), (-1,-1), 0.45, black),
            ("BOX", (0,0), (-1,-1), 0.85, black),
        ]))
        _, table_h = table.wrapOn(pdf, right-left, height)
        table.drawOn(pdf, left, y - 103 - table_h)
        pdf.drawString(left, 31, "批次 {}".format(batch_no))
        if preview:
            pdf.drawCentredString(width / 2, 31, "預覽｜非正式紀錄")
        pdf.drawRightString(right, 31, "第 {} 頁 / 共 {} 頁".format(index, len(pages)))
        pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream
