"""Agnes live connectivity probe (no server, no mocks).

Verifies the HCN gateway slot can actually reach the configured agnes
endpoint with a real key/model before we test the full server stack:
  1. plain chat completion reachable
  2. OpenAI-compatible tool/function calling honored
Prints PASS/FAIL per step; exit code 0 only when all steps pass.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


async def main() -> int:
    base_url = os.getenv("HCN_BASE_URL")
    api_key = os.getenv("HCN_API_KEY")
    model = "agnes-2.5-flash"
    results: list[tuple[str, bool, str]] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    if not base_url or not api_key:
        print("[FAIL] HCN_BASE_URL / HCN_API_KEY not configured")
        return 1

    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    # Step 1: plain chat completion -------------------------------------------
    try:
        llm = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.2,
            max_tokens=512,
            timeout=60,
        )
        resp = await llm.ainvoke(
            [SystemMessage(content="你是一个测试助手，回答要简短。"),
             HumanMessage(content="用一句话说明 OpenAI 兼容 API 是什么。")]
        )
        text = resp.content or ""
        step("chat completion 连通", bool(text.strip()), f"reply={text.strip()[:60]!r}")
        if not text.strip():
            return 1
    except Exception as e:  # noqa: BLE001
        step("chat completion 连通", False, f"{type(e).__name__}: {e}")
        return 1

    # Step 2: tool calling (OpenAI function calling) ---------------------------
    try:
        llm_tools = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.0,
            max_tokens=512,
            timeout=60,
        ).bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "get_price",
                        "description": "获取指定股票代码的最新价格",
                        "parameters": {
                            "type": "object",
                            "properties": {"symbol": {"type": "string", "description": "股票代码"}},
                            "required": ["symbol"],
                        },
                    },
                }
            ]
        )
        tool_resp = await llm_tools.ainvoke(
            [HumanMessage(content="请查询 AAPL 的最新价格，调用相应工具。")]
        )
        calls = getattr(tool_resp, "tool_calls", None) or []
        if calls:
            step("tool calling（function calling）", True,
                 f"tool={calls[0].get('name', calls[0].get('name') if isinstance(calls[0], dict) else calls[0])}")
        else:
            step("tool calling（function calling）", False,
                 f"no tool_call in response: {str(tool_resp.content)[:80]!r}")
            return 1
    except Exception as e:  # noqa: BLE001
        step("tool calling（function calling）", False, f"{type(e).__name__}: {e}")
        return 1

    ok = all(r[1] for r in results)
    print(f"\nAgnes 连通探针: {sum(1 for r in results if r[1])}/{len(results)} 通过" + (" — ✅" if ok else " — ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))