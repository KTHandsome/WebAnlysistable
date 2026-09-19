from exports.w434_lims_mapper import (
    build_w434_lims_export_data
)


form_data = {
    "instrument_id": "FQ-TEST-001",
    "analysis_start_date": "2026-09-08"
}


control_data = {
    "EXAMNO": "W-43401",
    "DETECT_LIMITED": "0.230"
}


analysis_state = {
    "qdl_value": "1.000",
    "calibration_result": {
        "r": 0.999659,
        "points": [
            {
                "x": 0.00000,
                "y": -0.0000
            },
            {
                "x": 0.00025,
                "y": 0.0027
            },
            {
                "x": 0.00050,
                "y": 0.0089
            },
            {
                "x": 0.00100,
                "y": 0.0182
            },
            {
                "x": 0.00250,
                "y": 0.0505
            },
            {
                "x": 0.00500,
                "y": 0.0993
            }
        ]
    },

    "included_batches": [
        {
            "batch_no": 1,
            "rows": [
                {
    "role": "SAMPLE",
    "sample_id": "W14070326001",
    "calculated_concentration": 1.1691
},
{
    "role": "SAMPLE",
    "sample_id": "W14070426001",
    "calculated_concentration": 0.500
},
            ]
        },
        {
            "batch_no": 2,
            "rows": [
                {
    "role": "SAMPLE",
    "sample_id": "W14070526001",
    "calculated_concentration": 0.100
}
            ]
        }
    ],

    "qaqc_results": [
        {
            "batch_no": 1,

            "rows": [
                {
                    "role": "CCV",
                    "sample_id": "CCV-1",
                    "check_value": 0.5
                },
                {
                    "role": "QC",
                    "sample_id": "QC-2",
                    "check_value": 107.4
                },
                {
                    "role": "CCV",
                    "sample_id": "CCV-2",
                    "check_value": 9.9
                }
            ],

            "precision": {
                "source": "DUP",
                "source_name": "原樣 / DUP",
                "rpd": 0.4
            },

            "spike_recovery": [
                {
                    "role": "MS",
                    "sample_id": "MS-2",
                    "recovery": 79.3
                },
                {
                    "role": "MSD",
                    "sample_id": "MSD-2",
                    "recovery": 81.3
                }
            ]
        },

        {
            "batch_no": 2,

            "rows": [
                {
                    "role": "CCV",
                    "sample_id": "CCV-3",
                    "check_value": -1.2
                },
                {
                    "role": "QC",
                    "sample_id": "QC-3",
                    "check_value": 98.7
                }
            ],

            "precision": {
                "source": "DUP",
                "source_name": "原樣 / DUP",
                "rpd": 1.1
            },

            "spike_recovery": [
                {
                    "role": "MS",
                    "sample_id": "MS-3",
                    "recovery": 95.6
                }
            ]
        }
    ],

    "sample_qaqc_rows": []
}


result = build_w434_lims_export_data(
    form_data=form_data,
    control_data=control_data,
    analysis_state=analysis_state,
    analyst="測試人員"
)


print("=== LIMS 品管資料 ===")

for row in result.qc_rows:

    print(
        "項目代碼：",
        row.exam_no
    )

    print(
        "設備序號：",
        row.instrument_id
    )

    print(
        "最高測定值：",
        row.max_signal
    )

    print(
        "重複分析：",
        row.duplicate_result
    )

    print(
        "查核分析：",
        row.qc_result
    )

    print(
        "添加分析：",
        row.spike_result
    )

    print(
        "檢量線確認：",
        row.calibration_check
    )

    print(
        "檢量線係數：",
        row.correlation_coefficient
    )


print()

print("=== LIMS 分析資料 ===")

for row in result.analysis_rows:

    print(
        row.sample_id,
        row.exam_no,
        row.result,
        row.batch_no
    )


# ========================================
# 自動驗證
# ========================================

assert len(
    result.qc_rows
) == 2

assert (
    result.qc_rows[0].batch_no
    == "2026/09/08W-43401-1"
)

assert (
    result.qc_rows[1].batch_no
    == "2026/09/08W-43401-2"
)

assert (
    result.qc_rows[0].duplicate_result
    == 0.4
)

assert (
    result.qc_rows[0].qc_result
    == 107.4
)

assert (
    result.qc_rows[0].spike_result
    == 79.3
)

assert (
    result.qc_rows[0].calibration_check
    == 0.5
)

assert (
    result.qc_rows[1].duplicate_result
    == 1.1
)

assert (
    result.qc_rows[1].qc_result
    == 98.7
)

assert (
    result.qc_rows[1].spike_result
    == 95.6
)

assert (
    result.qc_rows[1].calibration_check
    == -1.2
)


assert len(
    result.analysis_rows
) == 3

assert (
    result.analysis_rows[0].sample_id
    == "W14070326001"
)

assert (
    result.analysis_rows[0].batch_no
    == "2026/09/08W-43401-1"
)

assert (
    result.analysis_rows[1].sample_id
    == "W14070426001"
)

assert (
    result.analysis_rows[1].batch_no
    == "2026/09/08W-43401-1"
)

assert (
    result.analysis_rows[2].sample_id
    == "W14070526001"
)

assert (
    result.analysis_rows[2].batch_no
    == "2026/09/08W-43401-2"
)

assert (
    result.analysis_rows[0].result
    == "1.1691"
)

assert (
    result.analysis_rows[0].remark
    == ""
)

assert (
    result.analysis_rows[1].result
    == "<1.000"
)

assert (
    result.analysis_rows[1].remark
    == "QDL=1.000"
)

assert (
    result.analysis_rows[2].result
    == "ND<0.230"
)

assert (
    result.analysis_rows[2].remark
    == "MDL=0.230"
)

print()
print("W434 LIMS 雙批 Mapper 測試成功。")