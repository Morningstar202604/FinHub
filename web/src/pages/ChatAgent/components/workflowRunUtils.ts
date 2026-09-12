import React from 'react';
import {
  AlertCircle, Check, StopCircle, type LucideIcon,
} from 'lucide-react';
import type { TFunction } from 'i18next';
import type {
  WorkflowChild, WorkflowChildStatus, WorkflowRunState,
} from '../session/subagents/workflowRunState';

/** The uppercase hairline label above every band in the run detail. */
export const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: '0.6875rem',
  color: 'var(--color-text-quaternary)',
  letterSpacing: '0.05em',
  textTransform: 'uppercase',
};

/** Elapsed seconds as `12.3s` under a minute, `2m 07s` above it. */
export function formatRunDuration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  // Round the total before splitting: rounding the remainder on its own lets
  // it reach 60 and print an impossible `1m 60s` for anything in the top
  // half-second of a minute.
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}m ${String(rest).padStart(2, '0')}s`;
}

/**
 * Per-child-status presentation, shared by the inline run card and the detail
 * panel. A stop is not a failure — it gets the same quiet treatment the run
 * header gives it — and an invalid result is amber, not red: the child ran,
 * its output just didn't match the schema.
 */
export const WORKFLOW_CHILD_UI: Record<
  WorkflowChildStatus,
  { labelKey: string; color: string; Icon?: LucideIcon; live?: boolean }
> = {
  running: {
    labelKey: 'chat.workflowRun.childRunning',
    color: 'var(--color-warning)',
    live: true,
  },
  ok: { labelKey: 'chat.workflowRun.childDone', color: 'var(--color-success)', Icon: Check },
  invalid_schema: {
    labelKey: 'chat.workflowRun.childInvalid',
    color: 'var(--color-warning)',
    Icon: AlertCircle,
  },
  cancelled: {
    labelKey: 'chat.workflowRun.childStopped',
    color: 'var(--color-text-tertiary)',
    Icon: StopCircle,
  },
  timeout: {
    labelKey: 'chat.workflowRun.childTimedOut',
    color: 'var(--color-icon-danger)',
    Icon: AlertCircle,
  },
  error: { labelKey: 'chat.workflowRun.childFailed', color: 'var(--color-icon-danger)', Icon: AlertCircle },
};

/** i18n key for a child's status word — the row label and the icon's name. */
export function workflowChildLabelKey(status: WorkflowChildStatus): string {
  return (WORKFLOW_CHILD_UI[status] ?? WORKFLOW_CHILD_UI.error).labelKey;
}

/**
 * Finance-committee vocabulary. The prebuilt `finance_committee` workflow
 * dispatches children by role and stamps phases with fixed protocol names;
 * both read as department/agenda vocabulary wherever the run renders. Unknown
 * types/phases (any other script, incl. user-authored ones) pass through
 * untouched, so this layer only ever decorates the built-in meeting.
 */
export const MEETING_ROLE_UI: Record<string, { labelKey: string; tileVar: string }> = {
  accountant: { labelKey: 'chat.meeting.roleAccountant', tileVar: 'var(--color-tile-blue)' },
  treasury: { labelKey: 'chat.meeting.roleTreasury', tileVar: 'var(--color-tile-teal)' },
  'tax-specialist': { labelKey: 'chat.meeting.roleTax', tileVar: 'var(--color-tile-purple)' },
  'fp-analyst': { labelKey: 'chat.meeting.roleFpa', tileVar: 'var(--color-tile-gold)' },
  'internal-auditor': { labelKey: 'chat.meeting.roleAudit', tileVar: 'var(--color-tile-green)' },
};

export const MEETING_PHASE_UI: Record<string, string> = {
  agenda: 'chat.meeting.phaseAgenda',
  statements: 'chat.meeting.phaseStatements',
  'cross-examination': 'chat.meeting.phaseCross',
  'risk-gate': 'chat.meeting.phaseRiskGate',
  minutes: 'chat.meeting.phaseMinutes',
};

/** Speaking turns the `finance_committee` script labels children with. */
const MEETING_TURN_UI: Record<string, string> = {
  statement: 'chat.meeting.turnStatement',
  challenge: 'chat.meeting.turnChallenge',
  'risk gate': 'chat.meeting.turnRiskGate',
  minutes: 'chat.meeting.turnMinutes',
};

/** The localized department name a child's dispatch type maps to, or null. */
export function meetingRoleLabel(subagentType: string, t: TFunction): string | null {
  const ui = MEETING_ROLE_UI[subagentType];
  return ui ? t(ui.labelKey) : null;
}

/** The localized agenda step a phase title maps to, or null to pass through. */
export function meetingPhaseLabel(phase: string, t: TFunction): string | null {
  const key = MEETING_PHASE_UI[phase];
  return key ? t(key) : null;
}

/** Meeting child labels arrive as `<turn> · <role>` from the script; the turn
 *  word localizes with the role it names. Any other shape passes through. */
export function meetingLabelParts(label: string, t: TFunction): string | null {
  const split = label.indexOf(' · ');
  if (split <= 0) return null;
  const turnKey = MEETING_TURN_UI[label.slice(0, split)];
  const role = MEETING_ROLE_UI[label.slice(split + 3)];
  if (!turnKey || !role) return null;
  return `${t(turnKey)} · ${t(role.labelKey)}`;
}

/** The one colour a child's status is allowed to read as, row and detail alike.
 *
 * A schema miss is amber because the child ran — rendering its detail red
 * would contradict the row directly above it. */
export function workflowChildStatusColor(status: WorkflowChildStatus): string {
  return (WORKFLOW_CHILD_UI[status] ?? WORKFLOW_CHILD_UI.error).color;
}

/** The run totals both surfaces put in their band: how many children have
 *  settled, how many were promised, and how long the run took. */
export function summarizeRun(run: WorkflowRunState | undefined): {
  children: WorkflowChild[];
  doneCount: number;
  agentCount: number;
  duration: string | null;
} {
  const children = run?.children ?? [];
  return {
    children,
    doneCount: children.filter((c) => c.status !== 'running').length,
    // `childrenTotal` is the script's promise, `children.length` what has been
    // dispatched so far — the promise wins once the run reports it.
    agentCount: run?.childrenTotal ?? children.length,
    duration: formatRunDuration(run?.durationS),
  };
}
