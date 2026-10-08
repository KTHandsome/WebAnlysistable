def recalculate_sample_rows(
    rows,
    calibration_result,
    calculate_concentration
):
    """
    依目前檢量線重新計算樣品 / QAQC 的分析濃度。

    rows:
        sample_qaqc_rows

    calibration_result:
        必須包含 slope / intercept

    calculate_concentration:
        各分析方法使用的濃度計算函式。
        例如 W434 的 calculate_sample_concentration。
    """

    if not rows:
        return rows

    if not calibration_result:
        return rows

    slope = calibration_result.get(
        "slope"
    )

    intercept = calibration_result.get(
        "intercept"
    )

    if (
        slope is None
        or intercept is None
    ):
        return rows

    for row in rows:

        role = (
            row.get(
                "role",
                ""
            )
            .strip()
            .upper()
        )

        direct_instrument_roles = {
            "ICBK",
            "ICV",
            "CCBK",
            "CCV"
        }

        try:

            signal = float(
                row.get(
                    "signal"
                )
            )

            if role in direct_instrument_roles:

                sample_volume = 1.0
                final_volume = 1.0

            else:

                apply_volume_factor = row.get(
                    "apply_volume_factor",
                    True
                )

                if apply_volume_factor:

                    sample_volume = float(
                        row.get(
                            "sample_volume",
                            25
                        )
                    )

                    final_volume = float(
                        row.get(
                            "final_volume",
                            50
                        )
                    )

                else:

                    sample_volume = 1.0
                    final_volume = 1.0

            if role in direct_instrument_roles:
                dilution_factor = 1.0
                sample_prep_factor = 1.0
            else:
                dilution_factor = float(
                    row.get("dilution_factor", 1)
                )
                sample_prep_factor = float(
                    row.get("sample_prep_factor", 1)
                )

            reagent_blank = float(
                calibration_result.get("reagent_blank", 0.0)
            )

            result = (
                calculate_concentration(
                    signal=signal - reagent_blank,
                    slope=slope,
                    intercept=intercept,
                    sample_volume=sample_volume,
                    final_volume=final_volume,
                    dilution_factor=dilution_factor
                )
            )

            # 原計算已包含體積倍率與額外稀釋 D，
            # 此處只補上方法固定前處理倍率。
            sample_concentration = result.get(
                "sample_concentration",
                result.get("calculated_concentration")
            )

            if sample_concentration is not None:
                sample_concentration *= sample_prep_factor

            result["sample_concentration"] = (
                sample_concentration
            )
            result["calculated_concentration"] = (
                sample_concentration
            )

            row[
                 "measured_concentration"
                ] = result.get(
    "measured_concentration",
    result.get(
        "back_calculated_concentration"
    )
)

            row[
                 "sample_concentration"
                ] = result.get(
                 "sample_concentration",
                 result.get(
                 "calculated_concentration"
                 )
                )

            # 舊欄位暫時保留
            # 相容既有 PDF / LIMS / DB / JS
            row[
                 "calculated_concentration"
                ] = result.get(
                 "calculated_concentration"
                )

            role = str(
                  row.get(
                   "role",
                    ""
                   )
                 or ""
                ).strip().upper()

            if role in {
                "ICV",
                "CCV"
             }:
              row[
                    "qaqc_concentration"
                    ] = row.get(
                    "measured_concentration"
                    )
            else:
              row[
                    "qaqc_concentration"
                    ] = row.get(
                      "sample_concentration"
                    )

        except (
               TypeError,
               ValueError
              ):

            row[
                 "measured_concentration"
                ] = None

            row[
                 "sample_concentration"
                ] = None

            row[
                "calculated_concentration"
               ] = None

            row[
                "qaqc_concentration"
               ] = None

    return rows

def sync_sample_rows_to_batches(
    sample_rows,
    included_batches
):
    """
    將最新的樣品 / QAQC 計算結果同步到批次資料。

    sample_rows:
        sample_qaqc_rows
        為樣品 / QAQC 最新計算結果的主要來源。

    included_batches:
        只負責保存批次結構，
        QA/QC 判定前由此函式同步最新 row 資料。
    """

    if not sample_rows:
        return included_batches

    if not included_batches:
        return included_batches

    latest_row_map = {
        str(
            row.get(
                "sequence_no",
                ""
            )
        ): row
        for row in sample_rows
    }

    for batch in included_batches:

        # ------------------------------------
        # Batch 內所有資料列
        # ------------------------------------
        for batch_row in batch.get(
            "rows",
            []
        ):

            sequence_key = str(
                batch_row.get(
                    "sequence_no",
                    ""
                )
            )

            latest_row = (
                latest_row_map.get(
                    sequence_key
                )
            )

            if latest_row is None:
                continue

            batch_row.update(
                latest_row
            )

        # ------------------------------------
        # Batch 起始 / 結束 QAQC
        # ------------------------------------
        for check_name in (
            "start_check",
            "end_check"
        ):

            check_row = batch.get(
                check_name
            )

            if not check_row:
                continue

            sequence_key = str(
                check_row.get(
                    "sequence_no",
                    ""
                )
            )

            latest_row = (
                latest_row_map.get(
                    sequence_key
                )
            )

            if latest_row is None:
                continue

            check_row.update(
                latest_row
            )

    return included_batches