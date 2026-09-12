import React, { useState } from 'react';
import { motion, AnimatePresence, type MotionProps } from 'framer-motion';
import { Check, X, ChevronRight } from 'lucide-react';
import { Loader } from '@/components/ui/loader';

export type HitlCardState = 'pending' | 'approved' | 'rejected';

export interface HitlApproveRejectButtonsProps {
  onApprove?: () => void;
  onReject?: () => void;
  approveLabel: string;
  rejectLabel: string;
  /** Render buttons only, no wrapping row. */
  bare?: boolean;
}

/**
 * Unified Approve/Reject button pair for HITL cards.
 *
 * Both buttons share one visual language: primary (filled) approve + quiet
 * (bordered) reject, with the same hover/tap motion. Eliminates the per-card
 * duplicated inline `onMouseEnter`/`onMouseLeave` style juggling that existed
 * on PlanApprovalCard / CreateWorkspaceCard.
 */
export function HitlApproveRejectButtons({
  onApprove,
  onReject,
  approveLabel,
  rejectLabel,
  bare = false,
}: HitlApproveRejectButtonsProps) {
  const buttons = (
    <>
      <motion.button
        type="button"
        onClick={(e: React.MouseEvent) => { e.stopPropagation(); onApprove?.(); }}
        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-md font-medium transition-colors hover:brightness-110"
        style={{ backgroundColor: 'var(--color-btn-primary-bg)', color: 'var(--color-btn-primary-text)' }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <Check className="h-3.5 w-3.5 stroke-[2.5]" />
        {approveLabel}
      </motion.button>
      <motion.button
        type="button"
        onClick={(e: React.MouseEvent) => { e.stopPropagation(); onReject?.(); }}
        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-md font-medium transition-colors"
        style={{ backgroundColor: 'var(--color-border-muted)', color: 'var(--color-text-tertiary)' }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <X className="h-3.5 w-3.5" />
        {rejectLabel}
      </motion.button>
    </>
  );

  if (bare) return <>{buttons}</>;
  return <div className="pt-3 flex items-center gap-2">{buttons}</div>;
}

export interface HitlPendingShellProps {
  icon: React.ReactNode;
  title: string;
  body: React.ReactNode;
  footer?: React.ReactNode;
  animate?: MotionProps['animate'];
  transition?: MotionProps['transition'];
}

/**
 * Shared chrome for a *pending* HITL card: motion entrance, header row
 * (icon + title + trailing loader slot via footer), body region.
 */
export function HitlPendingShell({ icon, title, body, footer, animate, transition }: HitlPendingShellProps) {
  const anim: MotionProps['animate'] = animate ?? { opacity: 1, y: 0 };
  const trans: MotionProps['transition'] = transition ?? { duration: 0.4, ease: [0.22, 1, 0.36, 1] };
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={anim}
      transition={trans}
    >
      <div className="flex items-center gap-2 pb-3">
        <span className="h-4 w-4 flex-shrink-0 inline-flex items-center justify-center">{icon}</span>
        <span className="text-[0.9375rem] font-medium" style={{ color: 'var(--color-text-primary)' }}>
          {title}
        </span>
        <Loader
          size={14}
          className="ml-auto flex-shrink-0 text-[color:var(--color-icon-muted)]"
        />
      </div>
      {body}
      {footer}
    </motion.div>
  );
}

export interface HitlResolvedShellProps {
  state: Extract<HitlCardState, 'approved' | 'rejected'>;
  label: string;
  /** Optional trailing inline note rendered after the label. */
  note?: React.ReactNode;
  body: React.ReactNode;
  /** Resolved rows default to collapsed (true) or expanded (false). */
  defaultCollapsed?: boolean;
}

/**
 * Shared chrome for a *resolved* (approved/rejected) HITL row: a clickable
 * summary line (chevron + status glyph + label) that expands a detail body.
 */
export function HitlResolvedShell({ state, label, note, body, defaultCollapsed = true }: HitlResolvedShellProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const isApproved = state === 'approved';
  return (
    <div>
      <button
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        className="flex items-center gap-2 py-1 cursor-pointer w-full text-left"
      >
        <motion.div
          animate={{ rotate: collapsed ? 0 : 90 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronRight
            className="h-3.5 w-3.5 flex-shrink-0"
            style={{ color: 'var(--color-icon-muted)' }}
          />
        </motion.div>
        {isApproved ? (
          <Check className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />
        ) : (
          <X className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-text-tertiary)' }} />
        )}
        <span className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
          {label}
        </span>
        {note}
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pt-2 pb-1 pl-6">{body}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Bordered detail panel used inside resolved card bodies. */
export function HitlDetailPanel({ children, dimmed = false }: { children: React.ReactNode; dimmed?: boolean }) {
  return (
    <div
      className="rounded-lg px-4 py-3"
      style={{
        border: '1px solid var(--color-border-muted)',
        opacity: dimmed ? 0.6 : 0.8,
      }}
    >
      {children}
    </div>
  );
}
