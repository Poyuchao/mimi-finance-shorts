"""⑨ 資料庫 models(UPDATE 6)。

2 表,一對多:
    runs (1) ──< candidates (多)

一次 pipeline 執行 = 1 筆 Run + ~10 筆 Candidate(其中 3 筆 selected=True)。
目的:事後回查「LLM 從這 10 篇選了哪 3 篇、為什麼」→ 驗證選片品質。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Run(Base):
    """一次 pipeline 執行。"""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    run_date = Column(Date, index=True)
    created_at = Column(DateTime, default=datetime.now)
    status = Column(String)                    # success / failed / skipped
    video_title = Column(String, nullable=True)
    youtube_url = Column(String, nullable=True)

    candidates = relationship(
        "Candidate", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Run {self.id} {self.run_date} {self.status} {self.video_title!r}>"


class Candidate(Base):
    """該次執行的候選新聞(~10 篇全記,標記哪些被 LLM 選中)。"""

    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), index=True)   # 屬於哪次執行

    title = Column(String)
    source = Column(String)
    link = Column(String, index=True)          # 之後要做跨天去重也用得到
    published = Column(DateTime, nullable=True)

    selected = Column(Boolean, default=False)  # ★ 有沒有被 LLM 選中
    position = Column(Integer, nullable=True)  # ★ 選中的話是第幾則(1/2/3)
    select_reason = Column(Text, nullable=True)  # ★ LLM 的選片理由(選中才有)

    created_at = Column(DateTime, default=datetime.now)

    run = relationship("Run", back_populates="candidates")

    def __repr__(self) -> str:
        mark = f"✔{self.position}" if self.selected else " "
        return f"<Candidate [{mark}] {self.source} {self.title!r}>"
