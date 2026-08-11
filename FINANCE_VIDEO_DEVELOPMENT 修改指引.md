# 🆕 UPDATE 9（選片品質稽核 Agent）— 修改指引

> **給開發 agent 的核心提醒:這是分階段專案,一步一步做、每步都能單獨跑單獨驗,不要一次全寫完。遇到不確定的地方停下來回報,不要自行猜測補完。**

---

## 0. 這次要做什麼

把 UPDATE 6 存進 DB 的「LLM 選片決策紀錄」，從**人工翻 DB** 變成**用自然語言詢問的 custom agent**。

**動機（真實痛點）**：UPDATE 6 第一筆真實紀錄就抓到「同一次選了力積電兩則」的問題，但那是使用者手動跑 `query_runs.py` 才發現的。不可能每天翻，也看不出跨天的趨勢。

**核心差異**：
- 現有 pipeline = **線性**，順序由 `main.py` 寫死
- 稽核 agent = **迴圈**，由 LLM 自己決定要呼叫哪些工具、呼叫幾次、何時停

```
使用者在終端機提問
      ↓
agent.py（自建 host）
  ├─ 把問題 + MCP 工具清單丟給 LLM
  ├─ LLM 回「我要呼叫 get_recent_selections(days=7)」
  ├─ 透過既有 mcp_client 執行 → 拿到結果
  ├─ 結果餵回 LLM → LLM 再判斷（可能再呼叫 get_run_detail）
  └─ LLM 說「我有答案了」→ 輸出結構化稽核報告
      ↓
終端機印出報告
```

**★ 這次不碰發片流程。** `main.py` 完全不改，agent 是獨立入口、純唯讀。

---

## 1. 已定案決策（不要自行更改，有疑問先問）

| # | 項目 | 結論 |
|---|------|------|
| A1 | 定位 | **獨立的維運工具**，不整合進 `main.py`；`python agent.py` 單獨執行 |
| A2 | 介面 | **終端機 CLI**（`input()` 迴圈）。★不做網頁 UI、不接 Claude Desktop★ |
| A3 | 讀寫 | **純唯讀**。agent 只查 DB / 抓新聞，不寫入、不改 prompt、不動發片 |
| A4 | LLM | **OpenAI `gpt-4o-mini`**（與現有一致，沿用 `llm_service` 的 key 設定）|
| A5 | 決策機制 | **OpenAI function calling**（`tools` 參數 + `tool_calls` 回傳）|
| A6 | 工具來源 | **一律透過既有 `mcp_client` 呼叫 MCP server**。★不准繞過 MCP 直接呼叫 repository★ |
| A7 | 迴圈上限 | **`AGENT_MAX_ITERATIONS = 5`**（防無限迴圈）；達上限就用現有資訊作答並註記 |
| A8 | 工具失敗 | **結構化回傳錯誤給 LLM**（`{"error": "..."}`），★不 raise、不中斷 agent★，讓 LLM 自己決定要不要換方式 |
| A9 | 輸出格式 | **結構化 JSON**（沿用審圖的分級概念：blocking / minor），再由 CLI 印成易讀格式 |
| A10 | 新增 MCP tool | `get_run_detail(run_id)` —— 查單次執行的完整候選 + 選中理由 |
| A11 | 新增 MCP resource | `runs://latest` —— ★展示 MCP 的 Resource primitive（不只有 tools）★ |
| A12 | 開關 | 無需開關（獨立檔案，不影響現有流程）|

---

## 2. 分階段實作（★每階段單獨驗，驗過才進下一步★）

### U9-1：補 MCP tool `get_run_detail`

**Step 1** — `db/repository.py` 新增查詢：

```python
def get_run_detail(session, run_id: int) -> dict | None:
    """取單次執行的完整資訊：候選清單 + 哪 3 則被選中 + 選片理由"""
    # 用既有 Run / Candidate models + relationship
    # 回傳 {run_id, created_at, candidates: [{title, link, selected, position, reason}]}
    # 找不到 → 回 None
```

**Step 2** — `mcp_server/finance_news_server.py` 加 tool：

```python
@app.tool()
def get_run_detail(run_id: int) -> dict:
    """查詢某一次執行的完整選片細節，包含當時的所有候選新聞、
    LLM 選中的三則、每則的選片理由與排序位置。
    當你需要深入了解某一次選片的判斷依據時使用。"""
```

> 🔴 **docstring 是 agent 的使用手冊**。LLM 完全靠它判斷「什麼時候該用這個工具」。
> 寫清楚「這個工具做什麼」+「什麼情況該用」，不要只寫參數說明。

**Step 3** — 沿用 UPDATE 8 的 `_jsonable()` 處理 datetime。

**✅ 驗證**：直接跑 server 端函式 → 給一個真實 run_id → 確認回傳完整且可 JSON 序列化。

---

### U9-2：補 MCP Resource `runs://latest`

```python
@app.resource("runs://latest")
def latest_run_summary() -> str:
    """最近一次執行的摘要：日期、候選數、選中的三則標題"""
```

> **為什麼要做**：MCP 有三個 primitives —— Tools（模型控制、有副作用的動作）、
> Resources（應用控制、唯讀資料）、Prompts（使用者控制的模板）。
> 只做 tools 是不完整的實作。

**✅ 驗證**：用 MCP Inspector 或 client 端 `list_resources()` 確認讀得到。

---

### U9-3：`agent.py` —— 決策迴圈（核心）

**檔案位置**：專案根目錄 `agent.py`

**結構**：

```
1. 啟動時：透過 mcp_client 取得工具清單（MCP discovery）
2. 把 MCP tool schema 轉成 OpenAI tools 格式
3. 進入對話迴圈：
   messages = [system_prompt, user_question]
   for i in range(AGENT_MAX_ITERATIONS):
       resp = openai.chat(messages, tools=tools)
       if resp.tool_calls:
           for call in resp.tool_calls:
               result = mcp_client.call_tool(call.name, call.args)   # 走 MCP
               messages.append(tool_result)
           continue                      # 回頭讓 LLM 再判斷
       else:
           return resp.content           # LLM 給答案了，結束
   # 迴圈用盡 → 用現有資訊作答並註記「達迭代上限」
```

**System prompt 要點**（★沿用專案既有的 prompt 經驗★）：

```
你是米米財經的選片品質稽核員。你可以呼叫工具查詢歷史選片紀錄。

稽核重點：
1. 主體重複 —— 同一次是否選了同一家公司/同一主體的多則新聞（違反題材分散）
2. 來源偏食 —— 三個來源（ETtoday/自由/風傳媒）是否嚴重失衡
3. 題材集中 —— 是否連續多天都選同類型（如都是盤勢、都是個股財報）
4. 理由品質 —— LLM 給的選片理由是否具體，還是流於空泛

★ 回答前的最終自我檢查（逐條確認後才輸出）★
- 我是否真的查了資料？還是在憑空推測？
- 我指出的每個問題，是否都能對應到具體的 run_id？
- 嚴重度分級是否正確？（blocking = 傷內容可信度；minor = 可接受的瑕疵）

輸出格式：JSON
{
  "period": "查詢區間",
  "runs_analyzed": 數量,
  "issues": [{"type","severity","run_id","detail","suggestion"}],
  "source_distribution": {...},
  "summary": "一句話總結"
}
```

> 🔴 **沿用 UPDATE 6 的關鍵經驗**：規則埋在條列清單裡 LLM 會忽略，
> 改成「回答前的自我檢查步驟」才有效。稽核 prompt 也要這樣寫。

**CLI 介面**：

```python
while True:
    q = input("\n問題> ").strip()
    if q in ("exit", "quit", ""):
        break
    run_agent(q)
```

> **★ Demo 用途：每次工具呼叫都要印出來 ★**
> ```
> [工具] get_recent_selections(days=7)
> [工具] get_run_detail(run_id=12)
> ```
> 這樣才看得出 agent 在做多步推理（面試 demo 的重點）。

**✅ 驗證（分兩階段）**：
- **單輪**：問「最近選了哪些新聞」→ 應只呼叫 1 次工具就作答
- **多輪**：問「這週選片品質有沒有問題」→ ★應先查 recent、發現異常後再查 detail，至少 2 輪★

---

### U9-4：config 與整合

```python
# config.py 新增
AGENT_MODEL = "gpt-4o-mini"
AGENT_MAX_ITERATIONS = 5
AGENT_AUDIT_DEFAULT_DAYS = 7
```

`requirements.txt` 不需新增（openai / mcp 都已有）。

---

## 3. ★ 卡關預告（照 UPDATE 8 的經驗提前避開）★

| 問題 | 對策 |
|------|------|
| **MCP server 的 stdout 汙染** | 已知問題，server 端 log 一律導 `stderr`（UPDATE 8 已處理，別破壞它） |
| **子行程 python / cwd** | 沿用 `mcp_client` 現有的 `sys.executable` + `cwd=_PROJECT_ROOT`，別改 |
| **MCP schema → OpenAI tools 格式不一致** | MCP 的 `inputSchema` 與 OpenAI 的 `parameters` 欄位名不同，需轉換函式。★先寫一個最小測試確認格式對得上★ |
| **tool_call_id 對應** | OpenAI 要求每個 `tool_calls` 的回覆必須帶對應的 `tool_call_id`，漏了會 400 |
| **一輪多個 tool_calls** | LLM 可能一次要求呼叫多個工具，要 for 迴圈全部執行完再一起回覆 |
| **LLM 不呼叫工具直接編答案** | system prompt 要明講「必須先查詢真實資料，不可推測」；驗證時檢查有沒有真的呼叫 |
| **無限迴圈** | `AGENT_MAX_ITERATIONS` 硬上限，且每輪印出當前輪數 |
| **JSON 解析失敗** | LLM 回的 JSON 可能包 markdown code fence，需 strip 後再 parse；失敗就印原文，別 crash |

---

## 4. Checklist

**U9-1 MCP tool**
- [ ] `repository.get_run_detail(session, run_id)` 完成
- [ ] `finance_news_server.py` 加 `@app.tool() get_run_detail`
- [ ] docstring 寫清楚「做什麼 + 何時該用」
- [ ] datetime 可 JSON 序列化
- [ ] ✅ 驗證：真實 run_id 回傳正確

**U9-2 MCP resource**
- [ ] `@app.resource("runs://latest")` 完成
- [ ] ✅ 驗證：client 端讀得到

**U9-3 agent.py**
- [ ] MCP 工具清單 discovery + 轉 OpenAI tools 格式
- [ ] 決策迴圈（含 `AGENT_MAX_ITERATIONS` 上限）
- [ ] 工具失敗 → 結構化錯誤回傳，不中斷
- [ ] system prompt 含「回答前的自我檢查」
- [ ] 每次工具呼叫印出（demo 用）
- [ ] CLI `input()` 迴圈
- [ ] ✅ 驗證：單輪問題（1 次工具呼叫）
- [ ] ✅ 驗證：★多輪問題（≥2 次工具呼叫，展現多步推理）★
- [ ] ✅ 驗證：弄壞 MCP server → agent 不 crash，回報錯誤

**U9-4 config**
- [ ] `AGENT_MODEL` / `AGENT_MAX_ITERATIONS` / `AGENT_AUDIT_DEFAULT_DAYS`
- [ ] ✅ 驗證：`main.py` 完全不受影響，發片流程正常

---

## 5. 需要使用者確認的

```
🟠 開發中回報:
  • system prompt 的稽核重點要不要調整（先做一版，看輸出再調）
  • 輸出的 JSON 欄位是否夠用
  • AGENT_MAX_ITERATIONS = 5 是否足夠（看實際多步推理需要幾輪）
```

---

## 6. 未來擴充（本階段不做）

```
• 把「生圖 / 審圖 / TTS」也暴露成 MCP tools → 讓 agent 調度整條產製線
• 稽核 agent 定期自動執行（排程）+ 有問題主動通知
• 讓 agent 直接建議 select prompt 的具體修改內容
• 審稿 agent（口播稿是否偏離原新聞、標題是否誇大）
• MCP over HTTP transport（跨機 / 多 agent 共用）
```

---

> 📌 **核心原則再強調：分階段、每步單獨驗、絕不影響現有發片流程。**
> 這次的成敗定義是「agent 能自己決定呼叫哪些 MCP 工具、做出多步推理、產出有用的稽核報告」，
> 不是「功能多完整」。先讓一個問題跑通兩輪工具呼叫，再談其他。
