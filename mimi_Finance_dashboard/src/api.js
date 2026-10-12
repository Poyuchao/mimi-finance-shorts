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

// 之後 chunk 2/3 會加:openRunStream / openAuditStream(EventSource SSE)
