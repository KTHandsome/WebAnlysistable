from sqlalchemy import inspect, text

from database import engine


TABLE_NAME = "analysis_sample"

COLUMNS_TO_ADD = {
    "measured_concentration": "FLOAT",
    "sample_concentration": "FLOAT",
    "qaqc_concentration": "FLOAT",
}


def get_existing_columns():

    inspector = inspect(engine)

    return {
        column["name"].lower()
        for column in inspector.get_columns(
            TABLE_NAME
        )
    }


def migrate_sqlite(
    existing_columns
):

    with engine.begin() as conn:

        for column_name, column_type in (
            COLUMNS_TO_ADD.items()
        ):

            if (
                column_name.lower()
                in existing_columns
            ):

                print(
                    "SKIP:",
                    column_name,
                    "already exists"
                )

                continue

            sql = (
                "ALTER TABLE "
                + TABLE_NAME
                + " ADD COLUMN "
                + column_name
                + " "
                + column_type
            )

            print(
                "ADD:",
                column_name
            )

            conn.execute(
                text(sql)
            )


def migrate_firebird(
    existing_columns
):

    raw_connection = (
        engine.raw_connection()
    )

    try:

        driver_connection = (
            raw_connection.driver_connection
        )

        for column_name, column_type in (
            COLUMNS_TO_ADD.items()
        ):

            if (
                column_name.lower()
                in existing_columns
            ):

                print(
                    "SKIP:",
                    column_name,
                    "already exists"
                )

                continue

            sql = (
                "ALTER TABLE "
                + TABLE_NAME
                + " ADD "
                + column_name
                + " "
                + column_type
            )

            print(
                "ADD:",
                column_name
            )

            driver_connection.execute_immediate(
                sql
            )

            driver_connection.commit()

    finally:

        raw_connection.close()


def main():

    existing_columns = (
        get_existing_columns()
    )

    dialect_name = (
        engine.dialect.name
    )

    print(
        "DATABASE DIALECT:",
        dialect_name
    )

    if dialect_name.startswith(
        "firebird"
    ):

        migrate_firebird(
            existing_columns
        )

    else:

        migrate_sqlite(
            existing_columns
        )

    print(
        "analysis_sample migration completed."
    )


if __name__ == "__main__":
    main()