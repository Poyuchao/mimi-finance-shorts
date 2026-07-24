"""⑨ DB 寫入邏輯(UPDATE 6)。

save_run():一次執行 → 寫入 1 筆 Run + N 筆 Candidate(候選 ~10 篇全記,標記選中的)。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Candidate, Run

logger = logging.getLogger(__name__)


def save_run(
    session: Session,
    *,
    status: str,
    video_title: str | None = None,
    youtube_url: str | None = None,
    candidates: list[dict] | None = None,
    selected_links: set[str] | None = None,
    reasons: dict[str, str] | None = None,
    positions: dict[str, int] | None = None,
) -> int:
    """寫入一次執行的記錄,回傳 run_id。

    candidates:候選 ~10 篇 [{title, source, link, published}, ...](全部記下)
    selected_links:被 LLM 選中的 link 集合
    reasons / positions:{link: 選片理由} / {link: 第幾則(1~3)}
    """
    selected_links = selected_links or set()
    reasons = reasons or {}
    positions = positions or {}

    run = Run(
        run_date=date.today(),
        status=status,
        video_title=video_title,
        youtube_url=youtube_url,
    )
    session.add(run)
    session.flush()   # 先拿到 run.id

    for c in candidates or []:
        link = c.get("link")
        is_sel = link in selected_links
        session.add(
            Candidate(
                run_id=run.id,
                title=c.get("title"),
                source=c.get("source"),
                link=link,
                published=c.get("published"),
                selected=is_sel,
                position=positions.get(link) if is_sel else None,
                select_reason=reasons.get(link) if is_sel else None,
            )
        )

    session.commit()
    logger.info(
        "DB 已記錄:run_id=%s(候選 %d 篇,選中 %d 篇)",
        run.id, len(candidates or []), len(selected_links),
    )
    return run.id


def get_recent_selections(session: Session, days: int = 7) -> list[dict]:
    """🆕 UPDATE 8:查過去 N 天「已被選用」的新聞(給 agent 參考最近發過什麼)。

    回 [{title, link, run_date}, ...];目前只供參考,不做強制去重。
    """
    cutoff = date.today() - timedelta(days=days)
    rows = session.execute(
        select(Candidate.title, Candidate.link, Run.run_date)
        .join(Run, Candidate.run_id == Run.id)
        .where(Run.run_date >= cutoff, Candidate.selected.is_(True))
        .order_by(Run.run_date.desc())
    ).all()
    return [
        {"title": t, "link": l, "run_date": str(d)} for t, l, d in rows
    ]


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from db.database import get_session, init_db

    init_db()

    # U6-2 驗證:塞一筆假資料(10 候選,標 3 篇 selected)
    fake_candidates = [
        {"title": f"測試新聞 {i}", "source": "自由時報" if i % 2 else "風傳媒",
         "link": f"https://example.com/news/{i}", "published": None}
        for i in range(1, 11)
    ]
    sel = {"https://example.com/news/3",
           "https://example.com/news/7",
           "https://example.com/news/1"}
    reasons = {
        "https://example.com/news/3": "權值股重大事件,市場焦點",
        "https://example.com/news/7": "影響整體大盤的資金流",
        "https://example.com/news/1": "產業級趨勢,衝擊相關股",
    }
    positions = {"https://example.com/news/3": 1,
                 "https://example.com/news/7": 2,
                 "https://example.com/news/1": 3}

    session = get_session()
    run_id = save_run(
        session, status="success",
        video_title="測試影片標題", youtube_url="https://youtu.be/TEST123",
        candidates=fake_candidates, selected_links=sel,
        reasons=reasons, positions=positions,
    )

    # 查回來驗證
    from db.models import Run as R

    run = session.get(R, run_id)
    print(f"\n{'=' * 66}")
    print(f"run_id={run.id}  {run.run_date}  status={run.status}")
    print(f"影片:{run.video_title}  →  {run.youtube_url}")
    print(f"候選共 {len(run.candidates)} 篇(用 relationship 查出來的)")
    print("=" * 66)
    for c in sorted(run.candidates, key=lambda x: (not x.selected, x.position or 99)):
        if c.selected:
            print(f"  ✅ 選中#{c.position}  [{c.source}] {c.title}")
            print(f"              理由:{c.select_reason}")
        else:
            print(f"  ⬜ 未選     [{c.source}] {c.title}")
    session.close()
