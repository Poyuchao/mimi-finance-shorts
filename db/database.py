"""⑨ DB 連線 + 初始化(UPDATE 6)。

本機:sqlite:///mimi.db
上雲(UPDATE 7):只改 config.DB_URL(+ GCS 上下載),models / repository 不用動。
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import config
from db.models import Base

logger = logging.getLogger(__name__)

engine = create_engine(config.DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """首次執行自動建表(已存在則不動)。"""
    Base.metadata.create_all(engine)
    logger.info("DB 就緒:%s", config.DB_URL)


def get_session() -> Session:
    return SessionLocal()


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # U6-1 驗證:建表 + 印出實際建好的 schema
    init_db()

    from sqlalchemy import inspect

    insp = inspect(engine)
    print(f"\n資料庫:{config.DB_URL}")
    for table in insp.get_table_names():
        print(f"\n=== 表:{table} ===")
        for col in insp.get_columns(table):
            print(f"  {col['name']:<15} {str(col['type']):<12}")
        for fk in insp.get_foreign_keys(table):
            print(f"  FK: {fk['constrained_columns']} → "
                  f"{fk['referred_table']}.{fk['referred_columns']}")
        idx = insp.get_indexes(table)
        if idx:
            print(f"  索引: {[i['column_names'] for i in idx]}")
