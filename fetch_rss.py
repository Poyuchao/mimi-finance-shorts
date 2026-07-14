"""① 抓 RSS(3 來源)。

各來源處理:
  • ETtoday / 自由:feedparser.parse(url) 直接抓(自由的 gzip feedparser 會自動解)
  • 風傳媒:先用 requests 帶 UA 抓 content,再 feedparser.parse(content)
            (直接 feedparser.parse(url) 會被 bot detection 擋)

容錯:某來源抓失敗 → skip 該來源、其他繼續(fault isolation),並 log。
回傳:[{source, title, link, description, published(datetime|None), image}, ...]
"""

from __future__ import annotations

import logging
from datetime import datetime

import feedparser
import requests

import config

logger = logging.getLogger(__name__)


def _to_datetime(entry) -> datetime | None:
    """feedparser 的 published_parsed(struct_time) → datetime。抓不到回 None。"""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6])
            except (TypeError, ValueError):
                pass
    return None


def _extract_entry_image(entry) -> str | None:
    """從 entry 層級盡量抓一張圖(media/enclosure)。抓不到回 None,
    後續 parse_filter 還會再從 description 的 <img> 補抓。"""
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media and isinstance(media, list) and media[0].get("url"):
            return media[0]["url"]
    # enclosure (RSS <enclosure>) 走 links
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    return None


def _parse_feed(source: dict):
    """依來源設定抓 feed,回傳 feedparser 的 feed 物件。"""
    if source["needs_ua"]:
        resp = requests.get(
            source["url"],
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.FETCH_TIMEOUT,
        )
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    return feedparser.parse(source["url"])


def fetch_rss(sources: list[dict] | None = None) -> list[dict]:
    """抓 3 來源,回傳合併後的原始 entry 列表(附來源名)。"""
    sources = sources if sources is not None else config.RSS_SOURCES
    all_entries: list[dict] = []

    for source in sources:
        name = source["name"]
        try:
            feed = _parse_feed(source)
            entries = feed.get("entries", [])
            if not entries:
                logger.warning("[%s] 抓到 0 則(來源可能有問題或網址不對)", name)
                continue

            for e in entries:
                all_entries.append(
                    {
                        "source": name,
                        "title": e.get("title", "").strip(),
                        "link": e.get("link", ""),
                        "description": e.get("summary", "") or e.get("description", ""),
                        "published": _to_datetime(e),
                        "image": _extract_entry_image(e),
                    }
                )
            logger.info("[%s] 抓到 %d 則", name, len(entries))

        except Exception as exc:  # noqa: BLE001 — 任一來源掛掉都不能拖垮其他
            logger.error("[%s] 抓取失敗,skip 該來源:%s", name, exc)
            continue

    logger.info("三來源合計 %d 則原始 entry", len(all_entries))
    return all_entries


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    entries = fetch_rss()
    print(f"\n=== 共 {len(entries)} 則 ===")
    for e in entries[:5]:
        print(f"[{e['source']}] {e['title']}  ({e['published']})")
