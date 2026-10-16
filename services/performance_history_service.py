# -*- coding: utf-8 -*-
"""
Phyon PRM performance measurement history.

This service uses the caller's SQLAlchemy Session.
It must not commit, rollback, or close that Session.
"""

from datetime import date, datetime
import math

from models import PerformanceMeasurementHistory


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

    category = _required_text(
        analysis_record.category,
        "category"
    ).upper()

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

        analysis_date = _parse_prm_date(
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

        expected_monitor_item = (
            "TOC/{}".format(category)
            if category in {"D", "W", "G"}
            else ""
        )

        monitor_item = str(
            control.get("monitor_item") or expected_monitor_item
        ).strip()

        performance_type = str(
            control.get("performance_type") or "CAL_HIGH_SIGNAL"
        ).strip()

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

        prepared.append(
            PerformanceMeasurementHistory(
                analysis_id=analysis_id,
                prm_sequence_no=index,
                instrument_id=instrument_id,
                method_code=method_code,
                category=category,
                monitor_item=monitor_item,
                performance_type=performance_type,
                sample_id=sample_id,
                analysis_date=analysis_date,
                measured_value=measured_value,
                signal_field=signal_field,
                control_import_id=control.get("import_id"),
                control_id=control.get("control_id"),
                reference_value=reference_value,
                lower_limit=lower_limit,
                upper_limit=upper_limit,
                unit=str(control.get("unit") or ""),
                status=status,
                message=str(result.get("message") or "")
            )
        )

    # Replace details within the caller's transaction.
    db.query(PerformanceMeasurementHistory).filter(
        PerformanceMeasurementHistory.analysis_id == analysis_id
    ).delete(synchronize_session=False)

    db.add_all(prepared)

    return len(prepared)
