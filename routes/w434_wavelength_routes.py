from flask import (
    Blueprint,
    request,
    session,
)

from analysis.analysis_route_helpers import (
    get_analysis_state_key,
)

from analysis.analysis_state import (
    load_analysis_state,
    save_analysis_state,
)


from auth_session import login_required


w434_wavelength_bp = Blueprint(
    "w434_wavelength_bp",
    __name__,
)


@w434_wavelength_bp.route(
    "/analysis/w43401/confirm-wavelength",
    methods=["POST"]
)

@login_required
def confirm_w434_wavelength():

    choice = request.form.get(
        "choice",
        ""
    ).strip().lower()

    form_data = session.get(
        "basic_info_form"
    ) or {}

    current_method_code = str(
        form_data.get(
            "method_code",
            ""
        )
        or ""
    ).strip().upper()

    if not current_method_code:
        current_method_code = "W434"

    analysis_state_key = (
        get_analysis_state_key(
            current_method_code
        )
    )

    analysis_state = load_analysis_state(
        analysis_state_key
    )

    if not analysis_state:

        return (
            "尚未找到 "
            + current_method_code
            + " 分析資料。",
            400
        )

    if not form_data:

        return (
            "尚未找到基本資料。",
            400
        )

    if not form_data:

        return (
            "尚未找到基本資料。",
            400
        )

    instrument_wavelength = (
        analysis_state.get(
            "instrument_wavelength"
        )
    )

    basic_wavelength_text = (
        form_data.get(
            "wavelength",
            ""
        )
        .strip()
    )

    if choice == "instrument":

        if instrument_wavelength is None:

            return (
                "儀器原始資料沒有有效波長。",
                400
            )

        confirmed_wavelength = float(
            instrument_wavelength
        )

        analysis_state[
            "confirmed_wavelength"
        ] = confirmed_wavelength

        analysis_state[
            "wavelength_warning"
        ] = None

        analysis_state[
            "wavelength_source"
        ] = "INSTRUMENT"

        # 使用者已明確確認採用儀器值，
        # 同步回 Basic Info session
        form_data["wavelength"] = format(
            confirmed_wavelength,
            ".2f"
        )

        session[
            "basic_info_form"
        ] = form_data

    elif choice == "basic":

        if not basic_wavelength_text:

            return (
                "基本資料沒有可保留的波長。",
                400
            )

        try:

            confirmed_wavelength = float(
                basic_wavelength_text
            )

        except ValueError:

            return (
                "基本資料波長格式不正確。",
                400
            )

        analysis_state[
            "confirmed_wavelength"
        ] = confirmed_wavelength

        analysis_state[
            "wavelength_warning"
        ] = None

        analysis_state[
            "wavelength_source"
        ] = "BASIC"

    else:

        return (
            "未知的波長確認方式。",
            400
        )

    save_analysis_state(
        analysis_state_key,
        analysis_state
    )

    return "", 204
