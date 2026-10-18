from flask import (
    Blueprint,
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

                    group_id = str(
                      user.get(
                         "group_id",
                         ""
                      )
                      or ""
                    ).strip().upper()

                    permissions = []

                    if group_id in {
                       "07",
                       "ADMIN"
                    }:

                        permissions = [
                        "REVIEW_ANALYSIS",
                        "DELETE_ANALYSIS",
                        "VIEW_ANALYSIS_DELETE_HISTORY"
                    ]
                        
                    group_id = str(
                           user.get(
                           "group_id",
                               ""
                          )
                      or ""
                    ).strip().upper()

                    permissions = []

                    if group_id in {
                         "07",
                          "ADMIN"
                        }:
                      permissions = [
                        "REVIEW_ANALYSIS",
                        "DELETE_ANALYSIS",
                        "VIEW_ANALYSIS_DELETE_HISTORY",
                        "MANAGE_PERFORMANCE_CONTROL"
                    ]     
                    
                    set_current_user(
                        user_id=user.get(
                            "user_id",
                            ""
                        ),
                        employee_id=user.get(
                            "employee_id",
                            ""
                        ),
                        employee_name=user.get(
                            "employee_name",
                            ""
                        ),                        
                        group_id=group_id,
                        dept_no=user.get(
                            "dept_no",
                            ""
                        ),
                        dept_name=user.get(
                            "dept_name",
                            ""
                        ),
                        permissions=permissions
                    )

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
        DATABASE_TYPE == "sqlite"
    )
)

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

            error_message = (
                "目前非公司環境，"
                "尚未啟用 LIMS 帳號驗證。"
            )

    return render_template(
        "login.html",
        error_message=error_message
    )


@auth_bp.route("/dev-login",methods=["POST"])
def dev_login():

    if DATABASE_TYPE != "sqlite":
        return (
            "正式環境不允許使用測試登入。",
            403
        )

    set_current_user(
        user_id="DEV",
        employee_id="S097-06",
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

