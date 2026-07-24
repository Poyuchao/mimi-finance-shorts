"""④e AI 審圖 agent(UPDATE 5)。

看一張生成的示意圖 + 該則新聞 → 判斷「能不能上片」,回 {"pass": bool, "issues": [...]}。

★ 防呆原則(跟 image_service 一致):
  審查 API 失效/逾時/解析失敗 → 🔴 保守視為「不通過」(不發沒審過的圖)。
  任何情況都不 raise;最終不通過 = 該則退回純字卡,絕不擋發片。
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from abc import ABC, abstractmethod

import config

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


class ReviewService(ABC):
    """provider-agnostic 審圖介面。"""

    @abstractmethod
    def review(self, image_path: str, item: dict) -> dict:
        """回 {"pass": bool, "issues": [str, ...]}。"""
        raise NotImplementedError


class GeminiReviewService(ReviewService):
    """Gemini 視覺文字模型審圖(SDK: google-genai)。"""

    def __init__(self, model: str | None = None):
        from google import genai

        if not config.GEMINI_API_KEY:
            raise RuntimeError("找不到 GEMINI_API_KEY(檢查 .env)")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = model or config.REVIEW_MODEL

    def review(self, image_path: str, item: dict) -> dict:
        from google.genai import types

        with open(image_path, "rb") as f:
            img_bytes = f.read()

        resp = self.client.models.generate_content(
            model=self.model,
            contents=[
                _build_review_prompt(item),
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = (getattr(resp, "text", "") or "").strip()
        data = json.loads(_FENCE.sub("", raw))
        blocking = [str(i) for i in (data.get("blocking") or [])]
        minor = [str(i) for i in (data.get("minor") or [])]
        return {
            "pass": not blocking,      # ★只看 blocking:沒有必擋違規就通過★
            "blocking": blocking,
            "minor": minor,
        }


def _build_review_prompt(item: dict) -> str:
    headline = item.get("headline", "")
    hl = item.get("highlight") or {}
    label = hl.get("label", "")

    return f"""你是「米米財經」財經短影音的**圖片審查員**。
以下是一張準備放進新聞卡的 AI 生成示意圖,以及它對應的新聞。請嚴格審查這張圖能不能上片。

新聞標題:{headline}
新聞重點:{label}

★★ 審查分兩級,請嚴格區分 ★★

🔴【必擋 blocking】—— 會傷害財經頻道「可信度」的重大問題(有任何一項就必須擋下):
B1. ★編造的財務數據★:圖上出現「看起來在陳述財經事實」的數字,
    例如「EPS +2.5元」「毛利率 53%」「跌 36%」「2024 Q2」「7/16」等。
    → 你我都知道 AI 不可能知道真實數字,這些一定是編造的假數據 → ★必擋★。
    (註:K線/長條圖上「純裝飾性的零星刻度」不算此項,歸到 minor)
B2. ★亂碼/錯字/不成句★:圖上有讀不通、拼錯、糊掉、不成句的文字。
B3. ★真實人物★:畫出真實的人(政治人物、央行總裁、CEO、真人臉孔)。
    ★注意:本頻道所有角色都是「Q版米米貓」(戴奶油色帽子的橘貓),貓咪角色完全正確、不算違規。★
B4. ★嚴重離題或扭曲★:圖跟這則新聞「完全無關」,或元素扭曲畸形到不能看。

☑【允許,不算違規】以下都 OK,不要因此判不通過:
   • 真實企業的商標 / logo(如 tsmc、NVIDIA、三星)—— ★編輯性使用,本頻道允許★
   • 台北101、城市天際線、地球、K線圖、金幣、箭頭等通用符號與地標

🟡【可容忍 minor】—— 只是小瑕疵,★不影響可信度、一律放行★,只要列出來記錄:
M1. ★任何「文字/標籤重複」★ —— 同一個詞出現 2 次、3 次、甚至更多次,
    或標籤數量偏多(5~6 個)。
    ★ 重要:重複「只是美觀問題」,★永遠歸類為 minor,絕對不可以放進 blocking★。
      不管你覺得它多影響閱讀,都不准因為「重複」而判 pass=false。★
    (只有當重複的文字本身是「亂碼/不成句」時,才依 B2 歸 blocking)
M2. 圖表座標軸上零星的裝飾性刻度數字(不是宣稱性的財經數據)。
M3. 構圖、美感、標籤貼不貼切、主題連結強不強 等★主觀意見★。

★★ 判定原則 ★★
- ★只要「blocking」是空的 → 一律 pass = true ★(minor 再多也照樣通過,不要吹毛求疵)
- 只有 blocking 有東西時才 pass = false

只回 JSON(不要有其他文字),格式:
{{
  "pass": true 或 false,
  "blocking": ["必擋問題1", "必擋問題2"],
  "minor": ["小瑕疵1"]
}}

- blocking 的敘述要「★具體、可執行★」(指出哪裡、是什麼),
  因為它會被直接拿去當「重新生圖的修正指示」。
  例:「圖片中央有編造的財務數據『EPS +2.5元、毛利率53%』,不可出現任何具體數字」"""


# ── 防呆包裝 ──────────────────────────────────────
_service: ReviewService | None = None


def _get_service() -> ReviewService:
    global _service
    if _service is None:
        _service = GeminiReviewService()
    return _service


def _fail(reason: str) -> dict:
    return {"pass": False, "blocking": [reason], "minor": []}


def safe_review(image_path: str, item: dict) -> dict:
    """審一張圖。任何失敗(API 錯/逾時/解析失敗)→ 🔴 保守視為「不通過」。

    回 {"pass": bool, "blocking": [...], "minor": [...]},不 raise。
    pass 只看 blocking(必擋);minor(美觀小瑕疵)不影響通過。
    """
    if not image_path or not os.path.exists(image_path):
        return _fail("圖片檔不存在")

    try:
        svc = _get_service()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(svc.review, image_path, item)
            result = fut.result(timeout=config.REVIEW_TIMEOUT)

        if result["pass"]:
            logger.info("審圖通過:%s%s", image_path,
                        f"(小瑕疵:{result['minor']})" if result["minor"] else "")
        else:
            logger.warning("審圖不通過(必擋):%s → %s", image_path, result["blocking"])
        return result

    except concurrent.futures.TimeoutError:
        logger.warning("審圖逾時(>%ds)→ 保守視為不通過", config.REVIEW_TIMEOUT)
        return _fail("審圖逾時,無法驗證")
    except Exception as e:  # noqa: BLE001 — 審查失效一律保守擋下,不發沒審過的圖
        logger.warning("審圖失敗(保守視為不通過):%s", e)
        return _fail(f"審圖失敗:{e}")


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    item = {
        "headline": "台積電法說會三個數據 外媒曝最值得關注",
        "highlight": {"value": "法說會", "trend": "flat", "label": "本週市場焦點"},
    }

    for path, expect in [
        ("output/images/news_1.png", "應該不通過(有編造數字+亂碼+標籤重複)"),
        ("output/images/news_0.png", "應該通過(乾淨的圖)"),
    ]:
        print(f"\n{'=' * 60}\n審查:{path}\n預期:{expect}\n{'=' * 60}")
        r = safe_review(path, item)
        print(f"pass = {r['pass']}")
        for i in r["blocking"]:
            print(f"  🔴 必擋:{i}")
        for i in r["minor"]:
            print(f"  🟡 小瑕疵(放行):{i}")
