import json
from sqlalchemy import or_, and_
from models import AnalysisWorkState
# -*- coding: utf-8 -*-
"""
Phyon Performance History Query Service.

Read-only.
The caller manages the SQLAlchemy Session.
"""

from datetime import date

from sqlalchemy import func

from models import (
    AnalysisRecord,
    PerformanceMeasurementHistory,
    PerformanceAnalysisLink
)


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

    # ========================================
    # PFM V2.1 事件查詢
    # 每次實際量測只回傳一筆
    # ========================================

    query = db.query(
        PerformanceMeasurementHistory
    )

    if instrument_id:
        query = query.filter(
            PerformanceMeasurementHistory.instrument_id
            == instrument_id
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

    # 日期範圍以 PDF 分析時間為準
    if start_date:
        query = query.filter(
            func.date(
                PerformanceMeasurementHistory.analysis_datetime
            ) >= start_date.isoformat()
        )

    if end_date:
        query = query.filter(
            func.date(
                PerformanceMeasurementHistory.analysis_datetime
            ) <= end_date.isoformat()
        )

    # ========================================
    # PFM V2.1 類別篩選
    # 由 AnalysisRecord.category 取得
    # 同一 Event 可關聯多筆正式分析紀錄
    # ========================================

    if category:
        category_token = json.dumps({"category": category}, ensure_ascii=False)
        snapshot_match = db.query(AnalysisWorkState.id).filter(
            AnalysisWorkState.analysis_id == AnalysisRecord.analysis_id,
            AnalysisWorkState.state_json.contains(category_token, autoescape=True),
        ).correlate(AnalysisRecord).exists()
        matching_events = (
            db.query(
                PerformanceAnalysisLink.performance_id
            )
            .join(
                AnalysisRecord,
                AnalysisRecord.analysis_id
                == PerformanceAnalysisLink.analysis_id
            )
            .filter(
                or_(AnalysisRecord.category == category,
                    and_(AnalysisRecord.source_type == "ICP_IMPORT", snapshot_match))
            )
            .distinct()
        )

        query = query.filter(
            PerformanceMeasurementHistory.id.in_(
                matching_events
            )
        )

    rows = (
        query
        .order_by(
            PerformanceMeasurementHistory.analysis_datetime.desc(),
            PerformanceMeasurementHistory.id.desc()
        )
        .limit(limit)
        .all()
    )

    # ========================================
    # 取得查詢結果的所有分析關聯
    # ========================================

    event_ids = [row.id for row in rows]

    category_map = {}
    analysis_map = {}

    if event_ids:

        links = (
            db.query(
                PerformanceAnalysisLink,
                AnalysisRecord
            )
            .join(
                AnalysisRecord,
                AnalysisRecord.analysis_id
                == PerformanceAnalysisLink.analysis_id
            )
            .filter(
                PerformanceAnalysisLink.performance_id.in_(
                    event_ids
                )
            )
            .order_by(
                PerformanceAnalysisLink.performance_id,
                PerformanceAnalysisLink.id
            )
            .all()
        )

        for link, linked_record in links:
            linked_category = linked_record.category
            if linked_record.source_type == "ICP_IMPORT":
                from services.icp_record_service import load_snapshot
                categories = load_snapshot(db, linked_record).get("categories", [])
                category_map.setdefault(link.performance_id, set()).update(categories)
                linked_category = ""

            category_map.setdefault(
                link.performance_id, set()
            )

            analysis_map.setdefault(
                link.performance_id, []
            )

            analysis_map[link.performance_id].append(
                link.analysis_id
            )

            linked_category = str(
                linked_category or ""
            ).strip().upper()

            if linked_category:
                category_map[link.performance_id].add(
                    linked_category
                )

    # ========================================
    # 維持既有 HTML 使用的輸出欄位
    # ========================================

    result = []

    for row in rows:

        categories = sorted(
            category_map.get(row.id, set())
        )

        analysis_ids = analysis_map.get(
            row.id, []
        )

        result.append({
            "id": row.id,
            "analysis_id": (
                analysis_ids[0] if analysis_ids else ""
            ),
            "analysis_ids": analysis_ids,
            "analysis_date": (
                row.analysis_datetime.date().isoformat()
                if row.analysis_datetime
                else ""
            ),
            "analysis_datetime": (
                row.analysis_datetime.isoformat(
                    sep=" ", timespec="seconds"
                )
                if row.analysis_datetime
                else ""
            ),
            "instrument_id": row.instrument_id,
            "category": "、".join(categories),
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
        })

    return result
