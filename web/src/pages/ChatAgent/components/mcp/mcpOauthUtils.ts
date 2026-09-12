import type { McpOauthStatus } from '../../utils/api';
import { AlertCircle, CheckCircle2, MinusCircle, type LucideIcon } from 'lucide-react';

interface PillMeta {
  labelKey: string;
  color: string;
  bg: string;
  icon: LucideIcon;
}

export const OAUTH_META: Record<McpOauthStatus, PillMeta> = {
  connected: {
    labelKey: 'plugins.oauth.connected',
    color: 'var(--color-profit)',
    bg: 'var(--color-profit-soft)',
    icon: CheckCircle2,
  },
  needs_reauth: {
    labelKey: 'plugins.oauth.needsReauth',
    color: 'var(--color-warning)',
    bg: 'var(--color-warning-soft)',
    icon: AlertCircle,
  },
  refresh_ambiguous: {
    labelKey: 'plugins.oauth.refreshAmbiguous',
    color: 'var(--color-warning)',
    bg: 'var(--color-warning-soft)',
    icon: AlertCircle,
  },
  revoked: {
    labelKey: 'plugins.oauth.revoked',
    color: 'var(--color-text-tertiary)',
    bg: 'var(--color-bg-tag)',
    icon: MinusCircle,
  },
};

export function oauthLabelKey(status: McpOauthStatus | null | undefined): string | null {
  return (status && OAUTH_META[status]?.labelKey) || null;
}
