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

# ★ code 層防呆網:LLM 常把「喵/口語/專業度」或「詮釋/潤飾語氣」硬塞進 blocking(即使 prompt 禁止)。
#   風格/詮釋相關、又沒有「真違規訊號」(數字、買賣指令、保證/必漲)的 blocking 項,一律踢出(改歸 minor)。
#   這是「不信任 LLM 自我分類,用程式強制規則」—— 比一直加 prompt 可靠。
#   ★ 有 _HARD_PAT 訊號(數字/買賣/保證…)的一律保留 → 捏造數字、投資建議照樣擋。★
_STYLE_PAT = re.compile(r"喵|口語|口吻|語氣|風格|專業度|正式|活潑|親切|斷言|誇大|詮釋|評論|因果|情緒|潤飾|主觀")
_HARD_PAT = re.compile(r"買|賣|進場|出場|加碼|減碼|套牢|抄底|保證|一定|必[漲崩賺]|\d")
# ★「要求補內容」的抱怨一律不是違規(口播稿本來就只是摘要)→ 不管有沒有數字都降級。
#   只收「要求納入更多」的字眼(缺少/應體現/遺漏/漏講/省略…),不碰「原文沒有/與原文不符」
#   這種可能是『編造』的字眼,避免誤放真違規。
_OMIT_PAT = re.compile(r"缺少|應(該)?(有所)?體現|應(包含|納入|提及|提到)|未(能)?(涵蓋|包含|納入)|遺漏|漏(掉|講|報|提)|省略|不夠完整|不完整")
# ★「焦點 / 值得關注 / 點名」= 中性點名,不是投資建議 → 降級。
#   但若同時有「明確買賣/進出動作詞」(_ACTION_PAT),代表可能是真的投資建議 → 保留不降。
_FOCUS_PAT = re.compile(r"焦點|關注|矚目|注目|留意|值得注意|值得關注|點名")
_ACTION_PAT = re.compile(r"買進|賣出|進場|出場|加碼|減碼|快買|快賣|抄底|套牢|停損|停利|布局|該買|該賣")
# ★ 除權息時程用語是中性資訊,但「最後買進日」含「買進」會誤中 _ACTION_PAT → 比對前先排除。★
_NEUTRAL_TERMS = re.compile(r"最後買進日|最後交易日|除息日|除權日|除權息|買進評等")


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
B1. ★與原文事實不符 / 編造★:稿裡出現「原文沒有的**具體**數字、公司、事件」。
    例:原文說「台積電上漲」,稿寫成「台積電漲到 2000 元」(原文沒這數字)→ 擋。
    ★順著原文方向的輕度詮釋/總結(如「這顯示需求強勁」「帶來不少機會」)不是「編造事實」,不算 B1。★
    ★★「只少講」絕不算 B1 ★★:口播稿是 15~30 秒的精簡摘要,★只挑部分重點、
      省略原文其他數字/公司/細節,完全正確,不是問題★。B1 只擋「稿裡**多出**原文沒有的假資訊」,
      ★絕對不要因為「稿沒把原文的數字/公司講完、不夠完整」而判 blocking★(那是摘要,不是錯誤)。
    ★但:潤飾用詞、程度副詞、口語修飾(如「熱鬧」「似乎」「呢」「走強」)只要沒改變核心事實,
      不算 B1 —— 不要為了用詞不同就擋。只擋「捏造出具體的新資訊」。★
    ★合理四捨五入 / 約略不算 B1★:原文 31.75、稿說「約 31.8」「31.8 左右」→ 放行。
      只擋「原文完全沒有、憑空生出來的數字/事件」。
      ★例外:別用四捨五入後的數字去講「突破/升破」那種關卡語氣★ ——
      原文 31.75 沒到 31.8,卻寫「升破 31.8」,是講了沒發生的事(關卡沒過)→ 這個要擋。
B2. ★投資建議★:★只擋「明確叫人買賣 / 進出場」的指令★(買進、賣出、進場、出場、加碼、減碼、
    快買、快賣、別套牢、抄底、停損、停利、現在該買/該賣)。
    ★★以下都是中性描述,★絕對不算★投資建議,不要擋 ★★:
      - 「成為(市場/大家)關注的焦點」「市場焦點」「受矚目」「點名這幾檔」「值得注意 / 值得關注」
        「多留意市場動態」「投資人觀望」—— 這些只是「指出哪些標的受關注」,★不是叫人買★。
      例:稿說「台積電、科林研發、馬拉松石油成為大家關注的焦點」→ ★這是中性點名,pass,不要當投資建議★。
      - ★除權息時程(最後買進日、除息日、除權日)屬中性資訊★:稿說「10月16日是最後買進日,可以留意」→ 不算投資建議。
    ★判準:有沒有「明確的買賣/進出動作指令」?沒有 → 就不是投資建議。★
    (本頻道是「回顧重點」,不給投資建議 → 這是紅線,但紅線只畫在「明確買賣指令」)
B3. ★嚴重誇大 / 斷言★:只擋「**與原文方向相反**,或原文中性/看好卻說成『保證賺、一定大漲、必崩』」這種強烈斷言。
    ★換句話說、程度上的潤飾(原文「看好」→稿「信心滿滿」)、順著原文方向的輕度評論
      (「值得關注」「帶來不少機會」「顯示需求強勁」),以及一般形容詞、活潑口語(「走強」「熱鬧」)
      —— 全都不算誇大、不算斷言,★不要擋★。只擋「強烈且與原文抵觸/原文完全沒有的斷言」。★
B4. ★完全離題★:稿講的跟這則原文無關。

☑【允許,完全不算違規 —— 這是本頻道的「正確」樣子,不要擋、也不用挑成 minor】:
   • 本頻道是「AI 貓主播米米」的親切口播 → ★「喵~」、口語、親切、活潑語氣都是刻意設計,正確的★。
   • 潤飾、換句話說、精簡、加語氣詞 —— 改寫本來就會這樣,只要沒改變事實,就 OK。
   • ★詮釋 / 輕度評論語氣★:把原文立場換句話說(原文「看好」→「信心滿滿」),或順著原文方向
     的輕度總結(「這顯示需求強勁」「帶來不少機會」「值得關注」)—— 只要方向跟原文一致、
     沒有捏造具體新事實(數字/公司/事件),★都正確,不要擋、也不用挑成 minor★。
   ★ 絕對不要因為「太口語 / 有喵 / 不夠正式 / 不像正式報導 / 太有詮釋」而判 blocking,那些不是問題。★

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


# ── 🆕 二審:逐條覆核一審的擋下理由(審查員也要被審查)──────────────
# 起因:同一份輸入連審 5 次,4 次通過、1 次誤判 → 單次 LLM 判決在邊界案例不穩定。
# ★ 二審要推翻一審,必須附原文逐字引文,且程式確認引文真的在原文裡才放行(不靠模型說了算)。★
_MIN_EVIDENCE_CHARS = 6   # 引文正規化後至少這麼長才採信(避免「台積電」這種太短的巧合命中)


def _build_verify_prompt(source: str, script: str, claim: str) -> str:
    return f"""你是「米米財經」審稿的**二審覆核員**。一審審稿員對下面這份口播稿提出了一條指控,
請你★只針對這條指控★,對照原文判斷它是否成立。

【原文】
{source}

【口播稿】
{script}

【一審指控】
{claim}

★ 判斷方式 ★
- 指控說「某數字 / 日期 / 公司 / 事件 原文沒有、屬編造」→ 請在原文中★逐字搜尋★。
  原文確實有寫(或只是合理四捨五入、同義改寫)→ 指控不成立。
- 指控說「投資建議」→ 只有「明確叫人買賣 / 進出場」才成立;中性描述、「值得留意」、
  除權息時程(最後買進日、除息日)→ 不成立。
- 指控說「誇大斷言 / 離題」→ 對照原文,確實與原文抵觸或無關才成立。

★★ 若判定「不成立」,evidence 必須填原文中支持口播稿的那一句,★逐字複製,不可改寫或摘要★。
   在原文找不到可以支持的句子,就不能判不成立。★★

只回 JSON(不要其他文字):
{{"valid": true 或 false, "evidence": "原文逐字引文(判不成立時必填)", "reason": "一句話說明"}}
valid = true 代表一審指控成立(維持擋下);false 代表不成立(推翻)。"""


def _norm(text: str) -> str:
    """比對引文用:NFKC(全形→半形)後只留文字與數字,避免括號/標點差異造成誤判。"""
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKC", text or "") if ch.isalnum())


def verify_claim(source: str, script: str, claim: str) -> dict:
    """二審單一指控。回 {"valid", "evidence", "reason"}。"""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.SCRIPT_REVIEW_MODEL,
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke(_build_verify_prompt(source, script, claim))
    data = json.loads(_FENCE.sub("", (resp.content or "").strip()))
    return {"valid": bool(data.get("valid", True)),
            "evidence": str(data.get("evidence") or ""),
            "reason": str(data.get("reason") or "")}


def _second_review(source: str, script: str, blocking: list[str]) -> tuple[list[str], list[dict]]:
    """逐條覆核。回 (維持擋下的, 被推翻的[{claim, evidence, reason}])。

    推翻條件(三者都要):二審判不成立 + 有附引文 + 引文正規化後確實出現在原文。
    其餘一律維持擋下(含二審本身出錯)→ 寧可多擋,不誤放編造/投資建議。
    """
    confirmed, overturned = [], []
    norm_source = _norm(source)
    for claim in blocking:
        try:
            v = verify_claim(source, script, claim)
        except Exception as exc:  # noqa: BLE001 — 二審失敗 → 保守維持一審
            logger.warning("二審失敗,維持一審擋下:%s", exc)
            confirmed.append(claim)
            continue
        ev = _norm(v["evidence"])
        if (not v["valid"]) and len(ev) >= _MIN_EVIDENCE_CHARS and ev in norm_source:
            overturned.append({"claim": claim, "evidence": v["evidence"], "reason": v["reason"]})
            logger.info("二審推翻一審:%s|原文引文:%s", claim, v["evidence"])
        else:
            if not v["valid"]:
                logger.info("二審判不成立但引文對不上原文 → 維持擋下:%s", claim)
            confirmed.append(claim)
    return confirmed, overturned


def critic(source: str, script: str) -> dict:
    """審一份稿。回 {"pass", "blocking", "minor", "overturned"}。pass 只看 blocking。

    流程:一審(LLM)→ 程式防呆網降級 → 二審逐條覆核(SCRIPT_REVIEW_VERIFY 開時)。
    """
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
        is_style = _STYLE_PAT.search(b) and not _HARD_PAT.search(b)   # 純風格意見
        is_omit = _OMIT_PAT.search(b)                                  # 「嫌稿講得不夠完整」
        is_focus = (_FOCUS_PAT.search(b)                                # 中性點名/值得關注(非買賣指令)
                    and not _ACTION_PAT.search(_NEUTRAL_TERMS.sub("", b)))  # 先排除「最後買進日」等用語
        if is_style or is_omit or is_focus:
            demoted.append(b)        # 風格 / 要求補內容 / 中性點名 → 都不該擋發片
        else:
            blocking.append(b)
    if demoted:
        logger.info("審稿:%d 個非實質違規項被降級(不擋發片):%s", len(demoted), demoted)
        minor += demoted

    # 🆕 二審:一審有擋下才觸發,逐條覆核;被推翻的(附原文引文)降為 minor
    overturned: list[dict] = []
    if blocking and getattr(config, "SCRIPT_REVIEW_VERIFY", True):
        blocking, overturned = _second_review(source, script, blocking)
        minor += [f"(二審推翻){o['claim']}" for o in overturned]

    return {"pass": not blocking, "blocking": blocking, "minor": minor, "overturned": overturned}


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


def _pass_result(draft: str, overturned: list[dict] | None = None) -> dict:
    return {"script": draft, "changed": False, "status": "pass",
            "blocking": [], "before": draft, "after": draft, "overturned": overturned or []}


def review_and_fix_verbose(source: str, draft: str) -> dict:
    """🆕 UPDATE 15:同 review_and_fix,但回傳細節給控制台 UI。

    回 {script, changed, status(pass/rewrite/fallback), blocking(當初擋下的理由), before, after,
        overturned(被二審推翻的一審指控 + 原文引文)}。
    """
    verdict = critic(source, draft)
    first_overturned = verdict.get("overturned", [])   # 一審被二審推翻的(給 UI 顯示)
    if verdict["pass"]:
        return _pass_result(draft, first_overturned)

    first_blocking = verdict["blocking"]        # 當初擋下的理由(給 UI 顯示)
    current = draft
    for attempt in range(1, config.SCRIPT_REVIEW_MAX_RETRY + 1):
        logger.warning("審稿不通過(第 %d 次重寫),必修:%s", attempt, verdict["blocking"])
        current = writer(source, current, verdict["blocking"])
        verdict = critic(source, current)
        if verdict["pass"]:
            logger.info("審稿第 %d 次重寫後通過", attempt)
            return {"script": current, "changed": True, "status": "rewrite",
                    "blocking": first_blocking, "before": draft, "after": current,
                    "overturned": first_overturned}

    logger.warning("★審稿重寫 %d 次仍不過,用最後重寫版發片★ 殘留問題:%s",
                   config.SCRIPT_REVIEW_MAX_RETRY, verdict["blocking"])
    return {"script": current, "changed": True, "status": "fallback",
            "blocking": first_blocking, "before": draft, "after": current,
            "overturned": first_overturned}


def safe_review_and_fix_verbose(source: str, draft: str) -> dict:
    """★pipeline 用的 fail-open 入口(細節版)★:任何例外/空輸入 → 當作 pass 回原稿。"""
    if not source or not draft:
        return _pass_result(draft)
    try:
        return review_and_fix_verbose(source, draft)
    except Exception as exc:  # noqa: BLE001 — 審稿是附屬,出錯一律回原稿
        logger.warning("審稿流程出錯(fail-open 用原稿):%s", exc)
        return _pass_result(draft)


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
