"""Membrane record rendering, guarded review transitions, and correction recovery."""
import json
import secrets
from datetime import datetime
from flask import session, request, render_template, url_for, redirect, abort
from sqlalchemy import update
from auth_session import get_current_user, can_review_analysis
from models import AnalysisRecord, AnalysisWorkState, AnalysisWorkDraft, AnalysisReviewHistory
from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError
from analysis.analysis_work_access import resolve_work_owner, add_work_actor_history

METHODS = {'E202','E230'}


def check_csrf():
    token = session.get('membrane_csrf','')
    if not token or not secrets.compare_digest(token,request.form.get('membrane_csrf','')):
        abort(403, description='頁面已失效，請重新開啟。')


def can_correct(record):
    actor = str((get_current_user() or {}).get('user_id') or '').strip()
    return bool(actor and (actor == str(record.analyst_user_id or '').strip() or can_review_analysis()))


def detail(db, record):
    work = db.query(AnalysisWorkState).filter_by(analysis_id=record.analysis_id).first()
    if not work:
        return '查無濾膜法正式紀錄快照。',404
    state = json.loads(work.state_json)
    if state.get('membrane_format') != 1 or not state.get('membrane_batches'):
        return '正式紀錄快照格式不符。',409
    history = db.query(AnalysisReviewHistory).filter_by(analysis_id=record.analysis_id).order_by(
        AnalysisReviewHistory.created_at.asc(),AnalysisReviewHistory.id.asc()).all()
    session.setdefault('membrane_csrf', secrets.token_urlsafe(32))
    return render_template('methods/membrane_record.html',record=record,batches=state['membrane_batches'],
        can_review=can_review_analysis(),can_correct=can_correct(record),review_history=history,
        csrf=session['membrane_csrf'],active_page='analysis_records')


def review(db, analysis_id, action):
    check_csrf()
    if not can_review_analysis():
        return '您沒有分析紀錄審核權限。',403
    record = db.query(AnalysisRecord).filter_by(analysis_id=analysis_id).first()
    if record is None or str(record.method_code or '').upper() not in METHODS:
        return '查無此濾膜法分析紀錄。',404
    transitions = {'approve':('UNDER_REVIEW','APPROVED','APPROVE'),
                   'reject':('UNDER_REVIEW','REJECTED','REJECT'),
                   'reopen':('APPROVED','REJECTED','REOPEN_AFTER_APPROVAL')}
    if action not in transitions:
        return '不支援此審核動作。',400
    old,new,event = transitions[action]
    comment = request.form.get('review_comment','').strip()
    if action != 'approve' and not comment:
        return '退回修正必須填寫原因。',400
    if record.status != old:
        return '紀錄狀態已變更，請重新開啟。',409
    user = get_current_user() or {}
    actor = str(user.get('user_id') or '').strip()
    if not actor:
        return '無法取得登入人員。',403
    employee = str(user.get('employee_id') or '').strip()
    name = str(user.get('employee_name') or '').strip()
    changed = db.execute(update(AnalysisRecord).where(AnalysisRecord.analysis_id==analysis_id,
        AnalysisRecord.status==old).values(status=new,reviewer_user_id=actor,reviewer_employee_id=employee,
        reviewer_name=name,reviewed_at=datetime.utcnow(),review_comment=comment).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        return '紀錄狀態已變更，請重新開啟。',409
    db.add(AnalysisReviewHistory(analysis_id=analysis_id,action=event,from_status=old,to_status=new,
        reviewer_user_id=actor,reviewer_employee_id=employee,reviewer_name=name,comment=comment))
    db.commit()
    return redirect(url_for('analysis_record_bp.analysis_record_detail',analysis_id=analysis_id))


def resume(db, record):
    check_csrf()
    method = str(record.method_code or '').upper()
    if method not in METHODS or not can_correct(record):
        return '沒有權限續作此紀錄。',403
    if record.status != 'REJECTED':
        return '只有退回修正的紀錄可續作。',409
    drafts = db.query(AnalysisWorkDraft).filter_by(formal_analysis_id=record.analysis_id).limit(2).all()
    if len(drafts) != 1:
        return '找不到唯一的關聯工作，無法續作。',409
    actor = str((get_current_user() or {}).get('user_id') or '').strip()
    try:
        repo = AnalysisWorkDraftRepository(db)
        owner = resolve_work_owner(db,drafts[0],actor,method)
        bundle = repo.load_draft(drafts[0].work_id,owner,method)
        if bundle['work_status'] == 'SUBMITTED':
            revision = repo.resume_draft(bundle['work_id'],owner,method,bundle['revision'])
            add_work_actor_history(db,record.analysis_id,'RESUME_DRAFT',bundle['work_id'],revision,'REJECTED')
            db.commit()
        elif bundle['work_status'] != 'EDITING':
            return '目前工作狀態不可續作。',409
        return redirect(url_for('membrane_bp.entry',draft=bundle['work_id'],method=method))
    except (DraftConflictError,ValueError,PermissionError):
        db.rollback()
        return '無法續作，請重新開啟紀錄後重試。',409
