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

import os
from pathlib import Path

from firebird.driver import driver_config
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

INSTANCE_DIR.mkdir(
    exist_ok=True
)


# ========================================
# 資料庫類型
# 預設仍使用 SQLite
# ========================================

DATABASE_TYPE = (
    os.getenv(
        "PHYON_DB_TYPE",
        "sqlite"
    )
    .strip()
    .lower()
)


# ========================================
# SQLAlchemy Engine
# ========================================

if DATABASE_TYPE == "firebird":

    # ----------------------------------------
    # 明確指定 64-bit Firebird Client
    # ----------------------------------------

    driver_config.fb_client_library.value = (
        r"C:\Program Files\Firebird\Firebird_5_0\fbclient.dll"
    )

    DATABASE_URL = (
        "firebird+firebird://SYSDBA:masterkey@192.168.0.5/"
        "E:/PhyonDatabase/PHYON.FDB"
        "?charset=UTF8"
    )

else:

    DATABASE_URL = (
        f"sqlite:///{DATABASE_PATH.as_posix()}"
    )


engine = create_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True
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