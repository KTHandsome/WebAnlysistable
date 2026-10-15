# services/performance_publish_service.py

import hashlib
import json
import os

from datetime import datetime, timezone, timedelta


TAIWAN_TIMEZONE = timezone(timedelta(hours=8))


def calculate_performance_sha256(file_bytes):
    """
    計算 Performance CSV 原始位元組的 SHA-256。
    """

    if not isinstance(file_bytes, bytes):
        raise ValueError(
            "Performance CSV 必須為 bytes 格式。"
        )

    return hashlib.sha256(
        file_bytes
    ).hexdigest()


def build_performance_publish_record(
    file_bytes,
    published_by,
    record_count,
    control_versions
):
    """
    建立 Performance 發布紀錄。
    本函式不寫入任何檔案。
    """

    published_by = str(
        published_by or ""
    ).strip()

    if not published_by:
        raise ValueError(
            "Performance 發布紀錄缺少發布者。"
        )

    if not isinstance(record_count, int) or record_count <= 0:
        raise ValueError(
            "Performance 發布筆數必須大於零。"
        )

    if not isinstance(control_versions, (list, tuple)):
        raise ValueError(
            "Performance 管制版本格式不正確。"
        )

    versions = sorted({
        str(version).strip()
        for version in control_versions
        if str(version).strip()
    })

    if not versions:
        raise ValueError(
            "Performance 發布紀錄缺少管制版本。"
        )

    published_at = datetime.now(
        TAIWAN_TIMEZONE
    ).isoformat(timespec="seconds")

    return {
        "published_at": published_at,
        "published_by": published_by,
        "filename": (
            "Phyon_Instrument_Performance_Control.csv"
        ),
        "record_count": record_count,
        "sha256": calculate_performance_sha256(
            file_bytes
        ),
        "control_versions": versions
    }


def append_performance_publish_record(
    record,
    log_path
):
    """
    以 JSON Lines 格式附加發布紀錄。

    注意：
    本函式只負責紀錄寫入，
    不負責正式 CSV 替換或交易復原。
    """

    if not isinstance(record, dict):
        raise ValueError(
            "Performance 發布紀錄格式不正確。"
        )

    required_fields = {
        "published_at",
        "published_by",
        "filename",
        "record_count",
        "sha256",
        "control_versions"
    }

    if not required_fields.issubset(record.keys()):
        raise ValueError(
            "Performance 發布紀錄缺少必要欄位。"
        )

    log_folder = os.path.dirname(
        os.path.abspath(log_path)
    )

    os.makedirs(
        log_folder,
        exist_ok=True
    )

    json_line = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True
    ) + "\n"

    with open(
        log_path,
        "a",
        encoding="utf-8",
        newline="\n"
    ) as log_file:

        log_file.write(json_line)

        log_file.flush()

        os.fsync(
            log_file.fileno()
        )

# ========================================
# Performance：檢查未完成的發布紀錄
# ========================================

# ========================================
# Performance：發布歷程與正式檔一致性檢查
# ========================================

def check_performance_publish_history(
    log_path,
    save_path
):

    # ========================================
    # 第一次正式發布保護
    # ========================================

    if not os.path.isfile(log_path):

        if os.path.isfile(save_path):
            raise ValueError(
                "Performance 正式 CSV 已存在，"
                "但尚無發布歷程紀錄。"
                "請先確認既有管制資料，"
                "不得直接覆寫。"
            )

        return

    prepared = set()
    completed = set()
    aborted = set()
    last_published = None

    with open(
        log_path,
        "r",
        encoding="utf-8"
    ) as f:

        for line_number, line in enumerate(f, start=1):

            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(
                    "Performance 發布歷程第 {} 行格式錯誤。"
                    .format(line_number)
                )

            if not isinstance(record, dict):
                raise ValueError(
                    "Performance 發布歷程資料格式不正確。"
                )

            publish_id = record.get("publish_id")
            status = record.get("status")

            if not publish_id:
                raise ValueError(
                    "Performance 發布歷程缺少 publish_id。"
                )

            if status == "PREPARED":
                prepared.add(publish_id)

            elif status == "PUBLISHED":

                if publish_id not in prepared:
                    raise ValueError(
                        "Performance 發布完成紀錄"
                        "缺少對應的 PREPARED。"
                    )

                if publish_id in completed:
                    raise ValueError(
                        "Performance 發布完成紀錄重複。"
                    )

                completed.add(publish_id)
                last_published = record

            elif status == "ABORTED":

                if publish_id not in prepared:
                    raise ValueError(
                        "Performance 取消發布紀錄"
                        "缺少對應的 PREPARED。"
                    )

                if (
                    publish_id in completed
                    or publish_id in aborted
                ):
                    raise ValueError(
                        "Performance 取消發布紀錄重複"
                        "或與完成紀錄衝突。"
                    )

                aborted.add(publish_id)

    # ========================================
    # 1. 有未完成發布，禁止再次發布
    # ========================================

    if prepared != (completed | aborted):
        raise ValueError(
            "發現未完成的 Performance 發布紀錄，"
            "請先核對正式 CSV 與發布歷程。"
        )

    # ========================================
    # 尚無有效發布紀錄
    # ========================================

    if last_published is None:

        if os.path.isfile(save_path):
            raise ValueError(
                "Performance 正式 CSV 已存在，"
                "但發布歷程沒有有效的完成紀錄，"
                "請先確認資料狀態。"
            )

        return

    # ========================================
    # 2. 必須存在正式 CSV
    # ========================================

    if not os.path.isfile(save_path):
        raise ValueError(
            "Performance 已有正式發布紀錄，"
            "但找不到目前正式 CSV。"
        )

    # ========================================
    # 3. 比對正式 CSV 的 SHA-256
    # ========================================

    expected_hash = last_published.get("sha256")

    if (
        not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(
            char not in "0123456789abcdefABCDEF"
            for char in expected_hash
        )
    ):
        raise ValueError(
            "Performance 最後發布紀錄的 SHA-256 無效。"
        )

    with open(save_path, "rb") as f:
        actual_hash = calculate_performance_sha256(
            f.read()
        )

    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            "Performance 正式 CSV 與最後發布紀錄"
            "的 SHA-256 不一致，已停止發布。"
        )

# ========================================
# Performance：受控發布正式 CSV
# 呼叫前必須已完成整份 CSV 驗證及權限檢查
# ========================================

def publish_performance_csv(
    file_bytes,
    record,
    save_path,
    backup_folder,
    log_path
):

    import shutil
    import tempfile

    from uuid import uuid4

    if not isinstance(file_bytes, bytes):
        raise ValueError(
            "Performance CSV 必須為 bytes 格式。"
        )

    if not isinstance(record, dict):
        raise ValueError(
            "Performance 發布紀錄格式不正確。"
        )

    expected_hash = calculate_performance_sha256(
        file_bytes
    )

    if record.get("sha256") != expected_hash:
        raise ValueError(
            "Performance 發布檔案與紀錄的 SHA-256 不一致。"
        )

    if not file_bytes:
        raise ValueError(
            "Performance CSV 不得為空白。"
        )

    data_folder = os.path.dirname(
        os.path.abspath(save_path)
    )

    os.makedirs(
        data_folder,
        exist_ok=True
    )

    # 使用獨占建立方式阻擋同時發布。
    # 如果程序異常中止而留下鎖定檔，
    # 必須人工核對後才能移除。
    lock_path = save_path + ".publish.lock"

    try:

        lock_fd = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )

    except FileExistsError:

        raise ValueError(
            "Performance 發布作業已鎖定，"
            "請確認是否有進行中或未完成的發布。"
        )

    os.close(lock_fd)

    temp_path = None

    publish_completed = False
    publication_started = False

    try:

        # ========================================
        # 1. 先確認沒有未完成發布
        # ========================================

        check_performance_publish_history(
            log_path,
            save_path
        )

        # ========================================
        # 2. 建立本次發布識別碼
        # ========================================

        publish_id = uuid4().hex

        publish_record = dict(record)

        publish_record["publish_id"] = publish_id

        # ========================================
        # 3. 建立新版 CSV 暫存檔
        # ========================================

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            prefix=".performance_",
            dir=data_folder,
            delete=False
        ) as temp_file:

            temp_path = temp_file.name

            temp_file.write(
                file_bytes
            )

            temp_file.flush()

            os.fsync(
                temp_file.fileno()
            )

        # ========================================
        # 4. 備份既有正式 CSV
        # ========================================

        backup_path = None

        if os.path.isfile(save_path):

            os.makedirs(
                backup_folder,
                exist_ok=True
            )

            backup_path = os.path.join(
                backup_folder,
                "Performance_"
                + publish_id
                + ".csv"
            )

            shutil.copy2(
                save_path,
                backup_path
            )

            # 備份內容必須與替換前正式檔一致
            with open(save_path, "rb") as f:
                current_hash = (
                    calculate_performance_sha256(
                        f.read()
                    )
                )

            with open(backup_path, "rb") as f:
                backup_hash = (
                    calculate_performance_sha256(
                        f.read()
                    )
                )

            if current_hash != backup_hash:
                raise ValueError(
                    "Performance 原始檔備份驗證失敗，"
                    "已停止發布。"
                )

        publish_record["backup_path"] = backup_path

        # ========================================
        # 5. 建立 PREPARED 紀錄
        # ========================================
        publication_started = True

        prepared_record = dict(publish_record)

        prepared_record["status"] = "PREPARED"

        append_performance_publish_record(
            prepared_record,
            log_path
        )

        # ========================================
        # 6. 原子替換正式 CSV
        # ========================================

        os.replace(
            temp_path,
            save_path
        )

        temp_path = None

        # ========================================
        # 7. 驗證正式檔案 SHA-256
        # ========================================

        with open(save_path, "rb") as f:

            saved_hash = calculate_performance_sha256(
                f.read()
            )

        if saved_hash != expected_hash:
            raise ValueError(
                "Performance 正式檔案雜湊值不一致，"
                "請立即停止使用並檢查。"
            )

        # ========================================
        # 8. 建立 PUBLISHED 紀錄
        # ========================================

        completed_record = dict(publish_record)

        completed_record["status"] = "PUBLISHED"

        append_performance_publish_record(
            completed_record,
            log_path
        )

        publish_completed = True

        return completed_record

    finally:

        if (
            temp_path
            and os.path.exists(temp_path)
        ):
            os.remove(temp_path)

        # 尚未開始發布，或已完整發布，
        # 才允許自動移除鎖定檔。
        #
        # 若發布途中出錯，
        # 保留鎖定檔等待人工核對。

        if (
            not publication_started
            or publish_completed
        ):
            if os.path.exists(lock_path):
                os.remove(lock_path)

# ========================================
# Performance：首次正式納管 Baseline
#
# 僅適用於：
# 1. 正式 CSV 已存在
# 2. 尚無發布歷程
# 3. CSV 已由呼叫端完成驗證
# 4. 呼叫端已確認操作者具有管理權限
#
# 本函式不修改原有正式 CSV
# ========================================

def register_performance_baseline(
    save_path,
    backup_folder,
    log_path,
    published_by,
    record_count,
    control_versions,
    expected_sha256
):

    import shutil
    from uuid import uuid4

    # ========================================
    # 1. 確認既有正式 CSV
    # ========================================

    if not os.path.isfile(save_path):
        raise ValueError(
            "找不到 Performance 正式 CSV，"
            "無法建立首次納管基準。"
        )

    if not isinstance(expected_sha256, str):
        raise ValueError(
            "Performance Baseline 缺少 SHA-256。"
        )

    expected_sha256 = expected_sha256.strip().lower()

    if (
        len(expected_sha256) != 64
        or any(
            c not in "0123456789abcdef"
            for c in expected_sha256
        )
    ):
        raise ValueError(
            "Performance Baseline SHA-256 格式錯誤。"
        )

    # ========================================
    # 2. 取得獨占發布鎖
    # ========================================

    lock_path = save_path + ".publish.lock"

    try:

        lock_fd = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )

    except FileExistsError:

        raise ValueError(
            "Performance 發布作業已鎖定，"
            "請先確認是否有未完成作業。"
        )

    os.close(lock_fd)

    publication_started = False
    baseline_completed = False

    try:

        # ========================================
        # 3. Baseline 只能執行一次
        # ========================================

        if os.path.exists(log_path):
            raise ValueError(
                "Performance 已存在發布歷程，"
                "不得重複建立 Baseline。"
            )

        # ========================================
        # 4. 核對既有正式 CSV
        # ========================================

        with open(save_path, "rb") as f:
            file_bytes = f.read()

        actual_sha256 = calculate_performance_sha256(
            file_bytes
        )

        if actual_sha256 != expected_sha256:
            raise ValueError(
                "Performance 正式 CSV 與確認的"
                " Baseline SHA-256 不一致，"
                "已停止納管。"
            )

        # ========================================
        # 5. 建立 Baseline 紀錄
        # ========================================

        baseline_record = build_performance_publish_record(
            file_bytes=file_bytes,
            published_by=published_by,
            record_count=record_count,
            control_versions=control_versions
        )

        baseline_id = uuid4().hex

        baseline_record["publish_id"] = baseline_id
        baseline_record["operation"] = "BASELINE"

        # ========================================
        # 6. 建立既有 CSV 的基準備份
        # ========================================

        os.makedirs(
            backup_folder,
            exist_ok=True
        )

        backup_path = os.path.join(
            backup_folder,
            "Performance_BASELINE_"
            + baseline_id
            + ".csv"
        )

        # 使用 xb 避免覆寫既有備份檔案
        with open(backup_path, "xb") as backup_file:

            backup_file.write(file_bytes)
            backup_file.flush()

            os.fsync(
                backup_file.fileno()
            )

        # 確認備份與既有正式 CSV 完全一致
        with open(backup_path, "rb") as f:

            backup_hash = calculate_performance_sha256(
                f.read()
            )

        with open(save_path, "rb") as f:

            current_hash = calculate_performance_sha256(
                f.read()
            )

        if (
            backup_hash != expected_sha256
            or current_hash != expected_sha256
        ):
            raise ValueError(
                "Performance Baseline 備份驗證失敗，"
                "已停止納管。"
            )

        baseline_record["backup_path"] = backup_path

        # ========================================
        # 7. 寫入 PREPARED
        # ========================================

        publication_started = True

        prepared_record = dict(baseline_record)
        prepared_record["status"] = "PREPARED"

        append_performance_publish_record(
            prepared_record,
            log_path
        )

        # ========================================
        # 8. 再次核對正式 CSV
        # 不進行任何檔案替換
        # ========================================

        with open(save_path, "rb") as f:

            final_hash = calculate_performance_sha256(
                f.read()
            )

        if final_hash != expected_sha256:
            raise ValueError(
                "Performance Baseline 納管期間"
                "正式 CSV 內容發生變更，"
                "請停止使用並核對。"
            )

        # ========================================
        # 9. 寫入 PUBLISHED
        # ========================================

        completed_record = dict(baseline_record)
        completed_record["status"] = "PUBLISHED"

        append_performance_publish_record(
            completed_record,
            log_path
        )

        baseline_completed = True

        return completed_record

    finally:

        # 開始寫入發布歷程後若發生異常，
        # 保留鎖定檔，等待人工核對。

        if (
            not publication_started
            or baseline_completed
        ):

            if os.path.exists(lock_path):
                os.remove(lock_path)

# ========================================
# Performance：發布狀態診斷
# 僅檢查，不修改任何檔案
# ========================================

def inspect_performance_publish_state(
    save_path,
    backup_folder,
    log_path
):

    lock_path = save_path + ".publish.lock"

    result = {
        "status": "MANUAL_REVIEW",
        "message": "",
        "lock_exists": os.path.exists(lock_path),
        "last_published_id": None,
        "pending_publish_id": None
    }

    def finish(status, message):
        result["status"] = status
        result["message"] = message
        return result

    def read_hash(path):
        if not path or not os.path.isfile(path):
            return None

        with open(path, "rb") as f:
            return calculate_performance_sha256(
                f.read()
            )

    try:

        # ========================================
        # 1. 取得正式 CSV 狀態
        # ========================================

        current_hash = read_hash(save_path)

        if not os.path.isfile(log_path):

            return finish(
                "MANUAL_REVIEW",
                "尚無 Performance 發布歷程。"
            )

        # ========================================
        # 2. 讀取發布歷程
        # ========================================

        prepared = {}
        completed = set()
        aborted = set()
        last_published = None

        with open(
            log_path,
            "r",
            encoding="utf-8"
        ) as f:

            for line_number, line in enumerate(
                f,
                start=1
            ):

                if not line.strip():
                    continue

                record = json.loads(line)

                if not isinstance(record, dict):
                    raise ValueError(
                        "發布紀錄格式錯誤。"
                    )

                publish_id = record.get(
                    "publish_id"
                )

                status = record.get(
                    "status"
                )

                if not publish_id:
                    raise ValueError(
                        "發布紀錄缺少 publish_id。"
                    )

                if status == "PREPARED":

                    if publish_id in prepared:
                        raise ValueError(
                            "PREPARED 紀錄重複。"
                        )

                    prepared[publish_id] = record

                elif status == "PUBLISHED":

                    if (
                        publish_id not in prepared
                        or publish_id in completed
                    ):
                        raise ValueError(
                            "PUBLISHED 紀錄無法配對。"
                        )

                    if (
                        record.get("sha256")
                        != prepared[publish_id].get("sha256")
                    ):
                        raise ValueError(
                            "發布紀錄 SHA-256 不一致。"
                        )

                    completed.add(publish_id)
                    last_published = record

                elif status == "ABORTED":

                    if publish_id not in prepared:
                        raise ValueError(
                            "ABORTED 缺少對應的 PREPARED。"
                        )

                    if (
                        publish_id in completed
                        or publish_id in aborted
                    ):
                        raise ValueError(
                            "ABORTED 紀錄重複或與完成紀錄衝突。"
                        )

                    if (
                        record.get("sha256")
                        != prepared[publish_id].get("sha256")
                    ):
                        raise ValueError(
                            "取消發布紀錄 SHA-256 不一致。"
                        )

                    aborted.add(publish_id)

        # ========================================
        # 3. 找出未完成發布
        # ========================================

        pending_ids = [
            publish_id
            for publish_id in prepared
            if (
                publish_id not in completed
                and publish_id not in aborted
            )
        ]

        if last_published:

            result["last_published_id"] = (
                last_published.get("publish_id")
            )

        if len(pending_ids) > 1:

            return finish(
                "MANUAL_REVIEW",
                "存在多筆未完成發布紀錄。"
            )

        # ========================================
        # 4. 正常完成狀態
        # ========================================

        if not pending_ids:

            if not last_published:

                return finish(
                    "MANUAL_REVIEW",
                    "沒有有效的完成紀錄。"
                )

            if (
                current_hash
                != last_published.get("sha256")
            ):

                return finish(
                    "MANUAL_REVIEW",
                    "正式 CSV 與最後發布紀錄不一致。"
                )

            if result["lock_exists"]:

                return finish(
                    "MANUAL_REVIEW",
                    "歷程正常，但存在發布鎖定檔，"
                    "須確認是否仍有作業執行。"
                )

            return finish(
                "NORMAL",
                "正式 CSV 與發布歷程一致。"
            )

        # ========================================
        # 5. 檢查未完成發布
        # ========================================

        pending_id = pending_ids[0]

        result["pending_publish_id"] = (
            pending_id
        )

        pending_record = prepared[pending_id]

        pending_hash = pending_record.get(
            "sha256"
        )

        backup_path = pending_record.get(
            "backup_path"
        )

        # 僅允許既有發布的診斷分類。
        # 首次納管異常須人工處理。

        if not last_published:

            return finish(
                "MANUAL_REVIEW",
                "首次納管尚未完成，須人工查核。"
            )

        old_hash = last_published.get(
            "sha256"
        )

        backup_hash = read_hash(
            backup_path
        )

        if (
            not backup_path
            or backup_hash != old_hash
        ):

            return finish(
                "MANUAL_REVIEW",
                "前一版備份不存在或 SHA-256 不一致。"
            )

        # 舊檔仍在，代表新版尚未替換成功。
        if (
            current_hash == old_hash
            and current_hash != pending_hash
        ):

            return finish(
                "RETRY_SAFE",
                "正式 CSV 仍為前一版，"
                "可進一步確認重試條件。"
            )

        # 新檔已存在，但完成紀錄尚未寫入。
        if (
            current_hash == pending_hash
            and current_hash != old_hash
        ):

            return finish(
                "COMPLETION_PENDING",
                "正式 CSV 已更新，"
                "但缺少 PUBLISHED 紀錄。"
            )

        return finish(
            "MANUAL_REVIEW",
            "正式 CSV 無法明確對應"
            "前一版或待發布版本。"
        )

    except (OSError, ValueError, TypeError) as exc:

        return finish(
            "MANUAL_REVIEW",
            "Performance 發布診斷失敗："
            + str(exc)
        )