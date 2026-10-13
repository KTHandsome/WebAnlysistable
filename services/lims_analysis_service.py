import pyodbc
import os

from services.lims_auth_service import LIMS_CONNECTION_STRING


def get_analysis_connection_string():
    """
    ICP 委測查詢專用連線設定。
    優先使用 PHYON_LIMS DSN，
    其他連線參數沿用既有 LIMS 設定。
    """
    dsn = os.getenv(
        "PHYON_LIMS_DSN",
        "PHYON_LIMS"
    )

    parts = LIMS_CONNECTION_STRING.split(";")

    parts = [
        part for part in parts
        if part.strip()
        and not part.strip().upper().startswith("DSN=")
    ]

    return "DSN={};{}".format(
        dsn,
        ";".join(parts)
    )


def get_lims_sample_analysis(keepid):
    """
    依 SAMPLE.KEEPID 查詢 LIMS 正式委測項目。

    不限制分析方法，保留樣品所有委測項目。
    僅執行 SELECT，不修改 LIMS 資料。
    """

    keepid = str(keepid or "").strip()

    if not keepid:
        return []

    sql = """
        SELECT
            S.KEEPID,
            S.SID,
            S.PROJID,
            S.EXAMTYPE,
            A.EXAMNO,
            E.EXAMNAME,
            E.EXALIAS,
            E.EM_NUM
        FROM SAMPLE S
        JOIN ANALYSIS A
            ON A.SID = S.SID
        JOIN EXAMITEM E
            ON E.EXAMNO = A.EXAMNO
        WHERE TRIM(S.KEEPID) = ?
        ORDER BY A.EXAMNO
    """

    with pyodbc.connect(
    get_analysis_connection_string()
    ) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (keepid,))

            columns = [
                column[0].lower()
                for column in cursor.description
            ]

            return [
                {
                    key: (
                        value.strip()
                        if isinstance(value, str)
                        else value
                    )
                    for key, value in zip(columns, row)
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
