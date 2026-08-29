import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { updatePreferences } from '../pages/Dashboard/utils/api';
import type { UserPreferences } from '../types/api';

/**
 * Mutation hook for updating user preferences.
 * Uses setQueryData on success for instant propagation to all usePreferences() consumers.
 */
export function useUpdatePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatePreferences as (prefs: Partial<UserPreferences>) => Promise<UserPreferences>,
    onSuccess: (updatedPrefs: UserPreferences) => {
      queryClient.setQueryData(queryKeys.user.preferences(), updatedPrefs);
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.user.preferences() });
    },
  });
}
