/**
 * Recently sent messages tracker
 * Tracks recently sent messages to avoid duplicates when loading history
 */

const RETENTION_TIME_MS = 5 * 60 * 1000; // 5 minutes

interface TrackedMessage {
  content: string;
  timestamp: Date;
  id: string;
}

export interface RecentlySentTracker {
  track: (content: string, timestamp: Date, id: string) => void;
  isRecentlySent: (content: string) => boolean;
  clear: () => void;
}

/**
 * Creates a tracker for recently sent messages
 */
export function createRecentlySentTracker(): RecentlySentTracker {
  const messages = new Map<string, TrackedMessage>();

  /**
   * Tracks a recently sent message
   */
  function track(content: string, timestamp: Date, id: string): void {
    const messageKey = `${content}-${Date.now()}`;
    messages.set(messageKey, {
      content: content.trim(),
      timestamp,
      id,
    });
    cleanup();
  }

  /**
   * Checks if a message content was recently sent
   */
  function isRecentlySent(content: string): boolean {
    cleanup();
    return Array.from(messages.values()).some(
      (msg) => msg.content === content.trim()
    );
  }

  /**
   * Clears all tracked messages
   */
  function clear(): void {
    messages.clear();
  }

  /**
   * Removes old entries (older than retention time)
   */
  function cleanup(): void {
    const cutoffTime = Date.now() - RETENTION_TIME_MS;
    for (const [key, msg] of messages.entries()) {
      if (msg.timestamp.getTime() < cutoffTime) {
        messages.delete(key);
      }
    }
  }

  return {
    track,
    isRecentlySent,
    clear,
  };
}
