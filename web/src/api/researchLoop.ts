/** Research Loop API client — managed research-loop state per workspace. */
import type { AxiosResponse } from 'axios';
import { api } from '@/api/client';

/** Get the workspace's research loop (404 if none). */
export const getWorkspaceResearchLoop = (workspaceId: string): Promise<AxiosResponse> =>
  api.get(`/api/v1/workspaces/${workspaceId}/research-loop`);

/** Start a research loop for a workspace (one per workspace). */
export const createWorkspaceResearchLoop = (
  workspaceId: string,
  data: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.post(`/api/v1/workspaces/${workspaceId}/research-loop`, data);

/** Update loop fields; a current_stage change appends to stage history. */
export const updateWorkspaceResearchLoop = (
  workspaceId: string,
  data: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.patch(`/api/v1/workspaces/${workspaceId}/research-loop`, data);

/** Delete the workspace's research loop. */
export const deleteWorkspaceResearchLoop = (workspaceId: string): Promise<AxiosResponse> =>
  api.delete(`/api/v1/workspaces/${workspaceId}/research-loop`);

/** Advance to the next stage in pipeline order. */
export const advanceWorkspaceResearchLoop = (
  workspaceId: string,
  data?: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.post(`/api/v1/workspaces/${workspaceId}/research-loop/advance`, data ?? {});

/** Append an evidence entry to the loop's evidence index. */
export const addWorkspaceResearchLoopEvidence = (
  workspaceId: string,
  data: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.post(`/api/v1/workspaces/${workspaceId}/research-loop/evidence`, data);

/** Append a deliverable to the loop's artifact index. */
export const addWorkspaceResearchLoopArtifact = (
  workspaceId: string,
  data: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.post(`/api/v1/workspaces/${workspaceId}/research-loop/artifacts`, data);

/** List the caller's research loops across workspaces (dashboard). */
export const listResearchLoops = (
  params?: Record<string, unknown>,
): Promise<AxiosResponse> =>
  api.get('/api/v1/research-loops', { params });
