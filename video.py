"""⑦ 影片合成:字卡 png + 配音 mp3 → final.mp4。

用 MoviePy(底層 ffmpeg)。
  • 開場卡:固定秒數(無聲)
  • 每則新聞卡:顯示時長 = 該則配音時長,並掛上配音
  • 結尾卡:固定秒數(無聲)
"""

from __future__ import annotations

import logging
import os

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

import config

logger = logging.getLogger(__name__)

OUT_PATH = "output/final.mp4"


def make_mimi_segment(
    mimi_path: str,
    card_png: str,
    duration: float,
    audio_path: str | None = None,
):
    """🆕 UPDATE 1:一個米米片段 = 米米動畫(底,循環撐滿) + 透明字卡(上) + 旁白。

    米米:resize 對齊寬 → 循環撐滿 duration → 去自帶聲 → 擺上半(下半被字卡深藍底蓋掉)。
    回傳 CompositeVideoClip(1080×1920,已設 duration 與 audio)。
    """
    w, h = config.VIDEO["width"], config.VIDEO["height"]

    mimi = VideoFileClip(mimi_path).without_audio()   # ★ 去掉米米素材自帶聲音
    mimi = mimi.resized(width=w)                       # 720×1280 → 1080×1920(對齊寬)
    mimi = mimi.with_effects([vfx.Loop(duration=duration)])  # 循環撐滿旁白長度
    mimi = mimi.with_position(("center", "top"))       # 擺上半

    card = ImageClip(card_png, transparent=True).with_duration(duration)

    comp = CompositeVideoClip([mimi, card], size=(w, h)).with_duration(duration)
    if audio_path:
        comp = comp.with_audio(AudioFileClip(audio_path))
    return comp


def _plain_segment(card_path: str, duration: float, audio_path: str | None = None):
    """不透明純字卡片段(封面/新聞/純字卡結尾/fallback 用)。"""
    clip = ImageClip(card_path).with_duration(duration)
    if audio_path:
        clip = clip.with_audio(AudioFileClip(audio_path))
    return clip


def compose(
    cards: dict,
    news_audio: list[dict],
    opening_audio: dict | None = None,
    closing_audio: dict | None = None,
    out_path: str = OUT_PATH,
    cover_dur: float = 3.0,
    closing_dur: float = 3.0,
) -> str:
    """🆕 UPDATE 2:4 階段 6 片段合成。依 config.USE_MIMI 分流。

    cards: {"cover","news":[...], 米米版另有 "opening"/"closing";純版另有 "closing_plain"}
    news_audio: [{audio_path,duration}, ...](對齊 cards["news"])
    opening_audio / closing_audio: {audio_path,duration}(米米版才需要)
    """
    if config.USE_MIMI:
        return _compose_mimi(cards, news_audio, opening_audio, closing_audio, out_path, cover_dur)
    return _compose_plain(cards, news_audio, out_path, cover_dur, closing_dur)


def _news_segments(cards, news_audio):
    """3 則純字卡新聞(不透明 + 旁白),米米/純版共用。"""
    segs = []
    for card_path, ai in zip(cards["news"], news_audio):
        dur = ai.get("duration") or 5.0
        segs.append(_plain_segment(card_path, dur, ai.get("audio_path")))
    return segs


def _mimi_or_fallback(clip_path, transp_card, dur, audio_path):
    """有素材 → 米米疊層;缺素材 → 用透明卡當靜態卡(不崩,upper 呈深色)。"""
    if clip_path and os.path.exists(clip_path):
        return make_mimi_segment(clip_path, transp_card, dur, audio_path)
    logger.warning("米米素材缺(%s)→ 該段退純字卡(靜態)", clip_path)
    return _plain_segment(transp_card, dur, audio_path)


def _compose_mimi(cards, news_audio, opening_audio, closing_audio, out_path, cover_dur) -> str:
    """米米頭尾版:封面 + 米米開場白 + 3 純字卡新聞 + 米米收尾。"""
    fps = config.VIDEO["fps"]
    segs = []

    # ① 封面(靜態純字卡,無聲)
    segs.append(_plain_segment(cards["cover"], cover_dur))
    # ② 米米開場白(疊層 + 旁白)
    op = opening_audio or {}
    segs.append(_mimi_or_fallback(config.MIMI_CLIPS.get("intro"), cards["opening"],
                                  op.get("duration") or 5.0, op.get("audio_path")))
    # ③ 3 則純字卡新聞
    segs += _news_segments(cards, news_audio)
    # ④ 米米收尾(疊層 + 旁白)
    cl = closing_audio or {}
    segs.append(_mimi_or_fallback(config.MIMI_CLIPS.get("outro"), cards["closing"],
                                  cl.get("duration") or 5.0, cl.get("audio_path")))

    final = concatenate_videoclips(segs, method="compose")
    logger.info("合成中(米米頭尾版,6 片段)… 總長約 %.1f 秒 → %s", final.duration, out_path)
    final.write_videofile(out_path, fps=fps, codec="libx264", audio_codec="aac")
    final.close()
    for s in segs:
        s.close()
    return out_path


def _compose_plain(cards, news_audio, out_path, cover_dur, closing_dur) -> str:
    """純字卡版(USE_MIMI=False):封面 + 3 純字卡新聞 + 純字卡結尾(來源),無米米。"""
    fps = config.VIDEO["fps"]
    segs = []
    segs.append(_plain_segment(cards["cover"], cover_dur))
    segs += _news_segments(cards, news_audio)
    segs.append(_plain_segment(cards["closing_plain"], closing_dur))

    final = concatenate_videoclips(segs, method="compose")
    logger.info("合成中(純字卡版,無米米)… 總長約 %.1f 秒 → %s", final.duration, out_path)
    final.write_videofile(out_path, fps=fps, codec="libx264", audio_codec="aac")
    final.close()
    for s in segs:
        s.close()
    return out_path
