import os
import secrets

from flask import (
    Blueprint,
    abort,
    make_response,
    render_template_string,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from auth_session import (
    set_current_user,
)

from database import DATABASE_TYPE

from services.lims_auth_service import (
    validate_lims_user,
)


auth_bp = Blueprint(
    "auth_bp",
    __name__,
)


def is_dev_login_allowed():

    enabled = (
        os.getenv(
            "PHYON_ENABLE_DEV_LOGIN",
            ""
        ).strip() == "1"
    )

    is_sqlite = DATABASE_TYPE == "sqlite"

    is_local = request.remote_addr in {
        "127.0.0.1",
        "::1",
    }

    return enabled and is_sqlite and is_local


def start_lims_web_session(user):
    group_id = str(user.get("group_id") or "").strip().upper()
    permissions = []
    if group_id in {"07", "ADMIN"}:
        permissions = [
            "REVIEW_ANALYSIS",
            "DELETE_ANALYSIS",
            "VIEW_ANALYSIS_DELETE_HISTORY",
            "MANAGE_PERFORMANCE_CONTROL",
        ]
    set_current_user(
        user_id=user.get("user_id", ""),
        employee_id=user.get("employee_id", ""),
        employee_name=user.get("employee_name", ""),
        group_id=group_id,
        dept_no=user.get("dept_no", ""),
        dept_name=user.get("dept_name", ""),
        permissions=permissions,
    )


@auth_bp.route("/vb-login", methods=["GET", "POST"])
def vb_login():
    from routes.internal_messages import web_ticket_identity

    if not request.is_secure:
        abort(403)

    if request.method == "GET":
        nonce = secrets.token_urlsafe(24)
        session["vb_login_nonce"] = nonce
        html = """<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>檢驗紀錄登入</title><h1>檢驗紀錄登入</h1>
<form method="post"><input type="hidden" name="nonce" value="{{ nonce }}">
<input type="hidden" name="ticket" id="ticket">
<input type="hidden" name="step" value="preview"><noscript>請回 VB 重新開啟或手動登入。</noscript></form>
<script nonce="{{ nonce }}">
const ticket = location.hash.slice(1);
history.replaceState(null, '', location.pathname);
if (/^[A-Za-z0-9_-]{43}$/.test(ticket)) {
    document.getElementById('ticket').value = ticket;
    document.forms[0].submit();
} else {
    location.replace({{ login_url|tojson }});
}
</script></html>"""
        response = make_response(render_template_string(html, nonce=nonce, login_url=url_for("login")))
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; form-action 'self'; frame-ancestors 'none'; script-src 'nonce-" + nonce + "'"
        )
    else:
        nonce = request.form.get("nonce", "")
        expected = session.get("vb_login_nonce", "")
        ticket = request.form.get("ticket", "")
        if not nonce or not expected or not nonce.isascii() or not secrets.compare_digest(nonce, expected):
            return redirect(url_for("login"), code=303)
        if request.form.get("step") == "confirm":
            session.pop("vb_login_nonce", None)
            identity = web_ticket_identity(ticket, consume=True)
            if identity is None:
                return redirect(url_for("login"), code=303)
            session.clear()
            start_lims_web_session(identity)
            response = redirect(url_for("home"), code=303)
        else:
            identity = web_ticket_identity(ticket)
            if identity is None:
                return redirect(url_for("login"), code=303)
            html = """<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>檢驗紀錄登入</title><h1>檢驗紀錄登入</h1>
<p>以 {{ user.employee_name }}（{{ user.user_id }}）登入 Phyon Web。</p>
<form method="post"><input type="hidden" name="nonce" value="{{ nonce }}">
<input type="hidden" name="ticket" value="{{ ticket }}">
<button name="step" value="confirm">繼續登入</button></form></html>"""
            response = make_response(render_template_string(html, user=identity, nonce=nonce, ticket=ticket))
            response.headers["Content-Security-Policy"] = "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@auth_bp.route("/login",methods=["GET", "POST"])
def login():

    error_message = None

    if request.method == "POST":

        user_id = request.form.get(
            "user_id",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not user_id:

            error_message = (
                "請輸入帳號。"
            )

        elif not password:

            error_message = (
                "請輸入密碼。"
            )

        else:

            try:

                user = validate_lims_user(
                    user_id,
                    password
                )

                if user is None:

                    error_message = (
                        "帳號或密碼錯誤。"
                    )

                else:

                        
                    start_lims_web_session(user)

                    return redirect(
                        url_for(
                            "home"
                        )
                    )

            except Exception as ex:

                print(
                    "LIMS login error:",
                    ex
                )

                error_message = (
                    "無法連線至 LIMS，"
                    "請稍後再試。"
                )

    return render_template(
    "login.html",
    error_message=error_message,
    show_dev_login=(
        is_dev_login_allowed()
    )
)



@auth_bp.route("/dev-login",methods=["POST"])
def dev_login():

    if not is_dev_login_allowed():
        return (
            "正式環境不允許使用測試登入。",
            403
        )

    set_current_user(
        user_id="DEV",
        employee_id="A100-33",
        employee_name="測試人員",
        group_id="04",
        group_name="分析部",
        dept_no="C",
        dept_name="分析課",
        job_title="檢驗員",
        permissions=[
            "REVIEW_ANALYSIS",
            "DELETE_ANALYSIS",
            "VIEW_ANALYSIS_DELETE_HISTORY",
            "MANAGE_PERFORMANCE_CONTROL"
        ]      
    )

    return redirect(
        url_for(
            "home"
        )
    )


@auth_bp.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )

