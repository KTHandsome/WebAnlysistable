"""First-stage E202/E230 entry, server-side calculation and repository drafts."""
from flask import Blueprint, current_app, render_template, request, session, jsonify, url_for, redirect
from auth_session import login_required, get_current_user
from services.membrane_setting_service import settings, entry_dates
from services.membrane_calculation_service import calculate_sample
from services.membrane_validation_service import validate_times

bp = Blueprint('membrane_bp', __name__)


def validate_data(data, method):
    if not isinstance(data, dict) or not isinstance(data.get('samples'), list) or len(data['samples']) > 500:
        raise ValueError('樣品資料格式錯誤。')
    seen = set()
    for row in data['samples']:
        if not isinstance(row, dict):
            raise ValueError('樣品格式錯誤。')
        sid = row.get('sid')
        name = row.get('number')
        if not isinstance(sid, str) or not sid or sid in seen or not isinstance(name, str) or len(name) > 64:
            raise ValueError('樣品編號或識別碼不符。')
        seen.add(sid)
        for key in ('time','inspection'):
            if not isinstance(row.get(key,''),str) or len(row.get(key,'')) > 16:
                raise ValueError('時間格式不符。')
        for key in ('sampled_at','received_at'):
            if key in row and (not isinstance(row[key],str) or len(row[key])>19):
                raise ValueError('樣品日期時間格式不符。')
        lines = row.get('lines')
        if not isinstance(lines,list) or not 1 <= len(lines) <= (1 if method == 'E230' else 7):
            raise ValueError('稀釋列數不符。')
        for line in lines:
            if not isinstance(line,dict) or any(not isinstance(line.get(k),str) or len(line[k]) > 12 for k in ('factor','x','y')):
                raise ValueError('稀釋資料格式不符。')
    batches = data.get('batches')
    if not isinstance(batches,list) or len(batches) != (len(data['samples'])+9)//10:
        raise ValueError('批次資料不符。')
    for batch in batches:
        if not isinstance(batch,dict) or any(not isinstance(batch.get(k),str) or len(batch[k]) > 256 for k in ('medium','temperature','sampling_date','received_at','start','end')):
            raise ValueError('批次欄位格式錯誤。')
        blank = batch.get('blank')
        if not isinstance(blank,dict) or not isinstance(blank.get('lines'),list) or len(blank['lines']) != 1:
            raise ValueError('實驗室空白格式錯誤。')
        for line in blank['lines']:
            if not isinstance(line,dict) or any(not isinstance(line.get(k),str) or len(line[k]) > 12 for k in ('factor','x','y')):
                raise ValueError('實驗室空白數據格式錯誤。')


@bp.route('/analysis/membrane/manual', methods=['GET','POST'])
@login_required
def entry():
    import secrets
    from uuid import uuid4
    from database import SessionLocal
    from analysis.analysis_work_identity import AnalysisWorkIdentity
    from analysis.analysis_work_draft_repository import AnalysisWorkDraftRepository, DraftConflictError
    from services.report_setting_service import load_report_setting
    from services.membrane_samples_service import load_page
    user = get_current_user() or {}
    owner = str(user.get('user_id') or '').strip()
    if not owner:
        return '無法取得登入人員。',403
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if request.method == 'POST':
        if not isinstance(payload,dict) or len(request.get_data(cache=True)) > 512000:
            return jsonify(error='送出資料格式錯誤或過大。'),400
        token = session.get('membrane_csrf','')
        if not token or not secrets.compare_digest(token,request.headers.get('X-Membrane-CSRF','')):
            return jsonify(error='頁面已失效，請重新開啟。'),403
    else:
        session.setdefault('membrane_csrf',secrets.token_urlsafe(32))
    work_id = payload.get('work_id') if request.method == 'POST' else request.args.get('draft')
    method = payload.get('method') if request.method == 'POST' else request.args.get('method')
    form = session.get('basic_info_form') or {}
    method = str(method or form.get('method_code','')).upper()
    if method not in {'E202','E230'}:
        return '請先選擇E202或E230。',400
    db = SessionLocal()
    try:
        repo = AnalysisWorkDraftRepository(db)
        if work_id:
            from models import AnalysisWorkDraft
            from analysis.analysis_work_access import resolve_work_owner
            draft_row = db.query(AnalysisWorkDraft).filter_by(work_id=work_id).first()
            if draft_row is None:
                raise ValueError('查無此暫存。')
            owner = resolve_work_owner(db,draft_row,owner,method)
        saved = repo.load_draft(work_id,owner,method) if work_id else None
        if saved:
            if saved['work_status'] == 'SUBMITTED' and saved.get('formal_analysis_id'):
                if request.method == 'GET':
                    return redirect(url_for('analysis_record_bp.analysis_record_detail',analysis_id=saved['formal_analysis_id']))
                raise ValueError('此工作已送審，請至正式紀錄查看。')
            if saved['work_status'] != 'EDITING' or saved['state'].get('membrane_format') != 1:
                raise ValueError('此暫存目前無法編輯。')
            form = saved['form_data']
            item,control,report = saved['method_data'],saved['control_data'],saved['report_data']
        else:
            item,control = settings(current_app.root_path,form)
            entry_dates(form)
            report,error = load_report_setting(item)
            if error or not report:
                raise ValueError(error or '查無報表設定。')
        from services.membrane_dates_service import effective_control,normalize_data
        control=effective_control(control)
        if saved:
            saved=dict(saved,state=dict(saved['state'],data=normalize_data(saved['state']['data'])),control_data=control)
        if str(item.get('METHOD_CODE','')).upper() != method:
            raise ValueError('方法與暫存不符。')
        if request.method == 'POST':
            data = payload.get('data')
            validate_data(data,method)
            data=normalize_data(data)
            action = payload.get('action')
            if action == 'calculate':
                results=[]
                calculation_rows = list(data['samples']) + [dict(sid='BLANK-'+str(i), lines=b['blank']['lines']) for i,b in enumerate(data['batches'])]
                for row in calculation_rows:
                    try:
                        results.append(dict(sid=row['sid'],result=calculate_sample(method,row['lines'],control['DC_UCL'])))
                    except ValueError as exc:
                        results.append(dict(sid=row['sid'],error=str(exc)))
                return jsonify(results=results,time_checks=validate_times(data,form))
            if action == 'export_lims':
                from types import SimpleNamespace
                from pathlib import Path
                from flask import send_file
                from services.membrane_formal_service import formal_state
                from services.membrane_lims_service import build_membrane_lims
                preview = formal_state(data,method,control)
                export_record=SimpleNamespace(method_code=method,exam_no=item['EXAMNO'],
                    analysis_start_date=form['analysis_start_date'],method_name=control['EM_NO'],
                    analyst_employee_id=str(user.get('employee_id') or ''),analyst_name=str(user.get('employee_name') or ''))
                try:
                    output=build_membrane_lims(export_record,preview,Path(current_app.root_path)/'resources'/'lims'/'lims匯入表格.xlsx')
                except FileNotFoundError:
                    return jsonify(error='找不到LIMS匯入Excel範本。'),404
                return send_file(output,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,download_name=method+'_LIMS_Import.xlsx',max_age=0)
            if action == 'export_pdf':
                from services.membrane_formal_service import formal_state
                from services.membrane_pdf_service import build_membrane_pdf
                from flask import send_file
                preview = formal_state(data,method,control)
                header = dict(report,_DC_UCL=control['DC_UCL'])
                pdf = build_membrane_pdf(preview['membrane_batches'],header,method,control['EM_NO'],
                    str(user.get('employee_name') or ''),preview=True)
                return send_file(pdf,mimetype='application/pdf',as_attachment=True,
                    download_name=method+'_Preview.pdf',max_age=0)
            if action not in {'draft','submit'}:
                raise ValueError('不支援此作業。')
            linked_id = saved.get('formal_analysis_id') if saved else None
            if linked_id:
                from models import AnalysisRecord
                record = db.query(AnalysisRecord).filter_by(analysis_id=linked_id).first()
                if not record or record.status != 'REJECTED' or str(record.analyst_user_id or '').strip() != owner or str(record.method_code or '').upper() != method:
                    raise ValueError('關聯正式紀錄目前不可修正。')
            from services.membrane_formal_service import formal_state
            state = formal_state(data,method,control,linked_id) if action == 'submit' else dict(membrane_format=1,data=data)
            if linked_id:
                state['formal_analysis_id'] = linked_id
            revision = saved['revision'] if saved else 0
            if type(payload.get('revision')) is not int or payload.get('revision') != revision:
                raise DraftConflictError('Stale revision')
            if not saved:
                work_id = str(uuid4())
                repo.create_draft(AnalysisWorkIdentity(work_id,owner,method),{})
            revision=repo.save_work_bundle(work_id,owner,method,revision,state=state,
                form_data=form,control_data=control,method_data={k:v for k,v in item.items() if k!='control'},report_data=report)
            if action == 'submit':
                from services.analysis_record_service import save_analysis_record
                from models import AnalysisReviewHistory
                response = save_analysis_record(form,control,{k:v for k,v in item.items() if k!='control'},report,state,user,
                    db=db,strict_work_identity=True)
                aid = response['analysis_id']
                if not linked_id:
                    db.add(AnalysisReviewHistory(analysis_id=aid,action='SUBMIT',from_status='DRAFT',to_status='UNDER_REVIEW',
                        reviewer_user_id=str(user.get('user_id') or ''),reviewer_employee_id=str(user.get('employee_id') or ''),
                        reviewer_name=str(user.get('employee_name') or ''),comment=''))
                revision = repo.save_work_bundle(work_id,owner,method,revision,state=dict(state,formal_analysis_id=aid))
                revision = repo.submit_draft(work_id,owner,method,revision,aid)
                db.commit()
                return jsonify(formal=True,work_id=work_id,revision=revision,url=url_for('analysis_record_bp.analysis_record_detail',analysis_id=aid))
            db.commit()
            return jsonify(work_id=work_id,revision=revision,url=url_for('membrane_bp.entry',draft=work_id,method=method),time_checks=validate_times(data,form))
        lookup = load_page(item,form,user,request.args,current_app.logger)
        return render_template('methods/membrane_entry.html',form=form,item=item,control=control,report=report,
            lookup=lookup,draft=saved,csrf=session['membrane_csrf'],method=method,active_page='analysis_basic')
    except DraftConflictError:
        db.rollback()
        return jsonify(error='暫存已有新版本，請重新開啟再修改。'),409
    except (ValueError,PermissionError) as exc:
        db.rollback()
        return (jsonify(error=str(exc)),400) if request.method=='POST' else (str(exc),400)
    except Exception:
        db.rollback()
        current_app.logger.exception('Membrane draft operation failed')
        return (jsonify(error='作業失敗，請保留頁面並查看伺服器紀錄。'),500) if request.method=='POST' else ('無法開啟濾膜法頁面。',500)
    finally:
        db.close()


@bp.route('/analysis/membrane/records/<analysis_id>/<action>', methods=['POST'])
@login_required
def review_record(analysis_id, action):
    from database import SessionLocal
    from services.membrane_record_service import review
    db = SessionLocal()
    try:
        return review(db,analysis_id,action)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
