import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReasonPanel from '../ReasonPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'percent' in opts ? `label ${opts.percent}%` : key,
  }),
}));

vi.mock('@/lib/queryKeys', () => ({
  queryKeys: {
    threads: {
      all: ['threads'],
      detail: (id: string) => ['threads', 'detail', id],
    },
  },
}));

const realGet = vi.fn();
vi.mock('@/api/client', () => ({
  api: { get: (...a: unknown[]) => realGet(...a) },
}));
vi.mock('../../utils/api', () => ({
  getThread: (id: string) => realGet(id),
}));

function renderWith(intent: unknown | undefined, threadId: string | null = 't-1') {
  realGet.mockResolvedValue({ metadata: intent ? { intent } : {} });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ReasonPanel threadId={threadId} />
    </QueryClientProvider>,
  );
}

describe('ReasonPanel (M4-1 intent route reason)', () => {
  beforeEach(() => {
    realGet.mockReset();
  });

  it('renders the ptc badge and reason when intent says ptc', async () => {
    renderWith({ mode: 'ptc', reason: 'strong ptc signal keyword', confidence: 0.9 });
    expect(await screen.findByText('intent.badge.ptc')).toBeTruthy();
    expect(screen.getByText('strong ptc signal keyword')).toBeTruthy();
    expect(screen.getByText('label 90%')).toBeTruthy();
  });

  it('renders the flash badge when intent says flash', async () => {
    renderWith({ mode: 'flash', reason: 'default quick path', confidence: 0.55 });
    expect(await screen.findByText('intent.badge.flash')).toBeTruthy();
    expect(screen.getByText('default quick path')).toBeTruthy();
  });

  it('renders nothing when the thread has no intent metadata', async () => {
    renderWith(undefined);
    // Let the query resolve, then assert the panel did not appear.
    await new Promise((r) => setTimeout(r, 30));
    expect(document.body.textContent ?? '').not.toContain('intent.badge.');
  });

  it('renders nothing when threadId is null', () => {
    renderWith({ mode: 'ptc', reason: 'r', confidence: 0.9 }, null);
    expect(document.body.textContent ?? '').not.toContain('intent.badge.');
  });
});