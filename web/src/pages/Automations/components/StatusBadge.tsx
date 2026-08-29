import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, type BadgeProps } from '@/components/ui/badge';

interface StatusBadgeProps {
  status: string;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const { t } = useTranslation();

  const STATUS_MAP: Record<string, { variant: BadgeProps['variant']; label: string }> = {
    active: { variant: 'success', label: t('automation.statusActive') },
    paused: { variant: 'warning', label: t('automation.statusPaused') },
    disabled: { variant: 'destructive', label: t('automation.statusDisabled') },
    completed: { variant: 'info', label: t('automation.statusCompleted') },
    failed: { variant: 'destructive', label: t('automation.statusFailed') },
    running: { variant: 'warning', label: t('automation.statusRunning') },
    pending: { variant: 'muted', label: t('automation.statusPending') },
  };

  const config = STATUS_MAP[status] || { variant: 'muted', label: status || t('automation.statusUnknown') };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
