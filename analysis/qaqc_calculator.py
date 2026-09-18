def _to_float(value):

    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        return float(text)

    except (TypeError, ValueError):
        return None


def calculate_recovery(
    calculated_concentration,
    spike_concentration
):

    calculated = _to_float(
        calculated_concentration
    )

    spike = _to_float(
        spike_concentration
    )

    if (
        calculated is None
        or spike is None
        or spike <= 0
    ):
        return None

    return (
        calculated
        / spike
        * 100.0
    )

def calculate_relative_error(
    calculated_concentration,
    spike_concentration
):

    calculated = _to_float(
        calculated_concentration
    )

    spike = _to_float(
        spike_concentration
    )

    if (
        calculated is None
        or spike is None
        or spike == 0
    ):
        return None

    return (
        (
            calculated
            - spike
        )
        / spike
        * 100.0
    )


def calculate_rpd(
    value_a,
    value_b
):

    value_a = _to_float(
        value_a
    )

    value_b = _to_float(
        value_b
    )

    if (
        value_a is None
        or value_b is None
    ):
        return None

    average = (
        value_a
        + value_b
    ) / 2.0

    if average == 0:
        return None

    return (
        abs(
            value_a
            - value_b
        )
        / abs(average)
        * 100.0
    )

def calculate_spike_recovery(
    spiked_value,
    original_value,
    spike_concentration
):

    spiked_value = _to_float(
        spiked_value
    )

    original_value = _to_float(
        original_value
    )

    spike_concentration = _to_float(
        spike_concentration
    )

    if (
        spiked_value is None
        or original_value is None
        or spike_concentration is None
        or spike_concentration == 0
    ):
        return None

    return (
        (
            spiked_value
            - original_value
        )
        / spike_concentration
        * 100.0
    )

def evaluate_rpd_status(
    rpd,
    uwl,
    ucl
):

    rpd = _to_float(
        rpd
    )

    uwl = _to_float(
        uwl
    )

    ucl = _to_float(
        ucl
    )

    if rpd is None:
        return "無法判定"

    if (
        ucl is not None
        and rpd > ucl
    ):
        return "超出管制"

    if (
        uwl is not None
        and rpd > uwl
    ):
        return "警告"

    return "合格"

def evaluate_control_status(
    value,
    lcl,
    lwl,
    uwl,
    ucl
):

    value = _to_float(value)
    lcl = _to_float(lcl)
    lwl = _to_float(lwl)
    uwl = _to_float(uwl)
    ucl = _to_float(ucl)

    if value is None:
        return "無法判定"

    # 超出管制界限
    if (
        lcl is not None
        and value < lcl
    ):
        return "超出管制"

    if (
        ucl is not None
        and value > ucl
    ):
        return "超出管制"

    # 落入警告區
    if (
        lwl is not None
        and value < lwl
    ):
        return "警告"

    if (
        uwl is not None
        and value > uwl
    ):
        return "警告"

    return "合格"


def evaluate_relative_error_status(
    value,
    limit
):

    value = _to_float(
        value
    )

    limit = _to_float(
        limit
    )

    if (
        value is None
        or limit is None
    ):
        return "無法判定"

    if abs(value) <= limit:
        return "合格"

    return "超出管制"

def build_qaqc_check_results(
    included_batches,
    control_data,
    cc_relative_error_limit,
    qdl_value
):

    if not included_batches or not control_data:
        return []

    qc_lcl = _to_float(
        control_data.get(
            "QC_LCL"
        )
    )

    qc_lwl = _to_float(
        control_data.get(
            "QC_LWL"
        )
    )

    qc_uwl = _to_float(
        control_data.get(
            "QC_UWL"
        )
    )

    qc_ucl = _to_float(
        control_data.get(
            "QC_UCL"
        )
    )

    cc_limit = _to_float(
        cc_relative_error_limit
    )

    dc_uwl = _to_float(
     control_data.get(
        "DC_UWL"
        )
    )

    dc_ucl = _to_float(
    control_data.get(
        "DC_UCL"
           )
    )

    spike_lcl = _to_float(
        control_data.get(
            "SPIKE_LCL"
        )
    )

    spike_lwl = _to_float(
        control_data.get(
            "SPIKE_LWL"
        )
    )

    spike_uwl = _to_float(
        control_data.get(
            "SPIKE_UWL"
        )
    )

    spike_ucl = _to_float(
        control_data.get(
            "SPIKE_UCL"
        )
    )

    results = []

    for batch in included_batches:

        batch_no = batch.get(
            "batch_no"
        )

        batch_category = batch.get(
            "batch_category"
        )

        batch_rows = batch.get(
            "rows",
            []
        )

        start_check = batch.get(
            "start_check"
        )

        end_check = batch.get(
            "end_check"
        )

        start_sequence = (
            start_check.get(
                "sequence_no"
            )
            if start_check
            else None
        )

        end_sequence = (
            end_check.get(
                "sequence_no"
            )
            if end_check
            else None
        )

        check_rows = []

        precision_result = None

        spike_recovery_results = []

        for row in batch_rows:

            role = (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
            )

            if role not in {
                "ICV",
                "QC",
                "CCV"
            }:
                continue

            sequence_no = row.get(
                "sequence_no"
            )

            calculated_concentration = (
                _to_float(
                    row.get(
                        "calculated_concentration"
                    )
                )
            )

            spike_concentration = (
                _to_float(
                    row.get(
                        "spike_concentration"
                    )
                )
            )


            # ---------------------------------
            # CC：ICV / CCV
            # W434 方法固定採相對誤差 ±20%
            # ---------------------------------
            if role in {
                "ICV",
                "CCV"
            }:

                check_value = (
                    calculate_relative_error(
                        calculated_concentration,
                        spike_concentration
                    )
                )

                calculation_type = (
                    "RELATIVE_ERROR"
                )

                calculation_name = (
                    "相對誤差"
                )

                status = (
                    evaluate_relative_error_status(
                        check_value,
                        cc_limit
                    )
                )

                if cc_limit is not None:

                    control_text = (
                        "±"
                        + format(
                            cc_limit,
                            ".1f"
                        )
                        + "%"
                    )

                else:

                    control_text = "-"

                warning_text = ""


            # ---------------------------------
            # QC 查核樣品
            # 使用 LIMS 年度 QC 管制值
            # ---------------------------------
            else:

                check_value = (
                    calculate_recovery(
                        calculated_concentration,
                        spike_concentration
                    )
                )

                calculation_type = (
                    "RECOVERY"
                )

                calculation_name = (
                    "回收率"
                )

                status = (
                    evaluate_control_status(
                        check_value,
                        qc_lcl,
                        qc_lwl,
                        qc_uwl,
                        qc_ucl
                    )
                )

                if (
                    qc_lcl is not None
                    and qc_ucl is not None
                ):

                    control_text = (
                        format(
                            qc_lcl,
                            ".1f"
                        )
                        + " ～ "
                        + format(
                            qc_ucl,
                            ".1f"
                        )
                        + "%"
                    )

                else:

                    control_text = "-"

                if (
                    qc_lwl is not None
                    and qc_uwl is not None
                ):

                    warning_text = (
                        format(
                            qc_lwl,
                            ".1f"
                        )
                        + " ～ "
                        + format(
                            qc_uwl,
                            ".1f"
                        )
                        + "%"
                    )

                else:

                    warning_text = ""


            # ---------------------------------
            # 批次位置
            # ---------------------------------
            if role == "ICV":

                check_position = (
                    "起始查核"
                )

            elif (
                role == "CCV"
                and sequence_no
                == start_sequence
            ):

                check_position = (
                    "起始查核"
                )

            elif (
                role == "CCV"
                and sequence_no
                == end_sequence
            ):

                check_position = (
                    "結束查核"
                )

            else:

                check_position = (
                    "批內查核"
                )


            check_rows.append(
                {
                    "role":
                        role,

                    "check_position":
                        check_position,

                    "sequence_no":
                        sequence_no,

                    "sample_id":
                        row.get(
                            "sample_id",
                            ""
                        ),

                    "spike_concentration":
                        spike_concentration,

                    "calculated_concentration":
                        calculated_concentration,

                    "calculation_type":
                        calculation_type,

                    "calculation_name":
                        calculation_name,

                    "check_value":
                        check_value,

                    "control_text":
                        control_text,

                    "warning_text":
                        warning_text,

                    "status":
                        status
                }
            )

        # =================================
        # 3B：重複分析精密度
        # =================================

        duplicate_row = None
        original_row = None

        for index, row in enumerate(
            batch_rows
        ):

            role = (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
            )

            if role != "DUP":
                continue

            duplicate_row = row

            # DUP 往前尋找最近一筆正式 SAMPLE
            for previous_index in range(
                index - 1,
                -1,
                -1
            ):

                previous_row = (
                    batch_rows[
                        previous_index
                    ]
                )

                previous_role = (
                    previous_row.get(
                        "role",
                        ""
                    )
                    .strip()
                    .upper()
                )

                if previous_role == "SAMPLE":

                    original_row = (
                        previous_row
                    )

                    break

            break

        if (
            duplicate_row is not None
            and original_row is not None
             ):

             duplicate_value = _to_float(
                duplicate_row.get(
                    "calculated_concentration"
                )
            )

             original_value = _to_float(
                original_row.get(
                    "calculated_concentration"
                )
            )

             if (
                duplicate_value is not None
                and qdl_value is not None
                and duplicate_value >= qdl_value
            ):

                rpd = calculate_rpd(
                    original_value,
                    duplicate_value
                )

                precision_result = {
                    "source":
                        "DUP",

                    "source_name":
                        "原樣 / DUP",

                    "sample_id_a":
                        original_row.get(
                            "sample_id",
                            ""
                        ),

                    "sample_id_b":
                        duplicate_row.get(
                            "sample_id",
                            ""
                        ),

                    "value_a":
                        original_value,

                    "value_b":
                        duplicate_value,

                    "rpd":
                        rpd,

                    "uwl":
                        dc_uwl,

                    "ucl":
                        dc_ucl,

                    "status":
                        evaluate_rpd_status(
                            rpd,
                            dc_uwl,
                            dc_ucl
                        )
                }
             else:

                ms_row = None
                msd_row = None

                for row in batch_rows:

                    role = (
                        row.get(
                            "role",
                            ""
                        )
                        .strip()
                        .upper()
                    )

                    if role == "MS":
                        ms_row = row

                    elif role == "MSD":
                        msd_row = row

                if (
                    ms_row is not None
                    and msd_row is not None
                ):

                    ms_value = _to_float(
                        ms_row.get(
                            "calculated_concentration"
                        )
                    )

                    msd_value = _to_float(
                        msd_row.get(
                            "calculated_concentration"
                        )
                    )

                    rpd = calculate_rpd(
                        ms_value,
                        msd_value
                    )

                    precision_result = {
                        "source":
                            "MS_MSD",

                        "source_name":
                            "MS / MSD",

                        "sample_id_a":
                            ms_row.get(
                                "sample_id",
                                ""
                            ),

                        "sample_id_b":
                            msd_row.get(
                                "sample_id",
                                ""
                            ),

                        "value_a":
                            ms_value,

                        "value_b":
                            msd_value,

                        "rpd":
                            rpd,

                        "uwl":
                            dc_uwl,

                        "ucl":
                            dc_ucl,

                        "status":
                            evaluate_rpd_status(
                                rpd,
                                dc_uwl,
                                dc_ucl
                            ),

                        "reason":
                            "DUP < QDL，改採 MS/MSD 進行重複分析判定"
                    }
                else:

                    precision_result = {
                        "source":
                            "MS_MSD",

                        "source_name":
                            "MS / MSD",

                        "sample_id_a":
                            "",

                        "sample_id_b":
                            "",

                        "value_a":
                            None,

                        "value_b":
                            None,

                        "rpd":
                            None,

                        "uwl":
                            dc_uwl,

                        "ucl":
                            dc_ucl,

                        "status":
                            "無法判定",

                        "reason":
                            "DUP < QDL，但本批缺少完整 MS/MSD 資料"
                    }        

        # =================================
        # 3C：MS / MSD 添加樣品回收率
        # =================================

        ms_row = None
        msd_row = None
        original_sample_row = None

        for index, row in enumerate(
            batch_rows
        ):

            role = (
                row.get(
                    "role",
                    ""
                )
                .strip()
                .upper()
            )

            if role == "MS":

                ms_row = row

                # MS 往前尋找最近一筆正式 SAMPLE
                for previous_index in range(
                    index - 1,
                    -1,
                    -1
                ):

                    previous_row = (
                        batch_rows[
                            previous_index
                        ]
                    )

                    previous_role = (
                        previous_row.get(
                            "role",
                            ""
                        )
                        .strip()
                        .upper()
                    )

                    if previous_role == "SAMPLE":

                        original_sample_row = (
                            previous_row
                        )

                        break

            elif role == "MSD":

                msd_row = row

        if (
            original_sample_row is not None
            and ms_row is not None
        ):

            original_value = _to_float(
                original_sample_row.get(
                    "calculated_concentration"
                )
            )

            ms_value = _to_float(
                ms_row.get(
                    "calculated_concentration"
                )
            )

            ms_spike = _to_float(
                ms_row.get(
                    "spike_concentration"
                )
            )

            ms_recovery = (
                calculate_spike_recovery(
                    ms_value,
                    original_value,
                    ms_spike
                )
            )

            spike_recovery_results.append(
                {
                    "role":
                        "MS",

                    "sample_id":
                        ms_row.get(
                            "sample_id",
                            ""
                        ),

                    "original_sample_id":
                        original_sample_row.get(
                            "sample_id",
                            ""
                        ),

                    "original_value":
                        original_value,

                    "spiked_value":
                        ms_value,

                    "spike_concentration":
                        ms_spike,

                    "recovery":
                        ms_recovery,

                    "lcl":
                        spike_lcl,

                    "lwl":
                        spike_lwl,

                    "uwl":
                        spike_uwl,

                    "ucl":
                        spike_ucl,

                    "status":
                        evaluate_control_status(
                            ms_recovery,
                            spike_lcl,
                            spike_lwl,
                            spike_uwl,
                            spike_ucl
                        )
                }
            )

        if (
            original_sample_row is not None
            and msd_row is not None
        ):

            original_value = _to_float(
                original_sample_row.get(
                    "calculated_concentration"
                )
            )

            msd_value = _to_float(
                msd_row.get(
                    "calculated_concentration"
                )
            )

            msd_spike = _to_float(
                msd_row.get(
                    "spike_concentration"
                )
            )

            msd_recovery = (
                calculate_spike_recovery(
                    msd_value,
                    original_value,
                    msd_spike
                )
            )

            spike_recovery_results.append(
                {
                    "role":
                        "MSD",

                    "sample_id":
                        msd_row.get(
                            "sample_id",
                            ""
                        ),

                    "original_sample_id":
                        original_sample_row.get(
                            "sample_id",
                            ""
                        ),

                    "original_value":
                        original_value,

                    "spiked_value":
                        msd_value,

                    "spike_concentration":
                        msd_spike,

                    "recovery":
                        msd_recovery,

                    "lcl":
                        spike_lcl,

                    "lwl":
                        spike_lwl,

                    "uwl":
                        spike_uwl,

                    "ucl":
                        spike_ucl,

                    "status":
                        evaluate_control_status(
                            msd_recovery,
                            spike_lcl,
                            spike_lwl,
                            spike_uwl,
                            spike_ucl
                        )
                }
            )

        results.append(
            {
                "batch_no":
                    batch_no,

                "batch_category":
                    batch_category,

                "rows":
                    check_rows,

                "precision":
                    precision_result,

                "spike_recovery":
                    spike_recovery_results
            }
        )

    return results

