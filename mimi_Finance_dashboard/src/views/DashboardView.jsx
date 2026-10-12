import { useEffect, useState } from "react";
import { getStats, getRuns, getRun, refreshViews } from "../api.js";

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());

export default function DashboardView() {
  const [stats, setStats] = useState(null);
  const [runs, setRuns] = useState(null);
  const [latest, setLatest] = useState(null);
  const [err, setErr] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState(null);

  async function load() {
    const [s, r] = await Promise.all([getStats(), getRuns(30)]);
    setStats(s);
    setRuns(r);
    if (s.latest_run_id) setLatest(await getRun(s.latest_run_id));
  }

  useEffect(() => {
    let alive = true;
    load().catch((e) => { if (alive) setErr(e.message); });
    return () => { alive = false; };
  }, []);

  async function onRefresh() {
    setRefreshing(true);
    setMsg(null);
    try {
      const res = await refreshViews();
      if (res.ok) {
        setMsg(`已更新 ${res.updated}/${res.total} 支觀看數`);
        await load();
      } else {
        setMsg(`更新失敗:${res.error}`);
      }
    } catch (e) {
      setMsg(`更新失敗:${e.message}`);
    } finally {
      setRefreshing(false);
    }
  }

  if (err) {
    return (
      <div className="state err">
        後端未連線:{err}
        <div className="note" style={{ marginTop: 8 }}>
          請先啟動 API:<span className="mono">uvicorn api.server:app --port 8000</span>
        </div>
      </div>
    );
  }
  if (!stats || !runs) return <div className="state">載入中…</div>;

  return (
    <div className="view">
      <div className="toolbar">
        <button className="btn" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "更新中…(撈 YouTube)" : "↻ 重新整理觀看數"}
        </button>
        {msg && <span className="note">{msg}</span>}
      </div>
      <KpiRow stats={stats} />
      <LatestRun detail={latest} />
      <RunsTable runs={runs} />
    </div>
  );
}

function KpiRow({ stats }) {
  const kpis = [
    [fmt(stats.published), "已發布影片", `共 ${fmt(stats.runs)} 次執行(其餘為測試)`],
    [fmt(stats.total_views), "累計觀看", "YouTube Shorts"],
    [fmt(stats.avg_views), "平均每支觀看", "已發布影片"],
    [fmt(stats.runs), "總執行次數", "含測試重跑"],
  ];
  return (
    <div className="kpis">
      {kpis.map(([n, l, d], i) => (
        <div className="kpi" key={i}>
          <span className="n">{n}</span>
          <span className="l">{l}</span>
          <span className="d">{d}</span>
        </div>
      ))}
    </div>
  );
}

function LatestRun({ detail }) {
  if (!detail) return <div className="card"><div className="state">載入最近一次…</div></div>;
  const picked = detail.candidates
    .filter((c) => c.selected)
    .sort((a, b) => (a.position || 99) - (b.position || 99));

  return (
    <div className="card">
      <div className="card-h">
        <span className="eyebrow">最近一次 Run</span>
        <h2>{detail.video_title || "(無標題)"}</h2>
        {detail.privacy_status === "public"
          ? <span className="pill ok">✅ 已發布</span>
          : <span className="pill muted">未發布(私人/測試)</span>}
        {detail.view_count != null && <span className="pill view">▶ {fmt(detail.view_count)} 觀看</span>}
        <div className="spacer" />
        <span className="mono note">run #{detail.run_id} · {detail.run_date}</span>
        {detail.youtube_url && (
          <a className="link" href={detail.youtube_url} target="_blank" rel="noreferrer">YouTube ↗</a>
        )}
      </div>

      <div className="run-grid">
        <div className="news">
          {picked.map((c) => (
            <div className="item" key={c.link || c.title}>
              <span className="rank">{c.position || "·"}</span>
              <div className="body">
                <span className="src">{c.source || "—"}</span>
                <span className="ttl">{c.title}</span>
                {c.reason && <span className="reason"><b>選片理由:</b>{c.reason}</span>}
              </div>
            </div>
          ))}
        </div>
        <div className="side">
          <div className="vframe">
            <div className="vt">{detail.video_title}</div>
            <div className="cat">🐱</div>
            <div className="vmeta">
              {detail.run_date} · 1080×1920 · #Shorts
            </div>
          </div>
          <div className="note">
            候選 {detail.candidates.length} 則 · 選中 {picked.length} 則
            {detail.stats_updated_at && <><br/>📊 數字截至 {detail.stats_updated_at}</>}
          </div>
        </div>
      </div>
    </div>
  );
}

function RunsTable({ runs }) {
  return (
    <div>
      <div className="card-h"><span className="eyebrow">過往 Runs</span><h2 style={{ fontSize: 15 }}>最近發布</h2></div>
      <div className="tbl">
        <table>
          <thead>
            <tr><th>日期</th><th>影片標題</th><th>候選/選中</th><th className="num">觀看</th><th>狀態</th></tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td className="mono">{r.run_date}</td>
                <td>
                  {r.youtube_url
                    ? <a className="link" href={r.youtube_url} target="_blank" rel="noreferrer">{r.video_title || "(無標題)"}</a>
                    : (r.video_title || "(無標題)")}
                </td>
                <td className="mono">{r.candidates} / {r.selected}</td>
                <td className="num">{fmt(r.view_count)}</td>
                <td>{r.privacy_status === "public"
                  ? <span className="pill ok">已發布</span>
                  : <span className="pill muted">未發布</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
