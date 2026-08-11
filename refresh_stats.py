r"""🆕 UPDATE 10:撈 YouTube 觀看數 → 更新 DB(快照)。

獨立可跑:  .\venv\Scripts\python.exe refresh_stats.py

角色:「寫入 / 維運」類 —— 打 YouTube API 讀 statistics,寫回 Run。
      ★ 不上 MCP(agent 純唯讀);撈失敗只 log,絕不影響其他影片。★
      首次執行會開瀏覽器,要一次 youtube.readonly 授權(之後續用 token_readonly.json)。
"""

from __future__ import annotations

import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from sqlalchemy import select

from db import repository
from db.database import get_session, init_db
from db.models import Run
from publisher import youtube

logger = logging.getLogger("refresh_stats")


def refresh() -> None:
    init_db()
    session = get_session()
    try:
        runs = session.scalars(
            select(Run).where(Run.youtube_url.isnot(None)).order_by(Run.id.desc())
        ).all()
        if not runs:
            print("(沒有已上傳的影片可撈)")
            return

        print(f"準備撈 {len(runs)} 支影片的觀看數…(首次會開瀏覽器授權)")
        yt = youtube.get_read_service()   # ★首次:開瀏覽器同意 readonly★

        ok = 0
        for r in runs:
            vid = youtube.extract_video_id(r.youtube_url)
            if not vid:
                logger.warning("run %s 無法解析 video_id:%s", r.id, r.youtube_url)
                continue
            try:
                stats = youtube.fetch_video_stats(yt, vid)
                if not stats:
                    logger.warning("run %s(%s)撈不到 statistics(私人/不存在?)", r.id, vid)
                    continue
                repository.update_run_stats(session, r.id, stats)
                ok += 1
                print(f"  ✅ run {r.id:>2}  {vid}  觀看 {stats.get('view_count')}"
                      f"、讚 {stats.get('like_count')}、留言 {stats.get('comment_count')}")
            except Exception as exc:  # noqa: BLE001 — 單支失敗不影響其他支
                logger.warning("run %s 撈觀看數失敗:%s", r.id, exc)

        print(f"\n完成:更新 {ok}/{len(runs)} 支(其餘見上方警告)")
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    refresh()
