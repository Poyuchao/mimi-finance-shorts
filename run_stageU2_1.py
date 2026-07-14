r"""階段 U2-1:新聞卡回歸純字卡 + 數字視覺化。

跑 抓→篩→選→改寫(取得結構化 highlight)→ 產 3 張純字卡新聞。

跑法:  .\venv\Scripts\python.exe run_stageU2_1.py
"""

import json
import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import card_render
import fetch_rss
import parse_filter
import select_news
from llm_service import OpenAIService


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cands = select_news.select_news(parse_filter.parse_filter(fetch_rss.fetch_rss()))
    svc = OpenAIService()
    picked = svc.select_top_news(cands)
    result = svc.rewrite_scripts(picked)

    with open("output_llm.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n影片標題:{result['video_title']}")
    for i, item in enumerate(result["items"], 1):
        hl = item.get("highlight") or {}
        print(f"\n── 第 {i} 則 [{item['source']}] ──")
        print(f"  headline :{item['headline']}")
        print(f"  highlight:value={hl.get('value')!r} trend={hl.get('trend')!r} label={hl.get('label')!r}")

    paths = card_render.render_news_cards(result)
    print("\n=== 純字卡新聞產出 ===")
    for pth in paths:
        print(" ", pth)


if __name__ == "__main__":
    main()
