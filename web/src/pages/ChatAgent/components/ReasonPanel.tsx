import React from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Zap } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getThread } from '../utils/api';
import { queryKeys } from '@/lib/queryKeys';
import type { Thread, ThreadIntentDecision } from '@/types/api';

/**
 * M4-1 route-reason panel: explains *why* an auto-routed turn ran on flash
 * vs. ptc. Reads the server-persisted ``metadata.intent`` (written by the
 * intent classifier / messaging route) through GET /threads/{id} — no extra
 * contract, just a render of data the backend already stamps.
 */
export function ReasonPanel({ threadId }: { threadId: string | null }) {
  const { t } = useTranslation();

  const { data: thread } = useQuery({
    queryKey: threadId ? queryKeys.threads.detail(threadId) : queryKeys.threads.all,
    queryFn: () => getThread(threadId!),
    enabled: !!threadId && threadId !== '__default__',
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const intent = (thread as Thread | null | undefined)?.metadata?.intent as
    | ThreadIntentDecision
    | undefined;

  if (!intent) return null;

  const isPtc = intent.mode === 'ptc';
  const percent = Math.round((intent.confidence ?? 0) * 100);

  return (
    <div
      role="note"
      className="mb-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs"
      style={{
        borderColor: 'var(--color-border-muted)',
        background: isPtc ? 'var(--color-bg-subtle)' : undefined,
      }}
    >
      <span
        className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 font-semibold"
        style={{
          borderColor: isPtc
            ? 'rgba(251, 146, 60, 0.35)'
            : 'rgba(96, 165, 250, 0.35)',
          color: isPtc ? 'var(--color-accent-primary)' : '#60a5fa',
          background: isPtc ? 'rgba(251, 146, 60, 0.08)' : 'rgba(96, 165, 250, 0.08)',
        }}
      >
        {isPtc ? <Sparkles className="h-3 w-3" /> : <Zap className="h-3 w-3" />}
        {t(`intent.badge.${isPtc ? 'ptc' : 'flash'}`)}
      </span>
      <div className="min-w-0 flex-1 leading-5">
        <span className="font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          {intent.reason}
        </span>
        <span
          className="ml-2 shrink-0 whitespace-nowrap font-mono text-[10px]"
          style={{ color: 'var(--color-text-quaternary)' }}
        >
          {t('intent.confidence', { percent })}
        </span>
      </div>
    </div>
  );
}

export default ReasonPanel;