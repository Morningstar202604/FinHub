import type { AgentPlanItem } from '@/components/ui/stepper-track';

export interface TodoItem {
  status: 'pending' | 'in_progress' | 'completed' | 'stale';
  activeForm?: string;
  content?: string;
  [key: string]: unknown;
}

/**
 * Get items to display in collapsed view.
 * - If any in_progress: return ALL in_progress items
 * - Otherwise fallback to single most relevant: last stale > last completed > first pending > first item
 */
export function getPreviewItems(todos: TodoItem[]): { item: TodoItem; index: number }[] {
  if (!todos || todos.length === 0) return [];

  const inProgress = todos
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.status === 'in_progress');
  if (inProgress.length > 0) return inProgress;

  for (let i = todos.length - 1; i >= 0; i--) {
    if (todos[i].status === 'stale') return [{ item: todos[i], index: i }];
  }

  for (let i = todos.length - 1; i >= 0; i--) {
    if (todos[i].status === 'completed') return [{ item: todos[i], index: i }];
  }

  const pendingIdx = todos.findIndex(t => t.status === 'pending');
  if (pendingIdx !== -1) return [{ item: todos[pendingIdx], index: pendingIdx }];

  return [{ item: todos[0], index: 0 }];
}

/** Map TodoItem[] to AgentPlanItem[] for the UI component. */
export function toAgentPlanItems(todos: TodoItem[]): AgentPlanItem[] {
  return todos.map((todo, i) => ({
    id: todo.activeForm || todo.content || `task-${i}`,
    label: todo.activeForm || todo.content || `Task ${i + 1}`,
    status: todo.status,
  }));
}

export interface TodoData {
  todos: TodoItem[];
  total: number;
  completed: number;
  in_progress: number;
  pending: number;
}
