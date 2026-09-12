// ── Types ─────────────────────────────────────────────────

export type Frequency = 'minutes' | 'hourly' | 'daily' | 'weekdays' | 'weekly' | 'monthly' | 'custom';

export interface ScheduleState {
  frequency: Frequency;
  interval: number;
  minute: number;
  hour: number;
  dayOfWeek: number;
  dayOfMonth: number;
  raw: string;
}

// ── Parse / Build ─────────────────────────────────────────

const DEFAULTS: ScheduleState = {
  frequency: 'daily',
  interval: 30,
  minute: 0,
  hour: 9,
  dayOfWeek: 1,
  dayOfMonth: 1,
  raw: '',
};

export function parseCron(expr: string): ScheduleState {
  const raw = expr.trim();
  if (!raw) return { ...DEFAULTS };

  const parts = raw.split(/\s+/);
  if (parts.length !== 5) return { ...DEFAULTS, frequency: 'custom', raw };

  const [min, hr, dom, mon, dow] = parts;

  // */N * * * *
  if (min.startsWith('*/') && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
    const n = parseInt(min.slice(2), 10);
    if (n > 0 && n <= 59) return { ...DEFAULTS, frequency: 'minutes', interval: n, raw };
  }

  // M * * * *
  if (/^\d+$/.test(min) && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
    return { ...DEFAULTS, frequency: 'hourly', minute: parseInt(min, 10), raw };
  }

  if (!/^\d+$/.test(min) || !/^\d+$/.test(hr)) return { ...DEFAULTS, frequency: 'custom', raw };

  const m = parseInt(min, 10);
  const h = parseInt(hr, 10);

  if (dom === '*' && mon === '*' && dow === '1-5') return { ...DEFAULTS, frequency: 'weekdays', minute: m, hour: h, raw };
  if (dom === '*' && mon === '*' && /^[0-6]$/.test(dow)) return { ...DEFAULTS, frequency: 'weekly', minute: m, hour: h, dayOfWeek: parseInt(dow, 10), raw };
  if (dom === '*' && mon === '*' && dow === '*') return { ...DEFAULTS, frequency: 'daily', minute: m, hour: h, raw };
  if (/^\d+$/.test(dom) && mon === '*' && dow === '*') return { ...DEFAULTS, frequency: 'monthly', minute: m, hour: h, dayOfMonth: parseInt(dom, 10), raw };

  return { ...DEFAULTS, frequency: 'custom', raw };
}

export function buildCron(s: ScheduleState): string {
  switch (s.frequency) {
    case 'minutes': return `*/${s.interval} * * * *`;
    case 'hourly': return `${s.minute} * * * *`;
    case 'daily': return `${s.minute} ${s.hour} * * *`;
    case 'weekdays': return `${s.minute} ${s.hour} * * 1-5`;
    case 'weekly': return `${s.minute} ${s.hour} * * ${s.dayOfWeek}`;
    case 'monthly': return `${s.minute} ${s.hour} ${s.dayOfMonth} * *`;
    case 'custom': return s.raw;
  }
}
