# -*- coding: utf-8 -*-
"""
Phyon PRM Performance Trend Query Service.

Read-only service.
Uses an externally supplied SQLAlchemy Session.
Does not commit, rollback, or close the Session.
"""

from models import PerformanceMeasurementHistory


def get_performance_trend(
    db,
    instrument_id,
    monitor_item,
    performance_type,
    limit=30
):
    """
    Retrieve the latest valid PRM measurements.

    Results are returned chronologically for charting.
    """

    instrument_id = str(
        instrument_id or ""
    ).strip()

    monitor_item = str(
        monitor_item or ""
    ).strip()

    performance_type = str(
        performance_type or ""
    ).strip()

    if not instrument_id:
        raise ValueError("Missing instrument_id")

    if not monitor_item:
        raise ValueError("Missing monitor_item")

    if not performance_type:
        raise ValueError("Missing performance_type")

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("Invalid PRM trend limit")

    if not 1 <= limit <= 30:
        raise ValueError(
            "PRM trend limit must be between 1 and 30"
        )

    rows = (
        db.query(PerformanceMeasurementHistory)
        .filter(
            PerformanceMeasurementHistory.instrument_id
            == instrument_id,
            PerformanceMeasurementHistory.monitor_item
            == monitor_item,
            PerformanceMeasurementHistory.performance_type
            == performance_type,
            PerformanceMeasurementHistory.status.in_(
                ["PASS", "FAIL"]
            )
        )
        .order_by(
            PerformanceMeasurementHistory.analysis_datetime.desc(),
            PerformanceMeasurementHistory.id.desc()
        )
        .limit(limit)
        .all()
    )

    # Oldest -> newest for line charts.
    rows = list(reversed(rows))

    points = []

    for row in rows:

        points.append({
            "id": row.id,
            "analysis_date": (
                row.analysis_datetime.date().isoformat()
                if row.analysis_datetime
                else ""
                ),
            "analysis_datetime": (
                row.analysis_datetime.isoformat(
                sep=" ",
                timespec="seconds"
                )
                if row.analysis_datetime
                else ""
                ),
            "instrument_id": row.instrument_id,
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
            "control_import_id": row.control_import_id
        })

    return {
        "instrument_id": instrument_id,
        "monitor_item": monitor_item,
        "performance_type": performance_type,
        "count": len(points),
        "points": points
    }
