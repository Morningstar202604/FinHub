import { useMemo, useCallback, useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader } from '@/components/ui/loader';
import { useToast } from '@/components/ui/use-toast';
import { ToastAction } from '@/components/ui/toast';
import { useUploadUserMemo, useUserMemoList } from '../hooks/useMemo';
import type { MemoEntry } from '../utils/api';

// Mirror of ACCEPTED_MIME_TYPES in src/ptc_agent/agent/memo/schema.py.
const MEMO_EXT_TO_MIME: Record<string, string> = {
  md: 'text/markdown',
  txt: 'text/plain',
  csv: 'text/csv',
  json: 'application/json',
  pdf: 'application/pdf',
};

export function memoMimeForName(name: string): string | null {
  const i = name.lastIndexOf('.');
  if (i < 0) return null;
  return MEMO_EXT_TO_MIME[name.slice(i + 1).toLowerCase()] ?? null;
}

// --- useWorkspaceMemoIndex: workspace path → memo entry, for badge + banner lookup ---

// Toasts are width-constrained (~360px) and a long filename in quotes wraps
// awkwardly. Elide the middle, preserving the extension so the user can still
// recognize the file: "accelerator_landscape.md" → "accelerator_l…pe.md".
function shortenFilename(name: string, max = 22): string {
  if (name.length <= max) return name;
  const dot = name.lastIndexOf('.');
  if (dot > 0 && name.length - dot <= 6) {
    const ext = name.slice(dot);
    const headLen = Math.max(1, max - ext.length - 1);
    return name.slice(0, headLen) + '…' + ext;
  }
  return name.slice(0, max - 1) + '…';
}

export function useWorkspaceMemoIndex(workspaceId: string): Map<string, MemoEntry> {
  const { data: memoListData } = useUserMemoList(true);
  return useMemo(() => {
    const map = new Map<string, MemoEntry>();
    const entries = memoListData?.entries ?? [];
    for (const entry of entries) {
      if (
        entry.source_kind === 'sandbox'
        && entry.source_workspace_id === workspaceId
        && entry.source_path
      ) {
        map.set(entry.source_path, entry);
      }
    }
    return map;
  }, [memoListData, workspaceId]);
}

// --- useAddToMemo: upload a workspace file into the user's memo store ---

interface UseAddToMemoArgs {
  workspaceId: string;
  downloadFileAsArrayBufferFn: (workspaceId: string, path: string) => Promise<ArrayBuffer>;
  readFileFullFn: (workspaceId: string, path: string) => Promise<{ content: string }>;
  onSwitchToMemoTab: (() => void) | null | undefined;
}

export function useAddToMemo({
  workspaceId,
  downloadFileAsArrayBufferFn,
  readFileFullFn,
  onSwitchToMemoTab,
}: UseAddToMemoArgs): (filePath: string) => Promise<void> {
  const { t } = useTranslation();
  const { toast } = useToast();
  const uploadMemoMutation = useUploadUserMemo();

  return useCallback(async (filePath: string) => {
    const fileName = filePath.split('/').pop() || filePath;
    const mime = memoMimeForName(fileName);
    if (!mime) {
      toast({
        variant: 'destructive',
        title: t('context.memoAddError'),
        description: t('context.memoUnsupportedType'),
      });
      return;
    }
    const shortName = shortenFilename(fileName);
    const loading = toast({
      title: t('context.memoAdding', { name: shortName }),
      description: (
        <span className="inline-flex items-center gap-2 text-xs">
          <span aria-hidden="true" className="flex-shrink-0">
            <Loader size={14} className="text-current" />
          </span>
          {t('context.memoUploading')}
        </span>
      ),
      duration: Infinity,
    });
    try {
      // For text mimes, route through /files/read (unlimited) so the bytes we
      // upload are exactly what the detail view will later display. Going via
      // /files/download would skip vault-secret redaction and preserve a
      // trailing newline that /files/read strips — making future stale checks
      // false-positive even when the file hasn't changed.
      let file: File;
      if (mime === 'application/pdf') {
        const buf = await downloadFileAsArrayBufferFn(workspaceId, filePath);
        file = new globalThis.File([buf], fileName, { type: mime });
      } else {
        const data = await readFileFullFn(workspaceId, filePath);
        const text = (data?.content as string | undefined) ?? '';
        const bytes = new TextEncoder().encode(text);
        file = new globalThis.File([bytes], fileName, { type: mime });
      }
      const result = await uploadMemoMutation.mutateAsync({
        file,
        source: {
          source_kind: 'sandbox',
          source_workspace_id: workspaceId,
          source_path: filePath,
        },
      });
      loading.dismiss();
      toast({
        title: result.replaced
          ? t('context.memoUpdateSuccess', { name: shortName })
          : t('context.memoAddSuccess', { name: shortName }),
        description: (
          <span className="inline-flex items-center gap-2 text-xs">
            <span aria-hidden="true" className="flex-shrink-0">
              <Loader size={14} className="text-current" />
            </span>
            {t('context.memoGenerating')}
          </span>
        ),
        action: onSwitchToMemoTab ? (
          <ToastAction
            altText={t('context.viewInMemo')}
            onClick={() => onSwitchToMemoTab()}
          >
            {t('context.viewInMemo')}
          </ToastAction>
        ) : undefined,
        duration: 8000,
      });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      loading.dismiss();
      toast({
        variant: 'destructive',
        title: t('context.memoAddError'),
        description: e?.response?.data?.detail || e?.message || String(err),
        duration: 6000,
      });
    }
  }, [workspaceId, downloadFileAsArrayBufferFn, readFileFullFn, uploadMemoMutation, onSwitchToMemoTab, toast, t]);
}

// --- useMemoStaleCheck: cold-path verdict for the currently selected file ---

export type MemoStaleStatus = 'unknown' | 'checking' | 'fresh' | 'stale';

interface UseMemoStaleCheckArgs {
  workspaceId: string;
  selectedFile: string | null;
  fileMime: string | null | undefined;
  memoSha256: string | null;
  readFileFullFn: (workspaceId: string, path: string) => Promise<{ content: string }>;
}

interface UseMemoStaleCheckResult {
  status: MemoStaleStatus;
  sandboxText: string | null;
  refresh: () => void;
}

export function useMemoStaleCheck({
  workspaceId,
  selectedFile,
  fileMime,
  memoSha256,
  readFileFullFn,
}: UseMemoStaleCheckArgs): UseMemoStaleCheckResult {
  const [status, setStatus] = useState<MemoStaleStatus>('unknown');
  const [sandboxText, setSandboxText] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  // Track which file the last verdict was computed for, so silent re-checks
  // (memoListData polling, fileMime arriving after click) don't flicker the
  // banner CTAs in and out via a transient "checking" state.
  const lastVerdictFileRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedFile || !memoSha256) {
      setStatus('unknown');
      setSandboxText(null);
      lastVerdictFileRef.current = selectedFile;
      return;
    }
    if (fileMime === 'pdf' || fileMime === 'image' || fileMime === 'excel') {
      setStatus('unknown');
      setSandboxText(null);
      lastVerdictFileRef.current = selectedFile;
      return;
    }
    const isFileChange = lastVerdictFileRef.current !== selectedFile;
    lastVerdictFileRef.current = selectedFile;
    setStatus((prev) =>
      isFileChange || (prev !== 'fresh' && prev !== 'stale') ? 'checking' : prev
    );
    let cancelled = false;
    (async () => {
      try {
        const data = await readFileFullFn(workspaceId, selectedFile);
        const text = (data?.content as string | undefined) ?? '';
        const bytes = new TextEncoder().encode(text);
        const buf = await crypto.subtle.digest('SHA-256', bytes);
        const hex = Array.from(new Uint8Array(buf))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        if (cancelled) return;
        setSandboxText(text);
        setStatus(hex === memoSha256 ? 'fresh' : 'stale');
      } catch {
        if (!cancelled) {
          setStatus('unknown');
          setSandboxText(null);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [memoSha256, selectedFile, fileMime, readFileFullFn, workspaceId, nonce]);

  const refresh = useCallback(() => { setNonce((n) => n + 1); }, []);
  return { status, sandboxText, refresh };
}

