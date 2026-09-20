from datetime import date

from database import (
    Base,
    SessionLocal,
    engine
)

from models import (
    AnalysisRecord,
    AnalysisSample
)


Base.metadata.create_all(
    bind=engine
)


db = SessionLocal()

try:

    # ========================================
    # 1. 建立一筆正式分析主檔
    # ========================================

    record = AnalysisRecord(
        status="DRAFT",

        ctrl_year="2026",
        category="W",

        exam_no="W-43401",
        exam_name="砷",

        method_code="W434",
        method_name="NIEA W434.54B",

        instrument_id="TEST-INSTRUMENT",
        instrument_model="PinAAcle 900F",

        form_date=date(
            2026,
            9,
            20
        ),

        analysis_start_date=date(
            2026,
            9,
            8
        ),

        analysis_end_date=date(
            2026,
            9,
            8
        ),

        wavelength=193.70,

        analyst_user_id="DEV",
        analyst_employee_id="A11503-03",
        analyst_name="測試人員",

        source_type="IMPORT",
        source_filename="PE上機PDF-As-0908.pdf"
    )

    db.add(record)
    db.commit()

    db.refresh(record)

    print(
        "主檔建立成功：",
        record.id,
        record.analysis_id
    )

    # ========================================
    # 2. 建立分析明細
    # ========================================

    samples = [
        AnalysisSample(
            analysis_id=record.analysis_id,
            sequence_no=1,
            display_order=1,
            sample_id="ICBK",
            role="ICBK",
            signal=0.001,
            sample_volume=25,
            final_volume=50,
            dilution_factor=1,
            spike_concentration=None,
            calculated_concentration=0.0001,
            remark=""
        ),

        AnalysisSample(
            analysis_id=record.analysis_id,
            sequence_no=2,
            display_order=2,
            sample_id="ICV",
            role="ICV",
            signal=0.105,
            sample_volume=25,
            final_volume=50,
            dilution_factor=1,
            spike_concentration=0.01,
            calculated_concentration=0.0102,
            remark=""
        ),

        AnalysisSample(
            analysis_id=record.analysis_id,
            sequence_no=3,
            display_order=3,
            sample_id="W1150908-001",
            role="SAMPLE",
            signal=0.055,
            sample_volume=25,
            final_volume=50,
            dilution_factor=1,
            spike_concentration=None,
            calculated_concentration=0.0051,
            remark="正式樣品"
        )
    ]

    db.add_all(
        samples
    )

    db.commit()

    print(
        "明細建立成功：",
        len(samples),
        "筆"
    )

    # ========================================
    # 3. 用 analysis_id 查回全部明細
    # ========================================

    saved_samples = (
        db.query(
            AnalysisSample
        )
        .filter(
            AnalysisSample.analysis_id
            == record.analysis_id
        )
        .order_by(
            AnalysisSample.display_order
        )
        .all()
    )

    print(
        "查詢明細：",
        len(saved_samples),
        "筆"
    )

    for sample in saved_samples:

        print(
            sample.display_order,
            sample.sample_id,
            sample.role,
            sample.calculated_concentration
        )

    # ========================================
    # 4. 基本驗證
    # ========================================

    if len(saved_samples) != 3:

        raise RuntimeError(
            "AnalysisSample 明細數量不正確。"
        )

    if (
        saved_samples[0].role
        != "ICBK"
    ):

        raise RuntimeError(
            "第一筆角色不是 ICBK。"
        )

    if (
        saved_samples[2].sample_id
        != "W1150908-001"
    ):

        raise RuntimeError(
            "正式樣品編號查詢結果不正確。"
        )

    print(
        "AnalysisSample 關聯測試成功。"
    )

finally:

    db.close()
    