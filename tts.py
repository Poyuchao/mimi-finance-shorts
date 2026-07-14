"""⑤ TTS 配音。把每則 script(口播稿)→ mp3,並取得時長(給影片用)。

用 edge-tts(async),台灣女聲 zh-TW-HsiaoChenNeural。
時長:用 moviepy 的 AudioFileClip(path).duration。
"""

from __future__ import annotations

import asyncio
import logging
import os

import edge_tts

import config

logger = logging.getLogger(__name__)

AUDIO_DIR = os.path.join("output", "audio")


async def _synth_one(text: str, path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(path)


def _get_duration(path: str) -> float:
    """讀 mp3 時長(秒)。"""
    from moviepy import AudioFileClip

    clip = AudioFileClip(path)
    try:
        return float(clip.duration)
    finally:
        clip.close()


def synthesize_items(
    items: list[dict],
    voice: str | None = None,
    audio_dir: str = AUDIO_DIR,
) -> list[dict]:
    """把每則 item 的 script 轉成 mp3。

    回傳:每則附上 {audio_path, duration}(合併回原 item)。
    """
    voice = voice or config.TTS_VOICE
    os.makedirs(audio_dir, exist_ok=True)

    results: list[dict] = []
    for i, item in enumerate(items, 1):
        script = (item.get("script") or "").strip()
        path = os.path.join(audio_dir, f"item_{i}.mp3")

        if not script:
            logger.warning("第 %d 則沒有 script,跳過 TTS", i)
            results.append({**item, "audio_path": None, "duration": 0.0})
            continue

        asyncio.run(_synth_one(script, path, voice))
        duration = _get_duration(path)
        logger.info("第 %d 則配音完成:%s(%.1f 秒)", i, path, duration)
        results.append({**item, "audio_path": path, "duration": duration})

    return results


def synthesize_line(text: str, out_path: str, voice: str | None = None) -> dict:
    """🆕 UPDATE 2:單句配音(開場白/收尾用)。回傳 {audio_path, duration}。"""
    voice = voice or config.TTS_VOICE
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    asyncio.run(_synth_one(text, out_path, voice))
    duration = _get_duration(out_path)
    logger.info("配音完成:%s(%.1f 秒)", out_path, duration)
    return {"audio_path": out_path, "duration": duration}


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with open("output_llm.json", encoding="utf-8") as f:
        result = json.load(f)

    audio_items = synthesize_items(result["items"])
    print("\n=== TTS 完成 ===")
    total = 0.0
    for i, it in enumerate(audio_items, 1):
        total += it["duration"]
        print(f"第 {i} 則:{it['audio_path']}  {it['duration']:.1f} 秒")
    print(f"三則語音合計 ~{total:.0f} 秒(加開場/結尾約 {total + 6:.0f} 秒)")
