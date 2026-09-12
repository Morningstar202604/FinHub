import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { ScrollText, Check, X, ChevronRight } from 'lucide-react';
import Markdown from './Markdown';
import { HitlApproveRejectButtons, HitlPendingShell } from './HitlCardShell';
import type { PlanData } from '@/pages/ChatAgent/types/domain';

interface PlanApprovalCardProps {
  planData: PlanData | null;
  onApprove?: () => void;
  onReject?: () => void;
  onDetailClick?: () => void;
}

/**
 * PlanApprovalCard - Inline message segment card for HITL plan approval.
 *
 * Three states:
 *   pending  - plan preview with approve/reject buttons
 *   approved - status banner + plan visible (collapsible)
 *   rejected - status banner + plan visible (collapsible) + feedback hint
 *
 * Resolved states default to expanded; user can manually collapse.
 */
function PlanApprovalCard({ planData, onApprove, onReject, onDetailClick }: PlanApprovalCardProps): React.ReactElement | null {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);

  if (!planData) return null;

  const { description, status } = planData;
  const isApproved = status === 'approved';
  const isRejected = status === 'rejected';

  // --- Resolved (approved / rejected): expanded by default, manually collapsible ---
  if (isApproved || isRejected) {
    const resolvedBody = (
      <div
        className="relative cursor-pointer rounded-lg overflow-hidden"
        style={{
          border: '1px solid var(--color-border-muted)',
          opacity: isRejected ? 0.6 : 0.8,
        }}
        onClick={() => onDetailClick?.()}
      >
        <div className="px-4 py-3 overflow-hidden" style={{ maxHeight: '260px' }}>
          <Markdown variant="chat" content={description} className="text-sm" />
        </div>
        <div
          style={{
            position: 'absolute',
            bottom: 0, left: 0, right: 0, height: '64px',
            background: 'linear-gradient(to bottom, transparent, var(--color-bg-page))',
            pointerEvents: 'none',
          }}
        />
      </div>
    );

    return (
      <div>
        {/* Header row -- click to toggle */}
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
          <span
            className="text-sm"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {isApproved ? t('chat.hitl.planApproved') : t('chat.hitl.planRejected')}
          </span>
          {isRejected && (
            <span className="text-xs" style={{ color: 'var(--color-icon-muted)' }}>
              {t('chat.hitl.planFeedbackHint')}
            </span>
          )}
        </button>

        {/* Plan body -- expanded by default */}
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="pt-2 pb-1 pl-6">{resolvedBody}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  // --- Pending: full interactive ---
  return (
    <HitlPendingShell
      icon={<ScrollText className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />}
      title={t('chat.hitl.planApprovalRequired')}
      body={
        <div
          className="relative cursor-pointer rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--color-border-muted)' }}
          onClick={() => onDetailClick?.()}
        >
          <div className="px-4 py-3 overflow-hidden" style={{ maxHeight: '260px' }}>
            <Markdown variant="chat" content={description} className="text-sm" />
          </div>
          <div
            style={{
              position: 'absolute',
              bottom: 0, left: 0, right: 0, height: '64px',
              background: 'linear-gradient(to bottom, transparent, var(--color-bg-page))',
              pointerEvents: 'none',
            }}
          />
        </div>
      }
      footer={
        <HitlApproveRejectButtons
          onApprove={onApprove}
          onReject={onReject}
          approveLabel={t('chat.hitl.approve')}
          rejectLabel={t('chat.hitl.decline')}
        />
      }
    />
  );
}

export default PlanApprovalCard;
