from exports.lims_export_model import (
    LimsAnalysisRow,
    LimsExportData,
    LimsQcRow
)

from exports.lims_excel_exporter import (
    build_lims_excel
)


export_data = LimsExportData(
    qc_rows=[
        LimsQcRow(
            analysis_date="2026-09-08",
            analyst="",
            exam_no="W-43401",
            instrument_id="FQ-TEST-001",
            max_signal=0.0993,
            duplicate_result=0.4,
            qc_result=107.4,
            spike_result=79.3,
            calibration_check=0.5,
            blank_result="",
            remark="",
            batch_no="2026/09/08W-43401-1",
            correlation_coefficient=0.999659
        ),
        LimsQcRow(
            analysis_date="2026-09-08",
            analyst="",
            exam_no="W-43401",
            instrument_id="FQ-TEST-001",
            max_signal=0.0993,
            duplicate_result=1.1,
            qc_result=98.7,
            spike_result=95.6,
            calibration_check=-1.2,
            blank_result="",
            remark="",
            batch_no="2026/09/08W-43401-2",
            correlation_coefficient=0.999659
        )
    ],

    analysis_rows=[
        LimsAnalysisRow(
            sample_id="W14070326001",
            exam_no="W-43401",
            result="1.1691",
            actual_item="",
            batch_no="2026/09/08W-43401-1",
            remark=""
        ),
        LimsAnalysisRow(
            sample_id="W14070426001",
            exam_no="W-43401",
            result="<1.000",
            actual_item="",
            batch_no="2026/09/08W-43401-1",
            remark="QDL=1.000"
        ),
        LimsAnalysisRow(
            sample_id="W14070526001",
            exam_no="W-43401",
            result="ND<0.230",
            actual_item="",
            batch_no="2026/09/08W-43401-2",
            remark="MDL=0.230"
        )
    ]
)


template_path = (
    r"C:\PhyonWeb\lims匯入表格.xlsx"
)

output_path = (
    r"C:\PhyonWeb\test_lims_export.xlsx"
)


excel_buffer = build_lims_excel(
    template_path=template_path,
    export_data=export_data,
    analyst_id="S097-06",
    analyst_name="測試人員",
    analysis_method="NIEA W434.54B"
)


with open(
    output_path,
    "wb"
) as file:

    file.write(
        excel_buffer.getvalue()
    )


print(
    "LIMS Excel 匯出完成："
    + output_path
)