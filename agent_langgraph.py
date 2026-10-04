r"""稽核 agent — LangGraph 版(primary)。手刻對照版見 agent.py。

UPDATE 11:把手刻的 for 迴圈改寫成 LangGraph 的 StateGraph。
  L11-2:最小 graph(骨架跑通)。
  L11-3:加 checkpointer + thread_id → 跨題記憶 + 續跑(解手刻版的失憶)。
  L11-4:重現手刻版三巧思 —— 印工具呼叫 / fail-open / 達上限 fallback。
  L11-5(目前):CLI 包裝(input 迴圈,同 agent.py 體驗)。

★ MCP server 完全不改;手刻 agent.py 完全不動,兩版並存。★

跑法:  .\venv\Scripts\python.exe agent_langgraph.py
"""

from __future__ import annotations

import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from langchain_core.messages import SystemMessage, trim_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import config
from agent import SYSTEM_PROMPT   # ★ 沿用手刻版的 system prompt,不另外複製一份(DRY)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_SERVER_SCRIPT = os.path.join(_PROJECT_ROOT, "mcp_server", "finance_news_server.py")


def _connections() -> dict:
    """指向既有的 MCP server(完全不改它)。

    等同手刻 mcp_client._server_params(),只是換成 adapter 的 dict 格式。
    ★ command 用 venv python、cwd 用專案根 —— 原因同手刻版:
      否則抓到 Store 的 python stub、或 sqlite:///mimi.db 相對路徑找不到。★
    """
    return {
        "finance-news": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [_SERVER_SCRIPT],
            "cwd": _PROJECT_ROOT,
            "env": {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        }
    }


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())


async def load_tools():
    """透過 adapter 從既有 MCP server 載入工具(= 手刻版 list_tools + 轉格式)。

    ★ handle_tool_errors=True(本就是預設,這裡寫明)= fail-open:
      某個工具呼叫丟錯 → 錯誤會被包成訊息回給 LLM,讓它自己換方式,不會 crash 整張 graph。
      等同手刻版的 _call_tool_safe。★
    """
    client = MultiServerMCPClient(_connections(), handle_tool_errors=True)
    return await client.get_tools()


def build_graph(tools, checkpointer):
    """把手刻的「for turn 迴圈」宣告成一張 graph,並掛上 checkpointer。

    對照手刻 agent.py:
      agent node       = resp = LLM(messages, tools)
      ToolNode         = 執行 tool_calls 那段
      tools_condition  = if not msg.tool_calls: return(沒工具就結束)
      tools→agent 邊   = 迴圈回去再判斷
      State(messages)  = 手刻版的 messages list(但 reducer 自動累積)
      checkpointer     = ★手刻版沒有★:每步存檔 → 跨題記憶 + 續跑
    """
    llm = ChatOpenAI(model=config.AGENT_MODEL, temperature=0.3).bind_tools(tools)

    async def agent_node(state: MessagesState) -> dict:
        # ★ system prompt 不存進 State(否則跨題會一直累積複製)★
        #   改成「每次呼叫 LLM 前當場 prepend」,State 只留對話本身。
        # ★ 存多少 ≠ LLM 看多少:State(checkpointer)留全部,
        #   但這裡用 trim_messages 只「丟最近 N 則」給 LLM,防 context 爆。
        #   start_on="human" → 裁出來的視窗從使用者訊息開始,
        #   不會把 tool 訊息跟它的 assistant 呼叫切散(否則 OpenAI 會報錯)。
        recent = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=len,                 # 以「則數」計(不是 token),簡單夠用
            max_tokens=config.AGENT_HISTORY_KEEP,
            start_on="human",
            include_system=False,
        )
        msgs = [SystemMessage(content=SYSTEM_PROMPT), *recent]
        return {"messages": [await llm.ainvoke(msgs)]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))        # 內建:自動執行 tool_calls
    builder.add_edge(START, "agent")                  # 進來先到 agent
    builder.add_conditional_edges("agent", tools_condition)  # 有工具→tools;沒有→END
    builder.add_edge("tools", "agent")                # 工具跑完回 agent 再判斷(迴圈)
    return builder.compile(checkpointer=checkpointer)  # ★掛上 checkpointer★


async def ask(graph, question: str, thread_id: str) -> str:
    """問一個問題;靠 thread_id 讀回記憶,用 astream 邊跑邊印工具呼叫,回最終答案。

    三巧思(對照手刻 agent.py):
      ① 印每次工具呼叫  → 用 astream 觀察每步(手刻版是迴圈裡 print)
      ② fail-open      → 工具錯誤已由 handle_tool_errors 處理(見 load_tools)
      ③ 達上限 fallback → recursion_limit + 接 GraphRecursionError,用現有資訊逼答一次
    """
    cfg = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": config.AGENT_RECURSION_LIMIT,
    }
    final = None
    try:
        # stream_mode="updates":每個 node 跑完就吐一筆 {node: {"messages": [...]}}
        async for chunk in graph.astream(
            {"messages": [("user", question)]}, cfg, stream_mode="updates"
        ):
            for node, update in chunk.items():
                for m in (update or {}).get("messages", []):
                    if node != "agent":
                        continue
                    tool_calls = getattr(m, "tool_calls", None)
                    if tool_calls:                         # ① agent 決定呼叫工具
                        for c in tool_calls:
                            print(f"  [工具] {c['name']}({_fmt_args(c.get('args'))})")
                    elif getattr(m, "content", ""):        # agent 沒要工具 → 這就是最終答案
                        final = m.content
        return final or "(沒有內容)"

    except GraphRecursionError:                            # ③ 達上限 → 用現有資訊逼答一次
        print(f"  ⚠️ 達步數上限({config.AGENT_RECURSION_LIMIT}),用現有資訊作答")
        state = await graph.aget_state(cfg)
        history = trim_messages(
            state.values.get("messages", []),
            strategy="last", token_counter=len,
            max_tokens=config.AGENT_HISTORY_KEEP,
            start_on="human", include_system=False,
        )
        plain = ChatOpenAI(model=config.AGENT_MODEL, temperature=0.3)  # ★不綁工具 → 逼它直接答★
        resp = await plain.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT
                          + "\n(已達查詢上限,請用目前已知資訊直接作答,並註明結論可能不完整。)"),
            *history,
        ])
        return resp.content


async def cli() -> None:
    """終端機 CLI(同 agent.py 的體驗,但多了跨題記憶)。"""
    print("=" * 60)
    print(" 米米財經 — 選片品質稽核 agent(LangGraph 版)")
    print(" 輸入問題;exit/quit 離開。本版會記得同一次 session 的前面對話。")
    print("=" * 60)

    tools = await load_tools()
    # ★ checkpointer 要「開著的」連線 → 整個 CLI 都在這個 async with 裡 ★
    async with AsyncSqliteSaver.from_conn_string(config.AGENT_CHECKPOINT_DB) as saver:
        graph = build_graph(tools, saver)
        thread = "cli-session"   # 全程同一個 thread_id → 整段對話共享記憶(換 id = 開新對話)

        while True:
            # ★ input() 會阻塞 event loop → 丟到 thread 跑,不卡住 async ★
            try:
                q = (await asyncio.to_thread(input, "\n問題> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再見!")
                break
            if q.lower() in ("exit", "quit", ""):
                print("再見!")
                break
            try:
                print(await ask(graph, q, thread))
            except Exception as exc:  # noqa: BLE001 — 單題失敗不讓整個 CLI 崩
                print(f"  ⚠️ 這題處理失敗:{exc}(可再問一次或換個問法)")


if __name__ == "__main__":
    asyncio.run(cli())
