import { AlertCircle, Check, CheckCircle2, Circle, RefreshCw, RotateCw, StopCircle, type LucideIcon } from 'lucide-react';
import type { SubagentDisplayStatus } from '../session/subagents/subagentStatus';

export type TaskCardStatusKind =
  | 'running'
  | 'completed'
  | 'cancelled'
  | 'error'
  | 'updated'
  | 'resumed'
  | 'unknown';

export interface TaskCardStatusUi {
  /** i18n key for the status word; `null` renders the raw wire status instead. */
  labelKey: string | null;
  color: string;
  Icon: LucideIcon | null;
  /** Renders the ascii liveness glyph instead of a lucide icon. */
  live?: boolean;
}

/**
 * Per-status presentation for every inline task card. Subagent spawns and
 * workflow runs read this one table, so a status can never render amber on one
 * card and red on the other. Updated/Resumed share the warning amber with
 * Running because those are all "in flight or just changed"; Cancelled is
 * terminal-neutral (the run was stopped), Failed is the danger token — not
 * `--color-loss`, which belongs to market P&L.
 */
export const STATUS_UI: Record<TaskCardStatusKind, TaskCardStatusUi> = {
  running: {
    labelKey: 'chat.taskCard.statusRunning',
    color: 'var(--color-warning)',
    Icon: null,
    live: true,
  },
  completed: {
    labelKey: 'chat.taskCard.statusCompleted',
    color: 'var(--color-success)',
    Icon: Check,
  },
  cancelled: {
    labelKey: 'chat.taskCard.statusStopped',
    color: 'var(--color-text-tertiary)',
    Icon: StopCircle,
  },
  error: {
    labelKey: 'chat.taskCard.statusFailed',
    color: 'var(--color-icon-danger)',
    Icon: AlertCircle,
  },
  updated: {
    labelKey: 'chat.taskCard.statusUpdated',
    color: 'var(--color-warning)',
    Icon: RefreshCw,
  },
  resumed: {
    labelKey: 'chat.taskCard.statusResumed',
    color: 'var(--color-warning)',
    Icon: RotateCw,
  },
  unknown: {
    labelKey: null,
    color: 'var(--color-text-tertiary)',
    Icon: null,
  },
};

/**
 * The card status a task's own wire status maps onto, before a card's action
 * verb (`updated`/`resumed`) overrides it. Anything the vocabulary doesn't
 * name falls to `unknown`, which renders the wire value verbatim rather than
 * guessing an outcome.
 */
export function taskCardStatusKind(
  status: string | null | undefined,
): TaskCardStatusKind {
  switch (status) {
    case 'running':
    case 'completed':
    case 'cancelled':
    case 'error':
      return status;
    default:
      return 'unknown';
  }
}

interface SubagentStatusTreatment {
  Icon?: LucideIcon;
  color: string;
  /** Renders the ascii liveness glyph instead of a lucide icon. */
  live?: boolean;
}

/**
 * A subagent's status badge: exceptional terminal outcomes read at a glance
 * (error = red alert, stopped = stop glyph), a genuinely running task shows
 * the ascii liveness glyph (amber = live agent work, matching the nav tree's
 * running-thread rows), and a spawned-but-silent one holds an idle circle.
 * Completed renders NO glyph on the nav row: absence of the liveness glyph
 * already reads as done, and a checkmark next to the hover ✕ remove button
 * read as a second control.
 */
export const SUBAGENT_STATUS_UI: Record<SubagentDisplayStatus, SubagentStatusTreatment> = {
  initializing: { Icon: Circle, color: 'var(--color-icon-muted)' },
  active: { live: true, color: 'var(--color-accent-primary)' },
  completed: { color: 'var(--color-text-tertiary)' },
  cancelled: { Icon: StopCircle, color: 'var(--color-text-tertiary)' },
  error: { Icon: AlertCircle, color: 'var(--color-icon-danger)' },
};

export type SubagentStatusSurface = 'navRow' | 'statusBar';

/** Loader glyph px per surface — the lucide icons size via `className`, but
 *  the ascii glyph sizes by font, so the surface names its density here. */
export const LOADER_SIZE: Record<SubagentStatusSurface, number> = {
  navRow: 12,
  statusBar: 16,
};

/**
 * The status bar is the one surface that celebrates a finished task — it has
 * the room the nav row doesn't. Whether the two should converge is a design
 * call, not a structural one; until it's made, the difference is declared in
 * one place instead of implied by two ladders.
 */
export const SUBAGENT_STATUS_OVERRIDES: Partial<
  Record<SubagentStatusSurface, Partial<Record<SubagentDisplayStatus, SubagentStatusTreatment>>>
> = {
  statusBar: {
    completed: { Icon: CheckCircle2, color: 'var(--color-accent-primary)' },
  },
};
