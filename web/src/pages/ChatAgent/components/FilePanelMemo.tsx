import React, { useRef, useState, useEffect, Suspense } from 'react';
import { HardDrive, ScrollText } from 'lucide-react';
import { Loader } from '@/components/ui/loader';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useReadUserMemo } from '../hooks/useMemo';
import type { MemoStaleStatus } from './filePanelMemoHooks';

const CodeEditor = React.lazy(() => import('./viewers/CodeEditor'));

// --- MemoStaleBanner: detail-view banner with sync / view-diff CTAs ---

interface MemoStaleBannerProps {
  status: MemoStaleStatus;
  syncing: boolean;
  onSwitchToMemoTab: (() => void) | null;
  onSync: (() => void) | null;
  onViewDiff: (() => void) | null;
}

export function MemoStaleBanner({
  status,
  syncing,
  onSwitchToMemoTab,
  onSync,
  onViewDiff,
}: MemoStaleBannerProps): React.ReactElement {
  const { t } = useTranslation();
  const tone = status === 'stale' ? 'stale' : status === 'fresh' ? 'fresh' : 'neutral';
  const message =
    status === 'fresh' ? t('filePanel.memoBanner.fresh')
    : status === 'stale' ? t('filePanel.memoBanner.stale')
    : status === 'checking' ? t('filePanel.memoBanner.checking')
    : t('filePanel.memoBanner.unknown');
  return (
    <div className={`file-panel-memo-banner file-panel-memo-banner-${tone}`}>
      <ScrollText className="h-4 w-4 flex-shrink-0" />
      <span className="text-sm flex-1 truncate">{message}</span>
      <div className="file-panel-memo-banner-actions">
        {status === 'stale' && onViewDiff && (
          <button
            type="button"
            className="file-panel-memo-banner-action"
            onClick={onViewDiff}
            disabled={syncing}
          >
            {t('filePanel.memoBanner.viewDiff')}
          </button>
        )}
        {status === 'stale' && onSync && (
          <button
            type="button"
            className="file-panel-memo-banner-action file-panel-memo-banner-action-primary"
            onClick={onSync}
            disabled={syncing}
          >
            {syncing && (
              <span aria-hidden="true" className="flex-shrink-0">
                <Loader size={12} className="text-current" />
              </span>
            )}
            {syncing ? t('filePanel.memoBanner.syncing') : t('filePanel.memoBanner.sync')}
          </button>
        )}
        {onSwitchToMemoTab && (
          <button
            type="button"
            className="file-panel-memo-banner-action"
            onClick={onSwitchToMemoTab}
            disabled={syncing}
          >
            {t('context.viewInMemo')}
          </button>
        )}
      </div>
    </div>
  );
}

// --- MemoDiffModal: side-by-side compare of saved memo vs. workspace file ---

function DiffSpinner(): React.ReactElement {
  return (
    <div className="flex items-center justify-center h-full">
      <Loader size={20} className="text-[color:var(--color-text-tertiary)]" />
    </div>
  );
}

interface MemoDiffModalProps {
  open: boolean;
  memoKey: string | null;
  fileName: string;
  sandboxText: string;
  onClose: () => void;
}

export function MemoDiffModal({
  open,
  memoKey,
  fileName,
  sandboxText,
  onClose,
}: MemoDiffModalProps): React.ReactElement {
  const { t } = useTranslation();
  const { data: memoData, isLoading } = useReadUserMemo(memoKey, open && !!memoKey);
  const memoText = memoData?.content ?? '';

  // Monaco's diff editor splits its panes ~50/50 but the actual seam isn't
  // exactly at the wrapper's midpoint (the change-indicator strip lives there
  // and shifts the visible boundary). Measure the modified pane's DOM offset
  // so the header divider lines up with the real seam under any width.
  const editorWrapperRef = useRef<HTMLDivElement | null>(null);
  const [seamLeftPx, setSeamLeftPx] = useState<number | null>(null);
  useEffect(() => {
    if (!open) return undefined;
    const wrapper = editorWrapperRef.current;
    if (!wrapper) return undefined;

    const measure = () => {
      const modified = wrapper.querySelector(
        '.editor.modified, .modified-in-monaco-diff-editor'
      ) as HTMLElement | null;
      if (!modified) return false;
      const wrapperRect = wrapper.getBoundingClientRect();
      const modRect = modified.getBoundingClientRect();
      const offset = modRect.left - wrapperRect.left;
      if (offset > 0 && offset < wrapperRect.width) {
        setSeamLeftPx(offset);
        return true;
      }
      return false;
    };

    let attempts = 0;
    const pollId = window.setInterval(() => {
      attempts++;
      const ok = measure();
      if (ok || attempts > 30) window.clearInterval(pollId);
    }, 100);
    const observer = new ResizeObserver(() => { measure(); });
    observer.observe(wrapper);

    return () => {
      window.clearInterval(pollId);
      observer.disconnect();
    };
  }, [open, memoText]);

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent
        className="max-w-5xl"
        style={{
          width: '90vw',
          height: '80vh',
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'var(--color-bg-page)',
          borderColor: 'var(--color-border-muted)',
        }}
      >
        <div
          className="px-4 py-3 border-b"
          style={{ borderColor: 'var(--color-border-muted)' }}
        >
          <DialogTitle className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            {t('filePanel.memoBanner.diffTitle', { name: fileName })}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {t('filePanel.memoBanner.diffSubtitle')}
          </DialogDescription>
        </div>
        <div
          className="flex border-b"
          style={{ borderColor: 'var(--color-border-muted)' }}
        >
          <div
            className="flex items-center gap-2 px-4 py-2 border-r overflow-hidden"
            style={{
              width: seamLeftPx !== null ? `${seamLeftPx}px` : '50%',
              borderColor: 'var(--color-border-muted)',
              backgroundColor: 'var(--color-bg-card)',
            }}
          >
            <ScrollText className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-text-secondary)' }} />
            <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
              {t('filePanel.memoBanner.diffLeftLabel')}
            </span>
            <span className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('filePanel.memoBanner.diffLeftHint')}
            </span>
          </div>
          <div
            className="flex-1 flex items-center gap-2 px-4 py-2 overflow-hidden"
            style={{ backgroundColor: 'var(--color-bg-card)' }}
          >
            <HardDrive className="h-4 w-4 flex-shrink-0" style={{ color: 'var(--color-text-secondary)' }} />
            <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
              {t('filePanel.memoBanner.diffRightLabel')}
            </span>
            <span className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('filePanel.memoBanner.diffRightHint')}
            </span>
          </div>
        </div>
        <div ref={editorWrapperRef} className="flex-1 min-h-0 overflow-hidden">
          {isLoading ? (
            <DiffSpinner />
          ) : (
            <Suspense fallback={<DiffSpinner />}>
              <CodeEditor
                value={sandboxText}
                fileName={fileName}
                readOnly
                diffMode
                originalValue={memoText}
                height="100%"
              />
            </Suspense>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
