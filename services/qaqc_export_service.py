def validate_qaqc_export_ready(
    qaqc_results,
    has_control_data=True
):

    # ========================================
    # 無管制圖項目
    # 不執行 QA/QC 管制判定，
    # 直接允許正式儲存 / 匯出
    # ========================================
    if not has_control_data:

        return (
            True,
            ""
        )

    # ========================================
    # 有管制圖，但尚未產生 QA/QC 判定
    # 仍然屬於不完整資料，不可放行
    # ========================================
    if not qaqc_results:

        return (
            False,
            "已有年度管制資料，"
            "但尚未完成 QA/QC 判定，"
            "不可匯出。"
        )

    invalid_batches = []

    for batch in qaqc_results:

        batch_no = str(
            batch.get(
                "batch_no",
                ""
            )
            or ""
        ).strip()

        batch_label = (
            "Batch "
            + batch_no
            if batch_no
            else "未識別批次"
        )

        batch_remark = str(
            batch.get(
                "batch_remark",
                ""
            )
            or ""
        ).strip()

        batch_invalid_items = []

        # ========================================
        # 3A：ICV / QC / CCV
        # ========================================
        for row in batch.get(
            "rows",
            []
        ):

            status = str(
                row.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                role = str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                sample_id = str(
                    row.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip()

                batch_invalid_items.append(
                    role
                    + (
                        " / "
                        + sample_id
                        if sample_id
                        else ""
                    )
                    + "："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 3B：重複分析精密度
        # ========================================
        precision = batch.get(
            "precision"
        )

        if precision:

            status = str(
                precision.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                batch_invalid_items.append(
                    "重複分析精密度："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 3C：MS / MSD 回收率
        # ========================================
        for row in batch.get(
            "spike_recovery",
            []
        ):

            status = str(
                row.get(
                    "status",
                    ""
                )
                or ""
            ).strip()

            if status != "合格":

                role = str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                batch_invalid_items.append(
                    role
                    + " 回收率："
                    + (
                        status
                        if status
                        else "無法判定"
                    )
                )

        # ========================================
        # 此批次若有超限，
        # 必須有批次備註才可放行
        # ========================================
        if batch_invalid_items:

            if not batch_remark:

                invalid_batches.append(
                    batch_label
                    + " 尚有 QA/QC 超限，"
                    + "但未填寫批次備註：\n"
                    + "\n".join(
                        batch_invalid_items
                    )
                )

    if invalid_batches:

        return (
            False,
            "QA/QC 有超限批次尚未填寫備註，"
            "不可匯出：\n"
            + "\n".join(
                invalid_batches
            )
        )

    return (
        True,
        ""
    )
