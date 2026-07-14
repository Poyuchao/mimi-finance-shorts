"""集中設定:RSS 來源、股市關鍵字、影片參數。"""

import os

from dotenv import load_dotenv

load_dotenv()   # 讀 .env,讓 GEMINI_API_KEY 等環境變數可用

# ── RSS 來源(財經版) ──────────────────────────────
# type 決定用哪種抓法;needs_ua=True 表示要帶瀏覽器 UA(繞過 bot detection)
RSS_SOURCES = [
    {
        "name": "ETtoday",
        "url": "https://feeds.feedburner.com/ettoday/finance",  # 待確認是否全財經
        "type": "ettoday",
        "needs_ua": False,
    },
    {
        "name": "自由時報",
        "url": "https://news.ltn.com.tw/rss/business.xml",       # 待確認財經版
        "type": "ltn",
        "needs_ua": False,      # feedparser 自動解 gzip
    },
    {
        "name": "風傳媒",
        "url": "https://www.storm.mg/api/getRss/channel_id/2?path=https%3A%2F%2Fwww.storm.mg%2Farticle",
        "type": "storm",
        "needs_ua": True,       # bot detection,需帶 UA
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 抓取逾時(秒)
FETCH_TIMEOUT = 15

# ── 股市關鍵字(以股市為主) ───────────────────────
# 命中任一即視為股市新聞。開發時可迭代擴充/收斂(誤判/漏抓再調)。
# 註:「台幣」已移除 → 太鬆,會誤中任何提到「新台幣金額」的社會/政治新聞。
STOCK_KEYWORDS = [
    "台股", "加權指數", "收盤", "開盤", "盤中", "漲停", "跌停", "台積電",
    "股價", "美股", "道瓊", "那斯達克", "費半", "外資", "投信", "融資",
    "財報", "營收", "EPS", "上市", "上櫃", "股利", "除權息", "個股",
    "大盤", "類股", "殖利率", "ETF", "成交量", "櫃買", "標普",
]

# ── 排除詞(以台股/美股為主,篩掉中港股) ──────────
# 中了任一 → 丟棄,即使有股市關鍵字。用精準詞,避免誤傷台股/美股。
EXCLUDE_KEYWORDS = [
    "A股", "陸股", "港股", "中國股市", "滬指", "深證", "恒生",
]

# ── 影片/選片參數 ─────────────────────────────────
NEWS_COUNT = 3               # 一支影片最終幾則(LLM 從候選中挑這麼多)
NEWS_POOL = 10               # select_news 收斂出的候選則數(丟給 LLM 挑選)
TTS_VOICE = "zh-TW-HsiaoChenNeural"

VIDEO = {
    "width": 1080, "height": 1920, "fps": 30,
}

# ── 米米主播(UPDATE 2:只在頭尾) ──────────────────
# 米米預生成動畫素材(手動放進 assets/mimi/,重複使用,不對嘴)
# UPDATE 2:只要 2 段(開場白/收尾),news_a/b/c 不再需要
MIMI_CLIPS = {
    "intro": "assets/mimi/intro.mp4",   # 開場白
    "outro": "assets/mimi/outro.mp4",   # 收尾
}
USE_MIMI = True          # True=米米頭尾版 / False=純字卡版(無頭尾米米)
MIMI_AREA_RATIO = 0.58   # 開場白/收尾的米米上半佔比

# 開場白/收尾旁白 + 泡泡(先固定,之後可改 LLM 動態)
OPENING_LINE   = "哈囉~我是米米!今天股市有三件大事,一起來看喵~"
OUTRO_LINE     = "今天的股市重點就到這~喜歡的話記得追蹤米米財經,我們明天見!喵!"
OPENING_BUBBLE = "哈囉~我是米米!"
OUTRO_BUBBLE   = "掰掰~明天見!"

# 頻道標語(封面 + 收尾共用一處,誠實描述:重點回顧,非分析教學)
CHANNEL_SLOGAN = "每天 60 秒,米米帶你回顧今日財經重點"

# ── YouTube 上傳(UPDATE 3,本機版) ─────────────────
UPLOAD_ENABLED    = True        # 預設關(測 pipeline 時);要上傳才開 True
YT_PRIVACY        = "private"     # private / unlisted / public(先 private 測試)
YT_CATEGORY_ID    = "25"          # 25=News & Politics
YT_TAGS           = ["財經", "股市", "台股", "美股", "投資", "米米財經", "財經新聞"]
YT_CLIENT_SECRETS = "client_secrets.json"
YT_TOKEN_FILE     = "token.json"
YT_DISCLAIMER     = "本內容僅供參考,非投資建議。"
YT_TITLE_HASHTAGS = "#Shorts #米米財經 #台股"   # 標題固定接在後面

# ── AI 生成新聞示意圖(UPDATE 4) ────────────────────
USE_AI_IMAGE     = True          # 一鍵開關(False = 退回純字卡,等同 UPDATE 2 現狀)
IMAGE_PROVIDER   = "gemini"
IMAGE_MODEL      = "gemini-3.1-flash-lite-image"   # ★ 生圖用「-image」變體(flash-lite 文字版不會生圖)
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY")   # 放 .env,別 commit
IMAGE_TIMEOUT    = 120           # 單張生圖逾時(秒)
IMAGE_RETRY      = 1             # 失敗重試次數(再失敗就 fallback)
IMAGE_ASPECT     = "16:9"        # ★ 強制橫式(不設的話 Gemini 偶爾回直式 → 新聞卡爆版)
IMAGE_DIR        = "output/images"
IMAGE_DISCLAIMER = "部分畫面為 AI 生成示意圖"   # 加進 YT 描述
# 米米參考圖:生圖時需要人物 → 一律用這隻貓的 Q 版形象(頻道吉祥物一致性)
MIMI_REF_IMAGE   = "assets/mimi/米米財經主播4.jpg"

# ── AI 審圖 agent(UPDATE 5) ───────────────────────
USE_IMAGE_REVIEW = True          # 開關(False = 不審圖,等同 UPDATE 4 現狀)
REVIEW_MODEL     = "gemini-3.1-flash-lite"   # ★視覺文字模型(不是 -image 變體)
REVIEW_MAX_RETRY = 1             # 審不過 → 帶 issues 重生幾次(0 = 不重生,直接退純字卡)
REVIEW_TIMEOUT   = 60            # 單次審圖逾時(秒);逾時視為「不通過」(保守)

# ── 資料庫記錄(UPDATE 6) ─────────────────────────
# 記錄每次執行的「候選 ~10 篇 + LLM 選中的 3 篇 + 理由」→ 事後驗證選片品質
DB_URL = "sqlite:///mimi.db"     # 本機;上雲(UPDATE 7)改持久化連線,models/repository 不動
