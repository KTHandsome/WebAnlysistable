from flask import Blueprint, render_template

from database import SessionLocal

from auth_session import (
    login_required,
    can_view_analysis_delete_history,
)

from models import (
    AnalysisDeleteHistory,
    AnalysisRecord,
    AnalysisSample,
    AnalysisQaqcResult,
    AnalysisCalibrationSummary,
    AnalysisCalibrationPoint,
    AnalysisReviewHistory,
)


analysis_record_bp = Blueprint(
    "analysis_record_bp",
    __name__,
)


@analysis_record_bp.route(
    "/analysis-delete-history",
    methods=["GET"],
)
@login_required
def analysis_delete_history():

    if not can_view_analysis_delete_history():
        return (
            "您沒有查看分析刪除紀錄的權限。",
            403,
        )

    db = SessionLocal()

    try:
        records = (
            db.query(AnalysisDeleteHistory)
            .order_by(
                AnalysisDeleteHistory.deleted_at.desc(),
                AnalysisDeleteHistory.id.desc(),
            )
            .all()
        )

        return render_template(
            "analysis_delete_history.html",
            records=records,
            active_page="analysis_records",
        )

    finally:
        db.close()

@analysis_record_bp.route(
    "/analysis-records/<analysis_id>",
    methods=["GET"],
)
@login_required
def analysis_record_detail(analysis_id):

    db = SessionLocal()

    try:
        record = (
            db.query(AnalysisRecord)
            .filter(
                AnalysisRecord.analysis_id == analysis_id
            )
            .first()
        )

        if record is None:
            return "查無此分析紀錄。", 404

        samples = (
            db.query(AnalysisSample)
            .filter(
                AnalysisSample.analysis_id == analysis_id
            )
            .order_by(
                AnalysisSample.display_order,
                AnalysisSample.id,
            )
            .all()
        )

        qaqc_results = (
            db.query(AnalysisQaqcResult)
            .filter(
                AnalysisQaqcResult.analysis_id == analysis_id
            )
            .order_by(
                AnalysisQaqcResult.display_order,
                AnalysisQaqcResult.id,
            )
            .all()
        )

        calibration_summary = (
            db.query(AnalysisCalibrationSummary)
            .filter(
                AnalysisCalibrationSummary.analysis_id == analysis_id
            )
            .first()
        )

        calibration_points = (
            db.query(AnalysisCalibrationPoint)
            .filter(
                AnalysisCalibrationPoint.analysis_id == analysis_id
            )
            .order_by(
                AnalysisCalibrationPoint.display_order,
                AnalysisCalibrationPoint.id,
            )
            .all()
        )

        review_history = (
            db.query(AnalysisReviewHistory)
            .filter(
                AnalysisReviewHistory.analysis_id == analysis_id
            )
            .order_by(
                AnalysisReviewHistory.created_at,
                AnalysisReviewHistory.id,
            )
            .all()
        )

        return render_template(
            "analysis_record_detail.html",
            record=record,
            calibration_summary=calibration_summary,
            calibration_points=calibration_points,
            samples=samples,
            qaqc_results=qaqc_results,
            review_history=review_history,
            active_page="analysis_records",
        )

    finally:
        db.close()