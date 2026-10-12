r"""控制台 API — 查詢類 endpoint(UPDATE 15,chunk 1)。

全部唯讀,重用 db/repository.py 與 ORM。資料邏輯寫成純函式(fetch_*),
route handler 只是薄包裝 → 方便單獨測試(見檔尾 __main__)。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from sqlalchemy import case, func, select

from db import repository
from db.database import get_session
from db.models import Candidate, Run

router = APIRouter()

_refreshing = False   # 防前端連點 → 同時打 YouTube API


def _candidate_counts(session) -> dict[int, dict]:
    """{run_id: {"total": n, "selected": m}}(一次 group-by 查完,避免 N+1)。"""
    rows = session.execute(
        select(
            Candidate.run_id,
            func.count(Candidate.id),
            func.sum(case((Candidate.selected.is_(True), 1), else_=0)),
        ).group_by(Candidate.run_id)
    ).all()
    return {rid: {"total": int(total or 0), "selected": int(sel or 0)} for rid, total, sel in rows}


def fetch_runs(limit: int = 30) -> list[dict]:
    """最近 N 筆 run 摘要(給總覽表格)。"""
    session = get_session()
    try:
        runs = session.execute(
            select(
                Run.id, Run.run_date, Run.video_title, Run.status,
                Run.youtube_url, Run.view_count,
            ).order_by(Run.run_date.desc(), Run.id.desc()).limit(limit)
        ).all()
        counts = _candidate_counts(session)
    finally:
        session.close()

    out = []
    for rid, d, title, status, url, vc in runs:
        c = counts.get(rid, {"total": 0, "selected": 0})
        out.append({
            "run_id": rid,
            "run_date": str(d),
            "video_title": title,
            "status": status,
            "youtube_url": url,
            "view_count": vc,
            "candidates": c["total"],
            "selected": c["selected"],
        })
    return out


def fetch_stats() -> dict:
    """總覽 KPI。blocked_this_week 目前 DB 未記錄審稿結果 → 先不提供。"""
    session = get_session()
    try:
        total_runs = session.scalar(select(func.count(Run.id))) or 0
        published = session.scalar(
            select(func.count(Run.id)).where(Run.youtube_url.isnot(None))
        ) or 0
        views = session.execute(
            select(Run.view_count).where(Run.view_count.isnot(None))
        ).scalars().all()
        latest = session.scalar(select(Run.id).order_by(Run.run_date.desc(), Run.id.desc()))
    finally:
        session.close()

    total_views = int(sum(views)) if views else 0
    avg_views = round(total_views / len(views)) if views else 0
    return {
        "runs": int(total_runs),
        "published": int(published),
        "total_views": total_views,
        "avg_views": avg_views,
        "videos_with_stats": len(views),
        "latest_run_id": latest,
    }


def fetch_run_detail(run_id: int) -> dict | None:
    """單次完整細節(重用 repository.get_run_detail)。"""
    session = get_session()
    try:
        return repository.get_run_detail(session, run_id)
    finally:
        session.close()


@router.get("/stats")
def stats():
    return fetch_stats()


@router.get("/runs")
def runs(limit: int = 30):
    return fetch_runs(limit)


@router.get("/runs/{run_id}")
def run_detail(run_id: int):
    d = fetch_run_detail(run_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"找不到 run_id={run_id}")
    return d


@router.post("/stats/refresh")
async def refresh_views():
    """撈 YouTube 最新觀看數寫回 DB(重用 refresh_stats.refresh)。

    ★寫入 + 打外部 API 的動作:丟 to_thread 不卡事件迴圈;失敗回結構化錯誤不 500 crash。★
    需本機已有 token_readonly.json(首次請先在終端機跑一次 refresh_stats.py 完成授權)。
    """
    global _refreshing
    if _refreshing:
        return {"ok": False, "error": "已有一個 refresh 在進行中,請稍候"}
    _refreshing = True
    try:
        import refresh_stats   # 延後載入(避免 API 啟動就拉 google auth)
        summary = await asyncio.to_thread(refresh_stats.refresh)
        return {"ok": True, **summary}
    except Exception as e:  # noqa: BLE001 — 撈失敗(未授權/網路)不讓 API crash
        return {"ok": False, "error": str(e)}
    finally:
        _refreshing = False


if __name__ == "__main__":
    # 不起 server,直接測查詢邏輯(讀真 mimi.db)
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    print("stats =", json.dumps(fetch_stats(), ensure_ascii=False))
    rs = fetch_runs(5)
    print(f"runs({len(rs)}):")
    for r in rs:
        print("  ", json.dumps(r, ensure_ascii=False))
    if rs:
        d = fetch_run_detail(rs[0]["run_id"])
        print(f"detail run {rs[0]['run_id']}: {len(d['candidates'])} 候選,"
              f"選中 {sum(1 for c in d['candidates'] if c['selected'])}")
