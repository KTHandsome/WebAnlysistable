from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(
    TTFont(
        "MicrosoftJhengHei",
        r"C:\Windows\Fonts\msjh.ttc",
        subfontIndex=0
    )
)

def build_w434_pdf(
    report_data,
    method_data,
    control_data,
    form_data,
    analysis_state
):
    """
    W434 PDF 產生器
    第一階段：建立 PDF 表頭骨架。
    """

    pdf_buffer = BytesIO()

    pdf_canvas = canvas.Canvas(
        pdf_buffer,
        pagesize=A4
    )

    page_width, page_height = A4

        # ========================================
    # 共用頁尾
    # 每一頁均顯示：
    # 審核 / 驗算 / 分析 + 頁碼
    # ========================================
    def draw_page_footer(
        page_no,
        total_pages
    ):

        usable_width = (
            page_width
            - left_margin
            - right_margin
        )

        footer_col_width = (
            usable_width / 3
        )

        # -----------------------------
        # 簽核欄
        # -----------------------------
        signature_y = 38

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            9
        )

        pdf_canvas.drawString(
            left_margin,
            signature_y,
            "審核："
        )

        pdf_canvas.drawString(
            left_margin
            + footer_col_width,
            signature_y,
            "驗算："
        )

        pdf_canvas.drawString(
            left_margin
            + footer_col_width * 2,
            signature_y,
            "分析："
        )

        # -----------------------------
        # 頁碼
        # -----------------------------
        page_number_y = 14

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            7.5
        )

        pdf_canvas.drawCentredString(
            page_width / 2,
            page_number_y,
            "第 "
            + str(page_no)
            + " 頁 / 共 "
            + str(total_pages)
            + " 頁"
        )

    # -----------------------------
    # 基本版面參數
    # -----------------------------
    left_margin = 40
    right_margin = 40
    top_y = page_height - 42

    company_name = (
        report_data.get(
            "COMPANY_NAME",
            ""
        )
        if report_data
        else ""
    )

    form_title = (
        report_data.get(
            "FORM_TITLE",
            ""
        )
        if report_data
        else ""
    )

    doc_no = (
        report_data.get(
            "DOC_NO",
            ""
        )
        if report_data
        else ""
    )

    revision = (
        report_data.get(
            "REVISION",
            ""
        )
        if report_data
        else ""
    )

    issue_date = (
        report_data.get(
            "ISSUE_DATE",
            ""
        )
        if report_data
        else ""
    )

    analyte_display = (
    method_data.get(
        "ANALYTE_DISPLAY",
        ""
    )
    if method_data
    else ""
)

    confirmed_wavelength = (
    analysis_state.get(
        "confirmed_wavelength"
    )
    if analysis_state
    else None
)

    instrument_model = (
    form_data.get(
        "instrument_model",
        ""
    ).strip()
    if form_data
    else ""
)        

    exam_method = (
    control_data.get(
        "EM_NO",
        ""
    ).strip()
    if control_data
    else ""
)

    analysis_start_date = (
    form_data.get(
        "analysis_start_date",
        ""
    )
    if form_data
    else ""
)

    analysis_end_date = (
    form_data.get(
        "analysis_end_date",
        ""
    )
    if form_data
    else ""
)

    form_date = (
    form_data.get(
        "form_date",
        ""
    )
    if form_data
    else ""
)

    analysis_start_date = (
    analysis_start_date.replace("-", "/")
)

    analysis_end_date = (
    analysis_end_date.replace("-", "/")
)

    form_date = (
    form_date.replace("-", "/")
)   

    calibration_result = (
        analysis_state.get(
            "calibration_result"
        )
        if analysis_state
        else None
    )

    calibration_points = (
        calibration_result.get(
            "points",
            []
        )
        if calibration_result
        else []
    )

    sample_qaqc_rows = (
       analysis_state.get(
        "sample_qaqc_rows",
        []
      )
       if analysis_state
       else []
    )

    qaqc_results = (
    analysis_state.get(
        "qaqc_results",
        []
    )
    if analysis_state
    else []
)
    

    # -----------------------------
    # 左上：公司名稱
    # -----------------------------
    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        8
    )

    pdf_canvas.drawString(
        left_margin,
        top_y,
        company_name
    )

    # -----------------------------
    # 右上：文件資訊
    # -----------------------------
    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        8
    )

    right_x = page_width - right_margin

    pdf_canvas.drawRightString(
        right_x,
        top_y,
        doc_no
        + " 版次："
        + revision
    )

    pdf_canvas.drawRightString(
        right_x,
        top_y - 14,
        "發行日期："
        + issue_date
    )

    # -----------------------------
    # 中央：文件名稱
    # -----------------------------
    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        12
    )

    pdf_canvas.drawCentredString(
        page_width / 2,
        top_y - 32,
        form_title
    )

    # -----------------------------
    # 檢驗項目
    # -----------------------------
    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        9
    )

    pdf_canvas.drawCentredString(
        page_width / 2,
        top_y - 52,
        "檢驗項目："
        + analyte_display
    )

    # -----------------------------
    # 波長
    # -----------------------------
    if confirmed_wavelength is not None:

       wavelength_text = (
        format(
            confirmed_wavelength,
            ".2f"
        )
        + " nm"
    )

    else:

      wavelength_text = "-"

    pdf_canvas.drawCentredString(
    page_width / 2,
    top_y - 70,
    "使用波長："
    + wavelength_text
)

    # -----------------------------
    # 下方基本資訊
    # -----------------------------
    pdf_canvas.setFont(
    "MicrosoftJhengHei",
    9
)

    pdf_canvas.drawString(
    left_margin,
    top_y - 90,
    "儀器型號："
    + instrument_model
)

    pdf_canvas.drawRightString(
    right_x,
    top_y - 90,
    "填表日期："
    + form_date
)

    pdf_canvas.drawString(
    left_margin,
    top_y - 107,
    "檢驗方法："
    + exam_method
)

    pdf_canvas.drawRightString(
    right_x,
    top_y - 107,
    "分析日期："
    + analysis_start_date
    + " ～ "
    + analysis_end_date
)

    # -----------------------------
    # 表頭下方分隔線
    # -----------------------------
    pdf_canvas.line(
        left_margin,
        top_y - 116,
        page_width - right_margin,
        top_y - 116
    )

    # -----------------------------
    # 檢量線結果
    # -----------------------------
    calibration_title_y = (
        top_y - 136
    )

    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        11
    )

    pdf_canvas.drawString(
        left_margin,
        calibration_title_y,
        "一、檢量線"
    )

    if calibration_result:

        slope = calibration_result.get(
            "slope"
        )

        intercept = calibration_result.get(
            "intercept"
        )

        r_value = calibration_result.get(
            "r"
        )

        passed = calibration_result.get(
            "passed"
        )

        regression_y = (
            calibration_title_y
        )

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            9
        )

        if (
            slope is not None
            and intercept is not None
        ):

            if intercept >= 0:

                equation_text = (
                    "Y = "
                    + format(
                        slope,
                        ".5f"
                    )
                    + "X + "
                    + format(
                        intercept,
                        ".5f"
                    )
                )

            else:

                equation_text = (
                    "Y = "
                    + format(
                        slope,
                        ".5f"
                    )
                    + "X - "
                    + format(
                        abs(intercept),
                        ".5f"
                    )
                )

        else:
            equation_text = "Y = -"

        pdf_canvas.drawString(
            left_margin + 60,
            regression_y,
            equation_text
        )

        pdf_canvas.drawString(
            left_margin + 250,
            regression_y,
            "相關係數(r)："
            + (
                format(
                    r_value,
                    ".6f"
                )
                if r_value is not None
                else "-"
            )
        )

        table_top_y = (
            regression_y - 8
        )

        table_left = left_margin

        row_height = 16

        column_widths = [
            80,
            145,
            120,
            170
        ]

        headers = [
            "標準品",
            "設定濃度 (mg/L)",
            "吸光度",
            "回歸濃度 (mg/L)"
        ]

        # -----------------------------
        # 欄首
        # -----------------------------
        current_x = table_left

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            8
        )

        for index, header in enumerate(
            headers
        ):

            width = column_widths[
                index
            ]

            pdf_canvas.rect(
                current_x,
                table_top_y - row_height,
                width,
                row_height
            )

            pdf_canvas.drawCentredString(
                current_x + width / 2,
                table_top_y - 12,
                header
            )

            current_x += width

        # -----------------------------
        # 資料列
        # -----------------------------
        current_y = (
            table_top_y
            - row_height
        )

        for point_index, point in enumerate(
            calibration_points
        ):

            current_y -= row_height

            x_value = point.get(
                "x"
            )

            y_value = point.get(
                "y"
            )

            back_x = point.get(
                "back_calculated_x"
            )

            row_values = [
                "STD"
                + str(point_index),

                (
                    format(
                        x_value,
                        ".5f"
                    )
                    if x_value is not None
                    else "-"
                ),

                (
                    format(
                        y_value,
                        ".4f"
                    )
                    if y_value is not None
                    else "-"
                ),

                (
                    format(
                        back_x,
                        ".7f"
                    )
                    if back_x is not None
                    else "-"
                )
            ]

            current_x = table_left

            for index, value in enumerate(
                row_values
            ):

                width = column_widths[
                    index
                ]

                pdf_canvas.rect(
                    current_x,
                    current_y,
                    width,
                    row_height
                )

                pdf_canvas.drawCentredString(
                    current_x + width / 2,
                    current_y + 5,
                    value
                )

                current_x += width

    # -----------------------------
    # 二、樣品及品管分析結果
    # -----------------------------
    sample_title_y = (
        current_y - 28
    )

    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        11
    )

    pdf_canvas.drawString(
        left_margin,
        sample_title_y,
        "二、樣品及品管分析結果"
    )

    # -----------------------------
    # 取得實際分析計算條件
    # -----------------------------
    sample_volume = None
    final_volume = None   

    for row in sample_qaqc_rows:

        if sample_volume is None:
             value = row.get(
            "sample_volume"
        )
             if value is not None:
                final_volume = value       
        if (
        sample_volume is not None
        and final_volume is not None
    ):
         break

    sample_volume_text = (
    format(
        sample_volume,
        "g"
    )
    if sample_volume is not None
    else "-"
)
    final_volume_text = (
    format(
        final_volume,
        "g"
    )
    if final_volume is not None
    else "-"
)
    # -----------------------------
    # 品保驗算必要計算條件
    # -----------------------------
    pdf_canvas.setFont(
    "MicrosoftJhengHei",
    7.5
)    
    condition_y = (
    sample_title_y - 14
)   
    pdf_canvas.drawString(
    left_margin,
    condition_y,
    "計算條件：取樣體積 "
    + sample_volume_text
    + " mL"
    + "　｜　最終定量體積 "
    + final_volume_text
    + " mL"
)
    formula_y = (
    sample_title_y - 26
)
    pdf_canvas.drawString(
    left_margin,
    formula_y,
    "計算式：計算濃度 = 測定濃度 × "
    "(最終定量體積 / 取樣體積) × "
    "稀釋倍數(D)"
)
    sample_table_top_y = (
    sample_title_y - 34
)
    sample_row_height = 17

    sample_column_widths = [
    45,   # 序號
    105,  # 樣品編號
    80,   # 稀釋倍數
    75,   # 測定值
    100,  # 添加濃度
    110   # 計算濃度
]

    sample_headers = [
    "序號",
    "樣品編號",
    "稀釋倍數(D)",
    "測定值",
    "添加濃度 (mg/L)",
    "計算濃度 (mg/L)"
]

    current_x = left_margin

    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        7.5
    )

    # 表頭
    for index, header in enumerate(
        sample_headers
    ):

        width = sample_column_widths[
            index
        ]

        pdf_canvas.rect(
            current_x,
            sample_table_top_y - sample_row_height,
            width,
            sample_row_height
        )

        pdf_canvas.drawCentredString(
            current_x + width / 2,
            sample_table_top_y - 12,
            header
        )

        current_x += width

    current_y = (
        sample_table_top_y
        - sample_row_height
    )

    # 資料列
    for row in sample_qaqc_rows:

        current_y -= sample_row_height

        sequence_no = row.get(
            "sequence_no"
        )

        sample_id = row.get(
            "sample_id",
            ""
        )

        dilution_factor = row.get(
    "dilution_factor",
    1
)

        signal = row.get(
            "signal"
        )

        spike_concentration = row.get(
            "spike_concentration",
            ""
        )

        calculated_concentration = row.get(
            "calculated_concentration"
        )

        row_values = [
            str(sequence_no)
            if sequence_no is not None
            else "-",

            sample_id
            if sample_id
            else "-",

            (
        str(dilution_factor)
           if dilution_factor not in {
             None,
             ""
              }
           else "1"
            ),

            (
                format(
                    signal,
                    ".4f"
                )
                if signal is not None
                else "-"
            ),

            (
                str(spike_concentration)
                if spike_concentration not in {
                    None,
                    ""
                }
                else "-"
            ),

            (
                format(
                    calculated_concentration,
                    ".6f"
                )
                if calculated_concentration is not None
                else "-"
            )
        ]

        current_x = left_margin

        for index, value in enumerate(
            row_values
        ):

            width = sample_column_widths[
                index
            ]

            pdf_canvas.rect(
                current_x,
                current_y,
                width,
                sample_row_height
            )

            pdf_canvas.drawCentredString(
                current_x + width / 2,
                current_y + 5,
                str(value)
            )

            current_x += width

    # -----------------------------
    # 三、QA/QC 判定
    # -----------------------------
    qaqc_summary_rows = []

    for batch_result in qaqc_results:

        # 3A：ICV / QC / CCV
        for check in batch_result.get(
            "rows",
            []
        ):

            check_value = check.get(
                "check_value"
            )

            calculation_type = check.get(
                "calculation_type",
                ""
            )

            if check_value is None:

                result_text = "-"

            elif calculation_type in {
                "RELATIVE_ERROR",
                "RECOVERY"
            }:

                result_text = (
                    format(
                        check_value,
                        ".2f"
                    )
                    + " %"
                )

            else:

                result_text = format(
                    check_value,
                    ".2f"
                )

            item_text = (
                check.get(
                    "role",
                    ""
                )
                + " "
                + check.get(
                    "calculation_name",
                    ""
                )
            ).strip()

            qaqc_summary_rows.append(
                {
                    "item": item_text,
                    "result": result_text,
                    "control": check.get(
                        "control_text",
                        "-"
                    ),
                    "status": check.get(
                        "status",
                        "-"
                    )
                }
            )

        # 3B：重複分析精密度
        precision = batch_result.get(
            "precision"
        )

        if precision:

            rpd = precision.get(
                "rpd"
            )

            ucl = precision.get(
                "ucl"
            )

            qaqc_summary_rows.append(
                {
                    "item":
                        precision.get(
                            "source_name",
                            "重複分析"
                        )
                        + " RPD",

                    "result":
                        (
                            format(
                                rpd,
                                ".2f"
                            )
                            + " %"
                            if rpd is not None
                            else "-"
                        ),

                    "control":
                        (
                            "≤ "
                            + format(
                                ucl,
                                ".1f"
                            )
                            + " %"
                            if ucl is not None
                            else "-"
                        ),

                    "status":
                        precision.get(
                            "status",
                            "-"
                        )
                }
            )

        # 3C：MS / MSD 回收率
        for spike in batch_result.get(
            "spike_recovery",
            []
        ):

            recovery = spike.get(
                "recovery"
            )

            lcl = spike.get(
                "lcl"
            )

            ucl = spike.get(
                "ucl"
            )

            if (
                lcl is not None
                and ucl is not None
            ):

                control_text = (
                    format(
                        lcl,
                        ".1f"
                    )
                    + " ～ "
                    + format(
                        ucl,
                        ".1f"
                    )
                    + " %"
                )

            else:

                control_text = "-"

            qaqc_summary_rows.append(
                {
                    "item":
                        spike.get(
                            "role",
                            ""
                        )
                        + " 回收率",

                    "result":
                        (
                            format(
                                recovery,
                                ".2f"
                            )
                            + " %"
                            if recovery is not None
                            else "-"
                        ),

                    "control":
                        control_text,

                    "status":
                        spike.get(
                            "status",
                            "-"
                        )
                }
            )

    # -----------------------------
    # 三、QA/QC 判定
    # -----------------------------
    qaqc_title_y = (
        current_y - 24
    )

    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        10
    )

    pdf_canvas.drawString(
        left_margin,
        qaqc_title_y,
        "三、QA/QC 判定"
    )

    qaqc_table_top_y = (
        qaqc_title_y - 8
    )

    qaqc_row_height = 14

    qaqc_column_widths = [
        175,  # 項目
        105,   # 結果
        160,  # 管制標準
        75    # 判定
    ]

    qaqc_headers = [
        "項目",
        "結果",
        "管制標準",
        "判定"
    ]

    current_x = left_margin

    pdf_canvas.setFont(
        "MicrosoftJhengHei",
        7.5
    )

    # 表頭
    for index, header in enumerate(
        qaqc_headers
    ):

        width = qaqc_column_widths[
            index
        ]

        pdf_canvas.rect(
            current_x,
            qaqc_table_top_y - qaqc_row_height,
            width,
            qaqc_row_height
        )

        pdf_canvas.drawCentredString(
            current_x + width / 2,
            qaqc_table_top_y - 10,
            header
        )

        current_x += width

    current_y = (
        qaqc_table_top_y
        - qaqc_row_height
    )

    # 資料列
    for row in qaqc_summary_rows:

        current_y -= qaqc_row_height

        row_values = [
            row.get(
                "item",
                "-"
            ),

            row.get(
                "result",
                "-"
            ),

            row.get(
                "control",
                "-"
            ),

            row.get(
                "status",
                "-"
            )
        ]

        current_x = left_margin

        for index, value in enumerate(
            row_values
        ):

            width = qaqc_column_widths[
                index
            ]

            pdf_canvas.rect(
                current_x,
                current_y,
                width,
                qaqc_row_height
            )

            pdf_canvas.drawCentredString(
                current_x + width / 2,
                current_y + 4,
                str(value)
            )

            current_x += width

    # -----------------------------
    # 本頁頁尾
    # 目前尚未啟用跨頁，因此固定 1 / 1
    # 下一階段跨頁時改由各頁傳入實際頁次
    # -----------------------------
    draw_page_footer(
        page_no=1,
        total_pages=1
    )

    pdf_canvas.showPage()
    pdf_canvas.save()

    pdf_buffer.seek(0)

    return pdf_buffer