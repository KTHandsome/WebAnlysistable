# -*- coding: utf-8 -*-
"""Performance History Flask routes."""

from flask import Blueprint, request, render_template

from database import SessionLocal
from services.performance_history_query_service import (
    query_performance_history,
)


performance_history_bp = Blueprint(
    "performance_history_bp",
    __name__
)


def register_performance_history_route(login_required):

    @performance_history_bp.route(
        "/performance-history",
        methods=["GET"]
    )
    @login_required
    def performance_history():

        filter_names = [
            "instrument_id",
            "category",
            "monitor_item",
            "status",
            "analysis_date_start",
            "analysis_date_end"
        ]

        filters = {
            name: request.args.get(name, "").strip()
            for name in filter_names
        }

        searched = any(
            name in request.args
            for name in filter_names
        )

        rows = []
        error_message = ""

        if searched:
            db = SessionLocal()

            try:
                rows = query_performance_history(
                    db=db,
                    **filters
                )
            except ValueError as exc:
                error_message = str(exc)
            finally:
                db.close()

        return render_template(
            "performance_history_query.html",
            active_page="performance_history",
            filters=filters,
            searched=searched,
            rows=rows,
            error_message=error_message
        )