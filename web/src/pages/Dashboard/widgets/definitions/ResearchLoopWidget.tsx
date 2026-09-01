import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  GitBranch,
  CircleDashed,
  Check,
  FileText,
  Database,
  Loader2,
  Link2,
} from 'lucide-react';
import { listResearchLoops } from '@/api/researchLoop';
import { RESEARCH_LOOP_STAGES, type ResearchLoop } from '@/types/researchLoop';
import { registerWidget } from '../framework/WidgetRegistry';
import { useWidgetContextExport } from '../framework/contextSnapshot';
import { wrapWidgetContext } from '../framework/snapshotSerializers';
import { ResearchLoopConfigSchema } from '../framework/configSchemas';
import type { WidgetRenderProps } from '../types';

type ResearchLoopConfig = { limit?: number; status?: string };

const STAGE_ICON: Record<(typeof RESEARCH_LOOP_STAGES)[number], typeof CircleDashed> = {
  idea: GitBranch,
  data: Database,
  model: CircleDashed,
  report: FileText,
  track: CircleDashed,
  trigger: CircleDashed,
};

const STATUS_COLOR: Record<string, string> = {
  active: 'var(--color-accent-primary)',
  paused: 'var(--color-text-tertiary)',
  completed: 'var(--color-text-secondary)',
  archived: 'var(--color-text-tertiary)',
};

function stageKey(stage: string): string {
  return `dashboard.widgets.researchLoop.stage_${stage}`;
}

function LoopPipeline({ loop }: { loop: ResearchLoop }) {
  const { t } = useTranslation();
  const currentIdx = RESEARCH_LOOP_STAGES.indexOf(loop.current_stage as (typeof RESEARCH_LOOP_STAGES)[number]);
  const doneCount = Math.max(0, currentIdx);

  return (
    <div className="flex items-center gap-0 w-full my-2">
      {RESEARCH_LOOP_STAGES.map((stage, i) => {
        const done = i < doneCount;
        const current = i === currentIdx;
        const Icon = STAGE_ICON[stage];
        return (
          <div key={stage} className="flex items-center flex-1 last:flex-none" style={{ minWidth: 0 }}>
            <div className="flex flex-col items-center gap-1" style={{ width: '100%', minWidth: 0 }}>
              <div
                className="flex items-center justify-center rounded-full transition-colors"
                style={{
                  width: 26,
                  height: 26,
                  backgroundColor: current
                    ? 'var(--color-accent-primary)'
                    : done
                      ? 'rgba(82,196,26,0.14)'
                      : 'var(--color-bg-subtle)',
                  boxShadow: current ? '0 0 0 3px var(--color-focus-ring)' : 'none',
                }}
                title={t(stageKey(stage))}
              >
                {done ? (
                  <Check className="h-3.5 w-3.5" style={{ color: '#2E7D32' }} />
                ) : (
                  <Icon
                    className="h-3.5 w-3.5"
                    style={{ color: current ? '#fff' : 'var(--color-text-tertiary)' }}
                  />
                )}
              </div>
              <span
                className="text-[0.5625rem] uppercase tracking-wider truncate text-center"
                style={{
                  color: current ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                  maxWidth: '100%',
                }}
              >
                {t(stageKey(stage))}
              </span>
            </div>
            {i < RESEARCH_LOOP_STAGES.length - 1 && (
              <div
                className="h-px flex-1 mx-1 mb-4"
                style={{
                  backgroundColor: done
                    ? 'rgba(82,196,26,0.4)'
                    : 'var(--color-border-muted)',
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function LoopRow({ loop, onOpen }: { loop: ResearchLoop; onOpen: () => void }) {
  const { t } = useTranslation();
  const goal = loop.goal || loop.thesis || t('dashboard.widgets.researchLoop.untitled');
  const ev = loop.evidence.length;
  const arts = loop.artifacts.length;
  const symbol = loop.symbol ? ` · ${loop.symbol}` : '';
  const direction = loop.direction ? ` · ${t(`dashboard.widgets.researchLoop.dir_${loop.direction}`)}` : '';

  return (
    <div
      className="dashboard-glass-card p-3.5 mb-2.5 cursor-pointer transition-colors"
      style={{ borderRadius: 12 }}
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--color-bg-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = '';
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="flex-1 min-w-0 truncate dashboard-mono text-[0.8125rem]"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {goal}
            <span style={{ color: 'var(--color-text-tertiary)' }}>{symbol}{direction}</span>
          </span>
        </div>
        <span
          className="flex-shrink-0 text-[0.625rem] uppercase tracking-wider"
          style={{ color: STATUS_COLOR[loop.status] ?? 'var(--color-text-tertiary)' }}
        >
          {t(`dashboard.widgets.researchLoop.status_${loop.status}`)}
        </span>
      </div>

      <LoopPipeline loop={loop} />

      <div className="flex items-center gap-3 mt-1">
        <span className="flex items-center gap-1 text-[0.6875rem] tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
          <Database className="h-3 w-3" />
          {ev} {t('dashboard.widgets.researchLoop.evidence')}
        </span>
        <span className="flex items-center gap-1 text-[0.6875rem] tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
          <FileText className="h-3 w-3" />
          {arts} {t('dashboard.widgets.researchLoop.artifacts')}
        </span>
        {loop.portfolio_link ? (
          <span className="flex items-center gap-1 text-[0.6875rem]" style={{ color: 'var(--color-accent-primary)' }}>
            <Link2 className="h-3 w-3" />
            {t('dashboard.widgets.researchLoop.portfolioLinked')}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function ResearchLoopWidget({ instance }: WidgetRenderProps<ResearchLoopConfig>) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const limit = instance.config.limit ?? 5;
  const statusFilter = instance.config.status ?? 'all';

  const { data, isLoading, error } = useQuery<{ loops: ResearchLoop[]; total: number }>({
    queryKey: ['research-loops', statusFilter, limit],
    queryFn: async () => {
      const { data: d } = await listResearchLoops({
        limit,
        offset: 0,
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
      });
      return { loops: (d.loops ?? []) as ResearchLoop[], total: (d.total ?? 0) as number };
    },
    staleTime: 20_000,
  });

  const loops = useMemo(() => data?.loops ?? [], [data]);

  useWidgetContextExport(instance.id, {
    full: () => {
      const body = loops.length
        ? loops
            .map(
              (l) =>
                `- ${l.goal || l.symbol || '(untitled)'} | stage=${l.current_stage} | status=${l.status} | evidence=${l.evidence.length} | artifacts=${l.artifacts.length}`,
            )
            .join('\n')
        : '_no research loops_';
      return {
        widget_type: 'research.loop',
        widget_id: instance.id,
        label: `${t('dashboard.widgets.researchLoop.title')} · ${loops.length}`,
        description: `${loops.length} loop${loops.length === 1 ? '' : 's'}`,
        captured_at: new Date().toISOString(),
        text: wrapWidgetContext('research.loop', { count: loops.length, statusFilter }, body),
        data: { loops },
      };
    },
  });

  const openLoop = (loop: ResearchLoop) => {
    navigate(`/chat/${loop.workspace_id}`);
  };

  return (
    <div className="dashboard-glass-card p-5 flex flex-col h-full" style={{ minWidth: 0 }}>
      <div
        className="flex items-baseline justify-between mb-3 pb-3 border-b"
        style={{ borderColor: 'var(--color-border-muted)' }}
      >
        <div className="flex items-baseline gap-2.5 min-w-0">
          <GitBranch
            className="h-3.5 w-3.5 flex-shrink-0 self-center"
            style={{ color: 'var(--color-text-tertiary)' }}
          />
          <span
            className="text-[0.625rem] font-semibold uppercase tracking-[0.14em]"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {t('dashboard.widgets.researchLoop.header')}
          </span>
          <span
            className="title-font text-lg leading-none dashboard-mono"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {data?.total ?? loops.length}
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">
        {isLoading && loops.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-8" style={{ color: 'var(--color-text-tertiary)' }}>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-[0.6875rem]">{t('dashboard.widgets.researchLoop.loading')}</span>
          </div>
        ) : error ? (
          <div className="py-6 text-center text-[0.6875rem]" style={{ color: 'var(--color-text-tertiary)' }}>
            {t('dashboard.widgets.researchLoop.error')}
          </div>
        ) : loops.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 py-6">
            <div
              className="h-9 w-9 rounded-full flex items-center justify-center"
              style={{ backgroundColor: 'var(--color-bg-subtle)' }}
            >
              <GitBranch className="h-4 w-4" style={{ color: 'var(--color-text-tertiary)' }} />
            </div>
            <div className="text-center">
              <div className="dashboard-mono text-sm mb-0.5" style={{ color: 'var(--color-text-primary)' }}>
                {t('dashboard.widgets.researchLoop.empty')}
              </div>
              <div className="text-[0.6875rem]" style={{ color: 'var(--color-text-tertiary)' }}>
                {t('dashboard.widgets.researchLoop.emptyHint')}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col">
            {loops.map((loop) => (
              <LoopRow key={loop.loop_id} loop={loop} onOpen={() => openLoop(loop)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

registerWidget<ResearchLoopConfig>({
  type: 'research.loop',
  titleKey: 'dashboard.widgets.researchLoop.title',
  descriptionKey: 'dashboard.widgets.researchLoop.description',
  category: 'workspace',
  icon: GitBranch,
  component: ResearchLoopWidget,
  defaultConfig: { limit: 5, status: 'all' },
  configSchema: ResearchLoopConfigSchema,
  defaultSize: { w: 6, h: 24 },
  minSize: { w: 3, h: 16 },
});

export default ResearchLoopWidget;
