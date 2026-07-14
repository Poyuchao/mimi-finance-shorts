r"""階段 1 執行器:抓 RSS → 篩股市 → 收斂候選池,印出候選 ~10 則供人工確認。

跑法:  .\venv\Scripts\python.exe run_stage1.py
"""

import logging
import sys

# Windows 主控台 cp950,強制 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import fetch_rss
import parse_filter
import select_news


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    entries = fetch_rss.fetch_rss()
    stock = parse_filter.parse_filter(entries)
    candidates = select_news.select_news(stock)

    print("\n" + "=" * 70)
    print(f"候選股市新聞:{len(candidates)} 則")
    print("=" * 70)

    for i, n in enumerate(candidates):
        pub = n["published"].strftime("%m/%d %H:%M") if n.get("published") else "無時間"
        text = (n.get("clean_text") or "").strip()
        snippet = text[:80] + ("…" if len(text) > 80 else "")
        print(f"\n[{i}] 來源:{n['source']}   時間:{pub}   ({n.get('_reason','')})")
        print(f"    標題:{n['title']}")
        print(f"    內文:{snippet if snippet else '(無內文)'}")
        print(f"    圖片:{n.get('image_url') or '(無)'}")
        print(f"    連結:{n.get('link') or '(無)'}")


if __name__ == "__main__":
    main()
