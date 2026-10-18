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


report_settings_import_bp = Blueprint(
    "report_settings_import_bp",
    __name__,
)


@report_settings_import_bp.route("/report-settings-import", methods=["POST"])
@login_required
def report_settings_import():

    uploaded_file = request.files.get(
        "report_csv_file"
    )

    report_success_message = None
    report_error_message = None

    if (
        uploaded_file is None
        or uploaded_file.filename == ""
    ):

        report_error_message = (
            "請選擇報表設定 CSV 檔案。"
        )

    elif not uploaded_file.filename.lower().endswith(
        ".csv"
    ):

        report_error_message = (
            "只能匯入 CSV 檔案。"
        )

    else:

        try:

            file_bytes = uploaded_file.read()

            try:

                csv_text = file_bytes.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError:

                csv_text = None

                report_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "VERSION",
                    "EFFECTIVE_DATE",
                    "REPORT_CODE",
                    "COMPANY_NAME",
                    "FORM_TITLE",
                    "DOC_NO",
                    "REVISION",
                    "ISSUE_DATE",
                    "ACTIVE",
                    "REMARK"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns
                    - actual_columns
                )

                if missing_columns:

                    report_error_message = (
                        "報表設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(
                                missing_columns
                            )
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        report_error_message = (
                            "報表設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []
                        report_keys = set()

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            version = row.get(
                                "VERSION",
                                ""
                            ).strip()

                            effective_date = row.get(
                                "EFFECTIVE_DATE",
                                ""
                            ).strip()

                            report_code = row.get(
                                "REPORT_CODE",
                                ""
                            ).strip()

                            company_name = row.get(
                                "COMPANY_NAME",
                                ""
                            ).strip()

                            form_title = row.get(
                                "FORM_TITLE",
                                ""
                            ).strip()

                            doc_no = row.get(
                                "DOC_NO",
                                ""
                            ).strip()

                            revision = row.get(
                                "REVISION",
                                ""
                            ).strip()

                            issue_date = row.get(
                                "ISSUE_DATE",
                                ""
                            ).strip()

                            active = row.get(
                                "ACTIVE",
                                ""
                            ).strip().upper()

                            if not version:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：VERSION 不可空白。"
                                )

                            if not effective_date:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：EFFECTIVE_DATE 不可空白。"
                                )

                            else:

                                try:

                                    from datetime import datetime

                                    datetime.strptime(
                                        effective_date,
                                        "%Y-%m-%d"
                                    )

                                except ValueError:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：EFFECTIVE_DATE 必須為 yyyy-MM-dd。"
                                    )

                            if not report_code:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：REPORT_CODE 不可空白。"
                                )

                            if not company_name:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：COMPANY_NAME 不可空白。"
                                )

                            if not form_title:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：FORM_TITLE 不可空白。"
                                )

                            if not doc_no:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：DOC_NO 不可空白。"
                                )

                            if not revision:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：REVISION 不可空白。"
                                )

                            if not issue_date:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ISSUE_DATE 不可空白。"
                                )

                            if active not in {
                                "Y",
                                "N"
                            }:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ACTIVE 只能是 Y 或 N。"
                                )

                            if report_code and version:

                                report_key = (
                                    report_code.upper(),
                                    version.upper()
                                )

                                if report_key in report_keys:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：REPORT_CODE + VERSION 重複："
                                        + report_code
                                        + " / "
                                        + version
                                    )

                                else:

                                    report_keys.add(
                                        report_key
                                    )

                        if validation_errors:

                            report_error_message = (
                                "報表設定 CSV 驗證失敗："
                                + "<br>"
                                + "<br>".join(
                                    validation_errors[:20]
                                )
                            )

                        else:

                            data_folder = os.path.join(
                                current_app.root_path,
                                "data"
                            )

                            os.makedirs(
                                data_folder,
                                exist_ok=True
                            )

                            save_path = os.path.join(
                                data_folder,
                                "Phyon_Report_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(
                                    file_bytes
                                )

                            report_success_message = (
                                "報表設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )

        except Exception as ex:

            report_error_message = (
                "報表設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=report_success_message,
        report_error_message=report_error_message,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

