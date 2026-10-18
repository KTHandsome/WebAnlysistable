import csv
import io
import os

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
)

from auth_session import login_required


icp_analyte_import_bp = Blueprint(
    "icp_analyte_import_bp",
    __name__,
)


@icp_analyte_import_bp.route("/icp-analyte-import", methods=["POST"])
@login_required
def icp_analyte_import():

    import shutil
    import tempfile
    from datetime import datetime

    success_message = None
    error_message = None

    uploaded_file = request.files.get("icp_analyte_csv_file")

    try:
        if uploaded_file is None or not uploaded_file.filename:
            raise ValueError("請選擇 ICP 適用測項 CSV。")

        if not uploaded_file.filename.lower().endswith(".csv"):
            raise ValueError("只能匯入 CSV 檔案。")

        file_bytes = uploaded_file.read(2 * 1024 * 1024 + 1)

        if len(file_bytes) > 2 * 1024 * 1024:
            raise ValueError("CSV 檔案不可超過 2 MB。")

        try:
            csv_text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("CSV 必須使用 UTF-8 編碼。")

        reader = csv.DictReader(io.StringIO(csv_text))

        required_columns = {
            "EXAMNAME",
            "ELEMENT",
            "ANALYTE_VARIANT",
            "ACTIVE",
            "REMARK",
        }

        actual_columns = set(reader.fieldnames or [])

        if not required_columns.issubset(actual_columns):
            missing = required_columns - actual_columns
            raise ValueError(
                "CSV 缺少欄位：" + ", ".join(sorted(missing))
            )

        if None in actual_columns:
            raise ValueError("CSV 標題欄位不可空白。")

        if len(reader.fieldnames) != len(actual_columns):
            raise ValueError("CSV 標題欄位不可重複。")

        rows = list(reader)

        if not rows:
            raise ValueError("CSV 沒有任何測項資料。")

        valid_elements = {
            "Al", "Sb", "As", "Ba", "Be", "B",
            "Cd", "Ca", "Cr", "Co", "Cu",
            "Ga", "In", "Fe", "Pb", "Li",
            "Mg", "Mn", "Hg", "Mo", "Ni",
            "P", "K", "Se", "Ag", "Na",
            "Sr", "Tl", "Sn", "Ti", "V",
            "Y", "Zn"
        }

        valid_variants = {
            "TOTAL_OR_UNSPECIFIED",
            "DISSOLVED",
        }

        seen_names = set()
        validation_errors = []

        for row_number, row in enumerate(rows, start=2):

            if None in row:
                validation_errors.append(
                    "第 {} 列：欄位數量超出 CSV 標題。".format(
                        row_number
                    )
                )
                continue

            examname = str(
                row.get("EXAMNAME") or ""
            ).strip()

            element = str(
                row.get("ELEMENT") or ""
            ).strip()

            variant = str(
                row.get("ANALYTE_VARIANT") or ""
            ).strip().upper()

            active = str(
                row.get("ACTIVE") or ""
            ).strip().upper()

            if not examname:
                validation_errors.append(
                    "第 {} 列：EXAMNAME 不可空白。".format(
                        row_number
                    )
                )

            elif examname in seen_names:
                validation_errors.append(
                    "第 {} 列：測項名稱重複：{}".format(
                        row_number, examname
                    )
                )

            else:
                seen_names.add(examname)

            if element not in valid_elements:
                validation_errors.append(
                    "第 {} 列：無效元素代碼：{}".format(
                        row_number, element
                    )
                )

            if variant not in valid_variants:
                validation_errors.append(
                    "第 {} 列：無效測項類型：{}".format(
                        row_number, variant
                    )
                )

            if active not in ("Y", "N"):
                validation_errors.append(
                    "第 {} 列：ACTIVE 必須為 Y 或 N。".format(
                        row_number
                    )
                )

            if len(validation_errors) >= 20:
                break

        if validation_errors:
            raise ValueError(
                "CSV 驗證失敗："
                + "；".join(validation_errors)
            )

        # 驗證完成後，才處理正式設定檔
        data_folder = os.path.join(
            current_app.root_path, "data"
        )

        os.makedirs(data_folder, exist_ok=True)

        save_path = os.path.join(
            data_folder,
            "Phyon_ICP_Analyte_Map.csv"
        )

        backup_folder = os.path.join(
            data_folder,
            "backups",
            "icp_analyte"
        )

        os.makedirs(
            backup_folder, exist_ok=True
        )

        temp_path = None

        try:
            # 先建立同目錄暫存檔
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".csv",
                prefix=".icp_analyte_",
                dir=data_folder,
                delete=False
            ) as temp_file:

                temp_path = temp_file.name
                temp_file.write(file_bytes)

            # 正式檔案已存在時，先備份
            if os.path.exists(save_path):

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )

                backup_path = os.path.join(
                    backup_folder,
                    "Phyon_ICP_Analyte_Map_{}.csv".format(
                        timestamp
                    )
                )

                shutil.copy2(
                    save_path,
                    backup_path
                )

            # 同一檔案系統內原子替換
            os.replace(
                temp_path,
                save_path
            )

            temp_path = None

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        success_message = (
            "ICP 適用測項匯入成功，共 {} 筆。"
            .format(len(rows))
        )

    except ValueError as exc:
        error_message = str(exc)

    except Exception:
        current_app.logger.exception(
            "ICP 適用測項 CSV 匯入失敗"
        )
        error_message = (
            "ICP 適用測項匯入失敗，"
            "請查看伺服器錯誤紀錄。"
        )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        icp_analyte_success_message=success_message,
        icp_analyte_error_message=error_message,
        active_page="control"
    )

