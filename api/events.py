r"""pipeline 事件匯流排(UPDATE 15,chunk 2)。

main.run() 會被丟到 worker thread(asyncio.to_thread)執行,emit 從該 thread 呼叫;
但訂閱者的 asyncio.Queue 屬於 event loop 那條 thread → 直接 put_nowait 跨執行緒不安全。
所以 emit 用 loop.call_soon_threadsafe 把事件安全地排回 event loop。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("api.events")

# 每個訂閱者記 (它所屬的 event loop, queue)
_subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []


def subscribe() -> asyncio.Queue:
    """在 event loop(SSE handler)裡呼叫:建立並登記一個 queue。"""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    _subs.append((loop, q))
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    global _subs
    _subs = [(lp, qq) for (lp, qq) in _subs if qq is not q]


def emit(kind: str, data: dict) -> None:
    """可能從 worker thread 呼叫 → call_soon_threadsafe 跨回 event loop。失敗一律忽略。"""
    for loop, q in list(_subs):
        try:
            loop.call_soon_threadsafe(q.put_nowait, {"kind": kind, "data": data})
        except Exception as e:  # noqa: BLE001 — 事件推送失敗不可影響發片
            logger.warning("emit 失敗(忽略):%s", e)
