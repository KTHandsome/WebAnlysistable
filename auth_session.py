from functools import wraps

from flask import (
    redirect,
    session,
    url_for
)


SESSION_USER_KEY = "user"


def get_current_user():

    user = session.get(
        SESSION_USER_KEY
    )

    if not isinstance(
        user,
        dict
    ):
        return None

    return user


def is_logged_in():

    return (
        get_current_user()
        is not None
    )


def set_current_user(
    user_id,
    employee_id,
    employee_name,
    group_id="",
    group_name="",
    dept_no="",
    dept_name="",
    job_title=""
):

    session[
        SESSION_USER_KEY
    ] = {
        "user_id":
            str(
                user_id or ""
            ).strip(),

        "employee_id":
            str(
                employee_id or ""
            ).strip(),

        "employee_name":
            str(
                employee_name or ""
            ).strip(),

        "group_id":
            str(
                group_id or ""
            ).strip(),

        "group_name":
            str(
                group_name or ""
            ).strip(),

        "dept_no":
            str(
                dept_no or ""
            ).strip(),

        "dept_name":
            str(
                dept_name or ""
            ).strip(),

        "job_title":
            str(
                job_title or ""
            ).strip()
    }


def clear_current_user():

    session.pop(
        SESSION_USER_KEY,
        None
    )


def login_required(
    view_function
):

    @wraps(
        view_function
    )
    def wrapped_view(
        *args,
        **kwargs
    ):

        if not is_logged_in():

            return redirect(
                url_for(
                    "login"
                )
            )

        return view_function(
            *args,
            **kwargs
        )

    return wrapped_view