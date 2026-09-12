import { createContext, useContext } from 'react';
import type { DashboardDataContextValue } from './DashboardDataContext';

export const DashboardDataCtx = createContext<DashboardDataContextValue | null>(null);

export function useDashboardContext(): DashboardDataContextValue {
  const v = useContext(DashboardDataCtx);
  if (!v) throw new Error('useDashboardContext must be used within DashboardDataProvider');
  return v;
}
