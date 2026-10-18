from flask import (
    Blueprint,
    redirect,
    url_for,
)

from auth_session import get_current_user


home_bp = Blueprint(
    "home_bp",
    __name__,
)


@home_bp.route("/")
def home():

    if get_current_user() is None:
        return redirect(
            url_for("login")
        )

    return redirect(
        url_for("basic_info")
    )

