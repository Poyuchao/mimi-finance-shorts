import { useEffect, useRef, useState } from "react";
import { openRunStream } from "../api.js";

const LV = { info: "INFO", warn: "WARN", ok: " OK ", err: "ERR " };

export default function LiveView() {
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState([]);   // [{name, sub, status}]
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
            <div className={"step st-" + s.status} key={i}>
              <span className="ic">{s.status === "done" ? "✓" : s.status === "run" ? "•" : i + 1}</span>
              <span>
                <span className="nm">{s.name}</span>
                {s.sub ? <><br /><span className="sub">{s.sub}</span></> : null}
              </span>
              <span className="note mono">{s.status === "run" ? "…" : s.status === "done" ? "done" : ""}</span>
            </div>
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
