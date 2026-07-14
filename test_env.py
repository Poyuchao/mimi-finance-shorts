"""
階段 0 環境驗證：確認所有依賴都裝好、能 import，
外加檢查 ffmpeg 與 playwright chromium 是否就緒。

跑法（在 venv 啟用後）：
    python test_env.py
全部 [OK] 才算階段 0 過關。
"""

import importlib
import shutil
import subprocess
import sys

# Windows 主控台預設 cp950，強制用 UTF-8 輸出，避免中文/符號炸掉
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# (import 名稱, 顯示名稱)
PACKAGES = [
    ("feedparser", "feedparser"),
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("openai", "openai"),
    ("edge_tts", "edge-tts"),
    ("jinja2", "jinja2"),
    ("playwright", "playwright"),
    ("moviepy", "moviepy"),
    ("dotenv", "python-dotenv"),
]


def check_imports() -> bool:
    print("=== 套件 import 檢查 ===")
    all_ok = True
    for module, display in PACKAGES:
        try:
            importlib.import_module(module)
            print(f"  [OK]   {display}")
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {display}  ->  {e}")
            all_ok = False
    return all_ok


def check_ffmpeg() -> bool:
    print("=== ffmpeg 檢查 ===")
    exe = shutil.which("ffmpeg")
    if not exe:
        print("  [FAIL] 找不到 ffmpeg（沒在 PATH）")
        return False
    try:
        out = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, check=True
        )
        first = out.stdout.splitlines()[0] if out.stdout else "(無版本輸出)"
        print(f"  [OK]   {first}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] ffmpeg 執行失敗 -> {e}")
        return False


def check_playwright_chromium() -> bool:
    print("=== playwright chromium 檢查 ===")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        print("  [OK]   chromium 可啟動")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] chromium 無法啟動 -> {e}")
        print("         （若沒裝：playwright install chromium）")
        return False


def main() -> int:
    print(f"Python: {sys.version}\n")
    results = {
        "imports": check_imports(),
        "ffmpeg": check_ffmpeg(),
        "chromium": check_playwright_chromium(),
    }
    print("\n=== 總結 ===")
    for name, ok in results.items():
        print(f"  {name}: {'OK' if ok else 'FAIL'}")

    if all(results.values()):
        print("\n[PASS] 階段 0 環境全部就緒，可以進階段 1。")
        return 0
    print("\n[FAIL] 還有項目沒過，先修好再往下。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
