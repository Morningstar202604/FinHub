import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatDateTime, formatDuration } from '../utils/time';
import type { AutomationExecution } from '@/types/automation';

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-emerald-400',
  failed: 'bg-red-400',
  running: 'bg-yellow-400',
  pending: 'bg-gray-400',
};

interface ExecutionHistoryTableProps {
  executions: AutomationExecution[];
  loading: boolean;
  workspaceId?: string;
}

export default function ExecutionHistoryTable({ executions, loading, workspaceId }: ExecutionHistoryTableProps) {
  const navigate = useNavigate();

  if (loading && executions.length === 0) {
    return (
      <p className="text-xs py-4 text-center" style={{ color: 'var(--color-text-secondary)' }}>
        Loading executions...
      </p>
    );
  }

  if (executions.length === 0) {
    return (
      <p className="text-xs py-4 text-center" style={{ color: 'var(--color-text-secondary)' }}>
        No executions yet
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr
            className="text-left uppercase tracking-wider"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <th className="pb-2 pr-3 font-medium">Status</th>
            <th className="pb-2 pr-3 font-medium">Thread</th>
            <th className="pb-2 pr-3 font-medium">Scheduled</th>
            <th className="pb-2 pr-3 font-medium">Duration</th>
            <th className="pb-2 font-medium">Error</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((exec) => {
            const dotClass = STATUS_DOT[exec.status] || STATUS_DOT.pending;
            const threadId = exec.conversation_thread_id as string | undefined;
            return (
              <tr
                key={exec.automation_execution_id as string}
                className="border-t"
                style={{ borderColor: 'var(--color-border-default)' }}
              >
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-1.5">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotClass}`} />
                    <span style={{ color: 'var(--color-text-secondary)' }}>{exec.status}</span>
                  </div>
                </td>
                <td className="py-2 pr-3">
                  {threadId ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/chat/t/${threadId}`, {
                          state: workspaceId ? { workspaceId } : {},
                        });
                      }}
                      className="hover:underline truncate max-w-[120px] block"
                      style={{ color: 'var(--color-accent-primary)' }}
                    >
                      {threadId.slice(0, 8)}...
                    </button>
                  ) : (
                    <span style={{ color: 'var(--color-text-secondary)' }}>{'\u2014'}</span>
                  )}
                </td>
                <td className="py-2 pr-3" style={{ color: 'var(--color-text-secondary)' }}>
                  {formatDateTime(exec.scheduled_at as string | undefined)}
                </td>
                <td className="py-2 pr-3" style={{ color: 'var(--color-text-secondary)' }}>
                  {formatDuration(exec.started_at, exec.completed_at)}
                </td>
                <td className="py-2 max-w-[200px] truncate" style={{ color: 'var(--color-text-secondary)' }}>
                  {(exec.error_message as string) || '\u2014'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
