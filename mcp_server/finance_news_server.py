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
    """抓取三來源(ETtoday/自由時報/風傳媒)財經 RSS,篩出股市新聞,收斂成候選池。

    Args:
        pool_size: 候選池要幾則(預設 10)

    Returns:
        候選新聞列表,每則含 title / source / link / published / clean_text
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
    """查詢過去 N 天「已被選用/發布過」的新聞,供 agent 參考最近發過什麼。

    Args:
        days: 往前查幾天(預設 7)

    Returns:
        [{title, link, run_date}, ...]
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


if __name__ == "__main__":
    app.run(transport="stdio")
