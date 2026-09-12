import type { ResourceTier } from '@/types/api';
import { isPlatformMode } from '@/config/hostMode';
import {
  formatApiErrorDetail,
  apiErrorDetailMessage,
  apiErrorStatus,
} from '../utils/api';
import { tierLabel } from './tierUtils';

import type { TFunction } from 'i18next';
type Translate = TFunction;

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

/** Map entitlement failures (403 plan-gate / 429 quota) to actionable copy in
 *  platform mode; generic API detail otherwise. Single source — the gallery
 *  imports this too. */
export function entitlementErrorMessage(
  err: unknown,
  t: Translate,
  tier?: ResourceTier,
): string {
  if (isPlatformMode) {
    const status = apiErrorStatus(err);
    if (status === 403) {
      return t('workspace.notOnPlan', 'Not available on your plan — upgrade to unlock.');
    }
    if (status === 429) {
      const platformMessage = apiErrorDetailMessage(err);
      if (platformMessage) return platformMessage;
      if (tier) {
        return t('workspace.tierLimitReached', "You've reached your {{tier}} workspace limit.", {
          tier: tierLabel(t, tier),
        });
      }
      return t('workspace.workspaceLimitReached', "You've reached your workspace limit.");
    }
  }
  return formatApiErrorDetail(err);
}

/** Which flow just succeeded, so a host reacts to only the ones it cares about. */
export type WorkspaceMutationOp = 'spec' | 'always-on' | 'duplicate';
