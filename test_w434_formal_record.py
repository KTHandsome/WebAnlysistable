from database import SessionLocal
from models import (
    AnalysisRecord,
    AnalysisSample
)


db = SessionLocal()

try:

    record = (
        db.query(
            AnalysisRecord
        )
        .order_by(
            AnalysisRecord.id.desc()
        )
        .first()
    )

    if record is None:

        print(
            "目前沒有 AnalysisRecord。"
        )

    else:

        sample_count = (
            db.query(
                AnalysisSample
            )
            .filter(
                AnalysisSample.analysis_id
                == record.analysis_id
            )
            .count()
        )

        print()
        print(
            "===== 最新正式分析紀錄 ====="
        )

        print(
            "ID：",
            record.id
        )

        print(
            "Analysis ID：",
            record.analysis_id
        )

        print(
            "狀態：",
            record.status
        )

        print(
            "測項：",
            record.exam_name
        )

        print(
            "方法：",
            record.method_code
        )

        print(
            "分析人員：",
            record.analyst_name
        )

        print(
            "來源檔案：",
            record.source_filename
        )

        print(
            "明細筆數：",
            sample_count
        )

finally:

    db.close()