/**
 * The one place a task's status becomes an icon and a color.
 *
 * Two vocabularies live here because the surfaces genuinely speak two: inline
 * cards read `TaskCardStatusKind` (which carries the update/resume verbs a
 * card header shows), while the nav tree and the status bar read a subagent's
 * `SubagentDisplayStatus` (which distinguishes "spawned but silent" from
 * "running"). Each vocabulary has exactly one table; a surface that needs its
 * own treatment declares an override rather than restating the ladder.
 *
 * Liveness is the shared ascii Loader (`live: true`), never a spinning lucide
 * glyph — the same treatment as the running-thread rows in the nav tree.
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Loader } from '@/components/ui/loader';
import type { SubagentDisplayStatus } from '../session/subagents/subagentStatus';
import {
  STATUS_UI,
  SUBAGENT_STATUS_UI,
  SUBAGENT_STATUS_OVERRIDES,
  LOADER_SIZE,
  type TaskCardStatusKind,
  type SubagentStatusSurface,
} from './taskStatusTables';

/**
 * The status word every task surface shows: icon, accent and label from one
 * `STATUS_UI` row. The inline card header and the workflow-run detail header
 * render this, so the chip cannot drift between them.
 */
export function TaskStatusChip({
  kind,
  rawStatus,
  style,
}: {
  kind: TaskCardStatusKind;
  /** Wire status rendered verbatim when `kind` is `unknown`. */
  rawStatus?: string;
  style?: React.CSSProperties;
}): React.ReactElement {
  const { t } = useTranslation();
  const { labelKey, color, Icon, live } = STATUS_UI[kind];
  const label = labelKey ? t(labelKey) : rawStatus;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        color,
        fontSize: '0.6875rem',
        letterSpacing: '0.04em',
        fontWeight: 500,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {live ? (
        <Loader size={11} label={label || t('chat.taskCard.statusRunning')} style={{ color: 'inherit' }} />
      ) : (
        Icon && <Icon style={{ width: 11, height: 11 }} />
      )}
      {label}
    </span>
  );
}

export function SubagentStatusIcon({
  status,
  surface = 'navRow',
  className,
}: {
  status: SubagentDisplayStatus;
  surface?: SubagentStatusSurface;
  /** Sizing class for the lucide icons — the nav row is 3, the status bar 4. */
  className?: string;
}): React.ReactElement | null {
  const { t } = useTranslation();
  const { Icon, color, live } =
    SUBAGENT_STATUS_OVERRIDES[surface]?.[status] ?? SUBAGENT_STATUS_UI[status];
  if (live) {
    return (
      <Loader
        size={LOADER_SIZE[surface]}
        label={t('chat.taskCard.statusRunning')}
        style={{ color }}
      />
    );
  }
  // A status with neither liveness nor an icon is deliberately glyph-free.
  if (!Icon) return null;
  return <Icon className={className} style={{ color }} />;
}
