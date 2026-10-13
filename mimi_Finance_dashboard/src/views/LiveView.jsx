import { Fragment, useEffect, useRef, useState } from "react";
import { openRunStream } from "../api.js";

const LV = { info: "INFO", warn: "WARN", ok: " OK ", err: "ERR " };

// ── 候選池 / 選片(漏斗),插在時間軸對應步驟底下 ──
function Funnel({ cells }) {
  // cells: [{n, label, hl?, dedupBefore?}];dedupBefore = 這格前面的箭頭下標「去重後」
  return (
    <div className="funnel">
      {cells.map((c, i) => (
        <Fragment key={i}>
          {i > 0 && (
            <span className="fn-arrow">→{c.dedupBefore && <small>去重後</small>}</span>
          )}
          <div className={"fn" + (c.hl ? " hl" : "")}><b>{c.n}</b><span>{c.label}</span></div>
        </Fragment>
      ))}
    </div>
  );
}

function bySourceText(bySource) {
  return Object.entries(bySource || {}).map(([k, v]) => `${k} ${v}`).join(" · ");
}

function poolSummary(pool) {
  const s = pool.stats;
  return s ? `${s.raw} → ${s.stock} → ${s.pool}` : `候選 ${pool.candidates.length}`;
}

function PoolBlock({ pool }) {
  const s = pool.stats;
  return (
    <div className="step-rev">
      <div className="rv-chips">
        {pool.via === "mcp" && pool.tools.length > 0
          ? pool.tools.map((t) => <span className="tool-chip" key={t}>🔧 {t}</span>)
          : <span className="tool-chip">RSS 直接抓取(MCP fallback)</span>}
      </div>
      {s && (
        <Funnel cells={[
          { n: s.raw, label: `RSS 原始(${bySourceText(s.by_source)})` },
          { n: s.stock, label: "股市相關(關鍵字篩 + 排除中港股)" },
          { n: s.pool, label: "候選池(依發布時間取前 N)", hl: true, dedupBefore: true },
        ]} />
      )}
      <details className="xd">
        <summary>候選池 {pool.candidates.length} 則</summary>
        <ol className="cand-list">
          {pool.candidates.map((c, i) => (
            <li key={c.link || i}><span className="src">{c.source}</span>{c.title}</li>
          ))}
        </ol>
      </details>
      {pool.recent.length > 0 && (
        <details className="xd">
          <summary>近期已發 {pool.recent.length} 則(帶進選片 prompt,避免重複報導)</summary>
          <ul className="cand-list">
            {pool.recent.map((r, i) => (
              <li key={i}><span className="mono">{(r.run_date || "").slice(5)}</span> {r.title}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function PickBlock({ pick, pool }) {
  const pickedLinks = new Set(pick.picked.map((p) => p.link));
  const unpicked = pool ? pool.candidates.filter((c) => !pickedLinks.has(c.link)) : [];
  const s = pool && pool.stats;
  return (
    <div className="step-rev">
      {s && (
        <Funnel cells={[
          { n: s.raw, label: "RSS 原始" },
          { n: s.stock, label: "股市相關" },
          { n: s.pool, label: "候選池", dedupBefore: true },
          { n: pick.picked.length, label: "LLM 選中", hl: true },
        ]} />
      )}
      {pick.picked.map((p) => (
        <div className="pick" key={p.link || p.rank}>
          <span className="rank">{p.rank}</span>
          <div>
            <div className="pt"><span className="src">{p.source}</span>{p.title}</div>
            {p.reason && <div className="pr">選片理由:{p.reason}</div>}
          </div>
        </div>
      ))}
      {unpicked.length > 0 && (
        <details className="xd">
          <summary>未選 {unpicked.length} 則(LLM 只回傳選中的理由,未選的不另附理由)</summary>
          <ul className="cand-list">
            {unpicked.map((c, i) => (
              <li className="dim" key={c.link || i}><span className="src">{c.source}</span>{c.title}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// ── 審查結果(審稿/審圖 reflection),插在時間軸對應步驟底下 ──
// 審稿的 overturned = 被二審推翻的一審指控(附原文引文)
const hasOv = (r) => Array.isArray(r.overturned) && r.overturned.length > 0;
// 一審擋下、二審全部推翻 → 放行(紫卡)
const isVerified = (r) => r.status === "pass" && hasOv(r);

function revSummary(list) {
  const img = list[0].type === "image";
  let ps = 0, rw = 0, fb = 0, ov = 0;
  list.forEach((x) => {
    if (x.status === "pass") ps++; else if (x.status === "rewrite") rw++; else fb++;
    if (hasOv(x)) ov++;
  });
  const ovText = ov ? `(${ov} 則二審推翻)` : "";
  if (!rw && !fb) return `${ps}/${list.length} 通過${ovText}`;
  const parts = [];
  if (rw) parts.push(`${rw}${img ? " 重生" : " 重寫"}`);
  if (fb) parts.push(`${fb}${img ? " 退字卡" : " 用最後版"}`);
  if (ps) parts.push(`${ps} 通過`);
  return parts.join(" · ") + ovText;
}

function revTag(r) {
  const img = r.type === "image";
  if (isVerified(r)) return "⚖ 二審推翻,放行";
  if (r.status === "rewrite") return img ? "✏️ 重生後通過" : "✏️ 重寫後通過";
  // fallback:審圖 = 兩輪沒過、那則不放圖改純字卡;審稿 = 重寫到上限、用最後重寫版
  return img ? "⚠ 未通過,退回純字卡" : "⚠ 重寫上限,用最後重寫版";
}

function RevBlock({ list }) {
  const label = list[0].type === "image" ? "審圖" : "審稿";
  const pass = list.filter((r) => r.status === "pass" && !hasOv(r));   // 直接通過 → 小標籤
  const bad = list.filter((r) => r.status !== "pass" || hasOv(r));     // 重寫/退回/二審推翻 → 卡片
  return (
    <div className="step-rev">
      {pass.length > 0 && (
        <div className="rv-chips">
          {pass.map((r) => <span className="rv-chip" key={r.index}>{label} #{r.index} ✓</span>)}
        </div>
      )}
      {bad.map((r) => {
        const cls = isVerified(r) ? "verified" : r.status;
        return (
        <div className={"rv " + cls} key={r.index}>
          <div className="rv-top">
            <span className="rv-tag s">{label}</span>
            第 {r.index} 則
            <span className={"rv-tag " + cls}>{revTag(r)}</span>
          </div>
          {(r.overturned || []).map((o, j) => (
            <div className="ov" key={j}>
              <div className="ov-claim">一審擋下:<s>{o.claim}</s></div>
              <div className="ov-ev">📄 二審查到原文確有:「{o.evidence}」</div>
            </div>
          ))}
          {r.blocking && r.blocking.length > 0 && (
            <div className="blk">
              🔴 擋下{r.type === "script" ? "(二審確認)" : ""}:{r.blocking.join("；")}
            </div>
          )}
          {r.before && r.after && r.before !== r.after && (
            <div className="ba">
              <div className="box"><span className="k">原稿</span>{r.before}</div>
              <div className="box after"><span className="k">改寫後</span>{r.after}</div>
            </div>
          )}
        </div>
        );
      })}
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

  // pipeline 依序執行 → 候選池/選片/審查結果一定在對應步驟跑的當下送來,掛到「正在跑」的那一步
  function attachToRunning(update) {
    setStages((prev) => {
      let idx = prev.findIndex((s) => s.status === "run");
      if (idx === -1) idx = prev.length - 1;
      if (idx === -1) return prev;
      return prev.map((s, i) => (i === idx ? update(s) : s));
    });
  }

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
      } else if (type === "pool") {
        attachToRunning((s) => ({ ...s, pool: data }));
      } else if (type === "pick") {
        attachToRunning((s) => ({ ...s, pick: data }));
      } else if (type === "review") {
        attachToRunning((s) => ({ ...s, reviews: [...(s.reviews || []), data] }));
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

  // 選片那步要用候選池算「未選」→ 從掛著 pool 的那一步取出
  const poolData = (stages.find((s) => s.pool) || {}).pool;

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
                  : s.pick
                    ? <span className="rv-sum">{(poolData ? poolData.candidates.length : "?")} → {s.pick.picked.length}</span>
                    : s.pool
                      ? <span className="rv-sum">{poolSummary(s.pool)}</span>
                      : <span className="note mono">{s.status === "run" ? "…" : s.status === "done" ? "done" : ""}</span>}
              </div>
              {s.pool && <PoolBlock pool={s.pool} />}
              {s.pick && <PickBlock pick={s.pick} pool={poolData} />}
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
