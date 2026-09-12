export const meta = { name: 'finance_committee', description: '财政部门会议：议题简报 → 部门陈述 → 交叉质询 → 风控把关 → 决议纪要' };

// Prebuilt meeting protocol for the finance department. The lead agent acts
// as chair: it sets the agenda, invites departments, and supplies materials
// (data files, memo paths, or pasted figures) through `args`. Every speaking
// turn is a real subagent dispatch, so the meeting rides the standard
// workflow_lifecycle contract — no bespoke events, no bespoke card.

const DEPARTMENTS = [
  { role: 'accountant', zh: '会计', en: 'Accounting', scope: '凭证、总账、科目余额、结账与报销核算' },
  { role: 'treasury', zh: '资金', en: 'Treasury', scope: '现金流预测、银行对账、资金头寸与收付款计划' },
  { role: 'tax-specialist', zh: '税务', en: 'Tax', scope: '税种计算、申报准备、税负与税收优惠、涉税风险' },
  { role: 'fp-analyst', zh: 'FP&A', en: 'FP&A', scope: '三表分析、盈利/营运/偿债指标、预实差异与经营建议' },
  { role: 'internal-auditor', zh: '内控审计', en: 'Internal Audit', scope: '内控缺陷、舞弊信号、合规检查与整改建议' },
];

// Fixed challenge pairings — each statement is cross-examined by the
// department whose numbers must tie to it (账表勾稽 / 资金对账面 / 税负对利润…).
const CHALLENGERS = {
  'accountant': 'fp-analyst',
  'treasury': 'accountant',
  'tax-specialist': 'fp-analyst',
  'fp-analyst': 'treasury',
  'internal-auditor': 'accountant',
};

const topic = (args && args.topic) || '';
if (!topic) throw new Error('finance_committee requires args.topic (会议议题)');
const background = (args && args.background) || '';
const materials = (args && args.materials) || '';
const language = (args && args.language) || 'zh';
const decisionsNeeded = (args && args.decisions_needed) || '';

const invitable = new Set(DEPARTMENTS.map((d) => d.role));
let invited = Array.isArray(args && args.roles) && args.roles.length > 0
  ? args.roles.filter((r) => invitable.has(r))
  : DEPARTMENTS.map((d) => d.role);
if (invited.indexOf('internal-auditor') === -1) invited = invited.concat(['internal-auditor']);
const deptOf = {};
for (const d of DEPARTMENTS) deptOf[d.role] = d;

const langLine = language === 'en'
  ? 'Write all content values in English.'
  : '所有文本内容使用简体中文。';

const BRIEF = [
  '财政部门会议（书面审议制）——你是与会部门代表。',
  '议题：' + topic,
  background ? '背景：' + background : '',
  materials ? '会议材料（数据/文件路径，须实际读取核对，禁止编造）：\n' + materials : '',
  decisionsNeeded ? '需要会议裁定的问题：' + decisionsNeeded : '',
].filter(Boolean).join('\n');

phase('agenda');
log('议题：' + topic);
log('列席部门：' + invited.map((r) => deptOf[r].zh + '(' + r + ')').join('、'));

const STATEMENT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['department', 'position', 'key_numbers', 'risks', 'recommendations', 'assumptions'],
  properties: {
    department: { type: 'string' },
    position: { type: 'string', description: '本部门核心结论，不超过300字' },
    key_numbers: {
      type: 'array',
      items: {
        type: 'object',
        required: ['item', 'value', 'basis'],
        properties: { item: { type: 'string' }, value: { type: 'string' }, basis: { type: 'string', description: '数据来源或计算口径' } },
      },
    },
    risks: { type: 'array', items: { type: 'string' } },
    recommendations: { type: 'array', items: { type: 'string' } },
    assumptions: { type: 'array', items: { type: 'string' } },
  },
};

const statementPrompt = (d) =>
  BRIEF + '\n\n' +
  '以「' + d.zh + '（' + d.role + '）」部门立场出具书面意见，职责范围：' + d.scope + '。\n' +
  '要求：结论必须有材料中的数据支撑，每个关键数字给出来源或计算口径；材料不足时明确说' +
  '「材料未提供」，禁止臆测。' + langLine + ' 只输出符合 schema 的 JSON。';

phase('statements');
const statementResults = await parallel(
  invited.map((r) => () => agent(statementPrompt(deptOf[r]), {
    agentType: r,
    label: 'statement · ' + r,
    phase: 'statements',
    schema: STATEMENT_SCHEMA,
  }))
);
// Pair each statement with its invited role positionally — the child's
// `department` field is free text and can't be keyed on.
const statements = [];
for (let i = 0; i < invited.length; i++) {
  const s = statementResults[i];
  if (s && s.position) {
    s.department = deptOf[invited[i]].zh;
    statements.push({ role: invited[i], data: s });
  } else {
    log(deptOf[invited[i]].zh + ' 陈述缺席（子代理未返回有效意见）');
  }
}
const present = statements.map((p) => deptOf[p.role].zh);

const CROSS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['challenger', 'challenges', 'agreements'],
  properties: {
    challenger: { type: 'string' },
    challenges: {
      type: 'array',
      items: {
        type: 'object',
        required: ['target', 'issue', 'question'],
        properties: { target: { type: 'string' }, issue: { type: 'string' }, question: { type: 'string' } },
      },
    },
    agreements: { type: 'array', items: { type: 'string' } },
  },
};

phase('cross-examination');
const crossTasks = [];
for (const p of statements) {
  let challenger = CHALLENGERS[p.role];
  if (!invited.includes(challenger) || challenger === p.role) {
    challenger = invited.find((r) => r !== p.role) || 'fp-analyst';
  }
  crossTasks.push(() => agent(
    BRIEF + '\n\n' +
    '你是「' + deptOf[challenger].zh + '（' + challenger + '）」，正在质询 ' + p.data.department + ' 的部门陈述：\n' +
    JSON.stringify(p.data, null, 1) + '\n\n' +
    '从本部门数据勾稽关系出发，挑出口径不一致、数字对不上、假设不成立之处，逐条提出质询；' +
    '认可的部分也要写明。不得编造材料之外的数字。' + langLine + ' 只输出符合 schema 的 JSON。',
    { agentType: challenger, label: 'challenge · ' + p.role, phase: 'cross-examination', schema: CROSS_SCHEMA }
  ));
}
const crossResults = (await parallel(crossTasks)).filter((c) => c && c.challenges);
const crossSummary = crossResults.length > 0 ? JSON.stringify(crossResults, null, 1) : '（无有效质询记录）';

phase('risk-gate');
let gate = null;
try {
  gate = await agent(
    BRIEF + '\n\n' +
    '你是内控审计专员，代表风险把关席。以下是各部门陈述与交叉质询记录：\n' +
    JSON.stringify(statements, null, 1) + '\n' + crossSummary + '\n\n' +
    '出具风控结论：verdict 取 approve / approve_with_conditions / reject 之一；' +
    'reject 或 approve_with_conditions 时给出必须整改的事项与放行条件；' +
    'reject 时还必须给出 blocking_actions（整改完成前不得执行的行动清单）。' +
    '结论只依据上述记录与材料，不得臆测。' + langLine + ' 只输出符合 schema 的 JSON。',
    {
      agentType: 'internal-auditor',
      label: 'risk gate',
      phase: 'risk-gate',
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['verdict', 'concerns', 'conditions', 'required_actions', 'blocking_actions'],
        properties: {
          verdict: { type: 'string', enum: ['approve', 'approve_with_conditions', 'reject'] },
          concerns: { type: 'array', items: { type: 'string' } },
          conditions: { type: 'array', items: { type: 'string' } },
          required_actions: { type: 'array', items: { type: 'string' } },
          blocking_actions: { type: 'array', items: { type: 'string' }, description: 'reject 时：在整改完成前不得执行的事项' },
        },
      },
    }
  );
} catch (e) {
  log('风控把关席缺席：' + e);
}

phase('minutes');
let minutes = null;
try {
  minutes = await agent(
    '财政部门会议决议纪要。议题：' + topic + '\n' +
    (background ? '背景：' + background + '\n' : '') +
    (decisionsNeeded ? '需裁定问题：' + decisionsNeeded + '\n' : '') +
    '\n会议记录（部门陈述）：\n' + JSON.stringify(statements, null, 1) +
    '\n\n交叉质询：\n' + crossSummary +
    '\n\n风控把关结论：\n' + (gate ? JSON.stringify(gate, null, 1) : '（风控席缺席）') +
    '\n\n要求：' +
    '1) resolution 给出会议主决议与推荐执行方案；' +
    '2) dissent 逐条保留未决分歧、缺席部门意见与风控保留条件（不得为了统一口径抹平分歧）；' +
    '3) actions 为可执行任务清单，负责人填部门名；若风控 reject，把 blocking_actions 逐条列为 high 优先级行动；' +
    '4) financial_impact 用一段话给出量化影响（金额口径与来源）；' +
    '5) 只依据会议记录，不得新增编造数据。' + langLine + ' 只输出符合 schema 的 JSON。',
    {
      agentType: invited.includes('fp-analyst') ? 'fp-analyst' : 'general-purpose',
      label: 'minutes',
      phase: 'minutes',
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['topic', 'attendees', 'missing_departments', 'resolution', 'dissent', 'risk_gate', 'actions', 'financial_impact'],
        properties: {
          topic: { type: 'string' },
          attendees: { type: 'array', items: { type: 'string' } },
          missing_departments: { type: 'array', items: { type: 'string' } },
          resolution: { type: 'string' },
          dissent: { type: 'array', items: { type: 'string' } },
          risk_gate: { type: 'string', description: '风控结论摘要（verdict + 关键条件）' },
          actions: {
            type: 'array',
            items: {
              type: 'object',
              required: ['task', 'owner', 'priority'],
              properties: { task: { type: 'string' }, owner: { type: 'string' }, priority: { type: 'string', enum: ['high', 'medium', 'low'] } },
            },
          },
          financial_impact: { type: 'string' },
        },
      },
    }
  );
} catch (e) {
  log('纪要席缺席：' + e);
}

const missing = invited.filter((r) => present.indexOf(deptOf[r].zh) < 0 && present.indexOf(r) < 0).map((r) => deptOf[r].zh);

if (!minutes) {
  return {
    topic: topic,
    attendees: present,
    missing_departments: missing,
    resolution: '（纪要席未产出决议——综合子代理失败；完整记录见 children 存档与上方陈述）',
    dissent: statements.map((p) => p.data.department + '：' + p.data.position),
    risk_gate: gate ? '风控 ' + gate.verdict + '：' + (gate.conditions.join('；') || '无条件') : '风控席缺席',
    actions: [],
    financial_impact: '未量化',
    synthesis_failed: true,
    verification: {
      passed: false,
      unverified_claims: [],
      contradictions: [],
      missing_conditions: [],
      note: '纪要席缺席，无纪要可核',
    },
  };
}

minutes.missing_departments = missing;
minutes.attendees = present;

phase('verification');
// Quality gate: an independent verifier cross-checks the minutes against the
// record (M2-D style — the producer can't grade its own draft).
let verification = null;
try {
  verification = await agent(
    '你是独立核稿人。以下是会议决议纪要，以及全部会议记录（部门陈述 + 交叉质询 + 风控结论）：\n' +
    '【纪要】\n' + JSON.stringify(minutes, null, 1) +
    '\n【会议记录】\n' + JSON.stringify(statements, null, 1) +
    '\n【质询】\n' + crossSummary +
    '\n【风控】\n' + (gate ? JSON.stringify(gate, null, 1) : '缺席') + '\n\n' +
    '逐条核对：1) 纪要中每个数字/结论能否在记录中找到来源（找不到 → unverified，说明出现在纪要的哪个字段）；' +
    '2) 纪要是否与记录矛盾（记录说 A，纪要写 B → contradictions）；' +
    '3) 风控保留条件是否已写入 dissent 或 actions（漏写 → missing_conditions）。' +
    '没有问题的项给空数组。' + langLine + ' 只输出符合 schema 的 JSON。',
    {
      agentType: 'general-purpose',
      label: 'verification',
      phase: 'verification',
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['unverified_claims', 'contradictions', 'missing_conditions', 'passed'],
        properties: {
          unverified_claims: { type: 'array', items: { type: 'string' }, description: '纪要中找不到记录来源的数字或论断（含所在字段）' },
          contradictions: { type: 'array', items: { type: 'string' }, description: '纪要与会议记录矛盾之处' },
          missing_conditions: { type: 'array', items: { type: 'string' }, description: '风控保留条件未写入纪要之处' },
          passed: { type: 'boolean', description: '三项全空时才是 true' },
        },
      },
    }
  );
} catch (e) {
  log('核稿缺席（不影响纪要交付）：' + e);
}

if (verification) {
  minutes.verification = {
    passed: verification.passed,
    unverified_claims: verification.unverified_claims,
    contradictions: verification.contradictions,
    missing_conditions: verification.missing_conditions,
  };
  if (!verification.passed) {
    log('核稿未通过：' + [
      verification.unverified_claims.length + ' 条未溯源',
      verification.contradictions.length + ' 处矛盾',
      verification.missing_conditions.length + ' 条遗漏风控条件',
    ].join('、'));
  }
} else {
  minutes.verification = {
    passed: false,
    unverified_claims: [],
    contradictions: [],
    missing_conditions: [],
    note: '核稿子代理未返回有效结果，纪要未经独立核对',
  };
}

return minutes;
