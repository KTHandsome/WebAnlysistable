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


method_settings_import_bp = Blueprint(
    "method_settings_import_bp",
    __name__,
)


@method_settings_import_bp.route("/method-settings-import", methods=["POST"])
@login_required
def method_settings_import():

    uploaded_file = request.files.get("method_csv_file")

    method_success_message = None
    method_error_message = None

    if uploaded_file is None or uploaded_file.filename == "":

        method_error_message = "請選擇方法設定 CSV 檔案。"

    elif not uploaded_file.filename.lower().endswith(".csv"):

        method_error_message = "只能匯入 CSV 檔案。"

    else:

        try:

            file_bytes = uploaded_file.read()

            try:
                csv_text = file_bytes.decode("utf-8-sig")

            except UnicodeDecodeError:

                csv_text = None
                method_error_message = (
                    "CSV 編碼錯誤，必須使用 UTF-8 格式。"
                )

            if csv_text is not None:

                reader = csv.DictReader(
                    io.StringIO(csv_text)
                )

                required_columns = {
                    "VERSION",
                    "EFFECTIVE_DATE",
                    "CATEGORY_CODE",
                    "EXAMNO",
                    "EXAMNAME",
                    "METHOD_CODE",
                    "ANALYTE_DISPLAY",
                    "REPORT_CODE",
                    "MAX_SAMPLE_PER_BATCH",
                    "CALIBRATION_COUNT",
                    "CALIBRATION_VALUES",
                    "CALIBRATION_UNIT",
                    "DATA_ENTRY_MODE",
                    "IMPORT_TYPE",
                    "SIGNAL_FIELD",
                    "ICV_SPIKE_CONC",
                    "QC_SPIKE_CONC",
                    "CCV_SPIKE_CONC",
                    "MS_SPIKE_CONC",
                    "BLANK_MDL_MULTIPLIER",
                    "QDL_SOURCE",
                    "QDL_MULTIPLIER",
                    "ACTIVE",
                    "REMARK",
                    "SAMPLE_VOLUME_DEFAULT",
                    "FINAL_VOLUME_DEFAULT",
                    "APPLY_VOLUME_FACTOR",
                    "SAMPLE_PREP_FACTOR",                    
                    "DISPLAY_CONC_UNIT",
                    "QAQC_CONC_FACTOR",                    
                    "SAMPLE_DILUTION_DEFAULT",
                }

                actual_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    required_columns - actual_columns
                )

                if missing_columns:

                    method_error_message = (
                        "方法設定 CSV 格式不正確，缺少欄位："
                        + ", ".join(
                            sorted(missing_columns)
                        )
                    )

                else:

                    rows = list(reader)

                    if len(rows) == 0:

                        method_error_message = (
                            "方法設定 CSV 沒有任何資料。"
                        )

                    else:

                        validation_errors = []

                        for row_index, row in enumerate(
                            rows,
                            start=2
                        ):
                            decimal_fields = (
                               "UI_CALIBRATION_X_DECIMALS",
                               "UI_SIGNAL_DECIMALS",
                               "UI_CONCENTRATION_DECIMALS",
                               "UI_CALIBRATION_BACKCALC_DECIMALS",
                               "PDF_CALIBRATION_X_DECIMALS",
                               "PDF_SIGNAL_DECIMALS",
                               "PDF_CONCENTRATION_DECIMALS",
                               "PDF_CALIBRATION_BACKCALC_DECIMALS",
                            )

                            for field_name in decimal_fields:
                               decimal_text = str(
                               row.get(field_name, "") or ""
                                ).strip()

                               # 留空時，沿用原本顯示位數
                               if not decimal_text:
                                  continue

                               if (
                                     not decimal_text.isascii()
                                     or not decimal_text.isdecimal()
                                     or not 0 <= int(decimal_text) <= 10
                                  ):
                                     validation_errors.append(
                                     f"第 {row_index} 列：{field_name} "
                                     "必須為 0～10 的整數，或留空。"
                                   )

                            exam_no = row.get(
                                "EXAMNO",
                                ""
                            ).strip()

                            method_code = row.get(
                                "METHOD_CODE",
                                ""
                            ).strip()

                            analyte_display = row.get(
                                "ANALYTE_DISPLAY",
                                ""
                            ).strip()

                            report_code = row.get(
                                "REPORT_CODE",
                                ""
                            ).strip()
                            

                            max_sample_text = row.get(
                                "MAX_SAMPLE_PER_BATCH",
                                ""
                            ).strip()

                            calibration_count_text = row.get(
                                "CALIBRATION_COUNT",
                                ""
                            ).strip()

                            calibration_values_text = row.get(
                                "CALIBRATION_VALUES",
                                ""
                            ).strip()

                            data_entry_mode = row.get(
                                 "DATA_ENTRY_MODE",
                                 ""
                            ).strip().upper()

                            import_type = row.get(
                                "IMPORT_TYPE",
                                ""
                            ).strip().upper()

                            signal_field = row.get(
                                "SIGNAL_FIELD",
                                ""
                            ).strip().upper()


                            blank_mdl_multiplier_text = row.get(
                               "BLANK_MDL_MULTIPLIER",
                               ""
                            ).strip()

                            qdl_source = row.get(
                               "QDL_SOURCE",
                               ""
                            ).strip().upper()

                            qdl_multiplier_text = row.get(
                               "QDL_MULTIPLIER",
                               ""
                            ).strip()     

                            sample_volume_default_text = row.get(
                               "SAMPLE_VOLUME_DEFAULT",
                                ""
                            ).strip()

                            final_volume_default_text = row.get(
                              "FINAL_VOLUME_DEFAULT",
                               ""
                            ).strip()

                            apply_volume_factor = row.get(
                               "APPLY_VOLUME_FACTOR",
                               ""
                            ).strip().upper()

                            display_conc_unit = row.get(
                              "DISPLAY_CONC_UNIT",
                               ""
                            ).strip()

                            qaqc_conc_factor_text = row.get(
                             "QAQC_CONC_FACTOR",
                             ""
                            ).strip()                    

                            active = row.get(
                                "ACTIVE",
                                ""
                            ).strip().upper()

                            analysis_mode = str(
                                row.get("ANALYSIS_MODE", "")
                                or "SINGLE"
                            ).strip().upper() or "SINGLE"

                            if analysis_mode not in {
                                "SINGLE",
                                "MULTI_ANALYTE",
                            }:
                                validation_errors.append(
                                    f"第 {row_index} 列："
                                    "ANALYSIS_MODE 必須為 "
                                    "SINGLE 或 MULTI_ANALYTE。"
                                )

                            # EXAMNO
                            if not exam_no:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：EXAMNO 不可空白。"
                                )

                            # METHOD_CODE
                            if not method_code:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：METHOD_CODE 不可空白。"
                                )

                            # ANALYTE_DISPLAY
                            if not analyte_display:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ANALYTE_DISPLAY 不可空白。"
                                )    

                            # REPORT_CODE
                            if not report_code:

                                validation_errors.append(
                                     "第 "
                                     + str(row_index)
                                     + " 列：REPORT_CODE 不可空白。"
                                )    

                            # MAX_SAMPLE_PER_BATCH
                            try:

                                max_sample_per_batch = int(
                                    max_sample_text
                                )

                                if max_sample_per_batch <= 0:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：MAX_SAMPLE_PER_BATCH 必須大於 0。"
                                    )

                            except ValueError:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：MAX_SAMPLE_PER_BATCH 必須是整數。"
                                )

                            # CALIBRATION_COUNT
                            try:

                                calibration_count = int(
                                    calibration_count_text
                                )

                                if calibration_count <= 0:

                                    validation_errors.append(
                                        "第 "
                                        + str(row_index)
                                        + " 列：CALIBRATION_COUNT 必須大於 0。"
                                    )

                            except ValueError:

                                calibration_count = None

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_COUNT 必須是整數。"
                                )

                            # CALIBRATION_VALUES
                            calibration_values = []

                            if not calibration_values_text:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_VALUES 不可空白。"
                                )

                            else:

                                raw_values = (
                                    calibration_values_text.split("|")
                                )

                                for value in raw_values:

                                    value = value.strip()

                                    try:

                                        calibration_values.append(
                                            float(value)
                                        )

                                    except ValueError:

                                        validation_errors.append(
                                            "第 "
                                            + str(row_index)
                                            + " 列：CALIBRATION_VALUES 含有非數字資料："
                                            + value
                                        )

                            if (
                                calibration_count is not None
                                and len(calibration_values) > 0
                                and len(calibration_values)
                                != calibration_count
                            ):

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：CALIBRATION_COUNT = "
                                    + str(calibration_count)
                                    + "，但 CALIBRATION_VALUES 實際有 "
                                    + str(len(calibration_values))
                                    + " 個。"
                                )

                            # DATA_ENTRY_MODE
                            allowed_data_entry_modes = {
                                "MANUAL",
                                "IMPORT",
                                "BOTH"
                            }

                            if data_entry_mode not in allowed_data_entry_modes:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：DATA_ENTRY_MODE 只能是 MANUAL、IMPORT 或 BOTH。"
                                )

                            if data_entry_mode in {"IMPORT", "BOTH"}:

                                if not import_type:

                                     validation_errors.append(
                                         "第 "
                                          + str(row_index)
                                          + " 列：IMPORT_TYPE 不可空白。"
                                     )

                                if not signal_field:

                                    validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：SIGNAL_FIELD 不可空白。"
                                    )

                            # ACTIVE
                            if active not in {
                                "Y",
                                "N"
                            }:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：ACTIVE 只能是 Y 或 N。"
                                )                           
  
                            # QA/QC 預設添加濃度
                            spike_fields = [
                               "ICV_SPIKE_CONC",
                               "QC_SPIKE_CONC",
                               "CCV_SPIKE_CONC",
                               "MS_SPIKE_CONC"
                            ]
                            for field_name in spike_fields:

                               value_text = row.get(
                               field_name,
                                ""
                               ).strip()
                               if value_text == "":
                                 continue

                               try:
                                  value = float(value_text)

                               except ValueError:

                                validation_errors.append(
                                  "第 "
                                  + str(row_index)
                                  + " 列："
                                  + field_name
                                  + " 必須為數字。"
                                 )

                                continue

                               if value < 0:

                                 validation_errors.append(
                                  "第 "
                                  + str(row_index)
                                  + " 列："
                                  + field_name
                                  + " 不可小於 0。"
                                 )

                            # Blank MDL 倍數
                            if blank_mdl_multiplier_text == "":

                               validation_errors.append(
                               "第 "
                               + str(row_index)
                               + " 列：BLANK_MDL_MULTIPLIER 不可空白。"
                               )

                            else:

                               try:
                                   blank_mdl_multiplier = float(
                                   blank_mdl_multiplier_text
                                  )

                                   if blank_mdl_multiplier <= 0:

                                     validation_errors.append(
                                      "第 "
                                      + str(row_index)
                                      + " 列：BLANK_MDL_MULTIPLIER 必須大於 0。"
                                       )

                               except ValueError:

                                   validation_errors.append(
                                    "第 "
                                   + str(row_index)
                                    + " 列：BLANK_MDL_MULTIPLIER 必須為數字。"
                                    )


                            # QDL 來源
                            allowed_qdl_sources = {
                                 "FIRST_NONZERO_CALIBRATION_X",
                                 "LIMS_QDL"
                                  }

                            if qdl_source not in allowed_qdl_sources:

                               validation_errors.append(
                                "第 "
                                + str(row_index)
                                + " 列：QDL_SOURCE 不支援："
                                + qdl_source
                                 )


                            # QDL 倍數
                            if qdl_multiplier_text == "":

                                validation_errors.append(
                                "第 "
                                 + str(row_index)
                                 + " 列：QDL_MULTIPLIER 不可空白。"
                                  )

                            else:

                                try:
                                    qdl_multiplier = float(
                                    qdl_multiplier_text
                                     )

                                    if qdl_multiplier <= 0:

                                         validation_errors.append(
                                          "第 "
                                         + str(row_index)
                                             + " 列：QDL_MULTIPLIER 必須大於 0。"
                                          )

                                except ValueError:

                                     validation_errors.append(
                                     "第 "
                                      + str(row_index)
                                        + " 列：QDL_MULTIPLIER 必須為數字。"
                                       )

                            # 樣品預設取樣體積
                            if sample_volume_default_text == "":

                              validation_errors.append(
                                 "第 "
                                 + str(row_index)
                                 + " 列：SAMPLE_VOLUME_DEFAULT 不可空白。"
                                )

                            else:

                                 try:

                                      sample_volume_default = float(
                                      sample_volume_default_text
                                      )

                                      if sample_volume_default <= 0:

                                       validation_errors.append(
                                       "第 "
                                       + str(row_index)
                                       + " 列：SAMPLE_VOLUME_DEFAULT 必須大於 0。"
                                      )

                                 except ValueError:

                                       validation_errors.append(
                                       "第 "
                                       + str(row_index)
                                       + " 列：SAMPLE_VOLUME_DEFAULT 必須為數字。"
                                        )


                            # 最終定量體積
                            if final_volume_default_text == "":

                                 validation_errors.append(
                                 "第 "
                                 + str(row_index)
                                 + " 列：FINAL_VOLUME_DEFAULT 不可空白。"
                                  )

                            else:

                                 try:

                                      final_volume_default = float(
                                      final_volume_default_text
                                      )

                                      if final_volume_default <= 0:

                                           validation_errors.append(
                                            "第 "
                                          + str(row_index)
                                          + " 列：FINAL_VOLUME_DEFAULT 必須大於 0。"
                                          )

                                 except ValueError:

                                       validation_errors.append(
                                       "第 "
                                       + str(row_index)
                                       + " 列：FINAL_VOLUME_DEFAULT 必須為數字。"
                                )
                            
                            # 是否套用體積換算因子
                            if apply_volume_factor not in {
                                "Y",
                                "N"
                                 }:

                                validation_errors.append(
                                    "第 "
                                    + str(row_index)
                                    + " 列：APPLY_VOLUME_FACTOR "
                                    "只能是 Y 或 N。"
                                    )



                           # 畫面濃度單位
                            if not display_conc_unit:

                                 validation_errors.append(
                                 "第 "
                                  + str(row_index)
                                  + " 列：DISPLAY_CONC_UNIT 不可空白。"
                                  )


                            # QA/QC 濃度換算倍率
                            if qaqc_conc_factor_text == "":

                                   validation_errors.append(
                                   "第 "
                                   + str(row_index)
                                   + " 列：QAQC_CONC_FACTOR 不可空白。"
                                   )

                            else:

                                try:

                                       qaqc_conc_factor = float(
                                       qaqc_conc_factor_text
                                        )

                                       if qaqc_conc_factor <= 0:

                                          validation_errors.append(
                                          "第 "
                                          + str(row_index)
                                          + " 列：QAQC_CONC_FACTOR 必須大於 0。"
                                          )

                                except ValueError:

                                          validation_errors.append(
                                           "第 "
                                           + str(row_index)
                                          + " 列：QAQC_CONC_FACTOR 必須為數字。"
                                           )

                            sample_dilution_default_text = (
                                     row.get(
                                     "SAMPLE_DILUTION_DEFAULT",
                                     ""
                                     )
                                     .strip()
                            )

                            try:
                                sample_dilution_default = float(
                                sample_dilution_default_text
                                )

                                if sample_dilution_default <= 0:
                                         validation_errors.append(
                                         f"第 {row_index} 列 SAMPLE_DILUTION_DEFAULT "
                                         "必須大於 0。"
                                          )

                            except ValueError:

                               validation_errors.append(
                               f"第 {row_index} 列 SAMPLE_DILUTION_DEFAULT "
                               "必須為數字。"
                              )                                    

                        if validation_errors:

                            method_error_message = (
                                "方法設定 CSV 驗證失敗："
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
                                "Phyon_Method_Settings.csv"
                            )

                            with open(
                                save_path,
                                "wb"
                            ) as f:

                                f.write(file_bytes)

                            method_success_message = (
                                "方法設定匯入成功，共 "
                                + str(len(rows))
                                + " 筆。"
                            )
  
        except Exception as ex:
           method_error_message = (
                "方法設定匯入失敗："
                + str(ex)
            )

    return render_template(
        "control_import.html",
        success_message=None,
        error_message=None,
        method_success_message=method_success_message,
        method_error_message=method_error_message,
        report_success_message=None,
        report_error_message=None,
        instrument_success_message=None,
        instrument_error_message=None,
        method_instrument_success_message=None,
        method_instrument_error_message=None,
        active_page="control"
    )

