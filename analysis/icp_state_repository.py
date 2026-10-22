
import json
from datetime import datetime, timezone, timedelta
from database import SessionLocal
from models import IcpImportWorkState

# ========================================
# SQLite UTC 時間轉換台灣時間
# ========================================
TAIWAN_TIMEZONE = timezone(
    timedelta(hours=8)
)


def icp_utc_to_taiwan(value):

    if value is None:
        return None

    # SQLite 讀出的 DateTime 通常沒有時區資訊，
    # 依目前已確認的 SQLite CURRENT_TIMESTAMP，
    # 視為 UTC 時間。
    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        TAIWAN_TIMEZONE
    )

# ========================================
# 儲存 ICP 工作狀態
# 相同 work_key：更新
# 不同 work_key：新增
# ========================================
def save_icp_work_state(work_key, state_data):

    if not work_key or not isinstance(state_data, dict):
        raise ValueError("ICP 工作狀態資料不正確。")

    state_json = json.dumps(
        state_data,
        ensure_ascii=False
    )

    form_data = state_data.get("form_data") or {}

    method_code = str(
        form_data.get("method_code") or ""
    ).strip()

    source_filename = str(
        state_data.get("source_filename") or ""
    ).strip()

    db = SessionLocal()

    try:
        record = (
            db.query(IcpImportWorkState)
            .filter(
                IcpImportWorkState.work_key == work_key
            )
            .first()
        )

        if record is None:
            record = IcpImportWorkState(
                work_key=work_key,
                method_code=method_code,
                source_filename=source_filename,
                state_json=state_json
            )

            db.add(record)

        else:
            from services.icp_record_service import check_editable
            from auth_session import get_current_user
            current = json.loads(record.state_json)
            check_editable(current, get_current_user() or {})
            if current.get("formal_analysis_id") != state_data.get("formal_analysis_id"):
                raise ValueError("不可變更 ICP 工作的正式紀錄關聯。")
            from sqlalchemy import update
            changed = db.execute(update(IcpImportWorkState).where(
                IcpImportWorkState.work_key == work_key,
                IcpImportWorkState.state_json == record.state_json,
            ).values(method_code=method_code, source_filename=source_filename, state_json=state_json))
            if changed.rowcount != 1:
                raise ValueError("ICP 工作已更新，本次未儲存，請重新載入。")

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ========================================
# 讀取 ICP 工作狀態
# ========================================
def load_icp_work_state(work_key):

    if not work_key:
        return None

    db = SessionLocal()

    try:
        record = (
            db.query(IcpImportWorkState)
            .filter(
                IcpImportWorkState.work_key == work_key
            )
            .first()
        )

        if record is None:
            return None

        return json.loads(record.state_json)

    finally:
        db.close()

# ========================================
# 刪除 ICP 工作狀態
# ========================================
def delete_icp_work_state(work_key, current_user=None):

    if not work_key:
        return False

    db = SessionLocal()

    try:
        record = (
            db.query(IcpImportWorkState)
            .filter(
                IcpImportWorkState.work_key == work_key
            )
            .first()
        )

        if record is None:
            return False

        original = record.state_json
        work = json.loads(original)
        if work.get("formal_analysis_id"):
            raise ValueError("此工作已關聯正式分析紀錄，請由分析紀錄查詢處理。")
        from services.icp_record_service import check_editable
        if current_user is None:
            from auth_session import get_current_user
            current_user = get_current_user() or {}
        check_editable(work, current_user)
        from sqlalchemy import delete
        result = db.execute(delete(IcpImportWorkState).where(
            IcpImportWorkState.work_key == work_key,
            IcpImportWorkState.state_json == original,
        ))
        if result.rowcount != 1:
            raise ValueError("工作已更新，本次未刪除，請重新整理後再確認。")
        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

# ========================================
# 查詢已暫存 ICP 工作清單
# 不載入完整 PDF 解析 JSON
# ========================================
def list_icp_work_states(method_code=None):

    db = SessionLocal()

    try:
        query = db.query(
            IcpImportWorkState.work_key,
            IcpImportWorkState.method_code,
            IcpImportWorkState.source_filename,
            IcpImportWorkState.created_at,
            IcpImportWorkState.updated_at,
        )

        if method_code:
            query = query.filter(
                IcpImportWorkState.method_code
                == method_code
            )

        # Formal status is written with the canonical JSON serializer.
        # Filter in SQL without fetching every work's large raw-PDF JSON.
        query = query.filter(
            ~IcpImportWorkState.state_json.contains('"formal_status": "SUBMITTED"', autoescape=True),
            ~IcpImportWorkState.state_json.contains('"formal_status": "DELETED"', autoescape=True),
        )

        rows = (
            query
            .order_by(
                IcpImportWorkState.updated_at.desc(),
                IcpImportWorkState.id.desc()
            )
            .all()
        )

        return [
            {
                "work_key": row.work_key,
                "method_code": row.method_code,
                "source_filename": row.source_filename,
                "created_at": icp_utc_to_taiwan(row.created_at),
                "updated_at": icp_utc_to_taiwan(row.updated_at),
            }
            for row in rows
        ]

    finally:
        db.close()
