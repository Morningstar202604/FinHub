import type { WidgetContextSnapshot } from '@/pages/Dashboard/widgets/framework/contextSnapshot';

export interface FileAttachment {
  id: string;
  file: File;
  type: string;
  preview: string | null;
  uploadStatus: 'pending' | 'uploading' | 'complete';
  dataUrl: string | null;
}

// --- Shared context attachment types ---

/**
 * A file snippet or code selection pinned to the chat composer.
 *
 * `path` is optional so a pure-code snippet can be attached without a file.
 * `lineStart`/`lineEnd` are nullable to distinguish "not specified" from
 * "line 0". `source` is an optional provenance tag ("selection", "mention",
 * "chat", "paste", …).
 *
 * `MentionedFile` is a non-null-path variant used by the @mention
 * autocomplete (where a concrete file path is always known).
 */
export interface ContextAttachment {
  path?: string;
  snippet?: string;
  label?: string;
  lineStart?: number | null;
  lineEnd?: number | null;
  lineCount?: number;
  source?: string;
}

/** An @mention reference — `path` is always present (the user typed @path). */
export interface MentionedFile {
  path: string;
  snippet?: string;
  label?: string;
  lineStart?: number | null;
  lineEnd?: number | null;
  lineCount?: number;
  source?: string;
}

export interface SlashCommand {
  type: string;
  name: string;
  skillName?: string;
  description?: string;
  aliases?: string[];
}

export interface ModelOptions {
  model: string | null;
  reasoningEffort: string | null;
  fastMode: boolean;
  /** Per-message market-watch toggle — stamps live prices for tracked tickers. */
  marketWatch?: boolean;
  /**
   * Widget context snapshots attached via the deck rail. Forwarded to the
   * backend as `additional_context` items of `type: "widget"`. Image-bearing
   * snapshots also produce a sibling `type: "image"` MultimodalContext item;
   * see `widgetSnapshotsToContexts` in `pages/ChatAgent/utils/fileUpload.ts`.
   */
  widgetSnapshots?: WidgetContextSnapshot[];
}

export interface ReadyAttachment {
  file: File;
  dataUrl: string | null;
  type: string;
  preview: string | null;
}

export interface Workspace {
  workspace_id: string;
  name: string;
  [key: string]: unknown;
}
