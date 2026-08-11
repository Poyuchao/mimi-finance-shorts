"""⑨ DB 寫入邏輯(UPDATE 6)。

save_run():一次執行 → 寫入 1 筆 Run + N 筆 Candidate(候選 ~10 篇全記,標記選中的)。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

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
    """🆕 UPDATE 8(U9 補強):查過去 N 天「已被選中/發布」的新聞。

    ★ 這是「選片事實」的權威來源 —— 只回 selected=True 的,且附選片理由。★
    回 [{run_id, run_date, source, title, link, position, select_reason}, ...]。
    (U9 補上 run_id / source / position / select_reason,讓 agent 一次就拿到
     『選了什麼 + 哪一次 + 第幾則 + 為什麼』,不必再多查 get_run_detail。)
    """
    cutoff = date.today() - timedelta(days=days)
    rows = session.execute(
        select(
            Candidate.run_id,
            Run.run_date,
            Candidate.source,
            Candidate.title,
            Candidate.link,
            Candidate.position,
            Candidate.select_reason,
        )
        .join(Run, Candidate.run_id == Run.id)
        .where(Run.run_date >= cutoff, Candidate.selected.is_(True))
        .order_by(Run.run_date.desc(), Candidate.position.asc())
    ).all()
    return [
        {
            "run_id": rid,
            "run_date": str(d),
            "source": src,
            "title": t,
            "link": l,
            "position": pos,
            "select_reason": reason,
        }
        for rid, d, src, t, l, pos, reason in rows
    ]


def get_video_stats(session: Session, limit: int = 10) -> list[dict]:
    """🆕 UPDATE 10:查各支「已有觀看數」的影片,依觀看數由高到低。

    給 agent 回答「哪支觀看最多 / 前幾名」用。★唯讀,讀 DB 快照(非即時)。★
    只回有 view_count 的(剛發片還沒撈、或影片已刪的不列)。
    回 [{run_id, run_date, video_title, youtube_url,
         view_count, like_count, comment_count, stats_updated_at}, ...]
    """
    q = (
        select(
            Run.id, Run.run_date, Run.video_title, Run.youtube_url,
            Run.view_count, Run.like_count, Run.comment_count, Run.stats_updated_at,
        )
        .where(Run.view_count.isnot(None))
        .order_by(Run.view_count.desc())
    )
    if limit:
        q = q.limit(limit)
    rows = session.execute(q).all()
    return [
        {
            "run_id": rid,
            "run_date": str(d),
            "video_title": title,
            "youtube_url": url,
            "view_count": vc,
            "like_count": lc,
            "comment_count": cc,
            "stats_updated_at": str(sa) if sa else None,
        }
        for rid, d, title, url, vc, lc, cc, sa in rows
    ]


def update_run_stats(session: Session, run_id: int, stats: dict) -> bool:
    """🆕 UPDATE 10:把撈到的觀看數寫回 Run(快照,附撈取時間)。

    stats:{view_count, like_count, comment_count}(缺的為 None)。
    回傳是否有更新到(找不到 run_id → False)。★寫入類,不上 MCP。★
    """
    run = session.get(Run, run_id)
    if run is None:
        return False
    run.view_count = stats.get("view_count")
    run.like_count = stats.get("like_count")
    run.comment_count = stats.get("comment_count")
    run.stats_updated_at = datetime.now()   # ★記下「這批數字何時撈的」★
    session.commit()
    return True


def get_run_detail(session: Session, run_id: int) -> dict | None:
    """🆕 UPDATE 9:取單次執行的完整選片細節(供稽核 agent 深挖用)。

    回傳單次執行的所有候選新聞、哪 3 則被選中、每則的選片理由與排序。
    找不到該 run_id → 回 None(讓上層/agent 自行決定怎麼處理)。

    回傳形狀:
        {
          "run_id": int,
          "run_date": "YYYY-MM-DD",
          "status": str,
          "video_title": str | None,
          "youtube_url": str | None,
          "candidates": [
             {"title", "source", "link", "selected", "position", "reason"}, ...
          ],  # 選中的排前面(依 position),其餘依原順序
        }
    """
    run = session.get(Run, run_id)
    if run is None:
        return None

    cands = sorted(
        run.candidates,
        key=lambda c: (not c.selected, c.position or 99, c.id),
    )
    return {
        "run_id": run.id,
        "run_date": str(run.run_date),
        "status": run.status,
        "video_title": run.video_title,
        "youtube_url": run.youtube_url,
        # 🆕 UPDATE 10:觀看數快照(可能為 None:剛發片/影片已刪)
        "view_count": run.view_count,
        "like_count": run.like_count,
        "comment_count": run.comment_count,
        "stats_updated_at": str(run.stats_updated_at) if run.stats_updated_at else None,
        "candidates": [
            {
                "title": c.title,
                "source": c.source,
                "link": c.link,
                "selected": bool(c.selected),
                "position": c.position,
                "reason": c.select_reason,
            }
            for c in cands
        ],
    }


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
