from database import Base, SessionLocal, engine

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary
)


Base.metadata.create_all(
    bind=engine
)


db = SessionLocal()

try:

    summary_count = (
        db.query(
            AnalysisCalibrationSummary
        )
        .count()
    )

    point_count = (
        db.query(
            AnalysisCalibrationPoint
        )
        .count()
    )

    print(
        "AnalysisCalibrationSummary 筆數：",
        summary_count
    )

    print(
        "AnalysisCalibrationPoint 筆數：",
        point_count
    )

finally:

    db.close()