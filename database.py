from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ========================================
# 專案路徑
# ========================================

BASE_DIR = Path(__file__).resolve().parent

INSTANCE_DIR = BASE_DIR / "instance"

DATABASE_PATH = INSTANCE_DIR / "phyon.db"


# ========================================
# 確保 instance 資料夾存在
# ========================================

INSTANCE_DIR.mkdir(exist_ok=True)


# ========================================
# SQLAlchemy Engine
# ========================================

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    echo=True
)


# ========================================
# SQLAlchemy Base
# ========================================

class Base(DeclarativeBase):
    pass


# ========================================
# Session Factory
# ========================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)