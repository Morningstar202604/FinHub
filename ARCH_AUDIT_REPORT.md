# FinHub 架构深度诊断报告

审计范围：`src/` 636 文件 / 185,082 行。方法：AST 全量扫描（函数级 import、异常处理、模块级全局）、grimp 依赖图 + Tarjan SCC、逐点人工复核。所有数字为实测，非推测。

---

## Critical

### C1. 分层被 944 处函数级 import 反向掩盖，实为结构性循环

> **本节的实测数字已复核修正（2026-09-14）**。初版写的是「915 处 / 647 模块 / 17 对双向耦合」，重新实测后为 **944 处 / 644 模块 / 6 对**。差异原因：初版把 `config<->llms`、`config<->data_client` 也算作双向，但源码里只有 `llms -> config` 和 `data_client -> config` 单向。复核方法见 `scripts/guard/layering_guard.py`（AST 全量扫描，含函数级 import）。

**问题**：包间存在 **6 对双向耦合**，但**顶层 import 环路为 0**（grimp/Tarjan 实测，641 模块 SCC 无 >1 者）。即：所有循环都靠"把 import 塞进函数体"来绕过 Python 导入期。这是设计缺陷被刻意补贴的典型形态——`grimp` 与 `import-linter` 的默认视图都报告 **0 对耦合**，因为它们只看得见模块级 import。

**证据**：
- 函数级 import 总数 **944**（AST 实测），分布：`server=673`、`ptc_agent=110`、`tools=65`、`observability=29`、`data_client=26`、`llms=22`、`utils=13`、`config=4`、`market_protocol=2`。热点 `src/server/app/setup.py`（55 处）、`src/server/app/threads/messaging.py`（47 处）。
- 双向耦合对（实测 6 组）：
  - **`server <-> tools`（关键）**：`server -> tools` 16 处，`tools -> server` **33** 处。`tools` 是能力层，却 import `server` 的 DB/service，方向倒置：
    - `src/tools/secretary/tools.py:190` `from src.server.services.workspace_manager import WorkspaceManager`（在函数体内）
    - `src/tools/user_profile/tools.py:21-26` 顶层直连 `server.database.{user,watchlist,portfolio}`、`server.services.onboarding`
    - 反向：`src/server/app/memory.py:181` `from src.tools.memory.retrieval import build_chunks, recall`
  - `observability -> server` 1 处 / `server -> observability` 16 处
  - `config -> utils` 1 处 / `utils -> config` 4 处
  - `tools <-> utils`、`server <-> observability`、`utils <-> observability`
  - `src/utils/tracking/infrastructure_costs.py:74` `from src.tools.web.manifest import ...`（工具层元数据被 utils 反依赖）
  - `src/observability/redis_pool_callbacks.py:25` `from src.server.services.workspace_status_pubsub import peek_status_pubsub_pool`

**影响**：导入顺序脆弱，任何一次静态化重构都可能触发运行时 `ImportError`；测试无法按包隔离加载；`mypy --strict` 类工具失效。

**修复（进行中）**：
1. ✅ **已冻结**：`scripts/guard/layering_guard.py` 以 ratchet 形式把 13 条 `server -> tools` 链条锁死——新增即 fail，修好未删条目也 fail。已接入 CI `lint` job。
2. ✅ **已修 5 条**：`Timeframe` 迁到 `market_protocol.intervals`；web provider manifest 迁到 `config.web_manifest`。`server -> tools` 从 14 条降至 **9 条**。
3. ⏳ **剩余 9 条**：`tools.guardrails.pii`（2 处，宜下沉 utils）、`tools.decorators`（2 处）、`tools.guardrails`（2 处）、`tools.web.fetch`、`tools.market_data.company`、`tools.memory.retrieval`。按"修一条删一条"推进。
4. ⏳ **反向（`tools -> server` 33 处）未动**：把 `tools` 需要的 workspace/thread 能力抽为 `src/core/ports`（Protocol + DI 注入），`tools` 只依赖端口。这是 C1 的主体工作量。
5. ⏳ `utils/observability` 不得依赖 `tools`（manifest 已解决；`infrastructure_costs` 已随之清理）。


---

## High

### H1. 上帝模块 `workspace_manager.py`（3670 行 / 74 方法 / 单类）
**问题**：单类 `WorkspaceManager` 承担 **≥8 类职责**，是服务端耦合中心（其被测试 mock 引用 **197 次**，全仓第一）。

**证据** `src/server/services/workspace_manager.py`：import 源跨 38 个模块，职责混杂：
- 会话缓存与锁：`_sessions`(L107)、`_workspace_locks`(L120)、`_phase2_events`(L130)
- 沙箱生命周期：`_provision_sandbox_session`(L977)、`_recover_sandbox`(L1114)、`_maybe_migrate_sandbox`(L1408)
- 文件备份/恢复：`_backup_files_to_db`(L1162)、`_restore_files`(L1318)
- 密钥注入：`_apply_session_platform_secret`(L441)、`push_vault_secrets`(L484)、`_mint_sandbox_tokens`(L530)
- MCP 装配/发现：`_apply_session_mcp`(L572)、`_kick_mcp_discovery`(L745)
- Skill 同步：`_sync_sandbox_assets`(L847)、`_reconcile_skills`(L1705)
- 资源治理：`cleanup_idle_workspaces`(L3482)、`reap_stuck_starting_workspaces`(L3542)
- 进程内状态：`get_stats`(L3663)

**影响**：任何沙箱/权限/文件改动都要改这个文件，回归面 = 全平台；单文件 import 时依赖 38 个模块，抬高高频路径冷启动成本。
**修复**：按生命周期拆为 `SessionRegistry`（缓存+锁+phase2）、`SandboxProvisioner`（provision/recover/migrate）、`WorkspaceSecretInjector`、`WorkspaceReaper`（cleanup/reap）；`WorkspaceManager` 退化为门面（<300 行）。

### H2. 未持强引用的 `create_task` 可被 GC 回收
**问题**：`asyncio` 对 task 仅持弱引用；下列 `create_task` 返回值未存入任何容器，事件循环可能在协程完成前回收 task（CPython 已知语义）。

**证据**（均为实测调用点，返回值被丢弃）：
- `src/ptc_agent/agent/middleware/workspace_context.py:130` `asyncio.create_task(self._sync_front_matter_to_db(...))` — 注释自称 "Fire-and-forget"，但**无 anchor**；对照同仓正确写法 `src/server/app/threads/_deps.py:23 _track_task()` 持有集合。
- `src/server/handlers/automation_handler.py:338` `asyncio.create_task(executor.execute(...))` — 返回丢弃，自动化执行可能静默不执行。
- `src/server/services/price_monitor.py:414` 同上，价格监控触发丢失。
- `src/server/services/thread_mutation.py:189` `asyncio.create_task(_delete(), ...)` — Redis 键清理丢失导致残留。
- 正确反例（证明团队知道该模式）：`subagent_collection.py:780` 用 `_retain_collector()`、`messaging.py:717/849` 用 `_track_task()`。

**影响**：间歇性"任务没跑/回调没发/键没删"，低负载难复现，高负载随机丢。
**修复**：统一走 `create_task_with_context()`（`src/observability/tracing.py:187` 已有），并强制加入 anchor `set` + `add_done_callback(discard)`。

### H3. 配置在 import 期冻结 + 装饰性开关
**问题**：(a) 部分配置在模块导入时求值一次，运行期不可变；(b) 存在读取但**从不影响行为**的开关。

**证据**：
- import 冻结：`src/server/services/runs/sse_producer.py:43-46` `WORKFLOW_TIMEOUT = get_workflow_timeout()`、`SSE_EVENT_LOG_ENABLED = is_sse_event_log_enabled()`（L1826 消费）；`src/server/app/workspaces.py:273` `_EVENTS_KEEPALIVE_S = get_sse_keepalive_interval()`。
- 装饰性开关（全仓 0 消费点）：
  - `get_debug_mode()` `src/config/settings.py:48` ← `config.yaml:17 debug: false`，无任何调用者。
  - `is_result_log_db_enabled()` `src/config/settings.py:98` ← `config.yaml:26 result_log_db_enabled: true`，无调用者。
  - `is_cache_invalidate_on_write_enabled()` `src/config/settings.py:391`，无调用者。
- 死 getter **9/64**：`get_debug_mode`、`get_redis_ttl_results_list`、`get_redis_ttl_result_detail`、`get_redis_ttl_metadata`、`get_redis_ttl_metadata_summary`、`get_redis_ttl_workflow_status`、`get_redis_ttl_cancel_flag`、`get_subagent_task_max_wait`、`get_in_memory_event_tail_max_events`（均 AST 实测，无 `getattr` 动态引用）。
- 环境变量读取散落 **173 处**（`os.getenv/os.environ`），跨 20+ 目录，未收敛。

**影响**：运维改 `.env`/`config.yaml` 不生效（以为调了其实没读），排障误导；TTL 参数看似可调实则写死。
**修复**：删除 3 个装饰开关与 3 个死 TTL getter（或接入调用点）；把 import 冻结改为请求期读取（函数内调用 getter）；env 读取统一走 `src/config/env.py`。

### H4. 42 处路由直接把内部异常原文回传客户端，脱敏器形同虚设
**问题**：仓内已有脱敏器 `src/server/utils/error_sanitization.py`（`sanitize_error_text` / `single_line`），但路由层 `HTTPException(detail=str(e))` 全部绕过它。

**证据**：
- 泄漏点 **42 个，带 sanitize 的 0 个**（实测）。典型：
  - `src/server/app/cache.py:44` `detail=f"Failed to retrieve cache stats: {str(e)}"`
  - `src/server/app/market_data.py:258/282/335/455/534/587/683/839` 连号泄漏，含 `str(e)`
  - `src/server/app/mcp_servers.py:399/512/599`、`skills.py` 多处 `detail=str(e)`
- 对照正确用法：`src/server/app/api_keys.py:583` `msg = _sanitize_error(str(e))`；`src/server/app/public.py:441` `single_line(str(e))`（新代码已用，老代码未回填）。
- 风险面：`str(e)` 可含 psycopg 连接串（DSN 带口令）、SQL 片段、内网 host，直接进入客户端响应体。

**影响**：信息泄露（DSN/表结构/内网拓扑），可被用于进一步攻击；与已有安全设计自相矛盾。
**修复**：在 `setup.py` 注册全局 `exception_handler`，对所有 5xx `detail` 强制过 `sanitize_error_text(single_line(...))`；批量替换 42 处；CI 加正则禁止 `detail=str(e)`（`detail=f"...{str(e)}"`）。

### H5. 210 处异常被静默吞噬（无日志、无 raise）
**问题**：`except Exception` 共 **1208** 处，其中 **210 处** body 仅 `pass`/`continue` 且无任何日志或重抛（AST 实测）。

**证据**：热点 `src/ptc_agent/core/sandbox/mcp_client_runtime.py`(6)、`src/server/services/runs/recovery.py`(6)、`src/server/services/price_monitor.py`(5)、`src/server/services/thread_mutation.py`(5)、`src/server/services/workspace_status_pubsub.py`(5)。样例：
- `src/ptc_agent/agent/middleware/background_subagent/registry.py:733/824/1140` 三处静默
- `src/server/database/user.py:3 处`、`src/server/database/api_keys.py:3 处`（DB 层吞异常最危险）
- 裸 `except:` **2 处**：`src/data_client/yfinance/financial_source.py:34`、`src/observability/tracing.py:85`

**影响**：故障无痕；DB 写失败被吞导致状态不一致且无告警；可观测性自吞噬（`tracing.py` 内 `except: pass`）。
**修复**：DB/可观测层禁止静默；统一 `except Exception: logger.exception(...)` 或 `contextlib.suppress` 显式声明；CI 规则：`except` body 纯 `pass` 且无 log 即 fail（允许白名单加注释豁免）。

---

## Medium

### M1. 抽象泄漏：service/utils 层直写 SQL 与 Redis
**问题**：DB 访问本应收敛在 `src/server/database/`，但 `services/` 与 `utils/` 存在裸 SQL；Redis 客户端也在 service 层裸用。

**证据**：
- 裸 SQL（非 database/）：
  - `src/server/utils/checkpoint_retention.py:142/149/167` `DELETE FROM checkpoint_writes`/`DELETE FROM checkpoints`/`DELETE FROM checkpoint_blobs`（含连表 SELECT）
  - `src/server/services/writer_guard.py:119-124/158/395/487/577/620/690` 直连 `pg_locks`/`pg_advisory_*`，import `psycopg`/`AsyncConnectionPool`（L23-25）
  - `src/server/services/user_data_io.py:310/353/378/390/411/438` 裸 `SELECT ... FROM watchlist...` + `pg_advisory_xact_lock`
  - `src/server/services/thread_mutation.py:405/442` `pg_advisory_unlock`/`pg_try_advisory_lock`
  - `src/server/app/setup.py` 出现在含 SQL 关键字文件列表中
- 裸 Redis（非 utils/cache）：`src/server/services/stream_retention_sweep.py:175/181/183/342` 直接 `client.set(... nx=True, ex=...)`/`client.get` 做租约；`src/server/services/workspace_status_pubsub.py:79/86/168` 自建 `ConnectionPool.from_url` + `client.publish`；`src/ptc_agent/.../background_subagent/redis_stream.py` 同。共 **11 个文件**直接 `import redis`。

**影响**：连接池、键命名、TTL 策略分散，无法统一管控（如连接数、键前缀迁移）；advisory lock 语义散落。
**修复**：`checkpoint_retention`/`writer_guard`/`user_data_io` 的 SQL 下沉到 `database/`；Redis 租约/发布收敛到 `utils/cache` 端口（`peek_*_pool` 已有，service 不应自建池）。

### M2. `_workspace_locks` 无淘汰，随 workspace 数无限增长
**问题**：`WorkspaceManager._workspace_locks: Dict[str, asyncio.Lock]` 按需创建且**从不删除**。

**证据** `src/server/services/workspace_manager.py`：L120 定义；L189-191 懒创建 `self._workspace_locks[workspace_id] = asyncio.Lock()`；全文件 `pop`/`del` 计数 **0**（实测）。对照 `_phase2_events` 有 3 处 pop、`_sessions` 多处 pop——同族字段清理策略不一致。
**影响**：多租户长期运行下锁表单调增长（每 workspace 一个 Lock 对象常驻）。
**修复**：锁用 `WeakValueDictionary`，或在 `retire/delete_workspace` 时 pop；与 `_sessions` 清理对齐。

### M3. 进程内缓存无淘汰 + 多 worker 语义错误
**问题**：多处模块级 dict 以 user/workspace 为键、仅"读时过期"、不清死键；且部分"全局"状态实为进程内，多 worker 下语义错误。

**证据**：
- `src/server/dependencies/usage_limits.py:487` `_scope_cache: dict[str, tuple[...]] = {}`，L503 读、L513 写；**无任何淘汰/删除**，仅过期时间戳——用户 ID 数增长即内存无界。
- `src/server/app/news.py:38` `_inflight` 靠 done_callback pop（有界，属良性）；对照 `usage_limits` 无此机制。
- 多 worker 语义：`src/server/services/workspace_entitlements.py:307` 注释自认"the lock above is a per-process asyncio.Lock"，靠 DB claim `try_claim_workspace_for_replacement` 兜底——**说明进程内锁在多 worker 下不可信**，同类模式若漏兜底即 race。`WorkspaceManager` 的 `_sessions/_phase2_events/_last_sync_at/_pending_lazy_sync` 全为进程内单例状态（`src/server/services/workspace_manager.py:70` 类 docstring 自述 "owns in-process session cache"），`writer_guard.py:14` 注释 "single worker only"。
**影响**：内存缓慢泄漏；`--workers N>1` 时 warm/phase2 去重、空闲回收、entitlement 判定都可能重复执行或漏判。
**修复**：`_scope_cache` 换 LRU（`functools.lru_cache(maxsize=N)` 或带淘汰 dict）；进程内单例状态显式声明"每 worker 一份"，跨 worker 一致性依赖 Redis/DB（已有 `news.py` 双锁范式可复用）；部署文档明确单 worker 约束或提供分布式锁。

### M4. 测试与生产实现强耦合 + 生产代码残留测试钩子
**问题**：测试直接读写生产私有字段、mock 私有方法；生产代码保留仅测试用的 reset/normalize 入口。

**证据**：
- mock 生产模块内部 Top：`src.server.services.workspace_manager`(**197**)、`src.server.app.mcp_servers`(167)、`src.server.app.setup`(85)、`src.llms.llm.LLM`(73)、`src.server.services.workspace_entitlements`(57)。
- 直接操作私有字段：`tests/unit/server/services/test_workspace_manager.py:155/169/217` 直写 `wm._sessions[...]`；`tests/integration/test_message_hot_path.py:359` 写 `workspace_manager._last_sync_at[ws_id]`；`tests/unit/core/sandbox/test_mcp_stdio_reply_bounds.py:269/304` 操作 `m._server_processes`。
- mock 私有方法：`._run_flash_agent`(6)、`._push_vault_to_sandbox`(6)、`._cache`(13)、`._fmp_available`(5) 等。
- 生产代码测试钩子：`src/observability/otel.py:300 reset_for_tests()`、`src/utils/storage/s3_compatible.py:140 _reset_client_for_test()`，及 6 个 `reset_instance()`（`workspace_manager.py:182`、`session_manager.py:84`、`stream_retention_sweep.py:112` 等）——调用方 **全在 tests/**（实测：57+15+14+6+2+2+2 次），生产零调用。
- 无 `if TESTING`/`os.getenv("PYTEST")` 类生产分支（实测 0），这点是好的。

**影响**：重构 `_sessions`/`_server_processes` 等结构就会打挂大量测试（测试锁死实现而非行为）；测试钩子污染生产 API 面。
**修复**：测试改为通过 public API（`get_stats/has_ready_session`）断言行为；`reset_instance` 移入 `tests/conftest.py` 的 fixture（用 `monkeypatch.setattr`）或标注 `# test-only` 并收入 `src/_testing`；对私有字段注入提供显式构造参数/依赖注入替代。

---

## Low

### L1. 三处 `time.sleep` 位于可能被 async 调用的路径
**证据**：`src/ptc_agent/agent/middleware/model_resilience.py:328`（**同步孪生** `wrap_model_call`，L305 注释自认 "Unused in production... time.sleep here would stall an event loop" —— 已知且可控，降为 Low）；`src/ptc_agent/core/sandbox/mcp_client_runtime.py:383`、`skill_sync.py:105` 为 `time.sleep(0.2)` 重试，若被 async 路径调用会阻塞事件循环 200ms。
**修复**：确认后两处调用方均非 async；否则改 `await asyncio.sleep`。

### L2. 93 处 `asyncio.gather` 中多数未用 `return_exceptions`
**证据**：`asyncio.gather(` 共 93 处，未带 `return_exceptions` 的包括 `data_client/finhub_data/news_source.py:113`、`ptc_agent/agent/graph.py:27/146/202`（L27 携 `portfolio_count, watchlist_counts, prefs_set` 解包，任一失败即整体抛且其余结果丢弃）。
**影响**：单个子任务失败使整批结果丢失，且已成功的 IO 浪费。
**修复**：对"部分可用"语义的批处理补 `return_exceptions=True` + 逐项降级。

---

## 汇总

| 级别 | 条目 | 一句话 | 状态 |
|---|---|---|---|
| Critical | C1 | 944 函数级 import 掩盖 6 对包双向耦合；`server <-> tools` 16:33 | 🔶 已冻结+修 5/14 |
| High | H1 | `workspace_manager.py` 3670 行 8 职责上帝类（被 mock 197 次） | ⏳ 未动 |
| High | H2 | 5 处 `create_task` 无强引用，任务可被 GC | ⏳ 未动（活跃 bug，建议优先） |
| High | H3 | import 期冻结配置 + 3 装饰开关 + 9 死 getter + 173 处散落 env | ⏳ 未动 |
| High | H4 | 42 处路由 `detail=str(e)` 泄漏内部异常，脱敏器未接入 | ⏳ 未动 |
| High | H5 | 1208 `except Exception`，210 处静默吞噬 | ⏳ 未动 |
| Medium | M1 | service/utils 层裸 SQL（advisory lock、checkpoint 清理）与裸 Redis | ⏳ 未动 |
| Medium | M2 | `_workspace_locks` 无淘汰 | ⏳ 未动 |
| Medium | M3 | `_scope_cache` 无界；进程内单例多 worker 语义错误 | ⏳ 未动 |
| Medium | M4 | 测试直写生产私有字段；7 处生产测试钩子 | ⏳ 未动 |
| Low | L1/L2 | 3 处 `time.sleep`；93 处 gather 多数无 `return_exceptions` | ⏳ 未动 |

**汇总表状态图例**：🔶 进行中 ｜ ✅ 已完成 ｜ ⏳ 未动。

---

## 附：契约守卫

`scripts/guard/layering_guard.py`（本次新增，stdlib-only、离线、退出码即信号）以 ratchet 方式守护 `server -> tools` 反向依赖：

```bash
python scripts/guard/layering_guard.py            # 检查（CI 用，违规 exit 1）
python scripts/guard/layering_guard.py --list     # 列出全部观测链条并标记 NEW
python scripts/guard/layering_guard.py --json     # 机器可读
```

三种失败模式：**新反向依赖**、**已冻结链条被修好但条目未删**（STALE）、**已修复链条回归**。因此 `_FROZEN` 只能缩不能涨，修好一条会被强制认领。当前 **9 条观测 / 9 条冻结**（起点 14 条）。

`scripts/guard/contract_guard.py` 此前仅存在于 `docs/ROADMAP.md` 与 `docs/DEPLOYMENT.md` 的描述中，**从未真正接入 CI**；本次一并加入 `.github/workflows/test.yml` 的 `lint` job。

