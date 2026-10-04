# ResumePilot 2.0 — AI 履歷分析與互動式問答工具

上傳你的履歷，透過 AI 自動結構化分析，並支援多輪對話協助優化。

**線上 Demo：** https://resumepilot-frontend-338336680245.asia-east1.run.app

## 系統架構

```
使用者瀏覽器
    │
    ▼
Cloud Run（Next.js 前端）
    │ REST API + SSE Streaming
    ▼
Cloud Run（FastAPI 後端）
    │
    ├── Cloud SQL（PostgreSQL + pgvector）
    │     ├── 履歷、對話、訊息（關聯式資料）
    │     └── Embedding 向量（pgvector）
    │
    └── OpenAI API（LLM + Embedding）
```

## 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | Next.js 16、React 19、Tailwind CSS、Radix UI、SSE streaming |
| 後端 | FastAPI（Python）、LangChain、SQLAlchemy（async） |
| 資料庫 | PostgreSQL 16（Cloud SQL） |
| 向量搜尋 | pgvector（PostgreSQL extension） |
| Embedding | OpenAI text-embedding-3-small |
| LLM | OpenAI GPT-4o-mini（可切換 Claude） |
| 快取 | Redis（對話上下文快取） |
| 部署 | GCP Cloud Run、Cloud SQL、Artifact Registry、Cloud Build |
| 開發工具 | Claude Code（AI 輔助開發） |

## 核心功能

### RAG（檢索增強生成）
- **Section-based Chunking** — 按履歷結構（education/experience/project）切分，非固定長度，保留語意完整性
- **Top-K=3 檢索** — 平衡上下文品質與 Token 成本
- **Metadata 篩選** — 只搜尋指定履歷的 chunks，不會混入其他履歷

### Prompt Engineering
- **3 種分析模式** — 一般模式、HR 視角、技術面試官視角
- **結構化 JSON 輸出** — 強制輸出格式，確保前端解析穩定
- **多輪對話** — 帶入聊天歷史的上下文感知追問

### Token 成本控制
- **RAG Top-K 限制** — 只注入最相關的 3 個 chunks，非整份履歷
- **對話歷史裁剪** — 只保留最近 10 則訊息
- **Token 用量追蹤** — 每次 API 呼叫記錄估算 token 消耗，前端面板可視化

### 向量搜尋（pgvector）
- Embedding 向量直接存在 PostgreSQL，透過 pgvector extension
- 一個 query 同時完成向量相似度搜尋 + metadata 過濾 + 取得內容
- 不需要額外維護獨立的 Vector DB（Chroma/Pinecone）

### 即時串流（SSE）
- Server-Sent Events 逐 token 即時回傳
- 前端逐步渲染 AI 回覆，大幅降低使用者感受到的延遲

## 專案結構

```
resumeCopilot2-backend/          # FastAPI 後端
├── app/
│   ├── api/v1/                  # 路由處理
│   ├── models/                  # SQLAlchemy ORM 模型
│   ├── schemas/                 # Pydantic 請求/回應 Schema
│   ├── services/                # 商業邏輯
│   │   ├── rag_service.py       # 履歷分析（RAG chain）
│   │   ├── conversation_service.py  # 多輪對話 + streaming
│   │   ├── vectorstore_service.py   # pgvector 整合
│   │   ├── chunking_service.py  # Section-based 切分
│   │   └── pdf_service.py       # PDF 文字擷取
│   └── db/                      # 資料庫 + Redis 連線
├── Dockerfile
└── requirements.txt

resumeCopilot2-frontend/         # Next.js 前端
├── src/
│   ├── app/page.tsx             # 主頁面
│   ├── components/              # UI 元件
│   │   ├── ResumeInput.tsx      # 履歷上傳 + 文字輸入
│   │   ├── AnalysisResults.tsx  # 分析結果顯示（可收合）
│   │   ├── ChatInterface.tsx    # 多輪對話 + streaming
│   │   └── SettingsPanel.tsx    # 模式選擇 + Token 用量
│   └── lib/api.ts               # API client（fetch + SSE 解析）
├── Dockerfile
└── cloudbuild.yaml
```

## 快速開始

### 本地開發

**前置需求：** Docker、Node.js 20+、Python 3.11+

```bash
# 1. 啟動 PostgreSQL + Redis
cd resumeCopilot2-backend
docker compose up -d

# 2. 啟動後端
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入你的 OPENAI_API_KEY
uvicorn app.main:app --reload

# 3. 啟動前端
cd resumeCopilot2-frontend
npm install
npm run dev
```

### 部署到 GCP

```bash
# Build & 部署後端
cd resumeCopilot2-backend
gcloud builds submit --tag asia-east1-docker.pkg.dev/PROJECT/REPO/backend
gcloud run deploy resumepilot-backend --image=... --region=asia-east1

# Build & 部署前端
cd resumeCopilot2-frontend
gcloud builds submit --config=cloudbuild.yaml
gcloud run deploy resumepilot-frontend --image=... --region=asia-east1
```

## 設計決策

| 決策 | 原因 |
|------|------|
| pgvector 取代 Chroma | 少維護一個服務；向量搜尋與關聯式查詢在同一個 DB 完成 |
| Section-based chunking 取代固定長度切分 | 保留履歷各區塊的語意結構完整性 |
| SSE 取代 WebSocket | 單向 LLM token 串流場景更簡潔；原生 HTTP，無額外協議 |
| Cloud Run 取代 GKE | Serverless 自動擴縮，閒置零成本；這個規模不需要 Kubernetes |
| Redis 對話上下文快取 | 高併發下減少 DB 讀取；Cache-Aside 模式，TTL 30 分鐘 |
| 模型無關架構 | LangChain 抽象層讓 OpenAI/Claude 切換只需改設定檔 |


---


# ResumePilot 2.0 — AI Resume Analysis & Interactive Q&A Tool

Upload your resume, get AI-powered structured analysis, and optimize it through multi-turn conversation.

**Live Demo:** https://resumepilot-frontend-338336680245.asia-east1.run.app

## Architecture

```
User Browser
    │
    ▼
Cloud Run (Next.js Frontend)
    │ REST API + SSE Streaming
    ▼
Cloud Run (FastAPI Backend)
    │
    ├── Cloud SQL (PostgreSQL + pgvector)
    │     ├── Resumes, conversations, messages (relational data)
    │     └── Embedding vectors (pgvector)
    │
    └── OpenAI API (LLM + Embedding)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Tailwind CSS, Radix UI, SSE streaming |
| Backend | FastAPI (Python), LangChain, SQLAlchemy (async) |
| Database | PostgreSQL 16 (Cloud SQL) |
| Vector Search | pgvector (PostgreSQL extension) |
| Embedding | OpenAI text-embedding-3-small |
| LLM | OpenAI GPT-4o-mini (switchable to Claude) |
| Cache | Redis (conversation context caching) |
| Deployment | GCP Cloud Run, Cloud SQL, Artifact Registry, Cloud Build |
| Dev Tools | Claude Code (AI-assisted development) |

## Key Features

### RAG (Retrieval-Augmented Generation)
- **Section-based chunking** — splits resume by structure (education/experience/project), not fixed length, preserving semantic integrity
- **Top-K=3 retrieval** — balances context quality and token cost
- **Metadata filtering** — only searches chunks belonging to the target resume

### Prompt Engineering
- **3 analysis modes** — General, HR Perspective, Technical Interviewer
- **Structured JSON output** — enforced output format for frontend parsing stability
- **Multi-turn conversation** — context-aware follow-up with chat history

### Token Cost Control
- **RAG top-K limit** — only inject 3 most relevant chunks, not the entire resume
- **Conversation history trimming** — keep only the last 10 messages
- **Token usage tracking** — log estimated token consumption per API call, displayed in frontend

### Vector Search (pgvector)
- Embedding vectors stored directly in PostgreSQL via pgvector extension
- Single query for vector similarity search + metadata filtering + content retrieval
- No need to maintain a separate vector DB service (Chroma/Pinecone)

### Streaming (SSE)
- Server-Sent Events for real-time token-by-token response
- Frontend renders AI response incrementally, reducing perceived latency

## Project Structure

```
resumeCopilot2-backend/          # FastAPI backend
├── app/
│   ├── api/v1/                  # Route handlers
│   ├── models/                  # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/                # Business logic
│   │   ├── rag_service.py       # Resume analysis (RAG chain)
│   │   ├── conversation_service.py  # Multi-turn chat + streaming
│   │   ├── vectorstore_service.py   # pgvector integration
│   │   ├── chunking_service.py  # Section-based chunking
│   │   └── pdf_service.py       # PDF text extraction
│   └── db/                      # Database + Redis connections
├── Dockerfile
└── requirements.txt

resumeCopilot2-frontend/         # Next.js frontend
├── src/
│   ├── app/page.tsx             # Main page
│   ├── components/              # UI components
│   │   ├── ResumeInput.tsx      # Resume upload + text input
│   │   ├── AnalysisResults.tsx  # Analysis display (collapsible)
│   │   ├── ChatInterface.tsx    # Multi-turn chat with streaming
│   │   └── SettingsPanel.tsx    # Mode selection + token usage
│   └── lib/api.ts               # API client (fetch + SSE parsing)
├── Dockerfile
└── cloudbuild.yaml
```

## Getting Started

### Local Development

**Prerequisites:** Docker, Node.js 20+, Python 3.11+

```bash
# 1. Start PostgreSQL + Redis
cd resumeCopilot2-backend
docker compose up -d

# 2. Start backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your OPENAI_API_KEY
uvicorn app.main:app --reload

# 3. Start frontend
cd resumeCopilot2-frontend
npm install
npm run dev
```

### Deploy to GCP

```bash
# Build & deploy backend
cd resumeCopilot2-backend
gcloud builds submit --tag asia-east1-docker.pkg.dev/PROJECT/REPO/backend
gcloud run deploy resumepilot-backend --image=... --region=asia-east1

# Build & deploy frontend
cd resumeCopilot2-frontend
gcloud builds submit --config=cloudbuild.yaml
gcloud run deploy resumepilot-frontend --image=... --region=asia-east1
```

## Design Decisions

| Decision | Why |
|----------|-----|
| pgvector over Chroma | One fewer service to maintain; vector search + relational queries in single DB |
| Section-based chunking over fixed-length | Preserves semantic structure of resume sections |
| SSE streaming over WebSocket | Simpler for unidirectional LLM token streaming; native HTTP, no extra protocol |
| Cloud Run over GKE | Serverless, auto-scaling, zero cost when idle; K8s is overkill for this scale |
| Redis for context caching | Reduce DB reads under concurrent chat sessions; cache-aside pattern with 30min TTL |
| Model-agnostic architecture | LangChain abstraction allows switching between OpenAI/Claude with config change |

