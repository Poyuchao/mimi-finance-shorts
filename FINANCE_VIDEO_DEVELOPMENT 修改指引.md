# 🆕 UPDATE 10（數據驅動的選片優化 · 觀看數回饋迴圈）— 修改指引

> **給開發 agent 的核心提醒:分階段做、每步單獨跑單獨驗,不要一次全寫完。遇到不確定停下來回報,不要自行猜測補完。**
>
> ✅ 本指引的設計決策已與使用者逐項確認(見 §1),可據以實作。

---

## 0. 這次要做什麼

把「發布後的觀看數」撈回來,和當初的「選片決策 + 題材」關聯,統計出「哪些題材表現好」,
再把這個訊號**軟性**回饋進選片 prompt。

一句話:**讓系統在「新聞重要性」之外,多一個「歷史觀看表現」的參考,形成閉環。**

```
發片(UPDATE 3)
   ↓  過幾天觀看數才累積
撈觀看數(videos.list statistics)→ 寫回 DB(Run)
   ↓
統計:題材 → 平均觀看數 / 樣本數
   ↓
回饋:選片 prompt 帶入「近期高表現題材（僅供參考）」
   ↓
選片在「重要性硬門檻」之外,多一個加權訊號
```

**★ 定位:「觀察 + 輕推」,不是「自動最佳化」。★** 樣本還太小、觀看數低,訊號很雜;
先把管線接通、資料留痕,等樣本夠了才有統計意義。這個誠實定位本身就是重點。
**★ 不碰發片主流程產出品質;所有新動作失敗都不中斷發片。★**

---

## 1. 已確認決策

| # | 項目 | 結論 |
|---|------|------|
| V1 | 撈哪些數字 | ✅ **viewCount + likeCount + commentCount 全記**(YouTube 一次都回,順手記)|
| V2 | 撈取時機 | ✅ **pipeline 開頭自動撈**「過去已發布影片」的最新數字更新 DB;另附獨立 `refresh_stats.py` 可手動/排程跑 |
| V3 | 存哪裡 | ✅ v1 在 `Run` 加欄位;★時間序列成長曲線這次不做(未來才開 VideoStats 表)★ |
| V4 | 題材分類 | ✅ **給固定題材清單**讓 LLM 選(見 `config.NEWS_TOPICS`),不自由發揮 —— 固定清單才統計得起來 |
| V5 | 題材歸因 | ✅ 一支片 3 則、觀看數是整支的 → **整支觀看數歸給這 3 個題材(近似,誠實標註)** |
| V6 | 回饋強度 | ✅ **軟性參考**(同「近期已發過」模式);★重要性硬門檻仍優先,表現只在同等重要時當加權★ |
| V7 | agent 行為 | ✅ **agent 純唯讀,只讀 DB 快照**,回「上次 refresh 的數字 + `stats_updated_at`」,不即時撈 |
| V8 | 失敗處理 | ✅ 撈觀看數失敗只 log,絕不中斷發片 |
| V9 | 開關 | ✅ `USE_VIEW_FEEDBACK`(False = 完全等同 UPDATE 9 現狀)|

### ★ 設計原則:MCP 邊界 —— 唯讀上、寫入不上 ★

```
寫入 / 有副作用(打外部 API、改 DB)→ 不上 MCP,pipeline 直接呼叫
   • fetch_video_stats（打 YouTube API）
   • update_run_stats（寫 DB）
   → 與既有 save_run 同一類

唯讀查詢（agent 會想問）→ 上 MCP
   • get_topic_performance（題材表現）
   • view_count 透過既有 get_run_detail 讀得到（Run 已含該欄位）
   → 與既有 get_recent_selections / get_run_detail 同一類
```

> 💡 **MCP tool 不是「把每個函式包一層」,而是「把 agent 需要的唯讀能力暴露出去」。**
> 寫入 / 副作用留在 pipeline 直接呼叫,才能維持 agent 的「純唯讀」保證(UPDATE 9 Q3)。

---

## 2. 誠實的統計限制（★必寫進註解與 README,面試主動講★）

1. **樣本小**:~30 支、觀看數低 → 題材表現差異很可能是「發片時機 / 演算法運氣」而非題材本身。
2. **歸因粗糙**:整支觀看數歸給 3 題材,無法區分哪一則帶動。
3. **觀看數 ≠ 品質**:clickbait 題材可能高觀看但傷長期信任。
4. **結論**:v1 只做「讓資料看得到、讓 agent 參考」,★不宣稱自動最佳化★。
   → 統計一律附 `n_videos`(樣本數);低於 `VIEW_MIN_SAMPLE` 不進 prompt。

> 對應 JD:reason about failure modes、critically evaluate、apply human judgment。
> 「知道自己數據的限制、不過度宣稱」就是資深訊號。

---

## 3. 讀某支觀看數的完整流程（定案版）

```
【寫入·偶爾·碰網路】
  發片 → pipeline 開頭 refresh_stats（或手動 refresh_stats.py）
       → fetch_video_stats() 打 YouTube API
       → update_run_stats() 寫回 Run.view_count + stats_updated_at

【讀取·隨時·只讀 DB】
  你查:   python query_runs.py 10        → 顯示 view_count + 撈取時間
  問 agent:get_run_detail(10)            → 回 view_count（DB 快照）
  → 兩者都不碰 YouTube;要最新數字先跑一次 refresh
```

---

## 4. DB schema 變更

```
Run（影片層級,加 4 欄,皆 nullable）:
  + view_count       Integer
  + like_count       Integer
  + comment_count    Integer
  + stats_updated_at DateTime   ← 快照的撈取時間(判斷數字多新)

Candidate（單則層級,加 1 欄,nullable）:
  + topic            String     ← 題材,LLM 選片/改寫時標(從 NEWS_TOPICS 選)
```
★ 不開新表;皆 nullable(舊資料 / 剛發片還沒撈到時為空,不是 0)。★

---

## 5. 分階段實作（★每階段單獨驗,驗過才進下一步★)

### U10-1:撈觀看數 → 存 DB（不含題材、不含回饋）
- `db/models.py`:`Run` 加 view_count / like_count / comment_count / stats_updated_at。
- `publisher/youtube.py`:`fetch_video_stats(youtube, video_id) -> dict`(`videos.list(part="statistics")`)
  + `extract_video_id(url)`(`youtu.be/XXX` 與 `watch?v=XXX` 兩種)。
- `db/repository.py`:`update_run_stats(session, run_id, stats)`。
- `refresh_stats.py`(新,獨立可跑):撈所有有 youtube_url 的 Run → 更新 DB。
- ✅ 驗證:對真實已發布影片撈到 view_count,寫進 DB,`query_runs.py` 看得到 + 撈取時間。

### U10-2:題材標籤
- `config.py`:`NEWS_TOPICS = [...]`(固定清單)。
- `db/models.py`:`Candidate` 加 topic。
- `llm_service.py`:改寫時要 LLM 替每則選中新聞從清單挑 topic;`save_run` 一併寫入。
- ✅ 驗證:跑一次,三則各有一個「清單內」的合理題材。

### U10-3:題材表現統計（唯讀,上 MCP）
- `db/repository.py`:`get_topic_performance(session, days) -> [{topic, avg_views, n_videos}, ...]`
  (join Run+Candidate,只算有 view_count 的,GROUP BY topic)。
- `mcp_server`:加 tool `get_topic_performance(days)`(docstring 標明「近似、可能小樣本」)。
- ✅ 驗證:回得出「題材 → 平均觀看 / 樣本數」;樣本數一定要一起回。

### U10-4:回饋進選片（軟性）
- `config.py`:`USE_VIEW_FEEDBACK`、`VIEW_FEEDBACK_DAYS`、`VIEW_MIN_SAMPLE`。
- `main.py`:pipeline 開頭 refresh stats;取 topic performance。
- `llm_service.py`:`_build_select_prompt` 加「近期高表現題材（僅供參考,樣本數 N）」區塊,
  ★明講重要性優先,這只是同等重要時的參考★。
- ✅ 驗證:選片 prompt 看得到高表現題材;但「重要但冷門題材仍選得進來」(重要性沒被蓋過)。
- ✅ 驗證:`USE_VIEW_FEEDBACK=False` → 完全等同 UPDATE 9 現狀。

### U10-5:（可選）稽核 agent 加問法
- agent 已能透過 MCP 呼叫 `get_topic_performance` → 可問「哪些題材最紅?樣本夠嗎?」
- ✅ 驗證:agent 回答會一併提樣本數,不拿 2 支片下結論。

---

## 6. ★ 卡關預告 ★

| 問題 | 對策 |
|------|------|
| 剛發片觀看數還是 0 | 正常,需累積;`stats_updated_at` 記撈取時間,別把 0 當定論 |
| video_id 抽取 | `youtu.be/XXX` 與 `watch?v=XXX` 兩種都要處理 |
| OAuth quota | `videos.list` 便宜,但別一次撈太多歷史;先只撈近 N 天 Run |
| 題材歸因失真 | 註解與輸出都標「近似:整支歸給 3 題材」,別假裝精確 |
| 樣本太小下結論 | 統計一律附 `n_videos`;低於 `VIEW_MIN_SAMPLE` 不進 prompt |
| echo chamber | 重要性硬門檻在 prompt 中永遠排在表現訊號之前 |
| 撈數字失敗 | 只 log,不中斷發片 |

---

## 7. 未來擴充（本階段不做）

```
• 時間序列 VideoStats 表:追蹤每支片觀看成長曲線(24h/72h/7d)
• 標題表現追蹤:同題材不同標題的點閱率(自動化頻道難做嚴謹 A/B)
• 跨平台觀看數(IG Reels / TikTok)一起納入
• 樣本夠大後:從「軟性參考」升級為「加權選片」,做重要性 vs 表現的權衡實驗
```

---

## 8. 對應 JD 能力（面試用）

```
• 閉環 / 回饋系統設計:發布 → 觀測 → 統計 → 回饋選片
• reason about failure modes:時機、歸因、小樣本、echo chamber 四個坑都主動處理
• critically evaluate / 不過度宣稱:定位「觀察+輕推」,不宣稱自動最佳化
• MCP 邊界判斷:唯讀上、寫入不上 —— 不是每個函式都包成 tool
• 資料建模:題材標籤 + 統計聚合 + 樣本數透明化
```

> 📌 **核心原則:分階段、每步單獨驗、絕不影響現有發片流程。**
> 成敗定義是「資料迴圈接通、且誠實面對統計極限」,不是「觀看數立刻變高」。
