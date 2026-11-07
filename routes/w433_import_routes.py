"""W433 UV TXT preview."""
import hmac
import math
from datetime import date
from copy import deepcopy
from itsdangerous import URLSafeTimedSerializer, BadData
from database import SessionLocal
from auth_session import get_current_user, login_required
from services.w433_work_service import (
    new_bundle, load_bundle, save_bundle, list_drafts, clean_result, submit_bundle,
)
from analysis.analysis_work_draft_repository import DraftConflictError
from services.report_setting_service import load_report_setting
import os
import secrets

from flask import Blueprint, current_app, render_template, request, session, redirect, url_for, send_file
from parsers.uv_txt_parser import MAX_FILE_BYTES, parse_uv_text
from analysis.w433_core import build_w433_result



PFM_ITEMS = {
    "石英槽比對": "CELL_CHECK_664",
    "最大吸光度": "MAX_ABS_664",
    "最大吸光值": "MAX_ABS_664",
}


def evaluate_pfm(rows, form, lookup):
    output = []
    for label in ("石英槽比對", "最大吸光度"):
        monitor = PFM_ITEMS[label]
        matches = [row for row in rows if PFM_ITEMS[row["sample_id"]] == monitor]
        item = dict(label=label, status="無法判定", control={}, row=None, message="")
        output.append(item)
        if len(matches) != 1:
            item["message"] = "缺少量測或有重複量測。"
            continue
        item["row"] = row = matches[0]
        try:
            day = date.fromisoformat(form.get("analysis_start_date") or "")
        except ValueError:
            item["message"] = "請先完善基本資料：分析起始日期。"
            continue
        try:
            control = lookup(instrument_id=form["instrument_id"], monitor_item=monitor,
                             performance_type="CAL_HIGH_SIGNAL", analysis_date=day)
            if control.get("unit") != "Abs":
                raise ValueError("管制單位須為 Abs。")
            ref, low, high = (float(control[k]) for k in
                              ("reference_value", "lower_limit", "upper_limit"))
            if not all(math.isfinite(v) for v in (ref, low, high)) or not low <= ref <= high:
                raise ValueError("管制限值無效。")
            item["control"] = control
            item["status"] = "合格" if low <= row["absorbance"] <= high else "超限"
        except (ValueError, TypeError, KeyError, RuntimeError) as exc:
            item["message"] = str(exc)
    return output


def preview_uploads(uploads):
    files = {}
    for upload in uploads:
        name = upload.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not name.lower().endswith(".txt"):
            raise ValueError("只接受 .txt 檔案。")
        payload = upload.stream.read(MAX_FILE_BYTES + 1)
        rows, _ = parse_uv_text(payload, name)
        kinds = {row["type"].strip().upper() for row in rows}
        if kinds == {"STANDARD"}:
            kind = "standard"
        elif kinds == {"UNKNOWN"} and any(row["sample_id"] in PFM_ITEMS for row in rows):
            if any(row["sample_id"] not in PFM_ITEMS or row["wavelength"] != 664
                   for row in rows):
                raise ValueError(name + "：PFM 檔須為獨立的 664 nm 查核資料。")
            kind = "pfm"
            payload = rows
        elif kinds == {"UNKNOWN"}:
            kind = "sample"
        else:
            raise ValueError(name + "：無法辨識為單一標準檔或樣品檔。")
        if kind in files:
            raise ValueError("同一類 TXT 只可選一個。")
        files[kind] = payload, name
    if not {"standard", "sample"} <= set(files):
        raise ValueError("請同時選取檢量線 TXT 和樣品 TXT。")
    standard, sample = files["standard"], files["sample"]
    result = build_w433_result(standard[0], sample[0], standard[1], sample[1])
    result["rows"].sort(key=lambda row: row["source_line"])
    result["pfm_rows"] = files.get("pfm", ([], ""))[0]
    return result


def assign_batches(rows):
    count, original = 0, None
    for row in sorted(rows, key=lambda r: r["source_line"]):
        if row["role"] == "SAMPLE":
            count += 1
            original = row
        row["batch"] = max(1, (count + 9) // 10)
        row["original"] = original if row["role"] in {"DUP", "MS", "MSD"} else None


def build_qaqc_preview(rows, method, control):
    def number(data, key):
        try:
            value = float(data.get(key))
            return value if math.isfinite(value) else None
        except (ValueError, TypeError):
            return None

    checks = []
    for row in rows:
        role = row["role"]
        if role == "SAMPLE":
            continue
        measured = row["sample_concentration"]
        target = number(method, ("MS" if role == "MSD" else role) + "_SPIKE_CONC")
        item = dict(role=role, measured=measured, target=None, metric=None,
                    batch=row["batch"], original="", source_line=row["source_line"],
                    criteria="—", status="待確認")
        checks.append(item)
        if role in {"ICV", "CCV", "QC"}:
            if target is None or target <= 0:
                item["status"] = "未設定配製濃度"
                continue
            item["target"] = target
            percent = 100 * measured / target
            item["metric"] = percent if role == "QC" else percent - 100
            if role in {"ICV", "CCV"}:
                item["criteria"] = "±10.0%"
                item["status"] = "合格" if -10.0 <= item["metric"] <= 10.0 else "超限"
                continue
            if role == "QC":
                low, high = (number(control, key) for key in ("QC_LCL", "QC_UCL"))
                if str(control.get("CONFIRMED") or "").strip() == "1" and low is not None and high is not None and low <= high:
                    item["criteria"] = "{:g}～{:g}%".format(low, high)
                    item["status"] = "合格" if low <= percent <= high else "超限"
                    continue
            item["status"] = "未設定相對誤差限值" if role in {"ICV", "CCV"} else "未取得已確認的判定標準"
        elif role == "BK":
            mdl = number(control, "DETECT_LIMITED")
            multiplier = number(method, "BLANK_MDL_MULTIPLIER")
            if mdl is not None and mdl > 0 and multiplier is not None and multiplier > 0:
                item["criteria"] = "< {:g} mg/L（{:g} × MDL）".format(mdl * multiplier, multiplier)
                item["status"] = "<{:g}MDL".format(multiplier) if measured < mdl * multiplier else "空白超出管制"
            else:
                item["status"] = "未設定 MDL 或空白倍率"
        else:
            original = row["original"]
            if original is None:
                item["status"] = "找不到前置原樣"
                continue
            item["original"] = original["sample_id"]
            base = original["sample_concentration"]
            if role == "DUP":
                mean = (base + measured) / 2
                if mean <= 0:
                    item["status"] = "平均濃度須大於零"
                    continue
                item["metric"] = 100 * abs(base - measured) / mean
                low, high = 0, number(control, "DC_UCL")
            else:
                if target is None or target <= 0:
                    item["status"] = "未設定添加濃度"
                    continue
                item["target"] = target
                item["metric"] = 100 * (measured - max(base, 0)) / target
                low, high = (number(control, key) for key in ("SPIKE_LCL", "SPIKE_UCL"))
            if str(control.get("CONFIRMED") or "").strip() == "1" and low is not None and high is not None and low <= high:
                item["criteria"] = "{:g}～{:g}%".format(low, high)
                item["status"] = "合格" if low <= item["metric"] <= high else "超限"
            else:
                item["status"] = "未取得已確認的判定標準"
    source = {r["source_line"]: r for r in rows}
    for item in checks:
        row = source[item["source_line"]]
        item["sample_id"] = row.get("raw_sample_id", row["sample_id"])
        item["original_value"] = row["original"]["sample_concentration"] if row.get("original") else None
        prefix = "QC" if item["role"] == "QC" else "SPIKE" if item["role"] in {"MS", "MSD"} else "DC" if item["role"] == "DUP" else ""
        item["warning_low"] = number(control, prefix + "_LWL") if prefix else None
        item["warning_high"] = number(control, prefix + "_UWL") if prefix else None
        item["control_high"] = number(control, prefix + "_UCL") if prefix else None
        if item["status"] == "合格" and item["metric"] is not None:
            low, high = item["warning_low"], item["warning_high"]
            if (low is not None and item["metric"] < low) or (high is not None and item["metric"] > high):
                item["status"] = "警告"
    return checks


def recalculate(result, values, action):
    updated = deepcopy(result)
    def number(key, default, positive=False):
        value = float(values.get(key, default))
        if not math.isfinite(value) or (positive and value <= 0):
            raise ValueError("請輸入有效數字；稀釋倍數須大於零。")
        return value
    if action.startswith("move_"):
        parts = action.split("_")
        if len(parts) != 3 or parts[1] not in {"up", "down"}:
            raise ValueError("無效的順序操作。")
        rows = updated["rows"]
        index = next((i for i,r in enumerate(rows) if str(r["source_line"]) == parts[2]), None)
        if index is None:
            raise ValueError("找不到調整的樣品。")
        other = index + (-1 if parts[1] == "up" else 1)
        for row in rows:
            row["dilution"] = number("d_" + str(row["source_line"]), row["dilution"], True)
        if 0 <= other < len(rows):
            rows[index], rows[other] = rows[other], rows[index]
        action = "samples"
    if action == "curve":
        points = updated["standards"]
        x = [r["instrument_conc"] for r in points]
        y = [number("std_" + str(i), r["absorbance"]) for i,r in enumerate(points)]
        dx = [v - math.fsum(x)/len(x) for v in x]
        dy = [v - math.fsum(y)/len(y) for v in y]
        xx, yy, xy = (math.fsum(seq) for seq in
                      ([v*v for v in dx], [v*v for v in dy], [a*b for a,b in zip(dx,dy)]))
        if xx <= 0 or yy <= 0 or xy <= 0:
            raise ValueError("檢量線斜率須大於零。")
        a = xy / xx
        updated["calibration"] = dict(slope=a, intercept=(math.fsum(y)-a*math.fsum(x))/len(x), r=xy/math.sqrt(xx*yy))
        for row, val in zip(points,y):
            row.update(absorbance=val, absorbance_text=str(val))
    elif action != "samples":
        raise ValueError("未知的更新操作。")
    curve = updated["calibration"]
    for row in updated["rows"]:
        if action == "samples":
            row["dilution"] = number("d_" + str(row["source_line"]), row["dilution"], True)
        measured = (row["net_absorbance"] - curve["intercept"]) / curve["slope"]
        concentration = measured * row["dilution"]
        if not math.isfinite(concentration):
            raise ValueError("濃度超出可計算範圍。")
        row.update(equivalent_concentration=measured, sample_concentration=concentration)
    return updated


w433_import_bp = Blueprint("w433_import_bp", __name__)


@w433_import_bp.route("/analysis/w433/import", methods=["GET", "POST"])
@login_required
def import_w433():
    return render_w433_import(session.get("basic_info_form") or {})


def render_w433_import(form):
    user = get_current_user() or {}
    owner = str(user.get("user_id") or "").strip()
    if not owner:
        return "請先登入。", 403
    token = session.setdefault("w433_import_csrf", secrets.token_urlsafe(32))
    result, error, status, b = None, None, 200, None
    state, notice, pfm, checks, method, setting_message = "", "", [], [], {}, ""
    serializer = URLSafeTimedSerializer(current_app.secret_key, salt="w433-actions")
    action = request.form.get("edit_action") if request.method == "POST" else ""
    try:
        if request.method == "POST" and not hmac.compare_digest(
                request.form.get("csrf_token","").encode(),token.encode()):
            raise PermissionError("頁面已失效，請重新開啟。")
        if request.method == "GET" and request.args.get("work_id"):
            with SessionLocal() as db:
                b = load_bundle(db,request.args["work_id"],owner)
            form = b["form_data"]
            session["basic_info_form"] = form
            notice = "已載入暫存分析資料。" if b["work_status"]=="EDITING" else "已儲存分析紀錄並送審。"
        elif request.method == "POST" and action:
            payload = serializer.loads(request.form.get("edit_state",""),max_age=7200)
            if payload.get("owner")!=owner or payload.get("csrf")!=token:
                raise PermissionError("目前登入者與工作不符。")
            b = payload["bundle"]
            if b["form_data"] != form:
                raise ValueError("基本資料已變更，請從暫存清單重新載入工作。")
            # Submitted pages can only export persisted snapshots.
            if b["revision"] is not None:
                with SessionLocal() as db:
                    stored = load_bundle(db,b["work_id"],owner)
                if stored["revision"] != b["revision"]:
                    raise DraftConflictError("此頁面不是最新版本，請重新載入工作。")
                if stored["work_status"]!="EDITING":
                    if action not in {"pdf","excel"}:
                        raise ValueError("此工作已送審，目前不可修改。")
                    b=stored
            if b["work_status"] != "EDITING":
                pass
            elif action in {"samples","draft","submit","pdf","excel"} or action.startswith("move_"):
                b["state"]["result"] = clean_result(recalculate(b["state"]["result"],
                    request.form,action if action.startswith("move_") else "samples"))
            elif action=="curve":
                b["state"]["result"] = clean_result(recalculate(b["state"]["result"],request.form,"curve"))
            else:
                raise ValueError("未知的操作。")
        elif request.method == "POST":
            if str(form.get("method_code") or "").upper()!="W433" or not form.get("instrument_id"):
                raise ValueError("請先完成 W433 基本資料。")
            uploads=[f for f in request.files.getlist("uv_files") if f.filename]
            if len(uploads) not in (2,3):
                raise ValueError("請選取檢量線與樣品 TXT，可另選 PFM TXT。")
            result=preview_uploads(uploads)
            loader=current_app.extensions["phyon_load_basic_info_data"]
            control,method,setting_message=loader(form)
            if setting_message or not control or not method:
                raise ValueError(setting_message or "尚未取得方法或年度管制設定。")
            report,report_error=load_report_setting(method)
            if report_error: raise ValueError(report_error)
            b=new_bundle(result,form,control,method,report)
            notice="已匯入並計算，尚未暫存。"
        if b:
            result=b["state"]["result"]
            method=b["method_data"]
            assign_batches(result["rows"])
            checks=build_qaqc_preview(result["rows"],method,b["control_data"])
            if result.get("pfm_rows"):
                from services.performance_query_service import PerformanceControlQueryError, find_active_performance_control
                def lookup(**kwargs):
                    try:return find_active_performance_control(**kwargs)
                    except PerformanceControlQueryError as exc:raise ValueError(str(exc)) from exc
                pfm=evaluate_pfm(result["pfm_rows"],form,lookup)
            b["state"].update(result=clean_result(result),checks=checks,pfm=pfm)
            if action in {"draft","submit"}:
                with SessionLocal() as db:
                    try:
                        pending = deepcopy(b)
                        if action=="submit":pending=submit_bundle(db,user,pending,checks)
                        else:pending=save_bundle(db,owner,pending)
                        db.commit()
                        b=pending
                    except Exception:
                        db.rollback()
                        raise
                return redirect(url_for("w433_import_bp.import_w433",work_id=b["work_id"],saved="1"))
            if action in {"pdf","excel"}:
                from services.w433_export_service import build_pdf,build_excel
                if action=="pdf":
                    output=build_pdf(b,user);mime="application/pdf";name="W433_Analysis_Record.pdf"
                else:
                    template=os.path.join(current_app.root_path,"resources","lims","lims匯入表格.xlsx")
                    output=build_excel(b,user,template);mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";name="W433_LIMS_Import.xlsx"
                return send_file(output,mimetype=mime,as_attachment=True,download_name=name)
            state=serializer.dumps(dict(owner=owner,csrf=token,bundle=b))
            if request.args.get("saved")=="1":
                notice="已暫存分析資料。" if b["work_status"]=="EDITING" else "已儲存分析紀錄並送審。"
        with SessionLocal() as db:
            drafts=list_drafts(db,owner)
    except (BadData,ValueError,PermissionError,DraftConflictError) as exc:
        error,status=str(exc),400
        drafts=[]
        if b:
            result=b["state"]["result"]
            method=b["method_data"]
            assign_batches(result["rows"])
            state=serializer.dumps(dict(owner=owner,csrf=token,bundle=b))
    submitted=bool(b and b["work_status"]!="EDITING")
    return render_template("methods/w433_import.html",form=form,result=result,pfm=pfm,checks=checks,
        setting_message=setting_message,edit_state=state,method=method,error=error,csrf_token=token,
        notice=notice,drafts=drafts,submitted=submitted,
        is_saved=bool(b and b["revision"] is not None and request.method=="GET" and not error)),status
