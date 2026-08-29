import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getAvailableModels } from '../api/model';

/**
 * Shared hook for available model data.
 * All consumers share a single cached entry keyed by queryKeys.models.all.
 */
export function useModels() {
  const { data, ...rest } = useQuery({
    queryKey: queryKeys.models.all,
    queryFn: getAvailableModels,
    staleTime: 5 * 60_000,
    retry: false,
  });
  return { models: data ?? null, ...rest };
}
