import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/components/ui/use-toast';
import { isPlatformMode } from '@/config/hostMode';
import type { ResourceTier } from '@/types/api';
import { queryKeys } from '@/lib/queryKeys';
import {
  deleteWorkspace,
  setWorkspaceSpec,
  setWorkspaceAlwaysOn,
  duplicateWorkspace,
  getWorkspaceQuota,
} from '../utils/api';
import { useWorkspaceMutation } from '../hooks/useWorkspaceMutation';
import { forgetStableNavOrder } from '../hooks/useNavigationData';
import { forgetSharedWorkspaceThreads } from '@/lib/navThreadsStore';
import { removeStoredThreadId } from '../hooks/useChatMessages';
import { clearAllMarketThreadsForWorkspace } from '../../MarketView/utils/threadPersistence';
import { forgetNavPanelExpansion } from './navExpansionStore';
import { scrollMemory } from '@/lib/scrollMemory';
import ChangeSpecDialog from './ChangeSpecDialog';
import { tierLabel } from './tierUtils';
import { entitlementErrorMessage } from './workspaceActionsUtils';
import ConfirmDialog from '@/components/ui/confirm-dialog';
import type {
  MenuWorkspace,
  UseWorkspaceActionsOptions,
  WorkspaceActions,
} from './workspaceActionsTypes';

/**
 * Self-contained change-spec / always-on / duplicate / delete actions with
 * their dialogs. The canonical implementation for every host (gallery card,
 * sidebar tree, mobile drawer): same mutations, entitlement mapping, toasts,
 * and delete cleanup; deleting the currently-open workspace navigates back to
 * the gallery. Host-specific presentation lands in the two callbacks.
 */
export function useWorkspaceActions({
  currentWorkspaceId,
  onAfterMutate,
  onAfterDelete,
}: UseWorkspaceActionsOptions): WorkspaceActions {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [upgradeTarget, setUpgradeTarget] = useState<MenuWorkspace | null>(null);
  const [alwaysOnTarget, setAlwaysOnTarget] = useState<MenuWorkspace | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<MenuWorkspace | null>(null);
  const [duplicateBusy, setDuplicateBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<MenuWorkspace | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const upgradeMutation = useWorkspaceMutation<ResourceTier>({
    mutationFn: (wsId, tier) => setWorkspaceSpec(wsId, tier),
    optimisticPatch: (tier) => ({ resource_tier: tier }),
    invalidateQuota: true,
    errorTitleKey: 'workspace.specFailed',
    mapError: (err, tier) => entitlementErrorMessage(err, t, tier),
  });
  const alwaysOnMutation = useWorkspaceMutation<boolean>({
    mutationFn: (wsId, next) => setWorkspaceAlwaysOn(wsId, next),
    optimisticPatch: (next) => ({ is_always_on: next }),
    invalidateQuota: true,
    errorTitleKey: 'workspace.alwaysOnFailed',
    mapError: (err) => entitlementErrorMessage(err, t),
  });

  // Per-tier count quotas for the change-spec dialog's "N left" hint.
  // Platform mode only, fetched lazily when the dialog opens; null in OSS mode.
  const { data: workspaceQuota } = useQuery({
    queryKey: queryKeys.workspaces.quota(),
    queryFn: getWorkspaceQuota,
    enabled: isPlatformMode && !!upgradeTarget,
    staleTime: 60_000,
  });

  const handleUpgradeSubmit = async (tier: ResourceTier) => {
    if (!upgradeTarget) return;
    const ok = await upgradeMutation.run(upgradeTarget.workspace_id, tier);
    if (ok) {
      setUpgradeTarget(null);
      toast({ title: t('workspace.specUpdated', 'Workspace spec updated'), description: tierLabel(t, tier) });
      onAfterMutate?.('spec');
    }
  };

  const applyAlwaysOn = async (workspace: MenuWorkspace, next: boolean) => {
    const ok = await alwaysOnMutation.run(workspace.workspace_id, next);
    if (ok) {
      setAlwaysOnTarget((cur) => (cur?.workspace_id === workspace.workspace_id ? null : cur));
      onAfterMutate?.('always-on');
    }
  };

  const toggleAlwaysOn = (workspace: MenuWorkspace) => {
    if (alwaysOnMutation.busyIds.has(workspace.workspace_id)) return;
    if (workspace.is_always_on === true) {
      void applyAlwaysOn(workspace, false);
    } else {
      setAlwaysOnTarget(workspace);
    }
  };

  const handleDuplicateConfirm = async () => {
    if (!duplicateTarget || duplicateBusy) return;
    setDuplicateBusy(true);
    try {
      await duplicateWorkspace(duplicateTarget.workspace_id);
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.quota() });
      setDuplicateTarget(null);
      toast({ title: t('workspace.duplicated', 'Workspace duplicated') });
      onAfterMutate?.('duplicate');
    } catch (err) {
      console.error('Error duplicating workspace:', err);
      toast({ variant: 'destructive', title: t('workspace.duplicateFailed', 'Could not duplicate workspace'), description: entitlementErrorMessage(err, t) });
    } finally {
      setDuplicateBusy(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const wsId = deleteTarget.workspace_id;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(wsId);
      // Same cleanup set as the gallery's delete: stored thread pointers
      // (chat + market), remembered tree expansion, frozen nav orders, and the
      // shared thread lists — so nothing re-expands or 404s a dead workspace.
      removeStoredThreadId(wsId);
      clearAllMarketThreadsForWorkspace(wsId);
      forgetNavPanelExpansion(wsId);
      forgetStableNavOrder(wsId);
      forgetSharedWorkspaceThreads(wsId);
      scrollMemory.forget(`threads:${wsId}:active`);
      scrollMemory.forget(`threads:${wsId}:archived`);
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.lists() });
      onAfterDelete?.(wsId);
      if (currentWorkspaceId === wsId) {
        navigate('/chat');
      }
      setDeleteTarget(null);
    } catch (err) {
      console.error('Error deleting workspace:', err);
      setDeleteError(err instanceof Error && err.message ? err.message : t('workspace.failedDeleteWorkspace'));
    } finally {
      setDeleteBusy(false);
    }
  };

  const dialogs = (
    <>
      <ChangeSpecDialog
        target={upgradeTarget}
        onClose={() => setUpgradeTarget(null)}
        onSubmit={(tier) => void handleUpgradeSubmit(tier)}
        busy={!!upgradeTarget && upgradeMutation.busyIds.has(upgradeTarget.workspace_id)}
        quota={workspaceQuota}
      />
      <ConfirmDialog
        open={!!alwaysOnTarget}
        onOpenChange={(open) => { if (!open) setAlwaysOnTarget(null); }}
        title={t('workspace.alwaysOnEnable', 'Turn on always-on')}
        message={alwaysOnTarget?.status === 'stopped'
          ? t('workspace.alwaysOnConfirmStopped', { name: alwaysOnTarget?.name ?? '', defaultValue: 'Start "{{name}}" now and keep it running 24/7? The sandbox starts immediately, skips idle shutdown, and keeps billing until you turn always-on off.' })
          : t('workspace.alwaysOnConfirm', { name: alwaysOnTarget?.name ?? '', defaultValue: 'Keep "{{name}}" running 24/7? The sandbox skips idle shutdown and keeps billing until you turn always-on off.' })}
        loading={!!alwaysOnTarget && alwaysOnMutation.busyIds.has(alwaysOnTarget.workspace_id)}
        confirmLabel={t('workspace.alwaysOnEnableConfirm', 'Turn on')}
        onConfirm={() => { if (alwaysOnTarget) void applyAlwaysOn(alwaysOnTarget, true); }}
      />
      <ConfirmDialog
        open={!!duplicateTarget}
        onOpenChange={(open) => { if (!open) setDuplicateTarget(null); }}
        title={t('workspace.duplicate', 'Duplicate')}
        message={t('workspace.duplicateConfirm', { name: duplicateTarget?.name ?? '', defaultValue: 'Create a copy of "{{name}}"? Files are copied; always-on starts off on the copy.' })}
        loading={duplicateBusy}
        confirmLabel={t('workspace.duplicating', 'Duplicating…')}
        onConfirm={() => void handleDuplicateConfirm()}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        danger
        autoCloseOnConfirm={false}
        loading={deleteBusy}
        title="Delete Workspace"
        description={`Are you sure you want to delete the workspace "${deleteTarget?.name || ''}"? This action cannot be undone.`}
        error={deleteError}
        confirmLabel={deleteBusy ? 'Deleting...' : 'Delete'}
        onConfirm={() => void handleConfirmDelete()}
        onOpenChange={(open) => { if (!open) { setDeleteTarget(null); setDeleteError(null); } }}
      />
    </>
  );

  return {
    openUpgrade: setUpgradeTarget,
    toggleAlwaysOn,
    openDuplicate: setDuplicateTarget,
    openDelete: (ws) => { setDeleteTarget(ws); setDeleteError(null); },
    dialogs,
  };
}
