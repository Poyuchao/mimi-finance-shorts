import { Fragment, useEffect, useRef, useState } from "react";
import { openRunStream } from "../api.js";

const LV = { info: "INFO", warn: "WARN", ok: " OK ", err: "ERR " };

// ── 審查結果(審稿/審圖 reflection),插在時間軸對應步驟底下 ──
function revSummary(list) {
  const img = list[0].type === "image";
  let ps = 0, rw = 0, fb = 0;
  list.forEach((x) => { if (x.status === "pass") ps++; else if (x.status === "rewrite") rw++; else fb++; });
  if (!rw && !fb) return `${ps}/${list.length} 通過`;
  const parts = [];
  if (rw) parts.push(`${rw}${img ? " 重生" : " 重寫"}`);
  if (fb) parts.push(`${fb}${img ? " 退字卡" : " 用最後版"}`);
  if (ps) parts.push(`${ps} 通過`);
  return parts.join(" · ");
}

function revTag(r) {
  const img = r.type === "image";
  if (r.status === "rewrite") return img ? "✏️ 重生後通過" : "✏️ 重寫後通過";
  // fallback:審圖 = 兩輪沒過、那則不放圖改純字卡;審稿 = 重寫到上限、用最後重寫版
  return img ? "⚠ 未通過,退回純字卡" : "⚠ 重寫上限,用最後重寫版";
}

function RevBlock({ list }) {
  const label = list[0].type === "image" ? "審圖" : "審稿";
  const pass = list.filter((r) => r.status === "pass");
  const bad = list.filter((r) => r.status !== "pass");
  return (
    <div className="step-rev">
      {pass.length > 0 && (
        <div className="rv-chips">
          {pass.map((r) => <span className="rv-chip" key={r.index}>{label} #{r.index} ✓</span>)}
        </div>
      )}
      {bad.map((r) => (
        <div className={"rv " + r.status} key={r.index}>
          <div className="rv-top">
            <span className="rv-tag s">{label}</span>
            第 {r.index} 則
            <span className={"rv-tag " + r.status}>{revTag(r)}</span>
          </div>
          {r.blocking && r.blocking.length > 0 && (
            <div className="blk">🔴 擋下:{r.blocking.join("；")}</div>
          )}
          {r.before && r.after && r.before !== r.after && (
            <div className="ba">
              <div className="box"><span className="k">原稿</span>{r.before}</div>
              <div className="box after"><span className="k">改寫後</span>{r.after}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function LiveView() {
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState([]);   // [{name, sub, status, reviews?}]
  const [logs, setLogs] = useState([]);        // [{level, text}]
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);
  const esRef = useRef(null);
  const termRef = useRef(null);
  const finishedRef = useRef(false);

  // unmount 時關閉 SSE(避免殘留連線 + 自動重連 → 重跑)
  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);
  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
  }, [logs]);

  function stop() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setRunning(false);
  }

  function start() {
    if (running) return;
    finishedRef.current = false;
    setRunning(true); setStages([]); setLogs([]); setDone(null); setErr(null);

    const es = openRunStream((type, data) => {
      if (type === "stage") {
        setStages((prev) => [
          ...prev.map((s) => (s.status === "run" ? { ...s, status: "done" } : s)),
          { name: data.name, sub: data.sub || "", status: "run" },
        ]);
      } else if (type === "log") {
        setLogs((prev) => [...prev, { level: data.level || "info", text: data.text }]);
      } else if (type === "review") {
        // pipeline 依序執行 → 審查結果一定在對應步驟跑的當下送來,掛到「正在跑」的那一步
        setStages((prev) => {
          let idx = prev.findIndex((s) => s.status === "run");
          if (idx === -1) idx = prev.length - 1;
          if (idx === -1) return prev;
          return prev.map((s, i) =>
            i === idx ? { ...s, reviews: [...(s.reviews || []), data] } : s
          );
        });
      } else if (type === "progress") {
        // 合成進度:更新進行中那步(影片合成)的副標為「合成中 X%」
        setStages((prev) =>
          prev.map((s) => (s.status === "run" ? { ...s, sub: `合成中 ${data.pct}%` } : s))
        );
      } else if (type === "done") {
        finishedRef.current = true;
        setStages((prev) => prev.map((s) => ({ ...s, status: "done" })));
        setDone(data);
        stop();
      } else if (type === "error") {
        finishedRef.current = true;
        setErr(data.text || "發生錯誤");
        stop();
      }
    });
    es.onerror = () => {
      if (finishedRef.current) return;   // 正常結束造成的關閉 → 略過
      setErr("連線中斷(後端 API 是否在跑?)");
      stop();
    };
    esRef.current = es;
  }

  return (
    <div className="view">
      <div className="toolbar">
        <button className="btn" onClick={start} disabled={running}>
          {running ? "產生中…" : "▶ 立即跑一支"}
        </button>
        <span className="note">⚠️ 這會真的產生影片;若 UPLOAD_ENABLED=True 會上傳 YouTube。</span>
      </div>

      {err && <div className="errbox">✗ {err}</div>}
      {done && (
        <div className="donebox">
          ✅ 完成:{done.path} · {done.seconds}s
          {done.run_id ? ` · run #${done.run_id}` : ""}
          {done.youtube ? (
            <> · <a className="link" href={done.youtube} target="_blank" rel="noreferrer">{done.youtube}</a></>
          ) : null}
        </div>
      )}

      <div className="card">
        <div className="card-h"><span className="eyebrow">Pipeline</span><h2>即時進度</h2></div>
        <div className="steps">
          {stages.length === 0 && <div className="note">按「立即跑一支」開始。</div>}
          {stages.map((s, i) => (
            <Fragment key={i}>
              <div className={"step st-" + s.status}>
                <span className="ic">{s.status === "done" ? "✓" : s.status === "run" ? "•" : i + 1}</span>
                <span>
                  <span className="nm">{s.name}</span>
                  {s.sub ? <><br /><span className="sub">{s.sub}</span></> : null}
                </span>
                {s.reviews && s.reviews.length > 0
                  ? <span className="rv-sum">{revSummary(s.reviews)}</span>
                  : <span className="note mono">{s.status === "run" ? "…" : s.status === "done" ? "done" : ""}</span>}
              </div>
              {s.reviews && s.reviews.length > 0 && <RevBlock list={s.reviews} />}
            </Fragment>
          ))}
        </div>

        <div className="term-wrap">
          <div className="term-bar"><span>pipeline.log</span><span>{logs.length} 行</span></div>
          <div className="term" ref={termRef}>
            {logs.length === 0 && <span className="lv muted">// log 會在這裡逐行輸出</span>}
            {logs.map((l, i) => (
              <div key={i}><span className={"lv " + l.level}>{LV[l.level] || "INFO"}</span>{l.text}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
