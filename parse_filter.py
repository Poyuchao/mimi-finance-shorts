"""② 解析 + 篩股市 + 清洗。

職責:
  1. 清洗 description:剝 HTML、抽純文字內文、抽圖片 URL、去掉「詳全文」尾巴
  2. 篩股市:ETtoday finance 子網域 → 財經(優先);任一來源 title+內文 含關鍵字 → 股市
  3. 回傳乾淨的股市新聞列表

回傳:[{source, title, clean_text, image_url, link, published}, ...]
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

# 「詳全文」這類尾巴
_TAIL_PATTERNS = [
    re.compile(r"《詳全文[^》]*》.*$", re.S),
    re.compile(r"詳全文[:：].*$", re.S),
    re.compile(r"更多.{0,20}報導.*$", re.S),
]


def _clean_description(description: str) -> tuple[str, str | None]:
    """剝 HTML → (純文字內文, description 裡的第一張圖 URL|None)。"""
    if not description:
        return "", None

    soup = BeautifulSoup(description, "html.parser")

    # 先抓圖(在剝標籤前)
    img_url = None
    img = soup.find("img")
    if img and img.get("src"):
        img_url = img["src"]

    text = soup.get_text(separator=" ", strip=True)

    # 去掉「詳全文」尾巴
    for pat in _TAIL_PATTERNS:
        text = pat.sub("", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text, img_url


def _is_ettoday_finance(item: dict) -> bool:
    """ETtoday finance 子網域 → 視為財經。"""
    if item["source"] != "ETtoday":
        return False
    return "finance" in (item.get("link") or "").lower()


def _hit_stock_keyword(text: str) -> str | None:
    """回傳命中的第一個股市關鍵字(用來 log 說明為何保留),沒中回 None。"""
    for kw in config.STOCK_KEYWORDS:
        if kw in text:
            return kw
    return None


def _hit_exclude_keyword(text: str) -> str | None:
    """回傳命中的第一個排除詞(中港股等),沒中回 None。"""
    for kw in config.EXCLUDE_KEYWORDS:
        if kw in text:
            return kw
    return None


def parse_filter(entries: list[dict]) -> list[dict]:
    """清洗 + 篩股市,回傳乾淨的股市新聞列表。"""
    result: list[dict] = []

    for e in entries:
        clean_text, desc_img = _clean_description(e.get("description", ""))
        # 圖片:entry 層級優先,沒有再用 description 裡的 <img>
        image_url = e.get("image") or desc_img

        haystack = f"{e.get('title', '')} {clean_text}"

        # 排除詞優先:中港股等 → 丟棄(即使有股市關鍵字)
        excl = _hit_exclude_keyword(haystack)
        if excl:
            logger.debug("排除 [%s] %s  ← 排除詞「%s」", e["source"], e.get("title", ""), excl)
            continue

        by_subdomain = _is_ettoday_finance(e)
        hit_kw = _hit_stock_keyword(haystack)

        if not (by_subdomain or hit_kw):
            continue  # 不是股市新聞,跳過

        reason = "ETtoday-finance子網域" if by_subdomain else f"關鍵字「{hit_kw}」"
        logger.debug("保留 [%s] %s  ← %s", e["source"], e.get("title", ""), reason)

        result.append(
            {
                "source": e["source"],
                "title": e.get("title", ""),
                "clean_text": clean_text,
                "image_url": image_url,
                "link": e.get("link", ""),
                "published": e.get("published"),
                "_reason": reason,   # 除錯用:為什麼被當股市新聞
            }
        )

    logger.info("篩選:%d 則原始 → %d 則股市新聞", len(entries), len(result))
    return result


if __name__ == "__main__":
    import fetch_rss

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stock = parse_filter(fetch_rss.fetch_rss())
    print(f"\n=== 篩出 {len(stock)} 則股市新聞 ===")
    for n in stock[:8]:
        print(f"[{n['source']}] {n['title']}  ← {n['_reason']}")
