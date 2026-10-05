r"""口播稿 審稿 critic(UPDATE 12,writer-critic reflection)。

U12-1:critic —— 拿「改寫後的稿」跟「原文」比,判斷能不能上片。
U12-2(目前):writer + review_and_fix —— critic→writer→critic 的 reflection 迴圈(★純 Python,不用框架★)。
  之後 U12-3 fail-open 包裝 + 接進 pipeline(改寫→TTS 之間)。

★ 這是 reflection pattern(writer-critic),純比對/重寫文字,不需工具/記憶 → 用純迴圈最乾淨。★
★ 守門哲學同 U5 審圖:兩級分流,門檻偏寬,只擋真的傷可信度/法律的。★
★ 審稿不中斷發片:重寫到上限仍不過 → 用原稿 + 大聲 log(fail-open 的「叫得夠大聲」)。★

單獨測:  .\venv\Scripts\python.exe script_review.py
"""

from __future__ import annotations

import json
import logging
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import config

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)

# ★ code 層防呆網:LLM 常把「喵/口語/專業度」硬塞進 blocking(即使 prompt 禁止)。
#   風格相關、又沒有「真違規訊號」的 blocking 項,一律踢出(改歸 minor)。
#   這是「不信任 LLM 自我分類,用程式強制規則」—— 比一直加 prompt 可靠。
_STYLE_PAT = re.compile(r"喵|口語|口吻|語氣|風格|專業度|正式|活潑|親切")
_HARD_PAT = re.compile(r"買|賣|進場|出場|加碼|減碼|套牢|抄底|保證|一定|必[漲崩賺]|\d")


def _build_critic_prompt(source: str, script: str) -> str:
    return f"""你是「米米財經」的**口播稿審稿員**。
下面有一則新聞的「原文」和一份準備配音的「口播稿」。請嚴格審查這份稿能不能上片 ——
重點是:★稿有沒有忠於原文★,以及有沒有踩到財經頻道的紅線。

【原文】
{source}

【口播稿】
{script}

★★ 審查分兩級,請嚴格區分 ★★

🔴【必擋 blocking】(傷可信度 / 法律,有任一項就擋):
B1. ★與原文事實不符 / 編造★:稿裡出現「原文沒有的**具體**數字、公司、事件、因果」。
    例:原文說「台積電上漲」,稿寫成「台積電漲到 2000 元」(原文沒這數字)→ 擋。
    ★但:潤飾用詞、程度副詞、口語修飾(如「熱鬧」「似乎」「呢」「走強」)只要沒改變核心事實,
      不算 B1 —— 不要為了用詞不同就擋。只擋「捏造出具體的新資訊」。★
    ★合理四捨五入 / 約略不算 B1★:原文 31.75、稿說「約 31.8」「31.8 左右」→ 放行。
      只擋「原文完全沒有、憑空生出來的數字/事件」。
      ★例外:別用四捨五入後的數字去講「突破/升破」那種關卡語氣★ ——
      原文 31.75 沒到 31.8,卻寫「升破 31.8」,是講了沒發生的事(關卡沒過)→ 這個要擋。
B2. ★投資建議★:★明確叫人買賣 / 進出場★(買、賣、進場、出場、加碼、減碼、快買、快賣、別套牢、抄底)。
    ★但中性描述不算★:「投資人觀望」「多留意市場動態」「值得關注」這種不是投資建議
      (尤其原文本來就這樣講時)。只擋「明確的買賣指令」。
    (本頻道是「回顧重點」,不給投資建議 → 這是紅線)
B3. ★嚴重誇大 / 斷言★:原文沒說的**強烈**斷言(如「一定會大漲」「保證賺」「必崩」)。
    ★一般形容詞、活潑口語(「走強」「熱鬧」)不算誇大 —— 只擋「強烈且原文沒有的斷言」。★
B4. ★完全離題★:稿講的跟這則原文無關。

☑【允許,完全不算違規 —— 這是本頻道的「正確」樣子,不要擋、也不用挑成 minor】:
   • 本頻道是「AI 貓主播米米」的親切口播 → ★「喵~」、口語、親切、活潑語氣都是刻意設計,正確的★。
   • 潤飾、換句話說、精簡、加語氣詞 —— 改寫本來就會這樣,只要沒改變事實,就 OK。
   ★ 絕對不要因為「太口語 / 有喵 / 不夠正式 / 不像正式報導」而判 blocking,那些不是問題。★

🟡【可容忍 minor】(只記錄,一律放行):
M1. 真的無傷大雅的小地方(極少用到)。多數情況 minor 應為空。

★★ 判定原則 ★★
- ★blocking 只放「事實不符/編造、投資建議、嚴重誇大斷言、離題」這四類★。
  ★風格 / 語氣 / 口語化 / 喵 / 專業度 → 永遠不是 blocking,也不是問題。★
- ★只要 blocking 是空的 → pass = true ★。門檻偏寬:忠於事實 + 沒踩紅線就過。
- blocking 的敘述要★具體可執行★(指出哪句、什麼問題),因為它會被當「重寫的修正指示」。

只回 JSON(不要其他文字):
{{
  "pass": true 或 false,
  "blocking": ["具體問題1", ...],
  "minor": ["小瑕疵1", ...]
}}"""


def critic(source: str, script: str) -> dict:
    """審一份稿。回 {"pass", "blocking", "minor"}。pass 只看 blocking。"""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.SCRIPT_REVIEW_MODEL,
        temperature=0,   # 審稿要穩定,別發散
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke(_build_critic_prompt(source, script))
    raw = (resp.content or "").strip()
    data = json.loads(_FENCE.sub("", raw))
    raw_blocking = [str(x) for x in (data.get("blocking") or [])]
    minor = [str(x) for x in (data.get("minor") or [])]

    # ★防呆網★:純風格(喵/口語/專業度)又無真違規訊號的項 → 踢出 blocking、改記 minor。
    blocking, demoted = [], []
    for b in raw_blocking:
        if _STYLE_PAT.search(b) and not _HARD_PAT.search(b):
            demoted.append(b)        # 這是風格意見,不該擋
        else:
            blocking.append(b)
    if demoted:
        logger.info("審稿:%d 個風格項被降級(不擋發片):%s", len(demoted), demoted)
        minor += demoted

    return {"pass": not blocking, "blocking": blocking, "minor": minor}


def _build_writer_prompt(source: str, script: str, issues: list[str]) -> str:
    bullets = "\n".join(f"  - {i}" for i in issues)
    return f"""你是「米米財經」的口播稿改寫員。下面有一則新聞的原文、一份有問題的口播稿,
以及審稿員指出的「必須修正的問題」。請重寫這份稿。

【原文】
{source}

【原本的稿(有問題)】
{script}

【必須修正的問題】
{bullets}

★ 重寫規則 ★
1. 修正上面每一個問題。
2. ★只根據原文★:不得加入原文沒有的數字、公司、事件;不得給投資建議(買/賣/進場點)。
3. ★保留米米貓的親切口吻★:可以口語、活潑、用「喵~」,這是本頻道的正確風格。
4. 長度跟原本的稿差不多,一段口播即可。

只回「重寫後的口播稿」本身(不要任何解釋、不要標題、不要 JSON)。"""


def writer(source: str, script: str, issues: list[str]) -> str:
    """拿 原文 + 有問題的稿 + 問題 → 重寫一份稿(保留米米口吻、忠於原文)。"""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=config.SCRIPT_REVIEW_MODEL, temperature=0.5)
    resp = llm.invoke(_build_writer_prompt(source, script, issues))
    return (resp.content or "").strip()


def review_and_fix(source: str, draft: str) -> str:
    """審稿 reflection 迴圈(純 Python):critic → 不過就 writer 重寫 → 再 critic。

    回「驗證過的稿」;重寫到上限仍不過 → ★用原稿 + 大聲 log★(審稿不中斷發片)。
    """
    verdict = critic(source, draft)
    if verdict["pass"]:
        return draft     # 第一版就過 → 0 次重寫(省成本)

    current = draft
    for attempt in range(1, config.SCRIPT_REVIEW_MAX_RETRY + 1):
        logger.warning("審稿不通過(第 %d 次重寫),必修:%s", attempt, verdict["blocking"])
        current = writer(source, current, verdict["blocking"])
        verdict = critic(source, current)
        if verdict["pass"]:
            logger.info("審稿第 %d 次重寫後通過", attempt)
            return current

    # 到上限仍不過 → 用「最後一版重寫」(已修掉原稿的嚴重問題,通常比原稿乾淨),
    # ★不要退回原稿★(原稿才是觸發審查的壞版本,退回等於把嚴重問題發出去)。叫得夠大聲。
    logger.warning("★審稿重寫 %d 次仍不過,用最後重寫版發片★ 殘留問題:%s",
                   config.SCRIPT_REVIEW_MAX_RETRY, verdict["blocking"])
    return current


def safe_review_and_fix(source: str, draft: str) -> str:
    """★pipeline 用的 fail-open 入口★:任何例外/逾時/空輸入 → 回原稿,絕不中斷發片。

    (review_and_fix 內部已處理「審不過 → 用原稿」;這層再包一層 try/except,
     擋 API 出錯、JSON 解析失敗等,確保審稿永遠不會讓發片掛掉。)
    """
    if not source or not draft:
        return draft
    try:
        return review_and_fix(source, draft)
    except Exception as exc:  # noqa: BLE001 — 審稿是附屬,出錯一律回原稿
        logger.warning("審稿流程出錯(fail-open 用原稿):%s", exc)
        return draft


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    source = ("台積電今日股價上漲 3%,收在 1050 元,帶動電子類股走強。"
              "法人指出,市場看好 AI 晶片需求持續。")

    cases = [
        ("忠於原文(應直接過,0 次重寫)",
         "喵~今天台積電上漲 3%、收在 1050 元,帶動電子股走強!法人說是看好 AI 晶片需求喵~"),
        ("編造數字 + 投資建議(應重寫成乾淨版)",
         "喵~台積電要衝上 2000 元啦!AI 需求爆發,現在不買就來不及,大家快進場!"),
    ]

    for label, draft in cases:
        print(f"\n{'='*60}\n{label}\n原稿:{draft}\n{'='*60}")
        fixed = review_and_fix(source, draft)
        changed = "✏️ 有重寫" if fixed != draft else "✅ 原稿直接過"
        print(f"{changed}\n最終稿:{fixed}")
