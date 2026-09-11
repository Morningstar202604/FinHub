import { useTranslation } from 'react-i18next';
import type { ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Loader } from '@/components/ui/loader';

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  /** Body copy. `message` is accepted as a backward-compat alias. */
  description?: ReactNode;
  message?: ReactNode;
  /** Destructive action: red confirm button, "Delete" default label, warning accent. */
  danger?: boolean;
  /** Show the red warning icon in the header (defaults to `danger`). */
  warningIcon?: boolean;
  /** Leading icon before the title for non-danger contexts (e.g. Archive). */
  icon?: ReactNode;
  /** Optional error text rendered above the footer. */
  error?: ReactNode;
  /** Confirm button label. Defaults to "Delete" (danger) or "Confirm" (neutral). */
  confirmLabel?: ReactNode;
  /** Cancel button label. Defaults to i18n "Cancel". */
  cancelLabel?: ReactNode;
  /** Disable + spinner on the confirm button. */
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
  /** Extra body content (text inputs, etc.). */
  children?: ReactNode;
  /** Close automatically after onConfirm resolves. Set false when the caller
   *  keeps the dialog open during a long action and closes it on success. */
  autoCloseOnConfirm?: boolean;
}

/**
 * The one shared confirmation surface. Destructive actions pass `danger`;
 * neutral ones (logout, reset, archive) omit it. Duplicates the shape of the
 * ~8 bespoke confirm dialogs that each re-implemented the same header +
 * cancel/confirm footer.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  message,
  danger,
  warningIcon,
  icon,
  error,
  confirmLabel,
  cancelLabel,
  loading,
  onConfirm,
  children,
  autoCloseOnConfirm = true,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const body = description ?? message;
  const showWarning = warningIcon ?? danger;
  const confirmText = confirmLabel ?? (danger ? t('common.delete') : t('common.confirm', 'Confirm'));

  const handleConfirm = async () => {
    const result = onConfirm();
    await result;
    if (autoCloseOnConfirm) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        style={{ backgroundColor: 'var(--color-bg-elevated)', borderColor: 'var(--color-border-elevated)' }}
      >
        <DialogHeader>
          {showWarning ? (
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: 'color-mix(in srgb, var(--color-loss) 18%, transparent)' }}
              >
                <AlertTriangle className="h-5 w-5" style={{ color: 'var(--color-loss)' }} />
              </div>
              <DialogTitle className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {title}
              </DialogTitle>
            </div>
          ) : (
            <DialogTitle className="flex items-center gap-2" style={{ color: 'var(--color-text-primary)' }}>
              {icon}
              {title}
            </DialogTitle>
          )}
          {body != null && (
            <DialogDescription style={{ color: 'var(--color-text-secondary)' }}>{body}</DialogDescription>
          )}
        </DialogHeader>

        {children}

        {error && (
          <div
            className="rounded-md p-3 text-sm"
            style={{
              color: 'var(--color-loss)',
              backgroundColor: 'color-mix(in srgb, var(--color-loss) 10%, transparent)',
              border: '1px solid color-mix(in srgb, var(--color-loss) 30%, transparent)',
            }}
          >
            {error}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
            style={{ color: 'var(--color-text-primary)' }}
          >
            {cancelLabel ?? t('common.cancel')}
          </Button>
          <Button
            variant={danger ? 'destructive' : 'default'}
            onClick={handleConfirm}
            disabled={loading}
            className="min-w-[5rem] gap-1.5"
          >
            {loading && <Loader size={12} speed={0.6} label="" />}
            {confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConfirmDialog;
