
import json

from database import SessionLocal
from models import IcpImportWorkState


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
        