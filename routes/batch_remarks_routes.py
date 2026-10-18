from flask import (
    Blueprint,
    redirect,
    request,
    session,
    url_for,
)

from auth_session import login_required

from analysis.analysis_route_helpers import (
    get_analysis_page_endpoint,
    get_analysis_state_key,
)

from analysis.analysis_state import (
    load_analysis_state,
    save_analysis_state,
)


batch_remarks_bp = Blueprint(
    "batch_remarks_bp",
    __name__,
)


@batch_remarks_bp.route(
    "/analysis/update-batch-remarks",
    methods=["POST"]
)
@login_required
def update_batch_remarks():

    form_data = session.get(
        "basic_info_form"
    ) or {}

    method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not method_code:

        return (
            "尚未找到目前分析方法。",
            400
        )

    analysis_state_key = (
        get_analysis_state_key(
            method_code
        )
    )

    analysis_state = (
        load_analysis_state(
            analysis_state_key
        )
        or {}
    )

    included_batches = (
        analysis_state.get(
            "included_batches",
            []
        )
    )

    qaqc_results = (
        analysis_state.get(
            "qaqc_results",
            []
        )
    )

    if not included_batches:

        return (
            "尚未找到分析批次資料。",
            400
        )

    remark_map = {}

    for batch in included_batches:

        batch_no = batch.get(
            "batch_no"
        )

        if batch_no is None:
            continue

        remark = (
            request.form.get(
                "batch_remark_"
                + str(batch_no),
                ""
            )
            .strip()
        )

        batch[
            "batch_remark"
        ] = remark

        remark_map[
            str(batch_no)
        ] = remark

    # QA/QC 顯示資料也同步帶入
    for batch in qaqc_results:

        batch_no = batch.get(
            "batch_no"
        )

        if batch_no is None:
            continue

        batch[
            "batch_remark"
        ] = remark_map.get(
            str(batch_no),
            ""
        )

    analysis_state[
        "included_batches"
    ] = included_batches

    analysis_state[
        "qaqc_results"
    ] = qaqc_results

    save_analysis_state(
        analysis_state_key,
        analysis_state
    )

    analysis_endpoint = (
       get_analysis_page_endpoint(
        method_code
       )
    )

    return redirect(
      url_for(
          analysis_endpoint,
          saved="1"
      )
    )
