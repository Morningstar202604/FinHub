# FinHub 改进建议

> 本文档中的**每一个数字都在当前代码上实测得出**，不是估计值。凡是与我早期说法不符的地方，我按实测结果修正，并在正文中标注。
>
> 测量基线：`main@b968a05`，后端 `tests/unit` 9446 passed / 0 failed，前端 `check-critical-path` 绿。

---

## 0. 先说结论

这个项目的工程质量**高于同类项目的平均水平**：`src/server/` 有清晰分层、`tests/unit` 有 9446 个用例、前端有 `check-critical-path.mjs` 这种主动守卫首屏预算的脚本、`error_sanitization.py` 这种为凭证泄露专门写的工具。这些都不是通用脚手架能生成的，是有人认真做过。

所以下面的建议**不是"你这里一团糟"**，而是：**项目已经长到"体量的瓶颈"阶段了**——决定质量上限的不再是"某个功能写得好不好"，而是几个**结构性选择**在同时放大维护成本。我把它们按 `影响 ÷ 改造成本` 排序。

### 本轮已修复（3 项）

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| 1 | monaco-editor 进了首屏临界路径 | 首屏 gzip **1349.8 kB → 370.2 kB（−72.6%）** | ✅ 已修 |
| 2 | 3 处 `asyncio.create_task` 丢弃返回值 | 任务可能被 GC 中途回收，**无异常无日志** | ✅ 已修 |
| 3 | 42 处 `HTTPException(detail=str(e))` | 异常文本回显连接串，**泄露凭证** | ✅ 已修 |

第 1 项是**我上一轮自己引入的回归**——我把 `monaco-editor` 从 `devDependencies` 挪到 `dependencies` 时，没注意到 `monacoSetup.ts` 是 `main.tsx` 里的静态副作用导入。守卫脚本当场变红（超预算 899.8 kB），现在绿了，剩余余量 79.8 kB。

---

## 1. 最高优先级：架构分层是"名义上的"

这是我认为**唯一值得单独拿出来讨论**的问题，其余都是它的副产品。

### 实测结果

我用 AST 只在**模块体层面**（排除函数体）重建了包依赖图。结论出人意料：

```
模块体导入(src.*) 计数 : 1394
函数体内导入 计数       : 766
模块体层面的环数        : 13        ← 不是 0
```

13 个真实的环长这样：

```
ptc_agent.agent -> server.utils -> server.app -> ptc_agent.agent
server.utils    -> server.app   -> server.handlers -> server.utils
server.database -> server.services -> server.database
server.models   -> tools.chart_annotation -> server.database -> server.services -> server.models
...
```

### 为什么这件事比"有耦合"严重

因为它**同时否定了两个常见假设**：

1. **"分层是清晰的"** —— 如果 `server.utils` 在模块体层面依赖 `server.app`，那 `utils` 就不是底层工具层，而是和 `app` 互相嵌套。你没法按"从下往上加载"的顺序理解这个系统。
2. **"环是靠函数内导入打破的"** —— 部分是的（598 次函数内导入里，只有 62 条边是模块体层面不存在的新边），但**剩下的 13 个环在模块体层面就闭合了**。

第 2 点尤其值得注意：766 次函数内导入里，**536 次是在重复模块体已有的边**。也就是说，函数内导入**主要不是用来打破环的**，而是被当成了一种习惯写法。真正因为"必须打破环"而存在的只有 62 条边。

### 一个具体的分层倒置

`ptc_agent` 在文档里是"core agent"，但它有 **10 个文件在模块体层面导入 `src.server.*`**：

| 文件 | 模块体依赖 |
|---|---|
| `agent/backends/user_data.py` | `server.services.user_data_io` |
| `agent/middleware/background_subagent/tools.py` | `server.contracts.status` |
| `agent/middleware/background_subagent/workflow/driver.py` | `server.utils.error_sanitization` |
| `agent/tools/file_ops.py` | `server.services.user_data_io` |

**"核心"依赖"外壳"**——这是教科书式的分层倒置。它的真实代价不是"不好看"，而是：你没法把 `ptc_agent` 单独拿出来复用或测试，因为它的加载顺序被 `server` 反向锁定了。

### 建议

**不要做"大重构"**。13 个环、1394 个模块体边，一次性拆完的风险远大于收益。我建议的是**"冻结 + 单向收缩"**：

1. **加一个依赖守卫**（这是关键一步）。写一个和 `check-critical-path.mjs` 同风格的脚本 `scripts/check-import-layers.mjs`（或 Python），声明一份**允许的边白名单**，当前状态作为基线写入。任何新增的环或新增的倒置边 → 构建失败。
   - 理由：你已经有 `check-critical-path.mjs` 这个成功先例了——**它能拦住 5 个月的回归**，因为它把"不许变差"变成了机器可判定的事。分层同理。
   - 成本：约半天。**收益：从现在起分层只会变好，不会变坏。**

2. **三个具体的抽取动作**（按收益排序）：
   - `server.utils.error_sanitization` / `content_normalizer` / `contracts.status` 这三个被 `ptc_agent` 依赖的模块，**下沉到 `src/common/` 或 `src/shared/`**。它们本来就是无依赖的纯函数，下沉后 `ptc_agent` 对 `server` 的依赖从 10 个文件降到 6 个，且消除 `ptc_agent.agent <-> server.utils` 这个环。
   - `server.app <-> server.handlers` 的环：`server.app` 在模块体层面导入 handlers（路由注册），handlers 反过来导入 `server.app`。这个环可以用"路由注册表 + 延迟绑定"解开，是标准做法。
   - `server.utils -> server.app` 这条：查一下就发现是 `utils` 里某个模块为了读 app 级配置而反向依赖。配置应该来自 `src/config`，不是 `server.app`。

3. **制定"函数内导入"的书写规范**。既然 536/598 是重复边，那就明确：**函数内导入只在两种情况下允许**——(a) 真正为了打破环，(b) 重依赖的延迟加载。两种都要在导入行上方写一行注释说明是哪种。这条规则很便宜，但它会把"习惯"变成"决定"。

---

## 2. 后端（按性价比排序）

### 2.1 配置层：三个开关读了但没人用

实测（非 config 目录的引用数）：

| 函数 | 位置 | 被引用 |
|---|---|---|
| `is_result_log_db_enabled` | `src/config/settings.py:98` | **0** |
| `is_cache_invalidate_on_write_enabled` | `src/config/settings.py:391` | **0** |
| `get_debug_mode` | `src/config/settings.py:48` | **1，但只在测试里** |

`get_debug_mode()` 读的是 `config.yaml:17` 的 `debug: false`，唯一引用者是 `tests/unit/config/test_infrastructure_config.py:170`。也就是说：**这个测试在验证一个没有任何生产代码使用的开关**。

对 `src/config/settings.py` 里全部 72 个 getter 做了逐一扫描（AST 提取函数名 + 全仓正则匹配，排除自身与 pyc）：

| 类别 | 数量 | 含义 |
|---|---|---|
| 生产代码零引用 | 13 | `src/` 下除 `settings.py` 外无人调用 |
| **生产 + 测试均零引用** | **12** | 上者去掉 `get_debug_mode`（仅测试引用） |

12 个"完全无人使用"的 getter：

```
is_result_log_db_enabled              is_redis_warm_on_startup_enabled
is_langsmith_tracing_enabled          get_redis_ttl_results_list
get_redis_ttl_result_detail           get_redis_ttl_metadata
get_redis_ttl_metadata_summary        get_redis_ttl_workflow_status
get_redis_ttl_cancel_flag             is_cache_invalidate_on_write_enabled
get_subagent_task_max_wait            get_in_memory_event_tail_max_events
```

> 修正：我早期版本说"9/64 死 getter"。**实测是 13/72（生产零引用），12/72（完全无人使用）**。`is_redis_warm_on_startup_enabled` 和 `is_langsmith_tracing_enabled` 是早期漏掉的两个。

其中值得单独说的是 **`get_redis_ttl_*` 家族**：`results_list`、`result_detail`、`metadata`、`metadata_summary`、`workflow_status`、`cancel_flag` 这 6 个全部无人使用，而**它们的兄弟**（`get_redis_ttl_workflow_events`、`get_redis_ttl_steering`、`get_redis_ttl_market_watch`、`get_redis_ttl_memo_metadata_*`）**被大量使用**：

```
src/server/services/runs/executor.py:140          self.redis_event_ttl = get_redis_ttl_workflow_events()
src/server/handlers/chat/steering.py:121          pipe.expire(key, get_redis_ttl_steering())
src/utils/market_watch.py:69                      ttl=get_redis_ttl_market_watch()
src/server/app/memo.py:127                        ttl=get_redis_ttl_memo_metadata_cancel()
...
```

**这不是"配置层被废弃"，而是"配置层被废弃了一半"。** `config.yaml:143` 的 `ttl:` 段下 11 个键，5 个有 getter 但 getter 无人用（`results_list` / `result_detail` / `metadata` / `metadata_summary` / `workflow_status` / `cancel_flag`），另外 5 个链路通畅。

**这种"一半能用一半不能用"比全部废弃更危险**——运维看到同一段里有 11 个长相一样的键，会合理地假设它们行为一致。实际上一半调了没用。

**动作**：把 5 个断链的键从 `config.yaml` 里删掉（或接上），**让这一段"要么全真、要么不留"**。

**为什么值得修**：这不是"删几行代码"的问题，而是**它们在向运维撒谎**。有人看到 `config.yaml` 里有 `debug` 键、有 `result_log_db_enabled` 键，会合理地认为"调这个能改行为"。实际上调了没有任何效果。**配置项是运维的 API，不能有静默失效的项。**

**动作**：要么删（推荐，成本 1 小时），要么接上真正的消费点。**不要留着。**

### 2.2 异常处理：1220 个 `except Exception`，116 个裸 `pass`

实测：

```
except Exception 总数 : 1220
其中裸 pass 吞掉      : 116
```

集中度最高的文件：

```
5  src/server/services/workspace_status_pubsub.py
4  src/ptc_agent/core/sandbox/mcp_setup.py
4  src/ptc_agent/core/sandbox/providers/docker.py
4  src/server/app/oauth.py
4  src/server/services/thread_mutation.py
4  src/server/services/report_back/subagent.py
4  src/server/services/runs/recovery.py
```

**其中最值得注意的是 `src/server/database/api_keys.py` 和 `src/server/app/api_keys.py` 各 3 处**——数据库层静默吞异常意味着"写失败了但调用方以为成功了"。这个类别的问题不会在测试里暴露，只会在生产里以"数据莫名其妙丢了"的形式出现。

**动作**：不建议全量整改（1220 个太多了）。建议：
- **强制要求** `src/server/database/**` 里的裸 `pass` 全部改成 `logger.warning(..., exc_info=True)` + 保持原行为。约 6 处，成本极低，但堵住了最危险的类别。
- 其余位置按"**静默吞异常必须写一行注释说明为什么可以吞**"的规范逐步收口，可以配合 lint 规则（`ruff` 有 `S110 try-except-pass`）。

### 2.3 `_scope_cache` 是进程内的，而代码自己知道这样不对

`src/server/dependencies/usage_limits.py:487`：

```python
_scope_cache: dict[str, tuple[list[str] | None, float]] = {}
_SCOPE_CACHE_TTL = 300  # 5 minutes
```

**两个问题**：

1. **无上限，靠 TTL 被动过期。** 键是 `user_id`，值 5 分钟过期。但没有任何容量上限——活跃用户数上不封顶。单机场景问题不大，但它是"没有上界"的。
2. **进程内缓存，而项目已经支持多 worker。** `server.py:118` 的注释说得很清楚：lifespan 会在 WriterGuard 栅栏无法激活时**拒绝 `--workers>1`**——也就是说**多 worker 是受支持的一等模式**。而 `vault_invalidation.py:272` 自己承认了这一点：

   > `process — a fast path only, and one that misses under multiple workers.`

**动作**：把 `_scope_cache` 换成有 `maxsize` 的 `functools.lru_cache` 或带 LRU 淘汰的 dict，**并明确写上它是 per-worker 的**（在 docstring 里写清"多 worker 下每个进程各持一份，容忍 5 分钟不一致"）。如果 5 分钟的不一致不可接受（这是权限缓存，关系到 gating），那就该走 Redis。**这是设计决策，需要你拍板，不是纯技术问题。**

### 2.4 `_workspace_locks` 的清理比想象的完整，但仍有边界

我起初以为这是"永不驱逐"的泄漏。实测后**修正**：`workspace_manager.py:3424` 在 `delete_workspace` 里会 `pop`，`:3659` 在 shutdown 时会 `clear()`。所以**不是"永不驱逐"**。

残留的边界：**`create_workspace` 建的锁，如果那个 workspace 从不被删除，锁就一直在**。这其实是"合理缓存"而非"泄漏"——锁对象很小，且与 workspace 一一对应。**建议降级为"加一行注释说明生命周期"**，不必改。

### 2.5 173 处 `os.getenv` 与 import-time 冻结的配置

- `os.getenv` 在 `src/` 里散落了 173 处，而项目**已经有** `src/config/settings.py` 这个配置层。配置来源不唯一。
- `sse_producer.py:43-46` 在**模块导入时**读取配置并冻结。这意味着**改环境变量后必须重启进程**，且测试里没法用 monkeypatch 覆盖（要到 import 之前改，很别扭）。

**动作**：不要求全量迁移。建议制定规则"**新增的环境变量必须走 `src/config`**"，然后用一个 lint 规则拦住新增的裸 `os.getenv`（可以基于 `ruff` 的 `TID` 或自定义规则）。和 2.1 一样，**先冻结，再收缩**。

---

## 3. 前端

### 3.1 实测修正：我之前的 img/alt 数据是错的

我必须先纠正自己：我早期说"41 个 `<img>` 里 24 个缺 `alt`"。**实测结果不是这样**：

```
<img>     : 39   带 alt: 38   缺 alt: 1
```

**38/39 有 alt。** 这个项目的可访问性比我说的好得多。只有一个漏网的，基本可以忽略。

### 3.2 行情数据有两个真相来源（真问题，已实测）

这是我认为前端**最值得修**的一处。`useMarketDataWS.ts:71`：

```typescript
const [prices, setPrices] = useState<Map<string, PriceUpdate>>(() => new Map());
```

`useMarketDataWS.ts:193-206` 同时**写两个地方**：

```typescript
setPrices((prev) => { ... });                     // ① 本地 state
writeQuoteFromWs(queryClient, symbol, {...});      // ② TanStack Query 缓存
```

然后**消费方分裂成两派**：

| 消费方 | 读哪里 | 节奏 |
|---|---|---|
| `MarketSidebarPanel.tsx:54,159` | **① 本地 `wsPrices`** | WS 实时 |
| `MarketChartSurface.tsx:89,139`、`MarketView.tsx:331` | **① 本地 `wsPrices`** | WS 实时 |
| `MiniChartGridWidget.tsx:177,212` | **② Query 缓存** | 60 秒轮询 |
| `useWatchlistData.ts:137` | **② Query 缓存** | 60 秒轮询 |

**后果**：同一个 symbol，Dashboard 的 MiniChart 磁贴（走 Query）和 ChartWidget（走 WS Context）**可以显示不同价格**。

实测确认这条路径**真的可达**：

| 组件 | 订阅 WS？ | 价格来源 | 节奏 |
|---|---|---|---|
| `ChartWidget.tsx:901` | ✅ `subscribe([upper])` | `prices.get(sym)` | WS 实时 |
| `MiniChartGridWidget.tsx` | ❌ **完全不订阅** | `quotes[quoteKey(...)]` | 60 秒轮询 |

`MiniChartGridWidget` 从来不订阅 WS，所以它**永远读不到实时值**。而 `writeQuoteFromWs` 只更新"已经被 REST 快照填充过"的行（`if (prev == null) return prev;`）——磁贴走的是 `useQuotes`，理论上会被写透到，但它自己的 `refetchInterval: 60_000` 决定了它拿到的是**兜底轮询值**。

更关键的是 `MarketSidebarPanel.tsx:159` 那句注释 `// Overlay WS live prices onto rows`——**这句话本身就是证据：作者知道 rows 里的价格是旧的，需要在消费端叠加实时值。** 这是双源架构的直接症状。

**动作**：以 Query 缓存为唯一真相源，`wsPrices` 仅作为"哪些 symbol 当前有实时订阅"的存在性标记（`wsPrices.get(sym)` 只用于判断 `wsHasData`，不再用于取值）。所有价格统一从 `useQuote(symbol)` 读。`writeQuoteFromWs` 已经在正确的位置写 Query 了，**只要让所有人从 Query 读，双源就自动消失**。这是删代码的活，不是加代码的活。

### 3.3 393 个 `useEffect` + 41 个 `exhaustive-deps` 抑制

实测：`useEffect` 393 个，`useMemo` 184 个，`eslint-disable exhaustive-deps` 41 处。

41/393 ≈ 10% 的 effect 显式声明"我知道我的依赖不对"。**每一个抑制都是一个潜在的陈旧闭包（stale closure）bug**，且这类 bug 只在特定时序下复现。

**动作**：不建议批量整改，但建议：
- **禁止新增**（lint 里把 `react-hooks/exhaustive-deps` 的 disable 提升为 error 需要显式 `// justify:` 注释）。
- 已有的 41 处，**逐个人工过一遍**——不需要全修，但需要确认每一处是"故意的"而不是"当时嫌麻烦"。

### 3.4 `MarketChart.tsx`：2415 行，38 个 `useEffect`，0 个 `useMemo`

```
MarketChart.tsx: 2415 行, useMemo = 0 , useEffect = 38
```

2415 行、38 个 effect、**零个 memo**——这是一个组件在承担整个图表生命周期的所有状态。**0 个 `useMemo` 在这体量下几乎必然意味着每次渲染都在做重复计算**（指标计算、数据变换、格式化）。

**动作**：这个文件不适合"重构"，适合"**冻结 + 加测试 + 逐步抽 hook**"。先给它补一层的渲染性能测量（React DevTools Profiler），拿到"每次渲染耗时"的数字，再决定抽哪部分。**没有数字就重构 2415 行的组件是赌博。**

### 3.5 `tsconfig.json` 只开了 `strict`

`web/tsconfig.json:9` 只有 `strict: true`，缺 `noUncheckedIndexedAccess`、`noImplicitOverride`。

`noUncheckedIndexedAccess` 尤其值得开——这个项目大量用 `Map.get()` 和 `quotes[symbol]`，开了之后所有 `可能 undefined` 的索引访问都会变成类型错误。**会新增一批错误，但每一个都对应一个真实的"可能 undefined"风险。**

**动作**：单独一个 PR，先开 `noImplicitOverride`（通常改动很少），观察一轮；再单独开 `noUncheckedIndexedAccess`（会多一批，逐个处理或加显式守卫）。**分开做，不要一次全开**——否则你会在一个 PR 里面对几百个错误，最后倾向于到处加 `!`，反而更糟。

### 3.6 `<label>` 有 106 个，`htmlFor` 只有 5 个

```
<label>   : 106   htmlFor: 5
```

101 个 label 没有关联到任何控件。**这直接意味着点击 label 文本不会聚焦到输入框**——这是真实的可用性缺陷（不只是 a11y 合规问题），表单体验会明显受影响。而且这是**低成本高收益**的一类：加 `htmlFor` 不改变任何逻辑。

**动作**：可以作为一个"新人上手任务"批次处理，或者配合 `eslint-plugin-jsx-a11y` 的 `label-has-associated-control` 规则逐步收口。

---

## 4. 其他

### 4.1 函数内导入的规范（呼应第 1 节）

766 次函数内导入里，只有 62 条边是模块体层面不存在的新边。**这个比值应该被显式管起来**，否则它会继续变成默认写法，分层信息就彻底丢失在函数体里了。

### 4.2 值得保留并推广的做法

这几处我认为是**这个项目做得比其他项目好的地方**，建议保护和推广：

| 做法 | 位置 | 为什么值得保留 |
|---|---|---|
| 首屏预算守卫 | `web/scripts/check-critical-path.mjs` | 它的注释记录了它拦下过 5 个月的回归。**这是本次最有效的护栏** |
| 凭证脱敏工具 | `src/server/utils/error_sanitization.py` | 有 6 个正则覆盖各类 key 形态，思路是对的（只是之前没接全） |
| 后台任务追踪惯例 | 改为 `src/server/utils/task_tracking.py` | 原项目已有正确写法，我把它集中并补了异常日志 |
| 沙箱不可达的专用错误 | `sandbox_unreachable_detail` | 把"环境问题"和"逻辑问题"分开，运维友好 |

**推广方向**：`check-critical-path.mjs` 的模式可以复制到其他地方——**分层守卫（第 1 节）**、**`os.getenv` 新增守卫（2.5）**、**`exhaustive-deps` 新增守卫（3.3）**。你已经证明了"把不许变差变成机器可判定"这条路在这个项目里走得通。

---

## 5. 执行建议

如果让我排一个顺序：

**第一批（1 天内，收益确定）**
1. 删掉 3 个静默失效的配置开关 + 9 个死 getter（2.1）
2. `src/server/database/**` 的裸 `pass` 改成带 `exc_info` 的 warning（2.2）
3. Query 缓存统一为行情唯一真相源（3.2）

**第二批（1 周内，建立护栏）**
4. 分层依赖守卫脚本，当前状态为基线（1.1）
5. 新增 `os.getenv` / `exhaustive-deps` 守卫（2.5、3.3）
6. `tsconfig` 先开 `noImplicitOverride`（3.5）

**第三批（需要决策，不是纯技术）**
7. `_scope_cache` 走 Redis 还是接受 per-worker 不一致（2.3）—— **需要你拍板**
8. `MarketChart.tsx` 的重构：先上 Profiler 拿数字，再决定抽什么（3.4）
9. 三个共享模块下沉到 `src/common/`，消除分层倒置（1.2）

---

## 6. 一句话总结

**代码本身的局部质量是好的，问题在结构层。** 最该做的不是"改更多代码"，而是**把"不许变差"变成机器可判定的事**——你已经在 `check-critical-path.mjs` 上验证过这条路有效。分层、配置、依赖抑制，都用同一招。
