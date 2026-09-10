# FinHub 性能基线（M3 记录）

> 这份文档记录 M3 性能工程的前后基线,供后续回归对比。所有测试均在本仓库标准测试环境下执行;数字是**刻画值**不是承诺——单机环境、Redis/DB 负载都会改变绝对值,关注**相对变化**。

---

## 1. SSE 事件批量刷盘（M3-A）

### 改动前
- 每条 SSE 帧 → `stream_append_with_retry` → 单次 `XADD`,网络往返 **N 次/N 帧**。
- `executor.consume_workflow` 逐条 await,低吞吐场景每帧都有一次 Redis 往返延迟。

### 改动后
- `executor` 攒批:**32 帧**或 **50ms** 停顿触发一次 flush → `buffer_events_many` → `stream_append_many_with_retry` → `pipelined_event_buffer_many`(单 pipeline 内多条 XADD)。
- `StreamEventAccumulator` 质保不变(相邻 chunk 已在内存合并),批量只是传输层合并。

### 基线（本机,128 帧,无真实 Redis —— 单元形状 + `scripts/perf/event_write_smoke`）

| 指标 | 改动前 | 改动后 |
|---|---|---|
| XADD 网络往返 | 128（逐条） | 1（一次 pipeline） |
| 批写 wall-clock | — | ~14 ms（128 帧） |

### 回归护栏
- `uv run python -m scripts.perf.event_write_smoke`：断言 128 帧 = 1 次 pipeline 调用,耗时 ≤1s。CI 已挂 performance-smoke job。

---

## 2. Redis pipeline 批量写收敛（M3-C）

| 路径 | 改动前 | 改动后 |
|---|---|---|
| `set_many` | 已是单 pipeline ✅ | 不变 |
| `delete_pattern` | SCAN 循环内逐条 `delete`（O(N) 往返） | SCAN + 每 100 key 一个 pipeline delete（O(N/100) 往返） |
| 事件写 | 逐条 XADD（见 §1） | 批量 pipeline |

---

## 3. 索引审计（M3-B）

审计全部 32 个既有迁移 + 运行时查询路径（`research_loop.py` / `automation.py` / `lifecycle.py` / `outbox.py` / `subagent_runs.py` / `provenance_bodies.py`）：

| 表 | 查询 | 结论 |
|---|---|---|
| `conversation_responses` | 按 thread_id + status='in_progress' | ✅ 已有 `uq_responses_in_progress_slot`（部分索引直接覆盖） |
| `hook_outbox` | done 最近/terminal 年龄/run/thread | ✅ 019 已覆盖 |
| `subagent_runs` | thread_task / open / predecessor | ✅ 020 已覆盖 |
| `provenance_records` | thread / response / sha | ✅ 013/015 已覆盖 |
| `research_loops` | user+status 过滤 + updated_at 排序 | ⚠️ 缺复合 → **033** `(user_id, status, updated_at DESC)` |
| `automation_executions` | automation_id + created_at DESC 分页 | ⚠️ 缺复合 → **033** `(automation_id, created_at DESC)` |

附尾迁移 `migrations/versions/033_index_audit_tail.py` 已建,`contract_guard --check` 4 项全绿。

---

## 4. 沙箱预热（M3-D）

- 改动前:启动只预热 Redis 缓存(`redis_warm_on_startup`)与 prebuilt workflows;always-on 沙箱的冷启动全部落在用户首次消息。
- 改动后:启动 30s 后 `prewarm_sessions()` 拉取 `running + is_always_on` 的 workspace,后台走 `get_session_for_workspace`(含 ensure_sandbox_ready / asset sync / file restore),失败静默降级回惰性冷启动。
- 观测:`session_path_counter{path="prewarm"}` 计入预热路径。

---

## 5. 如何为本文档补充新基线

1. 用 `scripts/perf/event_write_smoke.py` 作为性能 smoke 模板;新性能项仿照「指标/改动前/改动后/回归护栏」四段。
2. 任何锁定依赖升级(见 [DEPENDENCY_REVIEW](./DEPENDENCY_REVIEW.md))后必须重跑 §1 smoke 与全量回归。