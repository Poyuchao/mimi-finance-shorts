r"""階段 2 第一步:LLM 選片。抓→篩→候選池 → LLM 從候選挑 3 則 + 理由。

跑法:  .\venv\Scripts\python.exe run_stage2_select.py
"""

import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import fetch_rss
import parse_filter
import select_news
from llm_service import OpenAIService


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    candidates = select_news.select_news(
        parse_filter.parse_filter(fetch_rss.fetch_rss())
    )

    print("\n候選池:")
    for i, c in enumerate(candidates):
        print(f"  [{i}] [{c['source']}] {c['title']}")

    svc = OpenAIService()
    picked = svc.select_top_news(candidates)

    print("\n" + "=" * 70)
    print(f"LLM 選出 {len(picked)} 則(重要性由高到低)")
    print("=" * 70)
    for rank, p in enumerate(picked, 1):
        print(f"\n{rank}. [{p['source']}] {p['title']}")
        print(f"   理由:{p['reason']}")


if __name__ == "__main__":
    main()
