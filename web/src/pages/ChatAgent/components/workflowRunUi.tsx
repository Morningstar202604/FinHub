import React from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';
import { Loader } from '@/components/ui/loader';
import type {
  WorkflowChild,
  WorkflowChildStatus,
} from '../session/subagents/workflowRunState';
import {
  WORKFLOW_CHILD_UI,
  MEETING_ROLE_UI,
  formatRunDuration,
  meetingLabelParts,
  meetingRoleLabel,
  workflowChildLabelKey,
} from './workflowRunUtils';

export function WorkflowChildStatusIcon({
  status,
  size = 11,
}: {
  status: WorkflowChildStatus;
  size?: number;
}): React.ReactElement {
  const { t } = useTranslation();
  const ui = WORKFLOW_CHILD_UI[status] ?? WORKFLOW_CHILD_UI.error;
  const { Icon } = ui;
  if (ui.live || !Icon) {
    // Shared liveness glyph (nav tree, task cards): ascii spinner, amber.
    return (
      <Loader
        size={size}
        label={t(workflowChildLabelKey(status))}
        style={{ color: ui.color, flexShrink: 0 }}
      />
    );
  }
  return (
    <Icon
      aria-label={t(workflowChildLabelKey(status))}
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        color: ui.color,
      }}
    />
  );
}

export type WorkflowChildRowSurface = 'card' | 'detail';

interface ChildRowSurfaceUi {
  testId: string;
  row: React.CSSProperties;
  iconSize: number;
  labelColor: string;
  /** Set only where a cell's size differs from the row's own. */
  cellFontSize?: string;
  durationMinWidth: number;
  /** The inline card drops an unknown dispatch type; the detail keeps the
   *  column so every row's trailing cells stay on the same rails. */
  alwaysShowType: boolean;
  /** An unfinished child has no duration: the card leaves the cell blank, the
   *  detail names the child's state there instead. */
  namesStatusWhenUnfinished: boolean;
}

/** Two densities of one row. The inline card is a glance — tight, quiet, no
 *  affordance; the detail is a list you navigate — roomier, hoverable, and it
 *  carries per-child telemetry. Everything else about the row is shared. */
const CHILD_ROW_UI: Record<WorkflowChildRowSurface, ChildRowSurfaceUi> = {
  card: {
    testId: 'workflow-child-row',
    row: { display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.6875rem', minWidth: 0 },
    iconSize: 11,
    labelColor: 'var(--color-text-secondary)',
    durationMinWidth: 42,
    alwaysShowType: false,
    namesStatusWhenUnfinished: false,
  },
  detail: {
    testId: 'workflow-detail-child-row',
    row: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '6px 8px',
      margin: '0 -8px',
      borderRadius: 6,
      fontSize: '0.75rem',
      minWidth: 0,
      cursor: 'default',
    },
    iconSize: 12,
    labelColor: 'var(--color-text-primary)',
    cellFontSize: '0.6875rem',
    durationMinWidth: 64,
    alwaysShowType: true,
    namesStatusWhenUnfinished: true,
  },
};

/**
 * One dispatched child: status glyph, label, dispatch type and elapsed time.
 * Both the inline run card and the detail panel render this, so the label
 * fallback and the overflow rules cannot drift between them. A finance-
 * committee child reads as its meeting vocabulary (发言环节 · 部门); any other
 * workflow's child renders its raw label and type.
 */
export function WorkflowChildRow({
  child,
  surface,
  meta,
  onOpen,
}: {
  child: WorkflowChild;
  surface: WorkflowChildRowSurface;
  /** Trailing telemetry cell (tool calls · tokens); detail only. */
  meta?: string;
  /** Makes the row a control that opens the child's own task view. */
  onOpen?: () => void;
}): React.ReactElement {
  const { t } = useTranslation();
  const ui = CHILD_ROW_UI[surface];
  const cellFontSize = ui.cellFontSize;
  const roleLabel = meetingRoleLabel(child.subagentType, t);
  const displayLabel = meetingLabelParts(child.label, t)
    ?? (child.label || t('chat.workflowRun.childFallbackLabel', { n: child.seq + 1 }));
  return (
    <div
      role={onOpen ? 'button' : undefined}
      tabIndex={onOpen ? 0 : undefined}
      data-testid={ui.testId}
      onClick={onOpen}
      onKeyDown={
        onOpen
          ? (e: React.KeyboardEvent<HTMLDivElement>) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpen();
              }
            }
          : undefined
      }
      onMouseEnter={
        onOpen
          ? (e: React.MouseEvent<HTMLDivElement>) =>
              (e.currentTarget.style.background = 'var(--color-bg-elevated)')
          : undefined
      }
      onMouseLeave={
        onOpen
          ? (e: React.MouseEvent<HTMLDivElement>) =>
              (e.currentTarget.style.background = 'transparent')
          : undefined
      }
      style={onOpen ? { ...ui.row, cursor: 'pointer' } : ui.row}
    >
      <WorkflowChildStatusIcon status={child.status} size={ui.iconSize} />
      {roleLabel && (
        // The department's identity color, on the 1px rail the status glyph
        // already reserves. A quiet marker — the meeting row is read by its
        // name and status, not by color.
        <span
          aria-hidden="true"
          data-testid="workflow-role-dot"
          style={{
            width: 5,
            height: 5,
            flexShrink: 0,
            borderRadius: '50%',
            background: MEETING_ROLE_UI[child.subagentType].tileVar,
          }}
        />
      )}
      <span
        style={{
          color: ui.labelColor,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
          flex: '1 1 auto',
        }}
      >
        {displayLabel}
      </span>
      {meta && (
        <span
          style={{
            color: 'var(--color-text-quaternary)',
            whiteSpace: 'nowrap',
            flexShrink: 0,
            fontSize: cellFontSize,
          }}
        >
          {meta}
        </span>
      )}
      {(ui.alwaysShowType || !!child.subagentType) && (
        <span
          style={{
            color: 'var(--color-text-quaternary)',
            whiteSpace: 'nowrap',
            flexShrink: 0,
            fontSize: cellFontSize,
          }}
        >
          {roleLabel ?? child.subagentType}
        </span>
      )}
      <span
        style={{
          color: 'var(--color-text-tertiary)',
          whiteSpace: 'nowrap',
          flexShrink: 0,
          fontSize: cellFontSize,
          minWidth: ui.durationMinWidth,
          textAlign: 'right',
        }}
      >
        {formatRunDuration(child.durationS)
          ?? (ui.namesStatusWhenUnfinished ? t(workflowChildLabelKey(child.status)) : '')}
      </span>
      {onOpen && (
        <ChevronRight
          aria-hidden="true"
          style={{ width: 13, height: 13, flexShrink: 0, color: 'var(--color-text-quaternary)' }}
        />
      )}
    </div>
  );
}
