# 米米財經 控制台 — 前端開發指引(React + Vite)

> 一個對應發片 pipeline 的前端控制台:**總覽(歷史 runs / 觀看數 / 審稿結果)**、**即時跑片(stage 進度 + log 串流)**、**稽核 Agent(自然語言問選片品質)**。
> 搭配後端見 `UPDATE15_Dashboard_API_修改指引.md`。UI 原型:claude artifact mockup(三分頁)。

---

## 0. 原則

- **純 client SPA**:React + Vite,所有資料來自後端 FastAPI(`fetch` + `EventSource`)。
- **不用 Next.js**:這個專案的後端是 Python,SSR / API routes 用不到,只會多一個 Node 後端跟 Python 打架。
- **前端只負責呈現**,不碰業務邏輯;後端掛掉時前端要能優雅顯示錯誤,不白屏。
- 面試定位是後端 / AI / agent → 前端「乾淨夠用」即可,**不過度投資**。

---

## 1. 技術選型

| 項目 | 選擇 | 備註 |
|---|---|---|
| 框架 | React 18 + Vite | `npm create vite@latest -- --template react` |
| 語言 | JS(或 TS,想要型別就上 TS) | 初版 JS 即可,之後可漸進轉 TS |
| 樣式 | 原生 CSS(沿用 mockup 的 token)/ 或 CSS Modules | 不急著上 Tailwind,mockup 的 CSS 可直接搬 |
| 狀態 | `useState` + 少量 Context | 資料量小,**不需要 Redux / Zustand** |
| SSE | 原生 `EventSource` | 跑片進度、agent 串流都用它 |
| 圖表(選用) | 之後要畫觀看趨勢再加 Recharts | 初版用數字卡即可 |

---

## 2. 專案結構

```
mimi_Finance_dashboard/
├── mimi_dashboard_development.md   # 本檔
├── index.html
├── vite.config.js                  # dev proxy → FastAPI(見 §5)
├── package.json
└── src/
    ├── main.jsx
    ├── App.jsx                     # 版面 + 分頁切換
    ├── api.js                      # fetch 封裝 + SSE helper(見 §4)
    ├── styles.css                  # 沿用 mockup 的 CSS token(亮/暗)
    ├── components/
    │   ├── TopBar.jsx              # 品牌 + 分頁 + 「立即跑一支」
    │   ├── KpiRow.jsx              # 4 個 KPI 數字卡
    │   ├── LatestRun.jsx           # 最近一次 run 大卡(3 則新聞 + 影片 + 審稿摘要)
    │   ├── RunsTable.jsx           # 過往 runs 表
    │   ├── NewsItem.jsx            # 單則新聞卡(來源/理由/漲跌 chip)
    │   ├── LiveRun.jsx             # 即時跑片:StageList + LogConsole
    │   ├── StageList.jsx           # stage 時間軸(pending/run/done)
    │   ├── LogConsole.jsx          # 深色終端機 log 區塊
    │   └── AuditChat.jsx           # 稽核對話框(chips + 輸入 + 工具呼叫串流)
    └── views/
        ├── DashboardView.jsx       # 總覽(KpiRow + LatestRun + RunsTable)
        ├── LiveView.jsx            # 即時跑片
        └── AuditView.jsx           # 稽核 Agent
```

---

## 3. 三個分頁 ↔ 元件 ↔ 後端

| 分頁 | 主要元件 | 後端呼叫 |
|---|---|---|
| **總覽** | `KpiRow` / `LatestRun` / `RunsTable` | `GET /stats`、`GET /runs`、`GET /runs/{id}` |
| **即時跑片** | `LiveRun`(`StageList` + `LogConsole`) | `POST /run` → **SSE** 推 `stage` / `log` / `done` |
| **稽核 Agent** | `AuditChat` | `POST /audit` → **SSE** 推 `tool` / `answer` / `report` |

> 漲跌顏色:**台股慣例紅漲綠跌**(`up` 紅 / `down` 綠 / `flat` 灰),token 名用 `--up/--down/--flat`,別用西方習慣。

---

## 4. API 介接(`src/api.js`)

```js
const BASE = "/api";                     // dev 由 vite proxy 轉到 FastAPI(見 §5)

export async function getStats()  { return (await fetch(`${BASE}/stats`)).json(); }
export async function getRuns()   { return (await fetch(`${BASE}/runs`)).json(); }
export async function getRun(id)  { return (await fetch(`${BASE}/runs/${id}`)).json(); }

// SSE:回傳 EventSource,呼叫端自己掛 onmessage / addEventListener(事件型別見後端指引 §4)
export function openRunStream(onEvent) {
  const es = new EventSource(`${BASE}/run/stream`);   // 後端:POST 觸發 or GET 直接開流,擇一(見後端指引)
  ["stage","log","done","error"].forEach(t =>
    es.addEventListener(t, e => onEvent(t, JSON.parse(e.data))));
  return es;   // 呼叫端記得在 done/error 或 unmount 時 es.close()
}

export function openAuditStream(question, onEvent) {
  const es = new EventSource(`${BASE}/audit/stream?q=${encodeURIComponent(question)}`);
  ["tool","answer","report","error"].forEach(t =>
    es.addEventListener(t, e => onEvent(t, JSON.parse(e.data))));
  return es;
}
```

**SSE 使用守則(重要)**
- 每次跑片 / 問一題 → 開一條 `EventSource`,收到 `done`/`error` 或元件 unmount 時**務必 `es.close()`**,否則會殘留連線 + 自動重連。
- `EventSource` 只支援 GET。若 `POST /run` 觸發後要串流,兩種做法:①`POST /run` 回一個 `job_id`,再 `GET /run/{job_id}/stream`;②直接 `GET /run/stream` 由後端啟動(單人本機可接受)。細節對齊後端指引。

---

## 5. 開發設定

```bash
cd mimi_Finance_dashboard
npm install
npm run dev          # http://localhost:5173
```

`vite.config.js` 把 `/api` 代理到 FastAPI(避免 CORS):

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } } },
});
```

> 後端 FastAPI 預設跑在 `:8000`(見後端指引)。生產可用 `npm run build` 出靜態檔,交給 FastAPI 的 `StaticFiles` 一起服務,就不用兩個 server。

---

## 6. 元件實作重點

- **`LiveRun`**:用一個 `stages` state(陣列,各含 `status: pending|run|done`)。SSE 收到 `stage` 事件就更新對應那筆;收到 `log` 事件 append 到 `LogConsole`。`done` 關流 + 顯示完成。
- **`LogConsole`**:固定高度、`overflow:auto`、新行進來自動捲到底;依 level(info/warn/ok/err)上色。**永遠深色**(終端機風格),不隨主題。
- **`AuditChat`**:訊息陣列 state;送出 → push user 泡泡 + 一個 bot 泡泡;SSE `tool` 事件往 bot 泡泡 append 工具 chip,`answer`/`report` 事件填最終內容。chips 是預設問題捷徑,輸入框走同一條流程。
- **錯誤處理**:任何 fetch / SSE 失敗 → 該區塊顯示「後端未連線」提示,不白屏、不 throw 到最上層。

---

## 7. Checklist(review 用)

- [ ] 三分頁切換 + 版面對齊 mockup
- [ ] 漲跌顏色台股慣例(紅漲綠跌),數字 `tabular-nums`
- [ ] 亮/暗主題(沿用 mockup token)
- [ ] `EventSource` 在 done/error/unmount 都有 `close()`
- [ ] 後端未連線時各區塊優雅降級(不白屏)
- [ ] `vite proxy` 設好,無 CORS 問題
- [ ] 手機寬度(~400px)不破版、不橫向捲動

---

## 8. 實作順序(建議)

1. Vite 專案 + 版面骨架(TopBar + 三分頁空殼)+ 搬 mockup CSS。
2. **總覽**(最單純,只讀 API):串 `/stats` `/runs`。先用假資料,再接真後端。
3. **即時跑片**:`StageList` + `LogConsole`,接 `POST /run` 的 SSE。
4. **稽核 Agent**:`AuditChat`,接 `/audit` 的 SSE。
5. 收尾:錯誤降級、手機版、`npm run build` 交給 FastAPI 服務。

> 先把後端 `UPDATE15_Dashboard_API_修改指引.md` 的 endpoint / SSE 事件格式定案,前端才好對接。
