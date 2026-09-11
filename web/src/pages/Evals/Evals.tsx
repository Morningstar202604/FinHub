import React from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Clock, FlaskConical, RefreshCw, XCircle } from 'lucide-react';
import { api } from '@/api/client';

/**
 * M4-4 evals dashboard: renders the last harness report served read-only by
 * GET /api/v1/evals/report (produced by `uv run python -m evals run all`).
 * Pure client — no writes, no re-runs; a 404 (no report yet) renders an
 * empty-state explaining how to produce one.
 */

interface SuiteSummary {
  passed: number;
  total: number;
}

type EvalsReport = {
  ok: boolean;
  passed: number;
  total: number;
  duration_ms: number;
  suites?: Record<string, SuiteSummary>;
  detail?: { line: string }[];
};

export default function Evals() {
  const { t } = useTranslation();

  const { data, status, refetch, isFetching } = useQuery({
    queryKey: ['evals', 'report'],
    queryFn: async (): Promise<EvalsReport> => {
      const { data: body } = await api.get<EvalsReport>('/api/v1/evals/report');
      return body;
    },
    staleTime: 60_000,
    retry: (failureCount, error) => {
      // A 404 means "no report yet" — show the empty state, avoid retry loops.
      const apiError = error as { response?: { status?: number } };
      return failureCount < 1 && apiError.response?.status !== 404;
    },
  });

  const suites = data?.suites ?? {};
  const suiteNames = Object.keys(suites);

  return (
    <div className="h-full w-full overflow-y-auto" style={{ background: 'var(--color-bg-page)' }}>
      <div className="mx-auto max-w-4xl px-6 py-6">
        <div className="mb-6 flex items-center gap-3">
          <span
            className="flex h-10 w-10 items-center justify-center rounded-xl"
            style={{ background: 'var(--color-bg-tool-card)', color: 'var(--color-accent-primary)' }}
          >
            <FlaskConical className="h-5 w-5" />
          </span>
          <div className="flex-1">
            <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {t('evals.title')}
            </h1>
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('evals.subtitle')}
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
            style={{
              borderColor: 'var(--color-border-default)',
              color: 'var(--color-text-secondary)',
              background: 'var(--color-bg-card)',
            }}
            disabled={isFetching}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            {t('evals.refresh')}
          </button>
        </div>

        {status === 'pending' ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
            <RefreshCw className="h-4 w-4 animate-spin" />
            {t('evals.loading')}
          </div>
        ) : status === 'error' || !data ? (
          <div
            className="rounded-lg border px-4 py-6 text-center"
            style={{ borderColor: 'var(--color-border-muted)', background: 'var(--color-bg-subtle)' }}
          >
            <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              {t('evals.empty')}
            </p>
            <code
              className="mt-2 inline-block rounded px-2 py-1 font-mono text-[11px]"
              style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-muted)' }}
            >
              uv run python -m evals run all
            </code>
          </div>
        ) : (
          <>
            {/* Overall scorecard */}
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <ScoreCard
                label={t('evals.passedRate')}
                value={`${data.passed}/${data.total}`}
                tone={data.ok ? 'green' : 'red'}
                icon={data.ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
              />
              <ScoreCard
                label={t('evals.suites')}
                value={`${suiteNames.length}`}
                tone="neutral"
                icon={<FlaskConical className="h-4 w-4" />}
              />
              <ScoreCard
                label={t('evals.duration')}
                value={`${(data.duration_ms / 1000).toFixed(1)}s`}
                tone="neutral"
                icon={<Clock className="h-4 w-4" />}
              />
            </div>

            {/* Per-suite table */}
            <div
              className="overflow-hidden rounded-lg border"
              style={{ borderColor: 'var(--color-border-default)', background: 'var(--color-bg-card)' }}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ color: 'var(--color-text-tertiary)', fontSize: 11 }}>
                    <th className="px-4 py-2 text-left font-medium">{t('evals.suite')}</th>
                    <th className="px-4 py-2 text-right font-medium">{t('evals.result')}</th>
                    <th className="px-4 py-2 text-right font-medium">{t('evals.rate')}</th>
                  </tr>
                </thead>
                <tbody>
                  {suiteNames.length === 0 ? (
                    <tr>
                      <td className="px-4 py-4 text-center" colSpan={3} style={{ color: 'var(--color-text-tertiary)' }}>
                        {t('evals.noSuites')}
                      </td>
                    </tr>
                  ) : (
                    suiteNames.map((name) => {
                      const s = suites[name];
                      const ok = s.total > 0 && s.passed === s.total;
                      return (
                        <tr key={name} style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                          <td className="px-4 py-2.5 font-mono text-xs" style={{ color: 'var(--color-text-primary)' }}>
                            {name}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span
                              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                              style={{
                                color: ok ? 'var(--color-profit)' : 'var(--color-loss)',
                                background: ok ? 'rgba(52, 211, 153, 0.08)' : 'rgba(248, 113, 113, 0.08)',
                              }}
                            >
                              {ok ? 'PASS' : 'FAIL'}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                            {s.passed}/{s.total}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Detail list */}
            {data.detail && data.detail.length > 0 && (
              <div className="mt-4 space-y-1">
                {data.detail.map((d, i) => (
                  <div
                    key={i}
                    className="rounded px-3 py-1.5 font-mono text-[11px]"
                    style={{ color: 'var(--color-text-quaternary)', background: 'var(--color-bg-subtle)' }}
                  >
                    {d.line}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ScoreCard({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: string;
  tone: 'green' | 'red' | 'neutral';
  icon: React.ReactElement;
}) {
  const color =
    tone === 'green' ? 'var(--color-profit)' : tone === 'red' ? 'var(--color-loss)' : 'var(--color-text-secondary)';
  return (
    <div
      className="rounded-lg border px-4 py-3"
      style={{ borderColor: 'var(--color-border-default)', background: 'var(--color-bg-card)' }}
    >
      <div className="flex items-center gap-2" style={{ color }}>
        {icon}
        <span className="text-[11px] font-medium uppercase tracking-wide" style={{ color: 'var(--color-text-tertiary)' }}>
          {label}
        </span>
      </div>
      <div className="mt-1.5 font-mono text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
        {value}
      </div>
    </div>
  );
}