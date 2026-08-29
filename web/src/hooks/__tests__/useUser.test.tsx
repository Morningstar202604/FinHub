import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { renderHookWithProviders } from '../../test/utils';
import { useUser } from '../useUser';
import { waitFor } from '@testing-library/react';

vi.mock('../../pages/Dashboard/utils/api', () => ({
  getCurrentUser: vi.fn(),
}));

import { getCurrentUser } from '../../pages/Dashboard/utils/api';

const mockGetCurrentUser = getCurrentUser as Mock;

describe('useUser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the user from the API response (unwraps .user field)', async () => {
    const mockUser = { id: 'u-1', name: 'Alice', email: 'alice@test.com' };
    mockGetCurrentUser.mockResolvedValue({ user: mockUser });

    const { result } = renderHookWithProviders(() => useUser());

    await waitFor(() => expect(result.current.user).toEqual(mockUser));
    expect(result.current.isSuccess).toBe(true);
  });

  it('falls back to raw response when .user field is absent', async () => {
    const raw = { id: 'u-2', name: 'Bob' };
    mockGetCurrentUser.mockResolvedValue(raw);

    const { result } = renderHookWithProviders(() => useUser());

    await waitFor(() => expect(result.current.user).toEqual(raw));
  });

  it('returns null as user while loading', () => {
    mockGetCurrentUser.mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHookWithProviders(() => useUser());

    expect(result.current.user).toBeNull();
    expect(result.current.isLoading).toBe(true);
  });

  it('does not retry on failure (retry: false)', async () => {
    mockGetCurrentUser.mockRejectedValue(new Error('Unauthorized'));

    const { result } = renderHookWithProviders(() => useUser());

    await waitFor(() => expect(result.current.isError).toBe(true));
    // With retry: false, getCurrentUser should only be called once
    expect(mockGetCurrentUser).toHaveBeenCalledTimes(1);
    expect(result.current.user).toBeNull();
  });
});
