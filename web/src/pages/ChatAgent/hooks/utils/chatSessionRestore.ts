const KEY = 'chat_session_restore';
const TTL_MS = 5 * 60 * 1000; // 5 minutes

export interface ChatSessionData {
  workspaceId: string;
  threadId?: string;
  ts: number;
}

export interface SaveChatSessionParams {
  workspaceId: string;
  threadId?: string | null;
}

export function saveChatSession({ workspaceId, threadId }: SaveChatSessionParams): void {
  if (!workspaceId) return;
  const data: ChatSessionData = { workspaceId, ts: Date.now() };
  if (threadId && threadId !== '__default__') {
    data.threadId = threadId;
  }
  sessionStorage.setItem(KEY, JSON.stringify(data));
}

export function getChatSession(): ChatSessionData | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  const session: ChatSessionData = JSON.parse(raw);
  if (Date.now() - session.ts > TTL_MS) {
    sessionStorage.removeItem(KEY);
    return null;
  }
  return session;
}

export function clearChatSession(): void {
  sessionStorage.removeItem(KEY);
}
