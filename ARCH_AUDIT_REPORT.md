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
**状态**：✅ 已修（2 处真实泄漏）+ 已建成 AST 棘轮守卫

**修正**：初版审计列了 5 处"返回值被丢弃"的调用点，**逐行复核后其中 3 处是误判** —— 它们早已有 anchor，只是写法不直观：

| 初版指认 | 复核结论 |
|---|---|
| `automation_handler.py:338` | ❌ 误判。实际调用的是 `spawn(...)`（L338 的 `asyncio.create_task` 只出现在注释里），本就有强引用 |
| `price_monitor.py:414` | ❌ 误判。行号漂移；真实的 L279/282/285 存入 `self._refresh_task` 等实例属性 |
| `thread_mutation.py:189` | ❌ 误判。同上，已用 `spawn()`，注释即写明 "spawn() rather than a bare create_task" |

真实泄漏是另外两处，且都是**返回值在下一行即失去作用域**的裸调用：

- `src/ptc_agent/agent/middleware/workspace_context.py:130` —— 注释自称 "Fire-and-forget"，但没有任何 anchor；`agent.md` 前置元数据同步可能静默不落库。
- `src/tools/web/inhouse/safe_wrapper.py:347` —— 浏览器孤儿进程回收；当前靠"单例长期存活"侥幸安全，但这是巧合而非保证。

**为何单靠注释修不掉**：该规则已在 `thread_mutation`、`insight_service`、`subagent_collection` 三处写成注释，仍被违反。散文无法执行，因此规则改为机械校验。

**实现**：`src/server/utils/task_tracking.py` 新增 AST 扫描器 `scan_unanchored_create_tasks()`，`tests/unit/server/utils/test_task_tracking.py` 将其固化为**棘轮**。扫描器判定"可证明已锚定"的五种形态：包进 `spawn/track_task` 等已知 helper；存入属性（`op.heartbeat = ...`）或模块级名字；存入局部变量且同函数内被 `await`；存入集合且该集合被 `await gather(*tasks)` 消费；作为参数交给未知调用。**不覆盖**裸表达式语句与"存了局部却从不 await"——后者如实上报为 unproven，不假装已检查。

棘轮的两条性质（均已实测验证会正确失败）：
- **新增**未证明锚定的站点 → 测试失败，加入需给出理由；
- **失效**的 `_FROZEN` 条目（记录在案却不再复现）→ 测试失败，迫使列表持续描述真相、只减不增。

**遗留**：`_FROZEN` 现存 26 条，均经复核确认安全（多为模块级 / 实例级集合，单函数视角看不见）。它们不是指控，而是"改动周边结构时需人工重读"的清单。

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

### H4. 路由把内部异常原文回传客户端
**状态**：✅ 已修 19 处 + 建成 AST 守卫

**修正**：初版审计的两条关键结论**都是反的**，逐行复核后更正：

| 初版说法 | 实测 |
|---|---|
| "泄漏点 42 个，带 sanitize 的 0 个" | ❌ 反了：**42 处已经用了 `sanitize_error_text`**，真正裸泄漏是另外 19 处 |
| "在 `setup.py` 注册全局 `exception_handler`" | ❌ 不可行：这些异常在**路由内部**就被 catch 并转成 `HTTPException` 了，全局 handler 永远等不到它们 |

**真实泄漏 19 处**，分三种拼写（这正是正则方案会漏的）：

- `detail=f"...{str(e)}"` —— 13 处（`cache.py`、`market_data.py`、`threads/crud.py`、`messaging.py`、`thread_maintenance.py`、`thread_status.py`）
- `detail=f"...{e}"` —— 6 处（`oauth.py`×2、`messaging.py`×2、`workspace_sandbox.py`、`steering.py`）。**这种拼写 `grep 'str(e)'` 完全抓不到**
- 手写响应体 —— 1 处：`utilities.py` 的 `/health`（**未鉴权端点**）返回 `{"error": str(e)}`，psycopg 失败会带出 host/port/库名
- 另 `plugins/probe.py` 两处走安装报告渲染到 UI

**一个不该漏的发现**：仓内 `handle_api_exceptions`（`src/server/utils/api.py:155`）**早就实现了正确行为**——ValueError→脱敏 409、Exception→通用 500 + 脱敏日志——导出在 `server.utils.__init__`，却**零采用者、零测试**。死抽象 + 无覆盖，是最危险的组合。已补 6 个测试固定其行为（含"DSN 进日志但不进响应"的双向断言）。

**关键判断：catch-all 不该只 sanitize，而应丢弃文本。**
`sanitize_error_text` 只挡凭证*形状*。把 `postgresql://user:pw@host` 脱敏后仍剩 `host`；psycopg 的表名、列名则**完全不受影响**。所以对 `except Exception` 分支，正确做法是丢文本、留动作——这也正是 `api.py` 从写下那天起就做的事，它旁边还留着注释 "Never `detail=str(e)` here"。注释没能拦住 19 处违规，所以规则改成可执行的。

**实现**：`scripts/guard/error_leak_guard.py`，按 **catch 的类型**区分而非拼写：
- `except Exception` / `except BaseException` / 裸 `except:` → 文本不得出网（**泄漏**）
- `except SomeDomainError` → 消息是本仓撰写、调用方需要读（**合法，不管**）

刻意不误报：logger 的 structlog 绑定不是 HTTP 字段；`e.response.status_code` 是 int 不是消息体；工具层 `return {"error": str(exc)}` 是给 LLM 读的（dict 检查**只作用于带路由装饰器的函数**）。已实测三种失败路径都会报错（注入 f-string 泄漏、注入 dict 泄漏、stale 豁免条目）。

**修复时的连带改进**：删掉 detail 文本会让服务端也看不到原因（滑向 H5 的静默失败），因此 6 处补了 `logger.warning/error`，异常文本留在它该在的地方。）。

### H5. 210 处异常被静默吞噬（无日志、无 raise）
**问题**：`except Exception` 共 **1208** 处，其中 **210 处** body 仅 `pass`/`continue` 且无任何日志或重抛（AST 实测）。

**证据**：热点 `src/ptc_agent/core/sandbox/mcp_client_runtime.py`(6)、`src/server/services/runs/recovery.py`(6)、`src/server/services/price_monitor.py`(5)、`src/server/services/thread_mutation.py`(5)、`src/server/services/workspace_status_pubsub.py`(5)。样例：
- `src/ptc_agent/agent/middleware/background_subagent/registry.py:733/824/1140` 三处静默
- `src/server/database/user.py:3 处`、`src/server/database/api_keys.py:3 处`（DB 层吞异常最危险）
- 裸 `except:` **2 处**：`src/data_client/yfinance/financial_source.py:34`、`src/observability/tracing.py:85`

**影响**：故障无痕；DB 写失败被吞导致状态不一致且无告警；可观测性自吞噬（`tracing.py` 内 `except: pass`）。
**修复**：DB/可观测层禁止静默；统一 `except Exception: logger.exception(...)` 或 `contextlib.suppress` 显式声明；CI 规则：`except` body 纯 `pass` 且无 log 即 fail（允许白名单加注释豁免）。
**进展（第五轮实测）**：严格口径复测为 **258** 处（原 210/125 两个数字均过期）。**DB 层 12 处已清零**（`bdd783b`）：旗标缓存（byok_active / oauth_active / user_prefs / thread 存在戳）绕过 get()/set() 直接打裸 `cache.client`，失败静默回退 DB——回退本身正确，但一个死 Redis 与健康 Redis 在观测上完全无差别。修复：`RedisCacheClient` 新增 `safe_get_raw/safe_set_raw/safe_delete`（保留原始字节语义，失败走 `_log_error` + `stats["errors"]`），12 处调用点全部转换，注入验证降级路径后恢复。

**services 层 75 处已完成甄别**（`8ff056e`）：逐文件归后只有一处真正的损失路径——`price_monitor.py` 的触发器配置解析失败后纯 `return`，用户的资金告警**永远不触发且无任何痕迹**，现以 error 级别记录 automation id 与解析堆栈（注入验证）。其余 74 处逐一看过语义：shutdown 路径（`hook_outbox`/`recovery` 的 stop 取消）、advisory unlock、lease 过期自愈（`stream_retention_sweep` 的注释明确解释了两 worker 抢锁风险如何自愈）、SSE 帧解析容错、best-effort wake——静默是这些位置的设计语义，改成 error 级日志只会制造噪音；它们进入后续批次按 debug 级补记。

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
| High | H2 | `create_task` 无强引用，任务可被 GC | ✅ 已修 2 处 + AST 棘轮守卫（初版 5 处指认中 3 处系误判，已更正） |
| High | H3 | import 期冻结配置 + 3 装饰开关 + 9 死 getter + 173 处散落 env | ⏳ 未动 |
| High | H4 | 路由 `detail` 泄漏内部异常原文 | ✅ 已修 19 处 + AST 守卫（初版"42 处未脱敏"系反读，实为 42 处已脱敏） |
| High | H5 | 1208 `except Exception`，210 处静默吞噬 | 🔶 进行中（严格口径复测 **258** 处；DB 层 12 处已清零，`server/services` 75 处待批处理） |
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

---

## 附：全量测试与覆盖率基线（本轮实测）

### 运行方式

`pyproject.toml` 声明 `requires-python = ">=3.13"`，而沙箱默认解释器为 3.11——**在 3.11 上整套测试无法收集**（`langgraph` 等依赖装不上）。基线在 3.13 venv 下取得：

```bash
uv python install 3.13 && uv venv --python 3.13 && uv sync --all-groups
.venv/bin/python -m pytest tests/ -q
```

### 基线

| 指标 | 数值 |
|---|---|
| 通过 | **9759**（基线 9722 + 37 条 market-data 路由用例） |
| 失败 | 0 |
| 跳过 | 24（条件跳过：`fcntl` 非 POSIX、前端目录缺失、manifest 无变体等，均合理） |
| 反选 | 592（`integration`/`slow`/`regression`，需真实 API / Docker） |
| 覆盖率 | **68.7%**（69017 语句，22117 未覆盖） |
| 完全零覆盖 | 16 个文件 / 853 语句 |

被反选的 615 个 integration/regression 用例**全部可正常收集**（`--collect-only` 无 import 错误），即未腐烂，只是需要外部凭证。

### 财政核心层：覆盖率与"财政部"目标不匹配

本节是本轮最值得注意的发现。既然目标是把项目做成财政部门，那么资金相关的数据层应该是覆盖最好的部分，实测相反：

| 模块 | 覆盖率（基线 → 现在） | 语句 |
|---|---|---|
| `tools/sec/earnings_call.py` | 16.3% → **100%** | 43 |
| `tools/sec/types.py` | — → **100%** | 62 |
| `tools/sec/parsers/edgartools_parser.py` | 12.3% → **88%** | 187 |
| `tools/sec/eight_k.py` | 11.3% → **76%** | 177 |
| `tools/sec/tool.py` | 20.2% → **72%** | 94 |
| `server/app/market_data.py` | 26.0% → **81.6%**（+37 用例） | 288 |
| `server/database/ledger.py` | 46.6% → **87.7%**（+13 用例） | 73 |
| `server/database/portfolio.py` | 16.9% → **88.8%**（+10 用例） | 89 |
| `tools/sec/*` 合计 | ~15% → **86%** | 694 |

本轮已补齐的测试与所压的性质——

- **`market_data.py`（+37）**：13 个路由处理器全覆盖——HTTP 边界的拼写坍缩（`aapl`/`AAPL.US` → AAPL；股票端点的 `equity` 提示把与指数别名冲突的真实股票 COMP 钉在 equity 上，否则裸 COMP 会被自动识别为纳斯达克综合指数）；限流错误统一 503 + `Retry-After: 60` 且不透传上游文本；缓存往返的 TTL 断言（搜索 300s、分析师 900s、市场状态 30s）；快照批量的去重与 250 上限；单一快照空结果 404。
- **`ledger.py`（+13）**：账本每个值必须以参数形式交给驱动（用真实注入 payload 断言它出现在参数元组里、绝不出现在语句里）；不平衡或科目不存在的分录在写入前被拒，不产生任何 INSERT；幂等键重复报 `DuplicateEntryError` 而非校验错误（补救动作不同：停止重试 vs 修分录）；DB 触发器拒绝浮出为 `LedgerError`；用户科目遮蔽内置科目。
- **`portfolio.py`（+10）**：每条语句都带 `user_id`（租户隔离）；无字段更新不发 UPDATE；合并持仓重算加权成本（10@100 再 10@200 = 20@150，沿用旧成本会让下游所有浮盈失真）；`FOR UPDATE` 防并发合并；清仓后成本基准置空。
- **`tools/sec/*`（+85）**：电话会议匹配的 30 天窗口与最近日期选择（错配会把 Q3 电话会议接到 Q2 财报上）；EDGAR 拉取循环的单条容错（一条损坏申报不损失其余）；8-K Item 描述映射（Item 2.02=业绩、Item 7.01=指引，是模型分诊的信号）；10-K 属性访问 vs 10-Q 索引访问两种 API 形状及全文兜底；`amendments=False` 修正案排除（10-K/A 无完整 XBRL）；markerdown 渲染的 $B 换算与零值省略。

全部关键断言做了诱导验证——把窗口放宽到 60 天、把修正案排除去掉、把加权合并改掉、把 memo 拼进 SQL、把 503 改回 500、把 `equity=True` 提示去掉、禁用批量上限，对应测试都变红后恢复。

### 本轮新发现（不在原审计条目中）

**1. MCP 解释器信任根被硬编码为部署路径（已修）**。`_TRUSTED_INTERPRETER_ROOTS = ("/app/", "/usr/local/bin/python", "/usr/bin/python")`，只在容器镜像里成立。任何其它安装前缀——裸机 `/opt`、本地检出、开发 venv——都无法启动自己的内置 MCP server，`test_mcp_client_negotiation.py` 的 **14 个用例因此全挂**。改为认可 `raw == sys.executable`：进程交出自己的解释器属于第一方行为，且比前缀白名单更严格（白名单实际放行 `/app` 下任何 python，包括事后写入的）。`workspace`/`user` 两个不可信档位不受影响，仍走裸名规则。

**2. `probe.py` 的"脱敏"是虚假安全感（已修）**。该函数零覆盖，且 `_client_safe()` 的 docstring 自己写着"URL 由包作者选定，回显失败文本等于回显攻击者选定的材料"，实现却把脱敏后的消息发了出去。实测：`sanitize_error_text` 对 `https://evil.example.com:8443/mcp` **完全不处理**——它只抹 DSN userinfo、bearer token 这类凭证形状，主机与端口原样保留。现改为只回传异常类名，完整原因进日志。

**3. `_market_data_error` 的通用 500 分支不脱敏（已修）**。路由自己的 `except Exception` 分支走 `sanitize_error_text`，但 `result.error`（缓存服务把上游异常**字符串化**后塞进结果对象，DSN 一并带入）走 `_market_data_error` → `detail=text` 原样透传——同一响应面两套标准。给所有调用方（intraday/daily/snapshots，含复用该 helper 的 `bars.py`）的通用分支统一加上脱敏。这条是给 daily 路由写泄漏断言时被测试当场抓出来的。

**4. `sanitize_error_text` 不识别裸 `password=`（已修）**。`_KEY_PARAM_RE` 覆盖 `api_key=`/`authorization=`/`client_secret=` 等 key=value 形状，却漏了最直白的 `password=`/`passwd=`/`pwd=`（URL query 里的 `?password=` 另有规则覆盖，裸文本没有）。实测：`conn to postgres://u:hunter2@db:5432` 被清理，`password=hunter2` 原样通过——同一条错误信息里两种形状，一种被抹一种不抹。已在 key 集合补上这三者（8 字符以上才触发，`passphrase=` 与普通行文不受影响，已用负例钉住）。

**5. 已知 flaky**：`test_fan_out_reconstruction_preserves_live_order` 以 `xfail(strict=False)` 兜底，文档自述"跨运行约 50/50"。因此全量结果中它有时报 `xpassed` 有时报 `xfailed`，**不是回归**。

### 关于审计数字（第五次更正）

审计的头条数字已被实测推翻五次：944→915（后修正）、H2 的 5 处指认中 3 处误判、H4 的"42 处未脱敏"实为 42 处已脱敏、H5 的"210 处静默吞噬"先修正为 125、再实测（严格口径：宽捕获 + 块内无日志无重抛）为 **258**——`server/services` 75、`ptc_agent` 35+、`server/app` 18、`server/database` 12（已清零）。**凡引用本审计的数字，都应先复测再据以决策。**

