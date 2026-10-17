from flask import Blueprint, render_template

from database import SessionLocal

from auth_session import (
    login_required,
    can_view_analysis_delete_history,
)

from models import AnalysisDeleteHistory


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