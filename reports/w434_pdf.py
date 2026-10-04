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
    top_y = page_height - 30

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

    calibration_unit = str(
    method_data.get(
        "CALIBRATION_UNIT",
        ""
       )
       or ""
    ).strip()

    display_conc_unit = str(
    method_data.get(
        "DISPLAY_CONC_UNIT",
        ""
       )
      or ""
    ).strip()

    signal_field = str(
    method_data.get(
        "SIGNAL_FIELD",
        ""
       )
      or ""
    ).strip().upper()

    if signal_field == "AREA":

        signal_label = "AREA"

    elif signal_field in {
        "ABSORBANCE",
        "ABS",
        "BLNKCORR_SIGNAL_MEAN"
    }:

       signal_label = "吸光度"

    else:

        signal_label = "測定值"

    spike_conc_unit = str(
        control_data.get(
        "CTRL_UNIT",
        ""
        )
      or ""
    ).strip()

    if not spike_conc_unit:

       spike_conc_unit = (
        display_conc_unit
    )   

    spike_conc_unit = str(
    control_data.get(
        "CTRL_UNIT",
        ""
    )
    or ""
).strip()

    if not spike_conc_unit:
       spike_conc_unit = display_conc_unit



    confirmed_wavelength = (
         analysis_state.get(
         "confirmed_wavelength"
         )
         if analysis_state
         else None
    )

    if confirmed_wavelength is None:

        basic_wavelength = str(
             form_data.get(
                "wavelength",
                ""
             )
             or ""
        ).strip()

        if basic_wavelength:

           try:
 
             confirmed_wavelength = float(
                basic_wavelength
             )

           except ValueError:

               confirmed_wavelength = None

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

    included_batches = (
    analysis_state.get(
        "included_batches",
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

    qaqc_result_map = {}

    for batch_result in qaqc_results:

        batch_no = str(
           batch_result.get(
            "batch_no",
            ""
            )
           or ""
        ).strip()

        if not batch_no:
          continue

        qaqc_result_map[
            batch_no
        ] = batch_result
    

    # ========================================
    # 每頁共用：表頭 + 檢量線
    # ========================================
    def draw_page_header_and_calibration():

        right_x = (
            page_width
            - right_margin
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
            top_y - 26,
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
            top_y - 39,
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
            top_y - 51,
            "使用波長："
            + wavelength_text
        )

        # -----------------------------
        # 基本資訊
        # -----------------------------
        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            9
        )

        pdf_canvas.drawString(
            left_margin,
            top_y - 64,
            "儀器型號："
            + instrument_model
        )

        pdf_canvas.drawRightString(
            right_x,
            top_y - 64,
            "填表日期："
            + form_date
        )

        pdf_canvas.drawString(
            left_margin,
            top_y - 77,
            "檢驗方法："
            + exam_method
        )

        pdf_canvas.drawRightString(
            right_x,
            top_y - 77,
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
            top_y - 84,
            page_width - right_margin,
            top_y - 84
        )

        # -----------------------------
        # 一、檢量線
        # -----------------------------
        calibration_title_y = (
            top_y - 96
        )

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            10
        )

        pdf_canvas.drawString(
            left_margin,
            calibration_title_y,
            "一、檢量線"
        )

        current_y = (
            calibration_title_y
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

            row_height = 16

            column_widths = [
                80,
                145,
                120,
                170
            ]

            headers = [
                "標準品",
                (
                    "設定濃度 ("
                    + calibration_unit
                    + ")"
                ),
                signal_label,
                (
                    "回歸濃度 ("
                    + calibration_unit
                    + ")"
                )
            ]

            current_x = left_margin

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

                current_x = left_margin

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

        return current_y


    sample_row_height = 17

    sample_column_widths = [
        40,   # 序號
        95,   # 樣品編號
        65,   # 稀釋倍數
        65,   # 測定值
        80,   # 添加濃度
        85,   # 測定濃度
        85    # 樣品濃度
    ]

    sample_headers = [
    "序號",
    "樣品編號",
    "稀釋倍數(D)",
    signal_label,
    (
        "添加濃度 ("
        + spike_conc_unit
        + ")"
    ),
    (
        "測定濃度 ("
        + display_conc_unit
        + ")"
    ),
    (
        "樣品濃度 ("
        + display_conc_unit
        + ")"
    )
    ]

    # ========================================
    # 共用：單一 Batch 樣品及品管分析結果
    # ========================================
    def draw_batch_samples(
        start_y,
        batch_rows
    ):

        sample_volume = None
        final_volume = None

        for row in batch_rows:

            if sample_volume is None:

                value = row.get(
                    "sample_volume"
                )

                if value is not None:
                    sample_volume = value

            if final_volume is None:

                value = row.get(
                    "final_volume"
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

        sample_title_y = (
            start_y - 18
        )

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            10
        )

        pdf_canvas.drawString(
            left_margin,
            sample_title_y,
            "二、樣品及品管分析結果"
        )

        condition_y = (
            sample_title_y - 12
        )

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            7.5
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
            sample_title_y - 22
        )

        pdf_canvas.drawString(
            left_margin,
            formula_y,
            "計算式：樣品濃度 = 測定濃度 × "
            "(最終定量體積 / 取樣體積) × "
            "稀釋倍數(D)"
        )

        sample_table_top_y = (
            sample_title_y - 29
        )

        current_x = left_margin

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            7.5
        )

        for index, header in enumerate(
            sample_headers
        ):

            width = sample_column_widths[
                index
            ]

            pdf_canvas.rect(
                current_x,
                sample_table_top_y
                - sample_row_height,
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

        for row in batch_rows:

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

            measured_concentration = (
                row.get(
                    "measured_concentration"
                )
            )

            sample_concentration = (
                row.get(
                    "sample_concentration"
                )
            )

            row_values = [
                (
                    str(sequence_no)
                    if sequence_no is not None
                    else "-"
                ),

                (
                    sample_id
                    if sample_id
                    else "-"
                ),

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
                        measured_concentration,
                        ".6f"
                    )
                    if measured_concentration
                    is not None
                    else "-"
                ),

                (
                    format(
                        sample_concentration,
                        ".6f"
                    )
                    if sample_concentration
                    is not None
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

        return current_y    

    # -----------------------------
    # 三、QA/QC 判定
    # -----------------------------
    # ========================================
    # 單一 Batch QA/QC 摘要資料
    # ========================================
    def build_batch_qaqc_summary_rows(
        batch_result
    ):

        summary_rows = []

        if not batch_result:
            return summary_rows

        batch_no = str(
            batch_result.get(
                "batch_no",
                ""
            )
            or ""
        ).strip()

        batch_category = str(
            batch_result.get(
                "batch_category",
                ""
            )
            or ""
        ).strip()

        batch_remark = str(
            batch_result.get(
                "batch_remark",
                ""
            )
            or ""
        ).strip()

        batch_title_parts = []

        if batch_no:

            batch_title_parts.append(
                "Batch " + batch_no
            )

        if batch_category:

            batch_title_parts.append(
                "類別：" + batch_category
            )

        if batch_remark:

            batch_title_parts.append(
                "批次備註：" + batch_remark
            )

        summary_rows.append(
            {
                "row_type":
                    "BATCH_HEADER",

                "item":
                    "｜".join(
                        batch_title_parts
                    )
            }
        )

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

            summary_rows.append(
                {
                    "item":
                        item_text,

                    "result":
                        result_text,

                    "control":
                        check.get(
                            "control_text",
                            "-"
                        ),

                    "status":
                        check.get(
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

            summary_rows.append(
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
                            "<= "
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

            summary_rows.append(
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

        return summary_rows

    qaqc_row_height = 14

    qaqc_column_widths = [
        175,  # 項目
        105,  # 結果
        160,  # 管制標準
        75    # 判定
    ]

    qaqc_headers = [
        "項目",
        "結果",
        "管制標準",
        "判定"
    ]

    # ========================================
    # 共用：單一 Batch QA/QC 判定
    # ========================================
    def draw_batch_qaqc(
        start_y,
        summary_rows
    ):

        qaqc_title_y = (
            start_y - 16
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
            qaqc_title_y - 6
        )

        current_x = left_margin

        pdf_canvas.setFont(
            "MicrosoftJhengHei",
            7.5
        )

        for index, header in enumerate(
            qaqc_headers
        ):

            width = qaqc_column_widths[
                index
            ]

            pdf_canvas.rect(
                current_x,
                qaqc_table_top_y
                - qaqc_row_height,
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

        for row in summary_rows:

            current_y -= qaqc_row_height

            if (
                row.get(
                    "row_type"
                )
                == "BATCH_HEADER"
            ):

                total_width = sum(
                    qaqc_column_widths
                )

                pdf_canvas.setFillColorRGB(
                    0.94,
                    0.96,
                    0.98
                )

                pdf_canvas.rect(
                    left_margin,
                    current_y,
                    total_width,
                    qaqc_row_height,
                    fill=1
                )

                pdf_canvas.setFillColorRGB(
                    0,
                    0,
                    0
                )

                pdf_canvas.setFont(
                    "MicrosoftJhengHei",
                    7.5
                )

                pdf_canvas.drawString(
                    left_margin + 5,
                    current_y + 4,
                    row.get(
                        "item",
                        ""
                    )
                )

                continue

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

        return current_y

    # ========================================
    # 所有 Batch 共用同一套頁面繪製流程
    # ========================================
    page_batches = (
        included_batches
        if included_batches
        else [
            {
                "batch_no": "",
                "rows": sample_qaqc_rows
            }
        ]
    )

    total_pages = len(
        page_batches
    )

    for batch_index, current_batch in enumerate(
        page_batches
    ):

        if batch_index > 0:

            pdf_canvas.showPage()

        # -----------------------------
        # 每頁完整表頭 + 檢量線
        # -----------------------------
        current_y = (
            draw_page_header_and_calibration()
        )

        # -----------------------------
        # 本 Batch 樣品
        # -----------------------------
        current_batch_rows = (
            current_batch.get(
                "rows",
                []
            )
        )

        current_y = (
            draw_batch_samples(
                current_y,
                current_batch_rows
            )
        )        

        # -----------------------------
        # 本 Batch QA/QC
        # -----------------------------
        current_batch_no = str(
            current_batch.get(
                "batch_no",
                ""
            )
            or ""
        ).strip()

        current_batch_qaqc = (
            qaqc_result_map.get(
                current_batch_no,
                {}
            )
        )

        # fallback：
        # 沒有 included_batches 時，
        # 保留單一 QA/QC 結果
        if (
            not current_batch_qaqc
            and not current_batch_no
            and qaqc_results
        ):

            current_batch_qaqc = (
                qaqc_results[0]
            )

        current_qaqc_rows = (
            build_batch_qaqc_summary_rows(
                current_batch_qaqc
            )
        )

        current_y = (
            draw_batch_qaqc(
                current_y,
                current_qaqc_rows
            )
        )

        # -----------------------------
        # 本頁頁尾
        # -----------------------------
        draw_page_footer(
            page_no=batch_index + 1,
            total_pages=total_pages
        )

    pdf_canvas.showPage()
    pdf_canvas.save()

    pdf_buffer.seek(0)

    return pdf_buffer