from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LimsQcRow:
    analysis_date: str = ""
    analyst: str = ""
    exam_no: str = ""
    instrument_id: str = ""

    max_signal: Optional[float] = None
    duplicate_result: Optional[float] = None
    qc_result: Optional[float] = None
    spike_result: Optional[float] = None
    calibration_check: Optional[float] = None
    blank_result: str = ""

    remark: str = ""
    batch_no: str = ""
    correlation_coefficient: Optional[float] = None


@dataclass
class LimsAnalysisRow:
    sample_id: str = ""
    exam_no: str = ""
    result: str = ""
    actual_item: str = ""
    batch_no: str = ""
    remark: str = ""


@dataclass
class LimsExportData:
    qc_rows: List[LimsQcRow] = field(
        default_factory=list
    )

    analysis_rows: List[LimsAnalysisRow] = field(
        default_factory=list
    )