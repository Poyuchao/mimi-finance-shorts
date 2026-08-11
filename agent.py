r"""選片品質稽核 agent(UPDATE 9)。

一個獨立、純唯讀的終端機 CLI:用自然語言問「歷史選片品質」,
由 LLM(OpenAI function calling)★自己決定★呼叫哪些 MCP 工具、呼叫幾次,
做完多步推理後,產出結構化稽核報告。

與發片 pipeline 的差異:
  • pipeline(main.py)是「線性」:步驟順序寫死。
  • 這個 agent 是「迴圈」:呼叫哪個工具、幾次、何時停,由 LLM 決定。

★ 純唯讀:只透過 MCP 查 DB / 抓新聞,不寫入、不改 prompt、不動發片。★
★ 一律走既有 mcp_client 的 MCP server,不繞過直接呼叫 repository。★

跑法:
    python agent.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

# Windows 主控台 cp950 → 強制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from mcp import ClientSession, stdio_client

import config
import mcp_client   # 沿用其 _server_params() 啟 server、_parse() 解析回傳

logger = logging.getLogger("agent")


SYSTEM_PROMPT = """你是「米米財經」的選片品質稽核員。
你可以呼叫工具查詢歷史選片紀錄,用資料回答使用者對「選片品質」的提問。

★★★ 三個概念千萬不要混淆(這是最重要的一條)★★★
  「候選(candidate)」= 一堆『可能被選』的新聞,大多數最後沒被選中。
  「選中/發布(selected)」= LLM 真的挑進影片、已發布的那 3 則(有選片理由)。
  只有「選中」的才算「選了 / 上了 / 發布了」。候選 ≠ 選中。

可用的資料工具(由 MCP 提供,實際清單以傳入的 tools 為準):
- get_recent_selections(days)【選片事實·來自 DB】:近 N 天『真正選中/已發布』的新聞,
    附選片理由 select_reason、position、run_id。★問「選了什麼 / 上了什麼」一律用這個★
    (days=1 就是今天)
- get_run_detail(run_id)【單次深挖·來自 DB】:某一次的完整候選 + 選中的 3 則 + 理由,
    要比較「選中的」與「同批被淘汰的」時用。
- fetch_finance_news(pool_size)【即時候選·非 DB】:抓現在即時 RSS 的候選池。
    ⚠️ 回的是『還沒被選』的候選,★沒有 selected、沒有理由★,而且會隨時間變動。
    只用來回答「今天現在還有哪些新題材可選」。
    ★★ 絕對不可用它回答「選了什麼 / 上了什麼 / 為什麼選」—— 它的新聞都不是選片結果 ★★

稽核時重點看:
1. 主體重複 —— 同一次是否選了同一家公司/同一主體的多則新聞(違反題材分散)
2. 來源偏食 —— 三個來源(ETtoday / 自由時報 / 風傳媒)是否嚴重失衡
3. 題材集中 —— 是否連續多天都選同類型(如都是大盤盤勢、都是個股財報)
4. 理由品質 —— LLM 給的選片理由是否具體,還是流於空泛

★★★ 送出答案前,務必做這道「最終自我檢查」★★★
  檢查①【有沒有真的查資料】我是根據工具回傳的真實資料,還是在憑空推測?
        → 若還沒查,先呼叫工具,不要編造。★尤其:選片理由只能來自工具回傳的
          select_reason 欄位,絕不可自己生一個看起來合理的理由。★
  檢查②【候選 vs 選中,沒搞混】我講的每一則「選了/上了/發布了」的新聞,
        是不是真的來自 get_recent_selections / get_run_detail(有 select_reason)?
        → 若它是來自 fetch_finance_news,那它只是候選,★不能說它被選中/發布★。
  檢查③【每個問題都對得上 run_id】我指出的每個問題,是否都能指到具體的 run_id?
  檢查④【嚴重度分級正確】blocking = 傷內容可信度(如主體重複);
        minor = 可接受的瑕疵(如來源略偏)。別把小事當大事。

當你已經有足夠資訊、不需要再呼叫工具時,直接輸出「稽核報告」,格式為 JSON:
{
  "period": "查詢區間(如:近 7 天,run 3~8)",
  "runs_analyzed": 分析了幾次執行,
  "issues": [
    {"type": "主體重複/來源偏食/題材集中/理由空泛",
     "severity": "blocking 或 minor",
     "run_id": 對應的執行編號(跨多次就填代表性的),
     "detail": "具體描述",
     "suggestion": "具體建議"}
  ],
  "source_distribution": {"自由時報": n, "風傳媒": n, "ETtoday": n},
  "summary": "一句話總結"
}
若使用者只是問簡單事實(如「最近選了哪些新聞」),可用簡短自然語言回答,不必套 JSON。
"""


# ── MCP tool schema → OpenAI tools 格式 ────────────────────
def _mcp_to_openai_tools(mcp_tools) -> list[dict]:
    """把 MCP 的 tool 定義轉成 OpenAI function calling 的 tools 格式。

    ★ MCP 的 inputSchema 本身就是合法 JSON Schema,OpenAI 的 parameters 直接吃;
      兩邊差在外層包裝(MCP: name/description/inputSchema;OpenAI: function.parameters)。★
    """
    tools = []
    for t in mcp_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "").strip(),
                "parameters": t.inputSchema,
            },
        })
    return tools


async def _call_tool_safe(session: ClientSession, name: str, args: dict):
    """呼叫 MCP 工具;失敗回結構化錯誤(不 raise、不中斷 agent)。

    ★ Q8:工具失敗要讓 LLM 自己決定換方式,所以錯誤要「回給它」,不是拋出去。★
    """
    try:
        result = await session.call_tool(name, args)
        return mcp_client._parse(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("工具 %s 失敗:%s", name, exc)
        return {"error": f"工具 {name} 呼叫失敗:{exc}"}


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


async def run_agent(question: str) -> None:
    """對單一問題跑決策迴圈,把結果印到終端機。"""
    from openai import OpenAI

    client = OpenAI()   # 讀環境變數 OPENAI_API_KEY(.env 已 load)

    async with stdio_client(mcp_client._server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # MCP discovery → 轉 OpenAI tools
            mcp_tools = (await session.list_tools()).tools
            oai_tools = _mcp_to_openai_tools(mcp_tools)

            messages: list[dict] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            for turn in range(1, config.AGENT_MAX_ITERATIONS + 1):
                resp = client.chat.completions.create(
                    model=config.AGENT_MODEL,
                    messages=messages,
                    tools=oai_tools,
                    temperature=0.3,
                )
                msg = resp.choices[0].message

                # 沒有要呼叫工具 → LLM 給答案了,結束
                if not msg.tool_calls:
                    _print_answer(msg.content or "(沒有內容)")
                    return

                # 把 assistant 這輪(含 tool_calls)加回對話
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })

                # ★ 一輪可能要求多個工具 → 全部執行完再一起回覆 ★
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"  [工具] {tc.function.name}({_fmt_args(args)})   ← 第 {turn} 輪")

                    result = await _call_tool_safe(session, tc.function.name, args)

                    # ★ 每筆 tool 回覆必須帶對應 tool_call_id,漏了 OpenAI 會 400 ★
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                # 回頭讓 LLM 再判斷(可能再查,或給答案)

            # 迴圈用盡 → 逼它用現有資訊作答一次(不再給工具)
            print(f"  ⚠️ 已達迭代上限({config.AGENT_MAX_ITERATIONS} 輪),用現有資訊作答")
            messages.append({
                "role": "user",
                "content": "已達查詢次數上限,請用目前已取得的資訊直接給出稽核報告,"
                           "並在 summary 註明『因達迭代上限,結論可能不完整』。",
            })
            final = client.chat.completions.create(
                model=config.AGENT_MODEL,
                messages=messages,
                temperature=0.3,
            )
            _print_answer(final.choices[0].message.content or "(沒有內容)")


def _root_cause(exc: BaseException) -> str:
    """從 async 的 ExceptionGroup / 巢狀 __cause__ 中挖出最有意義的根因訊息。

    (stdio 子行程起不來時,錯誤會被包成 ExceptionGroup,直接 str() 只會拿到
     『unhandled errors in a TaskGroup』這種無意義字串。)
    """
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        subs = getattr(cur, "exceptions", None)   # ExceptionGroup
        if subs:
            return _root_cause(subs[0])
        if cur.__cause__ is None and cur.__context__ is None:
            return f"{type(cur).__name__}: {cur}"
        nxt = cur.__cause__ or cur.__context__
        if nxt is None or isinstance(cur, (ConnectionError,)):
            return f"{type(cur).__name__}: {cur}"
        cur = nxt
    return f"{type(exc).__name__}: {exc}"


def _print_answer(content: str) -> None:
    """LLM 回的可能是純 JSON、可能包 markdown code fence,盡量印漂亮,失敗就印原文。"""
    text = content.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ``` 圍欄
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()

    print(f"\n{'─' * 60}")
    try:
        data = json.loads(text)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(content.strip())   # 不是 JSON(簡短自然語言回答)→ 原文照印
    print("─" * 60)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print("=" * 60)
    print(" 米米財經 — 選片品質稽核 agent(輸入問題;exit/quit 離開)")
    print(" 例:這週選片品質有沒有問題? / run 8 為什麼這樣選?")
    print("=" * 60)
    while True:
        try:
            q = input("\n問題> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再見!")
            break
        if q.lower() in ("exit", "quit", ""):
            print("再見!")
            break
        try:
            asyncio.run(run_agent(q))
        except Exception as exc:  # noqa: BLE001 — 單一問題失敗不該讓整個 CLI 崩
            root = _root_cause(exc)
            logger.warning("處理問題時發生錯誤:%s", root)
            print(f"  ⚠️ 這題處理失敗:{root}")
            print("     (MCP server 可能沒起來;可再問一次或檢查 mcp_server 設定)")


if __name__ == "__main__":
    main()
