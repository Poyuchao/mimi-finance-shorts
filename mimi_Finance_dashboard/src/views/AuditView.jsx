import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openAuditStream } from "../api.js";

const PRESETS = [
  "這週選片品質有沒有問題?",
  "哪支影片觀看最多?",
  "最近有沒有重複報導同一主體?",
];
const THREAD = "dashboard"; // 固定 thread → 同一串對話有跨題記憶

// 去掉 ```json ... ``` 圍欄,讓答案乾淨一點
function clean(text) {
  return (text || "").replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
}

export default function AuditView() {
  const [msgs, setMsgs] = useState([]); // {role, text?, tools?, answer?, error?}
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const esRef = useRef(null);
  const finishedRef = useRef(false);

  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);

  function patchLastBot(patch) {
    setMsgs((prev) => {
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === "bot") { next[i] = { ...next[i], ...patch }; break; }
      }
      return next;
    });
  }

  function ask(question) {
    const q = (question || "").trim();
    if (!q || busy) return;
    setBusy(true);
    finishedRef.current = false;
    setMsgs((prev) => [...prev, { role: "user", text: q }, { role: "bot", tools: [] }]);

    const es = openAuditStream(q, THREAD, (type, data) => {
      if (type === "tool") {
        setMsgs((prev) => {
          const next = [...prev];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "bot") {
              next[i] = { ...next[i], tools: [...(next[i].tools || []), data] };
              break;
            }
          }
          return next;
        });
      } else if (type === "answer") {
        finishedRef.current = true;
        patchLastBot({ answer: clean(data.text) });
        finish();
      } else if (type === "error") {
        finishedRef.current = true;
        patchLastBot({ error: data.text || "發生錯誤" });
        finish();
      }
    });
    es.onerror = () => {
      if (finishedRef.current) return;
      patchLastBot({ error: "連線中斷(後端 API 是否在跑?)" });
      finish();
    };
    esRef.current = es;
  }

  function finish() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setBusy(false);
  }

  function submit() {
    if (busy || !input.trim()) return;
    ask(input);
    setInput("");
  }
  function onSubmit(e) {
    e.preventDefault();
    submit();
  }
  function onKeyDown(e) {
    // Enter 送出;Shift+Enter 換行(textarea 預設行為)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const fmtArgs = (args) =>
    Object.entries(args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");

  return (
    <div className="view">
      <div className="card">
        <div className="card-h">
          <span className="eyebrow">選片品質稽核 Agent</span>
          <h2>用自然語言問選片品質</h2>
          <div className="spacer" />
          <span className="mono note">gpt-4o · MCP · 純唯讀</span>
        </div>

        <div className="chips">
          {PRESETS.map((p) => (
            <button className="chip" key={p} onClick={() => ask(p)} disabled={busy}>{p}</button>
          ))}
        </div>

        <div className="log-chat">
          {msgs.length === 0 && <div className="note">點一個問題,或在下面自己問。agent 會自己決定呼叫哪些 MCP 工具再作答。</div>}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div className="msg user" key={i}>
                <span className="av">🙂</span>
                <div className="bubble">{m.text}</div>
              </div>
            ) : (
              <div className="msg bot" key={i}>
                <span className="av">🐱</span>
                <div className="bubble">
                  {(m.tools || []).map((t, j) => (
                    <span className="toolchip" key={j}>🔧 <b>{t.name}</b>({fmtArgs(t.args)})</span>
                  ))}
                  {m.answer != null ? (
                    <div className="md" style={{ marginTop: (m.tools || []).length ? 8 : 0 }}>
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{ a: (props) => <a target="_blank" rel="noreferrer" {...props} /> }}
                      >
                        {m.answer}
                      </ReactMarkdown>
                    </div>
                  ) : m.error != null ? (
                    <div className="errbox" style={{ marginTop: 8 }}>✗ {m.error}</div>
                  ) : (
                    <div className="note" style={{ marginTop: (m.tools || []).length ? 8 : 0 }}>思考中…</div>
                  )}
                </div>
              </div>
            )
          )}
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="自己問問題…(Enter 送出,Shift+Enter 換行)"
            disabled={busy}
          />
          <button className="btn" type="submit" disabled={busy || !input.trim()}>送出</button>
        </form>
        <p className="note" style={{ marginTop: 10 }}>
          這是 agent_langgraph(gpt-4o + MCP),透過查 mimi.db 回答;ReAct loop:呼叫工具 → 看結果 → 再查或作答。
        </p>
      </div>
    </div>
  );
}
