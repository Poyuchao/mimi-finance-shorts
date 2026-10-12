import { useState } from "react";
import DashboardView from "./views/DashboardView.jsx";
import LiveView from "./views/LiveView.jsx";

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
        {tab === "dash" && <DashboardView />}
        {tab === "live" && <LiveView />}
        {tab === "audit" && (
          <div className="placeholder">稽核 Agent — 待 chunk 3(/audit SSE)接上後實作。</div>
        )}
        <p className="foot">米米財經 控制台 · 資料來自本機 FastAPI(讀 mimi.db)。</p>
      </div>
    </>
  );
}
