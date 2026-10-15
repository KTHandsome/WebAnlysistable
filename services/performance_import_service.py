# -*- coding: utf-8 -*-
"""Phyon Performance CSV parser and database batch importer.

The web route remains responsible for permissions and business validation.
This service does not modify the official published CSV or its JSONL log.
"""

import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select


PERFORMANCE_CSV_COLUMNS = (
    "CONTROL_ID", "INSTRUMENT_ID", "INSTRUMENT_MODEL", "YEAR",
    "EFFECTIVE_FROM", "EFFECTIVE_TO", "PERFORMANCE_TYPE",
    "MONITOR_ITEM", "NUMERATOR_ITEM", "NUMERATOR_WAVELENGTH_NM",
    "DENOMINATOR_ITEM", "DENOMINATOR_WAVELENGTH_NM",
    "TARGET_WAVELENGTH_NM", "REFERENCE_VALUE", "LOWER_LIMIT",
    "UPPER_LIMIT", "UNIT", "SAMPLE_LABELS", "FREQUENCY",
    "CONTROL_VERSION", "ENABLED", "SOP_REFERENCE", "NOTES",
)


def parse_performance_date(value, field_name, row_number):
    text = str(value or "").strip()
    if not text:
        raise ValueError("第 {} 列：{} 不可空白".format(row_number, field_name))
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("第 {} 列：{} 日期格式錯誤：{}".format(row_number, field_name, text))


def parse_performance_number(value, field_name, row_number):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = Decimal(text)
        if number.is_finite():
            return number
    except InvalidOperation:
        pass
    raise ValueError("第 {} 列：{} 數值格式錯誤：{}".format(row_number, field_name, text))


def parse_performance_enabled(value, row_number):
    text = str(value or "").strip().upper()
    if text == "Y":
        return True
    if text == "N":
        return False
    raise ValueError("第 {} 列：ENABLED 必須為 Y 或 N".format(row_number))


def parse_performance_year(value, row_number):
    text = str(value or "").strip()
    if len(text) != 4 or not text.isascii() or not text.isdigit():
        raise ValueError("第 {} 列：YEAR 必須為四位數西元年".format(row_number))
    return int(text)


def parse_performance_csv(file_bytes):
    """Return dictionaries matching InstrumentPerformanceControl model fields."""
    if not isinstance(file_bytes, bytes):
        raise ValueError("Performance CSV 必須提供 bytes")
    try:
        csv_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Performance CSV 必須使用 UTF-8 編碼")

    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if not reader.fieldnames:
        raise ValueError("Performance CSV 缺少標題列")
    headers = [str(name or "").strip() for name in reader.fieldnames]
    if len(headers) != len(set(headers)):
        raise ValueError("Performance CSV 存在重複欄位名稱")
    missing = [name for name in PERFORMANCE_CSV_COLUMNS if name not in headers]
    if missing:
        raise ValueError("Performance CSV 缺少欄位：{}".format(", ".join(missing)))

    records = []
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError("第 {} 列：欄位數量超過標題列".format(row_number))
        if all(not str(value or "").strip() for value in row.values()):
            continue
        normalized = {
            name: str(row.get(name) or "").strip()
            for name in PERFORMANCE_CSV_COLUMNS
        }
        record = {
            "control_id": normalized["CONTROL_ID"],
            "instrument_id": normalized["INSTRUMENT_ID"],
            "instrument_model": normalized["INSTRUMENT_MODEL"],
            "year": parse_performance_year(normalized["YEAR"], row_number),
            "effective_from": parse_performance_date(normalized["EFFECTIVE_FROM"], "EFFECTIVE_FROM", row_number),
            "effective_to": parse_performance_date(normalized["EFFECTIVE_TO"], "EFFECTIVE_TO", row_number),
            "performance_type": normalized["PERFORMANCE_TYPE"],
            "monitor_item": normalized["MONITOR_ITEM"],
            "numerator_item": normalized["NUMERATOR_ITEM"],
            "numerator_wavelength_nm": parse_performance_number(normalized["NUMERATOR_WAVELENGTH_NM"], "NUMERATOR_WAVELENGTH_NM", row_number),
            "denominator_item": normalized["DENOMINATOR_ITEM"],
            "denominator_wavelength_nm": parse_performance_number(normalized["DENOMINATOR_WAVELENGTH_NM"], "DENOMINATOR_WAVELENGTH_NM", row_number),
            "target_wavelength_nm": parse_performance_number(normalized["TARGET_WAVELENGTH_NM"], "TARGET_WAVELENGTH_NM", row_number),
            "reference_value": parse_performance_number(normalized["REFERENCE_VALUE"], "REFERENCE_VALUE", row_number),
            "lower_limit": parse_performance_number(normalized["LOWER_LIMIT"], "LOWER_LIMIT", row_number),
            "upper_limit": parse_performance_number(normalized["UPPER_LIMIT"], "UPPER_LIMIT", row_number),
            "unit": normalized["UNIT"],
            "sample_labels": normalized["SAMPLE_LABELS"],
            "frequency": normalized["FREQUENCY"],
            "control_version": normalized["CONTROL_VERSION"],
            "enabled": parse_performance_enabled(normalized["ENABLED"], row_number),
            "sop_reference": normalized["SOP_REFERENCE"],
            "notes": normalized["NOTES"],
        }
        records.append(record)
    if not records:
        raise ValueError("Performance CSV 沒有可匯入的資料")
    return records


def import_performance_csv_to_database(
    file_bytes,
    original_filename,
    imported_by,
    archive_dir,
    session_factory,
):
    """Import a *previously business-validated* full CSV as an active DB batch.

    An exclusive lock works for cooperating processes sharing archive_dir on
    the same host/filesystem. It is NOT a distributed database mutex.
    Never use this function from a web route before full business validation.
    """
    from models import PerformanceImportHistory, InstrumentPerformanceControl

    if not str(imported_by or "").strip():
        raise ValueError("缺少匯入者，拒絕匯入")

    records = parse_performance_csv(file_bytes)
    ids = [row["control_id"] for row in records]
    if any(not control_id for control_id in ids):
        raise ValueError("CONTROL_ID 不可空白")
    if len(ids) != len(set(ids)):
        raise ValueError("CSV 中有重複的 CONTROL_ID")

    import_id = str(uuid4())
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    versions = sorted(set(row["control_version"] for row in records))
    safe_original_name = str(original_filename or "performance.csv").replace("\\", "/").split("/")[-1]
    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)
    lock_path = archive_path / ".performance_db_import.lock"
    stored_name = "Performance_{}.csv".format(import_id)
    saved_path = archive_path / stored_name

    # Lock before writing an archive or changing ACTIVE statuses.
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError("已有 Performance 匯入作業進行中；若確定沒有作業，請由管理員檢查鎖定檔")

    temporary_path = None
    archived = False
    commit_started = False
    committed = False
    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(import_id + "\n")
            lock_file.flush()
            os.fsync(lock_file.fileno())

        # A unique immutable archive, separate from the official published CSV.
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(archive_path), prefix=".performance_",
            suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(file_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        if hashlib.sha256(temporary_path.read_bytes()).hexdigest() != sha256:
            raise RuntimeError("Performance CSV 備份驗證失敗")
        os.replace(str(temporary_path), str(saved_path))
        temporary_path = None
        archived = True

        with session_factory() as db:
            try:
                active_batches = db.scalars(
                    select(PerformanceImportHistory).where(
                        PerformanceImportHistory.status == "ACTIVE"
                    )
                ).all()
                if len(active_batches) > 1:
                    raise RuntimeError("資料庫存在多個 ACTIVE 批次，請先檢查")

                history = PerformanceImportHistory(
                    import_id=import_id,
                    original_filename=safe_original_name,
                    stored_filename=stored_name,
                    sha256=sha256,
                    record_count=len(records),
                    control_versions_json=json.dumps(versions, ensure_ascii=False),
                    imported_by=str(imported_by).strip(),
                    status="ACTIVE",
                )
                db.add(history)
                db.flush()  # Enforce parent-before-children insertion.
                for row in records:
                    db.add(InstrumentPerformanceControl(import_id=import_id, **row))
                db.flush()
                for old_batch in active_batches:
                    old_batch.status = "SUPERSEDED"
                db.flush()
                commit_started = True
                db.commit()
                committed = True
            except Exception:
                db.rollback()
                raise

        return {
            "import_id": import_id,
            "record_count": len(records),
            "sha256": sha256,
            "stored_filename": stored_name,
            "control_versions": versions,
        }
    except Exception:
        # Once COMMIT has been attempted the outcome may be uncertain; keep
        # the archive for reconciliation rather than breaking a committed FK.
        if archived and not commit_started and saved_path.exists():
            saved_path.unlink()
        raise
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        if lock_path.exists():
            lock_path.unlink()


# ========================================
# Performance: prepare an unpublished PENDING batch
# Does NOT change the official CSV, JSONL log, or ACTIVE batch.
# ========================================

def prepare_performance_import(
    file_bytes,
    original_filename,
    imported_by,
    archive_dir,
    session_factory,
):
    """Persist a validated CSV as PENDING without switching the active batch.

    The caller must first perform the existing full business validation.
    Intended for use by the future release coordinator, not as a stand-alone
    public route. This function does not publish the official CSV.
    """
    from models import PerformanceImportHistory, InstrumentPerformanceControl

    if not str(imported_by or "").strip():
        raise ValueError("缺少匯入者，拒絕建立 PENDING 批次")

    records = parse_performance_csv(file_bytes)
    control_ids = [row["control_id"] for row in records]
    if any(not control_id for control_id in control_ids):
        raise ValueError("CONTROL_ID 不可空白")
    if len(control_ids) != len(set(control_ids)):
        raise ValueError("CSV 中有重複的 CONTROL_ID")

    import_id = str(uuid4())
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    versions = sorted(set(row["control_version"] for row in records))
    safe_original_name = (
        str(original_filename or "performance.csv")
        .replace("\\", "/")
        .split("/")[-1]
    )
    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)
    lock_path = archive_path / ".performance_db_import.lock"
    stored_name = "Performance_{}.csv".format(import_id)
    saved_path = archive_path / stored_name

    try:
        lock_fd = os.open(
            str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError:
        raise RuntimeError(
            "已有 Performance 匯入作業進行中；請由管理員確認鎖定狀態"
        )

    temporary_path = None
    archived = False
    commit_started = False

    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(import_id + "\n")
            lock_file.flush()
            os.fsync(lock_file.fileno())

        # No second pending batch is allowed until the release coordinator
        # has activated or explicitly resolved the previous one.
        with session_factory() as db:
            active_count = len(db.scalars(
                select(PerformanceImportHistory).where(
                    PerformanceImportHistory.status == "ACTIVE"
                )
            ).all())
            pending_count = len(db.scalars(
                select(PerformanceImportHistory).where(
                    PerformanceImportHistory.status == "PENDING"
                )
            ).all())
            if active_count != 1:
                raise RuntimeError(
                    "Performance 資料庫必須恰有一個 ACTIVE 批次，停止準備"
                )
            if pending_count:
                raise RuntimeError(
                    "已有 PENDING 批次，請先核對或完成前次發布"
                )

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(archive_path),
            prefix=".performance_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(file_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if hashlib.sha256(temporary_path.read_bytes()).hexdigest() != sha256:
            raise RuntimeError("Performance PENDING CSV 備份驗證失敗")

        os.replace(str(temporary_path), str(saved_path))
        temporary_path = None
        archived = True

        with session_factory() as db:
            try:
                # Recheck after saving the archive, before database changes.
                # The file lock protects cooperating processes on this host.
                active_batches = db.scalars(
                    select(PerformanceImportHistory).where(
                        PerformanceImportHistory.status == "ACTIVE"
                    )
                ).all()
                pending_batches = db.scalars(
                    select(PerformanceImportHistory).where(
                        PerformanceImportHistory.status == "PENDING"
                    )
                ).all()
                if len(active_batches) != 1 or pending_batches:
                    raise RuntimeError(
                        "Performance 批次狀態已變動，停止準備 PENDING"
                    )

                history = PerformanceImportHistory(
                    import_id=import_id,
                    original_filename=safe_original_name,
                    stored_filename=stored_name,
                    sha256=sha256,
                    record_count=len(records),
                    control_versions_json=json.dumps(
                        versions, ensure_ascii=False
                    ),
                    imported_by=str(imported_by).strip(),
                    status="PENDING",
                )
                db.add(history)
                db.flush()  # Parent row must precede its FK children.

                for row in records:
                    db.add(InstrumentPerformanceControl(
                        import_id=import_id, **row
                    ))
                db.flush()

                # Deliberately do not update existing ACTIVE/SUPERSEDED rows.
                commit_started = True
                db.commit()
            except Exception:
                db.rollback()
                raise

        return {
            "import_id": import_id,
            "status": "PENDING",
            "record_count": len(records),
            "sha256": sha256,
            "stored_filename": stored_name,
            "control_versions": versions,
        }

    except Exception:
        # Before COMMIT: a failed transaction cannot refer to this archive.
        # After COMMIT attempt: retain it for reconciliation because the DB
        # outcome may be uncertain even if an exception was raised.
        if archived and not commit_started and saved_path.exists():
            saved_path.unlink()
        raise
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        if lock_path.exists():
            lock_path.unlink()

# ========================================
# Performance: activate a published PENDING batch
# Requires caller to confirm official CSV + JSONL publish completed.
# ========================================

def activate_pending_performance_import(
    import_id,
    save_path,
    archive_dir,
    session_factory,
):
    """Atomically replace ACTIVE with one already-prepared PENDING batch.

    This is the database-only final stage. The coordinator MUST verify that
    the official CSV/JSONL release is complete before calling this function.
    A COMMIT exception can leave an uncertain outcome: inspect state rather
    than immediately retrying. Not a distributed lock across hosts.
    """
    from sqlalchemy import func
    from models import PerformanceImportHistory, InstrumentPerformanceControl

    pending_id = str(import_id or "").strip()
    if not pending_id:
        raise ValueError("缺少 PENDING import_id")

    official_path = Path(save_path)
    if not official_path.is_file():
        raise ValueError("正式 Performance CSV 不存在")

    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)
    lock_path = archive_path / ".performance_db_import.lock"
    try:
        lock_fd = os.open(
            str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError:
        raise RuntimeError("已有 Performance 資料庫作業，禁止切換 ACTIVE")

    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_file:
            lock_file.write("ACTIVATE " + pending_id + "\n")
            lock_file.flush()
            os.fsync(lock_file.fileno())

        # Check on-disk official content again while holding the DB import lock.
        official_hash = hashlib.sha256(official_path.read_bytes()).hexdigest()

        with session_factory() as db:
            try:
                histories = db.scalars(
                    select(PerformanceImportHistory).where(
                        PerformanceImportHistory.status.in_(("ACTIVE", "PENDING"))
                    )
                ).all()
                current = [x for x in histories if x.status == "ACTIVE"]
                waiting = [x for x in histories if x.status == "PENDING"]
                if len(current) != 1 or len(waiting) != 1:
                    raise RuntimeError("ACTIVE/PENDING 批次數量異常，禁止切換")
                old_batch, new_batch = current[0], waiting[0]
                if new_batch.import_id != pending_id:
                    raise RuntimeError("指定的 PENDING import_id 與資料庫不符")
                if str(new_batch.sha256 or "").lower() != official_hash:
                    raise RuntimeError("正式 CSV SHA256 與 PENDING 不一致，禁止切換")
                stored_name = str(new_batch.stored_filename or "")
                if not stored_name or Path(stored_name).name != stored_name:
                    raise RuntimeError("PENDING 備份檔名不合法")
                archived_file = archive_path / stored_name
                if not archived_file.is_file():
                    raise RuntimeError("找不到 PENDING 原始 CSV 備份")
                if hashlib.sha256(archived_file.read_bytes()).hexdigest() != official_hash:
                    raise RuntimeError("PENDING 原始 CSV 備份 SHA256 不一致")

                actual_count = db.scalar(
                    select(func.count()).select_from(
                        InstrumentPerformanceControl
                    ).where(InstrumentPerformanceControl.import_id == pending_id)
                )
                if actual_count != new_batch.record_count or actual_count < 1:
                    raise RuntimeError("PENDING 管制明細數量異常，禁止切換")

                old_id = old_batch.import_id
                old_batch.status = "SUPERSEDED"
                new_batch.status = "ACTIVE"
                db.flush()
                db.commit()
            except Exception:
                db.rollback()
                raise

        return {
            "import_id": pending_id,
            "previous_import_id": old_id,
            "status": "ACTIVE",
            "record_count": actual_count,
            "sha256": official_hash,
        }
    finally:
        if lock_path.exists():
            lock_path.unlink()
