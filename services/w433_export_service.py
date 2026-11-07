"""W433 record exports using snapshot values and the shared LIMS writer."""
import math
import os
from io import BytesIO
from xml.sax.saxutils import escape
from exports.lims_export_model import LimsExportData, LimsQcRow, LimsAnalysisRow
from exports.w434_lims_mapper import _build_batch_no, _build_lims_result


def num(value, digits=6):
    return "-" if value is None else format(float(value), "."+str(digits)+"f")


def build_excel(b, user, template_path):
    from exports.lims_excel_exporter import build_lims_excel
    from services.w433_work_service import validate
    checks = b["state"]["checks"]
    validate(b, checks)
    form,control,result = b["form_data"],b["control_data"],b["state"]["result"]
    mdl = float(control.get("DETECT_LIMITED") or 0)
    if mdl <= 0 or not math.isfinite(mdl):
        raise ValueError("請先設定有效的年度 MDL。")
    qdl = min(r["instrument_conc"] for r in result["standards"] if r["instrument_conc"]>0)
    if b["method_data"].get("QDL_SOURCE") != "FIRST_NONZERO_CALIBRATION_X":
        raise ValueError("尚不支援此 QDL 來源，請確認方法設定。")
    qdl *= float(b["method_data"].get("QDL_MULTIPLIER") or 1)
    data = LimsExportData()
    for batch in sorted({r["batch"] for r in result["rows"]}):
        selected = [r for r in checks if r["batch"] == batch]
        def one(role):
            matches=[r for r in selected if r["role"] == role]
            if len(matches)!=1:
                raise ValueError("LIMS 每批需要一筆 "+role+"，請確認批次。")
            return matches[0]
        qc,dup,spike,bk = (one(role) for role in ("QC","DUP","MS","BK"))
        cc = [r for r in selected if r["role"] in {"ICV","CCV"}]
        if not cc: raise ValueError("缺少檢量線查核。")
        batch_no = _build_batch_no(form["analysis_start_date"],control["EXAMNO"],batch)
        data.qc_rows.append(LimsQcRow(analysis_date=form["analysis_start_date"],
            analyst=user.get("employee_name",""),exam_no=control["EXAMNO"],instrument_id=form["instrument_id"],
            max_signal=max(r["absorbance"] for r in result["standards"]),duplicate_result=dup["metric"],
            qc_result=qc["metric"],spike_result=spike["metric"],
            calibration_check=max(cc,key=lambda r:abs(r["metric"]))["metric"],
            blank_result=bk["status"],batch_no=batch_no,correlation_coefficient=result["calibration"]["r"]))
        for row in result["rows"]:
            if row["batch"]!=batch or row["role"]!="SAMPLE":continue
            value,remark = _build_lims_result(row["sample_concentration"],mdl*row["dilution"],qdl*row["dilution"])
            data.analysis_rows.append(LimsAnalysisRow(sample_id=row["sample_id"],exam_no=control["EXAMNO"],
                result=value,remark=remark,batch_no=batch_no))
    return build_lims_excel(template_path,data,analyst_id=user.get("employee_id",""),
                           analyst_name=user.get("employee_name",""),analysis_method=control.get("EM_NO",""))


def build_pdf(b, user):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
    from services.w433_work_service import validate
    validate(b,b["state"]["checks"])
    font="W433Record"
    if font not in pdfmetrics.getRegisteredFontNames():
        path=os.environ.get("PHYON_PDF_FONT") or r"C:\Windows\Fonts\msjh.ttc"
        if not os.path.isfile(path):
            if os.name == "nt":
                raise ValueError("找不到 PDF 中文字型，請設定 PHYON_PDF_FONT。")
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            font="STSong-Light"
            if font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(font))
        else:
            pdfmetrics.registerFont(TTFont(font,path,subfontIndex=0))
    width,height=A4;usable=width-60
    style=ParagraphStyle("W433",fontName=font,fontSize=7.5,leading=10)
    def para(s):return Paragraph(escape(str(s)),style)
    def table(rows,widths=None):
        t=Table([[v if hasattr(v,"wrap") else para(v) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.grey),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
            ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        return t
    result,form,control,report = b["state"]["result"],b["form_data"],b["control_data"],b["report_data"]
    batches=sorted({r["batch"] for r in result["rows"]});out=BytesIO();c=canvas.Canvas(out,pagesize=A4)
    for page,batch in enumerate(batches,1):
        c.setTitle("W433 硫化物檢驗紀錄表")
        c.setFont(font,8)
        c.drawString(30,height-26,str(report.get("COMPANY_NAME") or ""))
        c.drawRightString(width-30,height-26,str(report.get("DOC_NO") or "")+"　版次："+str(report.get("REVISION") or ""))
        c.drawRightString(width-30,height-39,"發行日期："+str(report.get("ISSUE_DATE") or ""))
        c.setFont(font,12)
        c.drawCentredString(width/2,height-57,str(report.get("FORM_TITLE") or "硫化物檢驗紀錄表"))
        c.setFont(font,8)
        c.drawCentredString(width/2,height-72,"檢驗項目：硫化物　使用波長：664 nm")
        c.drawString(30,height-88,"儀器："+str(form.get("instrument_model") or "")+"　"+form["instrument_id"])
        c.drawRightString(width-30,height-88,"填表日期："+form.get("form_date",""))
        c.drawString(30,height-101,"檢驗方法："+str(control.get("EM_NO") or "W433"))
        c.drawRightString(width-30,height-101,"分析日期："+form.get("analysis_start_date","")+" ～ "+form.get("analysis_end_date",""))
        c.drawString(30,height-114,"類別："+form.get("category","")+"　檢測代碼："+control.get("EXAMNO","")+"　Batch "+str(batch))
        c.line(30,height-122,width-30,height-122)
        flows=[]
        curve=result["calibration"]
        cal=[["標準點","濃度 (mg/L)","吸光度","回歸濃度"]]
        cal += [[r["sample_id"],num(r["instrument_conc"],4),num(r["absorbance"],4),
                 num((r["absorbance"]-curve["intercept"])/curve["slope"])] for r in result["standards"]]
        pfm=[["儀器性能查核（UV）","吸光度","管制範圍","判定"]]
        for item in b["state"].get("pfm",[]):
            ctrl=item["control"];row=item.get("row")
            pfm.append([item["label"],num(row["absorbance"],4) if row else "-",
                        num(ctrl.get("lower_limit"),4)+" ～ "+num(ctrl.get("upper_limit"),4),item["status"]])
        if len(pfm)==1:pfm.append(["本次未匯入 PFM","-","-","-"])
        flows += [para("一、檢量線　Y = "+num(curve["slope"])+" X "+format(curve["intercept"],"+.6f")+"；r = "+num(curve["r"])),
                  table([[table(cal,[42,65,57,84]),table(pfm,[72,38,91,37])]], [usable/2,usable/2]),Spacer(1,6)]
        rows=[["樣品編號","吸光度","D","測定濃度","樣品濃度","備註"]]
        mdl=float(control.get("DETECT_LIMITED") or 0);qdl=min(r["instrument_conc"] for r in result["standards"] if r["instrument_conc"]>0)
        for r in result["rows"]:
            if r["batch"]!=batch:continue
            note=""
            if r["role"]=="SAMPLE":
                if r["sample_concentration"]<mdl*r["dilution"]:note="ND<"+num(mdl*r["dilution"],4)
                elif r["sample_concentration"]<qdl*r["dilution"]:note="<QDL"
            if r["role"]=="BK":note=next((x["status"] for x in b["state"]["checks"] if x["source_line"]==r["source_line"]),"")
            rows.append([r.get("raw_sample_id",r["sample_id"]),num(r["absorbance"],4),num(r["dilution"],1),
                         num(r["equivalent_concentration"]),num(r["sample_concentration"]),note])
            if r.get("blank"):rows.append([r["blank"]["sample_id"],num(r["blank"]["absorbance"],4),"-","-","-",""])
        flows += [para("二、樣品及 QA/QC 計算"),table(rows,[145,55,30,90,90,usable-410]),Spacer(1,6)]
        qa=[["項目","原樣","結果 (%)","判定標準","判定"]]
        for item in b["state"]["checks"]:
            if item["batch"]==batch:qa.append([item["role"],item["original"],num(item["metric"],1),item["criteria"],item["status"]])
        flows += [para("三、QA/QC 檢核"),table(qa,[45,140,70,155,usable-410])]
        measured=[(f,f.wrap(usable,height)[1]) for f in flows]
        total=sum(h for _,h in measured);scale=min(1,(height-192)/total)
        if scale<.78:raise ValueError("本批資料過多，無法以可讀字級印於一頁，請確認批次。")
        c.saveState();c.translate(30,height-133);c.scale(scale,scale);y=0
        for f,h in measured:y-=h;f.drawOn(c,0,y)
        c.restoreState();c.setFont(font,8)
        c.drawString(30,36,"審核：　　　　　　　　驗算：　　　　　　　　分析："+user.get("employee_name",""))
        c.drawCentredString(width/2,18,"第 {} 頁／共 {} 頁".format(page,len(batches)))
        c.showPage()
    c.save();out.seek(0);return out
