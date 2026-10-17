import csv
import io
import os

from flask import (
    Blueprint,
    current_app,
    request,
    render_template,
)

from auth_session import login_required


control_import_bp = Blueprint(
    "control_import_bp",
    __name__,
)


@control_import_bp.route(
    "/control-import",
    methods=["GET", "POST"]
)
@login_required
def control_import():

    success_message = None
    error_message = None

    if request.method == "POST":

        ctrl_year = request.form.get(
            "ctrl_year", ""
        ).strip()

        uploaded_file = request.files.get(
            "csv_file"
        )

        if not ctrl_year:

            error_message = "請選擇年度。"

        elif uploaded_file is None or uploaded_file.filename == "":

            error_message = "請選擇 CSV 檔案。"

        elif not uploaded_file.filename.lower().endswith(".csv"):

            error_message = "只能匯入 CSV 檔案。"

        else:

            try:

                file_bytes = uploaded_file.read()

                try:
                    csv_text = file_bytes.decode(
                        "utf-8-sig"
                    )

                except UnicodeDecodeError:
                    error_message = (
                        "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                    )
                    csv_text = None

                if csv_text is not None:

                    reader = csv.DictReader(
                        io.StringIO(csv_text)
                    )

                    required_columns = {
                        "CTRL_YEAR",
                        "CATEGORY_CODE",
                        "EXAMNO",
                        "EXAMNAME",
                        "EXALIAS",
                        "EM_NUM",
                        "EM_NO",
                        "LABPARTID",
                        "CTRL_UNIT",
                        "DETECT_LIMITED",
                        "DC_UWL",
                        "DC_UCL",
                        "QC_UWL",
                        "QC_UCL",
                        "QC_LWL",
                        "QC_LCL",
                        "SPIKE_UWL",
                        "SPIKE_UCL",
                        "SPIKE_LWL",
                        "SPIKE_LCL"
                    }

                    actual_columns = set(
                        reader.fieldnames or []
                    )

                    missing_columns = (
                        required_columns - actual_columns
                    )

                    if missing_columns:

                        error_message = (
                            "CSV 格式不正確，缺少必要欄位："
                            + ", ".join(
                                sorted(missing_columns)
                            )
                        )

                    else:

                        rows = list(reader)

                        if len(rows) == 0:

                            error_message = (
                                "CSV 沒有任何管制資料。"
                            )

                        else:

                            invalid_year_rows = []

                            for index, row in enumerate(
                                rows,
                                start=2
                            ):

                                row_year = (
                                    row.get(
                                        "CTRL_YEAR",
                                        ""
                                    ).strip()
                                )

                                if row_year != ctrl_year:

                                    invalid_year_rows.append(
                                        index
                                    )

                            if invalid_year_rows:

                                error_message = (
                                    "CSV 年度與選擇年度不一致。"
                                    "目前選擇："
                                    + ctrl_year
                                    + " 年；錯誤資料列："
                                    + ", ".join(
                                        map(
                                            str,
                                            invalid_year_rows[:10]
                                        )
                                    )
                                )

                            else:

                                # 使用 current_app，避免反向匯入 app.py
                                data_folder = os.path.join(
                                    current_app.root_path,
                                    "data"
                                )

                                os.makedirs(
                                    data_folder,
                                    exist_ok=True
                                )

                                save_name = (
                                    "Phyon_Control_"
                                    + ctrl_year
                                    + ".csv"
                                )

                                save_path = os.path.join(
                                    data_folder,
                                    save_name
                                )

                                with open(
                                    save_path,
                                    "wb"
                                ) as f:

                                    f.write(file_bytes)

                                success_message = (
                                    ctrl_year
                                    + " 年管制資料匯入成功，"
                                    + "共 "
                                    + str(len(rows))
                                    + " 筆。"
                                )

            except Exception as ex:

                error_message = (
                    "匯入管制資料失敗："
                    + str(ex)
                )

    return render_template(
        "control_import.html",
        success_message=success_message,
        error_message=error_message,
        method_success_message=None,
        method_error_message=None,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )