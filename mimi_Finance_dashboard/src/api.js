// 後端 FastAPI 介接(dev 由 vite proxy 轉到 :8000)
const BASE = "/api";

async function j(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${url}`);
  return r.json();
}

async function post(url) {
  const r = await fetch(url, { method: "POST" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} @ ${url}`);
  return r.json();
}

export const getStats = () => j(`${BASE}/stats`);
export const getRuns = (limit = 30) => j(`${BASE}/runs?limit=${limit}`);
export const getRun = (id) => j(`${BASE}/runs/${id}`);
export const refreshViews = () => post(`${BASE}/stats/refresh`); // 撈 YouTube 最新觀看數

// 即時跑片 SSE:回傳 EventSource,呼叫端收到 done/error 後務必 es.close()
export function openRunStream(onEvent) {
  const es = new EventSource(`${BASE}/run/stream`);
  ["stage", "log", "done", "error"].forEach((t) =>
    es.addEventListener(t, (e) => onEvent(t, JSON.parse(e.data)))
  );
  return es;
}

// chunk 3 會加:openAuditStream
