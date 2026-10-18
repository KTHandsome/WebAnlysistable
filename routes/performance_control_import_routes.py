import csv
import io
import math
import os

from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
)

from auth_session import (
    login_required,
    can_manage_performance_control,
    get_current_user,
)

from database import SessionLocal

from services.performance_diff_service import (
    compare_performance_csv,
)

from services.performance_release_service import (
    PerformanceReleaseNeedsReview,
    release_performance_csv_to_database,
)


performance_control_import_bp = Blueprint(
    "performance_control_import_bp",
    __name__,
)


@performance_control_import_bp.route(
    "/performance-control-import",
    methods=["POST"]
)
@login_required
def performance_control_import():

    success_message = None
    error_message = None
    performance_diff = None

    uploaded_file = request.files.get(
        "performance_csv_file"
    )

    try:

        # ========================================
        # Performance CSV 操作模式判斷
        # ========================================

        performance_action = str(
            request.form.get(
                "performance_action",
                "validate"
            )
            or ""
        ).strip().lower()

        if performance_action not in {
            "validate",
            "publish"
        }:
            raise ValueError(
                "未知的 Performance CSV 操作模式。"
            )

        # ========================================
        # Performance 正式發布總開關
        # ========================================
        ENABLE_PERFORMANCE_WRITE = True

        if (
            performance_action == "publish"
            and not ENABLE_PERFORMANCE_WRITE
        ):
            raise ValueError(
                "Performance 正式發布功能尚未啟用。"
            )

        # ========================================
        # Performance 正式發布提前檢查權限
        # ========================================

        if (
            performance_action == "publish"
            and not can_manage_performance_control()
        ):
            raise ValueError(
                "您沒有 Performance 管制資料發布權限。"
            )

        # ========================================
        # 1. 檢查上傳檔案
        # ========================================
        if (
            uploaded_file is None
            or not uploaded_file.filename
        ):
            raise ValueError(
                "請選擇 Performance 管制 CSV。"
            )

        if not uploaded_file.filename.lower().endswith(".csv"):
            raise ValueError(
                "只能匯入 CSV 檔案。"
            )

        file_bytes = uploaded_file.read(
            2 * 1024 * 1024 + 1
        )

        if len(file_bytes) > 2 * 1024 * 1024:
            raise ValueError(
                "CSV 檔案不可超過 2 MB。"
            )

        # ========================================
        # 2. 檢查 UTF-8 編碼
        # ========================================
        try:
            csv_text = file_bytes.decode(
                "utf-8-sig"
            )

        except UnicodeDecodeError:
            raise ValueError(
                "CSV 必須使用 UTF-8 編碼。"
            )

        reader = csv.DictReader(
            io.StringIO(csv_text)
        )

        # ========================================
        # 3. 必要欄位
        # ========================================
        required_columns = {
            "CONTROL_ID",
            "INSTRUMENT_ID",
            "INSTRUMENT_MODEL",
            "YEAR",
            "EFFECTIVE_FROM",
            "EFFECTIVE_TO",
            "PERFORMANCE_TYPE",
            "MONITOR_ITEM",
            "LOWER_LIMIT",
            "UPPER_LIMIT",
            "SAMPLE_LABELS",
            "CONTROL_VERSION",
            "ENABLED",
        }

        fieldnames = reader.fieldnames or []
        actual_columns = set(fieldnames)

        if None in actual_columns or "" in actual_columns:
            raise ValueError(
                "CSV 標題欄位不可空白。"
            )

        if len(fieldnames) != len(actual_columns):
            raise ValueError(
                "CSV 標題欄位不可重複。"
            )

        missing_columns = (
            required_columns - actual_columns
        )

        if missing_columns:
            raise ValueError(
                "CSV 缺少必要欄位："
                + ", ".join(sorted(missing_columns))
            )

        # ========================================
        # 4. 讀取資料
        # ========================================
        rows = list(reader)

        if not rows:
            raise ValueError(
                "CSV 沒有任何 Performance 管制資料。"
            )

        # 記錄管制編號，避免同一 CSV 重複
        seen_control_ids = set()

        # ========================================
        # Performance 有效期間檢查索引
        # 僅記錄 ENABLED=Y 的管制資料
        # ========================================
        active_control_periods = {}   
        
        allowed_performance_types = {
            "SIGNAL_RATIO",
            "SIGNAL_INTENSITY",
            "CAL_HIGH_SIGNAL",
            "RELATIVE_CHANGE",
            "INSTRUMENT_CHECK",
        }

        # ========================================
        # Performance：載入既有儀器設定
        # INSTRUMENT_ID 對應 LABPARTID
        # ========================================

        instrument_file = os.path.join(
           current_app.root_path,
           "data",
           "Phyon_Instrument_Settings.csv"
        )

        if not os.path.isfile(instrument_file):
           raise ValueError(
            "尚未匯入儀器設定資料，"
            "無法驗證 Performance 儀器編號。"
        )

        instrument_map = {}

        with open(
           instrument_file,
           "r",
           encoding="utf-8-sig",
           newline=""
        ) as f:

          instrument_reader = csv.DictReader(f)

          if not {"LABPARTID", "MODAL"}.issubset(
             set(instrument_reader.fieldnames or [])
          ):
             raise ValueError(
                "儀器設定 CSV 缺少 LABPARTID 或 MODAL 欄位。"
            )

          for instrument_row in instrument_reader:

              labpartid = str(
              instrument_row.get("LABPARTID") or ""
               ).strip().upper()

              modal = str(
              instrument_row.get("MODAL") or ""
               ).strip().upper()

              if not labpartid:
                 continue

              if labpartid in instrument_map:
                 raise ValueError(
                   "儀器設定存在重複 LABPARTID："
                   + labpartid
               )

              instrument_map[labpartid] = modal

        for row_number, row in enumerate(
            rows,
            start=2
        ):

            if None in row:
                raise ValueError(
                    "第 {} 列：欄位數量超出 CSV 標題。"
                    .format(row_number)
                )

            for field in required_columns:

                # 上下限可依監測方式另行驗證，
                # 此階段先允許空白。
                if field in {
                    "LOWER_LIMIT",
                    "UPPER_LIMIT",
                }:
                    continue

                value = str(
                    row.get(field) or ""
                ).strip()

                if not value:
                    raise ValueError(
                        "第 {} 列：{} 不可空白。"
                        .format(
                            row_number,
                            field
                        )
                    )

            enabled = str(
                row.get("ENABLED") or ""
            ).strip().upper()

            if enabled not in {"Y", "N"}:
                raise ValueError(
                    "第 {} 列：ENABLED 必須為 Y 或 N。"
                    .format(row_number)
                )

            # ========================================
            # 5. 年度與日期驗證
            # ========================================

            year_text = str(
               row.get("YEAR") or ""
            ).strip()

            try:
                control_year = int(year_text)

                if len(year_text) != 4 or control_year < 2000:
                   raise ValueError()

            except ValueError:
                raise ValueError(
                  "第 {} 列：YEAR 必須為有效的四位西元年度。"
                   .format(row_number)
                        )

            # ========================================
            # Performance 有效日期格式
            # 支援 YYYY/MM/DD、YYYY-MM-DD
            # ========================================

            try:
                effective_from_text = str(
                row.get("EFFECTIVE_FROM") or ""
                ).strip().replace("/", "-")

                effective_to_text = str(
                row.get("EFFECTIVE_TO") or ""
                ).strip().replace("/", "-")

                effective_from = datetime.strptime(
                effective_from_text,
                "%Y-%m-%d"
                ).date()

                effective_to = datetime.strptime(
                effective_to_text,
                "%Y-%m-%d"
                ).date()

            except ValueError:
                raise ValueError(
                  "第 {} 列：有效日期必須為 YYYY/MM/DD "
                  "或 YYYY-MM-DD。"
                  .format(row_number)
                ) 

            if effective_from > effective_to:
               raise ValueError(
                "第 {} 列：生效日期不可晚於截止日期。"
                .format(row_number)
            )

            if not (
               effective_from.year <= control_year <= effective_to.year
            ):
                raise ValueError(
                "第 {} 列：YEAR 必須落在有效期間涵蓋的年度內。"
                .format(row_number)
            )

            # ========================================
            # 6. 監測類型驗證
            # ========================================

            performance_type = str(
                row.get("PERFORMANCE_TYPE") or ""
               ).strip().upper()

            if performance_type not in allowed_performance_types:
               raise ValueError(
               "第 {} 列：不支援的 PERFORMANCE_TYPE：{}"
                .format(row_number, performance_type)
            )

            # ========================================
            # 7. 管制上下限驗證
            # ========================================

            lower_text = str(
               row.get("LOWER_LIMIT") or ""
            ).strip()

            upper_text = str(
              row.get("UPPER_LIMIT") or ""
            ).strip()

            if lower_text or upper_text:

               if not lower_text or not upper_text:
                  raise ValueError(
                  "第 {} 列：管制上下限必須同時設定。"
                  .format(row_number)
                )

               try:
                   lower_limit = float(lower_text)
                   upper_limit = float(upper_text)

               except ValueError:
                   raise ValueError(
                    "第 {} 列：管制上下限必須為數字。"
                    .format(row_number)
                )

               if not (
                     math.isfinite(lower_limit)
                     and math.isfinite(upper_limit)
                ):
                 raise ValueError(
                 "第 {} 列：管制上下限必須為有限數值。"
                  .format(row_number)
                 )

               if lower_limit > upper_limit:
                 raise ValueError(
                  "第 {} 列：管制下限不可大於上限。"
                   .format(row_number)
                )

            elif enabled == "Y":
                raise ValueError(
                 "第 {} 列：啟用中的 Performance 管制資料"
                 "必須設定上下限。"
                 .format(row_number)
            )

            # ========================================
            # 8. 管制編號重複檢查
            # ========================================

            control_id = str(
                row.get("CONTROL_ID") or ""
            ).strip().upper()

            if control_id in seen_control_ids:
               raise ValueError(
                "第 {} 列：CONTROL_ID 重複：{}"
                 .format(row_number, control_id)
             )

            seen_control_ids.add(control_id)
            
            # ========================================
            # Performance：儀器編號及型號驗證
            # ========================================

            instrument_id = str(
              row.get("INSTRUMENT_ID") or ""
              ).strip().upper()

            instrument_model = str(
              row.get("INSTRUMENT_MODEL") or ""
              ).strip().upper()

            if instrument_id not in instrument_map:
               raise ValueError(
               "第 {} 列：找不到儀器編號 {}，"
               "請確認 Phyon_Instrument_Settings.csv。"
               .format(row_number, instrument_id)
            )

            registered_model = instrument_map[instrument_id]

            if (
                 registered_model
                 and registered_model != instrument_model
            ):
               raise ValueError(
               "第 {} 列：儀器 {} 的型號不一致。"
               "Performance CSV：{}；儀器設定：{}。"
               .format(
                      row_number,
                      instrument_id,
                      instrument_model,
                      registered_model
                 )
            )

            # ========================================
            # Performance：監測類型專屬欄位驗證
            # 僅檢查 ENABLED=Y 的資料
            # ========================================

            if enabled == "Y":

                monitor_item = str(
                    row.get("MONITOR_ITEM") or ""
                ).strip()

                numerator_item = str(
                    row.get("NUMERATOR_ITEM") or ""
                ).strip()

                denominator_item = str(
                    row.get("DENOMINATOR_ITEM") or ""
                ).strip()

                if performance_type == "SIGNAL_RATIO":

                    if not numerator_item:
                        raise ValueError(
                            "第 {} 列：SIGNAL_RATIO "
                            "必須設定 NUMERATOR_ITEM。"
                            .format(row_number)
                        )

                    if not denominator_item:
                        raise ValueError(
                            "第 {} 列：SIGNAL_RATIO "
                            "必須設定 DENOMINATOR_ITEM。"
                            .format(row_number)
                        )

                    if (
                        numerator_item.upper()
                        == denominator_item.upper()
                    ):
                        raise ValueError(
                            "第 {} 列：SIGNAL_RATIO "
                            "分子與分母不可為相同項目。"
                            .format(row_number)
                        )

                elif performance_type == "CAL_HIGH_SIGNAL":

                    if not monitor_item:
                        raise ValueError(
                            "第 {} 列：CAL_HIGH_SIGNAL "
                            "必須設定 MONITOR_ITEM。"
                            .format(row_number)
                        )

            # ========================================
            # Performance：有效期間重疊檢查
            # ========================================

            if enabled == "Y":

               monitor_item = str(
               row.get("MONITOR_ITEM") or ""
               ).strip().upper()

               # 同一儀器 + 監測類型 + 監測項目
               control_key = (
                instrument_id,
                performance_type,
                monitor_item
            )

               previous_periods = active_control_periods.get(
               control_key,
               []
            )

               for previous in previous_periods:

                   previous_from = previous["from"]
                   previous_to = previous["to"]

                   # 兩個閉區間有交集即視為重疊
                   is_overlap = (
                   effective_from <= previous_to
                   and effective_to >= previous_from
                )

                   if is_overlap:
                      raise ValueError(
                        "第 {} 列：Performance 管制有效期間重疊。"
                        "儀器：{}，監測項目：{}，"
                        "與第 {} 列的有效期間衝突。"
                        .format(
                        row_number,
                        instrument_id,
                        monitor_item,
                        previous["row_number"]
                       )
                    )

               active_control_periods.setdefault(
               control_key,
               []
               ).append({
                 "from": effective_from,
                 "to": effective_to,
                 "row_number": row_number
        })

        # ========================================
        # Performance CSV 差異摘要
        # ========================================

        official_path = os.path.join(
            current_app.root_path,
            "data",
            "Phyon_Instrument_Performance_Control.csv"
        )

        performance_diff = compare_performance_csv(
            official_path=official_path,
            candidate_bytes=file_bytes
        )

        # ========================================
        # Performance CSV 安全匯入
        # ========================================

        if performance_action == "validate":

            success_message = (
                "Performance CSV 驗證通過，共 {} 筆。"
                "目前為驗證模式，尚未寫入正式管制資料。"
            ).format(len(rows))

        else:

            # ========================================
            # 1. 正式發布權限檢查
            # ========================================

            if not can_manage_performance_control():
                raise ValueError(
                    "您沒有 Performance 管制資料發布權限。"
                )

            # ========================================
            # 2. 正式 CSV 與發布歷程路徑
            # ========================================

            data_folder = os.path.join(
                current_app.root_path,
                "data"
            )

            save_path = os.path.join(
                data_folder,
                "Phyon_Instrument_Performance_Control.csv"
            )

            backup_folder = os.path.join(
                data_folder,
                "backups",
                "performance_control"
            )

            log_path = os.path.join(
                backup_folder,
                "performance_publish_log.jsonl"
            )

            # ========================================
            # 3. 取得實際登入者
            # ========================================

            current_user = get_current_user() or {}

            published_by = str(
                current_user.get("user_id") or ""
            ).strip()

            if not published_by:
                raise ValueError(
                    "無法取得登入者的使用者編號，"
                    "禁止正式發布 Performance 管制資料。"
                )

            # ========================================
            # 4. 呼叫 CSV / JSONL / SQLite 整合發布
            # ========================================

            archive_dir = os.path.join(
                backup_folder,
                "db_imports"
            )

            release_result = (
                release_performance_csv_to_database(
                    file_bytes=file_bytes,
                    original_filename=uploaded_file.filename,
                    published_by=published_by,
                    save_path=save_path,
                    backup_folder=backup_folder,
                    log_path=log_path,
                    archive_dir=archive_dir,
                    session_factory=SessionLocal
                )
            )

            # ========================================
            # 5. 正式發布成功訊息
            # ========================================

            success_message = (
                "Performance 管制資料正式發布成功，"
                "共 {} 筆。"
                "CSV、JSONL 與 SQLite ACTIVE "
                "已完成一致性核對。"
                "匯入批次：{}"
            ).format(
                release_result["record_count"],
                release_result["import_id"]
            )

    except PerformanceReleaseNeedsReview as exc:

        current_app.logger.error(
            "Performance 發布需要人工核對："
            "stage=%s, import_id=%s",
            exc.stage,
            exc.pending_import_id
        )

        error_message = (
            "Performance 發布尚未完整完成，"
            "請勿重複上傳或再次發布。"
            "異常階段：{}；"
            "待核對批次：{}。"
            "請由管理員檢查發布狀態。"
        ).format(
            exc.stage,
            exc.pending_import_id
        )

    except ValueError as exc:

        error_message = str(exc)

    except Exception:

        current_app.logger.exception(
            "Performance CSV 驗證失敗"
        )

        error_message = (
            "Performance CSV 驗證失敗，"
            "請查看伺服器錯誤紀錄。"
        )

    return render_template(
        "control_import.html",
        performance_success_message=success_message,
        performance_error_message=error_message,
        performance_diff=performance_diff,
        active_page="control"
    )

