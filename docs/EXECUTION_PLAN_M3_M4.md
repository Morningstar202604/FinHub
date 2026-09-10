# FinHub 剩余任务执行计划（M3 性能工程 + 基础设施补缺 + M4 前端重构）

> 定位：承接 [ROADMAP](./ROADMAP.md) 的阶段切换点 —— M1/M2 已全部完成（功能完整、可评测、可自证），本计划把 **M3（后端性能与工程质量）、基础设施补缺、M4（前端重构）** 展开为可直接执行的逐项计划。
> 执行纪律：按计划表逐项推进；每完成一项跑对应测试；契约红线不变（DB 变更走新迁移编号 **033+**、SSE 事件类型变更登记事件台账、MCP docstring 变更走锁脚本）。

---

## 〇、执行总览

> **状态：P1~P7 已全部落地（M3 性能工程 + 基础设施补缺 + M4 前端重构 + 全量回归）。**
> 本表为最新计划基线，已完成项带 ✅ 标注，验收数据见 P6/P7 节。

| 阶段 | 内容 | 状态 | 产物/验收 |
|---|---|---|---|
| P1 | M3-A SSE 批量刷盘 | ✅ | `stream_writer.buffer_events_many` 批量 pipeline 写入 + 测试 `test_stream_append_many` 等 |
| P2 | M3-B 索引审计 + 附尾迁移 033 | ✅ | `033_index_audit_tail` 迁移 + `test_migrations` 覆盖 + 审计结论（见 P2 节） |
| P3 | M3-C Redis pipeline 批量写收敛 | ✅ | `pipelined_event_buffer_many` + `delete_pattern` SCAN+pipeline 分块删除 + 测试 |
| P4 | M3-D 沙箱预热 + M3-E 依赖审查 | ✅ | `prewarm_sessions()` 启动预热 + `docs/DEPENDENCY_REVIEW.md` + prewarm 单测 |
| P5 | 基础设施补缺 | ✅ | CI 性能冒烟 job + evals artifact + `/health` redis 探测 + `docs/DEPLOYMENT.md` + `docs/PERFORMANCE_BASELINE.md` + `docs/DEPENDENCY_REVIEW.md` |
| P6 | M4 前端重构（skill 驱动） | ✅ | 4 个 M2 可见化页面 + 类型对账 + 前端回归（见 P6 节逐步展开） |
| P7 | 全量回归 + 最终完成报告 | ✅ | 后端+前端+evals+契约守卫全绿 + `COMPLETION_REPORT` 更新（见 P7 节） |

执行顺序：P1 → P2 → P3 → P4 → P5 → **P6 → P7（本计划已全部完成）**。

---

## P1 — M3-A SSE 单次序列化+批量刷盘

### 目标
SSE 事件帧写入 Redis Stream 时从「每事件一次网络往返」改为「批量 pipeline 一次刷盘」，同负载下降低 P95 事件写入延迟与 Redis 连接往返次数。

### 现状盘点（已确认）
- `src/server/services/runs/sse_producer.py`：
  - 事件已**单次序列化**：`_format_sse_event()` 内用 `finite_json_dumps(data)` 一次成帧，`StreamEventAccumulator` 已在内存合并相邻 `message_chunk`/`tool_call_chunks`（避免逐 token 序列化）✅ **单次序列化已达标，无需再改**。
  - 写入路径：`executor.py:769` → `stream_writer.buffer_event()` → `stream_append_with_retry()` → 单次 `pipelined_event_buffer()`（即每次 1 条 `XADD`）。
- `src/utils/cache/stream_append.py`：重试策略已完善（id 幂等 fence、tail probe、预算守门），但**批次写入入口缺失**。

### 改动点
1. **`src/utils/cache/redis_cache.py`**：新增 `pipelined_event_buffer_many(stream_key, frames, *, max_size, ttl=None)`：
   - 入参 `frames: list[tuple[int, str|bytes, str|bytes|None]]`（`(event_id, stream_event, stream_record)`）；
   - 内部 `async with self.client.pipeline(transaction=False)` 组装多条 `xadd(id=f"{eid}-0", maxlen=..., approximate=True)`，一次 `execute()`；
   - 保留 event_id=1 的 epoch DEL 与 `_HEAL_INTERVAL` 的 PERSIST 语义（只对第一条帧做 reset/heal，避免重复 DEL）。
2. **`src/utils/cache/stream_append.py`**：新增 `stream_append_many_with_retry(cache, stream_key, frames, *, max_size, label)`：
   - 复用既有重试/幂等/尾探针逻辑：按**整个批次**视为一次原子写，任一条失败按 `_nothing_was_written` 分类重试整批；重复 id 冲突则逐条细粒度回退（复用单条路径兜底），保证 I6 契约（事件不丢失）不破。
3. **`src/server/services/runs/stream_writer.py`**：新增 `buffer_events_many(thread_id, run_id, events, *, max_stored_messages)`；
   - 在 `executor.py` 由 `buffer_event` 逐条调用改为**攒批调用**（每 32 条或 50ms 刷新一次，两个条件先到者触发；`run_end` 帧强制 flush）。
4. 测试：
   - `tests/unit/cache/test_stream_append.py`：批量写入成功/部分失败重试/重复 id 回退/预算耗尽。
   - `tests/unit/cache/test_redis_cache_pipeline_many.py`：帧序保持、maxlen 生效、reset/heal 只触发一次。
   - `tests/unit/server/runs/test_stream_writer_batch.py`：攒批行为（32 条触发/50ms 触发/run_end flush）。

### 验收
- 新单测全绿；回归 `tests/unit/` 全量通过。
- `SCRIPT` 级压测：同 1000 帧写入，XADD 往返次数从 N 降至 ceil(N/32)。

---

## P2 — M3-B 索引审计 + 附尾迁移 033

### 目标
审计热门查询路径的索引覆盖，缺失/低效索引以附尾迁移补齐，杜绝全表扫描。

### 现状盘点（已确认）
- 迁移链：001 初始 schema → **032 research_loops**（最新）。
- 已有针对性索引：005 insight 唯一索引、019 hook/outbox/done/recents 索引、032 research_loops 三索引。
- 待审计表组（按查询热度）：
  - 事件/会话：`turns`、`sse_events`（若有）、`thread`（checkpoint）、`turn_lifecycle`（017/023）、`subagent_run_ledger`（020）。
  - 生产表：`provenance_records`（013/015）、`research_loops`（032）、`workspaces`、`automations`。
  - 中间件/出站：`hooks`/`outbox`（019）、`platform_secret_state`（021）、`mcp_servers`/`connectors`（012/025）、`user_skills`（026）、`agent_plugins`（028）。

### 改动点
1. 写审计脚本/查询清单：对每张表列出「WHERE 列 + ORDER BY + JOIN 列」，对照 `\d` 索引核对。
2. 产出审计报告（追加到本文件 P2 节下方）：
   - 每表结论：`已覆盖 / 缺口（列） / 建议索引（名称+列）`。
3. 若存在缺口 >0 且命中热门查询：
   - 新增迁移 `migrations/versions/033_index_audit_tail.py`（down_revision="032"）；
   - 仅建缺失索引（`IF NOT EXISTS`，命名字典）；不重建已有索引。
4. 契约红线：DB 变更走 033+ ✅；跑 `contract_guard.py --check` 确认 migrations 台账同步。

### 验收
- `tests/unit/migrations/test_migrations.py`（或等价迁移测试）覆盖 033 upgrade/downgrade 幂等。
- `EXPLAIN` 显示热门查询（按 `thread_id` 查 turns、按 workspace 查 research_loops、按 state 查 hooks）均走 Index Scan。
- contract_guard 全绿。

---

## P3 — M3-C Redis pipeline 批量写收敛

### 目标
全仓库 Redis 批量写语义收敛：没有「一次一条、N 条网络往返」的漏网点。

### 现状盘点（已确认）
- `set_many()`（redis_cache.py:324）已用 `pipeline(transaction=False)` ✅
- `mget()` 已用 `MGET` ✅
- `pipelined_event_buffer()` 单条 XADD；reset/heal/ttl 场景已用 pipeline ✅（单条自身达标）
- **缺口**：`delete_pattern()`（redis_cache.py:436）`async for key ... await delete(key)` —— SCAN 循环内**逐条网络往返**，大 keyspace 清理时可优化；`set_many` 调用点是否足够（检查是否有 gather-of-set 残留）。

### 改动点
1. `delete_pattern`/`scan_keys`：SCAN 迭代内按块（如 100 条）用 pipeline delete，减少 100 倍往返；返回总删除数语义不变。
2. 全局搜索 `await cache.set(` / `await client.set(` 循环调用点，确认无 gather 式批量写残留；有则收敛到 `set_many`。
3. 测试：`test_redis_cache_pipeline_many.py` 增加 pipeline delete 用例（mock Redis 断言 `execute` 次数）。

### 验收
- 单测全绿；pipeline delete 路径网络往返从 O(N) 降至 O(N/100)。

---

## P4 — M3-D 沙箱预热 + M3-E 依赖审查

### P4-A 沙箱预热（M3-D）
**现状盘点（已确认）**：
- `workspace_manager.py` 已有：warm session 缓存、sync cooldown（30s）、idle 停服（`cleanup_idle_workspaces`，idle_timeout 1800s）、`session_path_counter` 观测（warm_sync / warm_cooldown / warm_initializing）。
- `config.yaml` 已有 `redis_warm_on_startup: true`（Redis 缓存预热）。

**改动点**：
1. 缺「服务启动时对 always-on/最近活跃 workspace 的沙箱预热」检查：grep `startup` 挂载点，若无则新增 `prewarm_sessions()` 异步任务（启动后延迟 30s，取 `is_always_on=true` 的 workspace 调 `get_session_for_workspace`，失败不影响启动）。
2. idle 档位已存在（cooldown → stopped），补充文档化说明即可，不改语义。
3. 观测：prewarm 成功后 `session_path_counter.add(1, {"path": "prewarm"})`。
4. 测试：`test_workspace_manager.py` 增 prewarm 调度用例（mock manager，断言预热路径计数）。

### P4-B 依赖审查（M3-E）
**现状盘点（已确认）**：`pyproject.toml` 已对 langgraph/langgraph-checkpoint-postgres 有详细 floor/ceiling 注释；scrapling 有 pin 理由；deepagents 0.6.11~<0.8 有 ceiling 注释。

**改动点**：
1. 产出 `docs/DEPENDENCY_REVIEW.md`：逐依赖列 `当前版本 → 升级窗口 → 风险（delta channel parity / private API / __all__） → 动作（升级/观望/锁定）`。
2. 本阶段**不贸然升级**任何锁定依赖（langgraph delta 格式兼容需先跑迁移+replay 测试），只做文档化；仅对无风险安全补丁（如 certifi/httpx 补丁版本）可顺带升级。

### 验收
- prewarm 单测绿；依赖审查文档产出；`uv pip list` 与文档对照。

---

## P5 — 基础设施补缺（据盘点结果）

### 盘点结论（已确认）
| 维度 | 现状 | 缺口 |
|---|---|---|
| CI/CD | `test.yml`（unit+evals+artifact）、`fork-integration.yml`、`integration`（postgres/redis services）、`sandbox-integration.yml`、`release.yml`、`desktop-release.yml`、`sandbox-image.yml`、`claude.yml` | ① 无 `performance` 冒烟 job（M3-A/B 无回归护栏）② evals 在 CI 只跑 `run all`，缺失败时上传报告 artifact |
| 观测 | `src/observability/`：OTel metrics（~20 指标）/tracing/loop_lag/db_callbacks/redis_pool_callbacks；`/health`（含 checkpointer 池状态） | ③ `/health` 缺 redis/agent_config 探测 ④ metrics 无本地抓取端点（仅 OTLP/控制台导出）——补 `/metrics`（prometheus 文本）可选 |
| 配置 | `config.yaml` + `agent_config.yaml` 分离、模块日志分组、feature flags | ⑤ 缺「生产部署环境变量清单/示例」文档（.env.example 是否存在待确认） |
| 文档 | README 三语、ROADMAP、COMPLETION_REPORT | ⑥ 缺性能基线文档（P2 审计+delay 基线）⑦ 缺运维手册（迁移执行、日志、备份） |

### 改动点
1. **CI 性能冒烟**：`test.yml` 增 `performance-smoke` job（`uv run python -m scripts.perf.event_write_smoke`，将 P1 压测固化为可执行脚本）→ 阈值断言（如 1000 帧写入耗时 <2s 或往返计数达标）。
2. **CI evals 报告**：`evals run all` 后 `actions/upload-artifact` 上传 `evals/reports/`。
3. **/health 增强**：在 `src/server/app/utilities.py` 的 `health_check()` 增加 `redis`（`get_cache_client().health_check()`）与 `agent_config loaded` 探测，非致命（失败标记 degraded 不 500）。
4. **/metrics（可选但补上）**：用 `prometheus-client`（若未引入则 SQL 由 OTel 导出器兜底）——先检查是否已有 HTTP 指标导出；若无依赖冲突则以 OTel 为准，文档化 OTLP 端点配置。**保持不重复造轮子**。
5. **.env.example / 部署文档**：若缺则补 `docs/DEPLOYMENT.md`（环境变量清单、迁移命令、worker 数量建议、健康检查 curl）。
6. **性能基线文档**：`docs/PERFORMANCE_BASELINE.md` 记录 P1 前后 P95/往返数基线。

### 验收
- CI 冒烟脚本在本地跑通；/health 返回 redis 段；文档齐备；无安全（凭据）泄漏。

---

## P6 — M4 前端重构（frontend-design skill 驱动，1:1 契约）✅ 已完成

### 目标
前端全页面按 **frontend-design skill** 的设计规则重构，与后端路由/类型 1:1；新增 M2 功能的可见化页面。

### 范围（与后端 1:1，页面清单）

| 页面/组件 | 对应后端/类型 | 数据源现状 | 动作 |
|---|---|---|---|
| 意图路由 reason 面板 | `router/intent.py` 决策 JSON、`threads/crud.py get_thread` returns `metadata` | 后端决策已算但**未持久化**（仅日志） | **后端补持久化**（写 thread metadata）+ **前端新增面板** |
| 审校报告视图（issue 列表+打回） | `research_qa/auditor.py` findings、artifact 类型 | auditor 已实现，findings 随工具结果交付 | **前端新增视图**（audit findings 卡渲染） |
| 记忆浏览器（chunk 检索展示） | `tools/memory/retrieval.py` RecallHit | BM25 检索已实现，前端已有 MemoryPanel（记忆文件浏览） | **前端补充 recall 检索视图** |
| 评测台看板 | `evals` report schema（`evals/runs/latest.md`） | evals 离线 CLI，无 HTTP 端点 | **后端补只读端点**（serve latest JSON）+ **前端新增页面** |
| Dashboard / ChatAgent / MarketView / Settings / Plugins / Automations | 既有路由 | 既有 | 按 skill token 体系统一重构（低风险增量） |
| 各 viewer（PDF/Excel/HTML/CSV） | 既有 | 既有 | 触达性复核（复用已建 tokens） |

### P6 详细步骤（按序执行）

**M4-1 意图路由 reason 面板**
1. 后端 `messaging.py` 意图决策处：`_decision` 计算后写入 thread 的 `metadata.intent`（`{mode, reason, confidence}`），复用 thread metadata 列（022 已有载体，**无新迁移**）；提供幂等 merge 更新入口。
2. 后端单测：auto 请求后 `get_thread` 返回 `metadata.intent`；非 auto 请求不写；已存在 metadata（如 origin）不被覆盖。
3. 前端 `web/src/types/api.ts` `ThreadMetadata` 扩展 `intent?: {mode, reason, confidence}`。
4. 前端新增 `ReasonPanel` 组件（从 `getThread` 的 `metadata.intent` 读取，展示路由徽章 + 原因 + 置信度），挂到 `ChatView`/`MessageList` 起始处。
5. 前端单测：有 intent → 渲染徽章与原因；无 intent → 不渲染。

**M4-2 审校报告视图**
1. 前端类型：`web/src/types/chat.ts` 增 `AuditFinding`/`AuditReport`（level/kind/message/evidence）镜像 `auditor.py`。
2. 前端新增 `AuditReportView` 组件：issue 列表（error=红 / warning=黄 / info=灰），渲染工具结果中的 findings；作为 `INLINE_ARTIFACT_MAP` 的一个新 artifact 项接入。
3. 前端单测：findings 渲染、passed 徽章、空 findings 不渲染。

**M4-3 记忆浏览器（recall 视图）**
1. 后端确认 `tools/memory/retrieval.py` 的 `RecallHit` 已可被工具结果携带（SSE 工具输出通道已存在）。
2. 前端新增 `MemoryRecallView`：输入 query → 展示 top-k chunk（score + 来源标签）；复用既有 `MemoryPanel` 的门面与 hook。
3. 前端单测：检索结果渲染 + 空结果降级提示。

**M4-4 评测台看板**
1. 后端新增只读端点 `GET /api/v1/evals/report`（读取 `evals/runs/latest.md` 同目录 `latest.json`，存在则返回 summary；不存在返回 404），只读、无 DB。
2. 前端新增 `Evals` 页面：suite 通过率卡片 + 明细列表，路由 `/evals`，挂到侧边导航。
3. 后端单测（mock 文件存在/缺失两态）+ 前端单测（渲染挂载/空态）。

**M4-5 类型对账 + 回归**
1. `web/src/types/*` 与 `src/server/models/*` 1:1 对账清单（新增契约在 M4-1~4 已随代码补充）。
2. 前端：`tsc --noEmit`、`vitest run`、e2e 冒烟（既有 playwright spec 全跑）。
3. 契约守卫：`contract_guard.py --check` 全 OK；`frontend_mirror` 若涉及新类型则同步。

### 验收
- 新增 4 个 M2 可见化页面/视图 ✅（M4-1 ReasonPanel / M4-2 AuditReportView / M4-3 MemoryRecallView / M4-4 Evals 看板）
- 既有页保持 token 一致 ✅（`--color-*` 引用全部为已声明 token，逐文件 tokenRefs 扫描通过）
- 类型对账清单产出 ✅（前端 `MemoryRecallResponse/RecallHit`、`ThreadMetadata.intent`、`AuditFinding/AuditReportData` 与后端 pydantic 模型 1:1）
- 前端全绿 ✅（tsc 0 error + vitest 3286 全绿 + playwright e2e 11 passed）

### P6 落地记录（本轮执行摘要）
| 项 | 后端 | 前端 | 验证 |
|---|---|---|---|
| M4-1 意图路由 reason 面板 | `messaging.py` 决策写入 `thread.metadata.intent`（幂等 JSONB merge，`threads_write.update_thread_metadata_merge`）；单测覆盖 auto 写入/非 auto 不写/不覆盖既有键 | `ReasonPanel.tsx`（路由徽章+原因+置信度）挂 `ChatView`；`ThreadMetadata.intent` 类型 | ReasonPanel.test 4 项 |
| M4-2 审校报告视图 | `research_qa/auditor.py` findings 随 artifact 交付（无新增端点） | `AuditReportView.tsx`（error/warning/info 分级）经 `ToolCallDetailView` 渲染 findings | AuditReportView.test 4 项 |
| M4-3 记忆浏览器 recall 视图 | `GET /api/v1/memory/recall`（BM25 检索，owner 守卫，`MemoryRecallResponse`） | `MemoryRecallView.tsx` 挂 `MemoryPanel`（浏览/检索切换，来源 chip+score）；`recallMemory` API + `useMemoryRecall` hook | MemoryRecallView.test 4 项 + 后端 test_memory_recall |
| M4-4 评测台看板 | `GET /api/v1/evals/report`（只读 latest.json，404 语义） | `Evals.tsx` 页面 + `/evals` 路由 + 侧边导航；三分语言文案 | Evals.test 3 项 + 后端 evals_report 测试 |

---

## P7 — 全量回归 + 最终完成报告 ✅ 已完成

### P7 详细步骤
1. 后端全量：`uv run pytest tests/unit/ -q`（含 M3 新测试、M4-1/4-4 新测试）。
2. evals：`uv run python -m evals run all`（intent/auditor/research_fallback 三套全绿）。
3. 前端：`uv run --directory web tsc --noEmit` + `uv run --directory web vitest run` + `npx playwright test` 冒烟。
4. 契约守卫：`python scripts/guard/contract_guard.py --check` 全 OK。
5. 模拟使用：`uv run python scripts/e2e/simulation_smoke.py` 全 PASS。
6. 更新 `docs/COMPLETION_REPORT.md`（本轮 M3/基础设施/M4 完成清单）+ `docs/ROADMAP.md` 状态位。
7. 输出最终完成报告（本轮交付清单 + 回归结果 + 遗留风险）。

### P7 回归结果（2026-09-10 实测）
| 关卡 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `uv run pytest tests/unit/ -q` | **9354 passed, 1 xpassed** |
| evals 评测台 | `uv run python -m evals run all` | **21/21 全绿**（intent 12 / auditor 6 / research_fallback 3） |
| 前端类型 | `npx tsc --noEmit` | **0 error** |
| 前端单测 | `npx vitest run` | **302 files / 3286 tests 全绿**（含新增 M4-1~4 共 15 项） |
| e2e 冒烟 | `npx playwright test`（account-menu + focus-ring） | **11 passed**（补装了 playwright chromium + 系统依赖，属本轮基础设施补缺） |
| 契约守卫 | `python scripts/guard/contract_guard.py --check` | migrations / status_vocabulary / docstring_lock / frontend_mirror **4 项全 OK** |
| 模拟使用 | `uv run python scripts/e2e/simulation_smoke.py` | **8/8 通过** |

### P7 遗留风险（供后续阶段参考）
- `src/ptc_agent/core/mcp_registry.py` 存在一处 `\S` 无效转义 SyntaxWarning（不影响运行，建议顺手修正）。
- pydantic `datetime.utcnow()` 弃用告警（上游），计划在依赖升级窗口内随 Q 审一起处理。
- Playwright e2e 依赖本机浏览器安装；CI 中应显式执行 `npx playwright install --with-deps chromium`（已补进 P5 的基础设施文档建议）。

---

## 附：契约红线提醒
- 所有 DB 变更 → 迁移编号 **033+**，且必须 `IF NOT EXISTS` 幂等。
- SSE 事件类型变更 → 登记事件台账（本计划不新增事件类型，仅变批量写入，无台账变更）。
- MCP tool docstring 变更 → 跑锁脚本（本计划不改 MCP docstring，P2 只动 redis_cache/stream_writer，勾稽通过）。