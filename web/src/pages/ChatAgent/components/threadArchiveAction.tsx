import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Archive } from 'lucide-react';
import { isThreadRunning } from '@/lib/threadLifecycle/store';
import ConfirmDialog from '@/components/ui/confirm-dialog';

export interface ThreadArchiveConfirm {
  /**
   * Archive `threadId` — immediately when nothing is running, else after the
   * user confirms. `archive` carries whatever the host's archive path needs
   * (cache patch, navigate-away, PATCH), so every trigger keeps its own.
   */
  requestArchive: (threadId: string, archive: () => void) => void;
  /** Render once at the host's root. */
  dialog: React.ReactNode;
}

/**
 * The single confirm choke point for archiving a thread. Archiving stays
 * allowed while a run is live (product call: the run survives, the row just
 * leaves the lists), so the gate is a confirm, not a block — and it exists
 * because both triggers are one-click hover affordances with no undo in view.
 *
 * Liveness comes from the thread lifecycle store, the frontend's only
 * authority on run status — read at click time, since a hook subscription
 * can't be taken per row from a shared handler.
 */
export function useArchiveThreadConfirm(): ThreadArchiveConfirm {
  const { t } = useTranslation();
  const [pending, setPending] = useState<{ threadId: string; archive: () => void } | null>(null);

  const requestArchive = useCallback((threadId: string, archive: () => void) => {
    if (!isThreadRunning(threadId)) {
      archive();
      return;
    }
    setPending({ threadId, archive });
  }, []);

  const handleConfirm = useCallback(() => {
    if (!pending) return;
    pending.archive();
    setPending(null);
  }, [pending]);

  const handleCancel = useCallback(() => setPending(null), []);

  return {
    requestArchive,
    dialog: (
      <ConfirmDialog
        open={!!pending}
        icon={<Archive aria-hidden className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-text-tertiary)' }} />}
        title={t('chat.archiveConfirm.title', 'Archive a running thread?')}
        description={t(
          'chat.archiveConfirm.body',
          "This thread has a run in progress. Archiving hides it from your lists while the run keeps going — you'll find it under Archived, with its results waiting.",
        )}
        confirmLabel={t('chat.archiveConfirm.confirm', 'Archive')}
        onConfirm={handleConfirm}
        onOpenChange={(o) => { if (!o) handleCancel(); }}
      />
    ),
  };
}
