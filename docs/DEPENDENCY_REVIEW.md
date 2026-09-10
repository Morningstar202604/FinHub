# FinHub 依赖季度审查（M3-E）

> 目的:本阶段**不做任何锁定依赖的升级**——只有先证明无回归才能升级。本文档记录当前版本、升级窗口与风险,供后续季度审查按窗口行动。
> 结论:除 `certifi`/`httpx` 类无风险补丁外,本季度**无强制升级项**;langgraph 系与 deepagents 的升级必须走「全量回归 + 迁移/replay 兼容测试」流程。

---

## 一、审查清单（按风险分组）

### 1.1 高风险锁定依赖（升级需先跑全量回归 + 迁移/replay）

| 依赖 | 当前约束 | 升级窗口 | 风险说明 | 动作 |
|---|---|---|---|---|
| `langgraph` | `>=1.2.2,<2` | 2.x 发布后评估 | DeltaChannel 磁盘格式：<1.2 读不了 delta blob；`ensure_message_ids` 依赖 1.2.2+ 的 upstream id-stamping | 观望；切 2.x 前必须跑 checkpoint rebuild + replay 测试 |
| `langgraph-checkpoint-postgres` | `>=3.1,<4` | 随 langgraph 一起 | 与 checkpointer 同锁大步进 | 观望 |
| `deepagents` | `>=0.6.11,<0.8` | 0.8+ 且确认 4 个符号仍在 `__all__` 外可用 | 0.7.0 已删 `WriteResult.files_update`——0.x minor 可随时删我们 import 的私有符号 | 观望；0.8 前核对 import |
| `scrapling[fetchers]` | `==0.4.15` | 验证 `_browsers._controllers` / `._stealth` 私有 API 后 | 私有模块名无 semver 保障 | 观望；升级前 grep 私有 import |
| `mcp` | `==2.1.1` | 2.2+ 稳定版 + 全量 MCP 测试 | SDK 协议层行为变化影响 connector 层 | 观望 |

### 1.2 中风险（有安全/兼容驱动但需验证）

| 依赖 | 当前约束 | 升级窗口 | 说明 | 动作 |
|---|---|---|---|---|
| `langchain-openai` / `langchain-anthropic` / `langchain_google_genai` / `langchain-deepseek` | 各自 floor | 任一 0.x/1.x 破坏性 release | wrapper 层 normalize 错误,影响 `classify_stream_exception` 的模块前缀匹配 | 升级后跑 SSE 分类测试 |
| `opentelemetry-*`（observability extra） | `>=1.41.1` / `0.62b1` | 贡献包与 core 锁步 bump | contrib 0.x.bN 与 core 1.x.x 必须同时升 | 成组升级 |

### 1.3 低风险（可顺带升级的补丁窗口）

| 依赖 | 当前约束 | 说明 | 动作 |
|---|---|---|---|
| `certifi>=2026.1.4` | 已含年份 pin | 证书轮换 | 安全补丁随时升 |
| `httpx[http2]>=0.28.1` | floor | 上游 bugfix | 补丁版本可升 |
| `rank-bm25>=0.2.2` | floor（M2-E 引入） | 纯 Python 零依赖 | 无风险 |
| `json-repair>=0.60.1` | override 到 >=0.60.1（GHSA-xf7x-x43h-rpqh） | 已解决安全通告 | 已达标 |

---

## 二、升级前置门禁（任何锁定依赖改动必须满足）

1. `uv run pytest tests/unit/` 全量绿。
2. langgraph 系:额外跑 migrations 到最新 + `contract_guard.py --check` + 事件台账 check（若涉及 checkpoint 格式）。
3. deepagents/scrapling/opentelemetry 系:跑 `scripts/e2e/simulation_smoke.py` + evals `run all`。
4. 前端: `tsc --noEmit` + vitest（若依赖影响 server 依赖树）。

> 本季度评估:无必须强制升级项;`certifi` 已是最新安全补丁;其余保持现状并每季度复核本表。

---

## 三、本季度实际变动记录

- 新增依赖 `rank-bm25>=0.2.2`（M2-E 记忆检索,零依赖纯 Python）——已完成并有 13 项单测。
- 新增 `override-dependencies` 中 `json-repair>=0.60.1`（安全通告 GHSA-xf7x-x43h-rpqh）——已完成。
- 未执行任何锁定依赖升级。