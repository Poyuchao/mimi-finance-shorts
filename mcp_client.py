"""MCP client(UPDATE 8):透過 MCP 標準協議向 finance-news server 取得工具能力。

啟動 server 子行程(stdio)→ 呼叫 tools → 回傳資料給選片 agent。
★ 呼叫端(main.py)要自行 try/except:MCP 失敗就 fallback 回直接呼叫。★
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client

import config

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_SERVER_SCRIPT = os.path.join(_PROJECT_ROOT, "mcp_server", "finance_news_server.py")


def _server_params() -> StdioServerParameters:
    """用「目前這個 venv 的 python」+ 專案根目錄當 cwd 啟動 server。

    ★ cwd 很重要:否則 sqlite:///mimi.db 這種相對路徑會找不到 DB。★
    """
    return StdioServerParameters(
        command=sys.executable,          # 確保用 venv 的 python(套件才找得到)
        args=[_SERVER_SCRIPT],
        cwd=_PROJECT_ROOT,
    )


def _parse(result) -> Any:
    """把 MCP 的 CallToolResult 解析成 Python 物件。"""
    # 新版 SDK 若有 structuredContent 就直接用;否則解析 text content
    structured = getattr(result, "structuredContent", None)
    if structured:
        # FastMCP 回傳 list 時會包成 {"result": [...]}
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    return None


async def fetch_candidates_via_mcp(
    pool_size: int | None = None,
    dedup_days: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """透過 MCP 取得 (候選新聞, 最近已發過的新聞)。

    失敗會 raise —— 由呼叫端(main.py)fallback 回直接呼叫。
    """
    pool_size = pool_size if pool_size is not None else config.NEWS_POOL
    dedup_days = dedup_days if dedup_days is not None else config.DEDUP_DAYS

    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            logger.info("MCP 可用工具:%s", [t.name for t in tools.tools])

            res = await session.call_tool("fetch_finance_news", {"pool_size": pool_size})
            candidates = _parse(res) or []

            rec = await session.call_tool("get_recent_selections", {"days": dedup_days})
            recent = _parse(rec) or []

    logger.info("MCP 取得:候選 %d 則、近 %d 天已發 %d 則",
                len(candidates), dedup_days, len(recent))
    return candidates, recent


if __name__ == "__main__":
    import asyncio

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cands, recent = asyncio.run(fetch_candidates_via_mcp())
    print(f"\n=== 透過 MCP 拿到候選 {len(cands)} 則 ===")
    for i, c in enumerate(cands):
        print(f"  [{i}] [{c['source']}] {c['title']}")
    print(f"\n=== 近 {config.DEDUP_DAYS} 天已選用 {len(recent)} 則 ===")
    for r in recent[:10]:
        print(f"  ({r['run_date']}) {r['title']}")
