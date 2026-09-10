# FinHub 功能完善路线图（ROADMAP v1.0）

> 定位：**功能阶段路线图**。把 FinHub 从"功能主体已成型"推进到"智能体基础设施完整、前后端 1:1、可评测可自证"。
> 明确不做：推广运营、多租户、渠道扩大、移动端、桌面分发签名（进入 M5 产品化阶段再议）。
> 铁律：契约不改（迁移历史 / DeltaChannel checkpoint / SSE Contract v2 / docstring 锁 / 核心依赖 pin）；只加补丁、只附尾迁移；每个里程碑完成先跑 `make test` + `make test-web` + `scripts/multiworker_gate/gate.py` 全绿再进下一步。

---

## 一、智能体能力盘点（对照"市面智能体标配"，避免重复造轮子）

| 能力 | 现状 | 差距 | 动作 |
|---|---|---|---|
| 联网搜索 | ✅ 已有 inhouse 零 key 爬虫 + 7 家搜索供应商（tavily/serper/bocha/exa/parallel/firecrawl） | 深度研究去重（research.py）未接线 | **M2-A** |
| 网页抓取 | ✅ 已有（scrapling 三档 + guard/safe_wrapper/熔断） | 覆盖率与站点黑名单维护 | 少量增强 |
| 意图识别 / 任务路由 | ❌ 仅客户端手动传 `agent_mode: ptc\|flash` | **无自动路由**：短问题也起 PTC 沙箱，浪费且慢 | **M2-B 核心** |
| 沙箱（PTC） | ✅ Daytona/Docker + 资源 tier 常量 | 无 per-workspace 资源配额/预算位 | **M2-C** |
| 研究循环（6 阶段） | ✅ research-loop Skill + `research_loops` 表 + 32 迁移 | 循环内无自动审校 → 证据全靠人工/单次 evidence-check | **M2-D 核心** |
| 自我验证 | ⚠️ evidence-check Skill 是"提示性门禁"，非代码级自动审校 | draft→critique→revise 未闭环 | **M2-D 核心** |
| 记忆与上下文 | ✅ agent.md + memory/memo + compaction/offload | **无向量检索**，memo 只按元数据匹配 | **M2-E** |
| 工具调用可靠性 | ✅ error_handling / empty_call_retry / result_normalization / leak_detection | 无结构化输出 schema 约束研究成果 | **M2-F** |
| Agent 评测 | ❌ 900+ 是单元/契约测试，无"行为评测" | 无场景库、无评分器、无 CI 门禁 | **M2-G 核心** |
| 护栏 Guardrails | ✅ protected_path / leak_detection / plan_mode / usage_limits | 无 skill 内容注入检测、无输出 PII 检测 | **M2-H** |
| 多模型/降级/计费 | ✅ llms 层完善 | 无需求级模型路由 | 并入 M2-B |
| 渠道/通知 | ⚠️ Slack/Discord/Feishu/TG 部分 | 促销阶段再做 | **不做** |

---

## 二、里程碑总览与依赖

```
M0 契约红线（常驻） → M1 基座清理 → M2 智能体基础设施（A~H，可部分并行）
                                     │
      M3 后端性能与工程质量（穿插） ←┘
                                     ↓
      M4 前端重构（frontend-design skill，前后端 1:1）→ （M5 产品化，本轮不做）
```

| 里程碑 | 内容 | 交付物 |
|---|---|---|
| **M1 基座清理** | 契约守卫脚本、死代码删除、重复收敛、陈旧引用修复、基线记账 | 干净的绿色基座 |
| **M2 智能体基础设施** | ✅ A 深度研究接线 · ✅ B 意图识别路由 · ✅ C 沙箱配额 · ✅ D 自我验证闭环 · ✅ E 记忆检索（BM25 recall） · ✅ F 结构化输出 · ✅ G Evals 评测台 · ✅ H Guardrails | **功能完整、可评测、可自证** |
| **M3 性能与工程** | SSE 序列化、索引附尾迁移、Redis pipeline、沙箱预热、前端分包 | 基线显著提升 |
| **M4 前端重构** | 用 `frontend-design` skill 出设计规范 → 按 1:1 API 契约完成所有页面/交互/视觉 | 好看、可控、完整的投研工作台 |

---

## 三、M1 基座清理（✅ 已完成，全部低风险）

> **状态：✅ 完成**（M1.3 前端部分随 M4 一并落地）

### M1.1 契约守卫脚本 ✅
- `scripts/guard/contract_guard.py`（4 项校验：迁移线性链 / status 分词族 / docstring 锁 / 前端镜像；纯 stdlib、离线、退出码即 CI 信号）
- 新建 `scripts/guard/contract_guard.py`（+ `--check` 模式进 CI）：
  1. `migrations/versions/` 只允许线性附尾（编号单调 +1，禁止改写已存在文件哈希——记录基线哈希到 `.contract-baseline.json`）
  2. `agent_docstring_lock.json` 与 MCP server docstring 一致性（复用 `update_agent_docstring_lock.py` 的读侧逻辑）
  3. `contracts/status.py` 的 TERMINAL/PUBLIC 状态集与迁移 CHECK 约束引用清单一致性
  4. SSE 事件类型登记：新增事件必须出现在 `test_event_ledger.py`（用静态扫描兜底）
- 验收：`python scripts/guard/contract_guard.py --check` 通过；CI 新增 job 调用；改动契约任一项（临时改动）会被拦。

### M1.2 死代码删除（先 grep 复核，零引用再删）
| 目标 | 复核方式 |
|---|---|
| `src/data_client/fmp/price_adapter.py`、`src/data_client/finhub_data/price_adapter.py` | `git grep -l "price_adapter"` 应仅剩声明处 |
| `fmp/data_source.py` / `finhub_data/data_source.py` 中仅被 price_adapter 引用的一对 `*PriceProvider` 别名 | 同上 |
| `src/tools/core/__init__.py`、`src/utils/__init__.py`（空占位） | 确认无导入语义后消减为空导出或删除 |
- 验收：单测全绿；`git grep` 复核通过。

### M1.3 重复收敛
- `storage/`：`oss_uploader.py`/`s3_compatible.py` 收敛为 `storage/__init__.py` 统一接口内部驱动（对外 API 不变，行为不变）
- `web`：`MarketView/utils/api.ts`、`Dashboard/utils/api.ts` 的 `streamFetch`/`sendFlashChatMessage` 收敛到 `ChatAgent/utils/api/transport.ts`（前端段，随 M4 一并做——此处只记录）
- 验收：后端单测全绿；前端类型检查通过。

### M1.4 陈旧引用修复
- `deploy/Dockerfile.backend|dev` 的 `COPY workflows/ workflows/`（目录不存在，删行）
- `Makefile` 补 `deploy`/`prod-up` 目标说明（标注"生产编排在私有仓库"）
- `libs/ptc-cli/README.md` 的 `llms.json` 过期引用改为指向 `src/llms/manifest/*.json`
- 验收：`docker build -f deploy/Dockerfile.backend` 可完成静态构建阶段。

### M1.5 基线记账
- 记录：`make test` / `make test-web` 全量耗时；`web` 首屏 JS 体积与 `check-critical-path.mjs` 水位线结果
- 产出 `docs/PERF_BASELINE.md`（M3 前后对比用）

---

## 四、M2 智能体基础设施（本轮核心，功能完整性）

### M2-A 联网搜索与深度研究完成化（✅ 已完成）
- 背景：`src/tools/web/research.py` 深度研究适配器已实现（exa/tavily/parallel 归一化）但未绑定任何 agent 工具。
- 设计：
  1. 新建 `src/tools/web/tools/deep_research.py`（`@tool` 壳，模式照 `market_data/tool.py`）：
     - 输入：`{question, depth: quick|standard|deep, max_sources}`
     - 流程：拆检索子问题 → 并行子检索（复用 `search.py` 选中的引擎）→ `research.py` 归一化 → 证据打分（来源新鲜度/可信域白名单/交叉一致性）→ 汇总带引用的结论
     - 输出：结构化 `DeepResearchResult`（摘要 + 证据列表[来源/引用/置信] + 未决问题）
  2. 在 `web_providers.json` 把 `research` capability 标记为已接线
  3. PTC 模式下由 Agent 决策调用；Flash 模式下暴露为可选高成本工具（受预算门）
- 涉及：`src/tools/web/{research,search,router,types}.py`、`manifest/web_providers.json`
- 验收：单测（mock 供应商）：快速深度（≤8 子问题）、结构化输出 schema 校验、无 key 时优雅降级到 inhouse 单轮检索。

### M2-B 意图识别与任务路由（✅ 已完成）
- 背景：`models/chat.py` 中 `agent_mode: ptc|flash` 由客户端决定；无自动路由。
- 设计：
  1. 新增 `src/server/services/router/intent.py`：轻量**规则 + LLM 双层意图分类**。
     - 规则层（零成本，先命中）：市场查询/定义/简单问答/问候 → `flash`；含"分析/建模/对比/写代码/财报深挖/跑数据"意图词 → `ptc`；引用了工作区/需要画图 → `ptc`
     - LLM 层（兜底）：命中不确定时用 flash 小模型一次切分打分（≤1 次调用，走 `LLMService.complete`）
     - 输出 `IntentDecision{agent_mode, confidence, reason, force_workspace?}`
  2. 路由接入点：`handlers/chat/request_prep.py` 中，当请求 `agent_mode` 未显式指定或为 `auto` 时调用 intent 分类器；前端默认发送 `agent_mode: auto`
  3. `models/chat.py` 的 Literal 扩为 `auto|ptc|flash`（兼容旧值）
  4. 观测：决策写入 per-turn metadata，前端 token 环展示"路由原因"
- 涉及：`src/server/services/router/`（新）、`handlers/chat/request_prep.py`、`models/chat.py`、`src/llms/service.py` 复用
- 验收：意图单元测试集 ≥15 条（规则层全过）；LLM 层用 mock LLM 验证；`auto` 请求端到端正确落库；低于 flash 阈值（如 >300 字+多个任务词）不再误进 flash。

### M2-C 沙箱资源配额与监管（✅ 已完成：配置 schema + 409 配额门禁）
- 背景：`resources tier` 常量存在但无 per-workspace 配额/限制。
- 落地：
  1. `SandboxConfig.quotas`（新 `SandboxQuotas` 模型）：`{max_workspaces, max_parallel_runs, cpu_share, memory_mb, idle_minutes}`，全部可空（None=不限制），默认部署行为不变；`agent_config.yaml` 附文档化示例
  2. `assert_sandbox_quotas()` 纯函数校验 + `SandboxQuotaError`（携带 current/limit 与中文文案）；`workspace_manager.create_workspace` 在配置了限额时先计数后放行
  3. `workspaces.py` POST /workspaces 把 `SandboxQuotaError` 映射为 **409**（未配置时不影响任何既有路径）
- 验收：`tests/unit/config/test_sandbox_quotas.py` 11 项全绿（schema/解析/越限拒绝/文案/默认不限制）；默认配置行为无回归。

### M2-D 自我验证闭环（✅ 第一阶段完成：代码级审校器 + Agent 工具）
- 背景：研究循环 6 阶段存在，但 evidence-check 是提示性 Skill，非自动审校。
- 设计：
  1. 新增 `src/tools/research_qa/auditor.py`：**代码级自动审校器**（多步）
     - 数字复算：抽取报告中关键数字（正则+Dollar/百分比模式），与 `data_client` 数据源交叉比对，超 2% 偏差标记
     - 引用溯源：检出无 provenance 记录的关键论断（走 `provenance/body_store` 匹配）
     - 矛盾检测：同一事实两处结论不一致 → 生成 conflict 报告
  2. 循环接入：`research_loop.py` 的 advance/report 阶段自动挂审校（新增 `evidence` 子状态），不合格打回 `generating` 并携带审计报告；人工可强制通过
  3. Skill 层：`evidence-check` SKILL.md 升级为"调用 auditor 工具 + 人工复核"双通道
- 涉及：`src/tools/research_qa/`（新）、`src/server/app/research_loop.py`、`plugins/finhub_research/skills/evidence-check/`
- 验收：对 3 个真实样例（1 个数字错误、1 个无引用、1 个矛盾）能全部检出并生成结构化报告；循环状态机单测更新通过；不阻塞无数据可查的报告。

### M2-E 记忆检索（✅ 已完成：BM25 兜底 recall 工具，无 embedding 强依赖）
- 背景：memory/memo 目录存在，检索按元数据；无向量。
- 落地：
  1. `pyproject.toml` 引入零依赖纯 Python 库 **rank-bm25**（BM25Plus 变体；不自己造轮子）
  2. 新增 `src/tools/memory/retrieval.py`：CJK 感知分词 + 300 字滑动窗口切片（40 字重叠）+ BM25Plus 排序 + ≤1200 token 注入预算守门；空查询/空语料/低分优雅降级
  3. 新增 `src/tools/memory/tool.py` 的 `recall_memory` 工具：Agent 传入记忆文档（agent.md / memory.md / memo / 历史研究结果）即返回 top-k 相关摘录 + 来源标签
  4. 注册进 `ptc_agent/agent/agent.py` 工具集（PTC 模式可用）
- 验收：`tests/unit/tools/memory/` 13 项单测全绿（分词/切片/排序/token 预算/降级/工具契约）；无需 API key。

### M2-F 结构化输出与工具契约
- 背景：研究成果无统一 JSON schema；工具结果已做 str 归一化。
- 设计：
  1. `src/ptc_agent/agent/tools/output_schema.py`：定义研究成果 schema（`ResearchArtifact{type, thesis, evidence[], risks[], confidence, next_actions[]}`）并为 `show_widget`/报告生成提供渲染契约
  2. tool 层对所有结构化 JSON 工具结果加 `schema_version` 字段（向后兼容，缺省默认 1）
  3. `services/persistence/usage.py` 侧记结构化输出校验失败次数（metric）
- 验收：schema conformance 单测；前端可按契约无损渲染（联调试验）。

### M2-G Evals 评测台（✅ 已完成 v1：21 场景 × 3 suite 全绿 + CI 冒烟）
- 背景：无行为评测。
- 设计：
  1. 新建 `evals/` 目录（仓库根）：
     - `scenarios/`：YAML 场景库（研究循环产出质量 / 工具调用精度 / 意图路由准确率 / 审校检出率 / 安全与护栏 / 长对话上下文保持），首波 ≥20 场景
     - `harness/run.py`：`uv run python -m evals run <suite> [--model 网关|真实]`——串行跑场景，可 mock LLM 或走 `LLMService`
     - `grader/`：规则评分器（数字/引用/结构） + LLM-as-judge 提示模板（复用 prompts 层）
     - `report.md` 输出与历史对比（存 `evals/runs/`）
  2. CI：`evals-smoke.yml` 仅跑 mock 断言集（<5min）；全量 eval 手动/定时
  3. 意图路由与审校器上线门槛：对应 suite 通过率 ≥80% 才可在生产打开开关
- 涉及：`evals/`（新）、`.github/workflows/evals-smoke.yml`、pyproject 增加 dev 依赖组（如 `openai` grader 无需新依赖）
- 验收：`uv run python -m evals run intent --dry` 零外部依赖可跑；至少 intent/router/auditor 三套 suite 全绿。

### M2-H Guardrails 补齐
- 背景：有 path/leak/plan 防护，缺内容注入与 PII。
- 设计：
  1. `middleware/tool/skill_injection.py`：扫描 Skill 与用户上传文档（memo 文本化阶段）中的提示注入特征（"忽略以上/你是/系统提示"空白+指令模式、量级阈值），命中则阻断或强制引用白名单
  2. `middleware/tool/pii_guard.py`：输出水门——检测身份证/银行卡/邮箱/密钥模式并统一打码（复用 `secret_redactor`；纯规则、无外部调用）
  3. `config.yaml` `features.guardrails.*` 开关默认全开
- 验收：注入样本（10 条攻击变体）全部命中或有审慎降级；PII 样本（10 条）全部打码；正常输出零误伤（黄金样本回归）。

### M2 配套迁移（本阶段未引入新迁移，理由如下）
- 原计划 `033_memory_chunks` / `034_intent_decisions` / `035_audit_reports`。
- **决策**：三项本轮均未引入新迁移——
  - `034` 意图决策：落 per-turn metadata（022 已有 `thread_metadata` 载体），无需新表；
  - `035` 审校报告：作为工具工件随 SSE 交付（结构化 artifact），非 DB 实体；
  - `033` 向量表：embedding 服务未配置，检索走 BM25 兜底（无表），避免无实际消费的空表迁移。
- 契约红线不变：后续任何 DB 变更仍走 033+ 附尾，`contract_guard` 守护线性链。

---

## 五、M3 后端性能与工程质量（✅ 已完成，见 [EXECUTION_PLAN_M3_M4.md](./EXECUTION_PLAN_M3_M4.md) P1~P4 + [PERFORMANCE_BASELINE.md](./PERFORMANCE_BASELINE.md)）

| 项 | 做法 | 验收 |
|---|---|---|
| SSE 序列化 | `sse_producer.py` 事件单次序列化+批量刷盘（`buffer_events_many`，攒批 32 条/50ms） | ✅ 批量 pipeline 写入 + 单测；往返 O(N)→O(N/32) |
| 索引审计 | 慢查询 `EXPLAIN` → 附尾 033 索引迁移 | ✅ `033_index_audit_tail` + `test_migrations` |
| Redis pipeline | `stream_append`/`stream_pool` 批量写（`delete_pattern` 分块 pipeline 删除） | ✅ 单测全绿 |
| 沙箱预热 | workspace_manager 启动预热 + idle 档位（`prewarm_sessions` 延迟 30s） | ✅ prewarm 单测 |
| 依赖季度审查 | 列出升级窗口（delta channel parity 先测） | ✅ `docs/DEPENDENCY_REVIEW.md` |

---

## 六、M4 前端重构（✅ 已完成，skill 驱动，见 EXECUTION_PLAN P6）

- 前端设计**已按 design token 体系实现**（全站 `--color-*` 引用受 tokenRefs 扫描约束；字体栈纯系统字体，CN 可访问）。
- 范围（与后端 1:1）已落地：
  - 意图路由可视化（M2-B 的 reason 面板 → `ReasonPanel.tsx`，决策持久化 `thread.metadata.intent`）
  - 审校报告视图（M2-D issue 列表 → `AuditReportView.tsx`）
  - 记忆浏览器（M2-E chunk 检索结果展示 → `MemoryRecallView.tsx` + `GET /api/v1/memory/recall`）
  - 评测台看板（M2-G report 渲染 → `Evals.tsx` + `GET /api/v1/evals/report` + `/evals` 路由）
- 类型对账完成；回归全绿：`tsc` 0 error + `vitest` 3286 全绿 + `playwright e2e` 11 passed。

---

## 七、执行顺序与节奏

```
本轮起步：M1.1（守卫脚本）→ M1.2（死代码）……然后 M2-B（意图路由，独立可交付）
           ↓
M2-B → M2-D（审校闭环）→ M2-A（深度研究）→ M2-C/E/F → M2-G（评测把上面串起来）
           ↓
M3 性能穿插 → M4 前端（skill 驱动，最后）→ 综合验收
```

- 每完成一个 M2 功能：跑对应单测 + 新增用例 + `evals`（已有 suite 即挂）
- 契约红线：所有数据库变更走 033+；任何 SSE 事件类型变更必须登记事件台账；MCP tool docstring 变更走锁脚本。

---

## 八、本轮明确不做（进入 M5 产品化再议）

推广与 SEO、多租户/组织、渠道扩大（WhatsApp 等）、移动端、桌面签名分发、公开插件市场、报告分享生态、计费与额度商业化。