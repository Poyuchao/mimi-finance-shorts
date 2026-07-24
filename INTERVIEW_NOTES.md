# 工程問題記錄 / Engineering Problem Log

> 記錄本專案(米米財經)開發過程中遇到的**非顯而易見**的問題、除錯過程、根因與解法。
> 用途:面試時的具體案例庫(STAR:Situation / Task / Action / Result)。
>
> **收錄標準**:值得講的問題,不是「打錯字」那種。通常符合其中一項 ——
> ① 症狀與根因距離很遠 ② 靠推理而非猜測定位 ③ 修完帶出可複用的設計原則 ④ 揭露架構層級的缺陷。
>
> A log of non-obvious engineering problems from this project, with the debugging process,
> root cause, and fix. Purpose: a case library of concrete examples for interviews.

---

## 索引 / Index

| # | 問題 / Problem | 關鍵字 / Tags |
|---|---|---|
| [001](#001) | MCP 序列化邊界造成 DB 無聲漏記 3 天<br>Silent data loss for 3 days at the MCP serialization boundary | `MCP` `serialization` `silent-failure` `observability` `fault-isolation` |

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
