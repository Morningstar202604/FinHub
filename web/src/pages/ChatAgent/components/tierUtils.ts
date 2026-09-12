import type { ResourceTier } from '@/types/api';

import type { TFunction } from 'i18next';
type Translate = TFunction;

/** Tier presets, ordered for the change-spec radiogroup. */
export const TIER_ORDER: ResourceTier[] = ['standard', 'performance', 'max'];

/** Coerce an unknown/legacy tier value to a known tier (defaults to standard). */
export function normalizeTier(tier: unknown): ResourceTier {
  return tier === 'performance' || tier === 'max' ? tier : 'standard';
}

/** Localized display name for a tier. */
export function tierLabel(t: Translate, tier: ResourceTier): string {
  return t(`workspace.tier.${tier}`);
}
