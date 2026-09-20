from database import SessionLocal

from models import (
    AnalysisQaqcResult,
    AnalysisRecord,
    AnalysisSample
)


db = SessionLocal()

try:

    before_qaqc = (
        db.query(
            AnalysisQaqcResult
        )
        .count()
    )

    before_samples = (
        db.query(
            AnalysisSample
        )
        .count()
    )

    before_records = (
        db.query(
            AnalysisRecord
        )
        .count()
    )

    print(
        "清除前："
    )

    print(
        "AnalysisQaqcResult =",
        before_qaqc
    )

    print(
        "AnalysisSample =",
        before_samples
    )

    print(
        "AnalysisRecord =",
        before_records
    )


    # ========================================
    # 必須先刪子表，再刪主表
    # ========================================

    deleted_qaqc = (
        db.query(
            AnalysisQaqcResult
        )
        .delete(
            synchronize_session=False
        )
    )

    deleted_samples = (
        db.query(
            AnalysisSample
        )
        .delete(
            synchronize_session=False
        )
    )

    deleted_records = (
        db.query(
            AnalysisRecord
        )
        .delete(
            synchronize_session=False
        )
    )

    db.commit()


    after_qaqc = (
        db.query(
            AnalysisQaqcResult
        )
        .count()
    )

    after_samples = (
        db.query(
            AnalysisSample
        )
        .count()
    )

    after_records = (
        db.query(
            AnalysisRecord
        )
        .count()
    )

    print()

    print(
        "本次刪除："
    )

    print(
        "AnalysisQaqcResult =",
        deleted_qaqc
    )

    print(
        "AnalysisSample =",
        deleted_samples
    )

    print(
        "AnalysisRecord =",
        deleted_records
    )

    print()

    print(
        "清除後："
    )

    print(
        "AnalysisQaqcResult =",
        after_qaqc
    )

    print(
        "AnalysisSample =",
        after_samples
    )

    print(
        "AnalysisRecord =",
        after_records
    )

finally:

    db.close()