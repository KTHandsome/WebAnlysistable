# -*- coding: utf-8 -*-
"""Performance History Flask routes."""
from flask import (
    Blueprint,
    request,
    render_template,
    jsonify,
    current_app,
)

from database import SessionLocal

from services.performance_history_query_service import (
    query_performance_history,
)

from services.performance_trend_service import (
    get_performance_trend,
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

    @performance_history_bp.route(
        "/analysis/performance-trend",
        methods=["GET"]
    )
    @login_required
    def analysis_performance_trend():

        instrument_id = str(
            request.args.get("instrument_id", "")
        ).strip()

        monitor_item = str(
            request.args.get("monitor_item", "")
        ).strip()

        performance_type = str(
            request.args.get("performance_type", "")
        ).strip()

        if not all([
            instrument_id,
            monitor_item,
            performance_type
        ]):
            return jsonify({
                "success": False,
                "message": "缺少儀器或性能查核項目。"
            }), 400

        db = SessionLocal()

        try:
            result = get_performance_trend(
                db=db,
                instrument_id=instrument_id,
                monitor_item=monitor_item,
                performance_type=performance_type,
                limit=30
            )

            return jsonify({
                "success": True,
                "data": result
            })

        except ValueError as exc:
            return jsonify({
                "success": False,
                "message": str(exc)
            }), 400

        except Exception:
            current_app.logger.exception(
                "PRM performance trend query failed"
            )

            return jsonify({
                "success": False,
                "message": "查詢 PRM 歷程失敗。"
            }), 500

        finally:
            db.close()
        