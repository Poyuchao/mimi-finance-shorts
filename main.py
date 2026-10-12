r"""串整條 pipeline:抓 RSS → 篩股市 → 候選 → LLM 選片 → LLM 改寫
→ TTS 配音 → 字卡 → 影片合成 → output/final.mp4。

跑法:  .\venv\Scripts\python.exe main.py
"""

import asyncio
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
import mcp_client
import parse_filter
import select_news
import tts
import video
from db import repository
from db.database import get_session, init_db
from llm_service import OpenAIService

logger = logging.getLogger("main")

# 🆕 UPDATE 15:事件發送(給控制台即時跑片 SSE 用)。
# API 跑片前把 EMIT 設成 api.events.emit;CLI 直接跑時 EMIT 為 None → ★行為完全不變★。
# ★ 事件機制絕不影響發片:EMIT=None 不做事,_emit 本身也包 try/except。★
EMIT = None


def _emit(kind: str, **data) -> None:
    if EMIT:
        try:
            EMIT(kind, data)
        except Exception:  # noqa: BLE001 — 發事件失敗不能拖垮發片
            pass


def _stage(name: str, sub: str = "") -> None:
    _emit("stage", name=name, sub=sub)


def _log(text: str, level: str = "info") -> None:
    _emit("log", text=text, level=level)


def _review(rtype: str, index: int, status: str, blocking=None,
            before: str | None = None, after: str | None = None) -> None:
    # 🆕 UPDATE 15:審稿/審圖結果給控制台「審查流程」面板
    _emit("review", type=rtype, index=index, status=status,
          blocking=blocking or [], before=before, after=after)


def _step(n: int, msg: str) -> None:
    total = 6 if config.UPLOAD_ENABLED else 5
    print(f"\n{'─' * 60}\n[{n}/{total}] {msg}\n{'─' * 60}")
    _stage(msg)


def run(platform: str = "ig") -> str:
    t0 = time.time()
    init_db()   # 🆕 UPDATE 6:首次自動建表

    # ①②③ 🆕 UPDATE 8:優先走 MCP 取得候選池;失敗則 fallback 回直接呼叫
    recent: list[dict] = []
    candidates = None
    if config.USE_MCP:
        _step(1, "透過 MCP 取得候選池 + 歷史選片")
        try:
            candidates, recent = asyncio.run(
                mcp_client.fetch_candidates_via_mcp(
                    pool_size=config.NEWS_POOL, dedup_days=config.DEDUP_DAYS
                )
            )
            print(f"  MCP:候選 {len(candidates)} 則、近 {config.DEDUP_DAYS} 天已發 {len(recent)} 則")
            _log(f"MCP:候選 {len(candidates)} 則、近 {config.DEDUP_DAYS} 天已發 {len(recent)} 則")
        except Exception as exc:  # noqa: BLE001 — MCP 掛掉不能讓發片停擺
            logger.warning("MCP 取得失敗,fallback 直接呼叫:%s", exc)
            candidates = None

    if not candidates:
        _step(1, "抓 RSS(3 來源)→ 篩股市 → 候選池(直接呼叫)")
        entries = fetch_rss.fetch_rss()
        if not entries:
            raise RuntimeError("三來源都抓不到任何新聞,終止")
        stock_news = parse_filter.parse_filter(entries)
        if not stock_news:
            raise RuntimeError("篩不到任何股市新聞,終止(檢查關鍵字/來源)")
        candidates = select_news.select_news(stock_news)
        _log(f"RSS fallback:候選 {len(candidates)} 則")

    svc = OpenAIService()

    _step(2, "LLM 第一步:選片(挑 3 則 + 理由)")
    # 🆕 UPDATE 8:把「最近已發過的」帶進 prompt,讓 agent 避免重複報導
    picked = svc.select_top_news(candidates, recent=recent)
    for rank, p in enumerate(picked, 1):
        print(f"  {rank}. [{p['source']}] {p['title']}  ← {p.get('reason','')}")
        _log(f"{rank}. [{p['source']}] {p['title']}")

    # 🆕 UPDATE 14:抓選中 3 則的全文(RSS 只給殘缺摘要 → 改寫/審稿會誤判數字編造)
    # ★ 覆蓋 clean_text 一處,改寫與審稿同時吃到完整原文;抓不到 fallback 摘要,不中斷。★
    if config.USE_FULLTEXT:
        print(f"\n{'─' * 60}\n[+] 抓選中新聞全文(改寫/審稿用完整原文,抓不到退摘要)\n{'─' * 60}")
        _stage("抓選中新聞全文")
        import article_fetch
        got = article_fetch.enrich_fulltext(picked)
        print(f"  全文:{got}/{len(picked)} 則取得,其餘用 RSS 摘要")
        _log(f"全文:{got}/{len(picked)} 則取得,其餘用 RSS 摘要", "ok")

    _step(3, "LLM 第二步:改寫口播稿")
    llm_result = svc.rewrite_scripts(picked)
    print(f"  影片標題:{llm_result['video_title']}")
    _log(f"影片標題:{llm_result['video_title']}")

    # 🆕 UPDATE 12:審稿(改寫後、存檔前)——稿是否忠於原文?偏離/投資建議就重寫。
    # ★ fail-open:審稿出錯/不過到底 → 用原稿,絕不中斷發片。USE_SCRIPT_REVIEW=False 則完全跳過。★
    if config.USE_SCRIPT_REVIEW:
        print(f"\n{'─' * 60}\n[+] 審稿:檢查口播稿是否忠於原文(偏離/投資建議就重寫)\n{'─' * 60}")
        _stage("審稿 critic")
        import script_review
        n_fixed = 0
        # picked(含原文 clean_text)與 items 順序對齊 → zip 配對
        for i, (cand, item) in enumerate(zip(picked, llm_result["items"]), 1):
            # ★ critic 要看到跟 rewrite 一樣的來源(標題 + 內文)——
            #   否則標題裡的事實(如收盤點數)只在 title、critic 只拿 clean_text 時會誤判成「編造」。
            source = "\n".join(
                x for x in (cand.get("title", ""), cand.get("clean_text") or "") if x
            ) or cand.get("title", "")
            res = script_review.safe_review_and_fix_verbose(source, item["script"])
            item["script"] = res["script"]
            if res["changed"]:
                n_fixed += 1
                print(f"  ✏️ 第 {i} 則審稿不通過 → 已重寫")
                _log(f"第 {i} 則審稿不通過 → 已重寫", "warn")
            # 🆕 UPDATE 15:把審稿結果送給控制台「審查流程」面板
            _review("script", i, res["status"], blocking=res["blocking"],
                    before=res["before"], after=res["after"])
        print(f"  審稿完成:{n_fixed}/{len(llm_result['items'])} 則重寫,其餘原稿")
        _log(f"審稿完成:{n_fixed}/{len(llm_result['items'])} 則重寫,其餘原稿", "ok")

    with open("output_llm.json", "w", encoding="utf-8") as f:
        json.dump(llm_result, f, ensure_ascii=False, indent=2)

    # 🆕 UPDATE 4:每則生 AI 示意圖(rewrite 後、字卡前;失敗回 None 不中斷)
    print(f"\n{'─' * 60}\n[+] 生成新聞示意圖(每則;失敗即 fallback 純字卡)\n{'─' * 60}")
    _stage("AI 生圖 + 審圖")
    if config.USE_AI_IMAGE:
        for i, item in enumerate(llm_result["items"], 1):
            # 🆕 UPDATE 15:on_review 把每則審圖結果送給控制台面板(i=i 綁當下的 i)
            item["image_path"] = image_service.safe_generate(
                item, i,
                on_review=lambda r, i=i: _review("image", i, r["status"], blocking=r.get("blocking")),
            )
        used = sum(1 for it in llm_result["items"] if it.get("image_path"))
        print(f"  生圖:{used}/{len(llm_result['items'])} 則成功(其餘用純字卡)")
        _log(f"生圖:{used}/{len(llm_result['items'])} 則成功(其餘純字卡)", "ok")
    else:
        for item in llm_result["items"]:
            item["image_path"] = None
        print("  USE_AI_IMAGE=False,三則都用純字卡")

    _step(4, "TTS 配音(3 則新聞 + 開場白/收尾)+ 字卡")
    news_audio = tts.synthesize_items(llm_result["items"])
    opening_audio = closing_audio = None
    if config.USE_MIMI:
        opening_audio = tts.synthesize_line(config.OPENING_LINE, "output/audio/opening.mp3")
        closing_audio = tts.synthesize_line(config.OUTRO_LINE, "output/audio/outro.mp3")
    cards = card_render.render_program_cards(llm_result, platform=platform)

    _step(5, "影片合成(封面+開場白+3新聞+收尾)→ mp4")
    out = video.compose(cards, news_audio, opening_audio, closing_audio)

    # ⑧ UPDATE 3:自動上傳 YouTube(上傳失敗不影響已產出的 mp4)
    youtube_url = None
    if config.UPLOAD_ENABLED:
        _step(6, "上傳 YouTube")
        try:
            from publisher import youtube
            yt = youtube.get_authenticated_service()
            has_ai_image = any(it.get("image_path") for it in llm_result["items"])
            meta = youtube.build_youtube_metadata(llm_result, has_ai_image=has_ai_image)
            video_id = youtube.upload_video(yt, out, meta)
            youtube_url = f"https://youtu.be/{video_id}"
            print(f"  ✅ 已上傳:{youtube_url}（{config.YT_PRIVACY}）")
            _log(f"已上傳:{youtube_url}（{config.YT_PRIVACY}）", "ok")
            print("  ⚠️ 提醒:記得到 YT 後台(內容→編輯)勾選『變造/AI 合成內容』標註")
        except Exception as exc:  # noqa: BLE001 — 上傳失敗不能弄丟已產出的 mp4
            logger.exception("上傳失敗(mp4 已保留,可手動上傳):%s", exc)
    else:
        print("\n(UPLOAD_ENABLED=False,略過上傳,只產本機 mp4)")

    # ⑨ UPDATE 6:寫入 DB(候選池 + 選片結果)
    # ★ 記錄是附屬功能:寫失敗只 log,絕不中斷發片 ★
    run_id = None   # 先給預設,讓最後的 done 事件就算 DB 失敗也不會 NameError
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
            _log(f"已記錄到 DB(run_id={run_id}:候選 {len(candidates)}、選中 {len(selected_links)})", "ok")
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 — 寫 DB 失敗不能拖垮發片
        # ★ 影片照發,但要「叫得夠大聲」★
        #   曾經因為只印一行 warning,連續 3 天沒記錄卻沒人發現(MCP 的 published
        #   是字串、DB 欄位是 DateTime)。容錯不等於靜音。
        logger.exception("寫入 DB 失敗:%s", exc)
        print(f"\n{'!' * 60}")
        print(f"  ⚠️ 寫入 DB 失敗,這次執行沒有留下選片記錄:{exc}")
        print("     影片不受影響(已產出/已上傳),但 query_runs.py 查不到這次。")
        print(f"{'!' * 60}")

    dt = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"✅ 完成:{out}(全程 {dt:.0f} 秒)")
    print(f"{'=' * 60}")
    _emit("done", path=out, seconds=int(dt), youtube=youtube_url, run_id=run_id)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline 失敗:%s", exc)
        sys.exit(1)
