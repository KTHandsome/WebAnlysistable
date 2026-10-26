"""Read-only W427 exact category/exam selection. Annual control is authoritative."""
import csv
import os
from flask import current_app


def _read(name):
    path = os.path.join(current_app.root_path, "data", name)
    if not os.path.isfile(path):
        raise ValueError("尚未匯入 " + name + "。")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _name(value):
    return str(value or "").strip().replace("－", "-").replace(" ", "").upper()


def _basis(control):
    name = _name(control.get("EXAMNAME"))
    unit = str(control.get("CTRL_UNIT") or "").replace(" ", "")
    if unit:
        if unit == "mgP/L":return "mg P/L", "1"
        if unit in {"mgPO₄³⁻/L", "mgPO4/L", "mgPO4^3-/L"}:return "mg PO₄³⁻/L", "3.07"
        raise ValueError("年度管制表的 W427 單位尚未支援，請先確認。")
    # Unconfirmed annual G data may lack units; classify its named analyte, never fabricate MDL/limits.
    if name == "正磷酸鹽":return "mg PO₄³⁻/L", "3.07"
    if name in {"總磷", "磷酸鹽磷", "正磷酸鹽-磷", "磷酸鹽-磷"}:return "mg P/L", "1"
    raise ValueError("年度管制表的 W427 測項與單位尚未明確。")


def load_w427_settings(form):
    common = {"METHOD_CODE":"W427", "IMPORT_TYPE":"UV_TXT", "ANALYSIS_MODE":"SINGLE", "DATA_ENTRY_MODE":"BOTH"}
    try:
        category = str(form.get("category") or "").strip().upper()
        code = str(form.get("selected_exam_no") or "").strip()
        name = _name(form.get("exam_name"))
        year = str(form.get("ctrl_year") or "").strip()
        if not category or not year or not name:
            raise ValueError("請先填寫管制年度、類別與測項名稱。")
        candidates = [r for r in _read("Phyon_Control_"+year+".csv")
                      if r.get("CTRL_YEAR", "").strip()==year and r.get("CATEGORY_CODE", "").upper()==category
                      and r.get("EM_NUM", "").upper()=="W427"]
        if code:
            candidates = [r for r in candidates if r.get("EXAMNO")==code]
        else:
            exact = [r for r in candidates if name in {_name(r.get("EXAMNAME")),_name(r.get("EXALIAS"))}]
            if exact:candidates=exact
            elif name=="磷":pass
            elif name=="磷酸鹽":candidates=[r for r in candidates if "磷酸鹽" in str(r.get("EXAMNAME") or "")]
            else:candidates=[]
        if not candidates:raise ValueError("年度管制表查無此類別／檢測代碼的 W427 項目。")
        instrument = str(form.get("instrument_id") or "").strip().upper()
        specific = [r for r in candidates if instrument and str(r.get("LABPARTID") or "").upper()==instrument]
        candidates = specific or [r for r in candidates if not str(r.get("LABPARTID") or "").strip()]
        if len(candidates)>1:
            return {"_multiple_matches":candidates},common,"請先選擇 W427 檢測代碼。"
        if not candidates:raise ValueError("所選儀器沒有適用的 W427 年度設定。")
        control=candidates[0]
        methods=[r for r in _read("Phyon_Method_Settings.csv") if str(r.get("ACTIVE") or "").upper()=="Y"
                 and str(r.get("METHOD_CODE") or "").upper()=="W427"
                 and str(r.get("CATEGORY_CODE") or "").upper()==category and r.get("EXAMNO")==control["EXAMNO"]]
        if len(methods)!=1:raise ValueError("W427 方法設定必須依類別與檢測代碼唯一對應，請匯入本次修正版 CSV。")
        method=methods[0]
        unit,factor=_basis(control)
        if (method.get("DISPLAY_CONC_UNIT")!=unit or str(method.get("RESULT_CONVERSION_FACTOR") or "")!=factor
                or _name(method.get("EXAMNAME"))!=_name(control.get("EXAMNAME"))):
            raise ValueError("方法設定的測項、單位或結果換算係數與年度管制表不符，請匯入本次修正版 CSV。")
        if (method.get("CALIBRATION_UNIT")!="mg P/L" or method.get("IMPORT_TYPE")!="UV_TXT"
                or method.get("ANALYSIS_MODE")!="SINGLE"):
            raise ValueError("W427 須為 mg P/L 檢量線、UV_TXT／SINGLE。")
        return control,method,None
    except (ValueError,OSError) as exc:
        return {},common,str(exc)
