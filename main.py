r"""串整條 pipeline:抓 RSS → 篩股市 → 候選 → LLM 選片 → LLM 改寫
→ TTS 配音 → 字卡 → 影片合成 → output/final.mp4。

跑法:  .\venv\Scripts\python.exe main.py
"""

import json
import logging
import sys
import time

# Windows 主控台 cp950,強制 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import card_render
import config
import fetch_rss
import image_service
import parse_filter
import select_news
import tts
import video
from db import repository
from db.database import get_session, init_db
from llm_service import OpenAIService

logger = logging.getLogger("main")


def _step(n: int, msg: str) -> None:
    total = 8 if config.UPLOAD_ENABLED else 7
    print(f"\n{'─' * 60}\n[{n}/{total}] {msg}\n{'─' * 60}")


def run(platform: str = "ig") -> str:
    t0 = time.time()
    init_db()   # 🆕 UPDATE 6:首次自動建表

    _step(1, "抓 RSS(3 來源)")
    entries = fetch_rss.fetch_rss()
    if not entries:
        raise RuntimeError("三來源都抓不到任何新聞,終止")

    _step(2, "解析 + 篩股市 + 清洗")
    stock_news = parse_filter.parse_filter(entries)
    if not stock_news:
        raise RuntimeError("篩不到任何股市新聞,終止(檢查關鍵字/來源)")

    _step(3, "收斂候選池(去重 + 排序)")
    candidates = select_news.select_news(stock_news)

    svc = OpenAIService()

    _step(4, "LLM 第一步:選片(挑 3 則 + 理由)")
    picked = svc.select_top_news(candidates)
    for rank, p in enumerate(picked, 1):
        print(f"  {rank}. [{p['source']}] {p['title']}  ← {p.get('reason','')}")

    _step(5, "LLM 第二步:改寫口播稿")
    llm_result = svc.rewrite_scripts(picked)
    print(f"  影片標題:{llm_result['video_title']}")
    with open("output_llm.json", "w", encoding="utf-8") as f:
        json.dump(llm_result, f, ensure_ascii=False, indent=2)

    # 🆕 UPDATE 4:每則生 AI 示意圖(rewrite 後、字卡前;失敗回 None 不中斷)
    print(f"\n{'─' * 60}\n[+] 生成新聞示意圖(每則;失敗即 fallback 純字卡)\n{'─' * 60}")
    if config.USE_AI_IMAGE:
        for i, item in enumerate(llm_result["items"], 1):
            item["image_path"] = image_service.safe_generate(item, i)
        used = sum(1 for it in llm_result["items"] if it.get("image_path"))
        print(f"  生圖:{used}/{len(llm_result['items'])} 則成功(其餘用純字卡)")
    else:
        for item in llm_result["items"]:
            item["image_path"] = None
        print("  USE_AI_IMAGE=False,三則都用純字卡")

    _step(6, "TTS 配音(3 則新聞 + 開場白/收尾)+ 字卡")
    news_audio = tts.synthesize_items(llm_result["items"])
    opening_audio = closing_audio = None
    if config.USE_MIMI:
        opening_audio = tts.synthesize_line(config.OPENING_LINE, "output/audio/opening.mp3")
        closing_audio = tts.synthesize_line(config.OUTRO_LINE, "output/audio/outro.mp3")
    cards = card_render.render_program_cards(llm_result, platform=platform)

    _step(7, "影片合成(封面+開場白+3新聞+收尾)→ mp4")
    out = video.compose(cards, news_audio, opening_audio, closing_audio)

    # ⑧ UPDATE 3:自動上傳 YouTube(上傳失敗不影響已產出的 mp4)
    youtube_url = None
    if config.UPLOAD_ENABLED:
        _step(8, "上傳 YouTube")
        try:
            from publisher import youtube
            yt = youtube.get_authenticated_service()
            has_ai_image = any(it.get("image_path") for it in llm_result["items"])
            meta = youtube.build_youtube_metadata(llm_result, has_ai_image=has_ai_image)
            video_id = youtube.upload_video(yt, out, meta)
            youtube_url = f"https://youtu.be/{video_id}"
            print(f"  ✅ 已上傳:{youtube_url}（{config.YT_PRIVACY}）")
            print("  ⚠️ 提醒:記得到 YT 後台(內容→編輯)勾選『變造/AI 合成內容』標註")
        except Exception as exc:  # noqa: BLE001 — 上傳失敗不能弄丟已產出的 mp4
            logger.exception("上傳失敗(mp4 已保留,可手動上傳):%s", exc)
    else:
        print("\n(UPLOAD_ENABLED=False,略過上傳,只產本機 mp4)")

    # ⑨ UPDATE 6:寫入 DB(候選池 + 選片結果)
    # ★ 記錄是附屬功能:寫失敗只 log,絕不中斷發片 ★
    try:
        # picked 已是完整候選 dict(含 link/reason)→ 不需 index 對映
        selected_links = {p["link"] for p in picked}
        reasons = {p["link"]: p.get("reason", "") for p in picked}
        positions = {p["link"]: i + 1 for i, p in enumerate(picked)}

        session = get_session()
        try:
            run_id = repository.save_run(
                session,
                status="success",
                video_title=llm_result.get("video_title"),
                youtube_url=youtube_url,
                candidates=candidates,          # 候選 ~10 篇全記
                selected_links=selected_links,
                reasons=reasons,
                positions=positions,
            )
            print(f"\n  📝 已記錄到 DB(run_id={run_id}:候選 {len(candidates)} 篇,"
                  f"選中 {len(selected_links)} 篇)")
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 — 寫 DB 失敗不能拖垮發片
        logger.warning("寫入 DB 失敗(不影響發片):%s", exc)

    dt = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"✅ 完成:{out}(全程 {dt:.0f} 秒)")
    print(f"{'=' * 60}")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline 失敗:%s", exc)
        sys.exit(1)
