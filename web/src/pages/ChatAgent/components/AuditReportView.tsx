import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from 'lucide-react';

/**
 * M4-2 audit-report view: renders the self-verification findings produced by
 * ``audit_research_numbers`` (ROADMAP M2-D). The tool delivers
 * ``content_and_artifact`` — the artifact carries ``{report_text, findings}``
 * where each finding is ``{level, kind, message, evidence?, threshold_delta?}``.
 * Rendered inside the tool-call detail view; the message-list inline card is
 * registered separately (see INLINE_ARTIFACT_MAP).
 */

export interface AuditFinding {
  level: 'info' | 'warning' | 'error';
  kind: 'noverify' | 'uncited' | 'conflict';
  message: string;
  evidence?: string;
  threshold_delta?: number | null;
}

export interface AuditReportData {
  report_text?: string;
  findings?: AuditFinding[];
  passed?: boolean;
  errors?: number;
  warnings?: number;
}

const LEVEL_ICON = {
  error: ShieldAlert,
  warning: AlertTriangle,
  info: Info,
} as const;

const LEVEL_COLOR = {
  error: 'var(--color-loss, #f85149)',
  warning: 'var(--color-warning, #fbbf24)',
  info: 'var(--color-text-tertiary)',
} as const;

function isAuditReport(value: unknown): value is AuditReportData {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return 'findings' in v || 'report_text' in v;
}

export function AuditReportView({ artifact }: { artifact?: Record<string, unknown> }) {
  const { t } = useTranslation();
  if (!artifact || !isAuditReport(artifact)) return null;
  const findings = (artifact.findings ?? []) as AuditFinding[];
  if (findings.length === 0) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border px-3 py-2.5 text-xs"
        style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}
      >
        <CheckCircle2 className="h-4 w-4" style={{ color: '#34d399' }} />
        <span>{t('intent.auditPassed', { defaultValue: '审校通过：未发现数值/引用/矛盾问题。' })}</span>
      </div>
    );
  }
  const errorCount = findings.filter((f) => f.level === 'error').length;
  return (
    <div
      className="flex flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-xs"
      style={{ borderColor: 'var(--color-border-muted)', background: 'var(--color-bg-subtle)' }}
    >
      <div className="flex items-center gap-2 font-semibold" style={{ color: 'var(--color-text-primary)' }}>
        <ShieldAlert className="h-4 w-4" style={{ color: errorCount > 0 ? LEVEL_COLOR.error : 'var(--color-text-tertiary)' }} />
        {errorCount > 0
          ? t('intent.auditFound', { count: findings.length, defaultValue: '审校发现 {{count}} 项问题' })
          : t('intent.auditWarnings', { count: findings.length, defaultValue: '审校提示 {{count}} 项' })}
      </div>
      {findings.map((f, i) => {
        const Icon = LEVEL_ICON[f.level] ?? Info;
        return (
          <div key={i} className="flex items-start gap-2 leading-5">
            <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: LEVEL_COLOR[f.level] }} />
            <div className="min-w-0 flex-1">
              <span style={{ color: 'var(--color-text-secondary)' }}>{f.message}</span>
              {f.evidence ? (
                <span className="block truncate font-mono text-[10px]" style={{ color: 'var(--color-text-quaternary)' }}>
                  {f.evidence}
                </span>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default AuditReportView;