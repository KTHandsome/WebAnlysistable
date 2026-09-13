from flask import Flask
from sqlalchemy import create_engine, String, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

app = Flask(__name__)

engine = create_engine(
    "sqlite:///phyon_flask_test.db",
    echo=True
)


class Base(DeclarativeBase):
    pass


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


Base.metadata.create_all(engine)


@app.route("/")
def index():

    with Session(engine) as session:

        row = TestData(
            name="Flask Database Test"
        )

        session.add(row)
        session.commit()

        rows = session.query(TestData).all()

    result = "<h1>Phyon Flask + SQLite Test</h1>"

    for row in rows:
        result += f"<p>ID={row.id}, NAME={row.name}</p>"

    return result


if __name__ == "__main__":
    app.run(debug=True)