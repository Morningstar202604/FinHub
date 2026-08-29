import type { AxiosResponse } from 'axios';
import { api } from '@/api/client';

export const listAutomations = (params: Record<string, unknown>): Promise<AxiosResponse> =>
  api.get('/api/v1/automations', { params });

export const getAutomation = (id: string): Promise<AxiosResponse> =>
  api.get(`/api/v1/automations/${id}`);

export const createAutomation = (data: Record<string, unknown>): Promise<AxiosResponse> =>
  api.post('/api/v1/automations', data);

export const updateAutomation = (id: string, data: Record<string, unknown>): Promise<AxiosResponse> =>
  api.patch(`/api/v1/automations/${id}`, data);

export const deleteAutomation = (id: string): Promise<AxiosResponse> =>
  api.delete(`/api/v1/automations/${id}`);

export const pauseAutomation = (id: string): Promise<AxiosResponse> =>
  api.post(`/api/v1/automations/${id}/pause`);

export const resumeAutomation = (id: string): Promise<AxiosResponse> =>
  api.post(`/api/v1/automations/${id}/resume`);

export const triggerAutomation = (id: string): Promise<AxiosResponse> =>
  api.post(`/api/v1/automations/${id}/trigger`);

export const listExecutions = (id: string, params: Record<string, unknown>): Promise<AxiosResponse> =>
  api.get(`/api/v1/automations/${id}/executions`, { params });

export const listWorkspaces = (params: Record<string, unknown>): Promise<AxiosResponse> =>
  api.get('/api/v1/workspaces', { params });
