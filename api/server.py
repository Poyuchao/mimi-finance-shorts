r"""控制台 API — FastAPI app(UPDATE 15)。

薄層:把現有 Python 能力暴露給前端控制台。目前掛查詢類路由(chunk 1);
之後再加 /run(SSE 跑片)與 /audit(agent 串流)。

啟動(專案根目錄):
    .\venv\Scripts\uvicorn.exe api.server:app --port 8000 --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_run import router as run_router
from api.routes_runs import router as runs_router

app = FastAPI(title="米米財經 控制台 API", version="0.1")

# 前端 dev server(Vite)跨來源;prod 同源服務時可收斂
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router, prefix="/api")
app.include_router(run_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
