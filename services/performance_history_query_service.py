# -*- coding: utf-8 -*-
"""
Phyon Performance History Query Service.

Read-only.
The caller manages the SQLAlchemy Session.
"""

from datetime import date

from models import PerformanceMeasurementHistory


def _parse_query_date(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(
            "日期格式錯誤，請使用 YYYY-MM-DD。"
        )


def query_performance_history(
    db,
    instrument_id="",
    category="",
    monitor_item="",
    status="",
    analysis_date_start="",
    analysis_date_end="",
    limit=200
):
    """
    Search historical PRM records using optional filters.
    """

    instrument_id = str(instrument_id or "").strip()
    category = str(category or "").strip().upper()
    monitor_item = str(monitor_item or "").strip()
    status = str(status or "").strip().upper()

    if status and status not in {
        "PASS",
        "FAIL",
        "UNDETERMINED"
    }:
        raise ValueError("無效的性能查核判定條件。")

    start_date = _parse_query_date(
        analysis_date_start
    )

    end_date = _parse_query_date(
        analysis_date_end
    )

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise ValueError(
            "分析日期起不可晚於分析日期迄。"
        )

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("查詢筆數設定錯誤。")

    if not 1 <= limit <= 200:
        raise ValueError(
            "查詢筆數必須介於 1 至 200。"
        )

    query = db.query(
        PerformanceMeasurementHistory
    )

    if instrument_id:
        query = query.filter(
            PerformanceMeasurementHistory.instrument_id
            == instrument_id
        )

    if category:
        query = query.filter(
            PerformanceMeasurementHistory.category
            == category
        )

    if monitor_item:
        query = query.filter(
            PerformanceMeasurementHistory.monitor_item
            == monitor_item
        )

    if status:
        query = query.filter(
            PerformanceMeasurementHistory.status
            == status
        )

    if start_date:
        query = query.filter(
            PerformanceMeasurementHistory.analysis_date
            >= start_date
        )

    if end_date:
        query = query.filter(
            PerformanceMeasurementHistory.analysis_date
            <= end_date
        )

    rows = (
        query
        .order_by(
            PerformanceMeasurementHistory.analysis_date.desc(),
            PerformanceMeasurementHistory.id.desc()
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "id": row.id,
            "analysis_id": row.analysis_id,
            "analysis_date": (
                row.analysis_date.isoformat()
                if row.analysis_date
                else ""
            ),
            "instrument_id": row.instrument_id,
            "category": row.category,
            "method_code": row.method_code,
            "monitor_item": row.monitor_item,
            "performance_type": row.performance_type,
            "sample_id": row.sample_id,
            "measured_value": row.measured_value,
            "reference_value": row.reference_value,
            "lower_limit": row.lower_limit,
            "upper_limit": row.upper_limit,
            "unit": row.unit,
            "status": row.status,
            "control_id": row.control_id,
            "control_import_id": row.control_import_id,
            "message": row.message
        }
        for row in rows
    ]
