from firebird.driver import (
    connect,
    driver_config
)


# ========================================
# Firebird Client
# ========================================

driver_config.fb_client_library.value = (
    r"C:\Program Files\Firebird\Firebird_5_0\fbclient.dll"
)


# ========================================
# LIMS Database
# ========================================

LIMS_DATABASE = (
    "192.168.0.200:LIMSDB-FQ"
)

LIMS_USER = "SYSDBA"

LIMS_PASSWORD = "masterkey"

LIMS_CHARSET = "UTF8"


# ========================================
# LIMS Base64 編碼表
# 完整對應 VB Base64Url
# ========================================

CODES64 = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789+/"
)


def decode64(
    encoded_text
):

    result = []

    b = 0
    a = 0

    for ch in str(
        encoded_text
        or ""
    ):

        x = CODES64.find(
            ch
        )

        if x < 0:
            break

        b = (
            b * 64
            + x
        )

        a += 6

        while a >= 8:

            a -= 8

            y = (
                b >> a
            )

            b = (
                b
                & (
                    (1 << a)
                    - 1
                )
            )

            result.append(
                chr(y)
            )

    return "".join(
        result
    )


# ========================================
# LIMS 使用者驗證
# ========================================

def validate_lims_user(
    user_id,
    password
):

    user_id = str(
        user_id
        or ""
    ).strip()

    password = str(
        password
        or ""
    )

    if not user_id:
        return None

    if not password:
        return None

    conn = None
    cursor = None

    try:

        conn = connect(
            database=LIMS_DATABASE,
            user=LIMS_USER,
            password=LIMS_PASSWORD,
            charset=LIMS_CHARSET
        )

        cursor = conn.cursor()

        # ========================================
        # 1. 查 SYS_USER
        # ========================================

        cursor.execute(
            """
            SELECT
                TAKENO,
                PASSWORD,
                GROUPID
            FROM SYS_USER
            WHERE USERID = ?
            """,
            (
                user_id,
            )
        )

        user_row = (
            cursor.fetchone()
        )

        if user_row is None:
            return None

        employee_id = str(
            user_row[0]
            or ""
        ).strip()

        stored_password = str(
            user_row[1]
            or ""
        )

        group_id = str(
           user_row[2]
           or ""
        ).strip()

        # ========================================
        # 2. 解碼並比對密碼
        # ========================================

        decoded_password = (
            decode64(
                stored_password
            )
        )

        if (
            decoded_password
            != password
        ):
            return None

        # ========================================
        # 3. 查 EMPLOY / DEPARTMENT
        # ========================================

        cursor.execute(
            """
            SELECT
                e.EMPNAME,
                e.CARDNO,
                e.DEPTNO,
                d.DEPTNAME
            FROM EMPLOY e
            LEFT JOIN DEPARTMENT d
                ON d.DEPTNO = e.DEPTNO
            WHERE e.EMPID = ?
            """,
            (
                employee_id,
            )
        )

        employee_row = (
            cursor.fetchone()
        )

        if employee_row is None:
            return None

        return {
            "user_id":
                user_id,

            "employee_id":
                employee_id,

            "employee_name":
                str(
                    employee_row[0]
                    or ""
                ).strip(),

            "card_number":
                str(
                    employee_row[1]
                    or ""
                ).strip(),

            "dept_no":
                str(
                    employee_row[2]
                    or ""
                ).strip(),

            "dept_name":
                str(
                    employee_row[3]
                    or ""
                ).strip(),

            "group_id":
                group_id    
        }

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()
