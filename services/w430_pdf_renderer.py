"""W430 A4 record: calculated values, one batch per page."""
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
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer


def _font():
    name = "PhyonW430JhengHei"
    if name not in pdfmetrics.getRegisteredFontNames():
        path = os.environ.get("PHYON_PDF_FONT") or r"C:\Windows\Fonts\msjh.ttc"
        if not os.path.isfile(path):
            raise ValueError("找不到 PDF 中文字型，請確認 Windows 微軟正黑體。")
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
    return name


def _number(value, places=4):
    if value is None or value == "":
        return "-"
    try:
        value = float(value)
        return format(value, ".{}f".format(places)) if math.isfinite(value) else "-"
    except (ValueError, TypeError, OverflowError):
        return "-"


def _decimals(method, key, default=4):
    try:
        value = int(method.get(key) or default)
        return value if 0 <= value <= 10 else default
    except (TypeError, ValueError):
        return default


def _remark(row, control, places):
    """Only analytical interpretation belongs in the printed remark column."""
    value = str(row.get("interpretation") or "")
    if value == "ND":
        try:
            limit = float(control["DETECT_LIMITED"]) * float(row["dilution_factor"])
        except (KeyError, TypeError, ValueError):
            return value
        return "ND\nMDL=" + _number(limit, places)
    if value == "<QDL":
        return value + "\nQDL=" + _number(row.get("qdl"), places)
    return value


def build_w430_pdf(report, method, control, form, analysis):
    font = _font()
    width, height = A4
    usable, top, bottom = width - 80, height - 122, 57
    available = top - bottom
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    c.setTitle(str(report.get("FORM_TITLE") or "W430 硫酸鹽檢驗紀錄表"))
    regular = ParagraphStyle("W430Compact", fontName=font, fontSize=7, leading=9, wordWrap="CJK")
    heading = ParagraphStyle("W430CompactHeading", parent=regular, fontSize=8.3, leading=11)
    def p(value, style=regular):
        return Paragraph(escape(str(value if value is not None else "-")).replace("\n", "<br/>"), style)
    def table(headers, rows, weights, span=usable):
        widths = [w / sum(weights) * span for w in weights]
        t = Table([[p(v) for v in headers]] + [[p(v) for v in row] for row in rows],
                  colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.black),
                              ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                              ("LEFTPADDING",(0,0),(-1,-1),2), ("RIGHTPADDING",(0,0),(-1,-1),2),
                              ("TOPPADDING",(0,0),(-1,-1),1.5), ("BOTTOMPADDING",(0,0),(-1,-1),1.5)]))
        return t
    rows = [r for r in analysis.get("sample_qaqc_rows", []) if not r.get("is_excluded")]
    groups = {}
    for row in rows:
        key = str(row.get("edit_group") or "")
        if not key:
            raise ValueError("樣品缺少日期／批次識別，無法按批次列印。")
        groups.setdefault(key, []).append(row)
    def sort_key(item):
        date, number = item.rsplit("|", 1)
        return date, int(number)
    try:
        keys = sorted(groups, key=sort_key)
    except (ValueError, TypeError):
        raise ValueError("樣品批次識別格式異常。")
    qc = {str(b["batch_no"]): b for b in analysis.get("qaqc_3a_results", [])}
    if not keys or len(qc) != len(keys):
        raise ValueError("樣品批次與 QA/QC 不一致，請先更新樣品及 QA/QC。")
    places = _decimals(method,"PDF_CONCENTRATION_DECIMALS")
    signals = _decimals(method,"PDF_SIGNAL_DECIMALS")
    masses = _decimals(method,"PDF_CALIBRATION_BACKCALC_DECIMALS")
    xs = _decimals(method,"PDF_CALIBRATION_X_DECIMALS")
    calibration = analysis["calibration_result"]
    def page_header(batch_number):
        y = height - 30
        c.setFont(font,8)
        c.drawString(40,y,str(report.get("COMPANY_NAME") or ""))
        c.drawRightString(width-40,y,str(report.get("DOC_NO") or "")+" 版次："+str(report.get("REVISION") or ""))
        c.drawRightString(width-40,y-13,"發行日期："+str(report.get("ISSUE_DATE") or ""))
        c.setFont(font,12)
        c.drawCentredString(width/2,y-25,str(report.get("FORM_TITLE") or "W430 硫酸鹽檢驗紀錄表"))
        c.setFont(font,8)
        c.drawCentredString(width/2,y-39,"檢驗項目："+str(method.get("ANALYTE_DISPLAY") or form.get("exam_name") or "硫酸鹽")+"　使用波長：420 nm")
        c.drawString(40,y-53,"儀器："+str(form.get("instrument_model") or "")+"　"+str(form.get("instrument_id") or ""))
        c.drawRightString(width-40,y-53,"填表日期："+str(form.get("form_date") or ""))
        c.drawString(40,y-66,"檢驗方法："+str(control.get("EM_NO") or "NIEA W430.52C"))
        c.drawRightString(width-40,y-66,"分析日期："+str(form.get("analysis_start_date") or "")+" ~ "+str(form.get("analysis_end_date") or ""))
        c.drawString(40,y-79,"類別："+str(form.get("category") or "")+"　檢測代碼："+str(control.get("EXAMNO") or "")+"　Batch "+str(batch_number))
        c.line(40,y-85,width-40,y-85)
    for number, key in enumerate(keys,1):
        batch = qc.get(str(number))
        if batch is None:
            raise ValueError("缺少批次 QA/QC。")
        page_header(number)
        story=[]
        def add(flow):story.append(flow)
        half=(usable-10)/2
        a=calibration.get("intercept")
        left=[p("一、檢量線",heading), p("Y = {} X {} {}；r = {}".format(_number(calibration.get("slope"),6),
                "+" if a is not None and a>=0 else "-",_number(abs(a) if a is not None else None,6),_number(calibration.get("r"),4))),
              table(["標準品","設定含量 (mg)","吸光度","回歸含量 (mg)"],
                    [[r.get("sample_id") or "STD{}".format(i),_number(r.get("x"),xs),_number(r.get("y"),signals),
                      _number(r.get("back_calculated_x"),masses)] for i,r in enumerate(calibration.get("points",[]))],
                    [45,70,60,78],half)]
        pfm=[]
        for r in analysis.get("prm_results",[]):
            ctrl=r.get("control") or {}
            pfm.append([str(r.get("sample_id") or "")+"\n"+str(r.get("analysis_datetime") or ""),
                        _number(r.get("signal"),signals),_number(ctrl.get("lower_limit"),signals)+" ~ "+_number(ctrl.get("upper_limit"),signals),
                        {"PASS":"合格","FAIL":"不合格"}.get(r.get("status"),"無法判定")])
        # Align both table top borders using the actual regression paragraph height.
        equation_height = left[1].wrap(half, 10000)[1]
        right=[Spacer(1,equation_height),p("儀器性能查核（UV）",heading),
               table(["查核項目／實際測定時間","吸光度","管制範圍","判定"],pfm,[110,48,79,35],half),
               Spacer(1,5),p("年度 MDL：{} mg/L\n基準 QDL：{} mg/L".format(_number(control.get("DETECT_LIMITED"),places),_number(analysis.get("qdl_value"),places))),
               p("A 液不扣 BKA；B 液扣對應 B 空白含量。\nBKB 單獨扣除 1.5 mg。")]
        paired=Table([[left,"",right]],colWidths=[half,10,half],hAlign="LEFT")
        paired.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),
                                    ("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
        add(paired);add(Spacer(1,6));add(p("二、樣品及品管分析結果",heading))
        volumes=[]
        for r in groups[key]:
            if r.get("sample_volume") not in volumes:volumes.append(r.get("sample_volume"))
        add(p("濃度 (mg/L) = 淨含量 (mg) ÷ 水樣體積 (mL) × 1000 × D；本批水樣體積："+"、".join(_number(v,2) for v in volumes)+" mL"))
        sample_rows=[]
        for seq,r in enumerate(groups[key],1):
            sample_rows.append([seq,r.get("sample_id"),r.get("buffer") or "-",format(float(r["dilution_factor"]),".10g"),
                                _number(r.get("signal"),signals),_number(r.get("measured_concentration"),masses),
                                _number(r.get("blank_mass"),masses),_number(r.get("net_mass"),masses),
                                _number(r.get("sample_concentration"),places),_remark(r,control,places)])
        add(table(["序號","樣品編號","緩衝液","D","吸光度","測定含量\n(mg)","扣除含量\n(mg)","淨含量\n(mg)","樣品濃度\n(mg/L)","備註"],
                  sample_rows,[20,112,24,24,46,52,52,52,62,71]))
        add(Spacer(1,6));add(p("三、QA/QC 判定",heading))
        checks=[]
        for r in batch.get("rows",[]):
            checks.append([str(r.get("role") or "")+" "+str(r.get("calculation_name") or ""),_number(r.get("check_value"),2)+" %",r.get("control_text") or "-",r.get("status") or "-"])
        r=batch.get("precision")
        if r:checks.append([str(r.get("source_name") or "重複分析")+" RPD",_number(r.get("rpd"),2)+" %","≤ "+_number(r.get("ucl"),2)+" %",r.get("status") or "-"])
        for r in batch.get("spike_recovery",[]):
            checks.append([str(r.get("role") or "")+" 回收率",_number(r.get("recovery"),2)+" %",_number(r.get("lcl"),2)+" ~ "+_number(r.get("ucl"),2)+" %",r.get("status") or "-"])
        add(table(["查核項目","結果","判定標準","判定"],checks,[180,100,165,70]))
        if batch.get("batch_remark"):add(p("批次備註："+str(batch["batch_remark"])))
        measured=[(flow,flow.wrapOn(c,usable,10000)[1]) for flow in story]
        total=sum(h for _,h in measured)
        scale=min(1.0,available/total)
        if scale < .86:
            raise ValueError("Batch {} 資料量超出單頁可讀範圍，請先確認批次切割與樣品列數。".format(number))
        c.saveState();c.translate(40+(usable-usable*scale)/2,top);c.scale(scale,scale)
        y=0
        for flow,h in measured:
            y-=h;flow.drawOn(c,0,y)
        c.restoreState()
        c.setFont(font,9)
        for i,text in enumerate(("審核：","驗算：","分析：")):c.drawString(40+i*usable/3,38,text)
        c.setFont(font,7.5);c.drawCentredString(width/2,14,"第 {} 頁 / 共 {} 頁".format(number,len(keys)))
        c.showPage()
    c.save();output.seek(0);return output
