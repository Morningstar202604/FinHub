/**
 * Watchlists CRUD API.
 * GET /api/v1/users/me/watchlists, POST, PUT /:id, DELETE /:id
 */
import { api } from '@/api/client';

export interface CreateWatchlistPayload {
  name: string;
  description?: string;
  is_default?: boolean;
  display_order?: number;
}

export interface UpdateWatchlistPayload {
  name?: string;
  description?: string;
  display_order?: number;
}

export async function listWatchlists(): Promise<unknown> {
  const { data } = await api.get('/api/v1/users/me/watchlists');
  return data;
}

export async function createWatchlist(payload: CreateWatchlistPayload): Promise<unknown> {
  const { data } = await api.post('/api/v1/users/me/watchlists', payload);
  return data;
}

export async function updateWatchlist(id: string, payload: UpdateWatchlistPayload): Promise<unknown> {
  const { data } = await api.put(
    `/api/v1/users/me/watchlists/${encodeURIComponent(id)}`,
    payload
  );
  return data;
}

export async function deleteWatchlist(id: string): Promise<void> {
  await api.delete(`/api/v1/users/me/watchlists/${encodeURIComponent(id)}`);
}
