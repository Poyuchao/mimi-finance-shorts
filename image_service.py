"""④d AI 生成新聞示意圖(UPDATE 4)。

抽象介面(跟 llm_service 同哲學,provider 可替換)+ Gemini 實作。
★ 核心:safe_generate() 防呆 —— 生圖失敗/超時/例外一律回 None,絕不中斷 pipeline。
  回 None = 該則新聞用純字卡版面(fallback)。
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
from abc import ABC, abstractmethod

import config

logger = logging.getLogger(__name__)


class ImageService(ABC):
    """provider-agnostic 生圖介面。成功回檔案路徑,失敗回 None(不 raise)。"""

    @abstractmethod
    def generate(self, prompt: str, out_path: str) -> str | None:
        raise NotImplementedError


class GeminiImageService(ImageService):
    """Gemini 圖像生成(SDK: google-genai)。"""

    def __init__(self, model: str | None = None):
        from google import genai

        if not config.GEMINI_API_KEY:
            raise RuntimeError("找不到 GEMINI_API_KEY(檢查 .env)")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = model or config.IMAGE_MODEL

        # 米米參考圖(生圖需要人物時,用這隻貓的 Q 版形象)
        self._ref_bytes = None
        ref = getattr(config, "MIMI_REF_IMAGE", None)
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                self._ref_bytes = f.read()
            logger.info("已載入米米參考圖:%s", ref)

    def generate(self, prompt: str, out_path: str) -> str | None:
        """呼叫 Gemini 生一張圖,存成 out_path。抓不到圖回 None。"""
        from google.genai import types

        contents: list = [prompt]
        if self._ref_bytes:
            contents.append(types.Part.from_bytes(data=self._ref_bytes, mime_type="image/jpeg"))

        # ★ 強制橫式比例:Gemini 不保證遵守 prompt 的「橫幅」描述,
        #   曾回過直式 768×1376 導致新聞卡爆版 → 用 image_config 明確指定。
        gen_config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=config.IMAGE_ASPECT),
        )
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=gen_config,
        )

        # 從回應的 parts 找 inline image bytes
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(inline.data)
                    return out_path
        logger.warning("Gemini 回應沒有圖片資料")
        return None


# ── prompt 組裝 ───────────────────────────────────
def _build_image_prompt(item: dict, fix_issues: list[str] | None = None) -> str:
    """組生圖 prompt。fix_issues = 上一輪審圖找到的問題(當修正指示附在末尾)。"""
    headline = item.get("headline", "")
    hl = item.get("highlight") or {}
    label = hl.get("label", "")
    script = (item.get("script") or "")[:150]

    fix_block = ""
    if fix_issues:
        bullets = "\n".join(f"  - {i}" for i in fix_issues)
        fix_block = f"""

★★ 上一張圖被審查退件,問題如下,這次請務必避免 ★★
{bullets}"""

    return f"""請根據以下財經新聞,產出一張「對應新聞內容」的財經新聞示意圖,
適合放在台灣股市短影音的新聞卡上半。

新聞標題:{headline}
重點:{label}
內文摘要:{script}

風格與要求:
- 台灣財經新聞的示意插畫風格,畫面豐富、一眼看懂這則新聞在講什麼。
- 視覺化新聞的核心:資金流向(箭頭、錢潮)、K線走勢、台股/匯率、台灣語境(台北101、台股)。

★★ 文字規則(非常重要,務必遵守)★★
- ★ 絕對不要在圖上放「任何標題、抬頭、橫幅文字」★ —— 不論是新聞標題、圖片標題、
  或任何一整句話。標題會由影片字卡另外顯示,圖裡完全不需要標題。
- ★ 也絕對不要把「這段指示裡出現的文字」(例如「台灣股市短影音」「Q版」「新聞卡」等)
  畫進圖片裡 ★ —— 那些是給你的指示,不是要畫的內容。
- ★ 絕對不要在圖上寫任何「具體數字或財務數據」★:
  不准出現 EPS、毛利率、營收、股價、百分比(如 -36%、1%)、指數點數、年份或日期(如 2024 Q2、7/16)。
  ★ 理由:你並不知道這則新聞的真實數字,寫出來一定是「編造的假數據」,
    這是財經頻道的重大錯誤。所有真實數字一律由影片字卡顯示,不需要你畫。★
- ★ K線圖、長條圖、折線圖等圖表:只畫「純圖形」,★座標軸上不要標任何刻度數字、
  不要標百分比、不要標任何數值★。圖表只是視覺示意,不需要任何數字。★
- ★ 絕對不要加「圖說 / caption / 說明文字」★(圖片下方或角落的描述句),那些一定會變亂碼。
- 允許的文字:只有「最多 3~4 個簡短的情境標籤」(例如:資金匯出、資金湧入、台股走勢、外資動向)。
  ★ 每一個標籤文字「只能出現一次」,絕對不可以在畫面不同位置重複畫同一個標籤 ★;
  ★ 標籤總數不可超過 4 個 ★;必須是正確的繁體中文、不要簡體、不要錯字、不要亂碼。
- 整體以「圖像」為主、文字只是點綴。畫面寧可「少字」也不要「多字出錯」。
- ★ 頻道吉祥物:附上的參考圖是本頻道「米米財經」的貓咪主播「米米」(戴奶油色帽子的橘貓)。
  畫面中「凡是需要人物」的地方(官員、央行總裁、分析師、講師、投資人、主播等),
  一律改用「這隻貓的 Q 版可愛卡通形象」(圓潤大頭、大眼、保留奶油色帽子與橘貓特徵)來呈現,
  ★ 絕對不要畫真人;所有角色都是這隻米米貓的擬人化 Q 版。
- 若新聞主角是某家公司,可以出現相關的產業符號(晶圓、晶片、伺服器、廠房等);
  畫到該公司的 logo/商標也沒關係(編輯性使用)。
- 橫幅構圖,專業、現代,深色底配金色與紅綠漲跌色。"""


# ── 防呆包裝(🔴 這次最重要)────────────────────────
_service: ImageService | None = None


def _get_service() -> ImageService:
    global _service
    if _service is None:
        if config.IMAGE_PROVIDER == "gemini":
            _service = GeminiImageService()
        else:
            raise ValueError(f"未知 IMAGE_PROVIDER:{config.IMAGE_PROVIDER}")
    return _service


def _generate_once(item: dict, idx: int, out_path: str, fix_issues: list[str]) -> str | None:
    """生一張圖(含 timeout)。失敗/逾時/無效檔 → 回 None(不 raise)。"""
    prompt = _build_image_prompt(item, fix_issues=fix_issues)
    try:
        svc = _get_service()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(svc.generate, prompt, out_path)
            path = fut.result(timeout=config.IMAGE_TIMEOUT)
        if path and os.path.exists(path) and os.path.getsize(path) > 5000:
            return path
        logger.warning("第 %d 則生圖無效(空/過小)", idx)
    except concurrent.futures.TimeoutError:
        logger.warning("第 %d 則生圖逾時(>%ds)", idx, config.IMAGE_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — 生圖是加分項,失敗絕不中斷
        logger.warning("第 %d 則生圖失敗:%s", idx, e)
    return None


def safe_generate(item: dict, idx: int) -> str | None:
    """為第 idx 則新聞生一張圖,並(UPDATE 5)送 AI 審圖。

    流程:生圖 → 審圖 → 不通過就「帶著問題」重生 → 再審 …
    兩輪都不過 → 回 None = 該則退純字卡。

    ★任何失敗都回 None,絕不 raise、不中斷 pipeline(影片照常產出上傳)。★
    """
    out_path = os.path.join(config.IMAGE_DIR, f"news_{idx}.png")
    rounds = 1 + (config.REVIEW_MAX_RETRY if config.USE_IMAGE_REVIEW else config.IMAGE_RETRY)
    issues: list[str] = []

    for attempt in range(1, rounds + 1):
        path = _generate_once(item, idx, out_path, issues)
        if not path:
            continue   # 生圖本身失敗 → 下一輪(或用完就 fallback)

        logger.info("第 %d 則生圖成功(第 %d 輪):%s", idx, attempt, path)

        if not config.USE_IMAGE_REVIEW:
            return path   # 沒開審圖 → 直接用

        # 🆕 UPDATE 5:審圖(分級:只有 blocking 才擋;minor 小瑕疵放行)
        import review_service
        result = review_service.safe_review(path, item)
        if result["pass"]:
            if result["minor"]:
                logger.info("第 %d 則審圖通過(有小瑕疵,放行):%s", idx, result["minor"])
            else:
                logger.info("第 %d 則審圖通過 → 採用", idx)
            return path

        # ★重生時只餵 blocking(不拿美觀小事去干擾模型)★
        issues = result["blocking"]
        logger.warning("第 %d 則審圖不通過(第 %d 輪),必擋問題:%s", idx, attempt, issues)

    logger.warning("第 %d 則:生圖/審圖最終未通過 → fallback 純字卡", idx)
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # U5-1:用「曾生出編造數字+亂碼」的那則新聞測,驗證 prompt 修正是否有效
    fake = {
        "headline": "台積電法說會三個數據 外媒曝最值得關注",
        "highlight": {"value": "法說會", "trend": "flat", "label": "本週市場焦點"},
        "script": "本週台積電將公布第二季業績,外媒點名三個最值得關注的數據,不只反映台積電本身,也反映科技大廠客戶的表現。",
    }
    path = safe_generate(fake, 0)
    print("結果:", path or "(失敗,None → 該則會用純字卡)")
