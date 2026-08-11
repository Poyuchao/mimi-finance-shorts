# 米米財經 — AI 財經股市短影音自動化

自動把當日財經新聞做成一支**直式 9:16 短影音**(IG Reels / YouTube Shorts 通用),由 AI 虛擬貓主播「**米米**」在頭尾主持。
從抓 RSS、篩股市新聞、LLM 選題與改寫口播稿、TTS 配音、生成字卡與米米開場/收尾,到影片合成,全自動一鍵產出本機 mp4。

> 個人作品集專案。目標:整條 pipeline 跑通、能自動產出一支影片。
>
> **版本**:MVP(字卡版)→ U1 米米全程 → **U2 節目化**(米米只在頭尾)→ U3 YouTube 自動上傳
> → U4 AI 示意圖 → U5 AI 審圖 agent → U6 選片記錄(DB)→ **U8 MCP Server**(工具能力標準化)
> → **U9 選片品質稽核 Agent**(function calling 決策迴圈)→ **U10 觀看數追蹤**(發布 → 觀測回饋)。
> 每個階段都留一鍵開關(`USE_MIMI` / `USE_AI_IMAGE` / `USE_IMAGE_REVIEW` / `UPLOAD_ENABLED` / `USE_MCP`),可退回前一版行為。

---

## 影片結構(4 階段 6 片段)

```
① 封面        靜態卡:🐱米米財經 + LLM 動態標題 + 日期 + slogan
② 米米開場白  🐱 米米動畫 + 泡泡「哈囉~我是米米!」+ 開場旁白
③ 3 則新聞    純字卡 + 數字視覺化(漲跌大數字)+ 專業旁白(無米米)
④ 米米收尾    🐱 米米動畫 + 泡泡「掰掰~明天見!」+ 來源 + 收尾旁白
```

節奏:**萌開場 → 專業新聞 → 萌收尾**。米米集中頭尾(記憶點),新聞段純字卡(專業、資訊聚焦)。

### 為什麼米米能「預生成、重複用」

- 米米**不對嘴(no lip-sync)** → 動作與當日內容無關 → 同一段米米動畫每天重複用。
- AI 圖生影片只**手動預生成 2 段**(開場 `intro.mp4` / 收尾 `outro.mp4`),放進 `assets/mimi/`。
- 每天 pipeline 只挑素材疊字卡,**不把 AI 圖生影片放進每天的自動流程**(慢/貴/不穩)。

---

## Pipeline

```
①②③ 取得候選池 —— 走 MCP:呼叫 fetch_finance_news + get_recent_selections
      (MCP 掛掉自動 fallback 回下面的直接呼叫,發片不中斷)
   ① 抓 RSS 財經新聞(3 來源:ETtoday / 自由時報 / 風傳媒)
   ② 解析 + 篩股市 + 清洗(剝 HTML、股市關鍵字 + 排除中港股)
   ③ 收斂候選池(去重 + 排序 → ~10 則)
④a LLM 選片:從候選挑 3 則「最重要」的 + 理由(硬門檻:必須直接跟股市有關;
    並帶入近 7 天已發過的新聞 → 避免重複報導同一事件)
④b LLM 改寫:口播稿(親切但專業)+ headline + 結構化 highlight + video_title + hashtag
④c 每則生 AI 示意圖(Gemini,Q版米米人物;失敗即 fallback 純字卡)
④d AI 審圖(擋編造數字/亂碼/真人/嚴重離題);不過 → 重生一次 → 再不過 → 退純字卡
⑤ TTS 配音:3 則新聞 script + 開場白/收尾旁白
⑥ 生字卡:封面 / 新聞卡(有圖版=AI圖+資訊 / 無圖版=純字卡+數字視覺化)/ 開場白·收尾
⑦ 影片合成(MoviePy):封面 + 米米開場白 + 3 新聞 + 米米收尾 → output/final.mp4
⑧ 自動上傳 YouTube(選用):videos.insert(resumable)+ OAuth,先傳 private
⑨ 寫入 DB:記錄候選 ~10 篇 + LLM 選中的 3 篇 + 理由(用於驗證選片品質)
```

---

## 特色

- **AI 虛擬貓主播(頭尾)+ 一鍵切換**:`USE_MIMI=True` 出米米頭尾版、`False` 出純字卡版(封面 + 3 新聞 + 純字卡結尾)。
- **數字視覺化**:每則新聞把 highlight 做成大數字 + 漲跌箭頭(**台股慣例:紅漲 ▲ / 綠跌 ▼ / 中性白**),方向由 LLM 判定(結構化 `{value, trend, label}`)。
- **封面動態標題**:用 LLM 的 `video_title`,永遠對得上當天內容。
- **LLM 分兩步「先選再改寫」**:先挑最有影響力的新聞(市場級/結構性優先),再改寫成親切但專業的口播稿。
- **LLM 可替換介面**:`LLMService` 抽象介面,目前 OpenAI `gpt-4o-mini`,換 Gemini/Claude 只需加 class。
- **MCP Server**:把「抓新聞 / 查歷史選片」以 [Model Context Protocol](https://modelcontextprotocol.io) 標準暴露成 tools —— 同一份 server,**pipeline 與 Claude Desktop 都能用**。
- **全鏈路容錯**:RSS 單一來源失敗 → skip 其他繼續;生圖/審圖失敗 → 退純字卡;上傳失敗 → 保留 mp4;寫 DB 失敗 → 只 log;**MCP 失敗 → fallback 直接呼叫**。任何一環都不讓影片發不出去。
- **誠實文案**:slogan 定調「回顧財經重點」(非分析教學),收斂在 `config.CHANNEL_SLOGAN`。

---

## 技術棧

| 用途 | 工具 |
|------|------|
| 語言 | Python 3.11+(開發用 3.14) |
| 抓 RSS | feedparser、requests、beautifulsoup4 |
| LLM | openai(gpt-4o-mini) |
| TTS | edge-tts(`zh-TW-HsiaoChenNeural`) |
| 字卡 | Jinja2 + Playwright(chromium) |
| 影片 | MoviePy(CompositeVideoClip 疊層,底層 ffmpeg) |
| 生圖 / 審圖 | google-genai(Gemini;`-image` 變體生圖、vision 模型審圖) |
| 上傳 | google-api-python-client + OAuth 2.0(YouTube Data API v3) |
| 資料庫 | SQLAlchemy 2.0 + SQLite |
| 工具協議 | `mcp`(Model Context Protocol,FastMCP + stdio) |
| 米米素材 | AI 圖生影片工具(如 DeeVid)手動預生成,直式 9:16 |

---

## 專案結構

```
.
├── main.py              # 一鍵串整條 pipeline(依 USE_MIMI 分流)
├── config.py            # RSS、關鍵字、影片參數、米米設定、文案 slogan
├── fetch_rss.py         # ① 抓 RSS(3 來源 + 容錯)
├── parse_filter.py      # ② 解析 + 篩股市 + 清洗
├── select_news.py       # ③ 收斂候選池(去重 + 排序)
├── llm_service.py       # ④ LLM 選片 + 改寫(結構化 highlight;可替換介面)
├── image_service.py     # ④c AI 生成新聞示意圖(Gemini;safe_generate 生圖+審圖防呆鏈)
├── review_service.py    # ④d AI 審圖 agent(Gemini vision;blocking/minor 分級)
├── tts.py               # ⑤ TTS(新聞 script + 開場白/收尾旁白)
├── card_render.py       # ⑥ 字卡(封面/新聞卡兩版面/開場白·收尾泡泡卡)
├── video.py             # ⑦ 影片合成(6 片段;make_mimi_segment 疊層只用頭尾)
├── templates/
│   ├── base.html / base_mimi.html          # 共用樣式(不透明 / 透明)
│   ├── cover_card.html                     # 封面(動態標題)
│   ├── news_card.html                      # 新聞卡(有圖版 / 無圖版數字視覺化)
│   ├── opening_card.html / closing_card.html  # 開場白 / 收尾(透明泡泡卡)
│   └── outro_card.html                     # USE_MIMI=False 的純字卡結尾
├── publisher/           # YouTube 上傳 + 讀觀看數
│   └── youtube.py       #   OAuth 上傳 / 讀取(唯讀)+ fetch_video_stats(U10)
├── db/                  # ⑨ 資料庫記錄(SQLAlchemy)
│   ├── models.py        #   Run 1 ──< Candidate(Run 含觀看數欄位 U10)
│   ├── database.py      #   engine / session / init_db + 輕量遷移(U10)
│   └── repository.py    #   save_run / get_recent_selections / get_run_detail / get_video_stats
├── mcp_server/          # 🔌 MCP Server(把唯讀能力標準化暴露)
│   └── finance_news_server.py  # FastMCP:fetch_finance_news / get_recent_selections
│                        #          get_run_detail / get_video_stats + resource runs://latest
├── mcp_client.py        # 🔌 MCP Client(啟 server 子行程 + call_tool;可單獨跑測試)
├── agent.py             # 🤖 選片品質稽核 agent(U9,function calling 決策迴圈,純唯讀)
├── refresh_stats.py     # 📊 撈 YouTube 觀看數 → 更新 DB(U10,寫入類維運)
├── query_runs.py        # 查詢 DB:每次「選了哪 3 則、為什麼」+ 觀看數
├── assets/mimi/         # 🐱 米米素材(手動放,重複用)
│   ├── intro.mp4        #   開場白
│   ├── outro.mp4        #   收尾
│   └── 米米財經主播4.jpg  #   米米參考圖(生圖時人物用 Q版米米)
├── client_secrets.json  # OAuth Desktop 憑證(自備,gitignore)
├── token.json           # 首次授權後自動產生(gitignore)
├── output/              # 產出(cards/ png、audio/ mp3、final.mp4)
├── test_env.py          # 階段 0 環境驗證
└── run_stage*.py        # 各階段單獨執行器(開發驗證用)
```

---

## 安裝

```powershell
# 1. venv
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate

# 2. 套件
pip install -r requirements.txt

# 3. Playwright 瀏覽器
playwright install chromium

# 4. ffmpeg(系統層)
#   Windows: winget install Gyan.FFmpeg   (裝完重開終端讓 PATH 生效)
#   macOS:   brew install ffmpeg
#   Ubuntu:  sudo apt install ffmpeg

# 5. API key
copy .env.example .env           # 填入 OPENAI_API_KEY
```

驗證環境:`python test_env.py`(全部 [OK] 才算就緒)。

### 米米素材(米米版才需要)

把 2 段預生成米米動畫放進 `assets/mimi/`:`intro.mp4`(開場)、`outro.mp4`(收尾)。
- 直式 9:16、幾秒的自然動作(眨眼/擺頭)、**看鏡頭、無浮水印**。
- 缺任一段 → 那一段自動退純字卡(不崩)。
- ⚠️ 浮水印請在素材端處理,**pipeline 不去浮水印**。

---

## 使用

```powershell
python main.py
```

產物在 `output/`:
- `final.mp4` — 最終影片(1080×1920)
- `cards/*.png` — 各字卡
- `audio/*.mp3` — 各段配音(item_1..3 / opening / outro)
- `output_llm.json` — LLM 文案(標題 / hashtag / 每則腳本 + 結構化 highlight)

### 米米頭尾版 ↔ 純字卡版

在 `config.py`:`USE_MIMI = True`(米米頭尾)/ `False`(純字卡:封面 + 3 新聞 + 純字卡結尾)。

---

## 新聞卡 AI 示意圖(選用)

每則新聞用 **Gemini** 生一張財經示意插畫放進新聞卡上半 —— **畫面中的人物(官員/分析師/投資人)一律用 Q 版米米貓**(靠參考圖 `assets/mimi/米米財經主播4.jpg`),品牌一致。**生圖失敗/超時 → 該則自動退回純字卡,絕不中斷發片。**

**準備:**
1. `.env` 加 `GEMINI_API_KEY=...`(到 Google AI Studio 拿;圖像生成是**付費功能**,需在 GCP 開帳單)。
2. 裝套件:`pip install google-genai`。

**開關與設定(config.py):**
- `USE_AI_IMAGE = True`(關掉 = 三則都純字卡,等同前一版)。
- `IMAGE_MODEL = "gemini-3.1-flash-lite-image"`(★ 生圖要用「-image」變體,純文字版不生圖)。
- `IMAGE_TIMEOUT`(120s)、`IMAGE_RETRY`(1)、`IMAGE_DIR`、`IMAGE_DISCLAIMER`、`MIMI_REF_IMAGE`。

**經驗談(生圖 prompt 調校):**
- prompt **用中文寫** → 圖上中文才正確(英文 prompt 會中文亂碼)。
- 用「**illustration / 插畫**」而非「infographic」→ 才不會硬塞一堆標籤文字。
- **禁止圖上出現任何具體數字/財務數據**(AI 一定會編造假的 EPS、毛利率)。
- **真實企業 logo 允許出現**(編輯性使用)。⚠️ 這條**生圖與審圖兩邊都要改** —— 只放寬生圖端,圖照樣會被審圖擋掉。
- **必須用 `image_config(aspect_ratio="16:9")` 強制橫式**(Gemini 不保證遵守 prompt 的「橫幅」,回直式會撐爆卡片)。
- 有圖 → YT 描述自動加「部分畫面為 AI 生成示意圖」。

---

## AI 審圖 agent(選用)

生圖後、上片前,用 **Gemini vision** 審查每張示意圖。審不過 → 帶問題**重生一次** → 再不過 → **該則退純字卡**。
**審圖永遠不會擋住發片** —— 它只決定「這則有沒有圖」。

**審查分兩級(關鍵設計):**

| 級別 | 項目 | 處置 |
|------|------|------|
| 🔴 **blocking**(傷可信度) | 編造的財務數據(EPS/毛利率/%/日期)、亂碼不成句、真人臉孔、嚴重離題或扭曲新聞 | **擋** → 重生 / 退純字卡 |
| 🟡 **minor**(純美觀) | 標籤重複、標籤過多、圖表裝飾刻度、構圖美感 | **放行**(只記 log) |
| ☑ **明確放行** | 真實企業 logo(編輯性使用)、台北 101 等地標與通用符號 | **不算違規** |

> 💡 **為什麼一定要分級**:不分級的話,會為了「標籤重複」這種小事把好圖整張丟掉,而重生後品質常常更糟 → 變成「又花錢又沒圖」。**審查員該守的是可信度底線,不是美感。**

**設定(config.py):** `USE_IMAGE_REVIEW`(關掉 = 不審)、`REVIEW_MODEL`(視覺文字模型,非 `-image` 變體)、`REVIEW_MAX_RETRY`(1;設 0 = 不重生)、`REVIEW_TIMEOUT`(60s)。
**審查 API 失效/逾時 → 保守視為「不通過」**(不發沒審過的圖)。

---

## YouTube 自動上傳(選用)

`main.py` 產出 mp4 後可自動上傳 YouTube(YouTube Data API v3 + OAuth 2.0)。**預設關閉**,先傳「私人」。

**一次性準備:**
1. GCP Console:建專案 → 啟用 **YouTube Data API v3**。
2. 建 **OAuth 2.0 用戶端 ID**,類型選 **桌面應用程式**;下載 JSON,命名 `client_secrets.json` 放專案根目錄。
3. OAuth 同意畫面:User type 選 External,把自己的 Google 帳號加為**測試使用者**。
4. 裝套件:`pip install google-api-python-client google-auth-oauthlib google-auth-httplib2`。

**首次授權(產生 token):**
```powershell
python run_youtube_auth.py     # 開瀏覽器登入+同意 → 產生 token.json(之後重複用)
```
> 會看到「Google 尚未驗證這個應用程式」→ 進階 → 繼續(你是自己 app 的測試使用者,正常)。

**啟用自動上傳:** 在 `config.py` 設 `UPLOAD_ENABLED = True`,之後 `python main.py` 跑完就會自動上傳。
- `YT_PRIVACY`:`private`(預設)/ `unlisted` / `public`。
- 上傳成功會 log 出影片網址;**上傳失敗不影響已產出的 mp4**。
- ⚠️ **AI 內容標註**:YouTube API 目前無穩定欄位 → 上傳後請到 **YT Studio 後台手動勾「變造/合成內容」**(pipeline 會 log 提醒)。
- 影片約 82 秒,直式 + `#Shorts` 會被 YT 當 Shorts(Shorts 上限已放寬到 3 分鐘)。

> ⚠️ `client_secrets.json`、`token.json` 含機密,已在 `.gitignore`,別 commit。
> GCP 部署 / 排程 / Instagram 上傳為之後的擴充。

---

## 選片記錄 / 驗證選片品質

每次執行都會把「**候選 ~10 篇 + LLM 選中的 3 篇 + 選片理由**」寫進 SQLite(`mimi.db`),用來**事後驗證 LLM 選片品質**(選片是黑箱,要有據可查)。**寫 DB 失敗不會中斷發片。**

```powershell
python query_runs.py           # 最近執行摘要 + 最新一次的完整候選池
python query_runs.py --list    # 只看摘要
python query_runs.py 5         # 看 run_id=5 的候選池 + 選片理由
```

也可用 [DB Browser for SQLite](https://sqlitebrowser.org/) 開 `mimi.db` 瀏覽 `runs` / `candidates` 兩張表。

> 💡 **實效**:上線第一天就靠它抓到「同一次選了兩則力積電」的選片問題(違反題材分散),並據此修好了 select prompt。
> `candidates.link` 已存並建索引 → 這份資料已由 MCP 的 `get_recent_selections` 回饋進選片 prompt(見下節)。
> `runs` 另存每支影片的觀看數(U10,見「觀看數追蹤」),`query_runs.py --list` 會多顯示一欄「觀看」。

---

## MCP Server(工具能力標準化)

把「抓財經新聞」和「查歷史選片」用 **[Model Context Protocol](https://modelcontextprotocol.io)** 標準暴露成 tools。
**同一份 server,兩個完全不同的 client 都能用,server 一行都不用改:**

| Client | 誰啟動 server | 用途 |
|---|---|---|
| `main.py`(經 `mcp_client.py`) | pipeline 自己 | 每天自動發片 |
| **Claude Desktop** | app 自己 | 手動聊天、實驗選片邏輯 |

**提供的 tools（唯讀能力,暴露給 agent）:**

| Tool | 參數 | 回傳 |
|---|---|---|
| `fetch_finance_news` | `pool_size`(預設 10) | 即時候選新聞 list(★未選中、無理由★) |
| `get_recent_selections` | `days`(預設 7) | 近 N 天「真正選中」的新聞 + 選片理由(來自 DB)|
| `get_run_detail` | `run_id` | 某次執行的完整候選 + 選中 3 則 + 理由 + 該支觀看數 |
| `get_video_stats` | `limit`(預設 10) | 各支影片觀看數/讚/留言,依觀看排序(🆕 U10)|

外加 MCP **Resource** `runs://latest`(最近一次選片摘要),展示 tools 以外的 primitive。

> 🔴 **MCP 邊界原則:唯讀上、寫入不上。** 上表都是「查詢」;會打外部 API / 寫 DB 的動作
> (`save_run`、撈觀看數 `fetch_video_stats`)**留在 pipeline 直接呼叫,不上 MCP** —— 才能維持 agent 的「純唯讀」保證。

```
Claude Desktop / main.py
        │  ① 啟動子行程  venv\python.exe finance_news_server.py
        │  ② stdin/stdout 互丟 JSON-RPC(不走網路,資料不出本機)
        ▼
finance_news_server.py  ──呼叫既有模組──> fetch_rss / parse_filter / select_news / repository
```

**設計重點:**
- **不重寫任何功能** —— tool 內部只是呼叫既有模組,MCP 純粹是「多一層標準化介面」。
- **fallback 是硬需求**:`main.py` 用 try/except 包住,MCP 掛掉就走原本的直接呼叫,**發片不中斷**(已實測:把 server 路徑指到不存在的檔,pipeline 照跑)。
- `USE_MCP = False` → 完全等同 UPDATE 6 現狀。

**⚠️ 兩個踩過的坑:**
1. **server 端絕對不能 `print`** —— stdout 是 MCP 協議通道,任何多餘輸出都會打壞協議。log 一律 `stream=sys.stderr`。
2. **client 要用 `sys.executable` + 絕對路徑 + `cwd`** —— 寫死 `"python"` 會抓到 Microsoft Store 的 python stub;沒設 `cwd` 則 `sqlite:///mimi.db` 這種相對路徑找不到 DB。

### 接到 Claude Desktop

在 `claude_desktop_config.json` 加入(**路徑換成你自己的**):

```json
{
  "mcpServers": {
    "finance-news": {
      "command": "C:\\...\\venv\\Scripts\\python.exe",
      "args": ["C:\\...\\mcp_server\\finance_news_server.py"],
      "cwd": "C:\\...\\ai internet influencer",
      "env": { "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1" }
    }
  }
}
```

> 設定檔位置:一般版在 `%APPDATA%\Claude\`;**Microsoft Store 版**則在
> `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\`。
> 改完要**完全結束 app**(系統匣右鍵 Quit,不是關視窗)再重開。
> ⚠️ app 結束時會重寫整份 config —— **請先關 app 再改檔**,否則會被覆蓋掉。

接上後可直接在 Claude Desktop 問「抓一下今天的財經新聞候選」「幫我挑 3 則最重要的並說明理由」——
等於一個**不用跑整條 pipeline 就能測選片邏輯的實驗場**,調好再把結論寫回 `llm_service.py` 的 prompt。

單獨測試 client:`python mcp_client.py`

---

## 選片品質稽核 Agent（U9,選用）

一個**獨立、純唯讀**的終端機 CLI:用自然語言問歷史選片品質,由 **LLM(OpenAI function calling)自己決定**呼叫哪些 MCP 工具、呼叫幾次,做多步推理後產出稽核報告。

```powershell
python agent.py
```
```
問題> 這週選片品質有沒有問題?有問題要指出是哪一次
  [工具] get_recent_selections(days=7)   ← 第 1 輪  先看全貌
  [工具] get_run_detail(run_id=8)         ← 第 2 輪  發現可疑,深挖
  [工具] get_run_detail(run_id=7)         ← 第 2 輪
  → 產出 JSON 稽核報告(主體重複 / 來源偏食 + 建議)
問題> 哪支影片觀看數最多?          → get_video_stats(limit=1)（🆕 U10）
```

- **這是 workflow 與 agent 的分水嶺**:pipeline 步驟由人寫死(線性);agent 呼叫哪個工具、幾次、何時停,由 LLM 決定(迴圈)。
- **防失控**:`AGENT_MAX_ITERATIONS=5` 硬上限;工具失敗回結構化錯誤、不中斷;弄壞 MCP server → CLI 報錯不 crash。
- **不碰發片流程**:純唯讀,`main.py` 完全不受影響。

> 💡 踩過的兩個真實 bug(都寫成雙語工程日誌 `INTERVIEW_NOTES.md`):
> ① MCP 序列化邊界造成 DB 無聲漏記(容錯 ≠ 靜音);② agent 把「即時候選」當「已選中」並捏造理由(工具語意歧義,非模型笨)。

---

## 觀看數追蹤（U10,選用）

把發布後的觀看數撈回來,和選片紀錄關聯 —— **發布 → 觀測** 的回饋迴圈第一步。

```powershell
python refresh_stats.py         # 撈所有已上傳影片的觀看數 → 寫進 DB（快照）
python query_runs.py --list     # 看到多一欄「觀看」
```

- **寫入端**:`refresh_stats.py` 打 YouTube `videos.list`,把 viewCount/likeCount/commentCount 寫回 `Run`,附 `stats_updated_at`(★記下「這數字何時撈的」★)。
- **讀取端**:`query_runs.py` 直接看;或問 agent「哪支觀看最多」(走 `get_video_stats`)。
- **快照 vs 即時**:讀到的是「上次 refresh 的數字」,不是即時 —— 要最新先跑 `refresh_stats.py`。這條紀律和 U8/U9 一脈相承(避免把即時與快照搞混,見上方 bug ②)。
- **需要唯讀授權**:讀觀看數要 `youtube.readonly` 權限,**與上傳 token 分開**(獨立 `token_readonly.json`)—— 讀取授權出問題也不影響發片。
- **優雅降級**:影片已刪/私人 → 該支跳過、記 warning,不 crash、不亂寫 0。

**誠實的定位**:目前只做到「觀測 + 留痕」。把觀看表現**回饋進選片**(依題材表現微調選片)是規劃中的下一步 —— 而且刻意定位為「軟性參考」,重要性硬門檻仍優先(避免為衝觀看而 clickbait 化)。

---

## 設定(config.py)

- `RSS_SOURCES` — 三來源網址與抓法(風傳媒需帶 UA)。
- `STOCK_KEYWORDS` / `EXCLUDE_KEYWORDS` — 股市篩選 / 排除詞(中港股)。
- `NEWS_COUNT`(3)/ `NEWS_POOL`(10)。
- `TTS_VOICE` / `VIDEO`(尺寸、fps)。
- **米米**:`MIMI_CLIPS`(intro/outro 路徑)、`USE_MIMI`、`MIMI_AREA_RATIO`(米米上半佔比 0.58)。
- **文案**:`OPENING_LINE` / `OUTRO_LINE`(開場/收尾旁白)、`OPENING_BUBBLE` / `OUTRO_BUBBLE`(泡泡)、`CHANNEL_SLOGAN`(封面+收尾共用標語)。
- **上傳**:`UPLOAD_ENABLED`(預設 False)、`YT_PRIVACY`(private)、`YT_CATEGORY_ID`、`YT_TAGS`、`YT_DISCLAIMER`、`YT_TITLE_HASHTAGS`(#Shorts #米米財經 #台股)、`YT_CLIENT_SECRETS` / `YT_TOKEN_FILE`。
- **生圖**:`USE_AI_IMAGE`、`IMAGE_MODEL`、`IMAGE_ASPECT`(16:9)、`IMAGE_TIMEOUT`(120)、`IMAGE_RETRY`、`IMAGE_DIR`、`IMAGE_DISCLAIMER`、`MIMI_REF_IMAGE`、`GEMINI_API_KEY`(.env)。
- **審圖**:`USE_IMAGE_REVIEW`、`REVIEW_MODEL`、`REVIEW_MAX_RETRY`(1)、`REVIEW_TIMEOUT`(60)。
- **DB**:`DB_URL`(預設 `sqlite:///mimi.db`)。
- **MCP**:`USE_MCP`(True;False = 走直接呼叫)、`DEDUP_DAYS`(7,查幾天歷史給選片 agent 參考)。
- **稽核 Agent(U9)**:`AGENT_MODEL`、`AGENT_MAX_ITERATIONS`(5)、`AGENT_AUDIT_DEFAULT_DAYS`(7)。
- **觀看數(U10)**:`YT_TOKEN_READONLY`(讀觀看數的獨立 token 檔)。

---

## 已知限制

- **米米素材需自備**:目前只放了 intro/outro;缺段自動退純字卡。
- **素材浮水印**:AI 工具生的素材可能帶浮水印,需素材端處理。
- **合成較慢**:米米版 CompositeVideoClip 疊層 + encoding,一支約 3~4 分鐘。
- **選片有隨機性**:LLM `temperature=0.5` + RSS 即時更新,每次選的 3 則可能不同(刻意保留)。
- **YouTube AI 標註**:API 無穩定欄位,需上傳後在 YT Studio 後台手動勾。
- **上傳未過 OAuth 驗證**:未驗證的 app 只能傳 private;要直接發 public 需送 OAuth 驗證,或手動把私人改公開。

> 註:風傳媒 RSS 曾一度回空 feed(伺服器端暫時性),已恢復正常。

---

## 後續擴充(架構已預留)

- 聲音:試不同 TTS 語音挑最搭米米的(voice 已可 config 切換)。
- GCP 部署 + 排程:影片生成+上傳放 Cloud Run Jobs、Cloud Scheduler 定時觸發(OAuth 需先本機授權好 token 帶上去)。
- Instagram 上傳:Graph API(商業帳號門檻高)。
- 多 LLM:`llm_service` 已抽象,加 class 即可換 Gemini / Claude。
- 轉場 / 背景音樂:`video.py` 加效果。
- MCP 再擴充:把生圖、上傳也包成 tool,讓 agent 自主決定整條發片流程。

> 各階段變更由架構規劃另出「修改指引」,整合進 `FINANCE_VIDEO_DEVELOPMENT.md` 後再據以實作。

---

## 免責聲明

內容由 AI 自動生成、僅供參考,不構成投資建議。投資有風險。
