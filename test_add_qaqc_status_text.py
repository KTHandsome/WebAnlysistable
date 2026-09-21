from sqlalchemy import text

from database import engine


def main():

    with engine.begin() as conn:

        columns = conn.execute(
            text(
                "PRAGMA table_info(analysis_qaqc_result)"
            )
        ).fetchall()

        column_names = {
            row[1]
            for row in columns
        }

        if "status_text" in column_names:

            print(
                "status_text 欄位已存在，"
                "不需要重複新增。"
            )

            return

        conn.execute(
            text(
                """
                ALTER TABLE analysis_qaqc_result
                ADD COLUMN status_text VARCHAR(30)
                NOT NULL DEFAULT ''
                """
            )
        )

        print(
            "analysis_qaqc_result.status_text "
            "新增成功。"
        )


if __name__ == "__main__":
    main()
    