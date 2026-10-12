r"""抓選中新聞的全文(UPDATE 14)。

RSS 只給 ~150 字摘要(甚至只有「《詳全文...》」),收盤等關鍵數字常只在「標題」,
內文又只是殘缺摘要 → 改寫/審稿拿半篇比對,總會「數字對不上」而誤判編造。
這裡對「選中的 3 則」用 link 抓整篇文章,trafilatura 萃取正文,覆蓋 clean_text,
讓改寫 + 審稿都看到完整原文。

★ 容錯(與全專案一致):抓失敗 / 逾時 / 正文太短 → 維持原 RSS 摘要,絕不中斷發片。★

單獨測:  .\venv\Scripts\python.exe article_fetch.py <url>
"""

from __future__ import annotations

import concurrent.futures
import logging

import requests

import config

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": config.USER_AGENT}   # ★自己帶 UA:風傳媒有 bot detection★


def fetch_fulltext(url: str) -> str | None:
    """抓單篇全文正文。失敗 / 逾時 / 太短 → 回 None(不 raise)。"""
    if not url:
        return None
    try:
        import trafilatura

        resp = requests.get(url, headers=_HEADERS, timeout=config.FULLTEXT_TIMEOUT)
        resp.raise_for_status()
        # ★自己下載 HTML 再丟給 trafilatura 萃取★(才能帶 UA;trafilatura 自抓會被風傳媒擋)
        text = (trafilatura.extract(resp.text) or "").strip()
        if len(text) >= config.FULLTEXT_MIN_CHARS:
            return text
        logger.info("全文太短(%d < %d),維持摘要:%s",
                    len(text), config.FULLTEXT_MIN_CHARS, url)
    except Exception as e:  # noqa: BLE001 — 抓全文是加分,失敗一律回 None
        logger.warning("抓全文失敗(維持摘要):%s(%s)", url, e)
    return None


def enrich_fulltext(picked: list[dict]) -> int:
    """把 picked 每則的 clean_text 換成全文(抓得到才換)。回傳成功幾則。★不 raise★。"""
    n = 0
    for i, item in enumerate(picked, 1):
        url = item.get("link", "")
        full = None
        try:
            # 再包一層 thread timeout:防 extract 遇到異常大頁面卡住(requests 已有連線逾時)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                full = ex.submit(fetch_fulltext, url).result(
                    timeout=config.FULLTEXT_TIMEOUT + 5)
        except Exception as e:  # noqa: BLE001
            logger.warning("第 %d 則抓全文逾時/錯誤(維持摘要):%s", i, e)

        if full:
            item["summary_rss"] = item.get("clean_text", "")   # 原摘要留著備查
            item["clean_text"] = full[:config.FULLTEXT_MAX_CHARS]   # 長特稿截斷,控 token
            n += 1
            shown = len(item["clean_text"])
            cap = "(截斷)" if len(full) > shown else ""
            print(f"  ✅ 第 {i} 則取得全文({shown} 字{cap})")
        else:
            print(f"  ↩ 第 {i} 則維持 RSS 摘要(抓不到/太短)")
    return n


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://ec.ltn.com.tw/article/breakingnews/5596738"
    t = fetch_fulltext(url)
    print(f"\n全文長度:{len(t) if t else 0}\n{'=' * 60}")
    print((t or "(抓不到)")[:800])
