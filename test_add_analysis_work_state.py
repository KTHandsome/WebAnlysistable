from database import engine
from models import Base, AnalysisWorkState


def main():

    table_name = (
        AnalysisWorkState.__tablename__
    )

    if table_name in Base.metadata.tables:

        AnalysisWorkState.__table__.create(
            bind=engine,
            checkfirst=True
        )

        print(
            table_name
            + " 建立完成或已存在。"
        )

    else:

        print(
            "找不到 "
            + table_name
            + " 的模型定義。"
        )


if __name__ == "__main__":
    main()
    