# -*- coding: utf-8 -*-
"""Phyon Performance CSV/JSONL + database coordinated release.

The caller MUST perform permission checks and full business validation first.
The file and database do not share a transaction: partial results are always
reported as requiring reconciliation, NEVER silently rolled back or retried.
"""

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import func, select

from models import PerformanceImportHistory, InstrumentPerformanceControl
from services.performance_import_service import (
    parse_performance_csv,
    prepare_performance_import,
    activate_pending_performance_import,
)
from services.performance_publish_service import (
    check_performance_publish_history,
    build_performance_publish_record,
    publish_performance_csv,
)


class PerformanceReleaseNeedsReview(RuntimeError):
    """Release may be partially complete; retain evidence and inspect state."""

    def __init__(self, stage, pending_import_id, reason):
        self.stage = stage
        self.pending_import_id = pending_import_id
        super().__init__(
            'Performance 發布於 {} 階段未完成；PENDING import_id={}。'
            '停止後續發布，請先核對 CSV、JSONL、SQLite。原因：{}'.format(
                stage, pending_import_id, reason
            )
        )


def inspect_performance_release_before_publish(
    save_path,
    log_path,
    archive_dir,
    session_factory,
):
    """Determine whether this is a genuine first publication."""

    save_path = Path(save_path)
    log_path = Path(log_path)
    archive_dir = Path(archive_dir)

    with session_factory() as db:
        history_count = db.scalar(
            select(func.count()).select_from(
                PerformanceImportHistory
            )
        )

        detail_count = db.scalar(
            select(func.count()).select_from(
                InstrumentPerformanceControl
            )
        )

    is_first_release = (
        not save_path.exists()
        and not log_path.exists()
        and history_count == 0
        and detail_count == 0
    )

    if is_first_release:
        if (
            Path(str(save_path) + ".publish.lock").exists()
            or (
                archive_dir / ".performance_db_import.lock"
            ).exists()
        ):
            raise ValueError(
                "存在 Performance 未完成作業鎖定檔，"
                "禁止首次發布。"
            )

        return {
            "first_release": True,
            "sha256": None,
            "active_import_id": None,
        }

    result = inspect_performance_release_ready(
        save_path,
        log_path,
        archive_dir,
        session_factory,
    )

    result["first_release"] = False
    return result

def inspect_performance_release_ready(save_path, log_path, archive_dir, session_factory):
    """Read-only consistency check of official CSV, JSONL and ACTIVE DB.

    Also rejects an unresolved PENDING batch. It never changes any file/DB.
    """
    save_path = Path(save_path)
    log_path = Path(log_path)
    archive_dir = Path(archive_dir)

    if not save_path.is_file():
        raise ValueError('找不到 Performance 正式 CSV。')
    if not log_path.is_file():
        raise ValueError('找不到 Performance 發布歷程 JSONL。')
    if Path(str(save_path) + '.publish.lock').exists():
        raise ValueError('存在 Performance CSV 發布鎖定檔，請先人工確認。')
    if (archive_dir / '.performance_db_import.lock').exists():
        raise ValueError('存在 Performance 資料庫匯入鎖定檔，請先人工確認。')

    check_performance_publish_history(str(log_path), str(save_path))
    official_hash = hashlib.sha256(save_path.read_bytes()).hexdigest()

    with session_factory() as db:
        active_batches = db.scalars(select(PerformanceImportHistory).where(
            PerformanceImportHistory.status == 'ACTIVE'
        )).all()
        if len(active_batches) != 1:
            raise ValueError('Performance 資料庫必須恰有一個 ACTIVE 批次。')
        pending_count = db.scalar(select(func.count()).select_from(
            PerformanceImportHistory
        ).where(PerformanceImportHistory.status == 'PENDING'))
        if pending_count:
            raise ValueError('存在未完成 PENDING 批次，禁止開始新發布。')

        active = active_batches[0]
        active_id = active.import_id
        active_hash = str(active.sha256 or '').lower()
        stored_name = str(active.stored_filename or '')
        record_count = active.record_count
        actual_count = db.scalar(select(func.count()).select_from(
            InstrumentPerformanceControl
        ).where(InstrumentPerformanceControl.import_id == active_id))

    if official_hash != active_hash:
        raise ValueError('正式 CSV 與 SQLite ACTIVE 批次 SHA256 不一致，禁止發布。')
    if actual_count != record_count:
        raise ValueError('SQLite ACTIVE 管制明細筆數與匯入歷程不一致。')
    if not stored_name or Path(stored_name).name != stored_name:
        raise ValueError('SQLite ACTIVE 備份檔名無效。')
    archived_file = archive_dir / stored_name
    if not archived_file.is_file():
        raise ValueError('找不到 SQLite ACTIVE 批次的原始 CSV 備份。')
    if hashlib.sha256(archived_file.read_bytes()).hexdigest() != official_hash:
        raise ValueError('SQLite ACTIVE 備份與正式 CSV 不一致。')

    return {
        'ready': True,
        'active_import_id': active_id,
        'record_count': record_count,
        'sha256': official_hash,
    }


def _confirm_published_record(log_path, publish_id, sha256):
    """Confirm matching final PUBLISHED record; never auto-repair JSONL."""
    last_published = None
    with Path(log_path).open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                if record.get('status') == 'PUBLISHED':
                    last_published = record
    if not last_published or last_published.get('publish_id') != publish_id:
        raise RuntimeError('JSONL 最後 PUBLISHED 批次不符')
    if str(last_published.get('sha256', '')).lower() != sha256:
        raise RuntimeError('JSONL PUBLISHED SHA256 不符')


def release_performance_csv_to_database(
    file_bytes,
    original_filename,
    published_by,
    save_path,
    backup_folder,
    log_path,
    archive_dir,
    session_factory,
):
    """Coordinated release, called only AFTER complete web-route validation.

    Preflight -> prepare PENDING -> CSV/JSONL publish -> activate ACTIVE ->
    post-check. In any error after PENDING, it is intentionally retained for
    explicit reconciliation. This is not an ACID transaction across stores.

    NOTE: only cooperating calls to this coordinator are serialized by the
    .performance_release.lock file on this host. Existing legacy publishers
    must remain DISABLED until the web route switches to this coordinator.
    """
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise ValueError('候選 Performance CSV 不可空白。')
    if not str(published_by or '').strip():
        raise ValueError('缺少發布者。')

    save_path = Path(save_path)
    log_path = Path(log_path)
    backup_folder = Path(backup_folder)
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    release_lock = archive_dir / '.performance_release.lock'
    try:
        fd = os.open(str(release_lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError('存在 Performance 整合發布鎖定檔，禁止同時發布或重試。')

    pending = None
    stage = 'PREFLIGHT'
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('RELEASE IN PROGRESS\n')
            f.flush()
            os.fsync(f.fileno())

        before = inspect_performance_release_before_publish(
             save_path,
             log_path,
             archive_dir,
             session_factory,
        )
        # Parser is syntactic only. Validate instrument registry, overlapping
        # effective dates, permissions etc. in app.py BEFORE calling here.
        records = parse_performance_csv(file_bytes)
        control_ids = [r['control_id'] for r in records]
        if any(not x for x in control_ids) or len(control_ids) != len(set(control_ids)):
            raise ValueError('候選 CSV CONTROL_ID 不可空白或重複。')
        candidate_hash = hashlib.sha256(file_bytes).hexdigest()
        if candidate_hash == before['sha256']:
            raise ValueError('候選 CSV 與現行正式 CSV 完全相同，無須重複發布。')
        versions = sorted({r['control_version'] for r in records})
        publish_record = build_performance_publish_record(
            file_bytes=file_bytes,
            published_by=published_by,
            record_count=len(records),
            control_versions=versions,
        )

        stage = 'PREPARE_PENDING'
        pending = prepare_performance_import(
            file_bytes=file_bytes,
            original_filename=original_filename,
            imported_by=published_by,
            archive_dir=archive_dir,
            session_factory=session_factory,
        )
        stage = 'PUBLISH_CSV_JSONL'
        published = publish_performance_csv(
            file_bytes=file_bytes,
            record=publish_record,
            save_path=str(save_path),
            backup_folder=str(backup_folder),
            log_path=str(log_path),
        )
        stage = 'VERIFY_PUBLICATION'
        check_performance_publish_history(str(log_path), str(save_path))
        _confirm_published_record(log_path, published['publish_id'], candidate_hash)
        if hashlib.sha256(save_path.read_bytes()).hexdigest() != candidate_hash:
            raise RuntimeError('正式 CSV SHA256 不符')

        stage = 'ACTIVATE_SQLITE'
        activation = activate_pending_performance_import(
            import_id=pending['import_id'],
            save_path=save_path,
            archive_dir=archive_dir,
            session_factory=session_factory,
        )
        stage = 'VERIFY_FINAL_STATE'
        after = inspect_performance_release_ready(
            save_path, log_path, archive_dir, session_factory
        )
        if (after['active_import_id'] != pending['import_id']
                or after['sha256'] != candidate_hash
                or after['record_count'] != len(records)):
            raise RuntimeError('發布後三方核對結果不一致')

        stage = 'VERIFY_FINAL_STATE_SUCCESS'
        return {
            'status': 'PUBLISHED',
            'publish_id': published['publish_id'],
            'import_id': activation['import_id'],
            'previous_import_id': before['active_import_id'],
            'record_count': len(records),
            'sha256': candidate_hash,
        }
    except Exception as exc:
        if pending is not None:
            # Partial completion or uncertain COMMIT. Do NOT delete PENDING,
            # revert official files or auto-retry. Keep original evidence.
            raise PerformanceReleaseNeedsReview(
                stage, pending['import_id'], str(exc)
            ) from exc
        raise
    finally:
        # Release lock is only cleared if the entire release succeeded OR
        # failed before PENDING existed. Otherwise preserve it for review.
        # A successful return sets stage to VERIFY_FINAL_STATE.
        if pending is None or stage == 'VERIFY_FINAL_STATE_SUCCESS':
            if release_lock.exists():
                release_lock.unlink()


def diagnose_performance_release_state(save_path, log_path, archive_dir, session_factory):
    """Read-only diagnosis; never removes locks, mutates SQLite, or repairs JSONL.

    status: NORMAL / REVIEW_REQUIRED / INDETERMINATE.
    A NORMAL diagnosis is informational, not authorization for a write; the
    coordinator must still run its own guarded preflight before publishing.
    """
    from services.performance_publish_service import inspect_performance_publish_state

    save_path = Path(save_path)
    log_path = Path(log_path)
    archive_dir = Path(archive_dir)
    backup_folder = log_path.parent

    result = {
        'status': 'INDETERMINATE',
        'message': '',
        'issues': [],
        'official': {'exists': False, 'sha256': None},
        'jsonl': {
            'exists': log_path.is_file(), 'status': None,
            'last_published_id': None, 'last_published_sha256': None,
            'pending_publish_id': None, 'message': None,
        },
        'active': [],
        'pending': [],
        'locks': {
            'release': (archive_dir / '.performance_release.lock').exists(),
            'csv_publish': Path(str(save_path) + '.publish.lock').exists(),
            'db_import': (archive_dir / '.performance_db_import.lock').exists(),
        },
        'official_matches_active': None,
        'official_matches_pending': None,
        'jsonl_matches_official': None,
    }
    issues = result['issues']

    if save_path.is_file():
        result['official'] = {
            'exists': True,
            'sha256': hashlib.sha256(save_path.read_bytes()).hexdigest(),
        }
    else:
        issues.append('找不到正式 Performance CSV。')

    # The existing inspector covers PREPARED / PUBLISHED / ABORTED plus
    # incomplete publication and file backups without changing state.
    try:
        published_state = inspect_performance_publish_state(
            str(save_path), str(backup_folder), str(log_path)
        )
        result['jsonl'].update({
            'status': published_state.get('status'),
            'last_published_id': published_state.get('last_published_id'),
            'pending_publish_id': published_state.get('pending_publish_id'),
            'message': published_state.get('message'),
        })
    except Exception as exc:
        issues.append('發布歷程診斷無法完成：{}'.format(exc))

    # Extract the last PUBLISHED hash separately to compare all three stores.
    if log_path.is_file():
        try:
            last_published = None
            with log_path.open('r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError('第 {} 行不是物件'.format(line_no))
                    if item.get('status') == 'PUBLISHED':
                        last_published = item
            if last_published:
                result['jsonl']['last_published_sha256'] = str(
                    last_published.get('sha256') or ''
                ).lower()
        except (OSError, ValueError, TypeError) as exc:
            issues.append('無法完整讀取 JSONL：{}'.format(exc))
    else:
        issues.append('找不到 Performance JSONL 發布歷程。')

    official_sha = result['official']['sha256']
    published_sha = result['jsonl']['last_published_sha256']
    if official_sha is not None and published_sha is not None:
        result['jsonl_matches_official'] = official_sha == published_sha
        if not result['jsonl_matches_official']:
            issues.append('JSONL 最後 PUBLISHED SHA256 與正式 CSV 不一致。')

    # Read all non-superseded batches, and independently verify each archive.
    try:
        with session_factory() as db:
            histories = db.scalars(
                select(PerformanceImportHistory).where(
                    PerformanceImportHistory.status.in_(['ACTIVE', 'PENDING'])
                )
            ).all()
            for item in histories:
                stored_name = str(item.stored_filename or '')
                safe_name = bool(stored_name) and Path(stored_name).name == stored_name
                archived = archive_dir / stored_name if safe_name else None
                archive_sha = (
                    hashlib.sha256(archived.read_bytes()).hexdigest()
                    if archived is not None and archived.is_file() else None
                )
                row_count = db.scalar(
                    select(func.count()).select_from(InstrumentPerformanceControl).where(
                        InstrumentPerformanceControl.import_id == item.import_id
                    )
                )
                batch = {
                    'import_id': item.import_id,
                    'status': item.status,
                    'sha256': str(item.sha256 or '').lower(),
                    'record_count': item.record_count,
                    'actual_record_count': row_count,
                    'stored_filename': stored_name,
                    'archive_exists': archive_sha is not None,
                    'archive_matches_batch': archive_sha == str(item.sha256 or '').lower(),
                    'details_complete': row_count == item.record_count,
                    'matches_official': (
                        str(item.sha256 or '').lower() == official_sha
                        if official_sha is not None else None
                    ),
                }
                result[item.status.lower()].append(batch)
                if not batch['details_complete'] or not batch['archive_matches_batch']:
                    issues.append('{} 批次 {} 明細或原始檔不一致。'.format(
                        item.status, item.import_id
                    ))
    except Exception as exc:
        issues.append('SQLite 批次診斷無法完成：{}'.format(exc))
        result['message'] = 'SQLite 或發布歷程無法完整診斷，請人工核對。'
        return result

    active = result['active']
    pending = result['pending']
    if len(active) != 1:
        issues.append('SQLite ACTIVE 批次數量不是 1。')
    if len(pending) > 1:
        issues.append('SQLite 存在多個 PENDING 批次。')
    if pending:
        issues.append('存在未完成 PENDING，禁止開始新發布。')
    if official_sha is not None and len(active) == 1:
        result['official_matches_active'] = active[0]['matches_official']
        if not result['official_matches_active']:
            issues.append('正式 CSV 與 SQLite ACTIVE SHA256 不一致。')
    if official_sha is not None and pending:
        result['official_matches_pending'] = any(
            item['matches_official'] for item in pending
        )
    if result['jsonl']['status'] != 'NORMAL':
        issues.append('JSONL 發布狀態並非 NORMAL：{}'.format(result['jsonl']['status']))
    if any(result['locks'].values()):
        issues.append('仍存在發布或匯入鎖定檔，須核對執行狀態。')

    if not issues:
        result['status'] = 'NORMAL'
        result['message'] = '正式 CSV、JSONL 與唯一 ACTIVE 批次一致，且無 PENDING／鎖定。'
    else:
        result['status'] = 'REVIEW_REQUIRED'
        if (result['jsonl_matches_official'] is True
                and result['official_matches_pending'] is True
                and result['official_matches_active'] is False):
            result['message'] = (
                '正式 CSV／JSONL 已對應 PENDING，但 SQLite ACTIVE 仍為舊批次；'
                '需要人工核對，不得自動切換。'
            )
        else:
            result['message'] = '發現發布狀態不一致或未完成作業，須人工核對。'
    return result


# ========================================
# Performance：異常恢復條件評估（唯讀）
# 不啟用 PENDING、不移除鎖定檔
# ========================================

def assess_performance_recovery_options(save_path, log_path, archive_dir, session_factory):
    """Classify whether a *human-supervised* completion could be considered.

    This is only advisory. It is NOT authorization to activate, retry, reset a
    lock, or publish. A separate guarded recovery operation would be required.
    """
    diagnosis = diagnose_performance_release_state(
        save_path=save_path,
        log_path=log_path,
        archive_dir=archive_dir,
        session_factory=session_factory,
    )
    result = {
        'status': 'BLOCKED',
        'message': '資料狀態未符合受控補完條件，須人工調查。',
        'pending_import_id': None,
        'diagnosis': diagnosis,
    }

    if diagnosis['status'] == 'NORMAL':
        result['status'] = 'NO_RECOVERY_NEEDED'
        result['message'] = '三方一致，無需恢復。'
        return result

    if diagnosis['status'] != 'REVIEW_REQUIRED':
        return result

    active = diagnosis['active']
    pending = diagnosis['pending']
    locks = diagnosis['locks']
    j = diagnosis['jsonl']
    if len(active) != 1 or len(pending) != 1:
        return result

    old_batch = active[0]
    new_batch = pending[0]
    official_sha = diagnosis['official']['sha256']
    matching = (
        official_sha is not None
        and j['status'] == 'NORMAL'
        and bool(j['last_published_id'])
        and j['last_published_sha256'] == official_sha
        and diagnosis['jsonl_matches_official'] is True
        and diagnosis['official_matches_active'] is False
        and diagnosis['official_matches_pending'] is True
        and old_batch['sha256'] != new_batch['sha256']
        and new_batch['sha256'] == official_sha
        and all(
            isinstance(b['record_count'], int)
            and b['record_count'] > 0
            and b['details_complete'] is True
            and b['archive_matches_batch'] is True
            for b in (old_batch, new_batch)
        )
        and locks['release'] is True
        and locks['csv_publish'] is False
        and locks['db_import'] is False
    )
    if matching:
        result['status'] = 'SUPERVISED_COMPLETION_CANDIDATE'
        result['message'] = (
            'CSV、JSONL 已正式發布，PENDING 完整且與正式檔一致；'
            '僅符合管理員進一步核對與受控補完的候選條件，'
            '尚不得自行清鎖或切換 ACTIVE。'
        )
        result['pending_import_id'] = new_batch['import_id']
    return result
