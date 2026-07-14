r"""查詢 DB 記錄(UPDATE 6):看 LLM 每次「從候選 N 篇選了哪 3 篇、為什麼」。

跑法:
    python query_runs.py          # 最近幾次執行的摘要 + 最新一次的完整候選池
    python query_runs.py 5        # 看 run_id=5 的完整候選池
    python query_runs.py --list   # 只列出所有執行的摘要
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from sqlalchemy import select

from db.database import get_session, init_db
from db.models import Run

LINE = "=" * 78


def show_list(session, limit: int = 15) -> None:
    runs = session.scalars(
        select(Run).order_by(Run.id.desc()).limit(limit)
    ).all()
    if not runs:
        print("(DB 裡還沒有任何執行記錄)")
        return

    print(f"\n{LINE}\n最近 {len(runs)} 次執行\n{LINE}")
    print(f"{'run':>4}  {'日期':<12} {'狀態':<8} {'候選':>4} {'選中':>4}  影片標題")
    print("-" * 78)
    for r in runs:
        n_all = len(r.candidates)
        n_sel = sum(1 for c in r.candidates if c.selected)
        title = (r.video_title or "-")[:28]
        print(f"{r.id:>4}  {str(r.run_date):<12} {r.status or '-':<8} "
              f"{n_all:>4} {n_sel:>4}  {title}")
        if r.youtube_url:
            print(f"{'':>4}  → {r.youtube_url}")


def show_run(session, run_id: int | None = None) -> None:
    if run_id is None:
        run = session.scalars(select(Run).order_by(Run.id.desc()).limit(1)).first()
    else:
        run = session.get(Run, run_id)

    if not run:
        print(f"找不到 run_id={run_id}")
        return

    print(f"\n{LINE}")
    print(f"run_id={run.id}   {run.run_date}   status={run.status}")
    print(f"影片:{run.video_title or '-'}")
    if run.youtube_url:
        print(f"連結:{run.youtube_url}")
    print(f"候選 {len(run.candidates)} 篇,LLM 選中 "
          f"{sum(1 for c in run.candidates if c.selected)} 篇")
    print(LINE)

    # 選中的排前面(依 position),未選的排後面
    for c in sorted(run.candidates, key=lambda x: (not x.selected, x.position or 99, x.id)):
        if c.selected:
            print(f"\n  ✅ 選中 #{c.position}  [{c.source}]")
            print(f"     {c.title}")
            print(f"     理由:{c.select_reason}")
        else:
            print(f"  ⬜ 未選         [{c.source}] {c.title}")


def main() -> None:
    init_db()
    session = get_session()
    try:
        args = sys.argv[1:]
        if args and args[0] == "--list":
            show_list(session)
        elif args and args[0].isdigit():
            show_run(session, int(args[0]))
        else:
            show_list(session)
            show_run(session)          # 沒指定 → 順便看最新一次的完整候選池
    finally:
        session.close()


if __name__ == "__main__":
    main()
