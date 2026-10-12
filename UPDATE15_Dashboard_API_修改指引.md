# UPDATE 15:控制台後端 API(FastAPI + SSE)— 修改指引

> 在現有 Python 專案外加一層 **FastAPI**,把「歷史查詢 / 即時跑片 / 稽核 agent」暴露給前端控制台。
> 搭配前端見 `mimi_Finance_dashboard/mimi_dashboard_development.md`。

---

## 0. 原則(硬需求)

- **薄層、重用既有模組**:endpoint 內部呼叫 `repository.py` / `main.py` / `agent_langgraph.py`,**不重寫業務邏輯**。
- **不破壞發片容錯**:`main.py` 照樣能獨立 CLI 跑;加的「發事件」機制失敗**絕不中斷發片**(emit 包 try/except)。
- **純唯讀的查詢** vs **會跑 pipeline 的動作** 分清楚;跑片一次只允許一支(避免並發打架 / 重複上傳)。
- API 是**附屬**:API 掛了不影響 `python main.py` 照常發片。

---

## 1. 新檔結構

```
api/
├── __init__.py
├── server.py        # FastAPI app、CORS、掛路由、(選用)服務前端 build
├── events.py        # ★核心:pipeline 事件匯流排(emit/subscribe)
├── routes_runs.py   # GET /stats /runs /runs/{id}(讀 DB,重用 repository)
├── routes_run.py    # POST /run + GET /run/stream(SSE 推 stage/log)
└── routes_audit.py  # GET /audit/stream(SSE 轉 agent_langgraph.astream)
```

啟動:`uvicorn api.server:app --port 8000`(新增 `uvicorn`、`fastapi` 到 requirements)。

---

## 2. 查詢類 endpoint(最單純,先做這個)

全部直接重用 `db/repository.py`,開 session → 查 → 關。

| Method | Path | 回傳 | 重用 |
|---|---|---|---|
| GET | `/stats` | `{published, total_views, avg_views, blocked_this_week}` | 彙總 `get_video_stats` 等 |
| GET | `/runs` | 最近 N 筆 run 摘要陣列(日期/標題/候選數/選中數/審稿/觀看/狀態) | `get_video_stats` + runs 查詢 |
| GET | `/runs/{id}` | 單次完整:3 則選中(標題/來源/理由/highlight)+ 審稿結果 + 觀看數 + youtube_url | `get_run_detail` |

> `get_run_detail` 已回傳候選 + 選中 + 理由 + 觀看數,幾乎現成。只要把 ORM 物件轉成 JSON-safe dict(datetime → isoformat;沿用 U8 踩過的序列化教訓)。

---

## 3. ★核心:讓 pipeline「發事件」(給 SSE 用)

目前 `main.py` 是 `print` 進度。要讓 `/run` 能即時推送,改成「**發事件**」—— 但 **CLI 行為不變**。

### 3-1. `api/events.py`:極簡事件匯流排
```python
import asyncio, logging
logger = logging.getLogger("events")
_subscribers: list[asyncio.Queue] = []

def subscribe() -> asyncio.Queue:
    q = asyncio.Queue(); _subscribers.append(q); return q

def unsubscribe(q):
    if q in _subscribers: _subscribers.remove(q)

def emit(kind: str, data: dict):
    """kind: 'stage' | 'log' | 'done' | 'error'。★失敗絕不中斷發片★。"""
    try:
        for q in list(_subscribers):
            q.put_nowait({"kind": kind, "data": data})
    except Exception as e:  # noqa: BLE001
        logger.warning("emit 失敗(忽略,不影響發片):%s", e)
```

### 3-2. `main.py`:在既有步驟插 `emit`(薄薄幾行,不改邏輯)
- 把 `_step(n, msg)` 內多呼叫一次 `emit("stage", {"n": n, "msg": msg, "status": "run"})`;步驟做完 emit `status:"done"`。
- 關鍵節點 emit `log`(對齊現有 print 內容):候選數、選片結果、全文 `got/3`、審稿 `n_fixed/3`、生圖/審圖、上傳網址、DB run_id。
- **候選池 / 選片 emit `pool`、`pick`**(demo 展示漏斗用):
  - 候選池拿到後發 `pool`:走 MCP 時,`fetch_finance_news` 加選用參數 `with_stats=True`,
    多回傳各階段數字(RSS 原始 / 各來源 / 股市相關 / 候選池);**預設 `False` 行為不變**,稽核 agent 不受影響。
    MCP 失敗改走 RSS 直接抓時,main.py 本來就有 entries / stock_news / candidates,直接算。
    兩條路共用 `select_news.funnel_stats(entries, stock, candidates)`。
  - LLM 選片完發 `pick`:選中 3 則 + 名次 + 理由。未選的由前端用候選池扣掉選中的算出來(LLM 不會給未選理由,**不編造**)。
  - 「去重」不給數字,前端只在漏斗箭頭下方標小字「去重後」。
- **審稿/審圖 emit `review`**(reflection 面板用):
  - 審稿:main 改呼叫 `script_review.safe_review_and_fix_verbose()`(回 `{status, blocking, before, after}`),每則 emit 一筆 `review`。
  - 審圖:`image_service.safe_generate(item, i, on_review=...)` 加 `on_review` 回呼,把每則審圖結果(pass/rewrite/fallback + blocking)emit 成 `review`。
- **做法**:加一個模組級 `EMIT = None`(預設 None);API 跑片前設 `main.EMIT = events.emit`。`main.py` 內 `if EMIT: EMIT(...)`。CLI 直接跑時 `EMIT is None` → 完全照舊、零影響。
- ★所有 emit 包在 `if EMIT:` + 本身 try/except,絕不讓事件機制弄垮發片。★

### 3-3. SSE 格式(前端對接)
每個事件一筆:`event: <kind>\ndata: <json>\n\n`
- `stage`:`{"n":4,"name":"審稿","status":"run"|"done","sub":"1/3 重寫"}`
- `log`:`{"level":"info"|"warn"|"ok"|"err","text":"..."}`
- `pool`:候選池 + 漏斗數字 + 近 N 天已發
  ```json
  {"via":"mcp"|"rss",
   "tools":["fetch_finance_news(pool_size=10)","get_recent_selections(days=7)"],
   "stats":{"raw":129,"by_source":{"ETtoday":50,"自由時報":40,"風傳媒":39},"stock":71,"pool":10},
   "candidates":[{"title":"...","source":"自由時報","link":"..."}],
   "recent":[{"run_date":"2026-10-07","title":"..."}]}
  ```
  (`via:"rss"` = MCP 失敗、改走直接抓取;`tools` 為空,前端顯示「RSS 直接抓取(MCP fallback)」)
- `pick`:LLM 選片結果 `{"picked":[{"rank":1,"title":"...","source":"...","link":"...","reason":"..."}]}`
- `review`:審稿/審圖的 reflection 結果(給「審查流程」面板)
  `{"type":"script"|"image","index":2,"status":"pass"|"rewrite"|"fallback","blocking":["..."],"before":"原稿","after":"改寫後"}`
  (審圖沒有 before/after,只有 status + blocking)
- `progress`:影片合成百分比 `{"pct":24}`(MoviePy 寫檔進度,由 `video.compose(on_progress=...)` 經 proglog 攔截)
- `done`:`{"path":"output/final.mp4","seconds":58,"youtube":"...","run_id":38}`
- `error`:`{"text":"..."}`

> `routes_run` 的 SSE 迴圈轉發所有事件 kind,所以 `review` 不用特別處理;只有 `done`/`error` 會中止串流。

---

## 4. `/run`:觸發跑片 + SSE

- **併發保護**:模組級 `RUNNING = False`;已在跑就回 409 / 推一筆 error,不重複跑。
- **背景執行**:pipeline 是同步 + 重 IO(TTS/MoviePy),用 `asyncio.to_thread(main.run)` 丟執行緒,主執行緒跑 SSE 迴圈。
- **兩種觸發法擇一**(對齊前端):
  1. `GET /run/stream`:一開流就啟動跑片(單人本機最簡單)。
  2. `POST /run` 回 `job_id` → `GET /run/{job_id}/stream`(較正規)。
- SSE handler:`q = events.subscribe()`;迴圈 `await q.get()` → `yield` 成 SSE;收到 `done`/`error` 後 `unsubscribe` 並結束。用 `StreamingResponse(gen(), media_type="text/event-stream")`。

```python
# 範例(GET /run/stream,做法 1)
@router.get("/run/stream")
async def run_stream():
    if RUNNING: return StreamingResponse(_single_err("已有一支在跑"), media_type="text/event-stream")
    q = events.subscribe()
    async def gen():
        global RUNNING; RUNNING = True
        main.EMIT = events.emit
        task = asyncio.create_task(asyncio.to_thread(main.run))
        try:
            while True:
                ev = await q.get()
                yield f"event: {ev['kind']}\ndata: {json.dumps(ev['data'], ensure_ascii=False)}\n\n"
                if ev["kind"] in ("done", "error"): break
        finally:
            events.unsubscribe(q); main.EMIT = None; RUNNING = False
            await task if not task.done() else None
    return StreamingResponse(gen(), media_type="text/event-stream")
```
> `main.run()` 最後要 emit 一筆 `done`(成功)或 `error`(例外),迴圈才會收尾。

---

## 5. `/audit/stream`:稽核 agent 串流

重用 `agent_langgraph.py`,把它的 `astream`(工具呼叫 + 最終答案)轉成 SSE。

- `GET /audit/stream?q=<問題>`。
- 參考 `agent_langgraph.ask()` 的 `astream(..., stream_mode="updates")`:
  - 看到 `tool_calls` → emit `event: tool`,`{"name":"get_recent_selections","args":{"days":7}}`。
  - 看到 agent 最終 content → emit `event: answer`,`{"text":"..."}`(或結構化 `report`)。
- `thread_id` 可用隨機 UUID(每次對話一條);要跨題記憶就前端帶同一個 id。
- ★沿用 agent 既有的 `GraphRecursionError` fallback、`handle_tool_errors`,錯誤 emit `error` 不 crash。★

---

## 6. CORS / 服務前端

- dev:前端 `:5173` 走 vite proxy `/api` → `:8000`,通常免 CORS;保險起見加 `CORSMiddleware` 允許 `http://localhost:5173`。
- prod:`npm run build` 出 `dist/`,FastAPI 用 `StaticFiles` 掛在 `/`,前後端同源、單一 server。

---

## 7. Checklist(review 用)

- [ ] 查詢 endpoint 全部重用 `repository.py`,datetime 有轉 isoformat(不要重蹈 U8 序列化坑)
- [ ] `main.py` 加 emit 後,**`python main.py` 單獨跑行為完全不變**(EMIT=None)
- [ ] 每個 emit 都在 `if EMIT:` 內 + try/except,**事件失敗不中斷發片**
- [ ] `/run` 併發保護:一次只跑一支
- [ ] pipeline 跑在 `to_thread`,SSE 不被阻塞
- [ ] `main.run()` 結尾一定 emit `done` 或 `error`
- [ ] SSE 事件格式與前端 `api.js` 一致(stage/log/done/error、tool/answer/report)
- [ ] audit 串流沿用既有 recursion / tool-error fallback
- [ ] API 掛掉不影響既有 CLI 發片(它是附屬)

---

## 8. 實作順序(建議)

1. `api/server.py` + 查詢 endpoint(`/stats` `/runs` `/runs/{id}`)——先讓總覽頁有真資料,最低風險。
2. `api/events.py` + `main.py` 插 emit(先只測 CLI 行為不變)。
3. `/run/stream` 接起來,前端即時跑片頁串上 stage/log。
4. `/audit/stream` 轉 `agent_langgraph.astream`。
5. CORS / 靜態服務 / 收尾。

> 先跟前端對齊 §3-3 / §4 / §5 的事件格式,兩邊才不會各寫各的。
