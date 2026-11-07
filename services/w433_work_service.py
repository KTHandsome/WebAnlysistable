"""W433 snapshots and shared formal-record transaction adapter."""
import json
import math
from copy import deepcopy
from uuid import uuid4
from analysis.analysis_work_identity import AnalysisWorkIdentity
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError
from models import AnalysisWorkDraft, AnalysisWorkState, PerformanceMeasurementHistory, PerformanceAnalysisLink
from services.analysis_record_service import save_analysis_record


def clean_result(result):
    result = deepcopy(result)
    for row in result["rows"]:
        row.pop("original", None)
    return result


def new_bundle(result, form, control, method, report):
    return dict(work_id=str(uuid4()), revision=None, formal_analysis_id=None,
                work_status="EDITING", form_data=deepcopy(form), control_data=deepcopy(control),
                method_data=deepcopy(method), report_data=deepcopy(report),
                state=dict(w433_format=1, original=clean_result(result), result=clean_result(result)))


def load_bundle(db, work_id, owner):
    b = AnalysisWorkDraftRepository(db).load_draft(work_id, owner, "W433")
    if b["state"].get("w433_format") != 1:
        raise ValueError("W433 工作快照格式不符。")
    return b


def save_bundle(db, owner, b):
    repo = AnalysisWorkDraftRepository(db)
    if b["revision"] is None:
        repo.create_draft(AnalysisWorkIdentity(b["work_id"], owner, "W433"),
                          {"original":b["state"]["original"]})
        revision = 0
    else:
        old = load_bundle(db, b["work_id"], owner)
        if old["work_status"] != "EDITING" or old["revision"] != b["revision"]:
            raise DraftConflictError("此頁面不是最新版本，請重新載入暫存工作。")
        if old["state"]["original"] != b["state"]["original"]:
            raise ValueError("原始 TXT 不可覆寫。")
        revision = b["revision"]
    b["revision"] = repo.save_work_bundle(b["work_id"], owner, "W433", revision,
        state=b["state"], form_data=b["form_data"], control_data=b["control_data"],
        method_data=b["method_data"], report_data=b["report_data"])
    return b


def list_drafts(db, owner):
    rows = db.query(AnalysisWorkDraft).filter(
        AnalysisWorkDraft.owner_user_id == owner, AnalysisWorkDraft.method_code == "W433",
        AnalysisWorkDraft.work_status == "EDITING").order_by(AnalysisWorkDraft.updated_at.desc()).limit(20).all()
    result = []
    for row in rows:
        form = json.loads(row.form_data_json)
        raw = json.loads(row.state_json).get("original", {})
        names = list(dict.fromkeys(r["source_file"] for r in raw.get("raw_samples", [])))
        result.append(dict(work_id=row.work_id, day=form.get("analysis_start_date",""),
                           label="、".join(names) or "W433 分析資料"))
    return result


def validate(b, checks):
    curve = b["state"]["result"]["calibration"]
    if curve["r"] < .995 or not math.isfinite(curve["r"]):
        raise ValueError("檢量線須符合 r ≥ 0.995。")
    if not any(r["role"] == "SAMPLE" for r in b["state"]["result"]["rows"]):
        raise ValueError("沒有可儲存或匯出的一般樣品。")
    for batch in {r["batch"] for r in b["state"]["result"]["rows"]}:
        roles=[r["role"] for r in checks if r["batch"]==batch]
        required=["BK","QC","CCV"] + (["ICV"] if batch==1 else [])
        for role in required:
            if roles.count(role)!=1:
                raise ValueError("批次 {} 需要一筆 {}，請確認 TXT。".format(batch,role))
    for item in b["state"].get("pfm", []):
        if item["status"] not in {"合格","超限"}:
            raise ValueError("PFM 尚無有效判定，請確認管制設定。")
    unresolved = [r for r in checks if r["status"] not in {"合格","警告","超限","空白超出管制"} and not r["status"].startswith("<")]
    if unresolved:
        raise ValueError("請先完成 QA/QC 設定與配對：" + "、".join(r["role"] for r in unresolved))


def flat_state(b, checks):
    result, method = b["state"]["result"], b["method_data"]
    curve = deepcopy(result["calibration"])
    curve["is_pass"] = curve["passed"] = curve["r"] >= .995
    curve["points"] = [dict(sample_id=r["sample_id"], x=r["instrument_conc"], y=r["absorbance"],
        back_calculated_x=(r["absorbance"]-curve["intercept"])/curve["slope"])
        for r in result["standards"]]
    samples = []
    for row in result["rows"]:
        samples.append(dict(sequence_no=len(samples)+1, display_order=len(samples)+1,
            sample_id=row.get("raw_sample_id",row["sample_id"]), role=row["role"],
            signal=row["absorbance"], sample_volume=method.get("SAMPLE_VOLUME_DEFAULT"),
            final_volume=method.get("FINAL_VOLUME_DEFAULT"), dilution_factor=row["dilution"],
            measured_concentration=row["equivalent_concentration"], calculated_concentration=row["sample_concentration"],
            sample_concentration=row["sample_concentration"], qaqc_concentration=row["sample_concentration"],
            spike_concentration=method.get(("MS" if row["role"]=="MSD" else row["role"])+"_SPIKE_CONC")))
        if row.get("blank"):
            samples.append(dict(sequence_no=len(samples)+1, display_order=len(samples)+1,
                sample_id=row["blank"]["sample_id"], role="SAMPLE_BLANK",signal=row["blank"]["absorbance"],
                remark="配對空白；不計算濃度"))
    batches = []
    for number in sorted({r["batch"] for r in checks}):
        selected = [r for r in checks if r["batch"] == number]
        batch = dict(batch_no=str(number),batch_category=b["form_data"].get("category",""),
                     rows=[],spike_recovery=[],precision=None)
        for r in selected:
            item = dict(role=r["role"],sample_id=r["sample_id"],calculated_concentration=r["measured"],
                spike_concentration=r["target"], result_value=r["metric"], result=r["metric"],
                recovery=r["metric"], relative_error=r["metric"],criteria_text=r["criteria"],
                check_value=r["metric"],control_text=r["criteria"],
                calculation_name="相對誤差" if r["role"] in {"ICV","CCV"} else "回收率",
                status=("超出管制" if r["status"] in {"超限","空白超出管制"} else "合格" if r["status"].startswith("<") else r["status"]), is_pass=r["status"] in {"合格","警告"} or r["status"].startswith("<"))
            if r["role"] == "DUP":
                batch["precision"]=dict(source_name="原樣／DUP",sample_id_a=r["original"],sample_id_b=r["sample_id"],
                    rpd=r["metric"],ucl=r["control_high"],uwl=r["warning_high"],status=item["status"],is_pass=item["is_pass"])
            elif r["role"] in {"MS","MSD"}:
                item.update(original_sample_id=r["original"],original_concentration=r["original_value"],
                            spiked_concentration=r["measured"],recovery_percent=r["metric"],
                            lcl=b["control_data"].get("SPIKE_LCL"),ucl=b["control_data"].get("SPIKE_UCL"),
                            lwl=b["control_data"].get("SPIKE_LWL"),uwl=b["control_data"].get("SPIKE_UWL"))
                batch["spike_recovery"].append(item)
            else:
                batch["rows"].append(item)
        batches.append(batch)
    names = list(dict.fromkeys(r["source_file"] for r in result["raw_samples"]))
    state = dict(calibration_result=curve,calibration_rows=result["standards"],
                 sample_qaqc_rows=samples,qaqc_results=batches,prm_rows=[],prm_results=[],
                 confirmed_wavelength=664,uploaded_filename="、".join(names)[:255])
    if b.get("formal_analysis_id"):
        state["formal_analysis_id"]=b["formal_analysis_id"]
    return state


def submit_bundle(db, user, b, checks):
    validate(b, checks)
    b = save_bundle(db, str(user["user_id"]), b)
    result = save_analysis_record(b["form_data"], b["control_data"], b["method_data"],
        b["report_data"], flat_state(b,checks), user, db=db, strict_work_identity=True)
    aid = result["analysis_id"]
    # Optional PFM history participates in this same transaction.
    from services.performance_history_service import _find_existing_pfm_event, _parse_pfm_datetime
    db.query(PerformanceAnalysisLink).filter(PerformanceAnalysisLink.analysis_id == aid).delete(synchronize_session=False)
    for index,item in enumerate(b["state"].get("pfm",[]),1):
        control=item["control"]
        candidate=dict(instrument_id=control["instrument_id"],method_code="W433",
            monitor_item=control["monitor_item"],performance_type=control["performance_type"],
            sample_id=item["label"],analysis_datetime=_parse_pfm_datetime(item["row"]["measured_at"]),
            measured_value=item["row"]["absorbance"],signal_field="ABSORBANCE",
            control_import_id=control["import_id"],control_id=control["control_id"],
            reference_value=control["reference_value"],lower_limit=control["lower_limit"],
            upper_limit=control["upper_limit"],unit=control["unit"],
            status="PASS" if item["status"]=="合格" else "FAIL")
        event=_find_existing_pfm_event(db,candidate)
        if event is None:
            event=PerformanceMeasurementHistory(**candidate,message="W433 664 nm UV TXT")
            db.add(event);db.flush()
        db.add(PerformanceAnalysisLink(performance_id=event.id,analysis_id=aid,prm_sequence_no=index))
    b["state"]["formal_analysis_id"] = aid
    snapshot = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == aid).one()
    snapshot.state_json = json.dumps(b["state"],ensure_ascii=False)
    # Submission verifies all five draft/snapshot sections in the same transaction.
    b["revision"] = AnalysisWorkDraftRepository(db).save_work_bundle(
        b["work_id"],str(user["user_id"]),"W433",b["revision"],state=b["state"])
    b["revision"] = AnalysisWorkDraftRepository(db).submit_draft(
        b["work_id"],str(user["user_id"]),"W433",b["revision"],aid)
    b.update(formal_analysis_id=aid, work_status="SUBMITTED")
    return b


def record_bundle(db, record):
    snapshot = db.query(AnalysisWorkState).filter(AnalysisWorkState.analysis_id == record.analysis_id).one()
    state = json.loads(snapshot.state_json)
    if state.get("w433_format") != 1:
        raise ValueError("不是 W433 計算快照。")
    return dict(state=state,form_data=json.loads(snapshot.form_data_json),
                control_data=json.loads(snapshot.control_data_json),method_data=json.loads(snapshot.method_data_json),
                report_data=json.loads(snapshot.report_data_json))
