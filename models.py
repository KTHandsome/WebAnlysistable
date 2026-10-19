from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func
)

from sqlalchemy.orm import Mapped, mapped_column

from database import Base

class SystemTest(Base):
    __tablename__ = "system_test"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

class AnalysisRecord(Base):
    __tablename__ = "analysis_record"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid4())
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT"
    )

    ctrl_year: Mapped[str] = mapped_column(
        String(4),
        nullable=False
    )

    # 分析類別：D / W / G
    category: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )

    exam_no: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    exam_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    method_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    instrument_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    instrument_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    form_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    analysis_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    analysis_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    wavelength: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    analyst_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    analyst_employee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    analyst_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    reviewer_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    reviewer_employee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    reviewer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    review_comment: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=""
    )

    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=""
    )

    source_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=""
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class AnalysisSample(Base):
    __tablename__ = "analysis_sample"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        index=True
    )

    sequence_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    sample_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    signal: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    sample_volume: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    final_volume: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    dilution_factor: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    spike_concentration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    calculated_concentration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    measured_concentration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    sample_concentration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    qaqc_concentration: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )    

    remark: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=""
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class AnalysisQaqcResult(Base):
    __tablename__ = "analysis_qaqc_result"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        index=True
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    qaqc_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    sample_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    result_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    result_value: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default=""
    )

    criteria_text: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        default=""
    )

    is_pass: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )

    status_text: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=""
    )

    remark: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=""
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class AnalysisCalibrationSummary(Base):
    __tablename__ = "analysis_calibration_summary"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        unique=True,
        index=True
    )

    slope: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    intercept: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    correlation_r: Mapped[float] = mapped_column(
    Float,
    nullable=False
    )

    is_pass: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )


class AnalysisCalibrationPoint(Base):
    __tablename__ = "analysis_calibration_point"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        index=True
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    standard_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    concentration: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    signal: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    back_calculated_concentration: Mapped[Optional[float]] = mapped_column(
    Float,
    nullable=True
    )

    error_percent: Mapped[Optional[float]] = mapped_column(
    Float,
    nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )    

class AnalysisWorkState(Base):
    __tablename__ = "analysis_work_state"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        unique=True,
        index=True
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    state_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    form_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    control_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    method_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    report_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class AnalysisWorkDraft(Base):
    __tablename__ = "analysis_work_draft"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    work_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True
    )

    owner_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    formal_analysis_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True
    )

    work_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EDITING"
    )

    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    state_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    # Basic analysis information snapshot.
    form_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    # Annual control configuration snapshot.
    control_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    # Analytical method configuration snapshot.
    method_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    # Report configuration snapshot.
    report_data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class IcpImportWorkState(Base):
    __tablename__ = "icp_import_work_state"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    work_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    source_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=""
    )

    state_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

class AnalysisReviewHistory(Base):
    __tablename__ = "analysis_review_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "analysis_record.analysis_id"
        ),
        nullable=False,
        index=True
    )

    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    from_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=""
    )

    to_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=""
    )

    reviewer_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    reviewer_employee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    reviewer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    comment: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=""
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

class AnalysisDeleteHistory(Base):
    __tablename__ = "analysis_delete_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True
    )

    record_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    exam_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    analyst_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    record_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=""
    )

    deleted_by_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    deleted_by_employee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    deleted_by_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    delete_reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

# ========================================
# Performance CSV 匯入批次歷程
# ========================================

class PerformanceImportHistory(Base):

    __tablename__ = "performance_import_history"

    import_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    control_versions_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]"
    )

    imported_by: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        index=True
    )


# ========================================
# Performance 儀器管制設定
# 每筆資料對應一次 CSV 匯入批次
# ========================================

class InstrumentPerformanceControl(Base):

    __tablename__ = "instrument_performance_control"

    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "control_id",
            name="uq_performance_import_control"
        ),
    )

    # ----------------------------------------
    # 資料庫識別
    # ----------------------------------------

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    import_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "performance_import_history.import_id"
        ),
        nullable=False,
        index=True
    )

    # ----------------------------------------
    # CSV：儀器與管制項目
    # ----------------------------------------

    control_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    instrument_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    instrument_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    effective_from: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    effective_to: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    performance_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    monitor_item: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # ----------------------------------------
    # CSV：訊號項目與波長
    # ----------------------------------------

    numerator_item: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    numerator_wavelength_nm: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4, asdecimal=False),
        nullable=True
    )

    denominator_item: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    denominator_wavelength_nm: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4, asdecimal=False),
        nullable=True
    )

    target_wavelength_nm: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4, asdecimal=False),
        nullable=True
    )

    # ----------------------------------------
    # CSV：管制平均值與上下限
    # 由 LIMS 計算、品保審核後匯入
    # Phyon 不重新計算 15 次平均與 3SD
    # ----------------------------------------

    reference_value: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    lower_limit: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    upper_limit: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    # ----------------------------------------
    # CSV：管制狀態及其他資訊
    # ----------------------------------------

    sample_labels: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    frequency: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )

    control_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    sop_reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=""
    )

    notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=""
    )


# ========================================
# PRM 儀器性能查核歷程
# ========================================
class PerformanceMeasurementHistory(Base):

    __tablename__ = "performance_measurement_history"

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "monitor_item",
            "performance_type",
            "analysis_datetime",
            name="uq_pfm_measurement_event"
        ),
    )

    # 資料庫識別
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    # 儀器與分析資訊
    instrument_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    method_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    monitor_item: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    performance_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # PRM 原始量測資料
    sample_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # PFM 實際分析時間，以儀器 PDF 為唯一來源
    analysis_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True
    )

    measured_value: Mapped[float] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=False
    )

    signal_field: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # 當時使用的管制標準版本
    control_import_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True
    )

    control_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    reference_value: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    lower_limit: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    upper_limit: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 8, asdecimal=False),
        nullable=True
    )

    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=""
    )

    # 管制判定
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=""
    )

# ========================================
# PFM V2.1 儀器性能確校與正式分析紀錄關聯
# ========================================
class PerformanceAnalysisLink(Base):

    __tablename__ = "performance_analysis_link"

    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "prm_sequence_no",
            name="uq_pfm_link_analysis_sequence"
        ),
        UniqueConstraint(
            "analysis_id",
            "performance_id",
            name="uq_pfm_link_analysis_performance"
        ),
    )

    # 關聯資料庫主鍵
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    # PFM 量測事件
    performance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("performance_measurement_history.id"),
        nullable=False,
        index=True
    )

    # 正式分析紀錄
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_record.analysis_id"),
        nullable=False,
        index=True
    )

    # 同一分析紀錄中的 PFM 順序
    prm_sequence_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )


