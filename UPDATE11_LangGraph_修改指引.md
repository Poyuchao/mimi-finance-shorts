# 🆕 UPDATE 11（把稽核 agent 移植到 LangGraph）— 修改指引

> **給開發 agent 的核心提醒:分階段做、每步單獨跑單獨驗,不要一次全寫完。遇到不確定停下來回報,不要自行猜測補完。**
>
> ⚠️ 本指引是「提案 + 建議決策」。★實作前請先確認 §1 與 §7。★
> 🔴 **LangGraph / langchain-mcp-adapters 的 API 更新快** —— 一律以「當前官方文件 + 實際 API」為準,不照本指引的概念碼硬套(這是 UPDATE 8 的教訓)。

---

## 0. 這次要做什麼 / 為什麼

把現有**手刻**的稽核 agent([agent.py](agent.py))**另外用 LangGraph 重做一版**,
學會並實作「orchestration 框架」,順勢補上手刻版缺的能力(session recovery、跨題記憶)。

**★ 定位:技能 / 面試驅動,不是產品需求。★**
手刻版([agent.py](agent.py))跑得好好的,這次是為了:
1. 取得「用過 agent harness / orchestration 框架」的真實經驗(對應 Binance 那類 JD)。
2. 幾乎免費拿到 **session recovery + 跨題對話記憶**(手刻版目前沒有 —— 問它「上一題問什麼」會失憶)。
3. 面試能 **對照 demo**「手刻 loop」vs「框架 graph」,講得出差異。

**★ 兩大安全原則 ★**
- **手刻 `agent.py` 完全不動** —— 新開 `agent_langgraph.py`,兩版並存。壞了就回去用手刻版。
- **MCP server(`mcp_server/finance_news_server.py`)完全不改** —— 用 `langchain-mcp-adapters` 載入既有工具。

---

## 1. 建議決策（★實作前先確認★）

| # | 項目 | 建議 | 待你確認 |
|---|------|------|---------|
| L1 | 新檔還是取代 | **新開 `agent_langgraph.py`,`agent.py` 不動**(兩版並存)| 接受嗎? |
| L2 | 用 prebuilt 還是手建 | **手建 `StateGraph`**(agent node + ToolNode + 條件邊)—— 學習/面試價值高,看得到手刻 loop 如何對應 | 還是要快的 `create_react_agent`? |
| L3 | MCP 怎麼接 | **`langchain-mcp-adapters`** 載入既有 MCP server 的工具(server 不改)| 接受嗎? |
| L4 | checkpointer | **`SqliteSaver`**(存檔到磁碟 → 真 session recovery,重開還在);獨立檔 `langgraph_checkpoints.sqlite`,不混 `mimi.db` | 還是先用記憶體版 `MemorySaver`? |
| L5 | 跨題記憶 | CLI 全程用**同一個 `thread_id`** → 自動記得前面對話;並加**訊息裁剪**(留最近 N 則)防 context 爆掉 | 留最近幾則?(建議 ~20)|
| L6 | 保留手刻版的巧思 | fail-open 工具錯誤、印出每次工具呼叫、達上限的 fallback 作答 —— 都要在 LangGraph 版重現 | 接受嗎? |
| L7 | 範圍 | **只移植稽核 agent**;發片 pipeline(`main.py`)不碰 | 接受嗎? |

---

## 2. 架構對照（手刻 → LangGraph）

```
手刻(agent.py):                   LangGraph(agent_langgraph.py):

for turn in range(5):              [START] → agent node ──(有 tool_calls?)──► tools node
  resp = LLM(messages, tools)                 ▲                                  │
  if 沒 tool_calls: return                     └──────────(迴圈回來)──────────────┘
  else: 執行工具 → 塞回 messages               │ 沒有 → [END] → 答案
                                               State(MessagesState):messages 用 add_messages 自動累積
                                               Checkpointer(SqliteSaver + thread_id):每步存檔 → 續跑 + 跨題記憶
```

| 手刻的東西 | LangGraph 對應 |
|---|---|
| `for turn` 迴圈 | graph 的 agent↔tools 循環 |
| `messages` list(手動 append)| `State` / `MessagesState`(reducer 自動累積)|
| 執行 tool_calls 那段 | `ToolNode`(內建)|
| `if not tool_calls: return` | `tools_condition`(內建條件邊)|
| `AGENT_MAX_ITERATIONS` | `recursion_limit`(超過丟 `GraphRecursionError`)|
| `_mcp_to_openai_tools` + `_call_tool_safe` | `langchain-mcp-adapters` 載入工具 |
| (手刻版沒有)| `Checkpointer` = session recovery + 跨題記憶 |

### 2.1 對話記憶存在哪?(checkpointer / thread_id)

```
記憶 = State(messages)→ 由 checkpointer 存 → 用 thread_id 當 key

① 執行當下:State 在 RAM 流動(同一般程式變數)
② 每步之後:checkpointer 把 State 快照存一份,標記 thread_id
③ 實體落地:SqliteSaver → 磁碟上的 langgraph_checkpoints.sqlite(重開還在)
            (MemorySaver → 只在 RAM,關掉就沒)

一次對話:同 thread_id → 開跑前讀回舊 messages → 累積 → 每步寫回 sqlite
         → 下次同 thread_id 又讀回 → 所以記得(重開也記得)
```

- **key 是 `thread_id`**:同 id = 同一段記憶;換 id = 開新對話(乾淨失憶)。
- **★ 跟 `mimi.db` 分開的兩個檔 ★**:
  - `mimi.db` = 產品資料(runs / candidates / 觀看數),pipeline 寫的
  - `langgraph_checkpoints.sqlite` = agent 對話狀態,checkpointer 寫的
  - 分開原因:職責/生命週期不同,不讓 agent 聊天記錄污染產品 DB。
- **存的是「完整 State + 執行到哪一步」** → 所以同時給你「跨題記憶」+「session recovery(斷點續跑)」。
- ⚠️ **存多少 ≠ LLM 看多少**:checkpointer 可留整段歷史;每輪丟給 LLM 的是裁剪後「最近 N 則」(L5)。裁剪省 token,儲存可留更多。

---

## 3. 依賴(先裝、先確認版本)

```
langgraph
langchain-openai
langchain-mcp-adapters
langgraph-checkpoint-sqlite     # SqliteSaver(持久化 checkpointer)
```
> 裝完先 `import` 一遍確認版本,並★查當前官方 API★(ReAct 範例 + MCP adapter 用法)。

---

## 4. 分階段實作（★每階段單獨驗,驗過才進下一步★）

### L11-1:裝依賴 + 用 adapter 載入既有 MCP 工具
- 裝 §3 套件。
- 寫一小段:用 `langchain-mcp-adapters` 指向既有 `mcp_server/finance_news_server.py`,載入工具。
- ✅ 驗證:印出載入的工具名,應看到 `fetch_finance_news / get_recent_selections / get_run_detail / get_video_stats`(與手刻版一致)。
- ⚠️ 這步最可能卡:**adapter 的 session/連線模型要照當前文件**(stdio 怎麼帶 command/args/cwd)。

### L11-2:最小 graph(先不要 checkpointer)
- `StateGraph(MessagesState)` + `agent` node(LLM.bind_tools)+ `ToolNode` + `START→agent`、`agent→(tools_condition)`、`tools→agent`。
- system prompt 放成 State 第一則訊息(沿用 `agent.py` 的 `SYSTEM_PROMPT`)。
- ✅ 驗證 單輪:問「最近選了哪些新聞」→ 呼叫 1 次工具就作答(行為同手刻版)。
- ✅ 驗證 多輪:問「這週選片有問題嗎」→ graph 自己循環多輪(agent↔tools)。

### L11-3:加 checkpointer + 跨題記憶(解手刻版的失憶問題)
- `compile(checkpointer=SqliteSaver(...))`;invoke 帶 `config={"configurable": {"thread_id": "..."}}`。
- CLI 全程用**同一個 thread_id**。
- 加**訊息裁剪**(留最近 N 則)防 context 無限長大。
- ✅ 驗證 記憶:先問「run 8 觀看多少」→ 再問「**那上一題我問什麼?**」→ 它答得出來(手刻版答不出)。
- ✅ 驗證 續跑:關掉重開、同 thread_id → 還記得(SqliteSaver 的持久化)。

### L11-4:重現手刻版的三個巧思
- **印出每次工具呼叫**(demo 用)→ 用 `graph.stream(...)` 觀察每步並印 `[工具] name(args)`。
- **fail-open 工具錯誤** → `ToolNode(..., handle_tool_errors=True)`(或自訂 handler),錯誤回成 ToolMessage 給 LLM,不 crash。
- **達上限 fallback** → 設 `recursion_limit`;接 `GraphRecursionError` → 用現有資訊作答並註記(對應手刻版行為)。
- ✅ 驗證:弄壞 MCP server → 不 crash、回報錯誤;問很繞的問題 → 達上限會優雅作答。

### L11-5:CLI 包裝 + 並存確認
- `python agent_langgraph.py` 跑一個 `input()` 迴圈(同 `agent.py` 的體驗)。
- ✅ 驗證:★`agent.py` 完全沒被改到、仍可獨立跑★(兩版並存)。
- ✅ 驗證:同一題分別丟兩版,答案方向一致(行為對齊)。

---

## 5. ✅ Review Checklist（逐項勾)

**前置**
- [ ] L11-1 裝好 `langgraph / langchain-openai / langchain-mcp-adapters / langgraph-checkpoint-sqlite`
- [ ] L11-1 ★已查當前官方 API(不照概念碼硬套)★
- [ ] L11-1 用 adapter 載入既有 MCP server,工具名與手刻版一致
- [ ] `mcp_server/finance_news_server.py` ★完全沒改★

**graph 本體**
- [ ] L11-2 `StateGraph(MessagesState)` 建好
- [ ] L11-2 `agent` node(`ChatOpenAI(config.AGENT_MODEL).bind_tools(tools)`)
- [ ] L11-2 `ToolNode` + `tools_condition` + 三條邊(START→agent、agent→條件、tools→agent)
- [ ] L11-2 system prompt 沿用 `agent.py` 的 `SYSTEM_PROMPT`
- [ ] L11-2 ✅ 單輪(1 次工具)
- [ ] L11-2 ✅ 多輪(自動循環)

**記憶 / 續跑**
- [ ] L11-3 `SqliteSaver` checkpointer(獨立檔,不混 mimi.db)
- [ ] L11-3 CLI 全程同一個 `thread_id`
- [ ] L11-3 訊息裁剪(留最近 N 則)防 context 爆
- [ ] L11-3 ✅ 記憶:答得出「上一題問什麼」
- [ ] L11-3 ✅ 續跑:重開仍記得

**手刻巧思重現**
- [ ] L11-4 印出每次工具呼叫(`graph.stream`)
- [ ] L11-4 fail-open 工具錯誤(`handle_tool_errors`)
- [ ] L11-4 達上限 fallback(`recursion_limit` + 接 `GraphRecursionError`)
- [ ] L11-4 ✅ 弄壞 MCP → 不 crash

**並存 / 收尾**
- [ ] L11-5 `agent_langgraph.py` CLI 可跑
- [ ] L11-5 ✅ `agent.py` 未被改、仍可獨立跑
- [ ] L11-5 ✅ 兩版同題答案方向一致
- [ ] `requirements.txt` 補上新依賴
- [ ] `.gitignore` 加 `langgraph_checkpoints.sqlite*`
- [ ] config:沿用 `AGENT_MODEL`;新增 `AGENT_RECURSION_LIMIT`、`AGENT_HISTORY_KEEP`(訊息裁剪)

---

## 6. ★ 卡關預告(提前避開)★

| 問題 | 對策 |
|------|------|
| **adapter 的 API 與概念碼不符** | ★一定先查當前文件★(UPDATE 8 的教訓);stdio 的 command/args/cwd 照文件帶 |
| **async** | LangGraph + MCP adapter 多為 async → 用 `ainvoke`/`astream`;CLI 的 `input()` 是同步 → 用 `asyncio.run` 包(同 agent.py 現況)|
| **checkpointer async 版** | 持久化 SqliteSaver 可能要用 async 變體;照文件 |
| **recursion_limit 換算** | 一輪 = agent+tools 兩步 → limit ≈ 2×最大輪數 + 緩衝 |
| **context 無限長大** | 跨題記憶一定要配訊息裁剪/摘要,否則 token 爆(ResumePilot 的「留最近 10 則」同理)|
| **工具錯誤讓 graph 中止** | `ToolNode(handle_tool_errors=True)` 把錯誤回成訊息給 LLM |
| **印工具呼叫** | 用 `stream` 看每步事件,別想在 node 裡硬塞 print |

---

## 7. 需要你拍板的

```
🔴 實作前確認:
  • L1 新檔 agent_langgraph.py、agent.py 不動 —— OK?
  • L2 手建 StateGraph(學習型) vs create_react_agent(快) —— 選哪個?
  • L4 checkpointer:SqliteSaver(持久) vs MemorySaver(記憶體) —— 選哪個?
  • L5 訊息裁剪留最近幾則(建議 ~20)?

🟠 開發中回報:
  • adapter 實際 API 與本指引概念碼的差異(預期會有)
  • async 整合的細節
```

---

## 8. 對應 JD（面試用）

```
• Agent Harness / orchestration framework:實際用過 LangGraph(對應 Pi Agent/AgentScope 的 "equivalent")
• session recovery:SqliteSaver checkpointer
• plan/execute loop:graph 的 agent↔tools 循環(未來可加 plan node)
• retrieval-grounded tool calling:ToolNode 經 adapter 呼叫 MCP、結果回 State
• Memory:checkpointer + thread_id 跨題記憶 + 訊息裁剪(context engineering)
• 能講「手刻 vs 框架」差異 —— 因為兩版都做過
```

> 📌 **核心原則:分階段、每步單獨驗、`agent.py` 與 MCP server 絕不動。**
> 成敗定義:LangGraph 版能跑、有跨題記憶、且與手刻版並存可對照 —— 不是「功能更多」。
