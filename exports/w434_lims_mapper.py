from exports.lims_export_model import (
    LimsAnalysisRow,
    LimsExportData,
    LimsQcRow
)


def _to_float(value):

    if value in {
        None,
        ""
    }:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def _get_first_qaqc_row(
    qaqc_results,
    role
):

    role = role.strip().upper()

    for batch in qaqc_results or []:

        rows = batch.get(
            "rows",
            []
        )

        for row in rows:

            if (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
                == role
            ):

                return row

    return None


def _get_first_spike_row(
    qaqc_results,
    role
):

    role = role.strip().upper()

    for batch in qaqc_results or []:

        rows = batch.get(
            "spike_recovery",
            []
        )

        for row in rows:

            if (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
                == role
            ):

                return row

    return None


def _get_first_precision(
    qaqc_results
):

    for batch in qaqc_results or []:

        precision = batch.get(
            "precision"
        )

        if precision:
            return precision

    return None


def _get_max_calibration_signal(
    calibration_result
):

    if not calibration_result:
        return None

    points = calibration_result.get(
        "points",
        []
    )

    highest_point = None
    highest_x = None

    for point in points:

        x_value = _to_float(
            point.get(
                "x"
            )
        )

        if x_value is None:
            continue

        if (
            highest_x is None
            or x_value > highest_x
        ):

            highest_x = x_value
            highest_point = point

    if highest_point is None:
        return None

    return _to_float(
        highest_point.get(
            "y"
        )
    )

def _build_batch_no(
    analysis_date,
    exam_no,
    batch_no
):

    date_text = (
        analysis_date
        .strip()
        .replace("-", "/")
    )

    return (
        date_text
        + exam_no
        + "-"
        + str(batch_no)
    )

def _build_lims_result(
    calculated_concentration,
    mdl_value,
    qdl_value
):

    value = _to_float(
        calculated_concentration
    )

    mdl = _to_float(
        mdl_value
    )

    qdl = _to_float(
        qdl_value
    )

    mdl_text = (
        str(mdl_value).strip()
        if mdl_value not in {
            None,
            ""
        }
        else ""
    )

    qdl_text = (
        str(qdl_value).strip()
        if qdl_value not in {
            None,
            ""
        }
        else ""
    )

    if value is None:
        return "", ""

    # 小於 MDL
    if (
        mdl is not None
        and value < mdl
    ):

        return (
            "ND<" + mdl_text,
            "MDL=" + mdl_text
        )

    # 介於 MDL 與 QDL
    if (
        qdl is not None
        and value < qdl
    ):

        return (
            "<" + qdl_text,
            "QDL=" + qdl_text
        )

    # 高於 QDL
    return (
    format(
        value,
        ".6f"
    ),
    ""
)

    value = _to_float(
        calculated_concentration
    )

    mdl = _to_float(
        mdl_value
    )

    qdl = _to_float(
        qdl_value
    )

    if value is None:
        return "", ""

    # 小於 MDL
    if (
        mdl is not None
        and value < mdl
    ):

        return (
            "ND<" + format(mdl, "g"),
            "MDL=" + format(mdl, "g")
        )

    # 介於 MDL 與 QDL
    if (
        qdl is not None
        and value < qdl
    ):

        return (
            "<" + format(qdl, "g"),
            "QDL=" + format(qdl, "g")
        )

    # 高於 QDL
    return (
        format(
            value,
            ".6f"
        ),
        ""
    )


def build_w434_lims_export_data(
    form_data,
    control_data,
    analysis_state,
    analyst=""
):

    export_data = LimsExportData()

    if not analysis_state:
        return export_data

    exam_no = (
        control_data.get(
            "EXAMNO",
            ""
        )
        .strip()
        if control_data
        else ""
    )

    instrument_id = (
        form_data.get(
            "instrument_id",
            ""
        )
        .strip()
        if form_data
        else ""
    )

    analysis_date = (
        form_data.get(
            "analysis_start_date",
            ""
        )
        .strip()
        if form_data
        else ""
    )

    calibration_result = (
        analysis_state.get(
            "calibration_result"
        )
    )

    sample_qaqc_rows = (
        analysis_state.get(
            "sample_qaqc_rows",
            []
        )
    )

    blank_result = ""

    for row in sample_qaqc_rows:

      role = (
        row.get(
            "role",
            ""
        )
        .strip()
        .upper()
    )

      if role == "BK":

        blank_result = "<2MDL"
        break

    qaqc_results = (
        analysis_state.get(
            "qaqc_results",
            []
        )
    )

    included_batches = (
    analysis_state.get(
        "included_batches",
        []
    )
)
    mdl_value = (
    control_data.get(
        "DETECT_LIMITED",
        ""
    )
    if control_data
    else ""
)

    qdl_value = (
    analysis_state.get(
        "qdl_value"
    )
)

    max_signal = (
        _get_max_calibration_signal(
            calibration_result
        )
    )

    precision = (
        _get_first_precision(
            qaqc_results
        )
    )

    duplicate_result = None

    if precision:

        duplicate_result = _to_float(
            precision.get(
                "rpd"
            )
        )

    qc_row = (
        _get_first_qaqc_row(
            qaqc_results,
            "QC"
        )
    )

    qc_result = None

    if qc_row:

        qc_result = _to_float(
            qc_row.get(
                "check_value"
            )
        )

    ms_row = (
        _get_first_spike_row(
            qaqc_results,
            "MS"
        )
    )

    spike_result = None

    if ms_row:

        spike_result = _to_float(
            ms_row.get(
                "recovery"
            )
        )

    ccv_row = (
        _get_first_qaqc_row(
            qaqc_results,
            "CCV"
        )
    )

    calibration_check = None

    if ccv_row:

        calibration_check = _to_float(
            ccv_row.get(
                "check_value"
            )
        )

    correlation_coefficient = None

    if calibration_result:

        correlation_coefficient = (
            _to_float(
                calibration_result.get(
                    "r"
                )
            )
        )

    # ========================================
    # LIMS 品管資料
    # 每一個分析批次產生一列
    # ========================================
    for batch in included_batches:

        current_batch_no = batch.get(
        "batch_no"
        )

        if current_batch_no is None:
            continue

        lims_batch_no = _build_batch_no(
            analysis_date,
            exam_no,
            current_batch_no
        )

        current_qaqc = None

        for qaqc_batch in qaqc_results:

            if (
                qaqc_batch.get(
                    "batch_no"
                )
                == current_batch_no
            ):

                current_qaqc = qaqc_batch
                break

        duplicate_result = None
        qc_result = None
        spike_result = None
        calibration_check = None

        if current_qaqc:

            precision = current_qaqc.get(
                "precision"
            )

            if precision:

                duplicate_result = _to_float(
                    precision.get(
                        "rpd"
                    )
                )

            for check_row in current_qaqc.get(
                "rows",
                []
            ):

                role = (
                    check_row.get(
                        "role",
                        ""
                    )
                    .strip()
                    .upper()
                )

                if (
                    role == "QC"
                    and qc_result is None
                ):

                    qc_result = _to_float(
                        check_row.get(
                            "check_value"
                        )
                    )

                if (
                    role == "CCV"
                    and calibration_check is None
                ):

                    calibration_check = _to_float(
                        check_row.get(
                            "check_value"
                        )
                    )

            for spike_row in current_qaqc.get(
                "spike_recovery",
                []
            ):

                role = (
                    spike_row.get(
                        "role",
                        ""
                    )
                    .strip()
                    .upper()
                )

                if (
                    role == "MS"
                    and spike_result is None
                ):

                    spike_result = _to_float(
                        spike_row.get(
                            "recovery"
                        )
                    )

        export_data.qc_rows.append(
            LimsQcRow(
                analysis_date=analysis_date,
                analyst=analyst,
                exam_no=exam_no,
                instrument_id=instrument_id,
                max_signal=max_signal,
                duplicate_result=duplicate_result,
                qc_result=qc_result,
                spike_result=spike_result,
                calibration_check=calibration_check,
                blank_result=blank_result,
                remark="",
                batch_no=lims_batch_no,
                correlation_coefficient=(
                    correlation_coefficient
                )
            )
        )

    # ========================================
    # LIMS 分析資料
    # 正式樣品依 included_batches 判斷所屬批次
    # ========================================
    for batch in included_batches:

                # ========================================
        # 空白試驗
        # W434 每批若存在 BK，LIMS 匯出為 <2MDL
        # ========================================
        
        current_batch_no = batch.get(
            "batch_no"
        )

        if current_batch_no is None:
            continue

        lims_batch_no = _build_batch_no(
            analysis_date,
            exam_no,
            current_batch_no
        )

        batch_rows = batch.get(
            "rows",
            []
        )

        for row in batch_rows:

            role = (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
            )

            if role != "SAMPLE":
                continue

            calculated_concentration = (
                      row.get(
                     "calculated_concentration"
                     )
            )

            (
               result_text,
               result_remark
            ) = _build_lims_result(
               calculated_concentration,
               mdl_value,
               qdl_value
            )

            export_data.analysis_rows.append(
                LimsAnalysisRow(
                    sample_id=(
                        row.get(
                            "sample_id",
                            ""
                        )
                        .strip()
                    ),
                    exam_no=exam_no,
                    result=result_text,
                    actual_item="",
                    batch_no=lims_batch_no,
                    remark=result_remark
                )
            )

    return export_data