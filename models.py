from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SystemTest(Base):
    __tablename__ = "system_test"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )