/**
 * Agent long-term memory endpoints (LangGraph store).
 */
import { api } from '@/api/client';

export interface MemoryEntry {
  key: string;
  size: number;
  created_at: string | null;
  modified_at: string | null;
}

export interface MemoryListResponse {
  tier: 'user' | 'workspace';
  entries: MemoryEntry[];
}

export interface MemoryReadResponse {
  tier: 'user' | 'workspace';
  key: string;
  content: string;
  encoding: string;
  created_at: string | null;
  modified_at: string | null;
}

export async function listUserMemory(): Promise<MemoryListResponse> {
  const { data } = await api.get<MemoryListResponse>('/api/v1/memory/user');
  return data;
}

export async function readUserMemory(key: string): Promise<MemoryReadResponse> {
  const { data } = await api.get<MemoryReadResponse>('/api/v1/memory/user/read', {
    params: { key },
  });
  return data;
}

export async function listWorkspaceMemory(workspaceId: string): Promise<MemoryListResponse> {
  if (!workspaceId) throw new Error('Workspace ID is required');
  const { data } = await api.get<MemoryListResponse>(
    `/api/v1/memory/workspaces/${workspaceId}`,
  );
  return data;
}

export async function readWorkspaceMemory(
  workspaceId: string,
  key: string,
): Promise<MemoryReadResponse> {
  if (!workspaceId) throw new Error('Workspace ID is required');
  const { data } = await api.get<MemoryReadResponse>(
    `/api/v1/memory/workspaces/${workspaceId}/read`,
    { params: { key } },
  );
  return data;
}

export interface MemoryRecallHit {
  text: string;
  source: string;
  score: number;
  chars: number;
}

export interface MemoryRecallResponse {
  tier: 'user' | 'workspace';
  query: string;
  hits: MemoryRecallHit[];
}

/** BM25 keyword recall over the caller's long-term memory (mirrors
 *  `GET /api/v1/memory/recall` — the same tool the PTC agent uses, exposed
 *  read-only for the memory browser's search view). */
export async function recallMemory(
  query: string,
  opts?: { workspaceId?: string | null; topK?: number },
): Promise<MemoryRecallResponse> {
  if (!query.trim()) throw new Error('Query is required');
  const { data } = await api.get<MemoryRecallResponse>('/api/v1/memory/recall', {
    params: {
      q: query,
      ...(opts?.workspaceId ? { workspace_id: opts.workspaceId } : {}),
      ...(opts?.topK ? { top_k: opts.topK } : {}),
    },
  });
  return data;
}

// --- Memo (user-managed document store) -----------------------------------
