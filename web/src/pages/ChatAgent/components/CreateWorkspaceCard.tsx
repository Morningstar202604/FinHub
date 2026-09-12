import React from 'react';
import { useTranslation } from 'react-i18next';
import { FolderPlus } from 'lucide-react';
import type { CreateWorkspaceProposalData as ProposalData } from '@/pages/ChatAgent/types/domain';
import { HitlApproveRejectButtons, HitlPendingShell, HitlResolvedShell, HitlDetailPanel } from './HitlCardShell';

interface CreateWorkspaceCardProps {
  proposalData: ProposalData | null;
  onApprove?: () => void;
  onReject?: () => void;
}

/**
 * CreateWorkspaceCard - Inline HITL card for workspace creation approval.
 *
 * Three states:
 *   pending  - workspace name + description, Approve/Reject buttons
 *   approved - collapsed "Workspace created: [name]", expandable
 *   rejected - collapsed "Workspace creation declined"
 */
function CreateWorkspaceCard({ proposalData, onApprove, onReject }: CreateWorkspaceCardProps) {
  const { t } = useTranslation();

  if (!proposalData) return null;

  const { workspace_name, workspace_description, status } = proposalData;
  const isApproved = status === 'approved';
  const isRejected = status === 'rejected';

  const detailBody = (
    <HitlDetailPanel dimmed={isRejected}>
      <div className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
        {workspace_name}
      </div>
      {workspace_description && (
        <div className="text-sm mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
          {workspace_description}
        </div>
      )}
    </HitlDetailPanel>
  );

  // --- Resolved (approved / rejected) ---
  if (isApproved || isRejected) {
    return (
      <HitlResolvedShell
        state={status}
        label={isApproved
          ? t('chat.hitl.workspaceCreated', { name: workspace_name })
          : t('chat.hitl.workspaceDeclined')}
        body={detailBody}
      />
    );
  }

  // --- Pending: interactive ---
  return (
    <HitlPendingShell
      icon={<FolderPlus className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-accent-light)' }} />}
      title={t('chat.hitl.createWorkspace')}
      body={
        <HitlDetailPanel>
          <div className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
            {workspace_name}
          </div>
          {workspace_description && (
            <div className="text-sm mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
              {workspace_description}
            </div>
          )}
        </HitlDetailPanel>
      }
      footer={
        <HitlApproveRejectButtons
          onApprove={onApprove}
          onReject={onReject}
          approveLabel={t('chat.hitl.create')}
          rejectLabel={t('chat.hitl.decline')}
        />
      }
    />
  );
}

export default CreateWorkspaceCard;
