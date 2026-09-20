from database import (
    Base,
    SessionLocal,
    engine
)

from models import (
    AnalysisQaqcResult,
    AnalysisRecord
)


Base.metadata.create_all(
    bind=engine
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
            "找不到 analysis_record，"
            "請先建立一筆正式分析紀錄。"
        )

    else:

        print(
            "測試 Analysis ID：",
            record.analysis_id
        )

        test_rows = [
            AnalysisQaqcResult(
                analysis_id=record.analysis_id,
                display_order=1,
                qaqc_type="ICV",
                sample_id="ICV-1",
                result_name="ICV 回收率",
                result_value="101.2 %",
                criteria_text="80.0 ～ 120.0 %",
                is_pass=True,
                remark=""
            ),

            AnalysisQaqcResult(
                analysis_id=record.analysis_id,
                display_order=2,
                qaqc_type="CCV",
                sample_id="CCV-1",
                result_name="CCV 相對誤差",
                result_value="2.4 %",
                criteria_text="≤ 20.0 %",
                is_pass=True,
                remark=""
            ),

            AnalysisQaqcResult(
                analysis_id=record.analysis_id,
                display_order=3,
                qaqc_type="BK",
                sample_id="BK-1",
                result_name="空白樣品",
                result_value="< 2MDL",
                criteria_text="< 2MDL",
                is_pass=True,
                remark=""
            )
        ]

        db.add_all(
            test_rows
        )

        db.commit()

        rows = (
            db.query(
                AnalysisQaqcResult
            )
            .filter(
                AnalysisQaqcResult.analysis_id
                == record.analysis_id
            )
            .order_by(
                AnalysisQaqcResult.display_order,
                AnalysisQaqcResult.id
            )
            .all()
        )

        print(
            "QA/QC 筆數：",
            len(rows)
        )

        for row in rows:

            print(
                row.id,
                row.qaqc_type,
                row.sample_id,
                row.result_name,
                row.result_value,
                row.criteria_text,
                row.is_pass
            )

finally:

    db.close()