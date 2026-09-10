import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MemoryRecallView from '../MemoryRecallView';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'query' in opts ? `empty for ${opts.query}` : key,
  }),
}));

vi.mock('@/components/ui/loader', () => ({
  Loader: () => <span>spinner</span>,
}));

// Mock only the axios client — the real recallMemory() runs against it, so
// the URL/params contract is exercised end-to-end.
const realGet = vi.fn();
vi.mock('@/api/client', () => ({
  api: {
    defaults: { baseURL: '' },
    get: (...a: unknown[]) => realGet(...a),
  },
}));

function renderWith(
  hits: unknown[],
  tier: 'user' | 'workspace' = 'user',
  ws: string | null = null,
) {
  realGet.mockResolvedValue({ data: { tier, query: 'growth', hits } });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRecallView tier={tier} workspaceId={ws} />
    </QueryClientProvider>,
  );
}

function search(value: string) {
  fireEvent.change(screen.getByLabelText('memoryPanel.recallPlaceholder'), {
    target: { value },
  });
  fireEvent.click(screen.getByText('memoryPanel.recallSearch'));
}

describe('MemoryRecallView (M4-3 memory recall)', () => {
  beforeEach(() => {
    realGet.mockReset();
  });

  it('renders the hint state before any search is submitted', () => {
    renderWith([]);
    expect(screen.getByText('memoryPanel.recallHint')).toBeTruthy();
  });

  it('renders recall hits with source chip and score after search', async () => {
    renderWith([
      { text: 'market expansion notes', source: 'memory.md', score: 0.42, chars: 40 },
    ]);
    search('growth');
    expect(await screen.findByText('market expansion notes')).toBeTruthy();
    expect(screen.getByText('memory.md')).toBeTruthy();
    expect(realGet).toHaveBeenCalledWith('/api/v1/memory/recall', {
      params: { q: 'growth', top_k: 10 },
    });
  });

  it('passes the workspace id for the workspace tier', async () => {
    renderWith([], 'workspace', 'ws-1');
    search('growth');
    await Promise.resolve();
    expect(realGet).toHaveBeenCalledWith('/api/v1/memory/recall', {
      params: { q: 'growth', top_k: 10, workspace_id: 'ws-1' },
    });
  });

  it('renders an empty-state message when no hits match', async () => {
    renderWith([]);
    search('zzz');
    expect(await screen.findByText('empty for zzz')).toBeTruthy();
  });
});