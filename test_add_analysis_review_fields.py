from sqlalchemy import text

from database import engine


def main():

    with engine.begin() as conn:

        columns = conn.execute(
            text(
                "PRAGMA table_info(analysis_record)"
            )
        ).fetchall()

        column_names = {
            row[1]
            for row in columns
        }

        migrations = [
            (
                "reviewer_user_id",
                """
                ALTER TABLE analysis_record
                ADD COLUMN reviewer_user_id VARCHAR(50)
                NOT NULL DEFAULT ''
                """
            ),
            (
                "reviewer_employee_id",
                """
                ALTER TABLE analysis_record
                ADD COLUMN reviewer_employee_id VARCHAR(50)
                NOT NULL DEFAULT ''
                """
            ),
            (
                "reviewer_name",
                """
                ALTER TABLE analysis_record
                ADD COLUMN reviewer_name VARCHAR(100)
                NOT NULL DEFAULT ''
                """
            ),
            (
                "reviewed_at",
                """
                ALTER TABLE analysis_record
                ADD COLUMN reviewed_at DATETIME
                NULL
                """
            ),
            (
                "review_comment",
                """
                ALTER TABLE analysis_record
                ADD COLUMN review_comment VARCHAR(500)
                NOT NULL DEFAULT ''
                """
            )
        ]

        added_count = 0

        for column_name, sql in migrations:

            if column_name in column_names:

                print(
                    column_name
                    + " 已存在，略過。"
                )

                continue

            conn.execute(
                text(sql)
            )

            print(
                column_name
                + " 新增成功。"
            )

            added_count += 1

        print(
            "完成，共新增 "
            + str(added_count)
            + " 個欄位。"
        )


if __name__ == "__main__":
    main()