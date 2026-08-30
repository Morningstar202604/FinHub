"""HCN OpenAI-compatible gateway (local dev stand-in).

A protocol-complete OpenAI Chat Completions server used as the backend for the
``hcn-gateway`` model while no external gateway base URL is configured. It:

- implements GET /v1/models and POST /v1/chat/completions (stream + non-stream)
- logs every request to ``gateway_requests.log`` so tests can assert exactly
  which system prompt, tools, temperature, and reasoning params the app sent
- follows the language mandated by the app's system prompt
- triggers the app's ``web_search`` tool call when the user asks a
  current/factual question and the tool is available (exercises the search flow)
- synthesizes a final answer after a tool result (exercises tool-result flow)
- echoes memory-aware phrasing when the app injects memory context

Run:  .venv/bin/python hcn_gateway.py --port 8020
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="HCN Gateway", version="1.0.0")

LOG_PATH = Path(__file__).parent / "gateway_requests.log"

# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------


def _log_request(entry: dict) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Language / behavior helpers
# ---------------------------------------------------------------------------

_LANG_RE = {
    "zh": re.compile(r"[\u4e00-\u9fff]"),
    "ja": re.compile(r"[\u3040-\u30ff]"),
}


def _detect_language(text: str) -> str:
    zh = len(_LANG_RE["zh"].findall(text))
    ja = len(_LANG_RE["ja"].findall(text))
    if ja > zh and ja > 0:
        return "ja"
    if zh > 0:
        return "zh"
    return "en"


def _system_language(system_prompt: str) -> Optional[str]:
    """The app injects an explicit language instruction into the system prompt."""
    s = system_prompt
    if re.search(r"用中文|中文回答|Chinese", s, re.I) and "不用中文" not in s:
        return "zh"
    if re.search(r"日本語|日本語で|Japanese", s, re.I):
        return "ja"
    if re.search(r"respond in English|always English|in English", s, re.I):
        return "en"
    return None


# Keywords that signal the user wants current / factual info → trigger web_search.
_SEARCH_TRIGGERS = re.compile(
    r"搜索|查一下|最新|今天|实时|新闻|天气|股票行情|股价|收盘|涨跌|汇率|"
    r"news|latest|today|current|weather|stock price|quote|price of|how many|"
    r"what is the (latest|current)|search for",
    re.I,
)


def _has_tool(messages: list, tools: list) -> bool:
    """True when an earlier model turn already requested a tool (result pending)."""
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            return True
    if messages and messages[-1].get("role") == "tool":
        return True
    return False


def _last_user_message(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                return "\n".join(parts)
    return ""


def _system_prompt(messages: list) -> str:
    for m in messages:
        if m.get("role") == "system":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts = []
                for block in c:
                    if isinstance(block, dict):
                        if block.get("type") in ("text", "input_text"):
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "content_block":
                            parts.append(block.get("text", ""))
                return "\n".join(p for p in parts if p)
    return ""


def _find_tool(tools: list, name: str) -> Optional[dict]:
    for t in tools or []:
        fn = (t.get("function") or {}).get("name", "")
        if fn == name or name in fn:
            return t
    return None


def _tool_result_content(messages: list) -> str:
    """Content of the most recent tool result, for post-tool synthesis."""
    for m in reversed(messages):
        if m.get("role") == "tool":
            c = m.get("content")
            if isinstance(c, str):
                return c[:4000]
            if isinstance(c, list):
                return json.dumps(c, ensure_ascii=False)[:4000]
    return ""


def _extract_search_query(user_text: str) -> str:
    cleaned = re.sub(r"^\s*(请|帮我|麻烦)?\s*", "", user_text).strip()
    cleaned = re.sub(r"[。！？!?]+$", "", cleaned)
    return cleaned[:200] or "最新资讯"


# ---------------------------------------------------------------------------
# Response text synthesis
# ---------------------------------------------------------------------------

_FINANCE_WORDS = re.compile(
    r"股票|股价|行情|基金|投资|财报|财报|市值|收益|涨|跌|市盈率|"
    r"stock|share|equity|market|fund|invest|earnings|revenue|ticker|"
    r"portfolio|仓位|仓位|仓位|持仓",
    re.I,
)


def _synthesize_text(user_text: str, lang: str, has_memory: bool, custom_inst: str, params: dict) -> str:
    """Deterministic, coherent mock answer that reflects app wiring."""
    temperature = params.get("temperature")
    if lang == "zh":
        creative_hint = (
            "（创造力参数已生效：temperature=%.1f）" % temperature
            if isinstance(temperature, (int, float))
            else ""
        )
        memory_hint = "\n我注意到你已经开启了记忆功能，我会结合你的历史偏好来回答。" if has_memory else ""
        inst_hint = f"\n我已遵循你的自定义指令：「{custom_inst}」" if custom_inst else ""

        if _FINANCE_WORDS.search(user_text):
            base = (
                "好的，我帮你分析了当前行情。以$TSLA为例：最新价 $242.35（较前收 +2.4%），"
                "盘中成交量放大，市场情绪偏暖。从基本面看，其季度营收保持增长，现金流健康；"
                "短期支撑位在 $235，上方压力位 $252。建议结合你的风险偏好分批关注，"
                "不要追高。如果需要更详细的个股对比、财报拆解或技术指标，告诉我即可。"
            )
        else:
            base = (
                f"收到你的问题：「{user_text}」。\n"
                "我的理解如下：\n"
                "1. 核心诉求已明确，我会按优先级处理；\n"
                "2. 建议的下一步是：先确认目标与约束，再给出可执行方案；\n"
                "3. 如果你需要更深入的财务分析、数据表格或代码实现，随时告诉我。"
            )
        return f"{base}{memory_hint}{inst_hint}{creative_hint}"

    if lang == "ja":
        base = (
            f"ご質問「{user_text}」を受け取りました。\n"
            "要点を整理すると：\n"
            "1. 目的を明確化し、優先順位に沿って進めます；\n"
            "2. 次のアクションを提案します；\n"
            "3. 財務分析やデータ表、コード実装が必要ならお知らせください。"
        )
        memory_hint = "\n記憶機能が有効のため、あなたの過去の好みを考慮して回答します。" if has_memory else ""
        return f"{base}{memory_hint}"

    # English
    creative_hint = (
        " (creativity param active: temperature=%.1f)" % temperature
        if isinstance(temperature, (int, float))
        else ""
    )
    memory_hint = "\nI have memory enabled and will factor in your history." if has_memory else ""
    inst_hint = f"\nFollowing your custom instructions: \"{custom_inst}\"" if custom_inst else ""
    if _FINANCE_WORDS.search(user_text):
        base = (
            f"Got it. On {user_text}: $TSLA last traded at $242.35 (+2.4% from prior "
            "close) on healthy volume. Fundamentals remain solid with growing revenue "
            "and positive cash flow. Near-term support sits at $235 with resistance at "
            "$252. I'd suggest a phased approach sized to your risk appetite. Want a "
            "deeper dive into peer comparison, earnings, or technicals?"
        )
    else:
        base = (
            f"Understood — you're asking about: \"{user_text}\".\n"
            "Here's how I'd approach it:\n"
            "1. Clarify the goal and constraints;\n"
            "2. Propose an executable next step;\n"
            "3. Ask for more detail if you need deeper financial analysis, tables, or code."
        )
    return f"{base}{memory_hint}{inst_hint}{creative_hint}"


def _synthesize_from_tool(tool_content: str, lang: str) -> str:
    snippet = tool_content.strip().replace("\n", " ")[:500]
    if lang == "zh":
        return (
            "我已完成联网搜索，结果如下：\n"
            f"搜索到相关信息：{snippet}\n"
            "以上信息来自最新检索结果。如果你需要我进一步整理成表格、做交叉验证，"
            "或者针对某一条展开分析，直接告诉我就行。"
        )
    if lang == "ja":
        return (
            "Web検索の結果は以下のとおりです：\n"
            f"{snippet}\n"
            "さらに深掘りが必要であればお知らせください。"
        )
    return (
        "I've completed the web search. Here's what I found:\n"
        f"{snippet}\n"
        "Let me know if you'd like this organized into a table, cross-checked, or "
        "analyzed further."
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible endpoints
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    model: str = "hcn-gateway"
    messages: list[dict] = []
    tools: Optional[list] = None
    tool_choice: Any = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stream_options: Optional[dict] = None
    reasoning: Optional[dict] = None
    extra_body: Optional[dict] = None
    response_format: Optional[dict] = None
    model_kwargs: Optional[dict] = None
    n: Optional[int] = 1
    user: Optional[str] = None


@app.get("/v1/models")
async def list_models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": "hcn-gateway",
                "object": "model",
                "created": now,
                "owned_by": "hcn",
            }
        ],
    }


def _build_response(req: ChatRequest) -> dict:
    """Compute the completion content / tool calls for a request."""
    messages = req.messages
    tools = req.tools or []
    system = _system_prompt(messages)
    user_text = _last_user_message(messages)
    lang = _system_language(system) or _detect_language(user_text or system)

    # Custom instructions: the app merges them into the system prompt. Capture
    # a trimmed persona fragment for the mock to acknowledge.
    custom_inst = ""
    custom_match = re.search(r"自定义指令[:：]\s*(.{0,120})", system, re.S)
    if custom_match:
        custom_inst = custom_match.group(1).strip()

    has_memory = bool(re.search(r"记忆|memory", system, re.I))
    params = {
        "temperature": req.temperature,
        "max_tokens": req.max_tokens or req.max_completion_tokens,
        "reasoning": req.reasoning,
        "tool_choice": req.tool_choice,
    }

    # Post-tool-result: synthesize a final answer.
    if messages and messages[-1].get("role") == "tool":
        content = _synthesize_from_tool(_tool_result_content(messages), lang)
        return {"content": content, "tool_calls": None, "params": params}

    # Tool already requested earlier in this turn but result not yet present:
    # keep the loop moving with a short acknowledgement.
    if _has_tool(messages, tools):
        if lang == "zh":
            content = "收到工具结果，正在为你整理最终结论。"
        elif lang == "ja":
            content = "ツールの結果を受け取りました。最終的な回答をまとめます。"
        else:
            content = "Got the tool result; finalizing the answer now."
        return {"content": content, "tool_calls": None, "params": params}

    # Fresh user turn with a search tool available and search intent:
    # emit a web_search tool call so the app's search flow is exercised.
    search_tool = _find_tool(tools, "web_search")
    if search_tool is not None and _SEARCH_TRIGGERS.search(user_text):
        query = _extract_search_query(user_text)
        tool_call = {
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": json.dumps(
                    {"query": query, "topic": "general", "time_range": "week"},
                    ensure_ascii=False,
                ),
            },
        }
        return {"content": None, "tool_calls": [tool_call], "params": params}

    # Default: text answer.
    content = _synthesize_text(user_text, lang, has_memory, custom_inst, params)
    return {"content": content, "tool_calls": None, "params": params}


def _usage(req: ChatRequest) -> dict:
    prompt = sum(
        len(str(m.get("content", ""))) for m in req.messages
    ) + len(json.dumps(req.tools or [], ensure_ascii=False))
    return {
        "prompt_tokens": max(1, prompt // 4),
        "completion_tokens": 64,
        "total_tokens": max(1, prompt // 4) + 64,
    }


def _response_payload(req: ChatRequest) -> dict:
    result = _build_response(req)
    completion_id = f"chatcmpl_{uuid.uuid4().hex[:24]}"
    now = int(time.time())
    tool_calls = result["tool_calls"]
    payload = {
        "id": completion_id,
        "object": "chat.completion",
        "created": now,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["content"],
                },
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": _usage(req),
    }
    if tool_calls:
        payload["choices"][0]["message"]["tool_calls"] = tool_calls
    if result["params"].get("reasoning") is not None:
        payload["reasoning"] = {"effort": result["params"]["reasoning"].get("effort")}
    return payload


def _stream_payload(req: ChatRequest):
    """Yield OpenAI SSE chunks for a chat completion."""
    result = _build_response(req)
    completion_id = f"chatcmpl_{uuid.uuid4().hex[:24]}"
    now = int(time.time())
    tool_calls = result["tool_calls"]

    def chunk(delta: dict, finish: Optional[str] = None) -> str:
        data = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": req.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    # role preamble
    yield chunk({"role": "assistant", "content": ""})

    if tool_calls:
        tc = tool_calls[0]
        fn = tc["function"]
        # name chunk
        yield chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": fn["name"], "arguments": ""},
                    }
                ]
            }
        )
        # arguments chunk (split so incremental parsing is exercised)
        args = fn["arguments"]
        step = max(1, len(args) // 3)
        for i in range(0, len(args), step):
            yield chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"name": None, "arguments": args[i : i + step]},
                        }
                    ]
                }
            )
        yield chunk({}, finish="tool_calls")
        yield "data: [DONE]\n\n"
        return

    content = result["content"] or ""
    step = max(1, len(content) // 5)
    for i in range(0, len(content), step):
        yield chunk({"content": content[i : i + step]})
    yield chunk({}, finish="stop")
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    # Log for verification (tools, params, system prompt, language).
    _log_request(
        {
            "ts": time.time(),
            "model": req.model,
            "stream": req.stream,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens or req.max_completion_tokens,
            "reasoning": req.reasoning,
            "tool_choice": req.tool_choice,
            "tools": [t.get("function", {}).get("name") for t in (req.tools or [])],
            "roles": [m.get("role") for m in (req.messages or [])],
            "msg0_keys": list((req.messages[0].keys() if req.messages else [])),
            "system": (_system_prompt(req.messages) or "")[:20000],
            "last_user": (_last_user_message(req.messages) or "")[:1000],
        }
    )
    if req.stream:
        return StreamingResponse(
            _stream_payload(req),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    return JSONResponse(_response_payload(req))


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "hcn-gateway"}


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
