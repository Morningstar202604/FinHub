import { useState, useCallback, useRef } from 'react';

const MAX_ENTRIES = 5;

export interface CacheEntry {
  key: string;           // `${workspaceId}-${threadId}`
  instanceId: number;    // stable React key — never changes after creation
  workspaceId: string;
  threadId: string;
  workspaceName: string;
  initialTaskId?: string;
}

export type TouchParams = Omit<CacheEntry, 'key' | 'instanceId'>;

function makeKey(workspaceId: string, threadId: string): string {
  return `${workspaceId}-${threadId}`;
}

export function useChatViewCache() {
  const [entries, setEntries] = useState<CacheEntry[]>([]);
  const nextIdRef = useRef(1);

  // Idempotent: if entry already exists with same key and is already active, no state update.
  const touch = useCallback((params: TouchParams) => {
    const key = makeKey(params.workspaceId, params.threadId);

    setEntries(prev => {
      const idx = prev.findIndex(e => e.key === key);
      if (idx === 0) {
        // Already MRU — update fields if changed
        const existing = prev[0];
        if (
          existing.workspaceName === params.workspaceName &&
          existing.initialTaskId === params.initialTaskId
        ) {
          return prev; // truly no change — skip re-render
        }
        const updated = [...prev];
        updated[0] = { ...existing, ...params, key, instanceId: existing.instanceId };
        return updated;
      }

      let newEntries: CacheEntry[];
      if (idx > 0) {
        // Promote to front
        const entry = prev[idx];
        newEntries = [{ ...entry, ...params, key, instanceId: entry.instanceId }, ...prev.slice(0, idx), ...prev.slice(idx + 1)];
      } else {
        // New entry
        const instanceId = nextIdRef.current++;
        newEntries = [{ ...params, key, instanceId }, ...prev];
      }

      // Evict LRU if over cap
      if (newEntries.length > MAX_ENTRIES) {
        newEntries = newEntries.slice(0, MAX_ENTRIES);
      }

      return newEntries;
    });
  }, []);

  // Update key in-place (e.g., __default__ → real threadId).
  // instanceId is preserved so React doesn't remount.
  const updateKey = useCallback((oldKey: string, newKey: string, updates: Partial<Omit<CacheEntry, 'key' | 'instanceId'>>) => {
    setEntries(prev => {
      const idx = prev.findIndex(e => e.key === oldKey);
      if (idx === -1) return prev;
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...updates, key: newKey };
      return updated;
    });
  }, []);

  return { entries, touch, updateKey };
}
