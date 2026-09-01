/**
 * Research Loop types — the six-stage managed research pipeline
 * (idea → data → model → report → track → trigger).
 * Mirrors src/server/models/research_loop.py on the backend.
 */

export const RESEARCH_LOOP_STAGES = [
  'idea',
  'data',
  'model',
  'report',
  'track',
  'trigger',
] as const;

export type ResearchLoopStage = (typeof RESEARCH_LOOP_STAGES)[number];

export type ResearchLoopStatus = 'active' | 'paused' | 'completed' | 'archived';

export type ResearchLoopDirection = 'long' | 'short' | 'neutral';

export type ResearchLoopEvidenceLevel =
  | 'verified'
  | 'estimated'
  | 'user_provided'
  | 'unverified';

export interface ResearchLoopStageEntry {
  stage: ResearchLoopStage;
  status: string;
  at: string;
  note?: string;
}

export interface ResearchLoopEvidence {
  id: string;
  source: string;
  pulled_at?: string;
  caliber?: string;
  level: ResearchLoopEvidenceLevel;
  note?: string;
  metadata?: Record<string, unknown>;
  at?: string;
}

export interface ResearchLoopArtifact {
  id: string;
  path: string;
  type: string;
  title?: string;
  metadata?: Record<string, unknown>;
  at?: string;
}

export interface ResearchLoop {
  loop_id: string;
  workspace_id: string;
  user_id: string;
  goal: string;
  status: ResearchLoopStatus;
  current_stage: ResearchLoopStage;
  thesis: string;
  symbol?: string | null;
  direction?: ResearchLoopDirection | null;
  stage_history: ResearchLoopStageEntry[];
  evidence: ResearchLoopEvidence[];
  artifacts: ResearchLoopArtifact[];
  portfolio_link?: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ResearchLoopList {
  loops: ResearchLoop[];
  total: number;
}
