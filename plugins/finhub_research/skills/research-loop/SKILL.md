---
name: research-loop
description: "研究闭环主线：把 选题观点 → 数据采集 → 建模估值 → 报告产出 → 跟踪维护 → 触发再研究 串成一条可复跑、可追踪、证据可溯的完整研究流程，是 FinHub 的核心产品主线"
license: "FinHub original (Apache-2.0)"
---

# Research Loop（研究闭环主线）

## 定位

FinHub 不是一问一答的金融问答，而是一条**研究闭环**：从一个观点出发，经过数据、建模、报告、跟踪，直到新的信息触发下一轮研究。每个工作区对应一个研究目标，`agent.md` 记录研究状态，所有产出按阶段沉淀，研究跨会话累积。

**触发词**：research loop / 研究闭环 / 开一个研究 / start research / 深度研究 / thesis / 建立观点 / 我要跟踪这个 / initiate coverage。

## 核心原则（贯穿全流程）

1. **证据纪律**：报告里每一个数字都要能指出"来自哪个数据源、什么时间、什么口径"。凡是估算必须标注 `[估算]`，并说明假设。
2. **可证伪**：每个观点必须写清楚"什么证据会推翻它"（falsifiability）。没有 falsifiable 的观点不是观点。
3. **组合关联**：研究结论要落到"对你的 portfolio.json / watchlist 意味着什么"——影响什么持仓、影响多少。
4. **可复跑**：每个阶段产出都存到工作区固定路径，命名规范一致，下次可以增量更新而不是推倒重来。
5. **人机分工**：agent 做数据采集、建模、草拟；关键判断（目标价、买卖动作）必须交还用户确认（HITL）。

## 六阶段工作流

工作区根目录维护 `agent.md`，每一阶段结束都更新它：当前阶段、关键发现、文件索引、待办。

### 阶段 ① 选题与观点（Idea / Thesis）

- 用 `idea-generation` 技能生成候选观点，或接收用户已有观点
- 明确：**公司/标的、多空方向、核心论点（1-2 句）、3-5 个支撑支柱、3-5 个风险、催化剂、目标价/估值锚、止损触发**
- 检查是否 falsifiable；把观点写入工作区 `work/<task>/thesis.md` 并在 `agent.md` 登记
- 关联组合：用 `get_user_data(entity="portfolio")` / `get_watchlist(thread_id)` 判断该标的是否已持仓或关注，标注"已持仓 / 关注中 / 新增"

### 阶段 ② 数据采集（Data）

- 用 native 工具做快速查询：`get_company_overview`（行情、财务、一致预期）、SEC filings（10-K/10-Q/8-K）、`get_market_overview`、`get_daily_prices`
- 用 MCP 做批量/多年分析：fundamentals（多年报表、比率、增长）、price_data（OHLCV）、macro（利率、CPI、经济日历）、options（期权链）、yf_*（Yahoo 套件）
- **为每个关键数字建立证据快照**：`来源 | 工具 | 拉取时间 | 数值 | 口径`，写入 `work/<task>/evidence.md`
- 数据不足时明确标注缺口，不编造；能调用的数据源逐级回退（finhub-data → FMP → Yahoo）

### 阶段 ③ 建模估值（Model）

- 按场景选择技能：`dcf-model`（DCF 估值）、`comps-analysis`（可比公司）、`3-statements`（三表）、`model-update`（更新既有模型）
- 假设必须显式成表：`假设项 | 取值 | 依据/来源 | 敏感性`
- 用 PTC（execute_code）在沙箱里跑模型、做敏感性分析；模型文件存 `work/<task>/model*`，导出 `xlsx`/`html`
- 每个估值结论给出区间和"关键假设变了会怎样"，不报单一伪精确数字

### 阶段 ④ 报告产出（Report）

- 按用途选交付形态：`initiating-coverage`（覆盖报告）、`earnings-analysis` / `earnings-preview`（财报）、`morning-note`（晨报）、`html-report` / `inline-widget` / `interactive-dashboard`（可视化交付）
- **报告必须含证据附录**：跑 `evidence-check` 技能做交付前核验（见下）
- 产出写 `results/`，命名 `YYYY-MM-DD_<task>_<type>.(md|html|docx|xlsx|pdf)`
- 报告结论区明确写：**结论 / 关键依据（带来源）/ 对持仓的含义 / 风险与证伪条件 / 建议下一步**

### 阶段 ⑤ 跟踪维护（Track）

- 用 `thesis-tracker` 维护观点记分卡：支柱状态、风险、催化剂、信心度
- 用 `catalyst-calendar` 维护催化剂日历；关联 earnings calendar 与宏观事件
- 定期用 `market-watch` 刷新自选与价格异动；把组合联动写进 `portfolio.json` 关联说明
- 每次跟踪更新 `agent.md` 的"关键发现"与"最新数据点"，保证下次会话能续上

### 阶段 ⑥ 触发再研究（Trigger）

- 用 `automation` 技能把跟踪做成**自动化**：
  - 时间型：cron（"每周一晨报"、财报季"财报前夜分析"）
  - **价格触发型**：`PriceMonitorService` 订阅实时行情，标的/指数触达价格或涨跌幅条件时自动执行预设指令
- 触发后再进入阶段 ②（数据更新），形成闭环；`agent.md` 记录每次闭环迭代

## 工作区产物规范

```
work/<task>/          # 进行中：thesis.md · evidence.md · model* · data/
results/              # 定稿报告：YYYY-MM-DD_<task>_<type>.*
agent.md              # 工作区状态：目标 · 当前阶段 · 关键发现 · 文件索引 · 闭环历史
```

## 交付检查清单（每个研究交付前必须过）

- [ ] 每个数字有来源 + 拉取时间 + 口径（或标 `[估算]` + 假设）
- [ ] 观点可证伪，写明了证伪条件
- [ ] 结论与组合关联（portfolio/watchlist）已说明
- [ ] 目标价/建议给出区间与敏感性，非伪精确
- [ ] 产出已存 `results/`，命名规范，`agent.md` 已更新
- [ ] 已设置后续触发（cron 或价格触发），闭环未断
