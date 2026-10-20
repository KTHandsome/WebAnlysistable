"""Request-scoped W434 draft bridge. Legacy requests keep their existing path."""
import os
from copy import deepcopy
from uuid import UUID

from flask import abort, g, has_request_context, redirect, request, session, url_for

from auth_session import get_current_user
from database import SessionLocal
from models import AnalysisWorkDraft, AnalysisRecord
from analysis.analysis_work_access import resolve_work_owner, add_work_actor_history
from analysis.analysis_work_identity import create_work_identity
from analysis.analysis_work_draft_repository import (
    AnalysisWorkDraftRepository, DraftConflictError,
)
from analysis.analysis_state import (
    load_analysis_state as legacy_load_state,
    save_analysis_state as legacy_save_state,
)
from analysis.analysis_route_helpers import get_analysis_state_key
from services.basic_info_service import load_basic_info_data
from services.method_control_service import load_control_and_method_data as legacy_control
from services.report_setting_service import load_report_setting as legacy_report
from services.analysis_work_submission_service import submit_analysis_work


ENDPOINTS = {
    "analysis_w43401", "update_w434_calibration", "update_analysis_samples",
    "save_analysis_record_route", "export_w434_pdf", "export_w434_lims",
    "confirm_w434_wavelength", "w434_wavelength_bp.confirm_w434_wavelength",
    "update_batch_remarks", "batch_remarks_bp.update_batch_remarks",
}


def active_work():
    return getattr(g, "analysis_work", None) if has_request_context() else None


def work_form_data(default=None):
    work = active_work()
    return work["bundle"]["form_data"] if work else session.get("basic_info_form", default)


def work_formal_id(default=""):
    work = active_work()
    return (work["bundle"]["formal_analysis_id"] or "") if work else default


def load_analysis_state(key):
    work = active_work()
    if not work:
        return legacy_load_state(key)
    if key != get_analysis_state_key(work["method"]):
        abort(400, description="分析方法與目前工作不一致。")
    state = deepcopy(work["bundle"]["state"])
    formal_id = work["bundle"]["formal_analysis_id"]
    if formal_id:
        state["formal_analysis_id"] = formal_id
    return state


def save_analysis_state(key, state):
    work = active_work()
    if not work:
        return legacy_save_state(key, state)
    if key != get_analysis_state_key(work["method"]):
        abort(400, description="分析方法與目前工作不一致。")
    bundle = work["bundle"]
    if bundle["work_status"] != "EDITING":
        abort(409, description="此工作已送出待審核，目前不可修改。")
    # The original parser output is a separate immutable copy.
    state = deepcopy(state)
    if "parsed_data" not in state and "parsed_data" in bundle["state"]:
        state["parsed_data"] = deepcopy(bundle["state"]["parsed_data"])
    if getattr(g, "work_original_parsed_data", None) is not None:
        state["parsed_data"] = deepcopy(g.work_original_parsed_data)
    next_revision = work["repo"].save_work_bundle(
        bundle["work_id"], work["user_id"], work["method"],
        bundle["revision"], state=state,
        form_data=deepcopy(bundle["form_data"]),
    )
    if bundle["formal_analysis_id"]:
        add_work_actor_history(
            work["db"], bundle["formal_analysis_id"], "EDIT_DRAFT",
            bundle["work_id"], next_revision, "REJECTED",
        )
    bundle["state"] = state
    bundle["revision"] = next_revision
    work["dirty"] = True


def load_control_and_method_data(form_data):
    work = active_work()
    if work:
        return (deepcopy(work["bundle"]["control_data"]),
                deepcopy(work["bundle"]["method_data"]), None)
    return legacy_control(form_data)


def load_report_setting(method_data):
    work = active_work()
    if work:
        return deepcopy(work["bundle"]["report_data"]), None
    return legacy_report(method_data)


def capture_original_rows(rows):
    if active_work():
        g.work_original_parsed_data = deepcopy(rows)
    return rows


def submit_current_work():
    work = active_work()
    try:
        result = submit_analysis_work(
            db=work["db"], work_id=work["bundle"]["work_id"],
            method_code=work["method"],
            expected_revision=work["bundle"]["revision"],
            current_user=get_current_user(),
        )
        work["bundle"]["revision"] = result["revision"]
        work["dirty"] = True
        return redirect(url_for("analysis_w43401", saved="1", formal_saved="1"))
    except DraftConflictError as exc:
        work["db"].rollback()
        abort(409, description=str(exc))
    except PermissionError as exc:
        work["db"].rollback()
        abort(403, description=str(exc))
    except ValueError as exc:
        work["db"].rollback()
        abort(400, description=str(exc))
    except Exception:
        work["db"].rollback()
        raise


def install_work_web(app):
    @app.errorhandler(DraftConflictError)
    def work_revision_conflict(error):
        return str(error), 409

    @app.before_request
    def bind_analysis_work():
        if request.endpoint not in ENDPOINTS:
            return None
        ids = request.args.getlist("work_id") + request.form.getlist("work_id")
        if not ids:
            # Entering W434 from Basic Info starts a new independent work.
            # saved=1 without an ID remains the legacy resume path.
            form = session.get("basic_info_form") or {}
            if (os.getenv("PHYON_ENABLE_STAGE35G_WEB", "0") == "1"
                    and request.endpoint == "analysis_w43401"
                    and request.method == "GET"
                    and request.args.get("saved") != "1"
                    and str(form.get("method_code") or "").strip().upper() == "W434"):
                user = get_current_user() or {}
                user_id = str(user.get("user_id") or "").strip()
                if not user_id:
                    return None  # The existing login decorator handles sign-in.
                control, method, error = load_basic_info_data(form)
                if error or not control or not method:
                    abort(400, description=str(error or "分析設定不完整，請返回基本資料確認。"))
                report, error = legacy_report(method)
                if error:
                    abort(400, description=str(error))
                db = SessionLocal()
                try:
                    repo = AnalysisWorkDraftRepository(db)
                    identity = create_work_identity(user_id, "W434")
                    repo.create_draft(identity)
                    repo.save_work_bundle(
                        identity.work_id, user_id, "W434", 0,
                        state={}, form_data=deepcopy(form),
                        control_data=control, method_data=method,
                        report_data=report or {},
                    )
                    db.commit()
                    return redirect(url_for("analysis_w43401", work_id=identity.work_id))
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
            return None
        if any(not value for value in ids) or len(set(ids)) != 1:
            abort(400, description="工作識別資料不一致，請重新開啟工作頁面。")
        try:
            work_id = str(UUID(ids[0]))
        except (ValueError, TypeError, AttributeError):
            abort(400, description="工作識別資料格式不正確。")
        user = get_current_user() or {}
        user_id = str(user.get("user_id") or "").strip()
        if not user_id:
            abort(401)
        db = SessionLocal()
        # Register immediately, so teardown closes the session even on rejection.
        work = {"db": db, "dirty": False}
        g.analysis_work = work
        row = db.query(AnalysisWorkDraft).filter(
            AnalysisWorkDraft.work_id == work_id
        ).first()
        if row is None:
            abort(404, description="找不到指定的分析工作。")
        if row.method_code != "W434":
            abort(400, description="此工作不適用目前的分析頁面。")
        repo = AnalysisWorkDraftRepository(db)
        try:
            owner_id = resolve_work_owner(db, row, user_id, "W434")
            bundle = repo.load_draft(work_id, owner_id, "W434")
        except PermissionError:
            abort(403, description="您沒有權限存取此分析工作。")
        except ValueError as exc:
            abort(400, description=str(exc))
        work.update(repo=repo, bundle=bundle, method="W434", user_id=owner_id,
                    actor_user_id=user_id)
        if request.method == "POST":
            if bundle["formal_analysis_id"]:
                linked_record = db.query(AnalysisRecord).filter(
                    AnalysisRecord.analysis_id == bundle["formal_analysis_id"]
                ).first()
                if linked_record is None or linked_record.status != "REJECTED":
                    abort(409, description="此工作已送出待審核，目前不可修改。")
            revisions = (request.args.getlist("expected_revision")
                         + request.form.getlist("expected_revision"))
            if (not revisions or len(set(revisions)) != 1
                    or not revisions[0].isascii() or not revisions[0].isdigit()):
                abort(400, description="缺少有效的工作版本，請重新載入頁面。")
            if int(revisions[0]) != bundle["revision"]:
                abort(409, description="此頁面已不是最新版本，請重新載入後再操作。")
            if bundle["work_status"] != "EDITING":
                abort(409, description="此工作已送出待審核，目前不可修改。")
            if request.endpoint == "analysis_w43401" and bundle["state"]:
                abort(409, description="請返回基本資料建立另一筆工作，再匯入新的 PDF。")
        # A plain refresh must show the saved work instead of reinitializing it.
        if (request.method == "GET" and request.endpoint == "analysis_w43401"
                and bundle["state"] and request.args.get("saved") != "1"):
            return redirect(url_for("analysis_w43401", saved="1"))

    @app.url_defaults
    def retain_work_id(endpoint, values):
        work = active_work()
        if work and "bundle" in work and endpoint in ENDPOINTS:
            values.setdefault("work_id", work["bundle"]["work_id"])
            if endpoint not in {"analysis_w43401", "export_w434_pdf", "export_w434_lims"}:
                values.setdefault("expected_revision", work["bundle"]["revision"])

    @app.context_processor
    def expose_work_version():
        work = active_work()
        if work and "bundle" in work:
            return {"analysis_work_id": work["bundle"]["work_id"],
                    "analysis_work_revision": work["bundle"]["revision"],
                    "analysis_work_status": work["bundle"]["work_status"]}
        return {}

    @app.after_request
    def finish_analysis_work(response):
        work = active_work()
        if work:
            if response.status_code < 400 and work["dirty"]:
                work["db"].commit()
            else:
                work["db"].rollback()
        return response

    @app.teardown_request
    def close_analysis_work(error):
        work = active_work()
        if work:
            try:
                work["db"].rollback()
            finally:
                work["db"].close()
