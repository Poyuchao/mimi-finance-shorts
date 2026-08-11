# 米米財經 — AI 財經股市短影音自動化 — 開發規格文件

> 這是一個個人專案。目標:自動抓取財經(股市為主)新聞 → LLM 改寫成口播稿 → TTS 配音 → 生成字卡短影音(直式 9:16,IG Reels / YouTube Shorts 通用)→ 輸出本機 mp4。
>
> **給開發 agent 的核心提醒:這是分階段專案,一步一步做、每步都能單獨跑單獨驗,不要一次全寫完。先讓資料進來,再一路往影片推進。遇到不確定的地方停下來回報,不要自行猜測補完。**
>
> **📌 版本狀態:**
> - **字卡版 pipeline 已完成**(階段 0–6,`main.py` 可一鍵產出純字卡 mp4)。
> - **UPDATE 1(米米主播整合)**:加入 AI 虛擬貓主播「米米」,升級成「米米財經」。標記 🆕 UPDATE 1。
> - **UPDATE 2(節目化改版)**:🔴 **方向性修正** —— 米米**只在頭尾**(開場白/收尾),新聞段**回歸純字卡**;改成 4 階段(封面→米米開場白→3 純字卡新聞→米米收尾),補上封面動態標題、數字視覺化、聲音親切化。標記 🆕 UPDATE 2。**凡與 UPDATE 1 衝突處,以 UPDATE 2 為準**(尤其:新聞卡不再疊米米)。
> - **UPDATE 3(YouTube 自動上傳,本機版)**:`main.py` 產出 mp4 後,自動上傳 YouTube(YouTube Data API v3 + OAuth 2.0 Desktop,先傳 `private`)。標記 🆕 UPDATE 3。**只做本機版,GCP 部署/排程、IG 上傳都是之後。**
> - **UPDATE 4(新聞卡 AI 生成示意圖 + fallback)**:每則新聞用 AI 生一張財經示意圖放進新聞卡上半(下半保留數字視覺化/字幕/來源);**生圖失敗/超時 → 該則自動退回純字卡,絕不中斷發片**。`USE_AI_IMAGE` 開關。標記 🆕 UPDATE 4。**推翻 UPDATE 2 的 U5「新聞卡無 AI 生圖」決策**(實測 Gemini 財經示意圖夠到位)。
> - **UPDATE 5(AI 審圖 agent)**:生圖後、上片前,用 AI 審查每張示意圖(**編造數字/亂碼/重複標籤/真人/logo/離題**);不通過 → 帶問題**重生一次** → 再不過 → **該則退純字卡**。同時**修生圖 prompt**(禁編造數字、禁 caption)當第一道防線。`USE_IMAGE_REVIEW` 開關。標記 🆕 UPDATE 5。
> - **UPDATE 6(資料庫記錄)**:用 SQLAlchemy + 本機 SQLite(`mimi.db`)把**每次執行的候選 ~10 篇 + LLM 選中的 3 篇 + 選片理由**記錄下來,用於**事後驗證 LLM 選片品質**(不做去重、不做分析)。寫 DB 失敗**絕不中斷發片**。標記 🆕 UPDATE 6。
> - **UPDATE 7(GCP 部署)**:⏭️ **暫時跳過**(使用者決定先維持本機執行)。
> - **UPDATE 8(Finance News MCP Server)**:把「**抓新聞 + 查歷史選片**」封裝成本地 **stdio MCP server**,以標準協議把工具能力暴露給選片 agent,**取代硬編碼整合**。核心是「**不重寫功能,只用 MCP 暴露既有能力**」。`USE_MCP` 開關 + **MCP 失敗自動 fallback 回直接呼叫**(發片穩定性優先於架構潮度)。標記 🆕 UPDATE 8。
> - **UPDATE 9(選片品質稽核 Agent)**:做一個**獨立、純唯讀**的終端機 CLI `agent.py` —— 用**自然語言**詢問歷史選片品質,由 **LLM 自己決定**呼叫哪些 MCP 工具、呼叫幾次(function calling **決策迴圈**,非線性 pipeline),產出結構化稽核報告。新增 MCP tool `get_run_detail` + MCP **Resource** `runs://latest`。**★ 完全不碰發片流程(`main.py` 不改)★**。這是專案第一次「AI 當決策者」而非「AI 當單一工具」。標記 🆕 UPDATE 9。
> - 部分 UPDATE 另有搭配文件 `FINANCE_VIDEO_DEVELOPMENT 修改指引.md`。

---

## 0. 專案總覽

### 0.1 完整流程

```
① 抓 RSS 財經新聞(3 來源)
    ↓
② 解析 + 篩選股市新聞 + 清洗
    ↓
③ 收斂成「候選 N_pool 則」(去重、排序,預設 ~10 則)
    ↓
   🆕 UPDATE 8:①②③ 可改由 MCP tool `fetch_finance_news` 提供(USE_MCP=True)
   另有 tool `get_recent_selections` 查歷史選片給 agent 參考
   ★ MCP 失敗 → fallback 回直接呼叫 ①②③,發片不中斷 ★
    ↓
④a LLM 第一步:從候選中「挑 3 則 + 給挑選理由」
    ↓
④b LLM 第二步:改寫選中 3 則(口播稿 + 重寫標題 + highlight)+ 影片標題 + 標籤
    ↓
④c LLM 每則多產:🆕 UPDATE 2 結構化 highlight {value,trend,label}
    ↓
④d 🆕 UPDATE 4:每則新聞 → AI 生一張財經示意圖(image_service,失敗即 fallback 純字卡)
    ↓
④e 🆕 UPDATE 5:AI 審圖(review_service)—— 審編造數字/亂碼/重複標籤/真人/logo/離題
    不通過 → 帶問題重生一次 → 再不過 → 該則退純字卡(絕不擋發片)
    ↓
⑤ TTS 配音(edge-tts,台灣女聲)—— 唸 3 則 script + 🆕 UPDATE 2 開場白/收尾旁白(opening/outro.mp3)
    ↓
⑥ 生字卡(HTML/CSS → Playwright 截圖)
    🆕 UPDATE 2:封面卡(video_title)、新聞卡=純字卡+數字視覺化、開場白/收尾=透明泡泡卡
    🆕 UPDATE 4:新聞卡「有圖版(上半AI示意圖)/ 無圖版(純字卡)」依 image_path 有無切換
    ↓
⑦ 影片合成(MoviePy)→ 本機 mp4
    🆕 UPDATE 2:4 階段 6 片段 = 封面 + 米米開場白 + 3 純字卡新聞 + 米米收尾
    米米疊層(CompositeVideoClip)★ 只用在開場白/收尾 ★,新聞段回純字卡 ImageClip
    ↓
⑧ 🆕 UPDATE 3:自動上傳 YouTube(若 UPLOAD_ENABLED)
    videos.insert(resumable)+ OAuth 2.0 Desktop,先傳 private;失敗不影響已產出 mp4
    ↓
⑨ 🆕 UPDATE 6:寫入 DB(SQLite mimi.db)
    記錄「候選 ~10 篇 + LLM 選中的 3 篇 + 理由 + 位置」→ 事後驗證選片品質
    ★ 寫 DB 失敗只 log,絕不中斷發片 ★

──────────────────────────────────────────────
🆕 UPDATE 9:選片品質稽核 agent(獨立入口 `python agent.py`,★不在上面發片流程內★)
    自然語言問歷史選片品質 → LLM 用 function calling 自主呼叫 MCP 工具做多步推理 → 稽核報告
    純唯讀;不碰 main.py
```

> 🆕 **UPDATE 1 核心概念(仍成立)**:米米**不對嘴(no lip-sync)**→ 動作與當日內容無關 → **同一段米米動畫每天重複用** → AI 圖生影片只**手動預生成一次**建素材庫。
>
> 🆕 **UPDATE 2 核心轉向**:米米**只在頭尾**、新聞段**回純字卡**。理由:新聞段純字卡=專業/資訊聚焦,米米集中頭尾=萌/記憶點集中,形成「萌開場→專業新聞→萌收尾」反差。技術大幅簡化:新聞卡不疊米米、**米米素材只要 2 段(intro/outro)**、疊層邏輯只套頭尾。

### 0.2 已定案決策（不要自行更改，有疑問先問）

| # | 項目 | 結論 |
|---|------|------|
| 1 | 語言 | Python 3.11+，使用 venv 虛擬環境 |
| 2 | LLM | OpenAI **gpt-4o-mini**（API key 由使用者提供，放 env）|
| 3 | LLM 架構 | **抽一層 `llm_service` 介面**（provider-agnostic，之後可換 Gemini/Claude）|
| 4 | 財經定位 | **以股市為主**（台股/美股/個股/大盤，非廣義財經）|
| 5 | RSS 來源 | 3 來源財經版：ETtoday / 自由時報 / 風傳媒 |
| 6 | RSS 網址 | 放 `config.py` 當設定值（使用者填正確的財經版網址）|
| 7 | 篩選 | 股市關鍵字 + link 子網域（ETtoday finance）|
| 7b | 選片 | **`select_news` 不直接砍成 3**，而是收斂成「候選 ~10 則」（去重+排序）；真正挑 3 則交給 LLM |
| 8 | LLM 選片 | **LLM 第一步:從候選中挑 3 則 + 給挑選理由**（先選再改寫,分兩步呼叫）|
| 8b | LLM 產出 | **LLM 第二步:改寫選中 3 則** → 口播稿 + 重寫標題 + highlight + 影片標題 + hashtag |
| 9 | 標來源 | **結尾卡統一標**（「本集來源:ETtoday、自由時報、風傳媒」）|
| 10 | TTS | edge-tts，台灣女聲 `zh-TW-HsiaoChenNeural` |
| 11 | 字卡 | HTML/CSS 模板 + Jinja2 + Playwright 截圖（**純 HTML，不用 React**）|
| 12 | 影片合成 | MoviePy（底層 ffmpeg）|
| 13 | 影片規格 | 直式 9:16，1080×1920，約 60 秒 |
| 14 | 影片結構 | 開場卡 + 3 則新聞卡 + 結尾卡 |
| 15 | 平台 | IG Reels + YouTube Shorts **一支 9:16 通吃** + 架構預留 `platform` profile |
| 16 | 一支影片 | 3 則新聞，每則約 15-20 秒 |
| 17 | 輸出 | **本機 mp4**（本階段不發布、不排程）|
| 18 | 內容處理 | 改寫內容 + 重寫標題（不照抄原文，降低版權風險）|

#### 🆕 UPDATE 1（米米主播）新增決策

| # | 項目 | 結論 |
|---|------|------|
| M1 | 主播 | AI 虛擬貓主播「米米」,影片升級為「米米財經」 |
| M2 | 版面 | **B 案:米米上半 + 下半放字**（像新聞台:主播在上、資訊在下）|
| M3 | 米米素材 | **預生成素材庫**（AI 圖生影片先生好幾段,存 `assets/mimi/`,重複用）|
| M4 | 對嘴 | **不做 lip-sync**（貓嘴對配音會詭異）；米米只做自然動作(眨眼/擺頭)|
| M5 | 說話泡泡 | 米米旁的對話框,放 LLM 產的 `mimi_comment`(米米短評),CSS 畫 |
| M6 | 旁白分寸 | **`script` 旁白維持專業財經口吻**;米米的萌只放 `mimi_comment`,別把旁白貓化 |
| M7 | 下半字卡 | **沿用現有 news_card 風格**(深藍、大字),不重做 |
| M8 | 新聞圖 | **預設拿掉**（上半純米米,順便解版權顧慮）;可回報改為縮小塞下半 |
| M9 | 素材循環 | 素材短(如 8 秒)→ **loop 循環**撐滿該則旁白長度;`without_audio` 去自帶聲 |
| M10 | 開關 | **`USE_MIMI`** 一鍵切換米米版/純字卡版(對照與排查用)|

> ⚠️ UPDATE 2 修正:M2/M5/M6/M7/M8「新聞卡疊米米 + 泡泡」**取消**,新聞卡回純字卡。M3 素材由 5 段縮為 2 段(intro/outro)。疊層邏輯(M4/M9)保留,只用在頭尾。

#### 🆕 UPDATE 2（節目化改版）新增/修正決策

| # | 項目 | 結論 |
|---|------|------|
| U1 | 影片結構 | **4 階段 6 片段**:封面 → 米米開場白 → 3 則純字卡新聞 → 米米收尾 |
| U2 | 米米出現位置 | **只在開場白 + 收尾**;新聞段純字卡、無米米(退掉 UPDATE 1) |
| U3 | 米米素材 | **只要 2 段** `intro.mp4`(開場)、`outro.mp4`(收尾),使用者已備妥 |
| U4 | 封面 | 靜態純字卡:🐱米米財經 + `video_title`(LLM 動態,不寫死)+ 日期 |
| U5 | 新聞卡視覺 | **數字視覺化**:highlight 做成大數字+漲跌箭頭;**無 AI 生圖、無 RSS 新聞圖** |
| U6 | 漲跌顏色 | 🔴 **台股慣例:紅漲 ▲ / 綠跌 ▼ / 中性白**(修正指引 U2-4 的美股綠漲紅跌)|
| U7 | highlight 結構 | LLM 改回**結構化** `{value, trend:up/down/flat, label}`,由 LLM 判方向 |
| U8 | 開場白 | 米米動畫 + 泡泡「哈囉~我是米米!」+ 旁白引言(先固定 `OPENING_LINE`)|
| U9 | 收尾 | 米米動畫 + 泡泡「掰掰~明天見!」+ 旁白(固定 `OUTRO_LINE`)+ 來源標註 |
| U10 | 聲音 | 稿子親切但專業(開場/收尾更活潑、新聞段親切但專業);**全片同一語音**,voice 做成 config 可切 |
| U11 | 開關語意 | `USE_MIMI=False` = **封面 + 3 純字卡新聞 + 純字卡結尾(來源)**,不放任何米米 |

#### 🆕 UPDATE 3（YouTube 自動上傳,本機版)決策

| # | 項目 | 結論 |
|---|------|------|
| Y1 | 平台 | **只做 YouTube**(IG 之後);執行位置**本機**(`python main.py`),GCP 之後 |
| Y2 | API | YouTube Data API v3,`videos.insert`,**resumable** 分塊上傳 |
| Y3 | 認證 | OAuth 2.0,憑證類型 **Desktop app**;token 存本地(token.json)重複用,refresh 自動續期 |
| Y4 | 隱私 | **先 `private`**(私人 → 不需 OAuth 驗證審核);確認 OK 再由使用者決定改 public/unlisted |
| Y5 | 開關 | **`UPLOAD_ENABLED`**(config,預設 False);上傳失敗**不影響已產出的 mp4**(try/except 保護) |
| Y6 | 標題 | `video_title` + **`config.YT_TITLE_HASHTAGS`**(= `#Shorts #米米財經 #台股`)|
| Y7 | 描述 | 3 則 headline + **實際用到的來源** + 免責「本內容僅供參考,非投資建議」+ hashtags |
| Y8 | AI 標註 | 🔴 API 端**先不設欄位**(videos.insert 目前無穩定合成內容欄位)→ **上傳後 log 提醒使用者到 YT 後台手動勾** |
| Y9 | Shorts 長度 | 影片 ~82 秒 OK(YT 於 2024/10 起把 Shorts 上限放寬到 3 分鐘,不必砍到 60 秒) |
| Y10 | 機密 | `client_secrets.json`、`token.json` **加 .gitignore**,不 commit |

#### 🆕 UPDATE 4（新聞卡 AI 生成示意圖)決策

| # | 項目 | 結論 |
|---|------|------|
| I1 | 圖片來源 | **AI 生成示意圖**(不用 RSS 新聞圖,避版權);**推翻 UPDATE 2 的 U5** |
| I2 | 生圖時機 | LLM rewrite 之後、字卡渲染之前,每則一張 |
| I3 | fallback | 🔴 **生圖失敗/超時/例外 → 該則退回純字卡 + 數字視覺化**,絕不中斷 pipeline |
| I4 | 開關 | **`USE_AI_IMAGE`**(config,可一鍵關掉退回現狀) |
| I5 | 數字視覺化 | 無圖版保留;**★有圖版不顯示放大數字框★**(只留 highlight.label 小字,見實作)|
| I6 | provider/model | **Gemini `gemini-3.1-flash-lite-image`**(★「-image」變體才生圖★),SDK **`google-genai`**;抽象介面可換 |
| I7 | 生圖 prompt | 🔴 **實作後修正**:prompt **用中文寫**、風格「豐富的財經插畫(illustration,非 infographic)+ 正確繁中」;**圖上不放大標題**(標題交給卡片);**禁品牌 logo**;**所有人物一律用 Q版米米**(傳參考圖 `MIMI_REF_IMAGE`,不畫真人)|
| I7b | 有圖版新聞卡 | 米米財經 → 來源 → 標題 → 圖 → highlight.label 小字 → 字幕 |
| I8 | 逾時/重試 | 單張 **timeout 120 秒**、重試 1 次,再失敗即 fallback |
| I8b | 圖片比例 | 🔴 **強制 16:9**(`IMAGE_ASPECT` → `types.ImageConfig(aspect_ratio=...)`)—— Gemini 不保證遵守 prompt 的「橫幅」,曾回直式 768×1376 導致新聞卡爆版。**另加 CSS 防呆**(`.newsimg` max-height 660px + object-fit contain),怪比例也不撐爆版面 |
| I9 | 範圍 | **三則都生圖**(若太慢再回報改「只第一則」) |
| I10 | 標注 | 有用到 AI 圖 → YT 描述加「部分畫面為 AI 生成示意圖」 |
| I11 | 快取/機密 | 圖存 `output/images/`;`GEMINI_API_KEY` 放 .env(不 commit) |
| I12 | 審圖 | **UPDATE 4 不做** → 已於 **UPDATE 5** 實作(見下) |

#### 🆕 UPDATE 5（AI 審圖 agent)決策

| # | 項目 | 結論 |
|---|------|------|
| R1 | 兩道防線 | 🔴 **①修生圖 prompt(治本)+ ②審圖 agent(抓漏)**,缺一不可。只靠審圖會變成「常常生爛圖→重生→又爛→沒圖」,又花錢又沒圖 |
| R2 | 審什麼 | 審**生成的 AI 圖**(不是 render 後的字卡) |
| R3 | 模型 | Gemini **視覺文字模型**(`REVIEW_MODEL`,★不是 `-image` 變體★);抽象介面可換 provider |
| R4 | 輸出 | 🔴 **實作後修正**:JSON `{"pass": bool, "blocking": [...], "minor": [...]}`;**`pass` 只看 blocking** |
| R4b | ★審查分級★ | 🔴 **實作後新增,關鍵**:🔴blocking(傷可信度 → 擋)vs 🟡minor(純美觀 → 放行)。**不分級會為了「標籤重複」把好圖整張丟掉,而且重生常常更糟 → 變成「又花錢又沒圖」** |
| R5 | 不通過處置 | 把 **blocking**(★只餵 blocking,不拿美觀小事去干擾模型★)當修正指示餵回生圖 prompt → **重生一次**(`REVIEW_MAX_RETRY=1`)→ 再審;仍不過 → **該則退純字卡** |
| R6 | 審查 API 失效 | 🔴 **保守:當作「不通過」**(斷線/逾時/解析失敗都是)→ 最終退純字卡。**不發沒審過的圖**(保護財經頻道可信度) |
| R7 | 絕不擋發片 | 審圖只決定「該則有沒有圖」;**影片一定照常產出並上傳**(維持防呆原則) |
| R8 | 開關 | **`USE_IMAGE_REVIEW`**(False = 完全等同 UPDATE 4 現狀) |
| R9 | 接入點 | 寫在 `image_service.safe_generate()` 內部 → **`main.py` 不用改** |
| R10 | 範圍 | **這次只審圖**;審稿(口播稿是否偏離原新聞、標題誇大)留下次 |
| R11 | 生圖 prompt 修正 | ★**禁止圖上出現任何具體數字/財務數據/日期**★(理由要寫給模型:「你不知道真實數字,寫出來一定是編造的」);**禁 caption 圖說**;標籤 ≤4 個且不重複 |

**審查清單(★分兩級★,全部來自實際踩過的坑)**

🔴 **blocking(傷可信度 → 擋,觸發重生)**
- B1 **編造的財務數據**:圖上出現「看起來在陳述財經事實」的數字(實例:「台積電 2024 Q2 EPS +2.5元(舉例)、毛利率 53%」、日期「7/16」← AI 自己編的)
- B2 **亂碼/錯字/不成句**(實例:「Q版 Mimi 分虑 起路谘詢排梳 拨資者剮測」)
- B3 畫到**特定真實人物**(Q版米米貓 = 正確,不算違規)
- B4 **嚴重離題 / 扭曲到不能看**
- ☑ **允許(不擋)**:真實企業 logo/商標(tsmc/NVIDIA…,編輯性使用,2026-07-15 使用者定案放行)、台北101/城市天際線/K線/金幣等通用符號與地標

🟡 **minor(純美觀 → 放行,只記 log)**
- M1 **任何文字/標籤重複**、標籤數量偏多 → ★永遠 minor,絕不可放進 blocking★
- M2 圖表座標軸上的**裝飾性刻度數字**
- M3 構圖/美感/貼切度等**主觀意見**
- (實作定案)**圖上出現標題文字** → 接受,不擋(不傷可信度;模型難以完全壓制)

#### 🆕 UPDATE 6（資料庫記錄)決策

| # | 項目 | 結論 |
|---|------|------|
| D1 | 目的 | 🔴 **驗證 LLM 選片品質**(選片是黑箱 → 記下「從哪 10 篇選了哪 3 篇、為什麼」,事後可回查、調 prompt)|
| D2 | ORM / DB | **SQLAlchemy** + 本機 **SQLite**(`mimi.db`);上雲換持久化(UPDATE 7),ORM 不動 |
| D3 | 表結構 | 2 表:`runs`(一次執行)**(1) ──< (多)** `candidates`(該次候選,FK `run_id`) |
| D4 | 記錄範圍 | **候選 ~10 篇全記**,標記 `selected` / `position`(1~3) / `select_reason` |
| D5 | 寫入時機 | `main.py` **尾端**(上傳後)寫一次;開頭 `init_db()` 自動建表 |
| D6 | 失敗處理 | 🔴 **寫 DB 失敗只 log,絕不中斷發片**(記錄是附屬,不能拖垮主流程)|
| D7 | 這次不做 | ❌ 跨天去重 ❌ 資料分析/儀表板 ❌ 上雲持久化(但 `link` 已存,鋪好路)|
| D8 | 實作簡化 | ✅ **不需要 index 對映** —— 我們的 `select_top_news()` 回傳的 `picked` 本來就是完整候選 dict(含 `link`/`reason`),直接取即可(指引擔心的「index 對回 link」在本專案不存在)|

#### 🆕 UPDATE 8（Finance News MCP Server)決策

| # | 項目 | 結論 |
|---|------|------|
| P1 | 目的 | 🔴 **把工具能力以標準協議暴露給 agent,取代硬編碼整合** —— agent 與資料源解耦(換資料源/加工具只改 MCP server)|
| P2 | 協議 / 型態 | **MCP (Model Context Protocol)**,官方 Python SDK(`mcp`);**本地 stdio server**(同機子行程,不需對外網路)|
| P3 | 暴露的 tools | `fetch_finance_news`(抓+篩+收斂候選池)、`get_recent_selections`(查過去 N 天已選用的新聞)|
| P4 | 底層邏輯 | 🔴 **不重寫** —— tool 內部就是呼叫既有 `fetch_rss` / `parse_filter` / `select_news` / `repository` |
| P5 | fallback | 🔴 **MCP 連線/呼叫失敗 → 退回原本的直接呼叫**,發片絕不因 MCP 中斷 |
| P6 | 開關 | **`USE_MCP`**(False = 走原本直接呼叫,完全等同現狀)|
| P7 | 邊界 | 這次**只把「抓新聞 + 查歷史」上 MCP**;生圖/審圖/上傳暫不上(之後可擴充)|
| P8 | 歷史用途 | `get_recent_selections` 這次**只是「讓 agent 看得到最近發過什麼」**(可選地餵進選片 prompt),**不做強制去重**(與 D7 一致)|
| P9 | ⚠️ SDK 風險 | 🔴 **MCP SDK 更新快,不可照指引概念碼硬套** —— 必須先裝套件、**依當前版本的實際 API** 實作;不確定就停下來回報 |

> 💡 **誠實的效益評估**:現階段是「同程式、同機、呼叫自己的函式」,包成 MCP **功能完全一樣**,還多了子行程/序列化/async 成本與一個新失敗點。好處是**架構投資**(換資料源、加工具、agent 自主調度、跨專案共用時才兌現)。因此 `USE_MCP` 開關與 fallback 是必要的風險控制。

#### 🆕 UPDATE 9（選片品質稽核 Agent)決策

| # | 項目 | 結論 |
|---|------|------|
| Q1 | 定位 | **獨立維運工具**,不整合進 `main.py`;`python agent.py` 單獨執行。★這次完全不碰發片流程★ |
| Q2 | 介面 | **終端機 CLI**(`input()` 迴圈)。★不做網頁 UI、不接 Claude Desktop★ |
| Q3 | 讀寫 | 🔴 **純唯讀** —— 只查 DB / 抓新聞,不寫入、不改 prompt、不動發片 |
| Q4 | LLM | **OpenAI `gpt-4o-mini`**(沿用 `llm_service` 的 key 設定)|
| Q5 | 決策機制 | **OpenAI function calling**(`tools` 參數 + `tool_calls` 回傳)—— LLM 自己決定呼叫什麼 |
| Q6 | 工具來源 | 🔴 **一律透過既有 `mcp_client` 呼叫 MCP server**,★不准繞過 MCP 直接呼叫 repository★ |
| Q7 | 迴圈上限 | **`AGENT_MAX_ITERATIONS = 5`**(防無限迴圈);達上限用現有資訊作答並註記 |
| Q8 | 工具失敗 | 🔴 **結構化回傳錯誤給 LLM**(`{"error": "..."}`),不 raise、不中斷,讓 LLM 自己決定換方式 |
| Q9 | 輸出格式 | **結構化 JSON**(沿用審圖的 blocking / minor 分級概念),CLI 再印成易讀格式 |
| Q10 | 新增 MCP tool | `get_run_detail(run_id)` —— 查單次執行的完整候選 + 選中理由 |
| Q11 | 新增 MCP resource | `runs://latest` —— ★展示 MCP 的 **Resource** primitive(不只有 tools)★ |
| Q12 | 開關 | 無需開關(獨立檔案,不影響現有流程)|

> 💡 **這次的架構意義**:現有 pipeline 是**線性**(順序由 `main.py` 寫死);稽核 agent 是**迴圈**(呼叫哪個工具、幾次、何時停,由 LLM 決定)。這是本專案第一次讓 AI 從「填某一格的工具」升級成「規劃流程的決策者」—— 也是 workflow 與 agent 的分水嶺。成敗定義是「**agent 能自主做出多步推理、產出有用的稽核報告**」,不是功能多完整。
>
> 🔴 **沿用 UPDATE 6 的關鍵 prompt 經驗**:規則埋在條列清單裡 LLM 會忽略,改成「**回答前的自我檢查步驟**」才有效。稽核 prompt 也要這樣寫(見 §3.15)。

### 0.3 本階段「不做」（之後才做，別提前）

```
❌ 發布到 IG/YouTube（本階段只產本機 mp4）
❌ 排程自動化（先手動跑）
❌ 多 model 同時（先 OpenAI，架構可替換即可）
```

> 🆕 UPDATE 1:原本列在「不做」的「AI 虛擬人像」已升級為本次要做的**米米主播**,故從此清單移出。

---

## 1. 🔴 前置：環境設定（第一步，卡關級）

> 這專案依賴較多且有些是系統層（ffmpeg、瀏覽器），環境先跑通再往下。

### 1.1 虛擬環境 + 套件

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

`requirements.txt`：
```
feedparser          # 抓 RSS（自動解 gzip）
requests            # 風傳媒需帶 UA
beautifulsoup4      # 剝 description 的 HTML
openai              # LLM
edge-tts            # TTS
jinja2              # HTML 模板
playwright          # 字卡截圖
moviepy             # 影片合成
python-dotenv       # 讀 env
```

### 1.2 系統層依賴（重要，容易漏）

```bash
# Playwright 要裝瀏覽器
playwright install chromium

# MoviePy 需要 ffmpeg（系統層）
#   macOS:   brew install ffmpeg
#   Ubuntu:  sudo apt install ffmpeg
#   Windows: 下載 ffmpeg 加進 PATH
# 驗證：ffmpeg -version
```

### 1.3 env

```bash
# .env
OPENAI_API_KEY=sk-...        # 使用者提供
```

⚠️ `.env` 加進 `.gitignore`（別把 key commit 進 git）。

### 1.4 第一步驗證（跑這個確認環境 OK）

```
寫一個最小測試：import feedparser / openai / edge_tts / moviepy / playwright
→ 全部 import 成功 + ffmpeg -version 有輸出 + playwright chromium 裝好
→ 這步過了才往下
```

---

## 2. 專案結構

```
finance-video/
├── main.py                 # 串整條流程（最後才寫）
├── config.py               # 設定:RSS 網址、股市關鍵字、影片參數
├── fetch_rss.py            # ① 抓 RSS（3 來源）
├── parse_filter.py         # ② 解析 + 篩股市 + 清洗
├── select_news.py          # ③ 收斂候選池 ~10 則（去重、排序）
├── llm_service.py          # ④ LLM 選片+改寫（可替換介面,分兩步）★
├── tts.py                  # ⑤ TTS 配音
├── image_service.py        # 🆕 UPDATE 4:AI 生成新聞示意圖(抽象介面 + Gemini)
├── review_service.py       # 🆕 UPDATE 5:AI 審圖 agent(抽象介面 + Gemini vision)
├── card_render.py          # ⑥ 字卡（HTML→截圖）🆕 B案+透明背景+泡泡
├── video.py                # ⑦ 影片合成 🆕 CompositeVideoClip 疊層
├── templates/
│   ├── intro_card.html     # 開場卡模板
│   ├── news_card.html      # 新聞卡模板 🆕 上下分版面
│   └── outro_card.html     # 結尾卡模板
├── publisher/              # 🆕 UPDATE 3:上傳模組
│   ├── __init__.py
│   └── youtube.py          #   OAuth 認證 + videos.insert 上傳
├── db/                     # 🆕 UPDATE 6:資料庫記錄
│   ├── __init__.py
│   ├── models.py           #   Run + Candidate(SQLAlchemy)
│   ├── database.py         #   engine / session / init_db
│   └── repository.py       #   save_run + get_recent_selections(U8)+ get_run_detail(U9)
├── mcp_server/             # 🆕 UPDATE 8:MCP server(本地 stdio)
│   ├── __init__.py
│   └── finance_news_server.py  #   tools: fetch_finance_news / get_recent_selections
│                           #   🆕 U9 補:tool get_run_detail + resource runs://latest
├── mcp_client.py           # 🆕 UPDATE 8:啟動 server 子行程 + 呼叫 tools
├── agent.py                # 🆕 UPDATE 9:選片品質稽核 agent(獨立 CLI,純唯讀決策迴圈)
├── mimi.db                 # 🆕 UPDATE 6:SQLite 資料檔(gitignore)
├── assets/                 # 手動素材(非 pipeline 產)
│   └── mimi/               # 🆕 UPDATE 2:米米素材只要 2 段(頭尾)
│       ├── intro.mp4       #   開場白米米
│       └── outro.mp4       #   收尾米米
├── output/                 # 產出（mp4、中間檔）
│   ├── cards/              # 字卡 png（透明/不透明）
│   ├── audio/              # 配音 mp3(item_1..3 / opening / outro)
│   ├── images/             # 🆕 UPDATE 4:AI 生成示意圖
│   └── final.mp4
├── client_secrets.json     # 🆕 UPDATE 3:OAuth Desktop 憑證(使用者放,gitignore)
├── token.json              # 🆕 UPDATE 3:首次授權後產生(gitignore)
├── .env
├── .gitignore
└── requirements.txt
```

> 🆕 `assets/mimi/` 是**手動、一次性**放素材(UPDATE 2 只要 intro/outro 兩段)。檔名 config 化(`MIMI_CLIPS`)。缺檔那段 fallback 回純字卡(見 §3.8)。
> 🆕 `client_secrets.json`(使用者從 GCP 下載)、`token.json`(首次授權自動產生)**都加 .gitignore**,含機密別 commit。

> 模組化:一步一個檔，每個都能「單獨 import 進來測」。開發順序照 §8。

---

## 3. 各模組規格

### 3.1 `config.py` — 設定集中

```python
# RSS 來源（使用者填「財經版」網址）
RSS_SOURCES = [
    {
        "name": "ETtoday",
        "url": "https://feeds.feedburner.com/ettoday/finance",  # 使用者確認財經版網址
        "type": "ettoday",     # 決定用哪個 parser
        "needs_ua": False,
    },
    {
        "name": "自由時報",
        "url": "https://news.ltn.com.tw/rss/business.xml",       # 使用者確認財經版網址
        "type": "ltn",
        "needs_ua": False,      # feedparser 自動解 gzip
    },
    {
        "name": "風傳媒",
        "url": "...",                                            # 使用者確認財經版 channel
        "type": "storm",
        "needs_ua": True,       # bot detection，需帶 UA
    },
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."

# 股市關鍵字（以股市為主）
STOCK_KEYWORDS = [
    "台股", "加權指數", "收盤", "開盤", "盤中", "漲停", "跌停", "台積電",
    "股價", "美股", "道瓊", "那斯達克", "費半", "外資", "投信", "融資",
    "財報", "營收", "EPS", "上市", "上櫃", "股利", "除權息", "個股",
    # ...（開發時可迭代擴充）
]

NEWS_COUNT = 3               # 一支影片最終幾則(LLM 從候選中挑這麼多)
NEWS_POOL = 10               # select_news 收斂出的候選則數(丟給 LLM 挑選)
TTS_VOICE = "zh-TW-HsiaoChenNeural"

VIDEO = {
    "width": 1080, "height": 1920, "fps": 30,
}

# ── 🆕 UPDATE 1:米米主播 ──────────────────────────
# 🆕 UPDATE 2:米米素材只要 2 段(頭尾),news_a/b/c 不再需要
MIMI_CLIPS = {
    "intro": "assets/mimi/intro.mp4",   # 開場白
    "outro": "assets/mimi/outro.mp4",   # 收尾
}
USE_MIMI = True          # True=米米頭尾版;False=純字卡版(無頭尾米米,見 U11)
MIMI_AREA_RATIO = 0.58   # 開場白/收尾的米米上半佔比(看實際效果調)

# 🆕 UPDATE 2:開場白/收尾旁白 + 泡泡(先固定,之後可改 LLM 動態)
OPENING_LINE   = "哈囉~我是米米!今天股市有 3 件事,一起來看喵~"
OUTRO_LINE     = "今天的股市重點就到這~記得追蹤米米財經,我們明天見!喵!"
OPENING_BUBBLE = "哈囉~我是米米!"
OUTRO_BUBBLE   = "掰掰~明天見!"
CHANNEL_SLOGAN = "每天 60 秒,米米帶你回顧今日財經重點"   # 封面+收尾共用
# TTS_VOICE 已於上方定義;可切換試最搭米米的(edge-tts 其他台灣女聲 / 之後 OpenAI TTS)

# ── 🆕 UPDATE 3:YouTube 上傳 ──────────────────────
UPLOAD_ENABLED   = False        # 預設關(測 pipeline 時);要上傳才開 True
YT_PRIVACY       = "private"    # private / unlisted / public(先 private 測試)
YT_CATEGORY_ID   = "25"         # 25=News & Politics
YT_TAGS          = ["財經", "股市", "台股", "美股", "投資", "米米財經", "財經新聞"]
YT_CLIENT_SECRETS = "client_secrets.json"
YT_TOKEN_FILE    = "token.json"
YT_DISCLAIMER    = "本內容僅供參考,非投資建議。"

# ── 🆕 UPDATE 4:AI 生成新聞示意圖 ──────────────────
USE_AI_IMAGE     = True          # 一鍵開關(False = 退回純字卡,等同 UPDATE 2 現狀)
IMAGE_PROVIDER   = "gemini"      # 之後可換 provider
IMAGE_MODEL      = "gemini-3.1-flash-lite"   # ★ 使用者實測的 model(確切字串以能跑通為準)
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY")   # 放 .env,別 commit
IMAGE_TIMEOUT    = 120           # 單張生圖逾時(秒)
IMAGE_RETRY      = 1             # 失敗重試次數(再失敗就 fallback)
IMAGE_DIR        = "output/images"
IMAGE_DISCLAIMER = "部分畫面為 AI 生成示意圖"   # 加進 YT 描述
MIMI_REF_IMAGE   = "assets/mimi/米米財經主播4.jpg"   # 人物一律用 Q版米米

# ── 🆕 UPDATE 5:AI 審圖 agent ─────────────────────
USE_IMAGE_REVIEW  = True      # 開關(False = 不審圖,等同 UPDATE 4 現狀)
REVIEW_MODEL      = "gemini-3.1-flash-lite"   # ★視覺文字模型(不是 -image 變體)
REVIEW_MAX_RETRY  = 1         # 審不過 → 帶 issues 重生幾次(0 = 不重生,直接退純字卡)
REVIEW_TIMEOUT    = 60        # 單次審圖逾時(秒);逾時視為「不通過」(保守)

# ── 🆕 UPDATE 6:資料庫記錄 ────────────────────────
DB_URL = "sqlite:///mimi.db"  # 本機;上雲(UPDATE 7)改持久化連線,models/repository 不動

# ── 🆕 UPDATE 8:MCP ──────────────────────────────
USE_MCP    = True      # False = 走原本直接呼叫(等同 UPDATE 6 現狀)
DEDUP_DAYS = 7         # get_recent_selections 查幾天(給 agent 參考歷史,不強制去重)
# ★ 原設計的 MCP_SERVER_CMD 已取消:改由 mcp_client.py 自行推導
#   sys.executable + 絕對路徑 script + cwd=專案根(避免 "python" 抓到 Store stub)

# ── 🆕 UPDATE 9:選片品質稽核 agent ─────────────────
AGENT_MODEL              = "gpt-4o-mini"   # 沿用現有 LLM(與 llm_service 一致)
AGENT_MAX_ITERATIONS     = 5               # 決策迴圈硬上限(防無限迴圈)
AGENT_AUDIT_DEFAULT_DAYS = 7               # 稽核預設查幾天
```
⚠️ `.gitignore` 要加 `mimi.db`(資料檔不 commit)。

### 3.2 `fetch_rss.py` — 抓 RSS（3 來源）

```
職責:把 3 來源的 RSS 抓下來，回傳原始 entry 列表

各來源處理（已實測驗證）:
  • ETtoday:feedparser.parse(url) 直接抓
  • 自由:feedparser.parse(url) 直接抓（feedparser 自動處理 gzip）
  • 風傳媒:★ 先用 requests 帶 UA 抓 content，再 feedparser.parse(content) ★
    （直接 feedparser.parse(url) 會被 bot detection 擋）

實作:
  for source in RSS_SOURCES:
      if source["needs_ua"]:
          resp = requests.get(source["url"], headers={"User-Agent": USER_AGENT})
          feed = feedparser.parse(resp.content)
      else:
          feed = feedparser.parse(source["url"])
      # 每個 entry 附上來源名（source["name"]）

回傳:[{source, title, link, description, published, image?}, ...]
  → published 統一轉成 datetime（feedparser 的 published_parsed）
```

⚠️ 容錯:某來源抓失敗（timeout / 擋掉）→ **skip 該來源，其他繼續**（fault isolation，別讓一個掛掉全崩）。log 記下哪個失敗。

### 3.3 `parse_filter.py` — 解析 + 篩股市 + 清洗

```
職責:
  1. 清洗 description：
     • 用 BeautifulSoup 剝掉 HTML
     • 抽出「純文字內文」（給 LLM 用）
     • 抽出「圖片 URL」（<img src> 或 ETtoday 的 image 欄位，字卡素材用）
     • 去掉「《詳全文...》」這類尾巴
  2. 篩「股市」新聞:
     • ETtoday:link 是 finance 子網域 → 財經（優先）
     • 所有來源:title + 內文 含 STOCK_KEYWORDS 任一 → 算股市
     • 兩者其一成立即保留
  3. 回傳乾淨的股市新聞列表

回傳:[{source, title, clean_text, image_url, link, published}, ...]
```

⚠️ 關鍵字誤判提醒:短詞會誤中（「台積電做公益」不是股市新聞）。先求有，跑起來看結果再迭代調整關鍵字。這是正常的調校過程。

### 3.4 `select_news.py` — 收斂成候選池（不直接選最終 3 則）

```
職責:從篩出的股市新聞，收斂成「候選池」丟給 LLM 挑（config.NEWS_POOL = 10）
     ★ 注意:最終挑哪 3 則(NEWS_COUNT)是 LLM 的工作，不在這裡做 ★

邏輯（MVP 先簡單）:
  1. 去重:標題高度相似的只留一則（先用簡單比對:標題前 N 字相同 / 包含關係）
  2. 排序:按發布時間新→舊
  3. 取前 NEWS_POOL 則(候選池)

回傳:候選 ~10 則（結構同上）→ 交給 llm_service 挑 3 則

⚠️ 若「篩出的股市新聞 < NEWS_POOL」→ 有幾則給幾則(LLM 就從較少的候選挑)
⚠️ 若「候選 < NEWS_COUNT(3)」→ 最終有幾則做幾則 + log 提示（別硬湊/報錯）

🟡 已知潛在風險(2026-07-26 記錄,暫不處理):
   select_news 只「排序」不「過濾日期」→ 若某天 RSS 夾帶舊新聞、或今天有效新聞
   不足 NEWS_POOL,舊聞會補進候選池,LLM 可能選到。另 `published` 缺失的新聞會被
   `datetime.min` 墊底(排最後),正常進不了前 10,但稀少日可能浮上來。
   ★ 當日實測候選 10 則全為當天、無缺時間,故非急迫 bug。★
   未來若要加固:排序前加 MAX_AGE_DAYS 過濾;但需先決定「無 published 者嚴格丟/寬鬆留」
   政策,且防「RSS 時間格式異常 → 全被濾掉 → 發不出片」。
```

### 3.5 `llm_service.py` — LLM（🔴 可替換介面，★ 分兩步呼叫）

```
職責:LLM 負責兩件事,分兩次呼叫(先選再改寫):
  第一步 select:從候選 ~10 則挑 NEWS_COUNT(3) 則 + 給挑選理由
  第二步 rewrite:把選中的 3 則改寫成口播稿 + 重寫標題 + hashtag

★ 架構要求:抽象介面（provider-agnostic）★
  class LLMService(ABC):
      def generate(self, prompt: str) -> str: ...
  class OpenAIService(LLMService):
      # 用 openai gpt-4o-mini 實作
  → main 用介面，不直接綁 OpenAI
  → 之後換 Gemini/Claude 只加一個 class，不改其他 code
  → select / rewrite 兩步各自組 prompt,底層都走同一個 generate()

─────────────────────────────────────────────
第一步 select_top_news(candidates) — 挑 3 則
  輸入:候選 ~10 則,每則附 index(對回原始新聞用) + {title, clean_text, source}
  要求 LLM 只回 JSON:
  {
    "selected": [
      { "index": 3, "reason": "為什麼選這則(重要性/時效/影響)" },
      { "index": 0, "reason": "..." },
      { "index": 7, "reason": "..." }
    ]
  }
  ✅ 階段 2 先驗這步:印出 LLM 選了哪 3 則 + 理由,確認選片品質
  ⚠️ index 要能對回 select_news 的候選(用來配圖片/來源)

─────────────────────────────────────────────
第二步 rewrite_scripts(selected_3) — 改寫選中的 3 則
  輸入:選中的 3 則 {title, clean_text, source}
  要求 LLM 只回 JSON（明確要求「只回 JSON，無其他文字」）:
  {
    "video_title": "今日股市重點...",       // 整支影片標題
    "hashtags": ["#台股", "#台積電", ...],
    "items": [
      {
        "headline": "重寫後的短標題（字卡大字用，精簡有力）",
        // 🆕 UPDATE 2:highlight 改「結構化」,方向由 LLM 判
        "highlight": { "value": "+30%", "trend": "up", "label": "外資買超" },
        "script": "口播稿（親切但專業、順、適合念，20-30秒的量）",
        "mimi_comment": "喵~台積電要擴廠,這波有看頭!"   // UPDATE 1 遺留;UPDATE 2 頭尾版新聞卡用不到,保留欄位不強制
      },
      ...
    ]
  }
  ✅ 階段 2 再驗這步:印出稿子,確認「夠口語、股市角度、有改寫不照抄」

★ 內容要求（寫進 rewrite prompt）:
  • 改寫,不照抄原文（用自己的話講事實，降低版權風險）
  • 口播稿要「口語化」（給人聽的,不是書面語）
  • 以股市角度切入（漲跌、影響、數字）
  • headline 精簡（字卡大字，不超過約 15 字）
  • 繁體中文、台灣用語

🆕 UPDATE 2:highlight 結構化 + script 親切化（寫進 rewrite prompt）:
  • highlight = {value, trend, label}:
    - value:核心數字/短詞(如「+30%」「890億」「擴大1倍」);盡量含數字,容許質化
    - trend:"up"(利多/上漲) / "down"(利空/下跌) / "flat"(中性/質化),★ 由 LLM 判方向
    - label:一句話重點(如「外資買超」「AI算力過剩」)
    → 字卡依 trend 上色+箭頭:up=紅▲ / down=綠▼ / flat=白(★ 台股慣例 紅漲綠跌,見 U6)
  • script「親切但專業」:口語、有溫度、像跟朋友講,但資訊準確、保持專業(親切≠幼稚)
  • (mimi_comment:UPDATE 2 頭尾版新聞卡不顯示,LLM 可省略或保留,不影響)

🆕 UPDATE 2:開場白/收尾旁白:
  • 先「固定」(config.OPENING_LINE / OUTRO_LINE),不經 LLM;之後要動態引言再改成 LLM 產 opening_line

錯誤處理（兩步都適用）:
  • LLM 回傳非 JSON / 解析失敗 → retry 一次；再失敗 → log + raise（讓使用者知道）
  • select 若挑出的則數 < 3(候選本來就不足) → 有幾則做幾則 + log
  • （這步不 skip，因為是核心；跟抓取的 fault isolation 不同）
```

### 3.6 `tts.py` — TTS 配音

```
職責:把每則 script（口播稿）→ 語音檔 mp3

用 edge-tts:
  import edge_tts
  communicate = edge_tts.Communicate(script_text, voice="zh-TW-HsiaoChenNeural")
  await communicate.save("output/audio/item_1.mp3")
  （edge-tts 是 async，注意用 asyncio）

回傳:每則對應的 mp3 路徑 + 時長（時長給影片用:字卡顯示多久 = 配音多長）
  → 取得 mp3 時長:可用 moviepy 的 AudioFileClip(path).duration

🆕 UPDATE 2:除了 3 則新聞 script,也要幫「開場白」「收尾」旁白配音:
  • config.OPENING_LINE → output/audio/opening.mp3
  • config.OUTRO_LINE   → output/audio/outro.mp3
  • 這兩段語氣口語親切(米米人設);新聞段 script 親切但專業(全片同一 voice,靠稿子區分)
```

### 3.7 `card_render.py` — 字卡（HTML → 截圖）

```
職責:用 HTML/CSS 模板 + Jinja2 填資料 → Playwright 截圖成 png

流程:
  1. Jinja2 載入 templates/xxx_card.html
  2. 填資料（render）:
     • intro_card:日期、「今日股市」標題
     • news_card:序號、來源、新聞圖、headline、highlight、字幕
     • outro_card:「本集來源:ETtoday、自由時報、風傳媒」+ 追蹤提示
  3. Playwright:
     page.set_viewport_size({"width":1080,"height":1920})
     page.set_content(rendered_html)
     page.screenshot(path="output/cards/xxx.png")

模板（純 HTML/CSS,不用 React）:
  • 尺寸固定 1080×1920（直式 9:16）
  • 開場/新聞/結尾各一個模板
  • CSS 自由設計（圓角、字體、配色 → 頻道視覺識別）
  • 新聞圖從 image_url 載入（<img src>）

⚠️ 新聞圖版權:作品集/測試階段 OK；未來公開發布要留意（可換自有圖庫/AI 生圖）
⚠️ platform profile 預留:結尾卡的 CTA 文字用變數（ig="追蹤" / yt="訂閱"），現在都放，之後可依 platform 切
```

#### 🆕 UPDATE 1:card_render 改 B 案版面（上半留米米 + 說話泡泡 + 透明背景）

```
核心:字卡從「滿版不透明」改成「下半內容 + 透明背景」,讓米米動畫透在上半。

1. news_card.html 改「上下分」:
   • 上半(約 MIMI_AREA_RATIO=58% 高):透明區 + 說話泡泡
     - 移除原本「新聞圖」區(改由米米動畫填,不再放 RSS 新聞圖)→ 預設拿掉新聞圖
     - 說話泡泡:CSS 畫對話框(圓角 + 尖角指向米米),放 mimi_comment
   • 下半(約 42% 高):深藍底,放 headline / highlight / 字幕 / 來源(沿用現有樣式)

2. ★ 截圖改透明背景 ★:
   page.screenshot(path=..., omit_background=True)
   → body 背景設 transparent;下半的深藍底是「下半那個 div 自己的背景」
   → 上半透明(米米透出來)、下半有底

3. intro_card / outro_card 同樣改透明背景(上半米米、下半資訊)

4. 說話泡泡:純 CSS(圓角框 + 尖角 + 半透明白底/品牌色,文字清楚)

⚠️ 泡泡樣式/位置、MIMI_AREA_RATIO:先做一版,使用者看了再調
⚠️ USE_MIMI=False 時 → 回主規格的滿版不透明字卡(不加泡泡、不透明)
```

#### 🆕 UPDATE 2:card_render 卡片重整（封面 + 純字卡新聞+數字視覺化 + 開場白/收尾泡泡卡）

```
UPDATE 2 的字卡分三類:

1. 封面卡 cover_card.html(靜態、不透明):
   • 🐱 米米財經 + {{ video_title }}(LLM 動態)+ {{ date }}

2. 新聞卡 news_card(★ 回歸純字卡:不透明、無米米、無泡泡 ★):
   • 頂部識別條「🐱 米米財經 i/3」(品牌保留)
   • headline 大字
   • ★ 數字視覺化區:highlight={value,trend,label}
     - up   → 紅色 + ▲(台股慣例)
     - down → 綠色 + ▼
     - flat → 白色大字(質化,不強求箭頭)
     - CSS 做(圓角框、大字重、對比色)
   • 字幕(script)、來源
   • 無 RSS 新聞圖、無 AI 生圖

3. 開場白/收尾卡 opening_card / outro_card(透明泡泡卡,給米米疊層用):
   • 透明背景(omit_background)+ 說話泡泡(OPENING_BUBBLE / OUTRO_BUBBLE)
   • 收尾卡另放「本集來源:…」
   • 沿用 UPDATE 1 的透明泡泡做法(base_mimi.html 那套)

USE_MIMI=False:封面 + 3 純字卡新聞 + 一張純字卡結尾卡(來源+追蹤字樣),不產開場白/收尾泡泡卡。
```

### 3.8 `video.py` — 影片合成

```
職責:字卡 png + 配音 mp3 → 合成 final.mp4

【純字卡版(USE_MIMI=False,保留)】用 MoviePy:
  片段 = []
  # 開場卡（固定 ~3 秒）
  intro = ImageClip("cards/intro.png").set_duration(3)
  片段.append(intro)
  # 每則新聞卡（顯示時長 = 該則配音時長）
  for i in N:
      dur = 該則配音時長
      clip = ImageClip(f"cards/news_{i}.png").set_duration(dur).set_audio(AudioFileClip(f"audio/item_{i}.mp3"))
      片段.append(clip)
  # 結尾卡（固定 ~3 秒）
  outro = ImageClip("cards/outro.png").set_duration(3)
  片段.append(outro)

  final = concatenate_videoclips(片段, method="compose")
  final.write_videofile("output/final.mp4", fps=30)

可選（之後加）:轉場淡入淡出、背景音樂
platform profile 預留:輸出檔名/CTA 可依 platform 區分（現在先出一支通用）
```

#### 🆕 UPDATE 1:米米版合成（USE_MIMI=True）—— CompositeVideoClip 疊層

```
從「ImageClip(純圖)」升級成「VideoClip(米米動畫) + 透明字卡疊上層」。

每則片段 = 米米動畫(底層,循環撐滿) + 透明字卡 PNG(上層) + 旁白:
  底層 = 米米動畫:
    VideoFileClip → resize 對齊 1080 寬 → 擺上半(center/top)
                 → loop 循環撐滿該則旁白長度 → without_audio(去自帶聲)
  上層 = 透明字卡:
    ImageClip(透明 PNG) → set_duration(dur)
  合成:
    CompositeVideoClip([米米, 字卡], size=(1080,1920)).set_audio(旁白mp3)
  開場/結尾同理(用 intro.mp4 / outro.mp4)→ 最後 concatenate 串起來

技術點:
  • 尺寸:素材 720×1280 → resize 對齊寬,擺上半;下半是透明字卡的深藍底 → 湊成 1080×1920
  • 循環:素材 8 秒、旁白 18 秒 → loop 撐滿(眨眼素材適合循環,頭尾接順)
  • 去背景音:素材可能自帶聲 → without_audio(),只用我們的旁白
  • ⚠️ 去浮水印:AI 工具生的素材可能有浮水印 → 回報使用者處理素材,pipeline 不去浮水印
  • ★ fallback:某米米素材檔不存在 → 那則退回「純字卡」(不透明字卡),不讓整支崩

⚠️ 效能:CompositeVideoClip + loop + 多段 → 比純圖慢,正常。先求「成功、效果對」再談速度。
⚠️ 實作用 MoviePy 2.x API(with_duration/with_position/resized/effects),指引範例是 1.x 寫法。
```

#### 🆕 UPDATE 2:4 階段 6 片段組裝（米米疊層只用在頭尾）

```
★ 米米疊層「只用在開場白+收尾」;新聞段回純字卡(ImageClip)。★

片段組裝(USE_MIMI=True):
  片段 = []
  # ① 封面:純字卡(靜態,~3 秒)
  片段.append( ImageClip("cards/cover.png").with_duration(3) )
  # ② 開場白:米米動畫 intro.mp4 + 透明泡泡卡 + opening.mp3  ← 疊層(make_mimi_segment)
  片段.append( make_mimi_segment(intro.mp4, "cards/opening.png", dur=opening時長, audio=opening.mp3) )
  # ③ 三則新聞:純字卡(不疊米米)  ← 回主規格 ImageClip 做法
  for i in 3:
      片段.append( ImageClip(f"cards/news_{i}.png").with_duration(dur_i).with_audio(item_i.mp3) )
  # ④ 收尾:米米動畫 outro.mp4 + 透明泡泡卡 + outro.mp3  ← 疊層
  片段.append( make_mimi_segment(outro.mp4, "cards/outro.png", dur=outro時長, audio=outro.mp3) )
  final = concatenate_videoclips(片段, method="compose")

其中 make_mimi_segment = UPDATE 1 已寫好的疊層邏輯(米米底層 loop+without_audio + 透明字卡上層 + 旁白)。

fallback(逐段):intro.mp4 或 outro.mp4 缺 → 該段退純字卡(用不透明 opening/outro 卡),不整支崩。

USE_MIMI=False(見 U11):封面 + 3 純字卡新聞 + 純字卡結尾卡(來源),不做 ②④ 兩段米米。
```

### 3.9 `main.py` — 串整條（最後寫）

```
把 ①→⑦ 串起來:
  # 🆕 UPDATE 8:候選池改由 MCP 提供(失敗則 fallback 直接呼叫)
  if config.USE_MCP:
      try:
          candidates, recent = asyncio.run(
              mcp_client.fetch_candidates_via_mcp(config.NEWS_POOL, config.DEDUP_DAYS))
      except Exception as e:
          log(f"MCP 取得失敗,fallback 直接呼叫:{e}")   # ★ 發片不中斷 ★
          candidates = select_news(parse_filter(fetch_rss()), pool=config.NEWS_POOL)
          recent = []
  else:
      candidates = select_news(parse_filter(fetch_rss()), pool=config.NEWS_POOL)
      recent = []

  picked = llm_service.select_top_news(candidates, n=3)      # ④a LLM 選片
  # (可選 U8-4)把 recent 帶進 select prompt,讓 agent 看得到最近發過什麼
  llm_result = llm_service.rewrite_scripts(picked)           # ④b LLM 改寫

  # 🆕 UPDATE 4:每則生圖(rewrite 後、card_render 前;失敗回 None 不中斷)
  if config.USE_AI_IMAGE:
      for i, item in enumerate(llm_result.items, 1):
          item.image_path = image_service.safe_generate(item, i)   # 內含 timeout/retry/fallback
  else:
      for item in llm_result.items: item.image_path = None

  audio = tts(llm_result.items)                              # script → mp3
  cards = card_render(llm_result, audio_durations)           # 🆕 依 image_path 有無渲染兩種新聞卡版面
  video = compose(cards, audio)                              # 🆕 依 USE_MIMI 走米米疊層 or 純字卡
  → output/final.mp4

  # 🆕 UPDATE 3:產出後自動上傳(接在最後)
  if config.UPLOAD_ENABLED:
      try:
          from publisher import youtube
          yt = youtube.get_authenticated_service()
          meta = build_youtube_metadata(llm_result)          # 標題+#Shorts、描述+免責、tags
          vid = youtube.upload_video(yt, "output/final.mp4", meta)
          log(f"已上傳 YouTube: https://youtu.be/{vid}（{config.YT_PRIVACY}）")
          log("提醒:記得到 YT 後台勾選『AI/合成內容』標註")
      except Exception:
          log("上傳失敗,但 mp4 已保留,可手動上傳")   # ★ 不讓上傳失敗弄丟已產出的影片
  else:
      log("UPLOAD_ENABLED=False,略過上傳,只產本機 mp4")

  # 🆕 UPDATE 6:寫入 DB(最尾端;失敗只 log,絕不中斷發片)
  try:
      # picked 已是完整候選 dict(含 link/reason)→ 不需 index 對映(見 D8)
      selected_links = {p["link"] for p in picked}
      reasons        = {p["link"]: p.get("reason", "") for p in picked}
      positions      = {p["link"]: i + 1 for i, p in enumerate(picked)}
      repository.save_run(session, status="success",
                          video_title=llm_result["video_title"],
                          youtube_url=youtube_url,      # 沒上傳就 None
                          candidates=candidates,        # ★ 候選 ~10 篇全給
                          selected_links=selected_links,
                          reasons=reasons, positions=positions)
  except Exception as e:
      log(f"寫入 DB 失敗(不影響發片):{e}")   # ★ 記錄是附屬,不能拖垮主流程

main.py 開頭:db.database.init_db()(首次自動建表)

每步之間 log 進度，任一步失敗有清楚錯誤訊息
🆕 UPDATE 1:compose/card_render 依 config.USE_MIMI 切換米米版 or 純字卡版
```

### 3.10 `publisher/youtube.py` — YouTube 上傳（🆕 UPDATE 3）

```
職責:OAuth 認證 + 上傳影片到 YouTube。兩個核心函式:

1. get_authenticated_service():
   • 有 token.json → 讀取,過期用 refresh token 自動續期
   • 無 token.json(首次)→ InstalledAppFlow.from_client_secrets_file(
         client_secrets.json, scopes=["...youtube.upload"])
       creds = flow.run_local_server(port=0)   # 本機開瀏覽器授權
       → 存 creds 到 token.json
   • 回傳 build("youtube","v3", credentials=creds)

2. upload_video(youtube, file_path, metadata) -> video_id:
   • videos.insert + MediaFileUpload(resumable=True)
   • body.snippet = {title, description, tags, categoryId}
   • body.status = {privacyStatus(先 private), selfDeclaredMadeForKids: False}
   • resumable 分塊上傳(next_chunk 迴圈 + 進度 log)
   • 500/502/503/504 → 指數退避重試

★ AI 內容標註(Y8):videos.insert 目前無穩定的合成內容欄位 →
  不設 API 欄位,上傳後 log 提醒使用者到 YT 後台手動勾。不確定就回報,別瞎猜欄位名。

⚠️ 缺 client_secrets.json → 給明確錯誤提示(叫使用者先在 GCP 建憑證)。
```

★ metadata(build_youtube_metadata,見 U3-3):
```
標題:{video_title} #Shorts
描述:今日股市 3 大重點:1.{h1} 2.{h2} 3.{h3}
      📊 本集來源:{實際用到的來源}
      ⚠️ {YT_DISCLAIMER}
      #Shorts #財經 #股市 #台股 #米米財經
tags:config.YT_TAGS
隱私:config.YT_PRIVACY
```

### 3.11 `image_service.py` — AI 生成新聞示意圖（🆕 UPDATE 4）

```
職責:輸入一則新聞內容 → 產出一張財經示意圖(png 路徑);失敗回 None(不 raise)。

★ 抽象介面(跟 llm_service 同哲學):
  class ImageService(ABC):
      def generate(self, prompt: str, out_path: str) -> str | None: ...
  class GeminiImageService(ImageService):
      # SDK: google-genai(from google import genai);model: config.IMAGE_MODEL(3.1 Flash-lite)
      # 回傳的 image bytes 存成 out_path;成功回路徑,失敗回 None

★ safe_generate(item, idx) -> str | None(防呆包裝,🔴 最重要):
  🆕 UPDATE 5:改成「生圖 → 審圖 → (不過則帶 issues 重生) → 再審」的迴圈:

  issues = []
  for attempt in 1..(1 + REVIEW_MAX_RETRY):        # 預設 2 輪
      prompt = _build_image_prompt(item, fix_issues=issues)   # 第2輪帶上一輪的問題
      path   = 生圖(timeout=IMAGE_TIMEOUT,失敗/逾時 → 下一輪或回 None)
      if not USE_IMAGE_REVIEW: return path         # 沒開審圖 → 直接用
      result = review_service.safe_review(path, item)          # 🆕 審圖
      if result["pass"]: return path               # ✅ 通過
      issues = result["issues"]                    # ❌ 記下問題,下一輪修正
  return None                                      # 兩輪都不過 → 該則退純字卡

  • 生圖 timeout=IMAGE_TIMEOUT(120s)、審圖 timeout=REVIEW_TIMEOUT(60s),
    都用 concurrent.futures 強制逾時
  • 檢查:回傳檔案存在且非過小/損毀,否則當失敗
  • ★任何情況都不 raise;回 None = 該則用純字卡版面(不擋發片)★

★ 生圖 prompt 要求(🆕 UPDATE 5 修正,見 R11):
  • prompt **用中文寫**(英文 prompt → 圖上中文亂碼)
  • 風格:財經新聞「**illustration/插畫**」(★不要用 infographic 這個詞★,會招來一堆標籤文字)
  • 主軸:「請根據新聞內容,產出一張對應的示意圖」
  • ★禁止:圖上出現任何「具體數字/財務數據/日期」(EPS、毛利率、%、股價、年份)★
    理由要寫給模型:「你不知道真實數字,寫出來一定是編造的;數字由字卡負責」
  • ★禁止:圖說 caption / 描述文字(會亂碼)★
  • 標籤:最多 3~4 個簡短情境標籤(如「資金匯出」「台股走勢」),★不可重複★
  • ★禁止:圖上放新聞標題/大標題橫幅(標題由字卡顯示,避免重複)★
  • ★人物一律 Q版米米★:傳參考圖 config.MIMI_REF_IMAGE,所有官員/分析師/投資人
    都用這隻貓的 Q 版形象 → 品牌一致 + 絕不畫真人
  • ★禁止:品牌 logo / 真實企業商標★
  • 比例:image_config(aspect_ratio=IMAGE_ASPECT="16:9")強制橫式(見 I8b)
  • fix_issues:若上一輪審圖有問題,把 issues 當「上一張的問題,請務必避免」附在 prompt 末

⚠️ Gemini SDK/model 用法不確定就回報,別瞎猜 API。GEMINI_API_KEY 放 .env。
```

### 3.12 `review_service.py` — AI 審圖 agent（🆕 UPDATE 5）

```
職責:看一張生成的示意圖 + 該則新聞 → 判斷「能不能上片」,回 JSON。

★ 抽象介面(跟 llm_service / image_service 同哲學):
  class ReviewService(ABC):
      def review(self, image_path: str, item: dict) -> dict: ...
  class GeminiReviewService(ReviewService):
      # SDK: google-genai;model: config.REVIEW_MODEL(視覺文字模型,★非 -image 變體★)
      # 輸入:圖(Part.from_bytes)+ 中文審查 prompt(附該則 headline/label)
      # 輸出:只回 JSON {"pass": bool, "issues": [str, ...]}

★ 審查清單(寫進審查 prompt,6 項):
  1. 圖上有沒有「具體數字/財務數據/日期」→ ★一律視為編造,不通過★
  2. 有沒有亂碼、錯字、不成句的文字
  3. 標籤有沒有重複
  4. 有沒有畫到「特定真實人物」(應該全是 Q版米米貓)
  5. 有沒有品牌 logo / 真實企業商標
  6. 圖有沒有離題、元素扭曲畸形

★ safe_review(image_path, item) -> dict(防呆包裝):
  • timeout=config.REVIEW_TIMEOUT(60s),強制逾時
  • 🔴 審查 API 失效/逾時/JSON 解析失敗 → ★保守:回 pass=False(blocking=["審查失敗"])★
    (不發沒審過的圖;最終就是該則退純字卡)
  • 任何情況都不 raise
```

### 3.13 `db/` — 資料庫記錄（🆕 UPDATE 6）

```
職責:把每次執行的「候選 ~10 篇 + LLM 選中的 3 篇 + 理由」記下來,事後驗證選片品質。

db/models.py — SQLAlchemy models(2 表,runs 1──< candidates 多):
  class Run:            # 一次 pipeline 執行
      id, run_date(index), created_at, status(success/failed/skipped),
      video_title, youtube_url
      candidates = relationship("Candidate", back_populates="run")

  class Candidate:      # 該次的候選新聞(~10 篇全記)
      id, run_id(FK→runs.id), title, source, link(index), published,
      selected(Bool)        # ★ 有沒有被 LLM 選中
      position(1/2/3)       # ★ 選中的話是第幾則
      select_reason(Text)   # ★ LLM 的選片理由(選中才有)
      created_at
      run = relationship("Run", back_populates="candidates")

db/database.py:
  engine = create_engine(config.DB_URL)     # 本機 sqlite:///mimi.db
  SessionLocal = sessionmaker(bind=engine)
  init_db()      → Base.metadata.create_all(engine)(首次自動建表)
  get_session()  → SessionLocal()

db/repository.py:
  save_run(session, *, status, video_title, youtube_url,
           candidates, selected_links, reasons, positions) -> run_id
    • 建 1 筆 Run → flush 拿 run.id
    • 對候選 ~10 篇各建 1 筆 Candidate,link 在 selected_links 裡就標
      selected=True + position + select_reason
    • commit,回 run.id

  🆕 UPDATE 8 補:
  get_recent_selections(session, days) -> [{title, link}, ...]
    • 查過去 days 天內 selected=True 的新聞(join Run 用 run_date 過濾)
    • 供 MCP tool `get_recent_selections` 使用(讓 agent 看得到最近發過什麼)

  🆕 UPDATE 9 補:
  get_run_detail(session, run_id) -> dict | None
    • 取單次執行的完整資訊:候選清單 + 哪 3 則被選中 + 選片理由 + position
    • 用既有 Run/Candidate models + relationship;找不到 → 回 None
    • 回傳 {run_id, created_at, candidates: [{title, link, selected, position, reason}]}
    • datetime 沿用 U8 的 _jsonable() 處理

⚠️ 上雲(UPDATE 7):Cloud Run Job 無狀態 → 容器內 mimi.db 跑完就消失!
   屆時改持久化(SQLite+GCS 下載/上傳,或換 DB)→ 只改 config.DB_URL + 加上下載,
   models/repository 不用動。
```

### 3.14 `mcp_server/` + `mcp_client.py` — MCP 工具層（🆕 UPDATE 8）

```
職責:用 MCP 標準協議,把「抓新聞 + 查歷史選片」暴露成 agent 可呼叫的 tools。
     ★ 不重寫功能 —— tool 內部就是呼叫既有模組。★

mcp_server/finance_news_server.py(本地 stdio server):
  暴露兩個 tool(list_tools 回傳含 JSON Schema 的工具描述):

  1. fetch_finance_news(pool_size: int = 10)
     → 內部:fetch_rss() → parse_filter() → select_news(pool=pool_size)
     → 回候選池 JSON(⚠️ datetime 要轉字串才能序列化)

  2. get_recent_selections(days: int = 7)
     → 內部:repository.get_recent_selections(session, days)
     → 回 [{title, link}, ...](過去 N 天已選用的新聞)

mcp_client.py:
  fetch_candidates_via_mcp(pool_size, dedup_days) -> (candidates, recent)
    • 以 stdio 啟動 server 子行程 → initialize → call_tool ×2 → 解析 JSON
    • ⚠️ MCP 是 async → main.py(同步)呼叫處要用 asyncio.run() 包

🔴 SDK 風險(指引兩次警告):
   MCP Python SDK 的實際 API(class 名 / 裝飾器 / types)更新快,
   ★必須先安裝套件、依「當前版本的官方文件與實際 API」實作★,
   不可照指引的概念碼硬套;不確定就停下來回報。

🆕 UPDATE 9 補(mcp_server 再加):
  tool get_run_detail(run_id: int) -> dict
     → 內部:repository.get_run_detail(session, run_id)
     → docstring 🔴 是 agent 的使用手冊,要寫「做什麼 + 何時該用」,不只寫參數

  resource runs://latest -> str
     → @app.resource("runs://latest");回最近一次執行的摘要
     → ★展示 MCP 的 Resource primitive(唯讀資料,與 tool 的「有副作用動作」區分)★
```

### 3.15 `agent.py` — 選片品質稽核 agent（🆕 UPDATE 9）

```
職責:獨立、純唯讀的終端機 CLI。用自然語言問歷史選片品質,
     LLM 用 function calling 自主決定呼叫哪些 MCP 工具、幾次,產出結構化稽核報告。
     ★ 不碰發片流程;不繞過 MCP 直接呼叫 repository。★

決策迴圈(核心):
  1. 啟動:透過 mcp_client 取得工具清單(MCP discovery)
  2. 把 MCP tool schema 轉成 OpenAI tools 格式(★inputSchema→parameters 欄位名不同,需轉換★)
  3. messages = [system_prompt, user_question]
     for i in range(AGENT_MAX_ITERATIONS):
         resp = openai.chat(messages, tools=tools)
         if resp.tool_calls:                       # LLM 要查資料
             for call in resp.tool_calls:          # ★一輪可能多個 call,全部跑完再回覆★
                 result = mcp_client.call_tool(...) # 走 MCP;失敗回 {"error":...} 不中斷
                 messages.append(tool_result)       # ★每筆帶對應 tool_call_id,漏了 400★
             continue                               # 回頭讓 LLM 再判斷
         else:
             return resp.content                    # LLM 給答案 → 結束
     # 迴圈用盡 → 用現有資訊作答並註記「達迭代上限」

System prompt 要點(★沿用 UPDATE 6 經驗:規則要放進「回答前自我檢查」才有效★):
  身分:米米財經選片品質稽核員,可呼叫工具查歷史選片
  稽核重點:① 主體重複(同一次選了同公司多則)② 來源偏食(三來源失衡)
           ③ 題材集中(連續多天同類型)④ 理由品質(具體 vs 空泛)
  ★ 回答前自我檢查:我真的查了資料嗎?每個問題都對得上 run_id 嗎?嚴重度分級對嗎?
  輸出 JSON:{period, runs_analyzed, issues:[{type,severity,run_id,detail,suggestion}],
             source_distribution, summary}

CLI:while True → input("問題> ") → run_agent(q);exit/quit/空 → 結束
  ★ Demo 用:每次工具呼叫都印出來(如 [工具] get_run_detail(run_id=12)),
    才看得出 agent 在做多步推理。

驗證(分兩階段):
  單輪:「最近選了哪些新聞」→ 應只呼叫 1 次工具就作答
  多輪:「這週選片品質有沒有問題」→ ★先查 recent、發現異常再查 detail,至少 2 輪★
  容錯:弄壞 MCP server → agent 不 crash,回報錯誤
```

---

## 4. 🔴 開發順序（分階段，每步單獨驗）

> **不要一次全寫完。** 照這個順序，每步「跑起來、看到結果」再往下。這樣出錯容易定位。

```
階段 0:環境（§1）
  → import 全通 + ffmpeg + playwright chromium
  ✅ 驗證:最小 import 測試跑過

階段 1:抓 + 篩 + 收斂候選（資料層）
  → fetch_rss + parse_filter + select_news
  ✅ 驗證:印出「今天篩出的候選股市新聞 ~10 則」（source + title + clean_text 前段 + image_url + link + time）
  → 這步是地基，先確認資料真的進來、篩得對(關鍵字有無誤判/漏抓)

階段 2:LLM(先選再改寫,分兩步)
  → llm_service（可替換介面 + OpenAI 實作）
  ✅ 驗證 2a(選片):候選 ~10 則餵進去,印出 LLM 挑的 3 則 + 挑選理由 → 確認選片品質
  ✅ 驗證 2b(改寫):選中 3 則改寫,印出 JSON(video_title + 每則 headline/highlight/script)
  → 確認口播稿「夠口語、以股市角度、有改寫不照抄」

階段 3:TTS
  → tts
  ✅ 驗證:把一則 script 轉成 mp3，能播、聽得懂、台灣女聲

階段 4:字卡
  → card_render + templates
  ✅ 驗證:產出 intro/news/outro 的 png，打開看版面對不對（1080×1920）

階段 5:影片合成
  → video
  ✅ 驗證:字卡 + 配音 → final.mp4，能播、圖音對得上、約 60 秒

階段 6:串起來
  → main.py
  ✅ 驗證:一鍵跑，從抓 RSS 到產出 mp4 全自動
```

### 🆕 UPDATE 1:米米整合開發順序（階段 0–6 已完成後才做）

```
階段 M-1:LLM 加 mimi_comment
  → 改 prompt + 輸出格式
  ✅ 驗證:印出 JSON,確認每則有 mimi_comment 且「短、有米米味、script 仍專業」

階段 M-2:字卡改版(B 案 + 透明背景 + 說話泡泡)
  → 改 news_card.html(上下分)、加泡泡、omit_background;intro/outro 同步
  ✅ 驗證:產出字卡 PNG,確認「上半透明、下半深藍有內容、泡泡樣式對」
    (PNG 透明區在看圖軟體可能顯示成棋盤格,正常)

階段 M-3:單則合成測試 ★最關鍵,先單獨驗★
  → video.py 先只合成「一則」:米米動畫 + 透明字卡 + 旁白
  ✅ 驗證:播這一則,確認「米米在上半動、字卡在下半、泡泡在、旁白對、米米沒自帶聲音」
  → 這步過了才做整支(整支重跑慢又難定位)

階段 M-4:整支合成
  → 開場 + 3 則 + 結尾 全部米米版
  ✅ 驗證:播 final.mp4,整支流暢、米米萌、資訊清楚

階段 M-5:fallback + 開關
  → USE_MIMI 開關、素材缺失 fallback 純字卡
  ✅ 驗證:USE_MIMI=False 退回純字卡版;某素材檔改名(模擬缺失)不整支崩
```

> 🔴 素材依賴:M-1、M-2 不需素材即可做。**M-3 起需要 `assets/mimi/` 至少一段米米 mp4** → 到 M-3 前停下等使用者放素材。

### 🆕 UPDATE 2 節目化開發順序（UPDATE 1 完成後接續）

```
階段 U2-1:新聞卡回歸純字卡 + 數字視覺化
  → news_card 拿掉米米/透明,回不透明純字卡 + 加數字視覺化區(highlight={value,trend,label})
  → 漲跌色:台股 紅漲▲/綠跌▼/中性白
  ✅ 驗證:產出新聞卡 PNG,確認「純字卡、數字大而清楚、無米米、顏色對」

階段 U2-2:封面用 video_title
  → 新增 cover_card,顯示 LLM 的 video_title(動態)+ 日期
  ✅ 驗證:封面顯示當天動態標題(不是寫死的)

階段 U2-3:開場白 + 收尾兩段(套 UPDATE 1 疊層,只用在這兩段)
  → opening/outro 旁白 TTS(opening.mp3/outro.mp3)+ 透明泡泡卡 + 米米動畫疊層
  ✅ 驗證:單獨合成「開場白」+「收尾」,確認米米動、泡泡在、旁白對
  → 素材:需 assets/mimi/ 的 intro.mp4 / outro.mp4(使用者已備妥)

階段 U2-4:4 階段 6 片段串接
  → video.py 組裝:封面 + 開場白 + 3 純字卡新聞 + 收尾
  ✅ 驗證:播整支 final.mp4,確認 4 階段順、米米只在頭尾、新聞純字卡

階段 U2-5:聲音優化
  → script prompt 調口語親切(但專業)+ 試換語音(config 可切)
  ✅ 驗證:聽整支,確認「親切但專業」、跟米米搭
```

### 🆕 UPDATE 3:YouTube 上傳開發順序(先驗認證,再上傳,再整合)

```
一次性準備(使用者做,agent 說明 + code 缺檔給提示):
  • GCP 建專案 + 啟用 YouTube Data API v3
  • OAuth 憑證(Desktop app)→ client_secrets.json 放根目錄
  • OAuth 同意畫面加自己為測試使用者
  • pip 裝 google-api-python-client / google-auth-oauthlib / google-auth-httplib2
  • .gitignore 加 client_secrets.json、token.json

階段 U3-1:認證單獨測 ★基礎,先過★
  → 只做 get_authenticated_service()
  ✅ 驗證:首次跑 → 開瀏覽器授權 → 產生 token.json;再跑一次「不用重新授權」
  → 這步需使用者本人在瀏覽器登入 + 同意(agent 無法代做)

階段 U3-2:上傳單獨測(用現成 final.mp4)
  → upload_video() 傳一支現有 mp4,隱私 private
  ✅ 驗證:YT 後台(頻道→內容)看到這支「私人」影片,metadata 對

階段 U3-3:整合 main.py
  → UPLOAD_ENABLED=True,python main.py 一條龍(產出 + 上傳)
  ✅ 驗證:跑完 → mp4 + 自動傳上 YT(私人)+ log 出網址

階段 U3-4:容錯 + 開關
  → UPLOAD_ENABLED=False 略過上傳;上傳失敗不影響已產出的 mp4
  ✅ 驗證:關開關只產 mp4;模擬上傳失敗(斷網)→ mp4 還在、有錯誤 log
```

> 🔴 素材/憑證依賴:U3 的 code(publisher/config/main 整合)不需憑證即可寫;**U3-1 起需要 client_secrets.json + 使用者本人首次瀏覽器授權** → 寫到認證測試前停下等使用者。

### 🆕 UPDATE 4:AI 生成新聞示意圖開發順序

```
階段 U4-1:image_service 單獨測(不碰 pipeline)★先過品質★
  → 抽象介面 + GeminiImageService,拿一則假新聞的 headline/highlight 生一張圖
  ✅ 驗證:output/images/ 有圖,打開看「像不像財經示意圖」
        ★檢查:有沒有畫到特定真人?中文有沒有亂碼?★ 不 OK → 這步調 prompt
  → 需 GEMINI_API_KEY + 確認 model 名(使用者提供)

階段 U4-2:fallback 機制單獨測
  → safe_generate:timeout / 例外 / 回 None
  ✅ 驗證:故意斷網 or 給錯 key → 不 raise、回 None、log 警告

階段 U4-3:新聞卡兩種版面
  → news_card.html 加 {% if image_path %} 分支(圖用 base64 內嵌較保險)
  ✅ 驗證:分別渲染「有圖」「無圖」各一張 PNG,兩種版面都好看;數字/字幕/來源都在

階段 U4-4:整合 main + 三則混合情境
  ✅ 驗證:三則都有圖 → 影片好看
  ✅ 驗證:★模擬「第 2 則生圖失敗」→ 該則自動純字卡,影片仍正常產出上傳★
  ✅ 驗證:USE_AI_IMAGE=False → 完全等同現狀(純字卡)

階段 U4-5:YT 描述加 AI 標注
  → 有用 AI 圖時,描述加 IMAGE_DISCLAIMER
  ✅ 驗證:上傳後看 YT 描述有標注
```

> 🔴 依賴:U4-1 起需要 GEMINI_API_KEY + 確認 Gemini 生圖 model/SDK → 寫到生圖測試前停下等使用者確認 model。

### 🆕 UPDATE 5:AI 審圖 agent 開發順序

```
階段 U5-1:修生圖 prompt(第一道防線,治本)
  → 禁具體數字/財務數據/日期、禁 caption 圖說、標籤 ≤4 不重複
  ✅ 驗證:生一張,確認「不再有編造的數字」「不再有亂碼 caption」

階段 U5-2:review_service 單獨測 ★最關鍵★
  → ReviewService 抽象介面 + GeminiReviewService + safe_review
  ✅ 驗證:拿「已知有問題的那張圖」(編造 EPS +2.5元/毛利率53% + 底部亂碼 caption)
        餵進去 → ★審查員必須抓得出來、回 pass=false + 正確的 issues★
  ✅ 再拿一張「乾淨的圖」→ 應回 pass=true(不能亂擋)
  → 這步過了才往下(審不出問題的審查員沒有意義)

階段 U5-3:接進 safe_generate(生 → 審 → 重生一次 → 再審 → 退純字卡)
  ✅ 驗證:單則跑,看 log 的流程(通過 / 重生 / 最終退純字卡)

階段 U5-4:整合 main.py 完整跑
  ✅ 驗證:三則正常產出;審圖失敗的那則自動用純字卡、影片照常上傳
  ✅ 驗證:USE_IMAGE_REVIEW=False → 完全等同 UPDATE 4 現狀
```

> 💰 成本:每則最多 2 次生圖 + 2 次審圖(審圖用文字模型,便宜)。`REVIEW_MAX_RETRY=0` 可關掉重生。

### 🆕 UPDATE 6:資料庫記錄開發順序

```
階段 U6-1:models + database + 建表
  → db/models.py(Run + Candidate)、db/database.py(engine/session/init_db)
  ✅ 驗證:跑 init_db() → mimi.db 生成、runs / candidates 兩表建好(欄位/FK 對)

階段 U6-2:寫入單獨測
  → repository.save_run() 塞一筆假資料(1 run + 10 candidates,其中 3 篇 selected)
  ✅ 驗證:查 DB → 1 筆 run + 10 筆候選;3 筆 selected=True 且有 reason/position;
        run_id 關聯正確

階段 U6-3:整合進 main
  → main 開頭 init_db();尾端組 selected_links/reasons/positions + save_run(try/except)
  ✅ 驗證:正常跑 python main.py → mimi.db 多一筆完整記錄
  ✅ 驗證:★故意讓寫 DB 出錯(如改壞 DB_URL)→ 影片照樣產出/上傳,不中斷★

階段 U6-4:驗證選片(這功能的目的)
  → 查某天的 run → 看 10 篇候選 + 哪 3 篇 selected + 理由
  ✅ 驗證:能清楚看出「LLM 從這 10 篇選了哪 3 篇、為什麼」
  → 可用 DB Browser for SQLite(免費 GUI)或寫個小查詢腳本
```

### 🆕 UPDATE 8:MCP Server 開發順序

```
階段 U8-0:先確認 SDK 實際 API ★別照概念碼硬套★
  → pip install mcp,查當前版本的官方寫法(Server/裝飾器/types/stdio)
  ✅ 驗證:能寫出一個最小可跑的 stdio server + client 往返
  → 這步不確定就停下來回報

階段 U8-1:MCP server 單獨測
  → finance_news_server.py:兩個 tool,內部呼叫既有 fetch_rss/parse_filter/select_news/repository
  → 補 repository.get_recent_selections(days)
  ✅ 驗證:list_tools 列得出兩個 tool;call fetch_finance_news 回候選池;
        call get_recent_selections 回歷史(DB 已有 UPDATE 6 的資料可測)
  ⚠️ candidates 的 datetime 要能 JSON 序列化

階段 U8-2:MCP client 單獨測
  → mcp_client.fetch_candidates_via_mcp()
  ✅ 驗證:client 啟動 server 子行程 → 拿到 (candidates, recent)

階段 U8-3:整合 main + ★驗 fallback★
  ✅ 驗證:USE_MCP=True 跑完整 pipeline(透過 MCP 拿新聞)
  ✅ 驗證:★故意弄壞 MCP(改壞 server 路徑)→ fallback 直接呼叫,發片不中斷★
  ✅ 驗證:USE_MCP=False → 完全等同現狀

階段 U8-4:(可選)歷史參考進選片
  → 把 recent 帶進 select_top_news 的 prompt
  ✅ 驗證:agent 選片時看得到「最近發過的」
```

### 🆕 UPDATE 9:選片品質稽核 Agent 開發順序

```
階段 U9-1:補 MCP tool get_run_detail
  → repository.get_run_detail(session, run_id)(先寫,單獨測)
  → finance_news_server.py 加 @app.tool() get_run_detail(docstring 寫清楚何時該用)
  ✅ 驗證:給真實 run_id → 回傳完整候選+理由,且可 JSON 序列化

階段 U9-2:補 MCP resource runs://latest
  → @app.resource("runs://latest") 回最近一次摘要
  ✅ 驗證:client 端 list_resources() / 讀得到內容
  → 這步的重點是「展示 Resource primitive」,功能簡單即可

階段 U9-3:agent.py 決策迴圈(核心)★最容易卡:先打通 schema 轉換★
  → 先寫「MCP inputSchema → OpenAI tools parameters」的最小轉換測試,確認格式對得上
  → 再寫決策迴圈(tool_call_id 對應、一輪多 call、AGENT_MAX_ITERATIONS 上限)
  → system prompt 含「回答前自我檢查」;每次工具呼叫印出來
  ✅ 驗證 單輪:「最近選了哪些新聞」→ 1 次工具呼叫就作答
  ✅ 驗證 多輪:「這週選片品質有沒有問題」→ ★先 recent 再 detail,≥2 輪推理★
  ✅ 驗證 容錯:弄壞 MCP server → agent 不 crash,結構化回報錯誤

階段 U9-4:config + 確認零副作用
  → AGENT_MODEL / AGENT_MAX_ITERATIONS / AGENT_AUDIT_DEFAULT_DAYS
  ✅ 驗證:★main.py 完全不受影響,發片流程正常★
```

---

## 5. 實作 Checklist（開發 agent 打勾用）

### 階段 0 環境
- [x] venv + requirements.txt 裝好（Python 3.14.3）
- [x] playwright install chromium
- [x] ffmpeg 系統層裝好（ffmpeg 8.1.2,winget Gyan.FFmpeg）
- [x] .env（OPENAI_API_KEY）+ .gitignore
- [x] 最小 import 測試通過（test_env.py 全 PASS）

### 階段 1 資料層
- [x] config.py（RSS 來源、股市關鍵字、NEWS_COUNT/NEWS_POOL 參數;另加 EXCLUDE_KEYWORDS 排除中港股）
- [x] fetch_rss:3 來源（ETtoday 直接 / 自由 gzip / 風傳媒帶 UA）+ 容錯 skip
- [x] parse_filter:剝 HTML、抽圖、篩股市（子網域 + 關鍵字 + 排除詞）
- [x] select_news:去重 + 排序 + 取 NEWS_POOL(候選 ~10 則,不砍成 3)
- [x] ✅ 印出候選 ~10 則確認(已調整關鍵字:移除「台幣」、加排除中港股)

### 階段 2 LLM(分兩步)
- [x] llm_service:抽象介面 + OpenAIService（gpt-4o-mini）
- [x] select_top_news:從候選挑 3 則 + 理由,回 JSON(selected[{index,reason}])
- [x] rewrite_scripts:改寫選中 3 則,回 JSON（video_title/hashtags/items）
- [x] prompt:改寫、口語化、股市角度、繁中台灣用語（選片 prompt 已加「市場級/結構性優先」權重）
- [x] JSON 解析失敗 retry 一次(兩步都要;response_format=json_object)
- [x] ✅ 印出 LLM 選的 3 則+理由,再印口播稿,確認品質

### 階段 3 TTS
- [x] tts:edge-tts 台灣女聲，script → mp3
- [x] 取得每則時長（AudioFileClip.duration,給影片用）
- [x] ✅ 播一則確認

### 階段 4 字卡
- [x] templates:intro / news / outro（純 HTML/CSS，1080×1920,base.html 共用樣式）
- [x] Jinja2 填資料 + Playwright 截圖
- [x] 結尾卡標來源（本集來源:...,列出實際用到的來源）
- [x] platform CTA 用變數預留（PLATFORM_CTA:ig=追蹤/yt=訂閱)
- [x] ✅ 開 png 看版面（無圖時 📈 漸層 fallback）

### 階段 5 影片
- [x] video:MoviePy 合成，字卡時長 = 配音時長
- [x] 開場/結尾固定秒數（各 3 秒）
- [x] ✅ 播 final.mp4 確認圖音同步（1080×1920 H.264/AAC,~60-78 秒）

### 階段 6 串接
- [x] main.py 串整條 + 進度 log（7 步進度輸出）
- [x] ✅ 一鍵產出 mp4

### 卡關立刻停手回報(開發實況)
- [x] 財經版 RSS 網址 → 已確認:風傳媒 channel_id/2、ETtoday feedburner/finance、自由 business.xml 皆可用
- [x] 股市關鍵字誤判 → 已回報並調整:移除「台幣」(誤中社會/政治新聞)、新增排除詞篩掉中港股
- [~] LLM 口播稿品質 → 目前可接受;使用者決定「看最終產出再迭代 prompt」(句尾虛詞待調)
- [x] ffmpeg / playwright → 安裝順利,無卡關
- [x] 篩出股市新聞 < 3 則 → 未發生(每日約篩出 70-80 則,候選池充足)

### 🆕 UPDATE 1 米米整合 Checklist(已完成)

**LLM**
- [x] M2:LLM 輸出加 `mimi_comment`（短、米米味、script 保持專業）
- [x] ✅ 印出 JSON 確認

**字卡**
- [x] M3:news_card 改 B 案上下分（上半透明留米米 + 泡泡,下半沿用深藍字卡）
- [x] M3:說話泡泡 CSS（放 mimi_comment,尖角指向米米）
- [x] M3:截圖 `omit_background=True`（透明背景）
- [x] M3:intro/outro 同步改（另有 base_mimi.html 共用透明樣式）
- [x] M3:新聞圖預設拿掉（已與使用者確認 A 案）
- [x] ✅ 開 PNG 確認上半透明/下半有內容/泡泡

**影片合成**
- [x] M4:video.py 改 CompositeVideoClip（米米動畫底層 + 透明字卡上層）
- [x] M4:米米 resize + 擺上半 + loop 撐滿 + without_audio（MoviePy 2.x:resized/with_effects([vfx.Loop])/without_audio）
- [x] M4:素材缺失 fallback 純字卡（1:1 對應,缺哪段哪段退純字卡;card_render 另產 plain/ 不透明卡)
- [x] ✅ 先驗「單則」(M-3) 再驗整支(M-4)

**config**
- [x] M5:MIMI_CLIPS、USE_MIMI 開關、MIMI_AREA_RATIO(=0.58)
- [x] ✅ USE_MIMI=False 能退回純字卡版(已驗:出滿版純字卡 MVP)

**卡關實況**
- [x] 米米素材:使用者放了 `mimi/米米眨眼.mp4`(720×1280/8s/24fps),已複製為 assets/mimi/news_a.mp4
- [~] 素材有浮水印(DeeVid AI)→ 已回報使用者從素材端處理,pipeline 不去浮水印
- [x] CompositeVideoClip 合成:成功,米米版比純字卡慢/檔案較大(正常)
- [x] 透明背景 + 疊層:效果良好(米米上半、字卡下半、泡泡指向米米)

### 🆕 UPDATE 2 節目化 Checklist(已完成)

**結構 & 影片**
- [x] U2-1:video.py 改 4 階段 6 片段(封面/開場白/3純字卡/收尾)
- [x] U2-1:米米疊層「只用在開場白+收尾」,新聞段回純字卡(退掉 UPDATE 1 新聞卡疊米米)

**封面 & 數字**
- [x] U2-2:封面卡用 video_title(動態標題)+ 日期(cover_card.html)
- [x] U2-4:news_card 數字視覺化(highlight={value,trend,label}→大數字+箭頭,台股紅漲▲綠跌▼)
- [x] U2-4:無 AI 生圖、無 RSS 新聞圖

**開場白 & 收尾**
- [x] U2-3:開場白旁白 TTS(opening.mp3)+ 泡泡「哈囉~我是米米!」(opening_card.html)
- [x] U2-3:收尾旁白 TTS(outro.mp3)+ 泡泡「掰掰~明天見!」+ 來源(closing_card.html)
- [x] U2-3:開場/收尾套 UPDATE 1 疊層(intro.mp4/outro.mp4,make_mimi_segment)

**聲音 & config & LLM & 文案**
- [x] U2-5:script prompt 調口語親切(但專業)
- [~] U2-5:試換語音(voice 已可用 config.TTS_VOICE 切;多聲線試聽待做,可選)
- [x] U2-6:MIMI_CLIPS 改 2 段、OPENING/OUTRO 文案、USE_MIMI 語意(U11)
- [x] U2-7:rewrite JSON 的 highlight 改結構化 {value,trend,label}
- [x] 文案誠實化:封面/開場/收尾改「回顧財經重點」,收斂成 config.CHANNEL_SLOGAN

**卡關實況**
- [x] intro.mp4/outro.mp4:使用者已放 米米開場/收尾.mp4,已複製對齊檔名;皆 720×1280 8s
- [x] 素材浮水印:開場/收尾素材無浮水印(比 UPDATE 1 的 news_a 乾淨)
- [x] 風傳媒 RSS 失效:伺服器端改版,getRss 對所有 channel_id 回空 feed → 容錯自動 skip,pipeline 不崩
      (註:2026-07-07 已恢復,回 57 則;之前為暫時性中斷)

### 🆕 UPDATE 3 YouTube 上傳 Checklist(已完成)

**準備(使用者已完成)**
- [x] Y:GCP 專案 + 啟用 YouTube Data API v3
- [x] Y:OAuth 憑證(Desktop app)→ client_secrets.json 放根目錄
- [x] Y:OAuth 同意畫面加自己為測試使用者
- [x] Y:pip 裝 google-api-python-client / google-auth-oauthlib / google-auth-httplib2(已加 requirements)
- [x] Y:.gitignore 加 client_secrets.json、token.json

**開發**
- [x] publisher/youtube.py — get_authenticated_service()(token 存/讀 + refresh)
- [x] upload_video()(resumable + 退避重試;AI 標註改後台手動 + log 提醒)
- [x] build_youtube_metadata()(標題+#Shorts、描述+實際來源+免責、tags)
- [x] main.py 接上傳(UPLOAD_ENABLED 判斷 + try/except 保護 mp4)
- [x] config 上傳設定(UPLOAD_ENABLED 預設 False / YT_*)

**驗證**
- [x] 認證(U3-1):首次瀏覽器授權 → token.json;第二次讀既有 token、不重新授權
- [x] 上傳(U3-2):現成 final.mp4 傳成 private 成功(video_id 產生,YT 後台可見,metadata 對)
- [~] 整合(U3-3):main.py 一條龍(code + smoke test 完成;完整跑一次「產出+上傳」留待下次要發片時)
- [x] 開關/容錯(U3-4):UPLOAD_ENABLED 預設 False 略過上傳;上傳 try/except 保護 mp4(by design)

**卡關實況**
- [x] client_secrets.json:使用者已放(Desktop app,合法)
- [x] AI 內容標註:定案「後台手動勾 + 上傳後 log 提醒」(videos.insert 無穩定欄位)
- [~] 上傳 public:使用者已手動改一支測試片為 public 確認觀看正常;隱私預設仍 private,待下次要發片再開 public/OAuth 驗證

### 🆕 UPDATE 4 AI 生成示意圖 Checklist(已完成)

- [x] U4-1:image_service.py(抽象介面 ImageService + GeminiImageService,SDK google-genai)
- [x] U4-1:生圖 prompt 模板(見下方「方向修正」)
- [x] U4-2:safe_generate(try/except + timeout 120s + retry 1 次 + 回 None)
- [x] U4-2:★任何失敗都不中斷 pipeline★(429/無圖時已自證:回 None → 純字卡)
- [x] U4-3:news_card.html 兩種版面(有圖/無圖;圖 base64 內嵌)
- [x] U4-3:數字視覺化、字幕、來源 保留(★有圖版改版見下方★)
- [x] U4-4:main.py 在 rewrite 後、card_render 前插生圖(三則都生)
- [x] U4-4:config(USE_AI_IMAGE / IMAGE_MODEL / TIMEOUT=120 / RETRY / DIR / DISCLAIMER / MIMI_REF_IMAGE)
- [x] U4-5:YT 描述加「部分畫面為 AI 生成示意圖」(has_ai_image 才加)
- [x] .env 加 GEMINI_API_KEY(不 commit)
- [x] ✅ 完整跑通:main.py 一鍵(3/3 生圖 + 合成 + 上傳 private https://youtu.be/a9dBkxTM5ZE)

**🔴 方向修正(實作後與指引 I7 不同,以此為準)**
- **model**:`gemini-3.1-flash-lite-image`(不是純 `gemini-3.1-flash-lite`;純文字版不生圖)。生圖模型要「-image」變體。
- **prompt 用「中文」寫**:英文 prompt → 中文亂碼;中文 prompt → 正確中文。主軸「請根據新聞內容產出示意圖」。
- **風格改成「豐富、有正確中文的財經插畫」**(推翻 I7 的「少中文字」);關鍵是用「illustration/插畫」而非「infographic」的詞。
- **Q版米米人物**:傳參考圖 `assets/mimi/米米財經主播4.jpg`(config.MIMI_REF_IMAGE),要求「畫面中所有人物(官員/分析師/投資人)一律用這隻貓的 Q 版形象」→ 品牌一致、且不畫真人。
- **圖不放大標題**:prompt 要求「圖上不要放新聞標題/大標題橫幅」,標題交給卡片(避免卡片標題與圖內標題重複)。
- **有圖版新聞卡版面**:米米財經 → 來源 → 標題 → 圖 → highlight.label(小字)→ 字幕;★有圖時「不顯示放大的數字框」★(數字框只在無圖版)。
- **YT 標題**:`{video_title}` + `config.YT_TITLE_HASHTAGS`(= #Shorts #米米財經 #台股)。

**卡關實況**
- [x] Gemini 帳單:一度 429「prepayment credits depleted」→ 使用者充值後解決(付費功能,免費方案不生圖)
- [x] model 名稱:list models 找到 `-image` 變體才生得出圖
- [x] 中文亂碼 → 改中文 prompt + illustration 風格解決
- [x] 生圖速度:三則約幾十秒,全程 269 秒可接受(未觸發「只第一則」)
- [x] 圖片比例:Gemini 曾回直式 768×1376 → 新聞卡爆版 → 加 `IMAGE_ASPECT="16:9"` + CSS max-height 防呆(見 I8b)

### 🆕 UPDATE 5 AI 審圖 agent Checklist(已完成)

**第一道防線:修生圖 prompt(U5-1)**
- [x] 禁止圖上出現任何「具體數字/財務數據/日期」(EPS、毛利率、%、股價、年份)
- [x] ★禁止圖表(K線/長條圖)座標軸標任何刻度數字/百分比★
- [x] 禁止圖說 caption / 描述文字
- [x] 標籤 ≤4 個、★每個標籤只能出現一次,不可重複★
- [x] ★禁止畫任何公司 logo/商標/英文品牌名 —— **即使新聞主角就是該公司**(如台積電)★
      → 改用泛化產業符號(晶圓/晶片/伺服器/廠房)
- [x] ✅ 驗證:無編造數字、無亂碼 caption、無 tsmc logo

**第二道防線:審圖 agent(U5-2)**
- [x] review_service.py:ReviewService 抽象介面 + GeminiReviewService
- [x] 審查 prompt ★分兩級★(blocking / minor)+ 只回 JSON `{"pass","blocking","minor"}`
- [x] safe_review:timeout 60s;★API 失效/逾時/解析失敗 → 保守視為「不通過」★
- [x] ✅ 用「已知有問題的圖」測 → 抓得出編造 EPS/毛利率 + 日期 + 亂碼(★關鍵驗證通過★)
- [x] ✅ 用「乾淨的圖」測 → 回 pass=true(不亂擋)

**接入 + 整合(U5-3 / U5-4)**
- [x] safe_generate 改成「生圖 → 審圖 → 帶 blocking 重生一次 → 再審」迴圈
- [x] 兩輪都不過 → 回 None → 該則退純字卡(★絕不擋發片★)
- [x] config:USE_IMAGE_REVIEW / REVIEW_MODEL / REVIEW_MAX_RETRY(=1) / REVIEW_TIMEOUT
- [x] main.py 不用改(審圖包在 image_service 內)
- [x] ✅ 完整跑 main.py:**3/3 通過審圖、都拿到圖**、全部 16:9、影片正常產出

**🔴 校準過程(重要經驗,別重蹈覆轍)**
- [x] 審查太嚴格 → **誤擋乾淨的圖**:它把「台北101」當違規、還自加「標籤貼切度」主觀標準
      → 修法:**明確允許台灣地標/通用符號** + **禁止自行追加標準**
- [x] 為了小瑕疵擋好圖 → **必須分級**:標籤重複只是美觀,卻讓好圖被丟掉,重生後反而更糟
      → 修法:**blocking / minor 分級**,pass 只看 blocking
- [x] 審查員「標籤重複」判定不一致(有時放 blocking)→ 修法:prompt 明寫「重複永遠是 minor,不可放 blocking」
- [x] 生圖模型看到「台積電」就畫 tsmc logo → 修法:prompt 明寫「即使新聞主角是該公司也不准畫其 logo」
- [~] 圖上仍會出現標題文字 → **使用者定案:接受**(不傷可信度,不列 blocking)
- [x] ★重生常常更糟★(AI 生圖隨機性)→ 所以只對 blocking 重生,不為美觀重生

### 🆕 UPDATE 6 資料庫記錄 Checklist(已完成)

- [x] U6-1:`db/models.py`(Run + Candidate;`link`/`run_id` 建 index;relationship 雙向 + cascade)
- [x] U6-1:`db/database.py`(engine / SessionLocal / init_db / get_session)
- [x] U6-2:`db/repository.py` — `save_run()`(1 run + N candidates,標 selected/position/reason)
- [x] U6-3:`main.py` 開頭 `init_db()`;尾端組 selected_links/reasons/positions + `save_run()`
- [x] U6-3:★寫 DB 包 try/except —— 失敗只 log,絕不中斷發片★
- [x] U6-5:config `DB_URL = "sqlite:///mimi.db"`
- [x] `.gitignore` 加 `mimi.db`
- [x] 裝 SQLAlchemy 2.0(加進 requirements.txt)
- [x] ✅ U6-2 驗證:寫假資料 → 1 run + 10 候選 + 3 篇 selected(reason/position/關聯都對)
- [x] ✅ U6-3 驗證:真實資料寫入正確;★弄壞 DB_URL → 只 log warning,流程照常跑完★
- [x] ✅ U6-4 驗證:`query_runs.py` 能查出「LLM 從這 10 篇選了哪 3 篇、為什麼」

**卡關實況 & 立即成效**
- [x] 指引列的「index 對回 link」→ 本專案不存在(`picked` 已含 link,見 D8)
- [x] 🔴 **DB 立刻發揮價值**:第一筆真實記錄就抓到選片問題 ——
      **同一次選了「力積電董座保證配息」+「力積電Q2毛利率」兩則同一家公司**,違反題材分散。
- [x] 修法:select prompt 加 ★「送出前的最終自我檢查」★(逐條自查:主體是否重複 → 重複就換掉)
      → 驗證:重跑後三則變成三個不同主體(外資賣超 / 台股盤勢 / 力積電財報)✅
      → **經驗:規則埋在清單裡 LLM 會忽略;改成「回答前的自我檢查步驟」才有效**(同「放具體反例」)
- [x] 附加工具:`query_runs.py`(`--list` / `<run_id>`);也可用 DB Browser for SQLite 開 `mimi.db`

### 🆕 UPDATE 8 MCP Server Checklist

- [x] U8-0:`pip install mcp`(實裝 **1.28.1**)+ ★確認當前 SDK 的實際 API(不照概念碼硬套)★
- [x] U8-1:`mcp_server/finance_news_server.py`(**FastMCP** + `@app.tool()`,stdio)
- [x] U8-1:兩個 tool 內部呼叫既有邏輯(★不重寫功能★:fetch_rss / parse_filter / select_news / repository)
- [x] U8-1:`db/repository.get_recent_selections(session, days)` 補上
- [x] U8-1:candidates 的 datetime 可 JSON 序列化(`_jsonable()`:datetime→isoformat、clean_text 截 300 字)
- [x] U8-2:`mcp_client.py`(啟動 server 子行程 + call_tool + 解析)
- [x] U8-3:`main.py` USE_MCP 分支 + ★MCP 失敗 fallback 直接呼叫★(asyncio.run 包)
- [x] U8-4:config(USE_MCP / DEDUP_DAYS)★`MCP_SERVER_CMD` 最終未採用,見下方偏離說明★
- [x] U8-4:`recent` 帶進 select prompt(`select_top_news(candidates, recent=...)`)
- [x] requirements 加 `mcp`
- [x] ✅ 分階段驗證:server → client → 整合 → ★弄壞 MCP 驗 fallback★
- [x] ✅ USE_MCP=False → 完全等同現狀
      → 驗證:mcp_client **完全沒被呼叫**、候選仍 10 則、`recent=[]`、select prompt **不含歷史區塊**

**卡關實況(實作後回填)**
- [x] MCP SDK 的 API 與指引概念碼不符(★如預期發生★)
      → 指引用低階 `Server` + 手寫 `inputSchema`;SDK 1.28.1 實際有 **`FastMCP`**:
        `@app.tool()` 裝飾器 + type hints **自動生成 JSON Schema**,`app.run(transport="stdio")`
      → **經驗:先寫 10 行 ping/pong 打通 stdio,再接真邏輯**,別一次寫完才發現 API 不對
- [x] stdout 汙染:server 端任何 `print` 都會**打壞 MCP 協議**(stdout 是協議通道)
      → server 一律 `logging.basicConfig(stream=sys.stderr)`
- [x] server 子行程的 python / 工作目錄
      → 用 `sys.executable`(保證是 venv 的 python,套件才找得到)
      → 用 `cwd=_PROJECT_ROOT`(否則 `sqlite:///mimi.db` 相對路徑找不到 DB)
- [x] 回傳解析:優先讀 `structuredContent`(FastMCP 回 list 時包成 `{"result": [...]}`),
      沒有才 fallback 解析 `content[0].text` 的 JSON

**★ 與指引的偏離:`config.MCP_SERVER_CMD` 未採用 ★**
指引原設計 `MCP_SERVER_CMD = ["python", "mcp_server/finance_news_server.py"]`,實作改為
`mcp_client.py` 內自行推導 `sys.executable` + **絕對路徑** script + `cwd=專案根目錄`。
原因:寫死 `"python"` 在本機會抓到 Microsoft Store 的 python stub(本專案早期踩過),
且相對路徑受呼叫端 cwd 影響。→ 少一個會設錯的設定項,啟動更穩。

**⚠️ U8 事後修正(2026-07-24):序列化邊界的無聲漏記**
MCP 為了 JSON 把 `published` 轉成 isoformat 字串,但 `Candidate.published` 是 `DateTime` 欄位
→ `save_run` 拋 `StatementError`,7/21 後所有執行**都沒寫進 DB 卻沒人發現**(寫 DB 包在 try/except
只印一行 warning)。修正:`mcp_client._restore_datetimes()` 在 client 邊界把字串還原成 datetime;
`main.py` 的失敗訊息改成醒目區塊。**教訓:容錯 ≠ 靜音。** 詳見 `INTERVIEW_NOTES.md` #001。

### 🆕 UPDATE 9 選片品質稽核 Agent Checklist

**U9-1 MCP tool `get_run_detail`**
- [x] `repository.get_run_detail(session, run_id)`(候選 + selected + position + reason;找不到回 None)
- [x] `finance_news_server.py` 加 `@app.tool() get_run_detail`
- [x] docstring 寫清楚「做什麼 + 何時該用」(★是 agent 的使用手冊★)
- [x] datetime 可 JSON 序列化(回傳已無 datetime 物件 —— `run_date`/候選欄位都是字串/純量)
- [x] ✅ 驗證:真實 run_id 回傳正確且可序列化;找不到回 None;MCP tool 層回 `{"error":...}`

**U9-2 MCP resource `runs://latest`**
- [x] `@app.resource("runs://latest")` 回最近一次摘要
- [x] ✅ 驗證:client 端 `list_resources()` + `read_resource()` 皆讀得到

**U9-3 `agent.py` 決策迴圈**
- [x] MCP 工具 discovery + `inputSchema` → OpenAI `parameters` 轉換
      → ★實測:FastMCP 的 inputSchema 就是乾淨 JSON Schema,只需包一層 wrapper(指引擔心的格式不符不存在)★
- [x] 決策迴圈(`AGENT_MAX_ITERATIONS` 上限;每輪印當前輪數;用盡→逼一次無工具作答並註記)
- [x] `tool_call_id` 對應正確(每筆 tool 回覆帶對應 id)
- [x] 一輪多個 `tool_calls` → 全部執行完再一起回覆(多輪驗證實際觸發:一輪並行查 run 1/2/3)
- [x] 工具失敗 → `_call_tool_safe` 回結構化 `{"error":...}`,不 raise、不中斷
- [x] system prompt 含「送出答案前的最終自我檢查」(★沿用 U6 經驗★)
- [x] 每次工具呼叫印出(`[工具] name(args) ← 第 N 輪`)
- [x] JSON 解析容錯(strip ``` 圍欄;非 JSON 就原文照印,不 crash)
- [x] CLI `input()` 迴圈(exit/quit/空 → 結束;EOF/Ctrl+C 也優雅收工)
- [x] ✅ 驗證 單輪:「最近選了哪些新聞」→ 1 次 `get_recent_selections` 作答
- [x] ✅ 驗證 ★多輪:「稽核這週」→ 3 輪(recent → 並行 detail×3 → recent)產出 JSON 報告★
- [x] ✅ 驗證 容錯:弄壞 server → CLI 報 `McpError: Connection closed`、回提示、不 crash
      → 額外做 `_root_cause()` 從 async ExceptionGroup 挖根因(否則只顯示無意義的 TaskGroup 字串)

**U9-4 config**
- [x] `AGENT_MODEL` / `AGENT_MAX_ITERATIONS` / `AGENT_AUDIT_DEFAULT_DAYS`
- [x] ✅ 驗證:`main.py` 沒 import agent、未被改動、仍正常 import → 發片流程零影響

**實作後回填**
- [x] MCP `inputSchema` 與 OpenAI `parameters` **格式相容**(先寫最小測試確認,免驚)
- [x] LLM 有乖乖先查資料才作答(system prompt「自我檢查①」奏效,未見憑空編造)
- [x] 無限迴圈防護:`AGENT_MAX_ITERATIONS=5` 未觸發(多輪稽核 3 輪內完成)
- [⚠] **觀察**:agent 稽核時會把測試資料 run 1/2(假標題)也一起分析並產生雜訊
      → 印證「測試資料污染稽核」;run 9(除錯殘留)已清除,run 1/2 使用者決定保留

---

## 6. 需要使用者提供 / 確認的

```
🔴 必須:
  • OPENAI_API_KEY（放 .env）
  • 三來源「財經版」的正確 RSS 網址:
    - ETtoday 財經:feeds.feedburner.com/ettoday/finance（待確認是否全財經）
    - 自由財經:business.xml?（待確認）
    - 風傳媒財經:哪個 channel_id?（待確認）
    → 這些填進 config.py

🟠 開發中會回報:
  • 股市關鍵字表要不要調（看篩選結果）
  • LLM 口播稿風格要不要調（看產出）

🆕 UPDATE 1(米米)必須:
  • 米米素材放進 assets/mimi/(intro/news_a/b/c/outro.mp4)
    → 使用者用 AI 圖生影片工具預先生好,最好無浮水印、直式、看鏡頭
🆕 UPDATE 1 開發中會回報:
  • 新聞圖要不要保留(預設拿掉,已確認 A 案)
  • 說話泡泡樣式/位置、米米上半佔比 MIMI_AREA_RATIO(先做一版再調)

🆕 UPDATE 3(YouTube 上傳)必須:
  • GCP 專案 + 啟用 YouTube Data API v3
  • client_secrets.json(OAuth Desktop app 憑證)放專案根目錄
  • 首次執行完成瀏覽器授權(登入米米財經 / 測試 YT 帳號)
🆕 UPDATE 3 之後決定:
  • 何時把隱私 private → public(改前確認:浮水印去了、AI 標註、免責、影片就緒)
  • 要不要提交 OAuth 驗證(才能直接發 public;否則傳 private 再手動改)

🆕 UPDATE 4(AI 生圖)必須:
  • GEMINI_API_KEY(放 .env)
  • 確認要用的生圖 model(使用者:Gemini 3.1 Flash-lite;SDK google-genai)
🆕 UPDATE 4 開發中回報:
  • 生圖 prompt 風格(先做一版,看圖再調)
  • 圖在新聞卡佔比(先上半 ~52%,看效果調)
  • 三則都生圖;若太慢再改「只第一則」
```

---

## 7. 未來擴充（本階段不做，架構已預留）

```
• 🆕 UPDATE 3 之後:GCP 部署(影片生成+上傳放 Cloud Run Jobs)+ Cloud Scheduler 定時觸發
    ⚠️ OAuth:GCP 無瀏覽器 → 本機先授權好 token.json 帶上去(或改 Service Account)
• 發布:Instagram(Graph API,商業帳號門檻高,另做);YouTube 已於 UPDATE 3 完成本機版
• 縮圖:自訂 thumbnail(videos + thumbnails.set)
• 多 LLM:llm_service 已抽象，加 class 即可換 Gemini/Claude
• platform 差異:profile 已預留（不同 CTA/長度）
• 轉場/背景音樂:video.py 加效果
• 米米素材擴充:更多動作段(說話、驚訝…)、依新聞情緒挑素材
• 🆕 UPDATE 5(下一份):AI 審圖 agent(生圖後檢查中文亂碼/扭曲/離題/畫到真人 → 不過也 fallback)
    + AI 審稿(口播稿有無偏離原新聞/標題誇大 → 有問題暫停上傳通知使用者)
• 跨天去重:UPDATE 6 已存 `link`,之後要加去重資料就在(這次只記錄、不比對剔除)
• 🔴 UPDATE 7(部署)必須處理:**Cloud Run Job 無狀態 → 容器內 `mimi.db` 跑完就消失**
    → DB 要換持久化(SQLite+GCS 每次下載/上傳,或換 DB);ORM 只改 `config.DB_URL`,models/repository 不動
• 審稿 agent:口播稿是否偏離原新聞、標題是否誇大(UPDATE 5 只做了審圖)
• 🆕 UPDATE 9 之後可擴充:
    → 把「生圖 / 審圖 / TTS」也暴露成 MCP tools,讓 agent 調度整條產製線
    → 稽核 agent 定期自動執行(排程)+ 有問題主動通知
    → 讓 agent 直接建議 select prompt 的具體修改內容
• MCP over HTTP transport(跨機 / 多 agent 共用);與 LangGraph 等 agent 框架結合
```
（🆕 UPDATE 1:原「AI 虛擬人像」已落地為米米主播。UPDATE 3:YouTube 本機上傳已做。UPDATE 4:新聞卡 AI 生圖已做。UPDATE 9:選片品質稽核 agent 已規劃,移出未來清單。)

---

> 📌 **核心原則再強調:分階段、每步單獨驗、先求有再求好。** 先讓「3 則股市新聞」印出來，再一路推到影片。遇到不確定停下來問，不要猜。這是個人作品集專案,成敗定義是「整條 pipeline 跑通、能產出影片」,不是「一次到位」。
