from database import SessionLocal

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary,
    AnalysisRecord
)


db = SessionLocal()

try:

    record = (
        db.query(AnalysisRecord)
        .order_by(
            AnalysisRecord.id.desc()
        )
        .first()
    )

    if record is None:

        print("目前沒有正式分析紀錄。")
        raise SystemExit()


    print(
        "AnalysisRecord ID：",
        record.id
    )

    print(
        "analysis_id：",
        record.analysis_id
    )


    summary = (
        db.query(
            AnalysisCalibrationSummary
        )
        .filter(
            AnalysisCalibrationSummary.analysis_id
            == record.analysis_id
        )
        .first()
    )


    points = (
        db.query(
            AnalysisCalibrationPoint
        )
        .filter(
            AnalysisCalibrationPoint.analysis_id
            == record.analysis_id
        )
        .order_by(
            AnalysisCalibrationPoint.display_order
        )
        .all()
    )


    print()

    if summary is None:

        print(
            "AnalysisCalibrationSummary：查無資料"
        )

    else:

        print(
            "AnalysisCalibrationSummary：1 筆"
        )

        print(
            "Slope：",
            summary.slope
        )

        print(
            "Intercept：",
            summary.intercept
        )

        print(
            "Correlation r：",
            summary.correlation_r
        )

        print(
            "Pass：",
            summary.is_pass
        )


    print()

    print(
        "AnalysisCalibrationPoint 筆數：",
        len(points)
    )


    for point in points:

        print(
            point.display_order,
            "|",
            point.standard_id,
            "| 濃度 =",
            point.concentration,
            "| 訊號 =",
            point.signal,
            "| 回算濃度 =",
            point.back_calculated_concentration,
            "| 偏差 =",
            point.error_percent
        )

finally:

    db.close()
    