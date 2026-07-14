# 米米財經 — AI 財經股市短影音自動化

自動把當日財經新聞做成一支**直式 9:16 短影音**(IG Reels / YouTube Shorts 通用),由 AI 虛擬貓主播「**米米**」在頭尾主持。
從抓 RSS、篩股市新聞、LLM 選題與改寫口播稿、TTS 配音、生成字卡與米米開場/收尾,到影片合成,全自動一鍵產出本機 mp4。

> 個人作品集專案。目標:整條 pipeline 跑通、能自動產出一支影片。
>
> **版本**:字卡版(MVP)→ UPDATE 1(米米全程)→ **UPDATE 2 節目化**(米米只在頭尾、新聞回純字卡)。
> 用 `config.USE_MIMI` 一鍵在「米米頭尾版」與「純字卡版」之間切換。

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
① 抓 RSS 財經新聞(3 來源:ETtoday / 自由時報 / 風傳媒)
② 解析 + 篩股市 + 清洗(剝 HTML、股市關鍵字 + 排除中港股)
③ 收斂候選池(去重 + 排序 → ~10 則)
④a LLM 選片:從候選挑 3 則「最重要」的 + 理由(硬門檻:必須直接跟股市有關)
④b LLM 改寫:口播稿(親切但專業)+ headline + 結構化 highlight + video_title + hashtag
④c 每則生 AI 示意圖(Gemini,Q版米米人物;失敗即 fallback 純字卡)
④d AI 審圖(擋編造數字/亂碼/真人/企業logo);不過 → 重生一次 → 再不過 → 退純字卡
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
- **容錯**:任一 RSS 來源失敗/回空 → skip 該來源、其他繼續;某段米米素材缺 → 該段退純字卡,都不讓整支崩。
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
├── publisher/           # YouTube 上傳
│   └── youtube.py       #   OAuth 認證 + videos.insert
├── db/                  # ⑨ 資料庫記錄(SQLAlchemy)
│   ├── models.py        #   Run 1 ──< Candidate
│   ├── database.py      #   engine / session / init_db
│   └── repository.py    #   save_run()
├── query_runs.py        # 查詢 DB:看每次「從候選選了哪 3 則、為什麼」
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
- **禁止畫公司 logo —— 即使新聞主角就是該公司**(否則講台積電就會畫 tsmc 商標)。
- **必須用 `image_config(aspect_ratio="16:9")` 強制橫式**(Gemini 不保證遵守 prompt 的「橫幅」,回直式會撐爆卡片)。
- 有圖 → YT 描述自動加「部分畫面為 AI 生成示意圖」。

---

## AI 審圖 agent(選用)

生圖後、上片前,用 **Gemini vision** 審查每張示意圖。審不過 → 帶問題**重生一次** → 再不過 → **該則退純字卡**。
**審圖永遠不會擋住發片** —— 它只決定「這則有沒有圖」。

**審查分兩級(關鍵設計):**

| 級別 | 項目 | 處置 |
|------|------|------|
| 🔴 **blocking**(傷可信度) | 編造的財務數據(EPS/毛利率/%/日期)、亂碼不成句、真人臉孔、真實企業 logo、嚴重離題 | **擋** → 重生 / 退純字卡 |
| 🟡 **minor**(純美觀) | 標籤重複、標籤過多、圖表裝飾刻度、構圖美感 | **放行**(只記 log) |

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
> `candidates.link` 已存並建索引 → **未來要做跨天去重,資料就在**。

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

> 各階段變更由架構規劃另出「修改指引」,整合進 `FINANCE_VIDEO_DEVELOPMENT.md` 後再據以實作。

---

## 免責聲明

內容由 AI 自動生成、僅供參考,不構成投資建議。投資有風險。
