import React from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  workspaceName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
  error?: string | null;
  itemType?: 'workspace' | 'thread';
}

/**
 * DeleteConfirmModal Component
 *
 * Confirmation dialog for deleting a workspace or thread.
 * Bottom-sheet on mobile, centered on desktop.
 */
function DeleteConfirmModal({ isOpen, workspaceName, onConfirm, onCancel, isDeleting, error, itemType = 'workspace' }: DeleteConfirmModalProps) {
  const itemLabel = itemType === 'thread' ? 'thread' : 'workspace';
  const itemLabelCapitalized = itemType === 'thread' ? 'Thread' : 'Workspace';

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onCancel(); }}>
      <DialogContent
        style={{
          backgroundColor: 'var(--color-bg-page)',
          borderColor: 'var(--color-border-muted)',
        }}
      >
        {/* Warning icon + title */}
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: 'rgba(255, 56, 60, 0.2)' }}
          >
            <AlertTriangle className="h-5 w-5" style={{ color: 'var(--color-loss)' }} />
          </div>
          <DialogTitle className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Delete {itemLabelCapitalized}
          </DialogTitle>
        </div>

        {/* Message */}
        <DialogDescription asChild>
          <div>
            <p className="text-sm mb-2" style={{ color: 'var(--color-text-primary)' }}>
              Are you sure you want to delete the {itemLabel}
            </p>
            <p className="text-base font-medium mb-4" style={{ color: 'var(--color-text-primary)' }}>
              &ldquo;{workspaceName}&rdquo;?
            </p>
            <p className="text-xs" style={{ color: 'var(--color-loss)', opacity: 0.8 }}>
              This action cannot be undone. All data in this {itemLabel} will be permanently deleted.
            </p>
          </div>
        </DialogDescription>

        {/* Error message */}
        {error && (
          <div className="p-3 rounded-md" style={{ backgroundColor: 'rgba(255, 56, 60, 0.1)', border: '1px solid rgba(255, 56, 60, 0.3)' }}>
            <p className="text-sm" style={{ color: 'var(--color-loss)' }}>
              {error}
            </p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 justify-end pt-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isDeleting}
            className="px-4 py-2 rounded-md text-sm font-medium transition-colors hover:bg-foreground/10 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isDeleting}
            className="px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              backgroundColor: isDeleting ? 'var(--color-loss-soft)' : 'var(--color-loss)',
              color: 'var(--color-text-on-accent)',
            }}
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default DeleteConfirmModal;
