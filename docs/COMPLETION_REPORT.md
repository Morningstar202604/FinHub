# FinHub 功能阶段完成报告（ROADMAP 执行总结 · 终版）

> 会话目标：按 [ROADMAP](./ROADMAP.md) 逐项检查实现完整性，补齐剩余功能、消除可优化点，最后做模拟使用测试并提交完成报告。
> 共识约束：① 前端/产物不依赖国外资源（谷歌字体/CDN 等国内不可达）；② 能用现成库/框架就不自己造轮子；③ 前端与后端 1:1 对应。
>
> **终版说明**：本报告在 M2 版本基础上追加 **M3 性能工程 + 基础设施补缺 + M4 前端重构 + 全量回归**（对应 [EXECUTION_PLAN_M3_M4.md](./EXECUTION_PLAN_M3_M4.md) P1~P7，全部 ✅）。原 M2 内容保留在下方，新增部分见「二、M3/M4 轮次增量」。

---

## 一、完成情况总览

| 里程碑 | 内容 | 状态 | 验证 |
|---|---|---|---|
| M1 基座清理 | 契约守卫、死代码删除、重复收敛、陈旧引用修复 | ✅ 完成 | 单测全绿 |
| M2-A 深度研究接线 | 多 provider 熔断链注册为 Agent 工具 | ✅ 完成 | 单测 + evals |
| M2-B 意图识别路由 | 规则双层分类自动路由 `auto\|ptc\|flash` | ✅ 完成 | 12/12 evals |
| M2-C 沙箱资源配额 | `sandbox.quotas` 配置 + 创建配额门禁（409） | ✅ 完成 | 14 项单测 |
| M2-D 自我验证闭环 | 代码级审校器（数字/引用/矛盾）+ Agent 工具 | ✅ 完成 | 6/6 evals |
| M2-E 记忆检索 | BM25 兜底 `recall_memory` 工具（无 embedding 强依赖） | ✅ 完成 | 13 项单测 |
| M2-F 结构化输出 | `ArtifactVersion` schema + 序列化契约 | ✅ 完成 | 单测全绿 |
| M2-G Evals 评测台 | 21 场景 × 3 suite，CI 冒烟 | ✅ 完成 | 21/21 evals |
| M2-H Guardrails | 提示注入检测 + PII 打码 | ✅ 完成 | 单测全绿 |
| M3 性能与工程 | SSE 批量刷盘、索引审计+033 迁移、Redis pipeline、沙箱预热、依赖审查 | ✅ **本轮完成** | 见 PERF 基线 + 单测 |
| 基础设施补缺 | CI 性能冒烟、evals artifact、/health 增强、部署/基线/依赖文档、Playwright 浏览器 | ✅ **本轮完成** | CI 配置 + 4 份文档 |
| M4 前端重构 | 4 个 M2 可见化页面 + 类型对账 + 前端回归（skill 驱动） | ✅ **本轮完成** | 15 项新单测 + tsc/vitest/e2e |
| M4-Guardrails SSE 接线 | guardrails 事件在前端展示（SSE EventType 补全 + 通知入口 + 三语文案） | ✅ **本轮完成** | 0 regression |

**最终验收（2026-09-10 实测）：**

- 后端单测：**9354 passed，1 xpassed，0 failed**（含 M3 批量写入/pipeline/prewarm、M4-1/4-4 新端点用例）
- 前端：`tsc --noEmit` **0 error**；`vitest run` **302 files / 3286 tests 全绿**（复用 300 既有 + 新增 15）；playwright e2e 冒烟 **11 passed**
- evals 评测台：**21/21 ALL GREEN**（intent 12 + auditor 6 + research_fallback 3）
- 契约守卫 `contract_guard.py --check`：migrations / status_vocabulary / docstring_lock / frontend_mirror **4 项全 OK**
- 模拟使用全链路 smoke：**8/8 通过**
- Guardrails SSE 接线：后端 `sse_producer.py` 已发送 `guardrails` 事件（2026-09-10 实测），前端本次补齐类型与处理器 → 全链路打通

---

## 二、M3/M4 轮次增量（本终版新增）

### 2.1 M3 性能与工程（P1~P4）

- **SSE 批量刷盘（P1）**：`redis_cache.pipelined_event_buffer_many` + `stream_append_many_with_retry` + `stream_writer.buffer_events_many`；`executor.py` 攒批 32 条或 50ms 刷新，`run_end` 强制 flush。1000 帧写入网络往返从 O(N) 降至 ceil(N/32)。
- **索引审计 + 033 迁移（P2）**：审计热门查询索引覆盖，新增 `033_index_audit_tail` 附尾迁移（`IF NOT EXISTS` 幂等），`test_migrations` 覆盖 upgrade/downgrade。
- **Redis pipeline 收敛（P3）**：`delete_pattern` 改 SCAN+分块（100 条）pipeline 删除；全局收敛 `set` 批量写残留到 `set_many`。
- **沙箱预热（P4-A）**：`workspace_manager.prewarm_sessions()` 启动后延迟 30s 预热 always-on workspace，失败不影响启动；`session_path_counter` 观测 prewarm。
- **依赖审查（P4-B）**：产出 `docs/DEPENDENCY_REVIEW.md`（当前版本→升级窗口→风险→动作），本阶段不贸然升级锁定依赖。

### 2.2 基础设施补缺（P5）

- CI `test.yml` 新增 `performance-smoke` job（`event_write_smoke`）与 evals 报告 artifact 上传。
- `/health` 增加 redis 与 agent_config 探测（非致命，失败标记 degraded 不 500）。
- 文档产出：`docs/PERFORMANCE_BASELINE.md`（P1 前后基线）、`docs/DEPLOYMENT.md`（环境变量/迁移/worker/健康检查）、`docs/DEPENDENCY_REVIEW.md`。
- 本环境补齐 Playwright chromium 浏览器 + 系统依赖（`libatk` 等），使 e2e 冒烟可本地执行。

### 2.3 M4 前端重构（P6，frontend-design skill 驱动，1:1 契约）

| 项 | 后端 | 前端 | 验证 |
|---|---|---|---|
| M4-1 意图路由 reason 面板 | `messaging.py` 决策持久化 `thread.metadata.intent`（`update_thread_metadata_merge` 幂等 JSONB merge） | `ReasonPanel.tsx` 挂 `ChatView`（徽章+原因+置信度） | 4 项单测 |
| M4-2 审校报告视图 | auditor findings 随 artifact 交付 | `AuditReportView.tsx` 经 `ToolCallDetailView` 渲染（error/warning/info） | 4 项单测 |
| M4-3 记忆浏览器 recall | `GET /api/v1/memory/recall`（BM25、owner 守卫） | `MemoryRecallView.tsx` 挂 `MemoryPanel`（浏览/检索切换 + 来源 chip + score） | 4 项单测 + 后端测试 |
| M4-4 评测台看板 | `GET /api/v1/evals/report`（只读 latest.json） | `Evals.tsx` + `/evals` 路由 + 侧边导航 + 三语文案 | 3 项单测 + 后端测试 |

类型对账：`ThreadMetadata.intent` / `MemoryRecallResponse`·`RecallHit` / `AuditFinding`·`AuditReportData` 与后端 pydantic 模型 1:1 复核通过；`reset()` 修掉两处此前遗留的 token 引用（`--color-danger` → `--color-loss`）、ja-JP 缺失键（`intent.audit*`、`sidebar.evals`、`memoryPanel.recall*`、`evals.*`）补齐，`src-wide locale key parity` 与 `tokenRefs` 两套基建测试恢复全绿。

M4-Guardrails SSE 接线（2026-09-10）：后端 `sse_producer.py` 在每次 run 结束后已发送 `guardrails` 事件（含 `redacted_count`、`injection`），但前端 `SSEEventType` 未声明该类型、`processStreamEvent.ts` 未处理，导致 PII 打码 / 注入检测 结果在前端聊天的 toast 通知中不可见。本轮在 `web/src/types/sse.ts` 新增 `GuardrailsEvent` 接口并加入 `SSEEvent` discriminated union，在 `processStreamEvent.ts` 添加 guardrails handler（主 agent 仅、`redacted_count>0` 打 info toast、`injection[]` 打 warning toast），并在 `en-US`/`zh-CN`/`ja-JP` 三语言文件补 `chat.guardrailsPIIRedacted` 与 `chat.guardrailsInjectionDetected` 文案。`vitest run` 0 regression。

---

## 三、M2 轮次增量（历史记录，保留）

### 3.1 本轮补齐的功能

**M2-C 沙箱配额（新增）**
- `src/ptc_agent/config/core.py`：新增 `SandboxQuotas` 模型（max_workspaces / max_parallel_runs / cpu_share / memory_mb / idle_minutes，全部可空=不限制）+ `SandboxQuotaError` + `assert_sandbox_quotas()` 纯函数门禁。**默认不限制，无配置时行为零变化**。
- `SandboxConfig.quotas` 字段 + `create_sandbox_config()` 解析 `sandbox.quotas` YAML 块。
- `workspace_manager.create_workspace()`：仅当配额显式配置（`isinstance(int)` 判定，天然兼容 Mock/真实 config）时先计数后放行。
- `workspaces.py` POST /workspaces：`SandboxQuotaError` → **409** + 中文文案（current/limit）。
- `agent_config.yaml`：配额块文档化示例（对齐 Dockerfile.sandbox 8G 语义）。
- 测试：`tests/unit/config/test_sandbox_quotas.py`（11 项）+ `test_workspace_manager.py` 新增配额路径用例（3 项）。

**M2-E 记忆检索（新增）**
- 依赖：`pyproject.toml` + `uv.lock` 引入 **rank-bm25**（零依赖纯 Python；BM25Plus 变体，小语料 idf 不塌陷）——按"能不自己造就不造"原则直接使用成熟库。
- `src/tools/memory/retrieval.py`：CJK 感知分词 + 300 字滑动窗口切片（40 字重叠）+ BM25Plus 排序 + ≤1200 token 注入预算守门；空查询/空语料/同质语料优雅降级。
- `src/tools/memory/tool.py`：`recall_memory` 工具（content_and_artifact），Agent 传入记忆文档即返回 top-k 相关摘录 + 来源标签；已注册进 `ptc_agent/agent/agent.py` PTC 工具集。
- 测试：`tests/unit/tools/memory/test_retrieval.py`（13 项）全绿。

### 3.2 CN 可访问性修复（用户第 1 点：「不要用国外的」）

**谷歌 favicon 服务（`www.google.com/s2/favicons`）在国内不可达 → 全部替换为域名直连 `/favicon.ico` + 现有 Monogram 兜底：**

| 文件 | 改动 |
|---|---|
| `web/.../Favicon.tsx` | 新 `faviconUrlForHost()`：`https://<host>/favicon.ico`（www 剥离）；仍拒绝对内网/非公共主机探测（隐私不变）；新增单测 |
| `web/.../InlineArtifactCards.tsx` | `googleFaviconUrl` → `faviconUrlForDomain` |
| `web/.../ToolCallDetailView.tsx` | import 与调用同步更名 |
| `web/.../InsightDetailModal.tsx` | 直接生成直连 URL |
| `src/tools/web/providers/serper.py` | `_favicon_url` 改为直连 host |
| 相关测试 fixture / mock | 同步更新 |

**字体/报告 CDN 复核（已达标，本轮确认无需再改）：**
- `web/index.html`：无 Google Fonts / 国外 webfont 加载（早前已修，含注释说明）。
- `tokens.css` / `index.css`：纯系统字体栈（PingFang/微软雅黑/Noto Sans SC 兜底），无 `@import` 外链、无 `@font-face` 远程。
- `ExportPreviewModal.tsx` 打印字体预设：统一为「西文首字体 + 中文兜底」栈（Source Serif+宋体、Inter+苹方…），并校准 `PRINT_FONTS` 与 `PRINT_PRESETS` value 一致（修掉两处测试断言落后的问题）。
- 服务器端 CSP（`workspace_files/serve.py`、`pdf_render.py`）与 html-report skill：**Google Fonts 明确不在白名单**，报告走系统字体；CDN 白名单仅为 agent 内容加载的可选项，非应用硬依赖。

### 3.3 附带的「检查 + 优化」结论（用户第 2 点）

- **无重复造轮子**：记忆检索直接用 `rank_bm25`；意图/审校/guardrails 均为纯规则模块（不引外部 LLM 依赖）；未重复实现已有框架能力。
- **契约红线未破**：本轮未引入新 DB 迁移（意图决策落 thread_metadata、审校报告走 artifact、向量表在无 embedding 配置下不建空表）——已写入 ROADMAP「M2 配套迁移」决策说明；`contract_guard` 全绿。

---

## 四、模拟使用测试（用户第 3 点）

脚本：[scripts/e2e/simulation_smoke.py](./scripts/e2e/simulation_smoke.py)（无外部 key、无 DB、mock 供应商）

```
[PASS] 意图识别 → PTC（深度分析/建模）      mode=ptc reason=strong ptc signal keyword
[PASS] 意图识别 → Flash（简单行情）          mode=flash reason=no workspace
[PASS] 深度研究工具（无 key 优雅降级）        provider 链尝试后回退
[PASS] 联网搜索工具可构建                    WebSearch
[PASS] 自我验证审校器（检出数字失真）        errors=5
[PASS] 结构化输出 artifact 契约              schema_v=1 往返无损
[PASS] 记忆检索 recall（BM25 相关性）        memory.md 排第一
[PASS] Guardrails PII 打码                   aa********@qq.com / 110***…
模拟全链路: 8/8 通过
```

覆盖一条真实用户消息的完整链路：**用户输入 → 意图路由 → 工具调用（搜索/深度研究）→ 自我审校 → 结构化 artifact → 记忆召回 → 输出护栏**。

---

## 五、剩余项与后续

| 项 | 状态说明 |
|---|---|
| M3 性能工程 | ✅ 本终版已完成（见 2.1）；PERF 基线记录于 `docs/PERFORMANCE_BASELINE.md` |
| M4 前端重构 | ✅ 本终版已完成（见 2.3）；4 个 M2 可见化页面落地并通过回归 |
| 基础设施 | ✅ 本终版已补（CI 冒烟、/health、部署/基线/依赖文档、Playwright 环境）；遗留：`mcp_registry.py` 一处 `\S` 转义告警、pydantic `utcnow()` 弃用告警随 Q 审处理 |
| 033+ 迁移 | 后续 DB 变更仍强制附尾并通过守卫 |

## 六、结论

ROADMAP M1–M3（性能与工程）**全部完成**，M4 前端重构（skill 驱动、1:1 契约）**全部完成**。功能面：M2 的 8 个智能体能力（A–H）均有实现 + 单测 + evals 佐证；工程面：SSE 批量刷盘/索引审计/Redis pipeline/沙箱预热落地并有基线；体验面：意图路由 reason 面板、审校报告视图、记忆检索浏览器、评测台看板四个 M2 能力可见化。CN 可访问性隐患清零；模拟使用测试 8/8 通过；全量回归（后端 9354 + 前端 3286 + evals 21 + e2e 11 + 契约守卫 4 项）**无失败**。功能阶段全部完成，可进入下一阶段（M5 产品化/推广）。