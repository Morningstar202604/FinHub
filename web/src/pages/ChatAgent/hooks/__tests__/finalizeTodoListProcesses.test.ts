import { describe, it, expect } from 'vitest';
import type { ChatMessage, AssistantMessage } from '@/types/chat';
import { finalizeTodoListProcessesInMessages } from '../useChatMessages';

/** Helper to build a minimal assistant message with todoListProcesses. */
function makeAssistantMessage(
  id: string,
  todoListProcesses: AssistantMessage['todoListProcesses'] = {},
): AssistantMessage {
  return {
    id,
    role: 'assistant',
    content: '',
    contentType: 'text',
    timestamp: new Date(),
    isStreaming: false,
    contentSegments: [],
    reasoningProcesses: {},
    toolCallProcesses: {},
    todoListProcesses,
  };
}

function makeUserMessage(id: string): ChatMessage {
  return {
    id,
    role: 'user',
    content: 'hello',
    contentType: 'text',
    timestamp: new Date(),
    isStreaming: false,
  };
}

describe('finalizeTodoListProcessesInMessages', () => {
  it('returns the same array reference when there are no changes', () => {
    const messages: ChatMessage[] = [makeUserMessage('u1')];
    const result = finalizeTodoListProcessesInMessages(messages);
    expect(result).toBe(messages);
  });

  it('returns the same array when all todos are already completed', () => {
    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', {
        'todo-1': {
          todos: [
            { content: 'Task 1', status: 'completed' },
            { content: 'Task 2', status: 'completed' },
          ],
          total: 2,
          completed: 2,
          in_progress: 0,
          pending: 0,
          order: 1,
          baseTodoListId: 'base-1',
        },
      }),
    ];
    const result = finalizeTodoListProcessesInMessages(messages);
    expect(result).toBe(messages);
  });

  it('marks pending and in_progress todos as stale', () => {
    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', {
        'todo-1': {
          todos: [
            { content: 'Task 1', status: 'completed' },
            { content: 'Task 2', status: 'in_progress' },
            { content: 'Task 3', status: 'pending' },
          ],
          total: 3,
          completed: 1,
          in_progress: 1,
          pending: 1,
          order: 1,
          baseTodoListId: 'base-1',
        },
      }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages);
    const am = result[0] as AssistantMessage;
    const process = am.todoListProcesses!['todo-1'];

    expect(process.todos[0].status).toBe('completed');
    expect(process.todos[1].status).toBe('stale');
    expect(process.todos[2].status).toBe('stale');
    expect(process.in_progress).toBe(0);
    expect(process.pending).toBe(0);
  });

  it('preserves already-stale todos without re-creating them', () => {
    const staleTodo = { content: 'Task 2', status: 'stale' as const };
    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', {
        'todo-1': {
          todos: [
            { content: 'Task 1', status: 'completed' },
            staleTodo,
            { content: 'Task 3', status: 'pending' },
          ],
          total: 3,
          completed: 1,
          in_progress: 0,
          pending: 1,
          order: 1,
          baseTodoListId: 'base-1',
        },
      }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages);
    const am = result[0] as AssistantMessage;
    const process = am.todoListProcesses!['todo-1'];

    // Stale todo should be the exact same object (not cloned)
    expect(process.todos[1]).toBe(staleTodo);
    expect(process.todos[2].status).toBe('stale');
  });

  it('only finalizes the highest-order entry when multiple entries exist', () => {
    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', {
        'todo-early': {
          todos: [{ content: 'Early task', status: 'pending' }],
          total: 1,
          completed: 0,
          in_progress: 0,
          pending: 1,
          order: 1,
          baseTodoListId: 'base-1',
        },
        'todo-late': {
          todos: [{ content: 'Late task', status: 'in_progress' }],
          total: 1,
          completed: 0,
          in_progress: 1,
          pending: 0,
          order: 2,
          baseTodoListId: 'base-1',
        },
      }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages);
    const am = result[0] as AssistantMessage;

    // Early entry left untouched
    expect(am.todoListProcesses!['todo-early'].todos[0].status).toBe('pending');
    // Late entry (highest order) finalized
    expect(am.todoListProcesses!['todo-late'].todos[0].status).toBe('stale');
  });

  it('scopes to targetMessageId when provided', () => {
    const makeTodoProcess = () => ({
      todos: [{ content: 'Task', status: 'in_progress' as const }],
      total: 1,
      completed: 0,
      in_progress: 1,
      pending: 0,
      order: 1,
      baseTodoListId: 'base',
    });

    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', { 'todo-1': makeTodoProcess() }),
      makeAssistantMessage('a2', { 'todo-2': makeTodoProcess() }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages, 'a2');

    // a1 should be untouched
    const am1 = result[0] as AssistantMessage;
    expect(am1.todoListProcesses!['todo-1'].todos[0].status).toBe('in_progress');

    // a2 should be finalized
    const am2 = result[1] as AssistantMessage;
    expect(am2.todoListProcesses!['todo-2'].todos[0].status).toBe('stale');
  });

  it('skips user messages', () => {
    const messages: ChatMessage[] = [
      makeUserMessage('u1'),
      makeAssistantMessage('a1', {
        'todo-1': {
          todos: [{ content: 'Task', status: 'pending' }],
          total: 1,
          completed: 0,
          in_progress: 0,
          pending: 1,
          order: 1,
          baseTodoListId: 'base',
        },
      }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages);

    expect(result[0]).toBe(messages[0]); // user message identity preserved
    const am = result[1] as AssistantMessage;
    expect(am.todoListProcesses!['todo-1'].todos[0].status).toBe('stale');
  });

  it('finalizes all assistant messages when no targetMessageId', () => {
    const makeTodoProcess = () => ({
      todos: [{ content: 'Task', status: 'pending' as const }],
      total: 1,
      completed: 0,
      in_progress: 0,
      pending: 1,
      order: 1,
      baseTodoListId: 'base',
    });

    const messages: ChatMessage[] = [
      makeAssistantMessage('a1', { 'todo-1': makeTodoProcess() }),
      makeAssistantMessage('a2', { 'todo-2': makeTodoProcess() }),
    ];

    const result = finalizeTodoListProcessesInMessages(messages);

    const am1 = result[0] as AssistantMessage;
    const am2 = result[1] as AssistantMessage;
    expect(am1.todoListProcesses!['todo-1'].todos[0].status).toBe('stale');
    expect(am2.todoListProcesses!['todo-2'].todos[0].status).toBe('stale');
  });
});
