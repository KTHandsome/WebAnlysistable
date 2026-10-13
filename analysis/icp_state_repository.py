
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
            record.method_code = method_code
            record.source_filename = source_filename
            record.state_json = state_json

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
def delete_icp_work_state(work_key):

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

        db.delete(record)
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
