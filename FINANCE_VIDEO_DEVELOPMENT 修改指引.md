# FINANCE_VIDEO_DEVELOPMENT — 修改指引 UPDATE 6:資料庫記錄（候選池 + 選片結果,驗證選片品質）

> 搭配主規格 **FINANCE_VIDEO_DEVELOPMENT.md**,接續 UPDATE 1~5(米米、節目化、YouTube 上傳、AI 生圖、AI 審圖,皆已完成)。
>
> 現狀:`python main.py` 能抓新聞 → LLM 從候選 ~10 則挑 3 則(給理由)→ 改寫 → 生圖 → 審圖 → 米米節目影片 → 上傳 YouTube。這份加一個**輕量資料庫層**:把每次執行的**候選 10 篇 + LLM 選的 3 篇 + 選片理由**記錄下來,用於**事後驗證 LLM 選片品質**。
>
> **給開發 agent:這次加輕量記錄,用 SQLAlchemy + SQLite(本機)。不做去重、不做分析——只「記錄」。改動集中在:新增 db 模組、pipeline 選片後把候選池+選片結果寫入。這是「在既有 pipeline 尾端插一層記錄」,現有邏輯完全不動。分階段、每步單獨驗、不確定就停下來問。⚠️ 上雲時 SQLite 要換持久化(部署那份 UPDATE 7 處理)。**

---

## U6-0. 這次在做什麼 + 邊界

```
做:
  • SQLAlchemy models(runs 執行 + candidates 候選新聞)
  • 記錄:每次執行的「候選 ~10 篇」,標記哪 3 篇被 LLM 選中 + 選片理由
  • 用途:事後驗證「LLM 從 10 篇選的 3 篇合不合理」
  • 本機 SQLite(單檔 mimi.db)

不做(現在):
  ❌ 跨天去重(只記錄,不比對剔除)→ 但 link 有存,之後想加隨時能加
  ❌ 資料分析/儀表板
  ❌ 上雲持久化(SQLite→GCS)→ 部署那份 UPDATE 7 處理
```

### U6-0.1 為什麼做（用途明確,不是為記錄而記錄）

```
LLM 選片是「黑箱」(從候選 ~10 則挑 3 則)
→ 想知道「選得好不好、有沒有漏掉更重要的」
→ 記「10 篇候選 + 標記選中的 3 篇 + 理由」
→ 事後回看:評估選片品質 → 需要的話調 select prompt

→ 真實用途:資料驗證 AI 決策(不盲信 LLM)
→ 附帶:link 都存了,之後想做「跨天去重」資料就在
```

### U6-0.2 已定案決策（不要自行更改）

| # | 項目 | 結論 |
|---|------|------|
| 1 | ORM | **SQLAlchemy**（使用者 ResumePilot 用過）|
| 2 | DB | 本機 **SQLite**（`mimi.db`）;上雲換持久化(UPDATE 7)|
| 3 | 記錄範圍 | **候選 ~10 篇全記**,標記 `selected` + `select_reason` |
| 4 | 用途 | **驗證 LLM 選片品質**（非去重、非分析）|
| 5 | 去重 | **這次不做**（但 `link` 有存,鋪路）|
| 6 | 寫入時機 | 影片產出/上傳後(或選片後)寫一次 |
| 7 | 表結構 | 2 表:`runs`（執行）+ `candidates`（候選,FK→runs）|
| 8 | 失敗處理 | 寫 DB 失敗不可中斷發片(try/except 包住,log 即可)|

---

## U6-1. Schema（`db/models.py`）

```python
from sqlalchemy import (Column, Integer, String, Text, Boolean,
                        Date, DateTime, ForeignKey)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Run(Base):
    """一次 pipeline 執行 = 一筆"""
    __tablename__ = "runs"
    id          = Column(Integer, primary_key=True)
    run_date    = Column(Date, index=True)
    created_at  = Column(DateTime, default=datetime.now)
    status      = Column(String)                    # success / failed / skipped
    video_title = Column(String, nullable=True)
    youtube_url = Column(String, nullable=True)

    candidates  = relationship("Candidate", back_populates="run")

class Candidate(Base):
    """一次執行的候選新聞（~10 篇全記,標記哪些被選）"""
    __tablename__ = "candidates"
    id            = Column(Integer, primary_key=True)
    run_id        = Column(Integer, ForeignKey("runs.id"))   # ★ 關聯:屬於哪次執行
    title         = Column(String)
    source        = Column(String)
    link          = Column(String, index=True)               # 之後去重也用得到
    published     = Column(DateTime, nullable=True)
    selected      = Column(Boolean, default=False)           # ★ 被 LLM 選中?
    position      = Column(Integer, nullable=True)           # 若選中,第幾則(1/2/3)
    select_reason = Column(Text, nullable=True)              # ★ LLM 選片理由(選中才有)
    created_at    = Column(DateTime, default=datetime.now)

    run           = relationship("Run", back_populates="candidates")
```

```
關係:runs (1) ──< candidates (多)
  一次 run → ~10 筆 candidates(其中 3 筆 selected=True)
  用 run_id 串起「這 10 篇是同一次執行的」
```

---

## U6-2. DB 連線 + 初始化（`db/database.py`）

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base
import config

engine = create_engine(config.DB_URL, echo=False)   # 本機:sqlite:///mimi.db
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)   # 首次自動建表

def get_session():
    return SessionLocal()
```

```
→ config.DB_URL 本機:"sqlite:///mimi.db"
→ 上雲(UPDATE 7):改連線字串(SQLite+GCS 或其他),models 不動
→ main.py 開頭呼叫 init_db()
```

---

## U6-3. 寫入邏輯（`db/repository.py`）

```python
from datetime import date
from db.models import Run, Candidate

def save_run(session, *, status, video_title=None, youtube_url=None,
             candidates=None, selected_links=None, reasons=None, positions=None):
    """
    candidates: 候選 ~10 篇 [{title, source, link, published}, ...]
    selected_links: 被選中的 link 集合(set)
    reasons: {link: 選片理由}
    positions: {link: 第幾則}
    """
    run = Run(run_date=date.today(), status=status,
              video_title=video_title, youtube_url=youtube_url)
    session.add(run)
    session.flush()   # 拿 run.id

    for c in (candidates or []):
        is_sel = c["link"] in (selected_links or set())
        session.add(Candidate(
            run_id=run.id,
            title=c.get("title"), source=c.get("source"),
            link=c.get("link"), published=c.get("published"),
            selected=is_sel,
            position=(positions or {}).get(c["link"]) if is_sel else None,
            select_reason=(reasons or {}).get(c["link"]) if is_sel else None,
        ))
    session.commit()
    return run.id
```

```
→ 傳入「候選 10 篇」+「哪些被選(link)」+「理由」+「位置」
→ 一次寫入:1 筆 run + ~10 筆 candidates(標記 selected)
```

---

## U6-4. 整合進 pipeline（`main.py`）

```
在「LLM 選片之後」就有了「候選池 + 選中的 + 理由」,先留著,最後寫入。

現有流程:
  candidates = select_news(...)                    # 候選 ~10 篇
  picked = llm_service.select_top_news(candidates) # 選 3 則 + reason(index+理由)
  ... rewrite / 生圖 / 審圖 / TTS / 影片 / 上傳 ...

加寫入(main 尾端,上傳後):
  try:
      # 從 picked 整理出:selected_links / reasons / positions
      selected_links = {candidates[p.index]["link"] for p in picked}
      reasons   = {candidates[p.index]["link"]: p.reason for p in picked}
      positions = {candidates[p.index]["link"]: i+1 for i, p in enumerate(picked)}

      repository.save_run(
          session,
          status="success",              # 或 failed / skipped
          video_title=llm_result.video_title,
          youtube_url=youtube_url,        # 沒上傳就 None
          candidates=candidates,          # ★ 候選 ~10 篇全給
          selected_links=selected_links,
          reasons=reasons,
          positions=positions,
      )
  except Exception as e:
      log.warning(f"寫入 DB 失敗(不影響發片): {e}")   # ★ 不中斷

→ ⚠️ picked 的 index 對回 candidates 拿 link(主規格已有 index 對回機制)
→ ⚠️ 寫 DB 包 try/except:寫失敗只 log,影片照發(記錄是附屬,不能拖垮主流程)
```

---

## U6-5. `config.py` 新增

```python
# 🆕 UPDATE 6:資料庫記錄
DB_URL = "sqlite:///mimi.db"   # 本機;上雲(UPDATE 7)改持久化連線
```

⚠️ `.gitignore` 加 `mimi.db`（資料檔不 commit）。

---

## U6-6. 開發順序（分階段,每步單獨驗）

```
階段 U6-1:models + database + 建表
  → db/models.py、db/database.py
  ✅ 驗證:跑 init_db() → mimi.db 生成、runs/candidates 表建好

階段 U6-2:寫入單獨測
  → repository.save_run() 塞一筆假資料(1 run + 10 candidates,標 3 篇 selected)
  ✅ 驗證:用 DB Browser for SQLite 開 mimi.db,看到 1 筆 run + 10 筆候選、
        3 筆 selected=True 有 reason/position,關聯(run_id)對

階段 U6-3:整合進 main
  → main 尾端組 selected_links/reasons/positions + save_run(包 try/except)
  ✅ 驗證:正常跑一次 python main.py → mimi.db 多一筆完整記錄
  ✅ 驗證:故意讓寫 DB 出錯(如改壞 DB_URL)→ 影片照樣產出/上傳(不中斷)

階段 U6-4:驗證選片(這就是這功能的目的)
  → 開 mimi.db,查某天的 run → 看 10 篇候選 + 哪 3 篇 selected + 理由
  ✅ 驗證:能清楚看出「LLM 從這 10 篇選了哪 3 篇、為什麼」
```

---

## U6-7. 修改 Checklist

- [ ] U6-1:db/models.py（Run + Candidate,link 建 index,relationship）
- [ ] U6-1:db/database.py（engine/session/init_db）
- [ ] U6-3:repository.save_run（1 run + N candidates,標 selected/reason/position）
- [ ] U6-4:main 尾端整理 selected_links/reasons/positions + save_run
- [ ] U6-4:★ 寫 DB 包 try/except,失敗不中斷發片 ★
- [ ] U6-5:config DB_URL
- [ ] main.py 開頭 init_db()
- [ ] .gitignore 加 mimi.db
- [ ] 分階段驗證(建表→寫入→整合→開 DB 看選片)

### 卡關立刻停手回報
- [ ] picked 的 index 對不回 candidates 的 link(對應問題)
- [ ] SQLite 檔路徑/權限問題
- [ ] relationship 設定 / FK 關聯查詢有問題

---

## U6-8. ⚠️ 上雲注意（部署 UPDATE 7 處理，先記著）

```
Cloud Run Job「無狀態」→ 容器內 mimi.db 跑完就消失!
  → 上雲時 SQLite 存不住 → 記錄會遺失

→ 部署(UPDATE 7)要把 DB 換持久化:
  • SQLite + GCS(每次執行:GCS 下載 db → 用 → 上傳回)★ 推薦,維持 SQLAlchemy
  • 或 Firestore(使用者 Jaijaido 用過,但要改 NoSQL 寫法)

→ ★ 這份先做本機 SQLite,把「記錄」做對 ★
→ 上雲換 DB 只改 config.DB_URL + 加 GCS 上下載(models/repository 不動)
```

---

## U6-9. 需要使用者確認

```
🟠 決定:
  • 要不要「未來加去重」(現在只記錄;link 有存,之後想加隨時能加)
  • 上雲 DB 方案(SQLite+GCS / Firestore)→ 部署 UPDATE 7 再定
  • 驗證選片:建議用 DB Browser for SQLite(免費 GUI)開 mimi.db 看
```

---

> 📌 **這次:輕量記錄「候選池 + 選片結果 + 理由」,用來驗證 LLM 選片品質。** 不做去重、不做分析,只記錄。SQLAlchemy + SQLite(本機),寫在 pipeline 尾端且 try/except 包住(寫失敗不拖垮發片)。runs (1)──<candidates(多),用 run_id 關聯,candidates 全記 ~10 篇並標 selected/reason。分階段:建表→寫入→整合→開 DB 看選片。⚠️ 上雲時 SQLite 要換持久化(UPDATE 7,ORM 換 DB 只改連線)。不確定(尤其 index 對回 link)就停下來問。目標:每天發什麼、LLM 怎麼選的,都有據可查。
