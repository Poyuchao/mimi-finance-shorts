# 🆕 UPDATE 12（口播稿 審稿 critic · writer-critic reflection）— 修改指引

> **給開發 agent 的核心提醒:分階段做、每步單獨跑單獨驗,不要一次全寫完。遇到不確定停下來回報,不要自行猜測補完。**
>
> ⚠️ 本指引是「提案 + 建議決策」。★實作前先確認 §1 與 §7。★
> 🔴 這次會動到**發片主流程**(改寫→TTS 之間),所以**開關 + fail-open 是硬需求**。

---

## 0. 這次要做什麼 / 為什麼

在「改寫口播稿」之後、「TTS」之前,插一個 **writer-critic reflection 迴圈**:
critic 拿**改寫後的稿**跟**原文**比,擋掉「偏離原文 / 編造 / 誇大 / 投資建議」;不過就退回重寫。

**為什麼(真實價值,非炫技)**:
- 財經稿「忠於原文」是**可信度 + 法律**問題(尤其「投資建議」是紅線)。改寫目前**沒有任何一關把關**,偏離了就直接發。
- 這是你 U5 審圖 agent 的**文字版**(生成→評審→重做),架構一致;本來就在 roadmap(「審稿 agent」)。

**定位(面試用語要精準)**:這是 **reflection / writer-critic pattern**。
★ 不要對外宣稱「multi-agent system」★ —— 它是「同一 graph 的兩個 node(writer/critic)共享 State」,
嚴格說是 reflection loop,不是多個自主 agent。老實叫它 reflection 最穩。

**★ 安全原則 ★**
- **開關 `USE_SCRIPT_REVIEW`**(False = 完全等同現狀)。
- **fail-open**:審稿掛了/逾時/達上限 → **用原稿發片,絕不中斷**(同 U5、DB 哲學)。
- 不碰選片、不碰 MCP、不碰稽核 agent;只在「改寫後」加一道把關。

---

## 1. 建議決策（★實作前先確認★）

| # | 項目 | 建議 | 待你確認 |
|---|------|------|---------|
| S1 | 用什麼實作 | **LangGraph reflection graph**(你指定要練 LangGraph)| 還是純 Python 迴圈(發片主線零框架依賴,更保守)? |
| S2 | critic 判什麼(blocking)| 偏離原文/與原文事實不符、編造數字、**投資建議**、嚴重離題誇大 | 清單要增刪? |
| S3 | minor(放行只記錄)| 語氣、用詞、口語化程度等主觀風格 | OK? |
| S4 | critic 比對依據 | 拿「該則的原文 `clean_text`」跟稿比對(grounding)| OK? |
| S5 | 重寫上限 | `SCRIPT_REVIEW_MAX_RETRY = 1`(不過重寫 1 次;再不過 → fail-open 用原稿)| 幾次? |
| S6 | 範圍 | 只審**口播稿 script**;(可選)順便審 headline 誇大 | 要不要含 headline? |
| S7 | 開關/容錯 | `USE_SCRIPT_REVIEW` + fail-open(必有)| — |

---

## 2. 架構(reflection graph)

```
改寫 rewrite_scripts() → 得到每則草稿 script
      │(每則各跑一次 reflection)
      ▼
┌──────── 審稿 reflection graph(LangGraph)────────┐
│  [START] → critic node ──(過了 or 達上限?)──► [END] → 回「驗證過的稿」
│               ▲                      │
│               │ 沒過(有 blocking)    │
│            writer node ◄─────────────┘ (拿 source + blocking 重寫, attempts++)
│                                                  │
│  State(自訂) = { source, script, issues, attempts, verdict }
└──────────────────────────────────────────────────┘
      ▼ 驗證過的 script(或 fail-open 用原稿)
TTS → 字卡 → 合成 → 上傳
```

- **critic node**:LLM-as-judge,`(source, script)` → `{pass, blocking[], minor[]}`。
- **writer node**:`(source, blocking)` → 重寫稿(★保留米米口吻 + 原本改寫的風格規則★)。
- **conditional edge**(critic 後):`pass or attempts>=max` → END;否則 → writer。
- **START → critic**:先審現有草稿;**只有不過才重寫**(過了就 0 次重寫,省成本)。

### ★ 跟前兩個 graph 的差別(你學到的對照)
| | 稽核 agent(U11)| 審稿 reflection(U12)|
|---|---|---|
| State | MessagesState(對話)| **自訂 State**(source/script/issues)|
| checkpointer | 要 | **不要**(一次性)|
| MCP/工具 | 要 | **不要**(只比兩段文字)|
| 迴圈 | agent⇄tools | **writer⇄critic** |

---

## 3. critic 的兩級分流（★沿用 U5 經驗:給具體範例防過度擋★）

| 級別 | 擋什麼 | 具體範例 |
|---|---|---|
| 🔴 blocking | ① 與原文事實不符/編造(原文沒有的數字、公司、事件)② **投資建議**(「建議買進」「現在是進場點」)③ 嚴重誇大(原文沒說的斷言)④ 完全離題 | 原文說「台積電股價上漲」,稿寫成「台積電將漲到 2000 元,快買」→ blocking(編造+投資建議)|
| 🟡 minor | 語氣、用詞、口語化、米米風格強弱 | 「喵~」用太多、句子稍長 → minor,放行 |

★ 原則:blocking 的敘述要**具體可執行**(指出哪句、哪裡),因為會當「重寫的修正指示」。
★ 忠實度判斷很主觀 → 門檻偏寬,**只擋真的傷可信度/法律的**,別把「改寫本來就會潤飾」當偏離。

---

## 4. 分階段實作（★每階段單獨驗★)

### U12-1:critic node 單測(先不接 graph)
- 寫 critic:`(source, script)` → `{pass, blocking, minor}`(LLM-as-judge,response JSON)。
- ✅ 驗證:餵「忠於原文的稿」→ pass;餵「含投資建議/編造數字的稿」→ blocking 抓到。

### U12-2:reflection graph(critic + writer + 自訂 State)
- `script_review.py`:StateGraph(自訂 State)+ critic/writer node + 條件邊 + recursion 上限。
- writer:`(source, blocking)` → 重寫(保留米米口吻)。
- ✅ 驗證:給一份「故意偏離」的草稿 → graph 重寫 → 變 pass;達上限 → 回原稿(fallback)。

### U12-3:fail-open 包裝 + 接進 pipeline
- `review_and_fix(source, draft) -> str`:包 graph;任何錯/逾時/達上限 → 回原稿。
- `main.py`:改寫後、TTS 前,`if config.USE_SCRIPT_REVIEW:` 對每則跑 `review_and_fix`,
  ★把該則「原文 clean_text」配對進去★(從 picked 取)。
- ✅ 驗證:`USE_SCRIPT_REVIEW=False` → 完全等同現狀。
- ✅ 驗證:故意弄壞審稿 → pipeline 照跑、用原稿發片(fail-open)。

### U12-4:config + 文件
- `config.py`:`USE_SCRIPT_REVIEW`、`SCRIPT_REVIEW_MODEL`、`SCRIPT_REVIEW_MAX_RETRY`。
- README + requirements(若需)。

---

## 5. ✅ Review Checklist

**critic**
- [ ] U12-1 critic `(source, script) -> {pass, blocking, minor}`
- [ ] 兩級分流;blocking 敘述具體可執行
- [ ] ✅ 忠實稿→pass;投資建議/編造→blocking

**graph**
- [ ] U12-2 StateGraph + 自訂 State(source/script/issues/attempts)
- [ ] writer node 重寫時★保留米米口吻★
- [ ] START→critic、critic→(條件)→writer/END、writer→critic
- [ ] recursion 上限 + 達上限 fallback 回原稿
- [ ] ✅ 偏離草稿→重寫→pass;達上限→回原稿

**接 pipeline**
- [ ] U12-3 `review_and_fix` fail-open 包裝(錯/逾時→回原稿)
- [ ] main.py 改寫後、TTS 前接入,每則配對原文 clean_text
- [ ] ✅ USE_SCRIPT_REVIEW=False → 等同現狀
- [ ] ✅ 弄壞審稿 → 發片不中斷、用原稿

**收尾**
- [ ] config:USE_SCRIPT_REVIEW / SCRIPT_REVIEW_MODEL / SCRIPT_REVIEW_MAX_RETRY
- [ ] README 補 U12;requirements(沿用 langgraph/langchain-openai,應不需新增)

---

## 6. ★ 卡關預告 ★

| 問題 | 對策 |
|------|------|
| **過度擋**(忠實度主觀)| 兩級分流 + 給具體 blocking 範例;門檻偏寬,只擋傷可信度/法律的(U5 教訓)|
| **原文配對** | 每則稿要配對「它的」原文 clean_text(用 picked 的 link/順序對)|
| **重寫丟失米米口吻** | writer prompt 要帶原本改寫的風格規則(親切專業、米米、無投資建議)|
| **成本** | 只有「不過」才重寫;過了只花 1 次 critic |
| **LangGraph 進生產線** | 必須 fail-open + 開關;壞了用原稿,不影響發片 |
| **State 不是 MessagesState** | 這個是自訂 State,別硬套 MessagesState |

---

## 7. 需要你拍板的

```
🔴 實作前確認:
  • S1 用 LangGraph(你要練)還是純 Python 迴圈(更保守)?
  • S2 blocking 清單:編造/事實不符、投資建議、嚴重誇大、離題 —— 要增刪?
  • S5 重寫上限幾次(建議 1)?
  • S6 要不要連 headline(標題誇大)也審?

🟠 開發中回報:
  • critic 會不會過度擋(先做一版看判斷再調門檻)
  • 重寫後米米口吻有沒有跑掉
```

---

## 8. 對應 JD（面試用,精準版）

```
• reflection / writer-critic pattern(★老實這樣講,不吹 multi-agent system★)
• Critically evaluate AI output(AI 檢查 AI 的產出)
• reason about failure modes / guardrails(擋編造、擋投資建議、fail-open)
• 跟 U5 審圖並列 → 「我用 reflection 做了圖像 + 文字兩道品質閘」
• 形同 Corrective RAG(評估→不夠好就修正/fallback),用在生成端
```

> 📌 **核心原則:分階段、每步單獨驗、開關 + fail-open 不影響發片。**
> 成敗定義:審稿能擋掉「偏離原文/投資建議」並重寫,且壞掉時用原稿、發片不中斷。
