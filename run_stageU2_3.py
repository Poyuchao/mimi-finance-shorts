r"""階段 U2-3:開場白 + 收尾兩段(米米疊層,單獨驗)。

TTS 開場白/收尾 → 產透明泡泡卡 → 米米疊層合成兩段測試片。
產出:output/opening_test.mp4、output/closing_test.mp4

跑法:  .\venv\Scripts\python.exe run_stageU2_3.py
"""

import json
import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import config
import card_render
import tts
import video


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open("output_llm.json", encoding="utf-8") as f:
        result = json.load(f)

    # 1. 開場白/收尾旁白 TTS
    opening = tts.synthesize_line(config.OPENING_LINE, "output/audio/opening.mp3")
    closing = tts.synthesize_line(config.OUTRO_LINE, "output/audio/outro.mp3")

    # 2. 透明泡泡卡
    cards = card_render.render_headtail_cards(result)

    # 3. 米米疊層合成(各一段)
    fps = config.VIDEO["fps"]
    seg1 = video.make_mimi_segment(config.MIMI_CLIPS["intro"], cards["opening"],
                                   opening["duration"], opening["audio_path"])
    seg1.write_videofile("output/opening_test.mp4", fps=fps, codec="libx264", audio_codec="aac")
    seg1.close()

    seg2 = video.make_mimi_segment(config.MIMI_CLIPS["outro"], cards["closing"],
                                   closing["duration"], closing["audio_path"])
    seg2.write_videofile("output/closing_test.mp4", fps=fps, codec="libx264", audio_codec="aac")
    seg2.close()

    print(f"\n開場白 {opening['duration']:.1f}s → output/opening_test.mp4")
    print(f"收尾   {closing['duration']:.1f}s → output/closing_test.mp4")


if __name__ == "__main__":
    main()
