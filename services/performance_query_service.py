
"""
Phyon Performance ACTIVE control query service.

Read-only service for analysis modules.
Does not modify release history or control records.
"""

from datetime import date, datetime

from sqlalchemy import select

from models import (
    PerformanceImportHistory,
    InstrumentPerformanceControl,
)


class PerformanceControlQueryError(Exception):
    """Performance control cannot be uniquely resolved."""


def find_active_performance_control(
    session_factory,
    instrument_id,
    monitor_item,
    performance_type,
    analysis_date,
):
    """
    Find exactly one enabled Performance control
    belonging to the single ACTIVE release.

    Returns a dictionary suitable for analysis state.

    No database writes or commits are performed.
    """

    instrument_id = str(instrument_id or "").strip()
    monitor_item = str(monitor_item or "").strip().upper()
    performance_type = str(
        performance_type or ""
    ).strip().upper()

    if not instrument_id:
        raise ValueError("缺少儀器編號 instrument_id。")

    if not monitor_item:
        raise ValueError("缺少管制測項 monitor_item。")

    if not performance_type:
        raise ValueError("缺少管制類型 performance_type。")

    if isinstance(analysis_date, datetime):
        analysis_date = analysis_date.date()

    if not isinstance(analysis_date, date):
        raise ValueError(
            "analysis_date 必須是 Python date 或 datetime。"
        )

    with session_factory() as db:

        active_batches = db.scalars(
            select(PerformanceImportHistory).where(
                PerformanceImportHistory.status == "ACTIVE"
            )
        ).all()

        if len(active_batches) != 1:
            raise PerformanceControlQueryError(
                "Performance 必須恰有一個 ACTIVE 發布批次；"
                "目前找到 {} 個。".format(len(active_batches))
            )

        active_batch = active_batches[0]

        controls = db.scalars(
            select(InstrumentPerformanceControl).where(
                InstrumentPerformanceControl.import_id
                == active_batch.import_id,

                InstrumentPerformanceControl.instrument_id
                == instrument_id,

                InstrumentPerformanceControl.monitor_item
                == monitor_item,

                InstrumentPerformanceControl.performance_type
                == performance_type,

                InstrumentPerformanceControl.enabled.is_(True),

                InstrumentPerformanceControl.year
                == analysis_date.year,

                InstrumentPerformanceControl.effective_from
                <= analysis_date,

                InstrumentPerformanceControl.effective_to
                >= analysis_date,
            )
        ).all()

        if not controls:
            raise PerformanceControlQueryError(
                "找不到有效的 Performance 管制標準："
                "儀器={}，測項={}，類型={}，日期={}。".format(
                    instrument_id,
                    monitor_item,
                    performance_type,
                    analysis_date.isoformat(),
                )
            )

        if len(controls) != 1:
            raise PerformanceControlQueryError(
                "Performance 管制標準配對到 {} 筆，"
                "禁止自動選擇。".format(len(controls))
            )

        control = controls[0]

        return {
            "import_id": active_batch.import_id,
            "control_id": control.control_id,
            "control_version": control.control_version,
            "instrument_id": control.instrument_id,
            "instrument_model": control.instrument_model,
            "year": control.year,
            "effective_from": control.effective_from.isoformat(),
            "effective_to": control.effective_to.isoformat(),
            "performance_type": control.performance_type,
            "monitor_item": control.monitor_item,
            "reference_value": control.reference_value,
            "lower_limit": control.lower_limit,
            "upper_limit": control.upper_limit,
            "unit": control.unit,
            "sample_labels": control.sample_labels,
            "sop_reference": control.sop_reference,
        }