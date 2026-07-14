r"""階段 U3-1:YouTube 認證單獨測試。

第一次跑會開瀏覽器 → 登入 + 同意 → 產生 token.json。
再跑一次應「不用重新授權」(讀 token 成功)。

跑法:  .\venv\Scripts\python.exe run_youtube_auth.py
"""

import logging
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import config
from publisher import youtube


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    first_time = not os.path.exists(config.YT_TOKEN_FILE)
    if first_time:
        print("首次授權:等一下會開瀏覽器,請登入米米財經 / 測試 YT 帳號並按『同意』。\n")

    youtube.get_authenticated_service()

    print("\n" + "=" * 50)
    print(f"✅ 認證成功,token 已就緒:{config.YT_TOKEN_FILE}"
          f"({'首次產生' if first_time else '讀既有 token,未重新授權'})")
    print("=" * 50)


if __name__ == "__main__":
    main()
