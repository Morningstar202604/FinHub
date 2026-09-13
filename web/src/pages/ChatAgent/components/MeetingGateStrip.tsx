import { useTranslation } from 'react-i18next';
import { AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { StructuredResult } from '../utils/structuredResult';

/**
 * Quality-gate strip for a finance-committee minutes object. The workflow's
 * result already renders as generic fields below; this surfaces only the
 * adjudication — verification.passed and the risk-gate verdict — as
 * status, because those two fields change what the reader should do with
 * the minutes (draft vs record, proceed vs hold).
 */

type Structured = Record<string, unknown>;

function asObject(value: unknown): Structured | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Structured)
    : null;
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

function firstText(value: unknown): string {
  if (Array.isArray(value)) return asText(value[0]);
  return asText(value);
}

function countIssues(verification: Structured): number {
  return [
    'unverified_claims',
    'contradictions',
    'missing_conditions',
  ].reduce(
    (sum, key) => sum + (Array.isArray(verification[key]) ? (verification[key] as unknown[]).length : 0),
    0,
  );
}

interface MeetingGateStripProps {
  result: StructuredResult;
}

export default function MeetingGateStrip({ result }: MeetingGateStripProps) {
  const { t } = useTranslation();
  const record = Object.fromEntries(result.entries) as Structured;
  const verification = asObject(record.verification);
  const gate = asObject(record.risk_gate);

  const hasGate = gate !== null;
  if (!verification && !hasGate) return null;

  const passed = verification ? verification.passed === true : false;
  const gateText = hasGate
    ? asText(gate?.risk_gate) || asText(gate?.verdict)
    : '';
  const gateVerdict =
    (gate ? asText(gate.verdict) : null) ??
    (gateText && /reject/i.test(gateText) ? 'reject' : null);
  const gateWarn =
    gateVerdict === 'reject' || gateVerdict === 'approve_with_conditions';

  const items: { testid: string; Icon: typeof ShieldCheck; text: string; warn: boolean }[] = [];

  if (verification) {
    const note = asText(verification.note);
    const failed = !passed && (countIssues(verification) > 0 || note !== '');
    items.push({
      testid: 'meeting-verification',
      Icon: failed ? AlertTriangle : ShieldCheck,
      text: passed
        ? t('chat.meeting.verificationPassed')
        : note
          ? t('chat.meeting.verificationUnverifiedNote')
          : t('chat.meeting.verificationUnverified'),
      warn: !passed,
    });
  }

  if (hasGate) {
    const conditions = firstText(gate?.conditions ?? gate?.blocking_actions);
    const verdictKey = gateVerdict
      ? `chat.meeting.verdict.${gateVerdict === 'approve_with_conditions' ? 'approveWithConditions' : gateVerdict}`
      : null;
    items.push({
      testid: 'meeting-risk-gate',
      Icon: gateWarn ? ShieldAlert : ShieldCheck,
      text: verdictKey
        ? t('chat.meeting.riskGateSummary', {
            verdict: t(verdictKey),
            conditions: conditions || '—',
          })
        : gateText || firstText(gate?.conditions) || '—',
      warn: gateWarn,
    });
  }

  return (
    <div
      className="flex flex-col gap-1.5"
      style={{ marginTop: 4, fontSize: '0.75rem' }}
      data-testid="meeting-gate-strip"
    >
      {items.map(({ testid, Icon, text, warn }) => (
        <div
          key={testid}
          className="flex items-start gap-1.5"
          data-testid={testid}
          style={{ color: warn ? 'var(--color-warning)' : 'var(--color-text-secondary)' }}
        >
          <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <span style={{ wordBreak: 'break-word' }}>{text}</span>
        </div>
      ))}
    </div>
  );
}
