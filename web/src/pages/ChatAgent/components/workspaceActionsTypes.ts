import type { ResourceTier } from '@/types/api';

/** Minimal workspace shape the menu + actions need — both the gallery's richer
 *  record and the nav tree's loose entry satisfy it. */
export interface MenuWorkspace {
  workspace_id: string;
  name?: string;
  status?: string;
  is_pinned?: boolean;
  is_always_on?: boolean;
  /** Preselects the change-spec dialog's current tier. */
  resource_tier?: ResourceTier;
  [key: string]: unknown;
}

export interface WorkspaceActions {
  openUpgrade: (workspace: MenuWorkspace) => void;
  toggleAlwaysOn: (workspace: MenuWorkspace) => void;
  openDuplicate: (workspace: MenuWorkspace) => void;
  openDelete: (workspace: MenuWorkspace) => void;
  /** Render once at the host's root — the confirm/config dialogs. */
  dialogs: React.ReactNode;
}

/** Which flow just succeeded, so a host reacts to only the ones it cares about. */
export type WorkspaceMutationOp = 'spec' | 'always-on' | 'duplicate';

export interface UseWorkspaceActionsOptions {
  currentWorkspaceId?: string | null;
  /** After a successful CRUD flow. The gallery re-snaps to page 0 on 'duplicate' (the copy lands at the top). */
  onAfterMutate?: (op: WorkspaceMutationOp) => void;
  /** After a successful delete, with the removed id — a paginated host may need to step back a page. */
  onAfterDelete?: (wsId: string) => void;
}
