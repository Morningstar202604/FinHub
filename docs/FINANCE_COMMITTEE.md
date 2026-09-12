# 财政部门会议（Finance Committee Meeting）架构

对标 TradingAgents（arXiv 2412.20138）的多角色分析师→辩论→风控→决策流水线，
把 FinHub 的「一个会财务的聊天代理」升级为「以会议方式协作的财政部门智能体」。

## 总览

三层，全部复用既有机制，不新增 SSE 事件类型（ROADMAP 铁律：契约不改）：

| 层 | 载体 | 说明 |
|---|---|---|
| 角色层 | `BUILTIN_SUBAGENTS` + `roles/finance_*.md.j2` | 会计/资金/税务/FP&A/内控五角色从 agent_config.yaml 用户定义升格为一等内建 |
| 会议层 | `workflows/finance_committee/workflow.js`（预置 RunWorkflow） | 会议协议：议题→部门陈述→交叉质询→风控把关→决议纪要 |
| 呈现层 | WorkflowRunCard / WorkflowRunDetail + 角色身份映射 | 复用 workflow_lifecycle 契约；phase/子代理行渲染为会议发言 |

## 会议协议（finance_committee）

```
args = { topic, background?, materials?, roles?, language?, decisions_needed? }

phase 1  agenda          主席（lead agent）已给定议题；script 内组议程简报，不派发子代理
phase 2  statements      parallel(): 每个受邀角色一个子代理，JSON-schema 意见单
phase 3  cross           每份陈述由一个对口角色质询（数字对账/口径挑战），带 schema
phase 4  gate            internal-auditor 审阅全部意见+质询，出具风控结论（verdict/条件/
                         blocking_actions——reject 时必须列出整改完成前不得执行的行动）
phase 5  minutes         fp-analyst（未受邀时 general-purpose）综合成结构化决议纪要
phase 6  verification    独立核稿（general-purpose）：纪要逐条对照会议记录，
                         输出 unverified_claims / contradictions / missing_conditions / passed
return   纪要对象（含 verification 块）→ result.json / result_preview → 前端 StructuredResultBlock
```

- 派发预算：5 陈述 + 5 质询 + 1 把关 + 1 纪要 + 1 核稿 ≤ 13，远低于 max_dispatches_per_run=64；
  并发陈述 5 ≤ max_concurrent_children=8。
- 子代理失败吸收为 null（prelude 契约），script 全程 null-safe；纪要必须标注缺席部门。
- gate 不阻断会议：风控不认可时纪要中保留 dissent 与整改条件（blocking_actions 进
  high 优先级 actions），决议权在用户（主席呈报）。
- 质量门（对标 M2-D 审校器）：纪要生产者不能给自己的草稿打分——verification 是
  独立子代理核对纪要与记录的一致性；核稿缺席时纪要带 `verification.passed=false`
  + note，主席必须向用户明示「未经独立核对」，不得自行补数字。
- 质询配对（固定，可解释）：accountant↔fp-analyst（账表勾稽）、treasury↔accountant
  （资金与账面）、tax-specialist↔fp-analyst（税负与利润口径）、fp-analyst↔treasury
  （预测与现金流）、internal-auditor↔accountant（凭证与内控）。缺席方由在场角色顶替。
- language 默认 zh：children 的 schema 要求内容字段用目标语言，键名保持英文（机器可读）。

## 角色层迁移

- `builtins.py` 新增 5 个 SubagentDefinition，`role_prompt_template: roles/finance_*.md.j2`；
  模板内容承接 agent_config.yaml 原 role_prompt（职责/工作要求），并补齐
  researcher.md.j2 式的 <task>/<guidelines>/<output_format> 结构。
- YAML 删除这 5 个 definitions（enabled 列表保留 —— 与内建同名，语义不变）；
  SubagentRegistry 同名用户覆盖仍可用（想改人格的操作者写 YAML 即可，日志有记录）。
- 单一权威从此是 builtins；YAML 只是 override 通道。

## 契约与红线

- 事件：会议进度全部走已注册的 `workflow_lifecycle`（run_started/phase/log/
  child_started/child_done/run_completed），零新增事件类型。
- 多 worker：预置 registry 是 cwd 锚定的只读缓存（get_prebuilt_workflows @cache），
  无进程态；run 真值仍在 ledger/checkpoint。
- docstring 锁：不触碰 MCP 工具 docstring。
- 部署：`workflows/` 此前无人 COPY（目录为空、M1.4 删过死代码）；预置 workflow 落地后
  Dockerfile.dev / Dockerfile.backend 加 COPY，docker-compose.dev 挂载热更新。

## 前端呈现

- 角色身份表 `MEETING_ROLE_UI`（workflowRunUtils.ts，per-kind 展示表的既定归属）：
  subagentType → i18n 部门名 + 展示色（仅 text/border token，遵守 DESIGN.md）。
- 子代理行的 type 单元：命中角色表时显示本地化部门名（如「税务专员 / Tax」），否则照旧。
- phase 单元：命中 `chat.meeting.phase.*` 键时显示本地化议程环节名，否则显示原 phase 标题
  （用户自写 workflow 的中文 phase 不受影响）。
- 纪要：run_completed.resultPreview 已有 StructuredResultBlock 结构化渲染，不加新组件。
- i18n：en-US / zh-CN / ja-JP 同步补键（DESIGN.md：一个 change 内两主题、全语言）。

## 主席行为（提示词）

system.md.j2：`<finance_department>` 改为「部门名册 + 会议召集规则」——
单一专业问题 → Task() 直达对应角色；跨部门交付（月度结账评审、预算决议、涉税决策、
内控整改……）→ RunWorkflow(workflow:"finance_committee")，主席负责给议题、
读纪要、向用户呈报并执行决议。新增 components/finance_meeting.md.j2 组件说明协议。
