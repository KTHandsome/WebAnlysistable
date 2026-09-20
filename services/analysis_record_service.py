from datetime import datetime
from typing import Optional

from database import SessionLocal

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary,
    AnalysisQaqcResult,
    AnalysisRecord,
    AnalysisSample
)

# ========================================
# 共用轉換
# ========================================

def _parse_required_date(
    value: str,
    field_name: str
):
    value = str(
        value or ""
    ).strip()

    if not value:
        raise ValueError(
            field_name
            + "不可空白。"
        )

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        raise ValueError(
            field_name
            + "格式不正確。"
        )


def _to_optional_float(
    value
) -> Optional[float]:

    if value is None:
        return None

    value_text = str(
        value
    ).strip()

    if value_text == "":
        return None

    try:

        return float(
            value_text
        )

    except (
        TypeError,
        ValueError
    ):

        return None


def _to_int(
    value,
    default_value: int
) -> int:

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return default_value

def _format_snapshot_number(
    value,
    decimal_places: int = 2
) -> str:

    number = _to_optional_float(
        value
    )

    if number is None:
        return ""

    return format(
        number,
        "."
        + str(decimal_places)
        + "f"
    )


def _status_to_pass(
    status
) -> Optional[bool]:

    status_text = str(
        status
        or ""
    ).strip()

    if status_text == "合格":
        return True

    if status_text in {
        "警告",
        "超出管制"
    }:
        return False

    return None


def _build_range_text(
    lower_control,
    lower_warning,
    upper_warning,
    upper_control,
    unit: str = "%"
) -> str:

    parts = []

    if lower_control is not None:
        parts.append(
            "LCL="
            + _format_snapshot_number(
                lower_control,
                1
            )
            + unit
        )

    if lower_warning is not None:
        parts.append(
            "LWL="
            + _format_snapshot_number(
                lower_warning,
                1
            )
            + unit
        )

    if upper_warning is not None:
        parts.append(
            "UWL="
            + _format_snapshot_number(
                upper_warning,
                1
            )
            + unit
        )

    if upper_control is not None:
        parts.append(
            "UCL="
            + _format_snapshot_number(
                upper_control,
                1
            )
            + unit
        )

    return " / ".join(
        parts
    )

# ========================================
# W434 正式分析紀錄
# ========================================

def save_w434_analysis_record(
    form_data,
    control_data,
    method_data,
    analysis_state,
    current_user
):

    if not form_data:
        raise ValueError(
            "尚未取得分析基本資料。"
        )

    if not control_data:
        raise ValueError(
            "尚未取得年度管制資料。"
        )

    if not method_data:
        raise ValueError(
            "尚未取得分析方法設定。"
        )

    if not analysis_state:
        raise ValueError(
            "尚未取得 W434 暫存分析資料。"
        )

    sample_rows = analysis_state.get(
        "sample_qaqc_rows",
        []
    )

    qaqc_results = analysis_state.get(
    "qaqc_results",
    []
    )

    calibration_rows = analysis_state.get(
    "calibration_rows",
    []
)

    calibration_result = analysis_state.get(
    "calibration_result"
)   
    

    if not sample_rows:
        raise ValueError(
            "目前沒有可建立正式紀錄的分析明細。"
        )

    if not calibration_rows:
        raise ValueError(
        "目前沒有可建立正式紀錄的檢量線資料。"
    )

    if not calibration_result:
       raise ValueError(
        "目前沒有有效的檢量線計算結果。"
    )

    # ========================================
    # Basic Info
    # ========================================

    form_date = _parse_required_date(
        form_data.get(
            "form_date",
            ""
        ),
        "填表日期"
    )

    analysis_start_date = (
        _parse_required_date(
            form_data.get(
                "analysis_start_date",
                ""
            ),
            "分析日期起"
        )
    )

    analysis_end_date = (
        _parse_required_date(
            form_data.get(
                "analysis_end_date",
                ""
            ),
            "分析日期迄"
        )
    )

    if (
        analysis_end_date
        < analysis_start_date
    ):

        raise ValueError(
            "分析日期迄不可早於分析日期起。"
        )

    # ========================================
    # 波長
    # 優先使用已確認的波長
    # ========================================

    wavelength = _to_optional_float(
        analysis_state.get(
            "confirmed_wavelength"
        )
    )

    if wavelength is None:

        wavelength = _to_optional_float(
            form_data.get(
                "wavelength"
            )
        )

    # ========================================
    # 登入者
    # ========================================

    current_user = (
        current_user
        or {}
    )

    analyst_user_id = str(
        current_user.get(
            "user_id",
            ""
        )
        or ""
    ).strip()

    analyst_employee_id = str(
        current_user.get(
            "employee_id",
            ""
        )
        or ""
    ).strip()

    analyst_name = str(
        current_user.get(
            "employee_name",
            ""
        )
        or ""
    ).strip()

    if not analyst_user_id:
        raise ValueError(
            "尚未取得登入者帳號。"
        )

    # ========================================
    # 資料來源
    # ========================================

    source_filename = str(
        analysis_state.get(
            "uploaded_filename",
            ""
        )
        or ""
    ).strip()

    source_type = (
        "IMPORT"
        if source_filename
        else "MANUAL"
    )

    # ========================================
    # Database
    # ========================================

    db = SessionLocal()

    try:

        formal_analysis_id = str(
            analysis_state.get(
                "formal_analysis_id",
                ""
            )
            or ""
        ).strip()

        record = None

        # ========================================
        # 已建立正式 DRAFT
        # → 更新同一筆，不重複新增
        # ========================================

        if formal_analysis_id:

            record = (
                db.query(
                    AnalysisRecord
                )
                .filter(
                    AnalysisRecord.analysis_id
                    == formal_analysis_id
                )
                .first()
            )

        if record is not None:

            if (
                record.status
                != "DRAFT"
            ):

                raise ValueError(
                    "此正式分析紀錄已不是草稿狀態，"
                    "不可直接覆寫。"
                )

        # ========================================
        # 尚未建立
        # → 新增 AnalysisRecord
        # ========================================

        else:

            record = AnalysisRecord(
                status="DRAFT",

                ctrl_year=str(
                    form_data.get(
                        "ctrl_year",
                        ""
                    )
                    or ""
                ).strip(),

                category=str(
                    form_data.get(
                        "category",
                        ""
                    )
                    or ""
                ).strip(),

                exam_no=str(
                    control_data.get(
                        "EXAMNO",
                        ""
                    )
                    or ""
                ).strip(),

                exam_name=str(
                    form_data.get(
                        "exam_name",
                        ""
                    )
                    or ""
                ).strip(),

                method_code=str(
                    form_data.get(
                        "method_code",
                        ""
                    )
                    or ""
                ).strip(),

                method_name=str(
                    control_data.get(
                        "EM_NO",
                        ""
                    )
                    or ""
                ).strip(),

                instrument_id=str(
                    form_data.get(
                        "instrument_id",
                        ""
                    )
                    or ""
                ).strip(),

                instrument_model=str(
                    form_data.get(
                        "instrument_model",
                        ""
                    )
                    or ""
                ).strip(),

                form_date=form_date,

                analysis_start_date=(
                    analysis_start_date
                ),

                analysis_end_date=(
                    analysis_end_date
                ),

                wavelength=wavelength,

                analyst_user_id=(
                    analyst_user_id
                ),

                analyst_employee_id=(
                    analyst_employee_id
                ),

                analyst_name=(
                    analyst_name
                ),

                source_type=source_type,

                source_filename=(
                    source_filename
                )
            )

            db.add(
                record
            )

            db.flush()

        # ========================================
        # 更新主檔
        # ========================================

        record.ctrl_year = str(
            form_data.get(
                "ctrl_year",
                ""
            )
            or ""
        ).strip()

        record.category = str(
            form_data.get(
                "category",
                ""
            )
            or ""
        ).strip()

        record.exam_no = str(
            control_data.get(
                "EXAMNO",
                ""
            )
            or ""
        ).strip()

        record.exam_name = str(
            form_data.get(
                "exam_name",
                ""
            )
            or ""
        ).strip()

        record.method_code = str(
            form_data.get(
                "method_code",
                ""
            )
            or ""
        ).strip()

        record.method_name = str(
            control_data.get(
                "EM_NO",
                ""
            )
            or ""
        ).strip()

        record.instrument_id = str(
            form_data.get(
                "instrument_id",
                ""
            )
            or ""
        ).strip()

        record.instrument_model = str(
            form_data.get(
                "instrument_model",
                ""
            )
            or ""
        ).strip()

        record.form_date = form_date

        record.analysis_start_date = (
            analysis_start_date
        )

        record.analysis_end_date = (
            analysis_end_date
        )

        record.wavelength = wavelength

        record.analyst_user_id = (
            analyst_user_id
        )

        record.analyst_employee_id = (
            analyst_employee_id
        )

        record.analyst_name = (
            analyst_name
        )

        record.source_type = (
            source_type
        )

        record.source_filename = (
            source_filename
        )

        # ========================================
        # 若是更新既有草稿
        # 先清除原有 AnalysisSample
        # 再依目前暫存內容重建
        # ========================================

        db.query(
            AnalysisSample
        ).filter(
            AnalysisSample.analysis_id
            == record.analysis_id
        ).delete(
            synchronize_session=False
        )

        db.query(
           AnalysisQaqcResult
        ).filter(
           AnalysisQaqcResult.analysis_id
           == record.analysis_id
        ).delete(
           synchronize_session=False
        )

        db.query(
           AnalysisCalibrationPoint
        ).filter(
           AnalysisCalibrationPoint.analysis_id
            == record.analysis_id
        ).delete(
           synchronize_session=False
        )

        db.query(
           AnalysisCalibrationSummary
        ).filter(
           AnalysisCalibrationSummary.analysis_id
            == record.analysis_id
        ).delete(
           synchronize_session=False
        )


        # ========================================
        # AnalysisCalibrationSummary
        # ========================================

        slope = _to_optional_float(
              calibration_result.get(
                    "slope"
            )
        )

        intercept = _to_optional_float(
            calibration_result.get(
                 "intercept"
            )
        )

        correlation_r = _to_optional_float(
           calibration_result.get(
                "r"
            )
        )

        if slope is None:
           raise ValueError(
                 "檢量線斜率無效。"
        )

        if intercept is None:
          raise ValueError(
                 "檢量線截距無效。"
        )

        if correlation_r is None:
          raise ValueError(
               "檢量線相關係數無效。"
        )


        calibration_summary = AnalysisCalibrationSummary(
           analysis_id=record.analysis_id,
           slope=slope,
           intercept=intercept,
           correlation_r=correlation_r,
           is_pass=bool(
             calibration_result.get(
                 "passed",
                   False
                )
            )
        )

        db.add(
             calibration_summary
        )


        # ========================================
        # AnalysisCalibrationPoint
        # ========================================

        calibration_points = calibration_result.get(
            "points",
             []
         )

        if not calibration_points:

             raise ValueError(
                "檢量線缺少標準點計算結果。"
        )


        for index, point in enumerate(
            calibration_points,
            start=1
        ):

            concentration = _to_optional_float(
                point.get(
                    "x"
                )
            )

            signal = _to_optional_float(
                point.get(
                    "y"
                )
            )

            if concentration is None:

                raise ValueError(
                    "第 "
                    + str(index)
                    + " 筆檢量線標準濃度無效。"
                )

            if signal is None:

                raise ValueError(
                    "第 "
                    + str(index)
                    + " 筆檢量線測定值無效。"
                )

            back_calculated_concentration = (
                _to_optional_float(
                    point.get(
                        "back_calculated_x"
                    )
                )
            )

            error_percent = None

            if (
                concentration != 0
                and back_calculated_concentration is not None
            ):

                                error_percent = round(
                    (
                        (
                            back_calculated_concentration
                            - concentration
                        )
                        / concentration
                    ) * 100,
                    2
                )

            calibration_point = AnalysisCalibrationPoint(
                analysis_id=record.analysis_id,

                display_order=index,

                standard_id=str(
                    point.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip(),

                concentration=concentration,

                signal=signal,

                back_calculated_concentration=(
                    back_calculated_concentration
                ),

                error_percent=(
                    error_percent
                )
            )

            db.add(
                calibration_point
            )

        # ========================================
        # AnalysisSample
        # ========================================

        for index, row in enumerate(
            sample_rows,
            start=1
        ):

            sample = AnalysisSample(
                analysis_id=record.analysis_id,

                sequence_no=_to_int(
                    row.get(
                        "sequence_no"
                    ),
                    index
                ),

                display_order=_to_int(
                    row.get(
                        "display_order"
                    ),
                    index
                ),

                sample_id=str(
                    row.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip(),

                role=str(
                    row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip(),

                signal=_to_optional_float(
                    row.get(
                        "signal"
                    )
                ),

                sample_volume=(
                    _to_optional_float(
                        row.get(
                            "sample_volume"
                        )
                    )
                ),

                final_volume=(
                    _to_optional_float(
                        row.get(
                            "final_volume"
                        )
                    )
                ),

                dilution_factor=(
                    _to_optional_float(
                        row.get(
                            "dilution_factor"
                        )
                    )
                ),

                spike_concentration=(
                    _to_optional_float(
                        row.get(
                            "spike_concentration"
                        )
                    )
                ),

                calculated_concentration=(
                    _to_optional_float(
                        row.get(
                            "calculated_concentration"
                        )
                    )
                ),

                remark=str(
                    row.get(
                        "remark",
                        ""
                    )
                    or ""
                ).strip()
            )

            db.add(
                sample
            )

        # ========================================
        # AnalysisQaqcResult
        #
        # 將 W434 目前 QA/QC 判定結果
        # 保存為正式 Snapshot
        # ========================================

        qaqc_display_order = 1

        for batch in qaqc_results:

            batch_no = str(
                batch.get(
                    "batch_no",
                    ""
                )
                or ""
            ).strip()

            batch_category = str(
                batch.get(
                    "batch_category",
                    ""
                )
                or ""
            ).strip()

            # ====================================
            # 3A：ICV / QC / CCV
            # ====================================

            for qaqc_row in batch.get(
                "rows",
                []
            ):

                role = str(
                    qaqc_row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                sample_id = str(
                    qaqc_row.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip()

                calculation_name = str(
                    qaqc_row.get(
                        "calculation_name",
                        ""
                    )
                    or ""
                ).strip()

                check_value = (
                    qaqc_row.get(
                        "check_value"
                    )
                )

                control_text = str(
                    qaqc_row.get(
                        "control_text",
                        ""
                    )
                    or ""
                ).strip()

                warning_text = str(
                    qaqc_row.get(
                        "warning_text",
                        ""
                    )
                    or ""
                ).strip()

                status = str(
                    qaqc_row.get(
                        "status",
                        ""
                    )
                    or ""
                ).strip()

                remark_parts = []

                if batch_no:
                    remark_parts.append(
                        "批次 "
                        + batch_no
                    )

                if batch_category:
                    remark_parts.append(
                        batch_category
                    )

                check_position = str(
                    qaqc_row.get(
                        "check_position",
                        ""
                    )
                    or ""
                ).strip()

                if check_position:
                    remark_parts.append(
                        check_position
                    )

                if warning_text:
                    remark_parts.append(
                        warning_text
                    )

                qaqc_item = AnalysisQaqcResult(
                    analysis_id=record.analysis_id,
                    display_order=qaqc_display_order,
                    qaqc_type=role,
                    sample_id=sample_id,
                    result_name=(
                        calculation_name
                        if calculation_name
                        else role
                    ),
                    result_value=(
                        _format_snapshot_number(
                            check_value,
                            2
                        )
                        + "%"
                        if check_value is not None
                        else ""
                    ),
                    criteria_text=control_text,
                    is_pass=_status_to_pass(
                        status
                    ),
                    remark=" / ".join(
                        remark_parts
                    )
                )

                db.add(
                    qaqc_item
                )

                qaqc_display_order += 1

            # ====================================
            # 3B：重複分析精密度
            # ====================================

            precision = batch.get(
                "precision"
            )

            if precision:

                sample_id_a = str(
                    precision.get(
                        "sample_id_a",
                        ""
                    )
                    or ""
                ).strip()

                sample_id_b = str(
                    precision.get(
                        "sample_id_b",
                        ""
                    )
                    or ""
                ).strip()

                sample_ids = " / ".join(
                    value
                    for value in [
                        sample_id_a,
                        sample_id_b
                    ]
                    if value
                )

                status = str(
                    precision.get(
                        "status",
                        ""
                    )
                    or ""
                ).strip()

                criteria_text = _build_range_text(
                    None,
                    None,
                    precision.get(
                        "uwl"
                    ),
                    precision.get(
                        "ucl"
                    ),
                    "%"
                )

                remark_parts = []

                source_name = str(
                    precision.get(
                        "source_name",
                        ""
                    )
                    or ""
                ).strip()

                if source_name:
                    remark_parts.append(
                        source_name
                    )

                reason = str(
                    precision.get(
                        "reason",
                        ""
                    )
                    or ""
                ).strip()

                if reason:
                    remark_parts.append(
                        reason
                    )

                if batch_no:
                    remark_parts.append(
                        "批次 "
                        + batch_no
                    )

                qaqc_item = AnalysisQaqcResult(
                    analysis_id=record.analysis_id,
                    display_order=qaqc_display_order,
                    qaqc_type="PRECISION",
                    sample_id=sample_ids,
                    result_name="重複分析精密度 RPD",
                    result_value=(
                        _format_snapshot_number(
                            precision.get(
                                "rpd"
                            ),
                            2
                        )
                        + "%"
                        if precision.get(
                            "rpd"
                        ) is not None
                        else ""
                    ),
                    criteria_text=criteria_text,
                    is_pass=_status_to_pass(
                        status
                    ),
                    remark=" / ".join(
                        remark_parts
                    )
                )

                db.add(
                    qaqc_item
                )

                qaqc_display_order += 1

            # ====================================
            # 3C：MS / MSD 添加樣品回收率
            # ====================================

            for spike_row in batch.get(
                "spike_recovery",
                []
            ):

                role = str(
                    spike_row.get(
                        "role",
                        ""
                    )
                    or ""
                ).strip()

                sample_id = str(
                    spike_row.get(
                        "sample_id",
                        ""
                    )
                    or ""
                ).strip()

                original_sample_id = str(
                    spike_row.get(
                        "original_sample_id",
                        ""
                    )
                    or ""
                ).strip()

                status = str(
                    spike_row.get(
                        "status",
                        ""
                    )
                    or ""
                ).strip()

                criteria_text = _build_range_text(
                    spike_row.get(
                        "lcl"
                    ),
                    spike_row.get(
                        "lwl"
                    ),
                    spike_row.get(
                        "uwl"
                    ),
                    spike_row.get(
                        "ucl"
                    ),
                    "%"
                )

                remark_parts = []

                if original_sample_id:
                    remark_parts.append(
                        "原樣："
                        + original_sample_id
                    )

                if batch_no:
                    remark_parts.append(
                        "批次 "
                        + batch_no
                    )

                qaqc_item = AnalysisQaqcResult(
                    analysis_id=record.analysis_id,
                    display_order=qaqc_display_order,
                    qaqc_type=role,
                    sample_id=sample_id,
                    result_name=(
                        role
                        + " 添加樣品回收率"
                    ),
                    result_value=(
                        _format_snapshot_number(
                            spike_row.get(
                                "recovery"
                            ),
                            2
                        )
                        + "%"
                        if spike_row.get(
                            "recovery"
                        ) is not None
                        else ""
                    ),
                    criteria_text=criteria_text,
                    is_pass=_status_to_pass(
                        status
                    ),
                    remark=" / ".join(
                        remark_parts
                    )
                )

                db.add(
                    qaqc_item
                )

                qaqc_display_order += 1

        db.commit()

        db.refresh(
            record
        )

        return {
    "analysis_id":
        record.analysis_id,

    "record_id":
        record.id,

    "status":
        record.status,

    "sample_count":
        len(sample_rows),

    "qaqc_count":
        qaqc_display_order - 1,

    "calibration_point_count":
       len(calibration_points)    

        }

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()