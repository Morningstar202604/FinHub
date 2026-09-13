## intent — 12/12 passed
- [PASS] '深估值任务→PTC': want ptc, got ptc (strong ptc signal keyword)
- [PASS] '代码任务→PTC': want ptc, got ptc (strong ptc signal keyword)
- [PASS] '回测任务→PTC': want ptc, got ptc (strong ptc signal keyword)
- [PASS] '问候→Flash': want flash, got flash (strong flash signal keyword)
- [PASS] '感谢→Flash': want flash, got flash (strong flash signal keyword)
- [PASS] '解释→Flash': want flash, got flash (strong flash signal keyword)
- [PASS] '多指标对比→PTC': want ptc, got ptc (normal ptc signals outrank flash (5> 0))
- [PASS] '简单报价→Flash': want flash, got flash (strong flash signal keyword)
- [PASS] '无工作区弱信号→Flash': want flash, got flash (ptc requires a workspace; none available)
- [PASS] '计划模式→PTC': want ptc, got ptc (plan mode requested)
- [PASS] '闲聊→Flash': want flash, got flash (default quick path (workspace optional))
- [PASS] '深度研究→PTC': want ptc, got ptc (strong ptc signal keyword)

## auditor — 6/6 passed
- [PASS] '基准偏差→报错': expect error -> 1 error(s): 数字与基准不符: 营收 文本值 ¥12.4B vs 基准 18000.0 (偏差 31.1%，阈值 2.0%)
- [PASS] '基准一致→通过': expect pass -> no errors
- [PASS] '无引用→报错': expect error -> 3 error(s): 关键论断「毛利率」附近未发现对应数据来源; 关键论断「毛利率」附近未发现对应数据来源
- [PASS] '有引用→通过': expect pass -> no errors
- [PASS] '矛盾数值→报错': expect error -> 1 error(s): 文字内 毛利率 出现矛盾数值: 55%, 45%
- [PASS] '一致文本→通过': expect pass -> no errors

## research_fallback — 3/3 passed
- [PASS] empty provider chain -> provider=none
- [PASS] retryable fallback -> provider=parallel citations=1
- [PASS] fatal error stops chain -> provider=['exa', 'parallel'] error=yes

## finance_committee — 9/9 passed
- [PASS] 'accountant · statement': agentType=accountant; sample parsed (keys=6)
- [PASS] 'treasury · statement': agentType=treasury; sample parsed (keys=6)
- [PASS] 'tax-specialist · statement': agentType=tax-specialist; sample parsed (keys=6)
- [PASS] 'fp-analyst · statement': agentType=fp-analyst; sample parsed (keys=6)
- [PASS] 'internal-auditor · statement': agentType=internal-auditor; sample parsed (keys=6)
- [PASS] 'fp-analyst · challenge': agentType=fp-analyst; sample parsed (keys=3)
- [PASS] 'internal-auditor · risk gate': agentType=internal-auditor; sample parsed (keys=5)
- [PASS] 'fp-analyst · minutes': agentType=fp-analyst; sample parsed (keys=8)
- [PASS] 'general-purpose · verification': agentType=general-purpose; sample parsed (keys=4)

**总评: 30/30 通过 (4304 ms) — ✅ ALL GREEN**
