import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import {
  parseCron,
  buildCron,
  type ScheduleState,
  type Frequency,
} from './cronUtils';

// ── Day-of-week options ───────────────────────────────────

const DOW_KEYS = [
  { v: 0, k: 'automation.daySun' },
  { v: 1, k: 'automation.dayMon' },
  { v: 2, k: 'automation.dayTue' },
  { v: 3, k: 'automation.dayWed' },
  { v: 4, k: 'automation.dayThu' },
  { v: 5, k: 'automation.dayFri' },
  { v: 6, k: 'automation.daySat' },
];

// ── Component ─────────────────────────────────────────────

interface CronScheduleBuilderProps {
  value: string;
  onChange: (cron: string) => void;
}

export default function CronScheduleBuilder({ value, onChange }: CronScheduleBuilderProps) {
  const { t } = useTranslation();
  const lastEmitted = useRef(value);
  const [state, setState] = useState<ScheduleState>(() => parseCron(value));

  // Sync when parent value changes externally (e.g., template switch)
  useEffect(() => {
    if (value !== lastEmitted.current) {
      setState(parseCron(value));
      lastEmitted.current = value;
    }
  }, [value]);

  // Emit default cron on mount when starting from empty
  useEffect(() => {
    if (!value.trim() && state.frequency !== 'custom') {
      const cron = buildCron(state);
      lastEmitted.current = cron;
      onChange(cron);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = (patch: Partial<ScheduleState>) => {
    const next = { ...state, ...patch };
    const cron = buildCron(next);
    lastEmitted.current = cron;
    setState(next);
    onChange(cron);
  };

  const needsTime = ['daily', 'weekdays', 'weekly', 'monthly'].includes(state.frequency);
  const timeStr = `${String(state.hour).padStart(2, '0')}:${String(state.minute).padStart(2, '0')}`;

  const inputBg = {
    backgroundColor: 'var(--color-bg-card)',
    borderColor: 'var(--color-border-default)',
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        {/* Frequency */}
        <Select
          className="w-40"
          value={state.frequency}
          onChange={(e) => update({ frequency: e.target.value as Frequency })}
        >
          <option value="minutes">{t('automation.freqMinutes')}</option>
          <option value="hourly">{t('automation.freqHourly')}</option>
          <option value="daily">{t('automation.freqDaily')}</option>
          <option value="weekdays">{t('automation.freqWeekdays')}</option>
          <option value="weekly">{t('automation.freqWeekly')}</option>
          <option value="monthly">{t('automation.freqMonthly')}</option>
          <option value="custom">{t('automation.freqCustom')}</option>
        </Select>

        {/* Every N minutes */}
        {state.frequency === 'minutes' && (
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.every')}
            </span>
            <Input
              type="number"
              min={1}
              max={59}
              value={state.interval}
              onChange={(e) => update({ interval: parseInt(e.target.value, 10) || 1 })}
              className="w-20 border"
              style={inputBg}
            />
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.minutes')}
            </span>
          </div>
        )}

        {/* Hourly at minute */}
        {state.frequency === 'hourly' && (
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.atMinute')}
            </span>
            <Select
              className="w-24"
              value={state.minute}
              onChange={(e) => update({ minute: parseInt(e.target.value, 10) })}
            >
              {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                <option key={m} value={m}>:{String(m).padStart(2, '0')}</option>
              ))}
            </Select>
          </div>
        )}

        {/* Day of week */}
        {state.frequency === 'weekly' && (
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.onDay')}
            </span>
            <Select
              className="w-32"
              value={state.dayOfWeek}
              onChange={(e) => update({ dayOfWeek: parseInt(e.target.value, 10) })}
            >
              {DOW_KEYS.map((d) => (
                <option key={d.v} value={d.v}>{t(d.k)}</option>
              ))}
            </Select>
          </div>
        )}

        {/* Day of month */}
        {state.frequency === 'monthly' && (
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.onDay')}
            </span>
            <Select
              className="w-24"
              value={state.dayOfMonth}
              onChange={(e) => update({ dayOfMonth: parseInt(e.target.value, 10) })}
            >
              {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </Select>
          </div>
        )}

        {/* Time */}
        {needsTime && (
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {t('automation.atTime')}
            </span>
            <Input
              type="time"
              value={timeStr}
              onChange={(e) => {
                const [h, m] = (e.target.value || '00:00').split(':').map(Number);
                update({ hour: h || 0, minute: m || 0 });
              }}
              className="w-32 border"
              style={inputBg}
            />
          </div>
        )}
      </div>

      {/* Custom cron fallback */}
      {state.frequency === 'custom' && (
        <div className="flex flex-col gap-1.5">
          <Input
            value={state.raw}
            onChange={(e) => {
              const raw = e.target.value;
              setState((prev) => ({ ...prev, raw }));
              lastEmitted.current = raw;
              onChange(raw);
            }}
            placeholder="*/30 * * * *"
            required
            className="font-mono border placeholder:text-gray-500"
            style={inputBg}
          />
          <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            {t('automation.cronHelp')}
          </span>
        </div>
      )}
    </div>
  );
}
