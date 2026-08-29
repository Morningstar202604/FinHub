import { useQuery } from '@tanstack/react-query';
import type { AutomationExecution } from '@/types/automation';
import { listExecutions } from '../utils/api';

const POLL_INTERVAL = 15000;

interface UseExecutionsResult {
  executions: AutomationExecution[];
  total: number;
  loading: boolean;
}

export function useExecutions(automationId: string | undefined): UseExecutionsResult {
  const { data = { executions: [] as AutomationExecution[], total: 0 }, isLoading: loading } = useQuery({
    queryKey: ['executions', automationId],
    queryFn: async () => {
      const { data } = await listExecutions(automationId!, { limit: 20, offset: 0 });
      return { executions: data.executions as AutomationExecution[], total: data.total as number };
    },
    enabled: !!automationId,
    refetchInterval: POLL_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: 5000,
  });

  return { executions: data.executions, total: data.total, loading };
}
