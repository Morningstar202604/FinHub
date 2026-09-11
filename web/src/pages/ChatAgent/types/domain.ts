/**
 * Shared UI-domain types for the ChatAgent.
 *
 * Every type that is consumed by more than one component file lives here so
 * that components only *import* and never *declare* a shared shape. This
 * replaces the scattered local copies that previously sat in card components,
 * ToolCallDetailView, chatView/types, messageList/types, and filePanel/types.
 */

// ---------------------------------------------------------------------------
// Tool-call payloads
// ---------------------------------------------------------------------------

/** A tool-call invocation as it arrives from the backend. All fields optional
 *  so in-progress / partial / rehydrated records type-check. The index
 *  signature mirrors the UI render shape (looser than the strict wire type in
 *  `types/sse.ts`) so tool display helpers that expect `ToolCall` (which
 *  carries an index signature) accept it directly. */
export interface ToolCallData {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
  [key: string]: unknown;
}

/** A tool-call result with an optional artifact. The artifact's `type` field
 *  is the discriminator the UI uses to pick an inline card. `content_type`
 *  and `tool_call_id` are present on the strict wire shape but optional in
 *  the rehydrated / in-progress variant. */
export interface ToolCallResultData {
  content?: string | unknown;
  content_type?: string;
  tool_call_id?: string;
  artifact?: ArtifactRecord;
  [key: string]: unknown;
}

export interface ArtifactRecord {
  type?: string;
  [key: string]: unknown;
}

/** Render-time record: every field optional so a mid-stream partial still
 *  type-checks; carries the live state bits the UI needs. */
export interface ToolCallProcessRecord {
  toolName?: string;
  toolCall?: ToolCallData;
  toolCallResult?: ToolCallResultData;
  isInProgress?: boolean;
  isComplete?: boolean;
  isFailed?: boolean;
  _subagentStatus?: string | null;
  _createdAt?: number;
  _completedAt?: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Subagent identity
// ---------------------------------------------------------------------------

export interface SubagentInfo {
  subagentId: string;
  description?: string;
  prompt?: string;
  type?: string;
  status?: string;
  error?: string;
  ownerTaskId?: string;
}

// ---------------------------------------------------------------------------
// Activity-item (timeline row)
// ---------------------------------------------------------------------------

export type LiveState = 'active' | 'completing' | 'completed' | 'failed';

export interface ActivityItem {
  id?: string;
  toolCallId?: string;
  type: 'reasoning' | 'tool_call';
  toolName?: string;
  toolCall?: ToolCallData;
  toolCallResult?: ToolCallResultData;
  isComplete?: boolean;
  /** Set in MessageList from `proc.isFailed`. Persists across the live→completed
   *  transition so the accordion timeline can render a failure indicator. */
  isFailed?: boolean;
  _recentlyCompleted?: boolean;
  _liveState?: LiveState;
  /** Intermediate chart-annotation draw — render as an ordinary row, never a
   *  card (the latest draw per chart owns the card; set in MessageList). */
  _annotationStep?: boolean;
  content?: string;
  reasoningTitle?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// HITL interrupt payloads — one base + four subtypes (discriminated union)
// ---------------------------------------------------------------------------

export type ProposalStatus = 'pending' | 'approved' | 'rejected';

interface ProposalBase {
  status: ProposalStatus;
  [key: string]: unknown;
}

export interface PlanData {
  description: string;
  planApprovalId?: string;
  interruptId?: string;
  status: ProposalStatus;
  [key: string]: unknown;
}

export interface QuestionData {
  question: string;
  options?: string[];
  allow_multiple?: boolean;
  answer?: string;
  questionId?: string;
  interruptId?: string;
  status: ProposalStatus | 'answered' | 'skipped';
  [key: string]: unknown;
}

export interface CreateWorkspaceProposalData {
  workspace_name: string;
  workspace_description?: string;
  proposalId?: string;
  interruptId?: string;
  status: ProposalStatus;
  [key: string]: unknown;
}

export interface StartQuestionProposalData {
  question: string;
  proposalId?: string;
  interruptId?: string;
  status: ProposalStatus;
  [key: string]: unknown;
}

export interface PTCAgentProposalData {
  question: string;
  workspace_name?: string;
  thread_id?: string;
  workspace_id?: string;
  report_back?: boolean;
  proposalId?: string;
  interruptId?: string;
  status: ProposalStatus;
  [key: string]: unknown;
}

export interface SecretaryActionProposalData {
  actionType: 'delete_workspace' | 'stop_workspace' | 'delete_thread';
  workspace_id?: string;
  thread_id?: string;
  proposalId?: string;
  interruptId?: string;
  status: ProposalStatus;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Context attachment (file snippet / code selection pinned to a message)
// ---------------------------------------------------------------------------
//
// The canonical source for ContextAttachment lives in the chat-input UI
// component (components/ui/chat-input.tsx) because it is the owning UI
// contract. This module re-exports it so page-level code can import from a
// single domain module without reaching into the UI component tree.

import type { ContextAttachment } from '@/components/ui/chat-input';

// Re-exported under the domain module's namespace for page-level consumers.
export type { ContextAttachment };
