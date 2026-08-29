import { useState, useCallback } from 'react';
import { toast } from '@/components/ui/use-toast';
import * as automationApi from '../utils/api';

interface AxiosLikeError {
  response?: { data?: { detail?: string } };
  message?: string;
}

interface UseAutomationMutationsResult {
  create: (data: Record<string, unknown>) => Promise<unknown>;
  update: (id: string, data: Record<string, unknown>) => Promise<unknown>;
  remove: (id: string) => Promise<unknown>;
  pause: (id: string) => Promise<unknown>;
  resume: (id: string) => Promise<unknown>;
  trigger: (id: string) => Promise<unknown>;
  loading: boolean;
}

export function useAutomationMutations(refetch: () => void): UseAutomationMutationsResult {
  const [loading, setLoading] = useState(false);

  const run = useCallback(async <T>(fn: () => Promise<T>, successMsg: string): Promise<T> => {
    setLoading(true);
    try {
      const result = await fn();
      toast({ title: 'Success', description: successMsg });
      await refetch();
      return result;
    } catch (err: unknown) {
      const e = err as AxiosLikeError;
      const msg = e.response?.data?.detail || e.message || 'Something went wrong';
      toast({ variant: 'destructive', title: 'Error', description: typeof msg === 'string' ? msg : JSON.stringify(msg) });
      throw err;
    } finally {
      setLoading(false);
    }
  }, [refetch]);

  const create = useCallback(
    (data: Record<string, unknown>) => run(() => automationApi.createAutomation(data), 'Automation created'),
    [run]
  );

  const update = useCallback(
    (id: string, data: Record<string, unknown>) => run(() => automationApi.updateAutomation(id, data), 'Automation updated'),
    [run]
  );

  const remove = useCallback(
    (id: string) => run(() => automationApi.deleteAutomation(id), 'Automation deleted'),
    [run]
  );

  const pause = useCallback(
    (id: string) => run(() => automationApi.pauseAutomation(id), 'Automation paused'),
    [run]
  );

  const resume = useCallback(
    (id: string) => run(() => automationApi.resumeAutomation(id), 'Automation resumed'),
    [run]
  );

  const trigger = useCallback(
    (id: string) => run(() => automationApi.triggerAutomation(id), 'Automation triggered'),
    [run]
  );

  return { create, update, remove, pause, resume, trigger, loading };
}
