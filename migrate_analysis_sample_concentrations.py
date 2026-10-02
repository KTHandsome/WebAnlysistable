from sqlalchemy import inspect, text

from database import engine


TABLE_NAME = "analysis_sample"

COLUMNS_TO_ADD = {
    "measured_concentration": "FLOAT",
    "sample_concentration": "FLOAT",
    "qaqc_concentration": "FLOAT",
}


def main():

    inspector = inspect(engine)

    existing_columns = {
        column["name"].lower()
        for column in inspector.get_columns(
            TABLE_NAME
        )
    }

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

            if engine.dialect.name.startswith("firebird"):

                   sql = (
                  "ALTER TABLE "
                 + TABLE_NAME
                     + " ADD "
                  + column_name
                  + " "
                  + column_type
                  )

            else:

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

    print(
        "analysis_sample migration completed."
    )


if __name__ == "__main__":
    main()