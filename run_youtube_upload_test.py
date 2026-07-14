r"""階段 U3-2:上傳單獨測。把現成的 output/final.mp4 傳成「私人」影片。

跑法:  .\venv\Scripts\python.exe run_youtube_upload_test.py
"""

import json
import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import config
from publisher import youtube


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open("output_llm.json", encoding="utf-8") as f:
        result = json.load(f)
    meta = youtube.build_youtube_metadata(result)
    print(f"標題:{meta['title']}")

    yt = youtube.get_authenticated_service()
    video_id = youtube.upload_video(yt, "output/final.mp4", meta)

    print("\n" + "=" * 50)
    print(f"✅ 上傳完成({config.YT_PRIVACY}):https://youtu.be/{video_id}")
    print("   到 YT 後台(內容)確認影片、標題、描述,並勾『AI/合成內容』標註")
    print("=" * 50)


if __name__ == "__main__":
    main()
