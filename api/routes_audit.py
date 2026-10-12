r"""/audit:選片品質稽核 agent 串流(UPDATE 15,chunk 3)。

GET /api/audit/stream?q=<問題>&thread=<對話id>
重用 agent_langgraph:載入 MCP 工具 → 建 graph(掛 checkpointer)→ astream,
把「工具呼叫」與「最終答案」以 SSE 推給前端對話框。

★ 純唯讀(agent 只透過 MCP 查 DB);錯誤 emit error 不讓連線 crash。★
★ 這裡重現 agent_langgraph.ask() 的 astream 解析,但改成 yield SSE(ask 是 print)。★
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import agent_langgraph as ag
import config

router = APIRouter()


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/audit/stream")
async def audit_stream(q: str, thread: str = "dashboard"):
    async def gen():
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.errors import GraphRecursionError

        if not q or not q.strip():
            yield _sse("error", {"text": "問題是空的"})
            return
        try:
            tools = await ag.load_tools()   # 啟動既有 MCP server 子行程、載入工具
            async with AsyncSqliteSaver.from_conn_string(config.AGENT_CHECKPOINT_DB) as saver:
                graph = ag.build_graph(tools, saver)
                cfg = {
                    "configurable": {"thread_id": thread},
                    "recursion_limit": config.AGENT_RECURSION_LIMIT,
                }
                final = None
                try:
                    async for chunk in graph.astream(
                        {"messages": [("user", q)]}, cfg, stream_mode="updates"
                    ):
                        for node, update in chunk.items():
                            if node != "agent":
                                continue
                            for m in (update or {}).get("messages", []):
                                tcs = getattr(m, "tool_calls", None)
                                if tcs:
                                    for c in tcs:
                                        yield _sse("tool", {"name": c["name"],
                                                            "args": c.get("args", {})})
                                elif getattr(m, "content", ""):
                                    final = m.content
                    yield _sse("answer", {"text": final or "(沒有內容)"})
                except GraphRecursionError:
                    yield _sse("answer", {"text": "(已達查詢步數上限,請換個問法或縮小範圍再問)"})
        except Exception as e:  # noqa: BLE001 — 稽核是唯讀附屬,出錯不讓 API crash
            yield _sse("error", {"text": str(e)})

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
