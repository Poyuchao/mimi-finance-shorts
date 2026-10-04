# 面試準備 — Binance · AI Infra（Agentic RAG & Agent Harness）

> **本檔是你自己的備考筆記。** 對照兩個專案:
> - **ResumePilot 2.0** — production RAG 系統(pgvector / embeddings / chunking / LangChain / Cloud Run)
> - **米米財經** — agent loop / MCP / tool use / feedback loop / guardrails
>
> ## ✅ 校準(修正版):你比想像中接近這份 JD
> 你**不是**零 RAG。ResumePilot 是**真的、上線的 classic RAG**;米米財經是 **agent 那一半**。
> 兩個合起來覆蓋了 JD 的大部分基礎。
>
> **真正的缺口只剩「進階 agentic 層」** —— JD 開宗明義要「moving **beyond** static retrieve-once」,
> 而 ResumePilot 正是 static retrieve-once。所以你的缺口從「整個 RAG」縮小成
> **「把已有的 RAG 升級成 Agentic RAG」+ rerank/hybrid/eval/multi-agent/harness**。這是可攻的距離。
>
> **殺手級敘事(開場用)**:
> > "I've built both halves separately — a production RAG pipeline (ResumePilot: pgvector, embeddings, section-based chunking, multi-turn, deployed on Cloud Run) and an agentic tool-using loop (米米財經: MCP, function-calling agent, feedback loop). **Agentic RAG is fusing the two** — making retrieval adaptive and agent-driven. That's the natural next step from what I've already shipped, and I understand the patterns to get there."

---

## Part A — 可以講的（兩個專案 × JD 對應）

### A1. ResumePilot 2.0 → 命中 JD 的「RAG & production」半邊

| JD 關鍵詞 | ResumePilot 對應 | 面試怎麼講 |
|---|---|---|
| **RAG pipeline end-to-end** | PDF → section chunk → embedding → pgvector → top-k 檢索 → 注入 context → 生成 | 「我端到端做過並**上線**一條 RAG」|
| **Embedding models** | OpenAI `text-embedding-3-small` | 知道 embedding 把文字→向量;可討論換 BGE(開源)|
| **Vector store** | **pgvector**(Postgres extension)| ★有設計理由★:少維護一個服務,向量 + 關聯查詢同一 DB |
| **Chunking strategy(JD 要 deep understanding)** | **section-based**(按 education/experience/project 切),非固定長度 | 「固定長度會切斷語意,我按履歷結構切保留完整性」—— 這題答得漂亮 |
| **Metadata filtering** | 只搜尋指定履歷的 chunks | 向量相似度 + metadata 過濾一次查詢完成 |
| **Context management** | 多輪對話 + 歷史裁剪(保留最近 10 則)+ Redis 快取(cache-aside, TTL 30min)| context 放什麼、怎麼壓、怎麼快取 |
| **Latency / cost profiling** | top-k=3 限制、history 裁剪、**token 用量追蹤可視化** | 「我有量 token 成本並顯示在前端」= 成本意識 + profiling 雛形 |
| **Production(1+ 年硬需求)** | Cloud Run + Cloud SQL + Docker + Cloud Build + SSE streaming + FastAPI async | ★這是你「production LLM 經驗」的主要證據★ |
| **Orchestration framework** | LangChain(RAG chain + 多輪)| JD 要 harness/orchestration,LangChain 是入門對應 |
| **Multi-provider**(LiteLLM nice-to-have)| model-agnostic:OpenAI/Claude 切換只改設定 | 方向對(但不是 LiteLLM proxy)|

### A2. 米米財經 → 命中 JD 的「agent」半邊

| JD 關鍵詞 | 米米財經對應 | 面試怎麼講 |
|---|---|---|
| **Agent Loop / Tool Use / MCP** | U9 function-calling 決策迴圈 + U8 MCP server(4 tools + resource)| 手刻 agent loop + 用 MCP 標準化工具 |
| **Multi-hop / iterative** | agent 跑 3 輪:查 recent → 深挖 detail → 補查 | ★直接類比 retrieve-reflect-refine★ |
| **Real-world Feedback Loops** | U10:發片 → 撈觀看數 → DB → (規劃)回饋選片 | 🔴 JD 明寫「用真實任務數據當 research signal」= 你正在做 |
| **Guardrails / 失敗模式** | max-iter 上限、fail-open、結構化錯誤;#002 抓到 agent 幻覺 | 「幻覺常是工具語意歧義,不是模型笨」|
| **Prompt / Context Engineering** | 可複用原則 + 把歷史訊號注入 context | 跨兩個專案都有 |

### A3. 兩個專案共同 → 命中「AI-native / heavy agent user」

- **Claude Code 蓋出來的**(兩個專案都是)→ JD nice-to-have「Claude Code 已融入日常」**完全命中**。
- **vibe coding / learning velocity / 0→1** → 用「獨立從零做出並上線兩個 AI 系統」證明。

---

## Part B — 真正的缺口 + 必複習觀念 + 補強建議

> 範圍已縮小。以下是**兩個專案都沒碰、但 JD 要**的進階項。

### B1 🔴 Agentic RAG(最關鍵缺口 —— JD 的核心主題)

**你有 classic RAG(retrieve-once),但沒有 agentic 的那些 pattern。** JD 明寫要「beyond static retrieve-once」。

**必複習(一定被問,務必能講出「它解決 classic RAG 的什麼毛病」):**
- **Self-RAG**:模型**自己決定要不要檢索、檢索什麼**,並對「檢索結果相關嗎 / 答案有被支持嗎 / 有用嗎」產生反思 token。
  → 解決:classic RAG 每題都檢索(浪費)、且不自我批判。
- **Corrective RAG (CRAG)**:檢索後先**給文件評分**,相關性低就**觸發 fallback**(擴大檢索 / 改查網路 / 改寫 query)。
  → 解決:classic RAG 檢索到爛文件也硬用 → 幻覺。
- **Adaptive retrieval**:依問題難度決定「不檢索 / 檢索一次 / 多次」。
- **Multi-hop / query decomposition**:複雜問題拆子問題,各自檢索再合併(如「A 公司 CEO 的前東家市值?」要兩跳)。
- **retrieve-reflect-refine loop**:檢索→反思夠不夠→改寫 query 再檢索,直到夠。
  → ★你米米財經的 agent 迴圈就是這個結構,只是查的是 DB 不是向量庫 —— 面試把這個類比講出來★

**補強建議(最自然):把 ResumePilot 的 static RAG 升級成 agentic**
> ResumePilot 的基礎建設都在了(pgvector/embedding/LangChain)。加一層 agent:
> ① 先讓模型判斷「這題要不要檢索」(Self-RAG 入門);
> ② 檢索後評分,不夠相關就改寫 query 再查一次(CRAG + retrieve-reflect-refine)。
> 這就把「classic RAG」變「Agentic RAG」,而且是在**已上線的專案**上做,最可信。

---

### B2 🟠 Retrieval 品質進階:rerank + hybrid search

**你沒做**:ResumePilot 是**純向量** top-k,沒有 rerank、沒有 hybrid。

**必複習:**
- **Rerank(兩階段檢索)**:第一階段向量粗取 top-50(快、bi-encoder)→ **cross-encoder reranker** 精排成 top-5(準)。bi-encoder 各自編碼算相似度;cross-encoder 把 query+doc 一起進模型,準但慢。
- **Hybrid search**:BM25(關鍵字,精確名詞強)+ 向量(語意)→ 用 **RRF(Reciprocal Rank Fusion)** 融合排名。
- **為什麼需要**:純向量會漏「關鍵字精確匹配」(如型號、專有名詞);純關鍵字漏語意。hybrid 互補。

**補強建議**:在 ResumePilot 檢索後加一個 cross-encoder rerank 步驟(如 `bge-reranker`),是小改動、大加分。

---

### B3 🟠 RAG 評估 / Benchmarking(JD 第三大塊,你完全沒做)

**必複習:**
- **RAGAS 四大指標**:**faithfulness/groundedness**(答案忠於檢索內容、沒幻覺)、**answer relevance**(切題)、**context precision**(檢索到的相關比例)、**context recall**(該找的有沒有找到)。
- **retrieval 指標**:precision@k、recall@k、MRR、nDCG。
- **task success rate / latency**(JD 明列)。
- **工具**:RAGAS、TruLens(至少知道在算上面這些)。
- **LLM-as-judge 的坑**:位置偏差、冗長偏好、自我偏好 → 要控制。

**補強建議**:ResumePilot 加一個小 eval —— 量「履歷問答的 groundedness」(答案有沒有超出履歷內容)。哪怕 20 筆,講「我建了 RAG 評估」就贏一截。

---

### B4 🟠 Multi-Agent(JD 多次點名)

**你沒做**:兩專案都是單 agent。

**必複習:**
- **協作模式**:orchestrator–worker、reflection(writer+critic)、debate、hand-off。
- **何時用**:★有「獨立且可能衝突的目標」或「critique 實測提升品質」才值得;否則徒增成本★。
- **subagent**:丟子任務給獨立 context 的 subagent(不污染主 context、可並行)。
- **multi-agent retrieval collaboration**(JD 原文):多 agent 分工檢索不同來源/角度再合併。

**補強建議**:米米財經做「寫手 agent + 審稿 agent」reflection 迴圈(跟你 U5 生圖→審圖同構)= 真 multi-agent 入門。

---

### B5 🟡 Agent Harness / Memory / KV Cache

**你沒做**:Pi Agent / AgentScope 2.0 這類 runtime;session recovery、sandbox、middleware/hook、multi-tenant;long-term agent memory;KV cache。

**必複習:**
- **Agent Harness 解決什麼**:管 agent loop、工具呼叫、session 狀態持久化(斷點續跑)、sandbox 隔離、hook/middleware、多租戶。(你手刻過 loop + 用 Redis 存對話 = 迷你版,但知道成熟框架多了這些。)
- **Memory 分層**:short-term(context window)/ long-term(向量/摘要記憶)/ episodic。★你的 pgvector 其實就能當 long-term memory 的底層 —— 可以這樣延伸講★。
- **KV Cache**:固定 prefix(system prompt/工具定義)→ cache 命中 → 降延遲降成本。
- **Context Engineering**:context 放什麼、壓縮、排序。

**補強建議**:不硬補 harness(太重)。誠實說「手刻過 loop、懂 harness 要解什麼,還沒用過 Pi Agent/AgentScope」。

### B6 🟡 其餘(知道一句話即可)
| 缺口 | 一句話 |
|---|---|
| **GraphRAG** | 用知識圖譜(實體+關係)增強檢索,擅長跨文件多跳關聯 |
| **K8s/EKS** | 你 ResumePilot **刻意選 Cloud Run 不選 GKE**(有理由)→ 懂取捨,只是沒跑過 K8s |
| **RLHF / model co-design** | 用人類回饋微調;你偏 system 側,非 training 側 |
| **Prompt injection 防禦** | 隔離不可信輸入、最小權限、輸出驗證(你 agent 純唯讀算雛形)|

---

## Part C — 若要補強,最高投報的「一條路」

**別分散。選「把 ResumePilot 的 classic RAG → Agentic RAG」這一條**,因為基礎建設都在、最可信、且一條打穿 JD 核心:

```
現況(ResumePilot):retrieve-once → 生成
  ↓ 第 1 步:Self-RAG 入門
讓模型先判斷「要不要檢索」+ 對檢索結果打相關性分
  ↓ 第 2 步:CRAG + retrieve-reflect-refine
分數低 → 改寫 query 再檢索(multi-hop);到夠了才生成
  ↓ 第 3 步:rerank
向量粗取 top-50 → cross-encoder 精排 top-5
  ↓ 第 4 步:eval
groundedness + context precision 小 benchmark,量升級前後差異
```

做完能對 JD 說:「我把一條**已上線**的 classic RAG,0→1 升級成 **Agentic RAG(Self-RAG + CRAG + rerank)並做了評估**」—— 正中 "beyond static retrieve-once"、"retrieve-reflect-refine"、"benchmarking"。
**就算只做第 1~2 步都極有價值。**

---

## Part D — 誠實的面試策略

1. **開場就擺出「兩個專案 = 兩個半邊」**:ResumePilot(RAG/production)+ 米米財經(agent/MCP/feedback)= Agentic RAG 的兩塊拼圖。這個框架很強。
2. **production 經驗用 ResumePilot 撐**:Cloud Run 上線、pgvector、SSE、Redis —— 這是「1+ 年 production」的實證。
3. **缺口用「觀念清楚 + 升級路徑」補**:被問 Self-RAG/CRAG,講「它解決我 ResumePilot 現在的什麼毛病、我會怎麼加」—— 把缺口講成「我知道下一步」。
4. **Claude Code / vibe coding 是你的隱藏強項**:兩個系統都獨立用 agentic workflow 做出並上線 → 命中 heavy-agent-user / learning-velocity。
5. **誠實不吹**:pgvector≠用過 Pi Agent;classic RAG≠Agentic RAG;Redis 快取≠KV cache。研究型面試官一問細節就見真章,誠實反而加分。
6. **兩個 bug 當王牌**:#001 容錯≠靜音、#002 幻覺=工具語意歧義 → 證明「strong opinions about model behavior」。

---

## 附:進場前再掃一遍的 6 個名詞
1. **Self-RAG** — 模型自決是否檢索 + 反思 token
2. **Corrective RAG (CRAG)** — 檢索結果評分 + fallback
3. **retrieve-reflect-refine / multi-hop** — 迭代檢索(= 你米米 agent loop 的向量版)
4. **rerank(cross-encoder)** — 兩階段檢索精排
5. **hybrid search + RRF** — BM25 + 向量融合
6. **RAGAS:faithfulness / answer relevance / context precision / recall** — 怎麼量 RAG
