"""④ LLM 服務(🔴 可替換介面,分兩步:先選再改寫)。

架構:抽象介面 LLMService(provider-agnostic)。
  • generate(prompt) 是唯一要各家實作的底層方法。
  • select_top_news / rewrite_scripts 兩步都只組 prompt,走同一個 generate()。
  → 之後換 Gemini/Claude 只加一個 class,不改其他 code。

本階段先做第一步 select_top_news(從候選挑 N 則 + 理由)。
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod

from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)

load_dotenv()

# 去掉 LLM 可能包的 ```json ... ``` 圍欄
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


class LLMResponseError(Exception):
    """LLM 回傳無法解析(retry 後仍失敗)。核心步驟,不 skip。"""


def _norm_highlight(hl) -> dict:
    """把 LLM 的 highlight 正規化成 {value, trend, label}。
    容錯:LLM 萬一回字串 → 當 value、trend=flat。trend 只允許 up/down/flat。"""
    if isinstance(hl, str):
        hl = {"value": hl, "trend": "flat", "label": ""}
    hl = hl or {}
    trend = str(hl.get("trend", "flat")).strip().lower()
    if trend not in ("up", "down", "flat"):
        trend = "flat"
    return {
        "value": str(hl.get("value", "")).strip(),
        "trend": trend,
        "label": str(hl.get("label", "")).strip(),
    }


class LLMService(ABC):
    """provider-agnostic 介面。各家只要實作 generate()。"""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """送 prompt,回純文字。"""
        raise NotImplementedError

    def _generate_json(self, prompt: str) -> dict:
        """呼叫 generate 並解析 JSON;失敗 retry 一次,再失敗 raise。"""
        last_err: Exception | None = None
        for attempt in (1, 2):
            raw = self.generate(prompt)
            cleaned = _FENCE.sub("", raw.strip())
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning("LLM 回傳非 JSON(第 %d 次),準備 retry。片段:%.120s",
                               attempt, cleaned)
        raise LLMResponseError(f"LLM 回傳解析失敗(retry 後):{last_err}")

    # ── 第一步:選片 ──────────────────────────────
    def select_top_news(
        self,
        candidates: list[dict],
        n: int | None = None,
        recent: list[dict] | None = None,
    ) -> list[dict]:
        """從候選挑 n 則,回傳選中的候選(附 reason),保序為 LLM 給的順序。

        recent:🆕 UPDATE 8 —— 最近已發過的新聞(供 agent 參考,避免重複報導同一事件)。
        """
        n = n if n is not None else config.NEWS_COUNT
        if not candidates:
            logger.warning("候選為空,無可挑選")
            return []
        if len(candidates) <= n:
            logger.info("候選僅 %d 則(<= 需要的 %d),全數保留,不呼叫 LLM 選片",
                        len(candidates), n)
            return [{**c, "reason": "候選不足,直接保留"} for c in candidates]

        prompt = _build_select_prompt(candidates, n, recent=recent)
        data = self._generate_json(prompt)

        selected = data.get("selected", [])
        picked: list[dict] = []
        seen: set[int] = set()
        for item in selected:
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
                logger.warning("LLM 給了無效 index:%r,略過", idx)
                continue
            if idx in seen:
                continue
            seen.add(idx)
            picked.append({**candidates[idx], "reason": item.get("reason", "")})
            if len(picked) >= n:
                break

        if not picked:
            raise LLMResponseError("LLM 選片沒回任何有效 index")
        if len(picked) < n:
            logger.warning("LLM 只選出 %d 則(需要 %d),有幾則做幾則", len(picked), n)
        return picked

    # ── 第二步:改寫 ──────────────────────────────
    def rewrite_scripts(self, selected: list[dict]) -> dict:
        """把選中的新聞改寫成口播稿。回傳:
        {video_title, hashtags, items:[{headline, highlight, script,
                                        source, image_url, link, original_title}]}
        items 順序對齊 selected;每則附回原始 meta(來源/圖/連結)供字卡用。"""
        if not selected:
            raise LLMResponseError("沒有選中的新聞可改寫")

        prompt = _build_rewrite_prompt(selected)
        data = self._generate_json(prompt)

        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            raise LLMResponseError("LLM 改寫沒回 items")
        if len(items) != len(selected):
            logger.warning("改寫 items 數(%d)與選中(%d)不符,以較少者對齊",
                           len(items), len(selected))

        merged: list[dict] = []
        for src, item in zip(selected, items):
            merged.append(
                {
                    "headline": item.get("headline", "").strip(),
                    "highlight": _norm_highlight(item.get("highlight")),  # 🆕 UPDATE 2:結構化
                    "script": item.get("script", "").strip(),
                    # 附回原始 meta(字卡/來源標註用)
                    "source": src.get("source", ""),
                    "image_url": src.get("image_url"),
                    "link": src.get("link", ""),
                    "original_title": src.get("title", ""),
                }
            )

        return {
            "video_title": data.get("video_title", "").strip(),
            "hashtags": data.get("hashtags", []),
            "items": merged,
        }


class OpenAIService(LLMService):
    """OpenAI gpt-4o-mini 實作。"""

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("找不到 OPENAI_API_KEY(檢查 .env)")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


# ── prompt 組裝 ───────────────────────────────────
def _build_select_prompt(candidates: list[dict], n: int,
                         recent: list[dict] | None = None) -> str:
    lines = []
    for i, c in enumerate(candidates):
        text = (c.get("clean_text") or "")[:200]
        lines.append(f"[{i}] 來源:{c['source']}\n    標題:{c['title']}\n    內文:{text}")
    listing = "\n".join(lines)

    # 🆕 UPDATE 8:把「最近已發過的新聞」帶進來給 agent 參考
    recent_block = ""
    if recent:
        recent_lines = "\n".join(f"  ({r.get('run_date','')}) {r.get('title','')}"
                                 for r in recent[:20])
        recent_block = f"""

★ 這幾天已經發過的新聞(僅供參考)★
{recent_lines}
→ 若候選中有「和上面同一事件的重複報導」,請降權、盡量不要再選;
  但如果該事件今天有「重大新進展」,仍然可以選。"""

    return f"""你是台灣財經股市短影音的選題編輯。以下是今天篩出的 {len(candidates)} 則候選新聞。
請挑出「最重要、最有影響力」的 {n} 則來做股市短影音。

★★ 硬門檻(先過這關才談重要性)★★
每則必須「直接跟股市有關」—— 主題是以下之一:
  • 大盤/指數/個股的股價、漲跌、成交量
  • 資金流(外資/投信/融資、買超賣超)
  • 財報、營收、EPS、股利、除權息
  • 對「投資人/持股」有直接、明確的影響(升降息、政策、關稅對股價的衝擊)
⚠️ 只是「提到某公司名」不算股市新聞。純產業/人才/勞動/科技/政策/公益等議題,
   若對股價沒有直接明確的影響 → 一律不選。
   例:「台積電人才缺口/畢業生不願穿無塵衣」雖提到台積電,但主題是勞動議題、非股市 → 不選。

挑選原則(過了硬門檻後,重要性由高到低):
1. ★最高優先:權值股龍頭的重大事件★
   • 台積電、輝達等權值王的「法說會、財報、重大投資/擴廠、地緣政治衝擊」
   • ★ 就算事件「還沒發生」(例如本週即將舉行的法說會)、目前還沒有數字,
     它仍然是全市場最關注的焦點 → 一樣要優先選。★
2. 市場級/結構性的「盤勢」題材 —— 影響整個大盤/整個產業:
   • 全產業趨勢對股價的衝擊(如 AI 算力、AI 泡沫、半導體循環 → 帶動/拖累一整片股票)
   • 重大總經與央行「政策轉向」(升降息、重大政策宣示)對市場的衝擊
   • 影響「整體大盤」的資金流(如國安基金進退場、外資對大盤大幅買超/賣超)
3. ★降權(盡量不要選)★:
   • ★匯率題材「整體降權」★ —— 新台幣升貶、匯市波動、央行進場調節,
     這類「匯率」新聞與股市的連動性不是本頻道主軸 → 一律排後,
     除非是「重大匯率危機或央行重大政策轉向」等級。
     例:「新台幣午後急貶,央行尾盤調節終場翻升0.8分」→ 不選。
   • ★「外資買超/賣超某『一檔個股』」不算大盤級資金流 → 降權,不要選★
     (只有「外資對『整體大盤』的大幅買賣超」才算市場級題材)
     例:「外資最愛這檔,長榮航空名列外資買超第一」→ 這是單一個股的外資買超 → 不選。
   • 單一中小型個股的短線漲跌、例行月營收公告(如某公司6月營收年增X%)
4. ★題材必須「分散」★:
   • 同一事件的重複報導,只留最有代表性的一篇。
   • ★同一家公司/同一個主體,最多只能選「一則」★ ——
     不可以三則裡有兩則都在講同一家公司(即使那兩則角度不同)。
     例:「力積電董座掛保證明年配息」+「力積電Q2毛利率28%」→ 都是力積電 → ★最多只能選其中一則★。
   • 三則應該是「三個不同的題材/主體」(例如:大盤盤勢、權值王事件、產業趨勢)。
5. ★ 重要性 > 數字豐富度 ★:
   「有明確數字/漲跌」只是「同等重要時」的加分,★絕不能凌駕重要性★。
   不要因為某則有漂亮數字、而某則(重大但尚未發生)還沒數字,就把重大的那則擠掉。

候選新聞:
{listing}{recent_block}

★★★ 送出答案前,務必做這道「最終檢查」★★★
在你決定好 {n} 則之後、回覆之前,請逐條自我檢查;任何一條不通過,就回頭換掉那一則:

  檢查①【主體不可重複】★最常犯的錯,請特別注意★
        我選的這 {n} 則,是不是「{n} 個不同的公司/主體/事件」?
        有沒有其中兩則在講「同一家公司」(即使角度不同)?
        → 若有 → ★必須換掉其中一則★,改選候選池裡「別的主體」的新聞。
  檢查②【都跟股市直接相關】每一則都過了上面的硬門檻嗎?
  檢查③【重要性排序】有沒有把「更重要的」漏掉、卻選了「有數字但不重要的」?

只回 JSON(不要有其他文字),格式:
{{
  "selected": [
    {{"index": <候選編號整數>, "reason": "為什麼選這則(20字內,講對股市的重要性/影響)"}}
  ]
}}
挑滿 {n} 則(若真的不足 {n} 則符合股市硬門檻,寧可少選也不要硬湊不相關的),
index 依你認為的重要性由高到低排列。"""


def _build_rewrite_prompt(selected: list[dict]) -> str:
    lines = []
    for i, c in enumerate(selected, 1):
        text = (c.get("clean_text") or "")[:400]
        lines.append(f"第 {i} 則(來源:{c['source']})\n    原標題:{c['title']}\n    內文:{text}")
    listing = "\n".join(lines)
    n = len(selected)

    return f"""你是「米米財經」短影音的腳本編劇。頻道有一位 AI 虛擬貓主播「米米」。
以下有 {n} 則今天最重要的股市新聞。請把每一則改寫成適合短影音的內容。

內容要求(務必遵守):
- 【改寫,不照抄】用你自己的話重講事實,不要照抄原文句子(降低版權風險)。
- 【親切但專業】script 是「念出來給人聽」的口播稿:口語、有溫度、像在跟朋友講盤勢,
  但資訊要準確、保持專業(親切 ≠ 幼稚,別為了可愛亂講)。不要書面語。
- ★【數字鐵則】★ 所有數字(股價、點數、%、金額、日期)一律**依原文**,
  **不得新增原文沒有的數字、漲跌或事件**(原文沒提的,絕不能寫進稿)。
  可以為了口語做合理四捨五入/約略(如原文 31.75 → 「約 31.8」「31.8 左右」),
  但★別用四捨五入後的數字去講「突破/升破」那種關卡語氣★
  (原文 31.75 沒到 31.8,就不能寫「升破 31.8」——那是講了沒發生的事)。
- ★【不給投資建議】★ 本頻道只回顧重點,★禁止★叫人買賣/進出場,
  也★禁止★「好消息/不容錯過/值得進場/快買快賣」這類誇大或暗示性語氣;
  中性描述可以(「值得關注」「留意市場動態」)。
- 【股市角度】切入點放在漲跌、影響、數字、對投資人的意義。
- 【長度】每則 script 約 20~30 秒的量(大約 90~140 字)。
- headline 是字卡上的大字標題,精簡有力,不超過 15 字。
- 全部用繁體中文、台灣用語。

★ highlight(數字視覺化用)= 結構化物件 {{value, trend, label}}:
- value:這則最關鍵的「數字或短詞」,做成字卡大字(如「+30%」「890億」「跌274點」「擴大1倍」)。盡量含數字,真的沒有就放最關鍵短詞。
- trend:這個重點對股市是偏多還偏空 →
    "up"  = 利多/上漲(如大漲、買超、擴廠、財報佳)
    "down"= 利空/下跌(如大跌、賣超、跌破、財報差)
    "flat"= 中性或純質化(講不出明確方向)
    ★ 由你(LLM)依新聞內容判斷方向。
- label:一句話重點(如「外資買超」「AI算力過剩」「台積電擴廠」),約 10 字內。

新聞素材:
{listing}

只回 JSON(不要有其他文字),格式:
{{
  "video_title": "整支影片的標題(吸睛,15字內)",
  "hashtags": ["#台股", "#台積電", "..."],
  "items": [
    {{"headline": "字卡大字短標題",
      "highlight": {{"value": "+30%", "trend": "up", "label": "外資買超"}},
      "script": "口播稿(親切但專業)"}}
  ]
}}
items 的順序要對齊上面第 1~{n} 則。hashtags 給 5~8 個。"""


if __name__ == "__main__":
    import fetch_rss
    import parse_filter
    import select_news

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cands = select_news.select_news(parse_filter.parse_filter(fetch_rss.fetch_rss()))
    svc = OpenAIService()
    picked = svc.select_top_news(cands)
    print(f"\n=== LLM 選出 {len(picked)} 則 ===")
    for p in picked:
        print(f"[{p['source']}] {p['title']}\n    理由:{p['reason']}")
