# 工程問題記錄 / Engineering Problem Log

> 記錄本專案(米米財經)開發過程中遇到的**非顯而易見**的問題、除錯過程、根因與解法。
> 用途:面試時的具體案例庫(STAR:Situation / Task / Action / Result)。
>
> **收錄標準**:值得講的問題,不是「打錯字」那種。通常符合其中一項 ——
> ① 症狀與根因距離很遠 ② 靠推理而非猜測定位 ③ 修完帶出可複用的設計原則 ④ 揭露架構層級的缺陷。
>
> A log of non-obvious engineering problems from this project, with the debugging process,
> root cause, and fix. Purpose: a case library of concrete examples for interviews.
>
> **本檔分兩部分**:
> - **Part A — 問題記錄**:實際踩到的 bug + 除錯推理(STAR 案例)。
> - **Part B — 面試談資 / Talking Points**:概念性的講法與比喻,被問到時能順口說出的版本(含英文)。

---

## Part A 索引 / Problem Index

| # | 問題 / Problem | 關鍵字 / Tags |
|---|---|---|
| [001](#001) | MCP 序列化邊界造成 DB 無聲漏記 3 天<br>Silent data loss for 3 days at the MCP serialization boundary | `MCP` `serialization` `silent-failure` `observability` `fault-isolation` |
| [002](#002) | agent 把「即時候選」當成「已選中」並捏造理由<br>Agent reported a live *candidate* as *selected* and fabricated a reason | `agent` `hallucination` `tool-confusion` `prompt-engineering` `failure-modes` |

## Part B 索引 / Talking Points Index

| # | 主題 / Topic | 關鍵字 / Tags |
|---|---|---|
| [T1](#T1) | MCP 是什麼 + config 綁 client 不綁 tool<br>What MCP is; config is per-client, not per-tool | `MCP` `interoperability` `no-hard-coded-integration` |
| [T2](#T2) | 本機版 → 企業級 的對照(stdio → HTTP)<br>Local build → enterprise hardening | `transport` `registry` `auth` `gateway` `observability` |
| [T3](#T3) | workflow vs agent 的分水嶺(為什麼要決策迴圈)<br>Workflow vs agent; why the decision loop | `agent` `multi-step-reasoning` `guardrails` |

---

<a id="001"></a>
## 001 — 容錯做對了,可觀測性做錯了:MCP 序列化邊界的無聲資料遺失

**日期**:2026-07-24 · **嚴重度**:中(不影響產出,但遺失稽核資料)· **定位耗時**:約 10 分鐘

---

### 🇹🇼 中文版

#### 情境

專案是一條每日自動發布財經短影片的 pipeline。其中一個附屬功能是把每次執行的
「候選新聞 ~10 則 + LLM 選中的 3 則 + 選片理由」寫進 SQLite,用來**事後稽核 LLM 的選片品質**
—— 因為選片是整條 pipeline 唯一的黑箱,影片產不出來看得見,但「選錯新聞」不會有任何異常。

前一週剛完成一次改版:把「抓新聞 / 查歷史選片」用 **Model Context Protocol (MCP)** 包成標準化 tools,
讓 pipeline 和 Claude Desktop 兩個完全不同的 client 都能呼叫同一份 server。

#### 問題

使用者回報:「7/24 有上片,但資料庫查不到那次的選片記錄。」

影片確實產出了、也上傳到 YouTube 了。看起來一切正常。

#### 發現過程(推理路徑)

比對檔案時間戳,先把問題範圍縮小:

```
output/final.mp4   7/24 14:49   ← 影片確實產出
output_llm.json    7/24 14:44   ← LLM 有跑
mimi.db            7/21 13:46   ← DB 從三天前就沒被寫過
```

→ 結論:**pipeline 跑完了,但寫 DB 那一步失敗**。而且不是 7/24 單一事件,是 7/21 之後就一直在失敗。

第一個假設是「有第二個 mimi.db」—— 因為 MCP server 是被當**子行程**啟動的,
如果工作目錄不對,`sqlite:///mimi.db` 這種相對路徑會在別的地方另外建一個檔。
`find . -name "*.db"` 掃過,只有一個,**假設排除**。

第二個假設:資料在跨越 MCP 邊界時型別變了。查了兩邊的合約:

```python
# MCP server —— 為了 JSON 序列化,必須轉字串
"published": pub.isoformat() if isinstance(pub, datetime) else None

# DB model —— 欄位型別是 DateTime
published = Column(DateTime, nullable=True)
```

寫一個最小重現(不跑整條 pipeline,直接餵一筆字串進 `save_run`)確認:

```
StatementError: (builtins.TypeError)
SQLite DateTime type only accepts Python datetime and date objects as input.
```

#### 根因

**JSON 沒有 datetime 型別。** 跨越 MCP 邊界時,`datetime` 必須降級成字串;
但接收端直接把這個字串丟進 `DateTime` 欄位,SQLAlchemy 在 insert 時拋錯,整筆記錄失敗。

這是典型的**序列化邊界問題** —— 型別在跨越行程邊界時「單向損失」,而沒有人負責還原。

#### 為什麼三天沒人發現(真正的問題)

寫 DB 這段是**刻意**包在 `try/except` 裡的,設計原則是「**記錄是附屬功能,寫失敗絕不能拖垮發片**」。
這個原則本身是對的 —— 影片確實照常產出、照常上傳,使用者完全沒受影響。

**但當時的處理只印了一行 `logger.warning`**,淹沒在 pipeline 幾百行的輸出裡。

於是形成最糟的組合:**系統成功地隱藏了自己的失敗**。

> 💡 **核心教訓:容錯(fault tolerance)不等於靜音(silence)。**
> 「降級運行」和「假裝沒事」是兩回事。任何被吞掉的例外,都必須在**輸出的顯著位置**留下痕跡,
> 明確告訴使用者「這次少了什麼」。

#### 解法(兩處,缺一不可)

**1. 在 client 邊界還原型別** —— 而不是改 server

server 端**必須**維持字串(JSON 的限制,而且 Claude Desktop 這個 client 只需要字串)。
所以轉換責任放在「進入本系統」的那個邊界上,對其他 client 零影響:

```python
def _restore_datetimes(candidates: list[dict]) -> list[dict]:
    for c in candidates:
        pub = c.get("published")
        if isinstance(pub, str):
            try:
                c["published"] = datetime.fromisoformat(pub)
            except ValueError:
                c["published"] = None   # 格式怪就當沒有,不因記錄欄位擋下發片
    return candidates
```

注意 `except ValueError` 的處置:**降級成 None,而不是拋錯**。
一個稽核用的欄位,不該有能力擋下整支影片的發布。

**2. 讓失敗「叫得夠大聲」** —— 保留容錯,但拿掉靜音

```python
except Exception as exc:
    logger.exception("寫入 DB 失敗:%s", exc)      # warning → exception(留完整 traceback)
    print(f"\n{'!' * 60}")
    print(f"  ⚠️ 寫入 DB 失敗,這次執行沒有留下選片記錄:{exc}")
    print("     影片不受影響(已產出/已上傳),但 query_runs.py 查不到這次。")
    print(f"{'!' * 60}")
```

#### 結果

- 修復後實測:`published` 型別為 `datetime`,`save_run` 正常寫入(驗證資料已 rollback,不污染 DB)。
- 7/22–7/24 的候選池**無法救回** —— RSS 是即時的,當下沒存就永遠沒了。
  這也正是「稽核資料要即時寫入」的價值所在。
- 帶出一條可複用的設計原則,已回寫進專案文件。

#### 如果重來一次,怎麼更早發現

1. **跨行程邊界要有型別測試** —— MCP 整合時只驗證了「拿得到資料」(功能面),
   沒驗證「拿到的型別能不能被下游消費」。契約測試應該涵蓋型別,不只是有無。
2. **關鍵不變量要有斷言** —— 例如「每次成功執行都必須產生一筆 run 記錄」,
   跑完自我檢查一次,不符就大聲報。
3. **swallow 例外時,一律附帶「使用者可見的後果描述」** —— 不是印 exception,是印「你少了什麼」。

#### 對應 JD 能力

`Model Context Protocol (MCP) 整合` · `failure modes 推理` · `Reliability and resiliency` ·
`Observability and maintainability` · `Data modeling / persistence` · `Owning software end-to-end`

---

### 🇬🇧 English Version

#### Situation

The project is a daily pipeline that automatically produces and publishes short financial-news videos.
One auxiliary feature logs each run — the ~10 candidate news items, the 3 the LLM selected, and its
stated reasoning — into SQLite, so that **LLM selection quality can be audited after the fact**.
This matters because selection is the only black box in the pipeline: if video rendering breaks you
see it immediately, but if the LLM picks the *wrong* news, nothing looks abnormal.

The week prior, I had refactored news fetching and selection-history lookup into standardized tools
exposed over the **Model Context Protocol (MCP)**, so that two entirely different clients — the
pipeline itself and Claude Desktop — could call the same server without duplicated integration code.

#### Problem

User report: "I published a video on 7/24, but there's no record of that run in the database."

The video had in fact been produced and uploaded to YouTube. Everything appeared to work.

#### Investigation

I started by comparing file timestamps to bound the problem:

```
output/final.mp4   7/24 14:49   ← video was produced
output_llm.json    7/24 14:44   ← the LLM did run
mimi.db            7/21 13:46   ← DB hadn't been written in 3 days
```

→ The pipeline completed but the DB write step failed — and not just once; it had been failing
silently since 7/21.

**First hypothesis: a second `mimi.db`.** The MCP server runs as a *subprocess*, so if its working
directory were wrong, a relative path like `sqlite:///mimi.db` would silently create a second file
elsewhere. A `find . -name "*.db"` returned exactly one file — hypothesis eliminated.

**Second hypothesis: the type changed while crossing the MCP boundary.** I checked both sides of
the contract:

```python
# MCP server — must stringify for JSON serialization
"published": pub.isoformat() if isinstance(pub, datetime) else None

# DB model — the column is a DateTime
published = Column(DateTime, nullable=True)
```

A minimal reproduction (feeding one string row straight into `save_run`, without running the full
pipeline) confirmed it:

```
StatementError: (builtins.TypeError)
SQLite DateTime type only accepts Python datetime and date objects as input.
```

#### Root Cause

**JSON has no datetime type.** Crossing the MCP boundary forces `datetime` to degrade into a string,
but the receiving side passed that string straight into a `DateTime` column. SQLAlchemy raised on
insert, and the entire record was lost.

This is a classic **serialization-boundary defect**: a type is lossily downgraded when crossing a
process boundary, and no one owns restoring it.

#### Why It Went Unnoticed for Three Days (the real problem)

The DB write was **deliberately** wrapped in `try/except`, under the principle that
**logging is an auxiliary feature and must never block publishing**. That principle is correct —
the videos shipped normally and the user was never impacted.

**But the handler only emitted a single `logger.warning`**, buried in hundreds of lines of
pipeline output.

The result was the worst possible combination: **the system successfully concealed its own failure.**

> 💡 **Key lesson: fault tolerance is not the same as silence.**
> "Degrade gracefully" and "pretend nothing happened" are different behaviors. Any swallowed
> exception must leave a mark in a *prominent* position in the output, stating explicitly what
> the user just lost.

#### Fix (two parts — neither is sufficient alone)

**1. Restore the type at the client boundary** — not on the server.

The server **must** keep emitting strings: it's a JSON constraint, and the other client
(Claude Desktop) only needs strings anyway. So the conversion belongs at the boundary where data
*enters this system*, leaving every other consumer unaffected:

```python
def _restore_datetimes(candidates: list[dict]) -> list[dict]:
    for c in candidates:
        pub = c.get("published")
        if isinstance(pub, str):
            try:
                c["published"] = datetime.fromisoformat(pub)
            except ValueError:
                c["published"] = None   # bad format → drop the field, never block publishing
    return candidates
```

Note the `except ValueError` behavior: it **degrades to None rather than raising**. An
audit-only field should never have the power to block a video from shipping.

**2. Make the failure loud** — keep the fault tolerance, remove the silence.

```python
except Exception as exc:
    logger.exception("DB write failed: %s", exc)   # warning → exception (full traceback)
    print(f"\n{'!' * 60}")
    print(f"  ⚠️ DB write failed — no selection record for this run: {exc}")
    print("     The video is unaffected (produced and uploaded), but query_runs.py won't show it.")
    print(f"{'!' * 60}")
```

#### Result

- Verified after the fix: `published` arrives as a `datetime` and `save_run` succeeds
  (verification data rolled back so the DB stays clean).
- The 7/22–7/24 candidate pools are **unrecoverable** — RSS is a live feed; what wasn't captured
  at the time is gone. Which is precisely the point of writing audit data synchronously.
- Produced a reusable design principle, now written back into the project docs.

#### What Would Have Caught It Earlier

1. **Type-level tests at process boundaries.** The MCP integration was verified functionally
   ("does data come back?") but not structurally ("can downstream *consume* what came back?").
   Contract tests should cover types, not just presence.
2. **Assertions on key invariants** — e.g. "every successful run must produce exactly one run
   record." Self-check at the end of a run and fail loudly if violated.
3. **Whenever an exception is swallowed, always print the user-visible consequence** — not the
   exception text, but a plain statement of *what you no longer have*.

#### Mapped JD Competencies

`Model Context Protocol (MCP) integration` · `Reasoning about failure modes` ·
`Reliability and resiliency` · `Observability and maintainability` ·
`Data modeling and persistence` · `Owning software end-to-end`

---

<a id="002"></a>
## 002 — agent 把「即時候選」當成「已選中」,還捏造了選片理由

**日期**:2026-07-27 · **嚴重度**:中(agent 給出看似可信、實為錯誤的答案)· **定位耗時**:約 10 分鐘

### 🇹🇼 中文版

#### 情境
選片品質稽核 agent(function calling 決策迴圈)有三個 MCP 工具:兩個查 DB(`get_recent_selections`、
`get_run_detail`),一個抓即時 RSS(`fetch_finance_news`)。使用者用它問「選片」相關問題。

#### 問題
使用者發現:agent 報告某則新聞「被選上」,還附了選片理由 —— 但那則**根本沒進今天的影片**。

#### 發現過程(推理路徑)
不猜,直接查資料:
1. 用連結和標題去 DB 撈這則 → **0 筆**。它不在 DB 裡,連候選都不是。
2. 但使用者看到的版本**帶著「選片理由」** → 矛盾點出現:`fetch_finance_news` 回的候選
   **根本沒有 reason 欄位**,理由只存在於 DB 的 `select_reason`。→ 這個理由是**被捏造的**。
3. 查今天實際那次執行(run 10)的候選池 → 這則也不在。
4. 立刻抓一次**即時** RSS → 這則**排第 1**。真相大白:它是「現在」才出現的即時候選,
   run 10 早上跑時還沒有這則。

#### 根因
agent 呼叫了 `fetch_finance_news`(即時 RSS)來回答「選了什麼」,把**候選**當成**選中**,
又因為候選沒有理由,LLM 就**自己生了一個看似合理的理由**。三個概念被混為一談:
```
候選(可能被選) ≠ 選中(LLM 真的挑了,有理由) ≠ 發布(進了影片)
```
更陰險的是 `fetch_finance_news` 是**非確定性**的(即時、隨時變),它反映「現在」,
而不是「早上那次實際選了什麼」——概念上根本答錯了工具。

#### 為什麼是我的 prompt 沒寫好
system prompt 把 `fetch_finance_news` 描述成「抓今天的候選池」,但**沒警告**「這是候選、不是選中,
且是即時的」。自我檢查也只問「有沒有查資料」,沒問「我引用的是候選還是選中」。
→ LLM 沒有被給予區分這三者的依據。

#### 解法(工具 + prompt 一起,缺一不可)
1. **補強 DB 工具**:`get_recent_selections` 加回 `run_id / source / position / select_reason`
   → 讓「今天選了什麼 + 理由」一個工具一次答完,不必再拼第二個工具。
2. **工具 docstring 標明身分**(docstring 就是 agent 的使用手冊):
   - `get_recent_selections` →「【選片事實·來自 DB】問『選了什麼』用這個」
   - `fetch_finance_news` →「【即時候選·非 DB】★沒有 selected、沒有理由★,絕不可用來回答『選了什麼』」
3. **system prompt** 開頭放「候選 vs 選中 vs 發布」三概念定義 + 自我檢查新增一條
   「我講的『選了』是不是真的來自 DB 工具的 select_reason?」

> 💡 **教訓**:給 agent 多個功能相近的工具時,它會挑錯。防呆要三層 ——
> ① 工具本身少而清楚 ② docstring 講清楚「何時用/不該用」 ③ prompt 明確定義易混淆的概念。
> 光改 prompt 或光加工具都不夠:改 prompt 不補理由欄位 → 查得對但答不全;
> 補工具不改 prompt → agent 還是挑錯即時工具。

#### 結果
- 修後測兩題:「今天選了什麼+理由」→ 正確查 DB 附真實理由;
  「某則沒上的候選有被選嗎」→ 正確回答「沒有選中」,不再捏造。
- 一句話:**agent 的幻覺,常常不是模型笨,而是我給的工具語意不清 + 概念沒定義好。**

#### 對應 JD 能力
`reason about hallucination risk, failure modes, permissions, and guardrails` ·
`Strong understanding of prompt design and tool invocation` ·
`Critically evaluate AI output rather than accepting it blindly` · `Custom AI Agents`

### 🇬🇧 English Version

#### Situation
A selection-quality audit agent (function-calling loop) has three MCP tools: two read the DB
(`get_recent_selections`, `get_run_detail`), one hits live RSS (`fetch_finance_news`).

#### Problem
The agent reported a news item as "selected," with a selection reason — but that item never made it
into today's video.

#### Investigation
Didn't guess — queried the data:
1. Searched the DB by link and title → **zero rows**. Not selected, not even a candidate.
2. Yet the reported item **carried a "selection reason"** — but `fetch_finance_news` returns candidates
   with **no reason field**; reasons only exist as `select_reason` in the DB. → the reason was **fabricated**.
3. Checked today's actual run (run 10) candidate pool → item absent.
4. Pulled **live** RSS → the item was now **#1**. It's a candidate that appeared *after* run 10 executed.

#### Root Cause
The agent called `fetch_finance_news` (live RSS) to answer "what was selected," conflating a
**candidate** with a **selection**, and since candidates have no reason, the LLM **invented a plausible one**.
Three distinct concepts were blurred: candidate ≠ selected ≠ published. Worse, `fetch_finance_news` is
**non-deterministic** — it reflects "now," not "what that run actually selected."

#### Why It Was My Prompt's Fault
The system prompt described `fetch_finance_news` as "today's candidate pool" but never warned it's
candidates-not-selections and live. The self-check never asked "is what I'm citing a candidate or a
selection?" The model had no basis to distinguish the three.

#### Fix (tool + prompt together — neither alone is enough)
1. **Enrich the DB tool**: `get_recent_selections` now also returns `run_id / source / position /
   select_reason`, so "what was selected today + why" is answered in one call.
2. **Self-labeling docstrings** (the docstring *is* the agent's manual): mark `get_recent_selections`
   as "selection facts from DB — use this for 'what was selected'", and `fetch_finance_news` as
   "live candidates, no selected/no reason — never use to answer 'what was selected'."
3. **System prompt**: define candidate vs selected vs published up front, and add a self-check:
   "is my 'was selected' claim actually backed by a DB tool's `select_reason`?"

> 💡 **Lesson**: given several similar tools, an agent will pick the wrong one. Guard in three layers —
> keep tools few and distinct, make docstrings say when/when-not to use, and define the confusable
> concepts in the prompt. Prompt-only or tool-only fixes are insufficient.

#### Result
Post-fix, two tests pass: "what was selected today + why" correctly reads the DB with real reasons;
"was this unpublished candidate selected?" correctly answers "no," with no fabrication.
In one line: **agent hallucination is often not a dumb model — it's tool semantics I left ambiguous.**

#### Mapped JD Competencies
`reason about hallucination risk, failure modes, permissions, and guardrails` ·
`Strong understanding of prompt design and tool invocation` ·
`Critically evaluate AI output rather than accepting it blindly` · `Custom AI Agents`

---

# Part B — 面試談資 / Talking Points

> 這一區不是 bug,是**概念與比喻**。面試被問到 MCP / agent 時,能順口講出來的版本。
> 每則都附:一句話電梯稿 → 完整口語版 → 英文版 → 對應 JD。

---

<a id="T1"></a>
## T1 — MCP 是什麼 & config 綁 client 不綁 tool

### 一句話(電梯稿)
MCP 之於 AI agent,就像 USB 之於周邊設備:工具方實作一次,任何支援 MCP 的 client 都能用,不必為每個 client 各寫一套串接。

### 完整口語版(中文)
MCP(Model Context Protocol)標準化的是「怎麼把工具能力描述給 LLM、以及怎麼呼叫」。
它的運作核心是:**LLM 不執行任何程式碼,它只『說』要呼叫哪個工具、參數是什麼;真正執行的是 client(host)**,執行完把結果塞回對話,LLM 才有東西可講。

關鍵觀念是 **config 綁 client、不綁 tool**:
- server(真正的功能)只寫一次。
- 每個想用它的 client,各自在自己的地方「登記」一次:用哪個指令、跑哪支腳本、工作目錄在哪 —— 就 3~5 行。
- 你登記的是 **server(一整包工具)**,不是逐一登記每個 tool。所以 server 之後加第四個 tool,client 一個字都不用改,下次連上問一次 `list_tools` 就自動看到。

我的專案裡,同一份 server 被**兩個完全獨立的 client**使用 —— 我自己的 Python agent、跟 Claude Desktop。一個登記在程式碼裡、一個登記在 JSON 設定檔,但都是同樣那幾行「去哪找 server」。兩者互不依賴:一邊壞了不影響另一邊。

### 英文版
"MCP is like USB for AI agents — you implement a tool once, and any MCP-capable client can use it, instead of writing a separate integration per client.

The key idea is that the **config is per-client, not per-tool**. The server — the actual functionality — is written once. Every client that wants it just registers where to find it: which command, which script, which working directory — maybe five lines. And you register the *server*, a whole bundle of tools, not each tool. So if I add a fourth tool later, no client changes; they rediscover it via `list_tools`.

In my project the same server is used by two completely independent clients — my own Python agent and Claude Desktop. One registers it in code, the other in a JSON config, but it's the same few lines of 'where to find the server,' and neither depends on the other. You're registering an **address**, not re-implementing the integration."

### 對應 JD
`Model Context Protocol (MCP)` · `Interoperability across AI components without hard-coded integrations` · `Tool and capability exposure to LLM-based agents`

---

<a id="T2"></a>
## T2 — 本機版 → 企業級 的對照(我做了哪些簡化、該換成什麼)

### 一句話(電梯稿)
我用 stdio transport 做本機單人版,每個 client 各開一份 server;要上到 24×7 生產系統,會換成 HTTP transport + 中央 registry + 註冊時驗身分 + gateway 做限流/重試/稽核。我很清楚自己簡化了什麼、以及每一項該換成什麼。

### 對照表(核心)
| 面向 | 我的本機版 | 企業級(如製造業 24×7) |
|---|---|---|
| transport | **stdio**(server 當子行程) | **HTTP**(Streamable HTTP,常駐服務) |
| server 幾份 | 每 client 各開一份 | 一叢,水平擴展 + 負載均衡 |
| register 對象 | 本機腳本路徑 | 服務 URL + 憑證 |
| 發現方式 | 各 client 各寫 config | 中央 **registry** 目錄 |
| 權限 | 無(全信任) | **身分驗證 + 資料邊界**(同 server,不同 agent 看到不同資料) |
| 失敗處理 | try/except + 印訊息 | gateway 做 **重試 / 熔斷 / 告警** |
| 稽核 | 本機 SQLite | 集中式 **audit log** |
| 可觀測性 | 印 log | latency / 錯誤率 / rate limiting |

### 為什麼這樣講有殺傷力
不是假裝做過企業級,而是**「因為我手刻過本機版,所以我講得出為什麼企業需要那些東西」**。
每個「簡化」都是刻意的取捨,不是不知道 —— 這正是資深工程師的判斷力。

### 英文版
"I built it with **stdio** transport for local single-user use, where each client spawns its own server subprocess. In a production setting like a 24×7 manufacturing system, you'd move to an **HTTP transport** with a central **registry**, put **authentication and data-boundary checks at registration time** — so the same server exposes different data to different agents — and front it with a **gateway** for rate limiting, retries, circuit breaking, and audit logging.

I made those simplifications **deliberately**, and I know exactly which ones you'd have to replace to harden it for mission-critical use."

### 對應 JD
`Harden AI components for 24x7 mission critical physical manufacturing systems` · `Reliability and resiliency` · `Latency and performance` · `Security, permissions, and data boundaries` · `Observability and maintainability` · `Critically evaluate ... apply human judgment`

---

<a id="T3"></a>
## T3 — workflow vs agent 的分水嶺(為什麼需要決策迴圈)

### 一句話(電梯稿)
線性 pipeline 的步驟由人寫死;agent 的下一步由 LLM 自己決定,而它得先看到上一步的結果才能決定 —— 所以需要一個「查 → 把結果塞回 → 再問」的迴圈,直到它自己喊停。

### 完整口語版(中文)
LLM 一次呼叫只能做兩件事之一:「我要呼叫工具 X」或「我有答案了」。
如果它選了呼叫工具,這次呼叫就結束了、還沒有答案。我得幫它執行、把結果塞回對話、**再問它一次**。這個「執行→塞回→再問」如果只做一次,是 workflow;做到它自己不再要求工具,就是 agent。

關鍵在於:**下一步該查什麼,取決於上一步查到什麼。** 我專案的稽核 agent 實測會自己走多輪 —— 先查「近 7 天選片」看全貌,發現可疑後再深挖特定 run 的細節,最後才產出報告。這條路徑沒有人寫死,是它看了中間結果自己決定的。

而迴圈一定要配一道**保險絲**(我設 `AGENT_MAX_ITERATIONS=5`):萬一 LLM 鬼打牆一直查不收斂,強制停止、用現有資訊作答 —— 這就是 agent 的 guardrail。

### 英文版
"A single LLM call can only do one of two things: 'call tool X' or 'here's my answer.' If it asks for a tool, that call ends without an answer — so I execute the tool, feed the result back into the conversation, and ask again. Do that once and it's a workflow; loop until the model stops asking for tools and it's an agent.

The point is that **what to look up next depends on what the last lookup returned**. My audit agent decides its own path at runtime — it first pulls the week's selections to get the big picture, notices something off, then drills into specific runs, and only then writes the report. Nobody hard-coded that sequence.

And the loop always needs a fuse — I cap it at five iterations — so a model that never converges gets stopped and forced to answer with what it has. That's the guardrail."

### 對應 JD
`Design Custom AI Agents beyond simple chat interfaces` · `Multi-step reasoning and tool-driven execution` · `reason about hallucination risk, failure modes, permissions, and guardrails`

---

## 新增記錄的模板 / Template for New Entries

```markdown
<a id="00X"></a>
## 00X — <一句話標題:症狀 + 根因類型>

**日期**: · **嚴重度**: · **定位耗時**:

### 🇹🇼 中文版
#### 情境          <- 這個系統在做什麼、為什麼這件事重要
#### 問題          <- 觀察到的症狀(使用者視角)
#### 發現過程      <- ★最有價值的部分:假設 → 驗證 → 排除 → 收斂
#### 根因          <- 技術上到底發生什麼
#### 解法          <- 改了什麼,以及★為什麼改這裡而不是別處★
#### 結果          <- 驗證方式 + 無法挽回的損失(誠實)
#### 學到什麼      <- 可複用的原則
#### 對應 JD 能力

### 🇬🇧 English Version
<same structure>
```

> **寫作提醒**:面試官真正想聽的是**發現過程**(你怎麼想的),不是最終的修法。
> 「我比對了時間戳,先排除了 A 假設,再驗證 B」比「我加了一個型別轉換」值錢得多。
> 也別隱藏無法挽回的損失 —— 誠實評估後果本身就是資深工程師的訊號。
