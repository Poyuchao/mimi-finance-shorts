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


_TTS_RETRIES = 3   # edge-tts 走微軟非官方端點,403/連線錯誤常是暫時性 → 退避重試


async def _synth_edge(text: str, path: str, voice: str) -> None:
    """edge-tts 合成(線上、音質好);失敗退避重試,全部失敗才 raise。

    ★ 403(WSServerHandshakeError)多半是微軟端點限流/IP 被標記;產出空檔也算失敗。★
    """
    last: Exception | None = None
    for attempt in range(1, _TTS_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(text, voice=voice)
            await communicate.save(path)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return
            raise RuntimeError("edge-tts 產出空音檔")
        except Exception as exc:  # noqa: BLE001 — 攔下來退避重試
            last = exc
            if attempt < _TTS_RETRIES:
                wait = 2 * attempt
                logger.warning("edge-tts 第 %d/%d 次失敗:%s(%d 秒後重試)",
                               attempt, _TTS_RETRIES, exc, wait)
                await asyncio.sleep(wait)
    logger.error("edge-tts 重試 %d 次仍失敗:%s", _TTS_RETRIES, last)
    raise last if last else RuntimeError("edge-tts 失敗")


# ── 🆕 UPDATE 16:本機離線 TTS(edge-tts 被微軟持續 403 時頂上;離線、免費、不會 403)──
# 兩個後端:
#   winrt — OneCore 語音(Yating/Zhiwei,音質好),經 PowerShell 叫 WinRT(繞過在 3.14 裝不起來的 winsdk)
#   sapi  — Windows SAPI5 的 Hanhan(win32com;音色較老派),當 winrt 失敗時的最後備援
_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_winrt.ps1")
_SSFM_CREATE_FOR_WRITE = 3   # SpFileStream 模式:建立並覆寫


def _synth_winrt(text: str, wav_path: str) -> None:
    """用 PowerShell 叫 OneCore 語音(Yating 等)合成 wav。失敗/空檔 → raise。"""
    import subprocess
    import tempfile

    tf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        tf.write(text)
        tf.close()
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _PS1,
             "-TextFile", tf.name, "-OutFile", os.path.abspath(wav_path),
             "-VoiceMatch", config.TTS_LOCAL_VOICE, "-Rate", str(config.TTS_WINRT_RATE)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"WinRT TTS 失敗:{(proc.stderr or proc.stdout).strip()[:200]}")
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass
    if not (os.path.exists(wav_path) and os.path.getsize(wav_path) > 0):
        raise RuntimeError("WinRT TTS 產出空檔")


def _synth_sapi(text: str, wav_path: str) -> None:
    """用 win32com SAPI SpVoice 合成 wav(同步、可重複呼叫;挑 zh-TW Hanhan)。"""
    import win32com.client

    voice = win32com.client.Dispatch("SAPI.SpVoice")
    for tok in voice.GetVoices():
        if "ZH-TW" in (tok.Id or "").upper():   # 挑 zh-TW(Hanhan Desktop),避免抓到英文語音
            voice.Voice = tok
            break
    else:
        logger.warning("SAPI 找不到 zh-TW 語音,用系統預設")

    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(wav_path, _SSFM_CREATE_FOR_WRITE)
    try:
        voice.AudioOutputStream = stream
        voice.Speak(text)
    finally:
        stream.Close()
    if not (os.path.exists(wav_path) and os.path.getsize(wav_path) > 0):
        raise RuntimeError("SAPI TTS 產出空檔")


def _synth_local(text: str, wav_path: str) -> None:
    """本機合成:依 TTS_LOCAL_BACKEND 選後端;winrt 失敗自動退 sapi(Hanhan)。"""
    if getattr(config, "TTS_LOCAL_BACKEND", "winrt") == "sapi":
        _synth_sapi(text, wav_path)
        return
    try:
        _synth_winrt(text, wav_path)
    except Exception as exc:  # noqa: BLE001 — WinRT 掛了還有 SAPI 兜底
        logger.warning("WinRT 本機語音失敗,退 SAPI(Hanhan):%s", exc)
        _synth_sapi(text, wav_path)


def _produce(text: str, out_path: str, voice: str) -> str:
    """依 config.TTS_ENGINE 產生音檔,回傳「實際產出的路徑」(本機版副檔名為 .wav)。

    auto:先試 edge(音質好),失敗自動切本機 Hanhan → 發片永不被 403 卡死。
    edge:只用 edge(失敗就 raise)。 local:直接用本機。
    """
    engine = getattr(config, "TTS_ENGINE", "auto")
    if engine in ("auto", "edge"):
        try:
            asyncio.run(_synth_edge(text, out_path, voice))
            return out_path
        except Exception as exc:  # noqa: BLE001
            if engine == "edge":
                raise
            logger.warning("edge-tts 失敗 → 改用本機語音頂上:%s", exc)

    wav_path = os.path.splitext(out_path)[0] + ".wav"
    _synth_local(text, wav_path)
    logger.info("本機 TTS 產出:%s", wav_path)
    return wav_path


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

        actual = _produce(script, path, voice)
        duration = _get_duration(actual)
        logger.info("第 %d 則配音完成:%s(%.1f 秒)", i, actual, duration)
        results.append({**item, "audio_path": actual, "duration": duration})

    return results


def synthesize_line(text: str, out_path: str, voice: str | None = None) -> dict:
    """🆕 UPDATE 2:單句配音(開場白/收尾用)。回傳 {audio_path, duration}。"""
    voice = voice or config.TTS_VOICE
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    actual = _produce(text, out_path, voice)
    duration = _get_duration(actual)
    logger.info("配音完成:%s(%.1f 秒)", actual, duration)
    return {"audio_path": actual, "duration": duration}


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
