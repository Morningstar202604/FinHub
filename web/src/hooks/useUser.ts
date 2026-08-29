import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getCurrentUser } from '../pages/Dashboard/utils/api';
import type { User } from '../types/api';

/**
 * Shared hook for current user profile data.
 * Replaces manual useEffect+useState fetching of /api/v1/users/me.
 * All consumers share a single cached entry — updates propagate automatically.
 */
export function useUser() {
  const { data, ...rest } = useQuery({
    queryKey: queryKeys.user.me(),
    queryFn: async (): Promise<User> => {
      const res = await getCurrentUser() as Record<string, unknown> & { user?: User };
      return (res.user ?? res) as User;
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
  return { user: data ?? null, ...rest };
}
