import React from 'react';
import { useTranslation } from 'react-i18next';
import { MessageSquareText } from 'lucide-react';
import type { StartQuestionProposalData as ProposalData } from '@/pages/ChatAgent/types/domain';
import { HitlApproveRejectButtons, HitlPendingShell, HitlResolvedShell, HitlDetailPanel } from './HitlCardShell';

interface StartQuestionCardProps {
  proposalData: ProposalData | null;
  onApprove?: () => void;
  onReject?: () => void;
}


/**
 * StartQuestionCard - Inline HITL card for starter question approval.
 *
 * Three states:
 *   pending  - question text preview, Approve/Reject buttons
 *   approved - collapsed "Question started", expandable to show question
 *   rejected - collapsed "Question declined"
 */
function StartQuestionCard({ proposalData, onApprove, onReject }: StartQuestionCardProps) {
  const { t } = useTranslation();

  if (!proposalData) return null;

  const { question, status } = proposalData;
  const isApproved = status === 'approved';
  const isRejected = status === 'rejected';

  const questionBody = (
    <HitlDetailPanel dimmed={isRejected}>
      <div className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
        {question}
      </div>
    </HitlDetailPanel>
  );

  // --- Resolved (approved / rejected) ---
  if (isApproved || isRejected) {
    return (
      <HitlResolvedShell
        state={status}
        label={isApproved ? t('chat.questionStarted') : t('chat.questionDeclined')}
        body={questionBody}
      />
    );
  }

  // --- Pending: interactive ---
  return (
    <HitlPendingShell
      icon={<MessageSquareText className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />}
      title={t('chat.startQuestion')}
      body={questionBody}
      footer={
        <HitlApproveRejectButtons
          onApprove={onApprove}
          onReject={onReject}
          approveLabel={t('chat.letsGo')}
          rejectLabel={t('chat.skip')}
        />
      }
    />
  );
}

export default StartQuestionCard;
