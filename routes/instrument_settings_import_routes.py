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


instrument_settings_import_bp = Blueprint(
    "instrument_settings_import_bp",
    __name__,
)


@instrument_settings_import_bp.route("/instrument-settings-import", methods=["POST"])
@login_required
def instrument_settings_import():

    uploaded_file = request.files.get(
        "instrument_csv_file"
    )

    instrument_success_message = None
    instrument_error_message = None

    if (
        uploaded_file is None
        or uploaded_file.filename == ""
    ):

        instrument_error_message = (
            "請選擇儀器設定 CSV 檔案。"
        )

    elif not uploaded_file.filename.lower().endswith(
        ".csv"
    ):

        instrument_error_message = (
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

                instrument_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "LABPARTID",
                    "PARTID",
                    "PARTNAME",
                    "SERIALNO",
                    "MODAL",
                    "PROPERTYNO",
                    "PARTTYPE",
                    "PARTALIAS",
                    "DESCRIPTION",
                    "STATUS",
                    "BRAND",
                    "FACNAME",
                    "LOCATION",
                    "DEPT",
                    "DEPTNAME"
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns
                    - actual_columns
                )

                if missing_columns:

                    instrument_error_message = (
                        "儀器設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(
                                missing_columns
                            )
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        instrument_error_message = (
                            "儀器設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []
                        labpartid_set = set()

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):

                            labpartid = (
                                row.get(
                                    "LABPARTID",
                                    ""
                                )
                                .strip()
                            )

                            if not labpartid:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：LABPARTID 不可空白。"
                                )

                                continue

                            labpartid_key = (
                                labpartid.upper()
                            )

                            if (
                                labpartid_key
                                in labpartid_set
                            ):

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：LABPARTID 重複："
                                    + labpartid
                                )

                            else:

                                labpartid_set.add(
                                    labpartid_key
                                )

                        if validation_errors:

                            instrument_error_message = (
                                "儀器設定 CSV 驗證失敗："
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
                                "Phyon_Instrument_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(
                                    file_bytes
                                )

                            instrument_success_message = (
                                "儀器設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )

        except Exception as ex:

            instrument_error_message = (
                "儀器設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=instrument_success_message,
        instrument_error_message=instrument_error_message,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

