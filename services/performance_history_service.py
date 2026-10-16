# -*- coding: utf-8 -*-
"""
Phyon PRM performance measurement history.

This service uses the caller's SQLAlchemy Session.
It must not commit, rollback, or close that Session.
"""

from datetime import date, datetime
import math

from models import (
    PerformanceMeasurementHistory,
    PerformanceAnalysisLink
)


def _parse_prm_date(value):
    """
    Accepts dates such as:
    2026/10/13  下午05:12:
    2026/10/13
    2026-10-13
    """
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value or "").strip()

    if not value:
        raise ValueError("PRM analysis date is missing")

    date_part = value[:10].replace("/", "-")

    try:
        return date.fromisoformat(date_part)
    except ValueError:
        raise ValueError(
            "Invalid PRM analysis date: {}".format(value)
        )

def _parse_pfm_datetime(value):
    """
    Parse the actual PFM analysis time from the instrument PDF.
    Never substitute an import or save timestamp.
    """

    import re

    if isinstance(value, datetime):
        return value

    text = str(value or "").strip()

    if not text:
        raise ValueError("PFM analysis datetime is missing")

    text = re.sub(r"\s+", " ", text).rstrip(":")

    am_text = "\u4e0a\u5348"
    pm_text = "\u4e0b\u5348"

    if am_text in text or pm_text in text:

        text = text.replace(am_text, "AM ")
        text = text.replace(pm_text, "PM ")

        formats = (
            "%Y/%m/%d %p %I:%M:%S",
            "%Y/%m/%d %p %I:%M",
        )

    else:

        formats = (
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError(
        "Invalid PFM analysis datetime: {}".format(ascii(text))
    )

def _compare_pfm_event(existing, candidate):
    """
    Compare two PFM measurement events.

    Returns:
        MATCH     - Same event identity and content
        DIFFERENT - Different measurement identity
        CONFLICT  - Same identity but inconsistent content

    No database operations.
    """

    identity_fields = (
        "instrument_id",
        "monitor_item",
        "performance_type",
        "analysis_datetime",
    )

    content_fields = (
        "sample_id",
        "measured_value",
        "signal_field",
        "method_code",
        "control_import_id",
        "control_id",
        "reference_value",
        "lower_limit",
        "upper_limit",
        "unit",
        "status",
    )

    for field in identity_fields:
        if existing.get(field) != candidate.get(field):
            return "DIFFERENT"

    for field in content_fields:
        if existing.get(field) != candidate.get(field):
            return "CONFLICT"

    return "MATCH"

def _find_existing_pfm_event(db, candidate):
    """
    Find an existing PFM measurement event.

    Returns:
        PerformanceMeasurementHistory object or None

    Raises:
        ValueError on conflicting or ambiguous events.

    Does not insert, update, delete, or commit.
    """

    required_fields = (
        "instrument_id",
        "monitor_item",
        "performance_type",
        "analysis_datetime",
    )

    for field in required_fields:
        if candidate.get(field) is None or candidate.get(field) == "":
            raise ValueError(
                "Missing PFM event identity: {}".format(field)
            )

    matches = (
        db.query(PerformanceMeasurementHistory)
        .filter(
            PerformanceMeasurementHistory.instrument_id
            == candidate["instrument_id"],

            PerformanceMeasurementHistory.monitor_item
            == candidate["monitor_item"],

            PerformanceMeasurementHistory.performance_type
            == candidate["performance_type"],

            PerformanceMeasurementHistory.analysis_datetime
            == candidate["analysis_datetime"]
        )
        .order_by(
            PerformanceMeasurementHistory.id
        )
        .all()
    )

    fields = (
        "instrument_id",
        "monitor_item",
        "performance_type",
        "analysis_datetime",
        "sample_id",
        "measured_value",
        "signal_field",
        "method_code",
        "control_import_id",
        "control_id",
        "reference_value",
        "lower_limit",
        "upper_limit",
        "unit",
        "status",
    )

    matched_events = []

    for event in matches:

        existing = {
            field: getattr(event, field)
            for field in fields
        }

        comparison = _compare_pfm_event(
            existing,
            candidate
        )

        if comparison == "CONFLICT":
            raise ValueError(
                "PFM event conflict at {}: existing ID {}".format(
                    candidate["analysis_datetime"],
                    event.id
                )
            )

        if comparison == "MATCH":
            matched_events.append(event)

    if len(matched_events) > 1:
        raise ValueError(
            "Multiple identical PFM events found; "
            "migration or manual review is required."
        )

    if matched_events:
        return matched_events[0]

    return None

def _optional_finite_number(value, field_name):
    if value is None or str(value).strip() == "":
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "Invalid PRM {}: {}".format(field_name, value)
        )

    if not math.isfinite(number):
        raise ValueError(
            "Non-finite PRM {}: {}".format(field_name, value)
        )

    return number


def _required_text(value, field_name):
    result = str(value or "").strip()

    if not result:
        raise ValueError(
            "Missing PRM {}".format(field_name)
        )

    return result


def sync_performance_history(db, analysis_record, analysis_state):
    """
    Synchronize PRM results for one formal analysis record.

    Validation runs before existing history rows are deleted.
    The caller owns the database transaction.
    """

    prm_rows = analysis_state.get("prm_rows")
    prm_results = analysis_state.get("prm_results")

    # Both keys absent: older non-PRM workflows.
    # Do not delete existing history accidentally.
    if prm_rows is None and prm_results is None:
        return 0

    if not isinstance(prm_rows, list) or not isinstance(prm_results, list):
        raise ValueError("Invalid PRM state structure")

    if len(prm_rows) != len(prm_results):
        raise ValueError("PRM rows/results count mismatch")

    if not prm_rows:
        # Explicit empty PRM state is permitted.
        # Existing history is preserved for safety.
        return 0

    analysis_id = _required_text(
        analysis_record.analysis_id,
        "analysis_id"
    )

    instrument_id = _required_text(
        analysis_record.instrument_id,
        "instrument_id"
    )

    method_code = _required_text(
        analysis_record.method_code,
        "method_code"
    )

    prepared = []

    for index, (raw_row, result) in enumerate(
        zip(prm_rows, prm_results),
        start=1
    ):
        if not isinstance(raw_row, dict) or not isinstance(result, dict):
            raise ValueError("Invalid PRM row/result")

        sample_id = _required_text(
            result.get("sample_id") or raw_row.get("sample_id"),
            "sample_id"
        )

        if sample_id.upper() not in {"PERFORMANCE", "PFM"}:
            raise ValueError("Invalid PRM sample_id")

        raw_sample_id = str(raw_row.get("sample_id") or "").strip()

        if raw_sample_id.upper() != sample_id.upper():
            raise ValueError("PRM sample_id mismatch")

        status = _required_text(
            result.get("status"),
            "status"
        ).upper()

        if status not in {"PASS", "FAIL", "UNDETERMINED"}:
            raise ValueError("Invalid PRM status")

        analysis_datetime = _parse_pfm_datetime(
            result.get("analysis_datetime")
            or raw_row.get("analysis_datetime")
        )

        measured_value = _optional_finite_number(
            result.get("signal"),
            "signal"
        )

        if measured_value is None:
            raise ValueError("PRM signal is missing")

        signal_field = _required_text(
            result.get("signal_field"),
            "signal_field"
        )

        control = result.get("control") or {}

        if not isinstance(control, dict):
            raise ValueError("Invalid PRM control data")

        # The control snapshot may be unavailable for UNDETERMINED.
        if status in {"PASS", "FAIL"} and not control:
            raise ValueError("PRM control snapshot is missing")

        monitor_item = str(
         control.get("monitor_item") or ""
        ).strip()

        performance_type = str(
            control.get("performance_type") or "CAL_HIGH_SIGNAL"
        ).strip()

        if not monitor_item:
           raise ValueError(
             "PFM monitor_item is missing"
        )

        if not performance_type:
           raise ValueError(
             "PFM performance_type is missing"
        )

        reference_value = _optional_finite_number(
            control.get("reference_value"),
            "reference_value"
        )

        lower_limit = _optional_finite_number(
            control.get("lower_limit"),
            "lower_limit"
        )

        upper_limit = _optional_finite_number(
            control.get("upper_limit"),
            "upper_limit"
        )

        if status in {"PASS", "FAIL"}:
            if not monitor_item:
                raise ValueError("Missing PRM monitor_item")

            if any(value is None for value in (
                reference_value, lower_limit, upper_limit
            )):
                raise ValueError("Incomplete PRM control limits")

        prepared.append({
            "sequence_no": index,
            "instrument_id": instrument_id,
            "method_code": method_code,
            "monitor_item": monitor_item,
            "performance_type": performance_type,
            "sample_id": sample_id,
            "analysis_datetime": analysis_datetime,
            "measured_value": measured_value,
            "signal_field": signal_field,
            "control_import_id": control.get("import_id"),
            "control_id": control.get("control_id"),
            "reference_value": reference_value,
            "lower_limit": lower_limit,
            "upper_limit": upper_limit,
            "unit": str(control.get("unit") or ""),
            "status": status,
            "message": str(result.get("message") or "")
        })

    # ========================================
    # PFM V2.1 Event + Analysis Link Sync
    # ========================================

    # 先完成事件查找與衝突驗證
    resolved = []

    for item in prepared:

        candidate = {
            key: value
            for key, value in item.items()
            if key not in {"sequence_no", "message"}
        }

        event = _find_existing_pfm_event(
            db,
            candidate
        )

        if event is None:

            event = PerformanceMeasurementHistory(
                **candidate,
                message=item["message"]
            )

            db.add(event)
            db.flush()

        resolved.append({
            "sequence_no": item["sequence_no"],
            "event": event
        })

    # 移除本分析紀錄的舊關聯
    old_links = (
        db.query(PerformanceAnalysisLink)
        .filter(
            PerformanceAnalysisLink.analysis_id
            == analysis_id
        )
        .all()
    )

    old_event_ids = {
        link.performance_id
        for link in old_links
    }

    for link in old_links:
        db.delete(link)

    db.flush()

    # 建立新的分析關聯
    for item in resolved:

        db.add(
            PerformanceAnalysisLink(
                performance_id=item["event"].id,
                analysis_id=analysis_id,
                prm_sequence_no=item["sequence_no"]
            )
        )

    db.flush()

    # 清理不再被任何分析紀錄使用的舊事件
    for event_id in old_event_ids:

        remaining = (
            db.query(PerformanceAnalysisLink)
            .filter(
                PerformanceAnalysisLink.performance_id
                == event_id
            )
            .count()
        )

        if remaining == 0:

            old_event = db.get(
                PerformanceMeasurementHistory,
                event_id
            )

            if old_event is not None:
                db.delete(old_event)

    return len(resolved)

def delete_performance_links_for_analysis(db, analysis_id):
    """
    PFM V2.1:
    Remove an analysis record's PFM links.

    Delete a PFM event only when no analysis
    record references it.

    The caller owns commit and rollback.
    """

    from models import PerformanceAnalysisLink

    analysis_id = _required_text(
        analysis_id,
        "analysis_id"
    )

    links = (
        db.query(PerformanceAnalysisLink)
        .filter(
            PerformanceAnalysisLink.analysis_id
            == analysis_id
        )
        .all()
    )

    performance_ids = {
        link.performance_id
        for link in links
    }

    for link in links:
        db.delete(link)

    db.flush()

    deleted_events = 0

    for performance_id in performance_ids:

        remaining = (
            db.query(PerformanceAnalysisLink)
            .filter(
                PerformanceAnalysisLink.performance_id
                == performance_id
            )
            .count()
        )

        if remaining == 0:

            event = db.get(
                PerformanceMeasurementHistory,
                performance_id
            )

            if event is not None:
                db.delete(event)
                deleted_events += 1

    return {
        "deleted_links": len(links),
        "deleted_events": deleted_events
    }
