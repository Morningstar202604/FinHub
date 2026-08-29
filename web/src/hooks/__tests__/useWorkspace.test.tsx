import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { renderHookWithProviders, createTestQueryClient } from '../../test/utils';
import { useWorkspace } from '../useWorkspace';
import { waitFor } from '@testing-library/react';

// Mock the API function
vi.mock('../../pages/ChatAgent/utils/api', () => ({
  getWorkspace: vi.fn(),
}));

import { getWorkspace } from '../../pages/ChatAgent/utils/api';

const mockGetWorkspace = getWorkspace as Mock;

describe('useWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches workspace details when workspaceId is provided', async () => {
    const mockWs = { workspace_id: 'ws-1', name: 'Test WS' };
    mockGetWorkspace.mockResolvedValue(mockWs);

    const { result } = renderHookWithProviders(() => useWorkspace('ws-1'));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockWs);
    expect(mockGetWorkspace).toHaveBeenCalledWith('ws-1');
  });

  it('does not fetch when workspaceId is falsy', () => {
    const { result } = renderHookWithProviders(() => useWorkspace(null));

    expect(result.current.isFetching).toBe(false);
    expect(mockGetWorkspace).not.toHaveBeenCalled();
  });

  it('does not fetch when workspaceId is undefined', () => {
    const { result } = renderHookWithProviders(() => useWorkspace(undefined));

    expect(result.current.isFetching).toBe(false);
    expect(mockGetWorkspace).not.toHaveBeenCalled();
  });

  it('derives initialData from cached workspace lists', async () => {
    const cachedWs = { workspace_id: 'ws-cached', name: 'Cached WS' };
    const queryClient = createTestQueryClient();
    // Pre-populate the cache with a workspace list
    queryClient.setQueryData(['workspaces', 'list', {}], {
      workspaces: [cachedWs, { workspace_id: 'ws-other', name: 'Other' }],
    });

    mockGetWorkspace.mockResolvedValue({ ...cachedWs, name: 'Updated WS' });

    const { result } = renderHookWithProviders(() => useWorkspace('ws-cached'), { queryClient });

    // initialData should be present immediately from the cached list
    expect(result.current.data).toEqual(cachedWs);
    expect(result.current.data!.name).toBe('Cached WS');
  });

  it('returns undefined initialData when workspace is not in cache', async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(['workspaces', 'list', {}], {
      workspaces: [{ workspace_id: 'ws-other', name: 'Other' }],
    });

    mockGetWorkspace.mockResolvedValue({ workspace_id: 'ws-missing', name: 'Fetched' });

    const { result } = renderHookWithProviders(() => useWorkspace('ws-missing'), { queryClient });

    // No initialData, so starts loading
    expect(result.current.data).toBeUndefined();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.name).toBe('Fetched');
  });
});
