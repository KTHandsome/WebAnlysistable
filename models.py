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
    String,
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