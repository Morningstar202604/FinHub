#!/usr/bin/env python3
"""Agnes-driven end-to-end capability suite for FinHub.

Drives the real product surface: send a message through
``POST /api/v1/threads/messages`` and consume the SSE agent stream exactly like
the web client does, then report what the agent actually did — tool calls,
artifacts, errors, wall time.

Usage:
    python scripts/e2e/agnes_capability_suite.py            # default suite
    python scripts/e2e/agnes_capability_suite.py a,c        # subset by key
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from typing import Any

import requests

BASE = "http://localhost:8000/api/v1"

TASKS: dict[str, dict[str, str]] = {
    "code-ptc": {
        "query": (
            "用 Python 做一次投资组合蒙特卡洛模拟：5 个资产，252 个交易日，"
            "计算组合年化收益、波动率、夏普比率和 95% VaR，把结果写成 "
            "summary.md（含一张 Markdown 表格），并告诉我夏普比率是多少。"
        ),
        "mode": "ptc",
    },
    "chart-artifact": {
        "query": (
            "用 matplotlib 画一张 30 天模拟股价走势图（随机游走），标题写中文"
            "《模拟股价走势图》，X 轴『交易日』，Y 轴『价格』，保存为 chart.png，最后告诉我文件路径。"
        ),
        "mode": "ptc",
    },
    "market-data": {
        "query": "获取 AAPL 的最新股价，给出简要技术面判断（趋势、支撑、阻力）。",
        "mode": "ptc",
    },
    "research-report": {
        "query": (
            "写一份《数据中心 AI 算力产业链》投资研究报告大纲，要求：三级结构、"
            "每节给出核心问题清单与需要采集的数据项，最后附关键风险。"
        ),
        "mode": "flash",
    },
    "personal-ledger": {
        "query": (
            "我有这些月度数据：税后收入 38000 元、房租 9500、餐饮 4200、交通 1300、"
            "订阅服务 480、健身年卡分摊 300、房贷月供 12800（剩余本金 198 万，"
            "利率 4.1%，剩余 26 年）。帮我判断现金流健康度、储蓄率、应急基金缺口，"
            "并给出一条 12 个月的可执行改善方案。"
        ),
        "mode": "ptc",
    },
}


def workspaces() -> list[dict[str, Any]]:
    r = requests.get(f"{BASE}/workspaces", timeout=20)
    r.raise_for_status()
    return r.json().get("workspaces") or []


def parse_sse(resp: requests.Response):
    """Yield (event_name, data_str) tuples from an SSE body."""
    ev = "message"
    buf: list[str] = []
    for raw in resp.iter_lines(decode_unicode=True):
        line = raw.rstrip("\r") if raw else ""
        if line.startswith("event:"):
            ev = line.split(":", 1)[1].strip()
        elif line.startswith(":"):  # comment / heartbeat
            continue
        elif line.startswith("data:"):
            buf.append(line.split(":", 1)[1].lstrip())
        elif line == "":
            if buf:
                yield ev, "\n".join(buf)
            buf = []
            ev = "message"
    if buf:
        yield ev, "\n".join(buf)


def run_task(key: str, ws_id: str, timeout: int = 420) -> dict[str, Any]:
    task = TASKS[key]
    body = {
        "workspace_id": ws_id,
        "messages": [{"role": "user", "content": task["query"]}],
        "agent_mode": task["mode"],
        "plan_mode": False,
        "locale": "zh-CN",
        "timezone": "Asia/Shanghai",
    }
    t0 = time.time()
    stats: dict[str, Any] = {
        "key": key, "mode": task["mode"], "events": {}, "tools": [],
        "errors": [], "text_len": 0, "artifacts": [], "elapsed": 0.0, "samples": {},
        "status": None, "run_id": None, "final_text": "",
    }
    chunks: list[str] = []
    try:
        resp = requests.post(
            f"{BASE}/threads/messages", json=body, stream=True, timeout=timeout,
            headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"connect: {exc}")
        stats["status"] = "connect-failed"
        return stats

    if resp.status_code >= 400:
        stats["errors"].append(f"HTTP {resp.status_code}: {resp.text[:300]}")
        stats["status"] = "http-error"
        return stats

    cloc = resp.headers.get("Content-Location") or ""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(cloc).query)
    if qs.get("run_id"):
        stats["run_id"] = qs["run_id"][0]

    with resp:
        for ev, data in parse_sse(resp):
            stats["events"][ev] = stats["events"].get(ev, 0) + 1
            try:
                payload = json.loads(data)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(payload, dict):
                continue
            ptype = payload.get("type") or payload.get("event") or ""
            # Tool names arrive under a handful of schemas depending on the
            # event kind; scan the shallow rather than guessing one key.
            for key_ in ("tool_name", "tool", "toolName", "name", "display_name"):
                v = payload.get(key_)
                if isinstance(v, str) and v and len(v) < 64:
                    stats["tools"].append(v)
                    break
            # tool_calls events carry a list under "tool_calls"; results echo a
            # tool_call_id back. Name lives at tool_calls[].name (LangChain shape).
            for holder in (payload.get("tool_calls"), payload.get("tool_call_chunks")):
                if isinstance(holder, list):
                    for item in holder:
                        if isinstance(item, dict) and isinstance(item.get("name"), str):
                            stats["tools"].append(item["name"])
            nested = payload.get("tool_call") or payload.get("function")
            if isinstance(nested, dict):
                nm = nested.get("name")
                if isinstance(nm, str):
                    stats["tools"].append(nm)
            if ev in ("tool_calls", "tool_call_result", "artifact") and \
                    len(stats["samples"].get(ev, [])) < 1:
                stats["samples"][ev] = json.dumps(payload, ensure_ascii=False)[:400]
            if str(ptype).lower() in {"error", "failed"} or payload.get("error"):
                stats["errors"].append(json.dumps(payload)[:300])
            for key_ in ("content", "delta", "text"):
                v = payload.get(key_)
                if isinstance(v, str):
                    stats["text_len"] += len(v)
            # Final assistant answer lands as message_chunk deltas on the
            # model-scoped agent; tool results are attributed to agent="tools".
            if isinstance(payload.get("content"), str) and str(payload.get("agent", "")).startswith("model"):
                chunks.append(payload["content"])
            for key_ in ("file_path", "artifact", "artifact_path", "path"):
                v = payload.get(key_)
                if isinstance(v, str) and v:
                    stats["artifacts"].append(v)
            if time.time() - t0 > timeout:
                stats["errors"].append("timeout")
                break

    stats["final_text"] = "".join(chunks)
    with open(f"/tmp/finhub-transcript-{key}.txt", "w") as fh:
        fh.write(stats["final_text"])
    stats["elapsed"] = round(time.time() - t0, 1)
    stats["status"] = "stream-ended"
    return stats


def main() -> int:
    keys = sys.argv[1].split(",") if len(sys.argv) > 1 else list(TASKS)
    ws_list = workspaces()
    if not ws_list:
        print("[FAIL] no workspaces available")
        return 1
    ws_id = ws_list[0]["workspace_id"]
    print(f"workspace: {ws_id}\n")

    failures = 0
    for key in keys:
        if key not in TASKS:
            print(f"[SKIP] unknown task {key}")
            continue
        print(f"===== {key} ({TASKS[key]['mode']}) =====")
        res = run_task(key, ws_id)
        tools = sorted(set(res["tools"]))
        print(f"  status    : {res['status']}")
        print(f"  elapsed   : {res['elapsed']}s")
        print(f"  events    : {res['events']}")
        print(f"  tools     : {tools[:12]}")
        print(f"  artifacts : {sorted(set(res['artifacts']))[:8]}")
        print(f"  text bytes: {res['text_len']}")
        print(f"  answer    : {(res['final_text'] or '').strip()[:600]!r}")
        for k, v in res["samples"].items():
            print(f"  sample[{k}]: {v}")
        if res["errors"]:
            failures += 1
            for e in res["errors"][:4]:
                print(f"  ERROR     : {e}")
        print()
    print(f"SUMMARY: {len(keys) - failures}/{len(keys)} clean, {failures} with errors")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
