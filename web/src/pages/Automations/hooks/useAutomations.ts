import { useQuery } from '@tanstack/react-query';
import type { Automation } from '@/types/automation';
import { listAutomations } from '../utils/api';

const POLL_INTERVAL = 30000;

interface UseAutomationsOptions {
  status?: string;
}

interface UseAutomationsResult {
  automations: Automation[];
  total: number;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useAutomations({ status }: UseAutomationsOptions = {}): UseAutomationsResult {
  const { data = { automations: [] as Automation[], total: 0 }, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['automations', status],
    queryFn: async () => {
      const params: Record<string, unknown> = { limit: 100, offset: 0 };
      if (status) params.status = status;
      const { data } = await listAutomations(params);
      return { automations: data.automations as Automation[], total: data.total as number };
    },
    refetchInterval: POLL_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: 5000,
  });

  return { automations: data.automations, total: data.total, loading, error: error as Error | null, refetch };
}
