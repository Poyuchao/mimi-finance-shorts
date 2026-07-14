"""⑥ 字卡:HTML/CSS 模板(Jinja2) → Playwright 截圖成 png。

產出:output/cards/intro.png、news_1..n.png、outro.png(1080×1920)。
platform profile 預留:CTA 文字依平台切(ig=追蹤 / yt=訂閱)。
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

import config

logger = logging.getLogger(__name__)

CARDS_DIR = os.path.join("output", "cards")

# platform profile:CTA 文字(架構預留,現在先出一支通用)
PLATFORM_CTA = {"ig": "追蹤", "yt": "訂閱"}

_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

_env = Environment(loader=FileSystemLoader("templates"), autoescape=True)


def _date_str(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.year}.{dt.month:02d}.{dt.day:02d} 週{_WEEKDAYS[dt.weekday()]}"


def _render_html(template_name: str, **ctx) -> str:
    return _env.get_template(template_name).render(**ctx)


def _img_data_uri(path: str | None) -> str | None:
    """把圖片檔轉成 base64 data URI(內嵌進 HTML,避免 Playwright 讀本地路徑問題)。
    無圖/檔案不存在 → 回 None(該則走純字卡版面)。"""
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def render_program_cards(
    llm_result: dict,
    platform: str = "ig",
    cards_dir: str = CARDS_DIR,
    use_mimi: bool | None = None,
) -> dict:
    """🆕 UPDATE 2:一次產齊整支節目要的所有字卡(單一 Playwright session)。

    米米版(use_mimi=True):cover + news_i(不透明) + opening/closing(透明泡泡卡)
    純字卡版(False)     :cover + news_i(不透明) + closing_plain(不透明結尾)
    回傳 dict 給 video.compose 用。
    """
    use_mimi = config.USE_MIMI if use_mimi is None else use_mimi
    os.makedirs(cards_dir, exist_ok=True)
    items = llm_result.get("items", [])
    total = len(items)
    area = int(config.MIMI_AREA_RATIO * 100)
    cta = PLATFORM_CTA.get(platform, "追蹤")
    sources = "、".join(dict.fromkeys(it.get("source", "") for it in items if it.get("source")))
    hashtags = " ".join(llm_result.get("hashtags", []))

    def path(name: str) -> str:
        return os.path.join(cards_dir, name)

    # (輸出路徑, html, 是否透明)
    jobs: list[tuple[str, str, bool]] = []
    jobs.append((path("cover.png"),
                 _render_html("cover_card.html",
                              video_title=llm_result.get("video_title", ""),
                              date_str=_date_str(),
                              slogan=config.CHANNEL_SLOGAN), False))
    for i, item in enumerate(items, 1):
        jobs.append((path(f"news_{i}.png"),
                     _render_html("news_card.html", index=i, total=total,
                                  source=item.get("source", ""),
                                  headline=item.get("headline", ""),
                                  highlight=item.get("highlight") or {},
                                  script=item.get("script", ""),
                                  image_data=_img_data_uri(item.get("image_path"))), False))
    if use_mimi:
        jobs.append((path("opening.png"),
                     _render_html("opening_card.html", area_ratio=area,
                                  bubble=config.OPENING_BUBBLE), True))
        jobs.append((path("closing.png"),
                     _render_html("closing_card.html", area_ratio=area,
                                  bubble=config.OUTRO_BUBBLE, sources=sources,
                                  slogan=config.CHANNEL_SLOGAN), True))
    else:
        jobs.append((path("closing_plain.png"),
                     _render_html("outro_card.html", cta=cta, sources=sources,
                                  hashtags=hashtags), False))

    w, h = config.VIDEO["width"], config.VIDEO["height"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        for out, html, transparent in jobs:
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=out, omit_background=transparent)
            logger.info("字卡完成:%s", out)
        browser.close()

    result = {
        "cover": path("cover.png"),
        "news": [path(f"news_{i}.png") for i in range(1, total + 1)],
    }
    if use_mimi:
        result["opening"] = path("opening.png")
        result["closing"] = path("closing.png")
    else:
        result["closing_plain"] = path("closing_plain.png")
    return result


def render_headtail_cards(llm_result: dict, cards_dir: str = CARDS_DIR) -> dict:
    """🆕 UPDATE 2:開場白/收尾的透明泡泡卡(給米米疊層用)。

    回傳 {"opening": path, "closing": path}(透明背景 PNG)。
    """
    os.makedirs(cards_dir, exist_ok=True)
    items = llm_result.get("items", [])
    sources = "、".join(dict.fromkeys(it.get("source", "") for it in items if it.get("source")))
    area = int(config.MIMI_AREA_RATIO * 100)
    w, h = config.VIDEO["width"], config.VIDEO["height"]

    jobs = [
        ("opening.png", _render_html("opening_card.html",
                                     area_ratio=area, bubble=config.OPENING_BUBBLE)),
        ("closing.png", _render_html("closing_card.html",
                                     area_ratio=area, bubble=config.OUTRO_BUBBLE, sources=sources,
                                     slogan=config.CHANNEL_SLOGAN)),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        for filename, html in jobs:
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=os.path.join(cards_dir, filename), omit_background=True)
            logger.info("頭尾卡完成:%s", filename)
        browser.close()
    return {
        "opening": os.path.join(cards_dir, "opening.png"),
        "closing": os.path.join(cards_dir, "closing.png"),
    }


def render_cover_card(llm_result: dict, cards_dir: str = CARDS_DIR) -> str:
    """🆕 UPDATE 2:封面卡(🐱 米米財經 + LLM video_title + 日期)。回傳 png 路徑。"""
    os.makedirs(cards_dir, exist_ok=True)
    w, h = config.VIDEO["width"], config.VIDEO["height"]
    html = _render_html("cover_card.html",
                        video_title=llm_result.get("video_title", ""),
                        date_str=_date_str(),
                        slogan=config.CHANNEL_SLOGAN)
    out = os.path.join(cards_dir, "cover.png")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=out)
        browser.close()
    logger.info("封面卡完成:%s", out)
    return out


def render_news_cards(llm_result: dict, cards_dir: str = CARDS_DIR) -> list[str]:
    """🆕 UPDATE 2:只產「純字卡新聞」PNG(不透明、無米米、數字視覺化)。

    highlight 為結構化 {value, trend, label}。回傳 news png 路徑列表。
    """
    os.makedirs(cards_dir, exist_ok=True)
    items = llm_result.get("items", [])
    total = len(items)
    w, h = config.VIDEO["width"], config.VIDEO["height"]
    paths: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        for i, item in enumerate(items, 1):
            html = _render_html(
                "news_card.html",
                index=i, total=total,
                source=item.get("source", ""),
                headline=item.get("headline", ""),
                highlight=item.get("highlight") or {},
                script=item.get("script", ""),
                image_data=_img_data_uri(item.get("image_path")),
            )
            out = os.path.join(cards_dir, f"news_{i}.png")
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=out)   # 不透明
            paths.append(out)
            logger.info("新聞卡完成:%s", out)
        browser.close()
    return paths


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with open("output_llm.json", encoding="utf-8") as f:
        result = json.load(f)

    cards = render_program_cards(result)
    print("\n=== 字卡完成 ===")
    for k, v in cards.items():
        print(f"{k}: {v}")
