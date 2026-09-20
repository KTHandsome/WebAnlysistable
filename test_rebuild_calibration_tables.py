from database import Base, engine

from models import (
    AnalysisCalibrationPoint,
    AnalysisCalibrationSummary
)


AnalysisCalibrationPoint.__table__.drop(
    bind=engine,
    checkfirst=True
)

AnalysisCalibrationSummary.__table__.drop(
    bind=engine,
    checkfirst=True
)


Base.metadata.create_all(
    bind=engine
)


print(
    "檢量線 Snapshot 資料表重建完成。"
)