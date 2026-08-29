/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, type ReactNode } from 'react';

interface WorkspaceContextValue {
  workspaceId: string | null;
  downloadFile: ((path: string) => void) | null;
}

const WorkspaceContext = createContext<WorkspaceContextValue>({ workspaceId: null, downloadFile: null });

interface WorkspaceProviderProps {
  workspaceId: string | null;
  downloadFile: ((path: string) => void) | null;
  children: ReactNode;
}

export const WorkspaceProvider = ({ workspaceId, downloadFile, children }: WorkspaceProviderProps) => {
  const value = useMemo(() => ({ workspaceId, downloadFile }), [workspaceId, downloadFile]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
};

export const useWorkspaceId = () => useContext(WorkspaceContext).workspaceId;
export const useWorkspaceDownloadFile = () => useContext(WorkspaceContext).downloadFile;
