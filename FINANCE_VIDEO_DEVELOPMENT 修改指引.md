# FINANCE_VIDEO_DEVELOPMENT — 修改指引 UPDATE 8:Finance News MCP Server（工具能力以 MCP 暴露給選片 agent）

> 搭配主規格 **FINANCE_VIDEO_DEVELOPMENT.md**,接續 UPDATE 1~7(米米、節目化、YouTube 上傳、AI 生圖、AI 審圖、DB 記錄、GCP 部署)。
>
> 現狀:`main.py` 直接呼叫 `fetch_rss()` / `select_news()` / `repository` 抓新聞與存取 DB。這份把**新聞抓取與歷史選片查詢**封裝成一個 **MCP(Model Context Protocol)server**,以標準化協議把「工具能力」暴露給 LLM 選片 agent,取代硬編碼整合。
>
> **給開發 agent:這次引入 MCP,把既有的抓取/查詢邏輯「包成 MCP server 的 tools」,並讓選片改成「agent 透過 MCP 呼叫工具」。重點是『不重寫功能,而是用 MCP 標準協議暴露既有能力』。這是進階架構升級,務必分階段、每步單獨驗、不確定就停下來問。⚠️ 保留原本的直接呼叫路徑當 fallback(MCP 掛掉不能讓發片停擺)。**

---

## U8-0. 這次在做什麼 + 為什麼

```
現在:main.py 硬編碼呼叫 fetch_rss()、select_news()、repository.get_recent()
  → agent/LLM 與「資料來源」是寫死綁定的

改成:把這些能力包成 MCP server 的 tools:
  • fetch_finance_news → 抓 + 篩 + 收斂候選池
  • get_recent_selections → 查 DB 過去發過的新聞(歷史選片)
  → 選片 agent「透過 MCP 標準協議」呼叫這些工具拿資料
  → 不再硬編碼整合

為什麼(架構價值,也是履歷/JD 對齊點):
  ✅ Tool/capability exposure to LLM-based agents(工具暴露給 agent)
  ✅ Structured context sharing between models, tools, and agents
  ✅ Interoperability without hard-coded integrations(去除硬編碼整合)
  → agent 與資料源解耦,之後換資料源/加工具只改 MCP server
```

### U8-0.1 已定案決策（不要自行更改）

| # | 項目 | 結論 |
|---|------|------|
| 1 | 協議 | **MCP (Model Context Protocol)**,用官方 Python SDK（`mcp`）|
| 2 | server 型態 | 本地 **stdio** MCP server（同機、子行程,不需對外網路）|
| 3 | 暴露的 tools | `fetch_finance_news`、`get_recent_selections`（先兩個核心）|
| 4 | 消費端 | 選片 agent 透過 MCP client 呼叫 tools → 拿到資料再做 LLM 選片 |
| 5 | 底層邏輯 | **不重寫**:MCP tool 內部就是呼叫既有 `fetch_rss`/`parse_filter`/`select_news`/`repository` |
| 6 | fallback | ⚠️ **MCP 連線/呼叫失敗 → 退回原本的直接呼叫**（發片不可因 MCP 中斷）|
| 7 | 開關 | `USE_MCP`（config,False = 走原本直接呼叫,等同 UPDATE 7 現狀）|
| 8 | 邊界 | 這次**只把「抓新聞 + 查歷史」上 MCP**;生圖/審圖/上傳暫不上 MCP（之後可擴充）|

---

## U8-1. 新增 MCP Server（`mcp_server/finance_news_server.py`）

```
用 MCP Python SDK 建一個 stdio server,暴露兩個 tool。

概念結構(以 MCP SDK 的 server 寫法):

  from mcp.server import Server
  from mcp.server.stdio import stdio_server
  import mcp.types as types

  app = Server("finance-news")

  @app.list_tools()
  async def list_tools():
      return [
          types.Tool(
              name="fetch_finance_news",
              description="抓取三來源財經 RSS,篩股市,收斂成候選 ~10 則",
              inputSchema={
                  "type": "object",
                  "properties": {
                      "pool_size": {"type": "integer", "default": 10}
                  },
              },
          ),
          types.Tool(
              name="get_recent_selections",
              description="查詢過去 N 天已選用/發布過的新聞(標題+連結)",
              inputSchema={
                  "type": "object",
                  "properties": {
                      "days": {"type": "integer", "default": 7}
                  },
              },
          ),
      ]

  @app.call_tool()
  async def call_tool(name, arguments):
      if name == "fetch_finance_news":
          # ★ 內部呼叫既有邏輯,不重寫 ★
          entries = fetch_rss()
          stock = parse_filter(entries)
          candidates = select_news(stock, pool=arguments.get("pool_size", 10))
          return [types.TextContent(type="text", text=json.dumps(candidates, ensure_ascii=False))]
      if name == "get_recent_selections":
          session = get_session()
          links = repository.get_recent_selections(session, days=arguments.get("days", 7))
          return [types.TextContent(type="text", text=json.dumps(links, ensure_ascii=False))]

  async def main():
      async with stdio_server() as (r, w):
          await app.run(r, w, app.create_initialization_options())
```

```
⚠️ MCP SDK 的實際 API(class 名、裝飾器、types)可能與此概念碼有出入,
   且版本更新快 → agent 依「當前安裝的 mcp 套件官方文件/範例」實作,
   不確定就回報,不要照這段概念碼硬套。
⚠️ candidates 要能 JSON 序列化(datetime 轉字串)。
```

### U8-1.1 需要 repository 補一個查詢（若 UPDATE 6 沒有）

```
get_recent_selections 需要一個「查過去 N 天 selected 新聞」的方法:

  # db/repository.py 補
  def get_recent_selections(session, days: int):
      cutoff = date.today() - timedelta(days=days)
      rows = (session.query(Candidate.title, Candidate.link)
                     .join(Run)
                     .filter(Run.run_date >= cutoff, Candidate.selected == True)
                     .all())
      return [{"title": t, "link": l} for t, l in rows]

→ UPDATE 6 記錄了 selected → 這裡查得到
→ 目前 pipeline「不強制去重」,但這個查詢讓 agent「看得到歷史」
  (agent 可自行參考「最近發過什麼」來選片,或未來做去重)
```

---

## U8-2. MCP Client:選片改成透過 MCP 拿資料（`mcp_client.py`）

```
選片 agent 端:啟動 MCP server(子行程)→ 呼叫 tools → 拿資料。

概念:
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client

  async def fetch_candidates_via_mcp(pool_size=10, dedup_days=7):
      params = StdioServerParameters(command="python",
                                     args=["mcp_server/finance_news_server.py"])
      async with stdio_client(params) as (r, w):
          async with ClientSession(r, w) as session:
              await session.initialize()
              # 呼叫工具 1:拿候選新聞
              res = await session.call_tool("fetch_finance_news",
                                            {"pool_size": pool_size})
              candidates = json.loads(res.content[0].text)
              # 呼叫工具 2:拿歷史選片(給 agent 參考)
              rec = await session.call_tool("get_recent_selections",
                                            {"days": dedup_days})
              recent = json.loads(rec.content[0].text)
              return candidates, recent

→ 回傳 candidates(候選池)+ recent(歷史)給選片 agent
→ 選片 agent 拿這些做 LLM 選片(select_top_news)
→ ★ 這就是「agent 透過 MCP 標準協議取得工具能力」★
```

```
⚠️ 同上:MCP client 的實際 API 依當前 SDK 文件。
⚠️ async:MCP 是 async,main.py 呼叫處要用 asyncio.run() 包。
```

---

## U8-3. 整合進 `main.py`（加 USE_MCP 分支 + fallback）

```
現有:
  entries = fetch_rss()
  stock_news = parse_filter(entries)
  candidates = select_news(stock_news, pool=10)
  picked = llm_service.select_top_news(candidates, n=3)

改成(MCP 分支 + fallback):
  if config.USE_MCP:
      try:
          candidates, recent = asyncio.run(
              mcp_client.fetch_candidates_via_mcp(pool_size=config.NEWS_POOL,
                                                  dedup_days=config.DEDUP_DAYS))
      except Exception as e:
          log.warning(f"MCP 取得失敗,fallback 直接呼叫: {e}")
          candidates = select_news(parse_filter(fetch_rss()), pool=config.NEWS_POOL)
          recent = []
  else:
      candidates = select_news(parse_filter(fetch_rss()), pool=config.NEWS_POOL)
      recent = []

  picked = llm_service.select_top_news(candidates, n=config.NEWS_COUNT)
  # (可選)把 recent 傳進 select_top_news 的 prompt,讓 agent 參考「最近發過的」

→ ★ MCP 失敗 → 退回原本直接呼叫 → 發片不中斷 ★
→ USE_MCP=False → 完全等同 UPDATE 7 現狀
```

---

## U8-4. `config.py` 新增

```python
# 🆕 UPDATE 8:MCP
USE_MCP    = True      # False = 走原本直接呼叫(等同 UPDATE 7)
DEDUP_DAYS = 7         # get_recent_selections 查幾天(給 agent 參考歷史)
MCP_SERVER_CMD = ["python", "mcp_server/finance_news_server.py"]
```

---

## U8-5. requirements

```
新增:
  mcp            # MCP Python SDK(官方)

→ pip install mcp
→ ⚠️ 確認版本 + 官方文件(SDK 更新快)
```

---

## U8-6. ⚠️ 部署考量（GCP / UPDATE 7 已部署的話）

```
MCP server 是「本地 stdio 子行程」→ 跟主程式同一個容器一起跑:
  • Dockerfile 不用特別改(mcp_server/ 已在 code 內,一起打包)
  • Cloud Run Job 執行 main.py → main 內部啟動 MCP server 子行程 → 同容器
  • ★ 不需要「另外部署一個 MCP 服務」★(stdio 同機即可)

→ 對部署影響小(不是獨立網路服務)
→ 若之後要「跨機/對外 MCP」再改 HTTP transport(這次不做)
```

---

## U8-7. 開發順序（分階段,每步單獨驗）

```
階段 U8-1:MCP server 單獨測
  → 寫 finance_news_server.py(兩個 tool)
  → 用 MCP 官方的 inspector / 簡單 client 測「list_tools + call_tool」
  ✅ 驗證:能列出兩個 tool、呼叫 fetch_finance_news 回候選池、
        get_recent_selections 回歷史(先塞假 DB 資料測)
  → server 單獨會動,才接 client

階段 U8-2:MCP client 單獨測
  → mcp_client.fetch_candidates_via_mcp()
  ✅ 驗證:client 啟動 server 子行程 → 拿到 candidates + recent

階段 U8-3:整合 main + fallback
  → USE_MCP 分支 + try/except fallback
  ✅ 驗證:USE_MCP=True 正常跑完整 pipeline(透過 MCP 拿新聞)
  ✅ 驗證:★ 故意讓 MCP 掛掉(改壞 server 路徑)→ fallback 直接呼叫,發片不中斷 ★
  ✅ 驗證:USE_MCP=False → 完全等同 UPDATE 7

階段 U8-4:（可選）歷史參考進選片
  → 把 recent 傳進 select_top_news 的 prompt
  ✅ 驗證:agent 選片時「看得到最近發過的」(prompt 有帶入)
```

---

## U8-8. 修改 Checklist

- [ ] U8-1:mcp_server/finance_news_server.py(list_tools + call_tool)
- [ ] U8-1:兩個 tool(fetch_finance_news / get_recent_selections)內部呼叫既有邏輯
- [ ] U8-1:repository.get_recent_selections(若 UPDATE 6 沒有,補上)
- [ ] U8-1:candidates/datetime 可 JSON 序列化
- [ ] U8-2:mcp_client.py(啟動 server + call_tool + 解析)
- [ ] U8-3:main.py USE_MCP 分支 + ★ MCP 失敗 fallback 直接呼叫 ★
- [ ] U8-4:config(USE_MCP / DEDUP_DAYS / MCP_SERVER_CMD)
- [ ] U8-5:requirements 加 mcp
- [ ] 分階段驗證(server→client→整合→fallback)

### 卡關立刻停手回報
- [ ] MCP SDK 的 API(class/裝飾器/types)與概念碼不符 → 依當前官方文件,回報
- [ ] async / asyncio 整合到同步的 main.py 有問題
- [ ] MCP server 子行程啟動失敗 / stdio 溝通問題
- [ ] JSON 序列化(datetime、特殊字元)
- [ ] 部署後容器內子行程行為異常

---

## U8-9. 之後可擴充（本次不做）

```
• 更多 tool 上 MCP:生圖、審圖、TTS 也可暴露成 MCP tools
  → 讓「內容生成 agent」透過 MCP 調度整條產製
• HTTP transport:若要「跨機/多 agent 共用」→ 改 MCP over HTTP
• 與 LangGraph 審閱結合:審閱 agent 透過 MCP 呼叫審查工具
  → Agent(LangGraph)+ 工具(MCP)= 完整 agent 架構
```

---

> 📌 **這次:把「抓新聞 + 查歷史選片」封裝成 MCP server,以標準協議把工具能力暴露給選片 agent,取代硬編碼整合。** 重點是「不重寫功能,用 MCP 暴露既有能力」。stdio 本地 server(同容器子行程,部署影響小)。⚠️ MCP 失敗必須 fallback 回直接呼叫,USE_MCP 開關可退回現狀——發片穩定性優先於架構潮度。分階段:server→client→整合→驗 fallback。MCP SDK 更新快,依當前官方文件實作,不確定就停下來問,別照概念碼硬套。目標:讓米米財經的 agent 與資料源透過 MCP 解耦,對齊「工具暴露 / 結構化 context 共享 / 無硬編碼整合」的架構。