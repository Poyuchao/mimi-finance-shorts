r"""階段 2 第二步:LLM 改寫。抓→篩→候選→LLM選3→LLM改寫,印出口播稿。

跑法:  .\venv\Scripts\python.exe run_stage2_rewrite.py
"""

import json
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
    svc = OpenAIService()
    picked = svc.select_top_news(candidates)
    result = svc.rewrite_scripts(picked)

    print("\n" + "=" * 70)
    print(f"影片標題:{result['video_title']}")
    print(f"Hashtags:{' '.join(result['hashtags'])}")
    print("=" * 70)

    for i, item in enumerate(result["items"], 1):
        secs = f"{len(item['script'])} 字"
        print(f"\n── 第 {i} 則 [{item['source']}] ──")
        print(f"  原標題:{item['original_title']}")
        print(f"  headline :{item['headline']}")
        print(f"  highlight:{item['highlight']}")
        print(f"  script({secs}):{item['script']}")

    # 也存一份 JSON 方便下一階段接
    with open("output_llm.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n(已存 output_llm.json)")


if __name__ == "__main__":
    main()
