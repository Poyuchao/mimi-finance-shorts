"""Finance News MCP Server(UPDATE 8)。

以 MCP 標準協議,把「抓新聞 + 查歷史選片」暴露成 agent 可呼叫的 tools。
★ 不重寫功能 —— tool 內部就是呼叫既有的 fetch_rss / parse_filter / select_news / repository。★

本地 stdio server。可被:
  • 本專案的 mcp_client.py 呼叫(pipeline 用)
  • Claude Desktop / Cursor 等 MCP client 直接使用

單獨啟動(通常由 client 以子行程帶起,不用手動跑):
    python mcp_server/finance_news_server.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Any

# 讓「被當成腳本直接啟動」時也找得到專案根目錄的模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import config  # noqa: E402

# ★ stdio server:日誌一律走 stderr,絕不能污染 stdout(stdout 是 MCP 協議通道)
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(levelname)s [mcp-server] %(message)s")
logger = logging.getLogger(__name__)

app = FastMCP("finance-news")


def _jsonable(candidates: list[dict]) -> list[dict]:
    """把候選新聞轉成可 JSON 序列化的形式(datetime → 字串,去掉內部欄位)。"""
    out = []
    for c in candidates:
        pub = c.get("published")
        out.append({
            "title": c.get("title", ""),
            "source": c.get("source", ""),
            "link": c.get("link", ""),
            "published": pub.isoformat() if isinstance(pub, datetime) else None,
            "clean_text": (c.get("clean_text") or "")[:300],
        })
    return out


@app.tool()
def fetch_finance_news(pool_size: int = 10) -> list[dict[str, Any]]:
    """【即時候選】抓取三來源財經 RSS,篩出股市新聞,收斂成「今天還可以選的候選池」。

    ⚠️ 這是「候選」,不是「選中/已發布」:
      • 回傳的是「現在即時」抓到、『尚未經過 LLM 選片』的候選新聞。
      • 這些新聞 ★沒有被選中、也沒有選片理由★,更不代表任何一支已發布的影片。
      • 內容是即時的,會隨當天 RSS 更新而變 —— 不等於某次執行當時的候選池。
    → 想知道「某天實際選了/發布了什麼、理由是什麼」,請改用
      get_recent_selections 或 get_run_detail(那才是 DB 裡的選片事實),不要用本工具。
    → 本工具只適合回答「今天現在還有哪些新題材可以選」這類前瞻性問題。

    Args:
        pool_size: 候選池要幾則(預設 10)

    Returns:
        候選新聞列表,每則含 title / source / link / published / clean_text
        (★注意:無 selected、無 select_reason —— 因為根本還沒選★)
    """
    import fetch_rss
    import parse_filter
    import select_news

    entries = fetch_rss.fetch_rss()
    stock = parse_filter.parse_filter(entries)
    candidates = select_news.select_news(stock, pool=pool_size)
    logger.info("fetch_finance_news → %d 則候選", len(candidates))
    return _jsonable(candidates)


@app.tool()
def get_recent_selections(days: int = 7) -> list[dict[str, Any]]:
    """【選片事實】查過去 N 天「LLM 真正選中、且已發布」的新聞(來自 DB,附選片理由)。

    ★ 這才是「某天選了什麼 / 上了什麼」的權威答案 ★:
      • 只回 selected=True 的新聞 —— 每一則都真的被選進影片並發布過。
      • 附 select_reason(當初選它的理由)、position(第幾則)、run_id(哪一次)。
      • 資料是 DB 快照,穩定、可回溯,不會隨即時 RSS 變動。
    → 問「今天/這週選了哪些、為什麼」→ 用這個(days=1 就是今天)。
    → 不要用 fetch_finance_news 回答這種問題(那是即時候選,沒選中、沒理由)。

    Args:
        days: 往前查幾天(預設 7;days=1 = 只看今天)

    Returns:
        [{run_id, run_date, source, title, link, position, select_reason}, ...]
        依日期新→舊、同一次依 position(第 1/2/3 則)排序。
    """
    from db import repository
    from db.database import get_session, init_db

    init_db()
    session = get_session()
    try:
        rows = repository.get_recent_selections(session, days=days)
        logger.info("get_recent_selections(%d 天)→ %d 則", days, len(rows))
        return rows
    finally:
        session.close()


@app.tool()
def get_run_detail(run_id: int) -> dict[str, Any]:
    """查詢「某一次執行」的完整選片細節。

    回傳當時的所有候選新聞、LLM 選中的三則、每則的選片理由與排序位置。

    什麼時候用這個工具:
      • 當你已經從 get_recent_selections 看到某次選片「可能有問題」,
        需要深入了解那一次的完整判斷依據時。
      • 當使用者問「第 N 次(run_id=N)那次為什麼這樣選」時。
      • 需要比較「被選中的 3 則」與「同批被淘汰的其他候選」時。

    Args:
        run_id: 要查的執行編號(可從 get_recent_selections 或 runs://latest 得知)

    Returns:
        {run_id, run_date, status, video_title, youtube_url,
         candidates: [{title, source, link, selected, position, reason}, ...]}
        找不到該 run_id → {"error": "run_id=N 不存在"}
    """
    from db import repository
    from db.database import get_session, init_db

    init_db()
    session = get_session()
    try:
        detail = repository.get_run_detail(session, run_id=run_id)
        if detail is None:
            logger.info("get_run_detail(run_id=%d)→ 查無此執行", run_id)
            return {"error": f"run_id={run_id} 不存在"}
        n_sel = sum(1 for c in detail["candidates"] if c["selected"])
        logger.info("get_run_detail(run_id=%d)→ 候選 %d 篇、選中 %d 篇",
                    run_id, len(detail["candidates"]), n_sel)
        return detail
    finally:
        session.close()


@app.tool()
def get_video_stats(limit: int = 10) -> list[dict[str, Any]]:
    """【觀看表現 · 來自 DB 快照】查各支已發布影片的觀看數 / 讚 / 留言,依觀看數由高到低排序。

    什麼時候用:
      • 使用者問「哪支影片觀看數最多 / 前幾名 / 表現最好」時。
      • 想比較不同影片的觀看表現時。
      • (查「某一次的完整選片 + 該支觀看數」用 get_run_detail;本工具是跨影片排名。)

    ⚠️ 這是「DB 快照」,不是即時數字:
      • 回的是「上次 refresh_stats 撈的觀看數」,每則附 stats_updated_at 標明撈取時間。
      • 只列「有觀看數」的影片(剛發片還沒撈、或影片已刪的不會出現)。
      • 要最新數字需先在本機跑 refresh_stats(agent 無法觸發,純唯讀)。

    Args:
        limit: 回前幾名(預設 10;依觀看數由高到低)

    Returns:
        [{run_id, run_date, video_title, youtube_url,
          view_count, like_count, comment_count, stats_updated_at}, ...]
    """
    from db import repository
    from db.database import get_session, init_db

    init_db()
    session = get_session()
    try:
        rows = repository.get_video_stats(session, limit=limit)
        logger.info("get_video_stats(limit=%d)→ %d 支有觀看數", limit, len(rows))
        return rows
    finally:
        session.close()


@app.resource("runs://latest")
def latest_run_summary() -> str:
    """最近一次執行的摘要:日期、候選數、選中的三則標題。

    這是一個 MCP Resource(唯讀資料端點),讓 client 不必呼叫 tool
    就能快速取得「最新一次選片」的概況。
    """
    from db import repository
    from db.database import get_session, init_db

    init_db()
    session = get_session()
    try:
        from sqlalchemy import select as _select

        from db.models import Run
        run = session.scalars(
            _select(Run).order_by(Run.id.desc()).limit(1)
        ).first()
        if run is None:
            return "(尚無任何執行記錄)"

        detail = repository.get_run_detail(session, run_id=run.id)
        picked = [c for c in detail["candidates"] if c["selected"]]
        lines = [
            f"最近一次執行:run_id={detail['run_id']}  日期={detail['run_date']}",
            f"影片標題:{detail['video_title'] or '-'}",
            f"候選 {len(detail['candidates'])} 篇,選中 {len(picked)} 篇:",
        ]
        for c in picked:
            lines.append(f"  #{c['position']} [{c['source']}] {c['title']}")
        return "\n".join(lines)
    finally:
        session.close()


if __name__ == "__main__":
    app.run(transport="stdio")
