import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, SearchX, Sparkles } from 'lucide-react';
import { Loader } from '@/components/ui/loader';
import { useMemoryRecall } from '../hooks/useMemory';
import type { MemoryRecallHit } from '../utils/api';

type Tier = 'user' | 'workspace';

interface MemoryRecallViewProps {
  tier: Tier;
  workspaceId: string | null;
  /** Navigate to the source memory file when a hit's source chip is clicked. */
  onOpenSource?: (key: string, tier: Tier) => void;
}

function scoreLabel(score: number): string {
  return (score * 100).toFixed(0) + '%';
}

export default function MemoryRecallView({
  tier,
  workspaceId,
  onOpenSource,
}: MemoryRecallViewProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const { data, loading, error } = useMemoryRecall(
    submitted,
    tier,
    workspaceId,
    true,
  );

  const submit = () => {
    const q = query.trim();
    if (!q) return;
    setSubmitted(q);
  };

  const hits: MemoryRecallHit[] = data?.hits ?? [];

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: 'var(--color-bg-page)' }}>
      {/* Search input */}
      <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--color-border-muted)' }}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="flex items-center gap-1 rounded-md border px-2 py-1"
          style={{ borderColor: 'var(--color-border-default)', backgroundColor: 'var(--color-bg-card)' }}
        >
          <Search
            className="h-3.5 w-3.5 flex-shrink-0"
            style={{ color: 'var(--color-text-tertiary)' }}
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('memoryPanel.recallPlaceholder')}
            className="flex-1 min-w-0 bg-transparent text-xs outline-none"
            style={{ color: 'var(--color-text-primary)' }}
            aria-label={t('memoryPanel.recallPlaceholder')}
          />
          <button
            type="submit"
            className="text-[0.6875rem] font-medium px-2 py-0.5 rounded transition-colors"
            style={{
              color: 'var(--color-accent-primary)',
              backgroundColor: 'var(--color-bg-subtle)',
            }}
          >
            {t('memoryPanel.recallSearch')}
          </button>
        </form>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {!submitted && (
          <div className="px-4 py-8 flex flex-col items-center gap-2 text-center"
               style={{ color: 'var(--color-text-tertiary)' }}>
            <Sparkles className="h-6 w-6 opacity-40" />
            <div className="text-xs max-w-[16rem]">
              {t('memoryPanel.recallHint')}
            </div>
          </div>
        )}

        {submitted && loading && (
          <div className="px-4 py-6 flex items-center justify-center gap-2 text-xs"
               style={{ color: 'var(--color-text-tertiary)' }}>
            <Loader size={14} className="text-current" />
            {t('memoryPanel.loadingList')}
          </div>
        )}

        {submitted && !loading && error && (
          <div className="px-3 py-3 text-xs" style={{ color: 'var(--color-icon-danger)' }}>
            {error || t('memoryPanel.loadError')}
          </div>
        )}

        {submitted && !loading && !error && hits.length === 0 && (
          <div className="px-4 py-8 flex flex-col items-center gap-2 text-center"
               style={{ color: 'var(--color-text-tertiary)' }}>
            <SearchX className="h-6 w-6 opacity-40" />
            <div className="text-xs max-w-[16rem]">
              {t('memoryPanel.recallEmpty', { query: submitted })}
            </div>
          </div>
        )}

        {hits.map((hit, i) => (
          <div
            key={`${hit.source}-${i}`}
            className="px-3 py-2 border-b"
            style={{ borderColor: 'var(--color-border-subtle)' }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[0.625rem] truncate max-w-[65%]"
                style={{
                  color: 'var(--color-accent-primary)',
                  backgroundColor: 'var(--color-bg-subtle)',
                }}
                title={hit.source}
              >
                {hit.source}
              </span>
              <span
                className="flex-shrink-0 font-mono text-[0.625rem]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {scoreLabel(hit.score)}
              </span>
              {onOpenSource && (
                <button
                  className="ml-auto text-[0.625rem] font-medium"
                  style={{ color: 'var(--color-text-tertiary)' }}
                  onClick={() => onOpenSource(hit.source, tier)}
                >
                  {t('memoryPanel.recallOpenSource')}
                </button>
              )}
            </div>
            <div className="text-xs leading-5 break-words"
                 style={{ color: 'var(--color-text-secondary)' }}>
              {hit.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}