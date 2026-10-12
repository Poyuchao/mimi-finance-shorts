import { useState } from "react";
import DashboardView from "./views/DashboardView.jsx";
import LiveView from "./views/LiveView.jsx";
import AuditView from "./views/AuditView.jsx";

const TABS = [
  ["dash", "總覽"],
  ["live", "即時跑片"],
  ["audit", "稽核 Agent"],
];

export default function App() {
  const [tab, setTab] = useState("dash");
  return (
    <>
      <div className="bar">
        <div className="bar-in">
          <div className="brand"><span className="dot">🐱</span>米米財經 控制台</div>
          <div className="spacer" />
          <div className="tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                className="tab"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="wrap">
        {/* 三個分頁都保持掛載,只切顯示(hidden)——
            否則切 tab 會卸載即時跑片頁,正在跑的進度與 SSE 連線都會中斷。 */}
        <div hidden={tab !== "dash"}><DashboardView /></div>
        <div hidden={tab !== "live"}><LiveView /></div>
        <div hidden={tab !== "audit"}><AuditView /></div>
        <p className="foot">米米財經 控制台 · 資料來自本機 FastAPI(讀 mimi.db)。</p>
      </div>
    </>
  );
}
