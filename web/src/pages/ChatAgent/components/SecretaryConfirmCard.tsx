import React from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2, Square, MessageSquareX } from 'lucide-react';
import type { SecretaryActionProposalData as ProposalData } from '@/pages/ChatAgent/types/domain';
import { HitlApproveRejectButtons, HitlPendingShell, HitlResolvedShell, HitlDetailPanel } from './HitlCardShell';

type SecretaryActionType = 'delete_workspace' | 'stop_workspace' | 'delete_thread';

interface SecretaryConfirmCardProps {
  proposalData: ProposalData | null;
  onApprove?: () => void;
  onReject?: () => void;
}

const ACTION_CONFIG: Record<SecretaryActionType, {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  titleKey: string;
  approvedKey: string;
  rejectedKey: string;
  idLabelKey: string;
  idField: 'workspace_id' | 'thread_id';
}> = {
  delete_workspace: {
    icon: Trash2,
    titleKey: 'chat.hitl.secretary.deleteWorkspace',
    approvedKey: 'chat.hitl.secretary.deleteWorkspaceDone',
    rejectedKey: 'chat.hitl.secretary.deleteWorkspaceDeclined',
    idLabelKey: 'chat.hitl.secretary.workspaceLabel',
    idField: 'workspace_id',
  },
  stop_workspace: {
    icon: Square,
    titleKey: 'chat.hitl.secretary.stopWorkspace',
    approvedKey: 'chat.hitl.secretary.stopWorkspaceDone',
    rejectedKey: 'chat.hitl.secretary.stopWorkspaceDeclined',
    idLabelKey: 'chat.hitl.secretary.workspaceLabel',
    idField: 'workspace_id',
  },
  delete_thread: {
    icon: MessageSquareX,
    titleKey: 'chat.hitl.secretary.deleteThread',
    approvedKey: 'chat.hitl.secretary.deleteThreadDone',
    rejectedKey: 'chat.hitl.secretary.deleteThreadDeclined',
    idLabelKey: 'chat.hitl.secretary.threadLabel',
    idField: 'thread_id',
  },
};

/**
 * SecretaryConfirmCard - Generic HITL confirmation card for secretary actions.
 *
 * Handles delete_workspace, stop_workspace, and delete_thread interrupt types.
 *
 * Three states:
 *   pending  - action description + ID, Approve/Reject buttons
 *   approved - collapsed confirmation, expandable
 *   rejected - collapsed declined message
 */
function SecretaryConfirmCard({ proposalData, onApprove, onReject }: SecretaryConfirmCardProps) {
  const { t } = useTranslation();

  if (!proposalData) return null;

  const { actionType, status } = proposalData;
  const config = ACTION_CONFIG[actionType];
  if (!config) return null;

  const Icon = config.icon;
  const targetId = String(proposalData[config.idField] ?? 'unknown');
  const shortId = targetId.length > 12 ? `${targetId.slice(0, 8)}...` : targetId;
  const isApproved = status === 'approved';
  const isRejected = status === 'rejected';

  const idRow = (
    <div className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
      <span className="font-medium">{t(config.idLabelKey)}:</span>{' '}
      <span className="font-mono text-xs">{shortId}</span>
    </div>
  );

  // --- Resolved (approved / rejected) ---
  if (isApproved || isRejected) {
    return (
      <HitlResolvedShell
        state={status}
        label={t(isApproved ? config.approvedKey : config.rejectedKey)}
        body={<HitlDetailPanel dimmed={isRejected}>{idRow}</HitlDetailPanel>}
      />
    );
  }

  // --- Pending: interactive ---
  return (
    <HitlPendingShell
      icon={<Icon className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />}
      title={t(config.titleKey)}
      body={<HitlDetailPanel>{idRow}</HitlDetailPanel>}
      footer={
        <HitlApproveRejectButtons
          onApprove={onApprove}
          onReject={onReject}
          approveLabel={t('chat.hitl.confirm')}
          rejectLabel={t('chat.hitl.decline')}
        />
      }
    />
  );
}

export default SecretaryConfirmCard;
