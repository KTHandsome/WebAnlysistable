"""Configure all ICP batches and channels in one caller-visible save."""
import json
from copy import deepcopy
from datetime import datetime
from sqlalchemy import update
from database import SessionLocal
from models import IcpImportWorkState
from analysis.icp_data_view import build_icp_data_view
from services.icp_batch_category_service import build_category_view, build_batches
from services.icp_performance_service import work_token, IcpPfmConflictError


def build_setup_view(work):
    if not work or not (work.get("parsed_data") or {}).get("rows"):
        return None
    form = work.get("form_data") or {}
    channels = build_icp_data_view(work, [], None, include_excluded=True)
    views = [{"key": c["key"], "label": c["element"] + c["wavelength"] + "nm",
              "view": build_category_view(work, form, c, include_excluded=True)} for c in channels]
    batches, _, warnings = build_batches(work["parsed_data"]["rows"])
    saved = work.get("batch_categories") or {}
    for batch in batches:
        stored = saved.get(batch["id"]) or {}
        batch["category"] = "__EXCLUDE__" if stored.get("is_excluded") is True else stored.get("category", "")
        batch["channels"] = []
        for channel in views:
            item = next(b for b in channel["view"]["batches"] if b["id"] == batch["id"])
            batch["channels"].append({"key": channel["key"], "label": channel["label"],
                                      "exam_no": item["exam_no"], "ready": item["ready"],
                                      "setting": item["setting"], "is_excluded": item["is_excluded"]})
    catalogs = {c["key"]: c["view"]["catalog"] for c in views}
    categories = sorted({cat for catalog in catalogs.values() for cat in catalog})
    return {"batches": batches, "catalogs": catalogs, "categories": categories,
            "warnings": warnings, "settings_token": work_token(catalogs),
            "work_token": work_token(work), "work_key": work.get("work_key", ""),
            "ready": bool(batches and views) and all(c["ready"] for b in batches for c in b["channels"])}


def validate_setup(view, submitted):
    if not view or not isinstance(submitted, list) or not view["batches"]:
        raise ValueError("尚未取得批次設定。")
    expected = {b["id"] for b in view["batches"]}
    if (any(not isinstance(b, dict) for b in submitted) or
            len(submitted) != len(expected) or
            {b.get("batch_id") for b in submitted} != expected):
        raise ValueError("請完整提交全部批次，且不可重複。")
    output = {}
    for batch in submitted:
        category = batch.get("category")
        selections = batch.get("channels")
        if not isinstance(category, str) or not isinstance(selections, dict) or set(selections) != set(view["catalogs"]):
            raise ValueError("批次金屬清單不完整。")
        if category == "__EXCLUDE__":
            output[batch["batch_id"]] = {"category": "__EXCLUDE__", "is_excluded": True,
                "channels": {key: {"is_excluded": True, "exam_no": "", "settings_token": ""}
                             for key in view["catalogs"]}}
            continue
        if category not in view["categories"]:
            raise ValueError("請選擇有效的批次類別。")
        channels = {}
        for key, exam in selections.items():
            if exam == "__EXCLUDE__":
                channels[key] = {"is_excluded": True, "exam_no": "", "settings_token": ""}
                continue
            setting = next((s for s in view["catalogs"][key].get(category, [])
                            if s["exam_no"] == exam and not s["error"]), None)
            if setting is None:
                raise ValueError("BATCH " + batch["batch_id"] + " " + key + "：請選擇適用檢測代碼。")
            channels[key] = {"is_excluded": False, "exam_no": exam, "settings_token": work_token(setting),
                             "control_data": deepcopy(setting["control"]),
                             "method_data": deepcopy(setting["method"])}
        output[batch["batch_id"]] = {"category": category, "is_excluded": False, "channels": channels}
    return output


def save_setup(key, expected, settings_token, submitted, actor):
    user_id = str(actor.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("尚未取得登入操作者。")
    db = SessionLocal()
    try:
        row = db.query(IcpImportWorkState).filter(IcpImportWorkState.work_key == key).first()
        if row is None:
            raise IcpPfmConflictError("工作已不存在。")
        original = row.state_json
        work = json.loads(original)
        if work_token(work) != expected:
            raise IcpPfmConflictError("工作已更新，請重新載入後再設定。")
        view = build_setup_view(work)
        if not view or view["settings_token"] != settings_token:
            raise IcpPfmConflictError("方法或管制設定已更新，請重新載入。")
        saved = validate_setup(view, submitted)
        for entry in saved.values():
            entry.update(updated_by=user_id, updated_at_utc=datetime.utcnow().isoformat(timespec="seconds"))
        previous = work.get("batch_categories") or {}
        changed = set()
        for batch_id, entry in saved.items():
            old = previous.get(batch_id) or {}
            for channel_key, selection in entry["channels"].items():
                old_selection = (old.get("channels") or {}).get(channel_key) or {}
                fields = ("exam_no", "settings_token")
                if (old.get("category") != entry["category"] or
                        bool(old_selection.get("is_excluded")) != selection.get("is_excluded", False) or
                        any(old_selection.get(f, "") != selection.get(f, "") for f in fields)):
                    changed.add((batch_id, channel_key))
        manual = work.get("manual_adoptions") or {}
        for adoption_key, adoption in list(manual.items()):
            if isinstance(adoption, dict) and (adoption.get("batch_id"), adoption.get("channel_key")) in changed:
                work.setdefault("manual_adoption_history", []).append({
                    "previous": deepcopy(adoption), "current": None,
                    "action": "BATCH_SETTING_CHANGED", "actor_user_id": user_id,
                    "updated_at_utc": datetime.utcnow().isoformat(timespec="microseconds")})
                del manual[adoption_key]
        work["batch_categories"] = saved
        result = db.execute(update(IcpImportWorkState).where(
            IcpImportWorkState.work_key == key, IcpImportWorkState.state_json == original,
        ).values(state_json=json.dumps(work, ensure_ascii=False)))
        if result.rowcount != 1:
            raise IcpPfmConflictError("工作已更新，請重新載入。")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
