# FinHub 部署与运维手册（基础设施补缺）

> 面向自部署/生产运维,补齐 README 未覆盖的运维面:迁移、健康检查、worker 规模、日志、Redis 事件流语义。

---

## 1. 环境与启动

环境变量清单见 `.env.example`(已有,按段填写)。启动方式:

```bash
# 开发
make dev                # uv run python server.py --reload(需本地 DB + Redis)

# Docker Compose(生产形态示例,见 docker-compose 配置)
docker compose up -d    # 启动 DB / Redis / backend / web
```

前置依赖:**PostgreSQL**(checkpointer + 业务表)、**Redis**(事件流 + 缓存 + 配额锁)。缺 Redis 时:事件流传输不可用 → 运行会以 `transport_lost` 失败(by design,I6);缓存功能降级;`/health` 报告 degraded。

---

## 2. 数据库迁移

- 执行:`make migrate`(= `uv run alembic upgrade head`)。所有迁移幂等(`IF NOT EXISTS`),最新 head 见 `migrations/versions/`(当前 **033**)。
- 契约:任何 schema 变更必须新增迁移(**编号 033+**),且先跑 `uv run python scripts/guard/contract_guard.py --check` 验证 migrations 台账。
- 回滚:`uv run alembic downgrade -1`(仅用于显式事故;迁移代码提供对应 downgrade)。
- 运维注意:迁移会持有 ACCESS EXCLUSIVE 锁(022/023 已含 `lock_timeout=5s` 防排队);大表加索引请评估窗口;`033` 为纯增索引,低风险。

---

## 3. 健康检查与存活语义

- `GET /health`(无版本前缀):
  - `status`:`healthy`(全绿)/ `degraded`(checkpointer 或 Redis 任一异常)/ 异常时 HTTP 500。
  - 附 `checkpointer` 池状态(连接池健康)、`redis` 状态(`healthy`/`unreachable`/`error`)。
  - 语义:**非致命探测**——Redis 短暂抖动只降级不 500,避免负载均衡器在抖动期把实例摘除再放回。
- 就绪建议:负载均衡探活用 `/health`(200 即存活);真正收流量前自行校验 `status == healthy` 更严格。

---

## 4. Worker 规模与并发

关键上限(config.yaml / env):

| 参数 | 位置 | 说明 |
|---|---|---|
| `background_execution.max_concurrent_workflows` | config.yaml | 默认 100,后台工作流上限 |
| `redis.max_connections` / `REDIS_POOL_TIMEOUT` | config / env | 缓存池;`set_many`/批量事件写走单连接 pipeline 防池耗尽 |
| `server.idle_timeout`(workspace) | WorkspaceManager | 默认 30 分钟,决定工作区闲置回收 |
| `sandbox.quotas`(可选) | agent_config.yaml | 每用户工作区/并行上限,超限 409 |

- 多 worker(`uvicorn --workers N`):事件消费者按 stream 各自读,生产者用**显式 event id + SETNX run_end gate** 保证不重复/不丢失;Redis `workflow:stream:{thread}:{run}` 流自动互斥。
- 建议:单机 2~4 worker + 独立 Redis;沙箱不动则工作区预热任务只在启动 worker 上跑一次(prewarm 幂等)。

---

## 5. 日志与观测

- 日志:结构化(根日志 `log_format` 配置于 config.yaml),模块分级(`module_log_levels` 已含 `yfinance: CRITICAL` 等压制)。
- 指标:OTel metrics(`src/observability/metrics.py` 约 20 个计数器/直方图,含 `session_path_counter`、`hot_path_first_chunk_duration_ms` 等),经 `OTEL_EXPORTER_OTLP_ENDPOINT` 导出(见 pyproject `observability` extra);本地无 /metrics 文本端点,按 OTLP 采集。
- 追踪:OTel tracing,`langsmith_tracing` 开关(config.yaml)。
- 事件日志:`sse_event_log_enabled`/`sse_event_log_level`(默认关闭,开启逐帧记 SSE,谨慎生产)。

---

## 6. Redis 事件流关键语义(排障必读)

- 每条 SSE 帧写入 `workflow:stream:{thread_id}:{run_id}`,id 为 `{seq}-0` 显式主键 → **可幂等重放、可精确尾探针**。
- `run_end` 帧:finalize CAS 提交**之后**由 SETNX gate 唯一写入,携带 adopted outcome;消费者据此关闭;失联时双空轮 handshake 兜底。
- 活跃流**无 TTL**,terminal 时统一 stamp（`redis_event_ttl`,默认 24h);MAXLEN = max_stored_messages × 2 兜底裁剪。
- 排障:`redis-cli XRANGE workflow:stream:<t>:<r> - + COUNT 5` 查看事件;`stream_tail` 判断最近写入。

---

## 7. CI/CD

- `.github/workflows/`:`test.yml`(unit + evals + perf smoke + integration + web/e2e/desktop)、`fork-integration.yml`(fork PR,评审门控)、`sandbox-integration.yml`、`release.yml`、`desktop-release.yml`、`sandbox-image.yml`。
- 本阶段新增:unit job 挂 `performance-smoke`(M3-A 批量形状断言)与 `evals-report` artifact。
- 门禁:全绿 = unit + evals + integration + web typecheck/vitest/build/e2e + desktop + contract_guard。