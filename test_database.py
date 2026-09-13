from sqlalchemy import create_engine, String, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session


# ========================================
# 1. 建立 SQLite 連線
# ========================================

engine = create_engine(
    "sqlite:///phyon_test.db",
    echo=True
)


# ========================================
# 2. SQLAlchemy Base
# ========================================

class Base(DeclarativeBase):
    pass


# ========================================
# 3. 最小測試資料表
# ========================================

class TestData(Base):
    __tablename__ = "test_data"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )


# ========================================
# 4. 建立資料表
# ========================================

Base.metadata.create_all(engine)


# ========================================
# 5. 寫入測試資料
# ========================================

with Session(engine) as session:

    row = TestData(
        name="Phyon SQLite Test"
    )

    session.add(row)
    session.commit()


# ========================================
# 6. 查詢測試資料
# ========================================

with Session(engine) as session:

    rows = session.query(TestData).all()

    for row in rows:
        print(
            f"ID={row.id}, NAME={row.name}"
        )