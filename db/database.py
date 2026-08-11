"""⑨ DB 連線 + 初始化(UPDATE 6)。

本機:sqlite:///mimi.db
上雲(UPDATE 7):只改 config.DB_URL(+ GCS 上下載),models / repository 不用動。
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

import config
from db.models import Base

logger = logging.getLogger(__name__)

engine = create_engine(config.DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# 🆕 UPDATE 10:輕量遷移 —— create_all 只「建新表」,不會幫「既有表」加欄位。
# 對既有 mimi.db,用 SQLite 的 ALTER TABLE ADD COLUMN 補上新欄位(冪等)。
_MIGRATIONS: dict[str, dict[str, str]] = {
    "runs": {
        "view_count": "INTEGER",
        "like_count": "INTEGER",
        "comment_count": "INTEGER",
        "stats_updated_at": "DATETIME",
    },
}


def _migrate() -> None:
    """對既有資料表補加缺少的欄位(不動已有欄位、不刪資料)。"""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _MIGRATIONS.items():
            if table not in tables:
                continue   # 新 DB 由 create_all 直接帶齊,不需遷移
            have = {c["name"] for c in insp.get_columns(table)}
            for col, coltype in cols.items():
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                    logger.info("DB 遷移:%s 補上欄位 %s %s", table, col, coltype)


def init_db() -> None:
    """首次執行自動建表(已存在則不動)+ 既有表補欄位遷移。"""
    Base.metadata.create_all(engine)
    _migrate()
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
