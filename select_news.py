"""③ 收斂成候選池(不直接選最終 3 則)。

角色:去重 + 排序,收斂成「候選 ~NEWS_POOL 則」,交給 LLM 挑最終 NEWS_COUNT 則。
邏輯(MVP 先簡單):
  1. 去重:標題高度相似只留一則(前 N 字相同 / 一個標題包含另一個)
  2. 排序:發布時間新→舊(無時間者排最後)
  3. 取前 NEWS_POOL 則
"""

from __future__ import annotations

import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)

_PREFIX_LEN = 12   # 標題前 N 字相同視為重複


def _normalize_title(title: str) -> str:
    """去空白/標點,方便比對。"""
    return "".join(ch for ch in title if ch.isalnum())


def _is_duplicate(title: str, kept: list[str]) -> bool:
    """與已保留的標題比對:前綴相同 / 互相包含 → 視為重複。"""
    norm = _normalize_title(title)
    if not norm:
        return False
    for k in kept:
        if not k:
            continue
        # 互相包含
        if norm in k or k in norm:
            return True
        # 前 N 字相同
        if norm[:_PREFIX_LEN] and norm[:_PREFIX_LEN] == k[:_PREFIX_LEN]:
            return True
    return False


def select_news(
    stock_news: list[dict],
    pool: int | None = None,
) -> list[dict]:
    """去重 + 排序 → 候選池(前 pool 則)。"""
    pool = pool if pool is not None else config.NEWS_POOL

    # 1. 排序:新→舊(無時間者用最舊時間墊底)
    def sort_key(n: dict):
        return n.get("published") or datetime.min

    ordered = sorted(stock_news, key=sort_key, reverse=True)

    # 2. 去重(依序保留,先進先留 → 因已排序,留下的是較新的)
    kept: list[dict] = []
    kept_titles: list[str] = []
    for n in ordered:
        if _is_duplicate(n.get("title", ""), kept_titles):
            logger.debug("去重跳過:%s", n.get("title", ""))
            continue
        kept.append(n)
        kept_titles.append(_normalize_title(n.get("title", "")))

    # 3. 取前 pool 則
    candidates = kept[:pool]

    if len(candidates) < config.NEWS_COUNT:
        logger.warning(
            "候選只有 %d 則(< 最終需要的 %d 則),最終有幾則做幾則",
            len(candidates), config.NEWS_COUNT,
        )
    logger.info(
        "選片:%d 則股市新聞 → 去重後 %d 則 → 候選取前 %d 則",
        len(stock_news), len(kept), len(candidates),
    )
    return candidates


if __name__ == "__main__":
    import fetch_rss
    import parse_filter

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cands = select_news(parse_filter.parse_filter(fetch_rss.fetch_rss()))
    print(f"\n=== 候選 {len(cands)} 則 ===")
    for i, n in enumerate(cands):
        print(f"{i}. [{n['source']}] {n['title']}")
