r"""/run:觸發跑片 + SSE 推進度(UPDATE 15,chunk 2)。

GET /api/run/stream:一開流就在背景跑 main.run(),把 stage / log / done / error
事件以 SSE 逐步推給前端即時跑片頁。

★ 一次只允許一支(_running 鎖);pipeline 丟 to_thread 不卡事件迴圈。
★ 這會真的產出影片、且在 UPLOAD_ENABLED=True 時「真的上傳 YouTube」—— 不是模擬! ★
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import main
from api import events

router = APIRouter()
_running = False


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/run/stream")
async def run_stream():
    global _running
    if _running:
        async def busy():
            yield _sse("error", {"text": "已有一支正在產生,請等它跑完再開始"})
        return StreamingResponse(busy(), media_type="text/event-stream")

    q = events.subscribe()

    async def gen():
        global _running
        _running = True
        main.EMIT = events.emit   # 讓 pipeline 的 _emit 把事件送進匯流排

        async def _runner():
            try:
                await asyncio.to_thread(main.run)   # 同步、重 IO → 丟執行緒
            except Exception as e:  # noqa: BLE001 — run 內部多半已容錯,這裡兜底
                events.emit("error", {"text": str(e)})

        task = asyncio.create_task(_runner())
        try:
            yield _sse("stage", {"name": "啟動 pipeline", "sub": ""})
            while True:
                ev = await q.get()
                yield _sse(ev["kind"], ev["data"])
                if ev["kind"] in ("done", "error"):
                    break
        finally:
            events.unsubscribe(q)
            main.EMIT = None
            _running = False
            if not task.done():
                task.cancel()

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
