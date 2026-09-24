from datetime import date

from database import Base, SessionLocal, engine
from models import AnalysisRecord


Base.metadata.create_all(bind=engine)


db = SessionLocal()

try:

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
        analyst_employee_id="S097-06",
        analyst_name="測試人員",

        source_type="IMPORT",
        source_filename="PE上機PDF-As-0908.pdf"
    )

    db.add(record)
    db.commit()

    db.refresh(record)

    print(
        "建立成功：",
        record.id,
        record.analysis_id
    )

    saved_record = (
        db.query(
            AnalysisRecord
        )
        .filter(
            AnalysisRecord.analysis_id
            == record.analysis_id
        )
        .first()
    )

    if saved_record is None:
        raise RuntimeError(
            "查不到剛才建立的 AnalysisRecord。"
        )

    print(
        "查詢成功：",
        saved_record.exam_no,
        saved_record.exam_name,
        saved_record.method_code,
        saved_record.status,
        saved_record.analyst_name
    )

finally:

    db.close()
    