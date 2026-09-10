import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Evals from '../Evals';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const realGet = vi.fn();
vi.mock('@/api/client', () => ({
  api: { get: (...a: unknown[]) => realGet(...a) },
}));

function renderWith() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Evals />
    </QueryClientProvider>,
  );
}

describe('Evals page (M4-4 dashboard)', () => {
  beforeEach(() => {
    realGet.mockReset();
  });

  it('renders the header and empty-state when no report exists (404)', async () => {
    realGet.mockRejectedValue({ response: { status: 404 } });
    renderWith();
    expect(await screen.findByText('evals.title')).toBeTruthy();
    expect(await screen.findByText('evals.empty')).toBeTruthy();
    expect(screen.getByText('uv run python -m evals run all')).toBeTruthy();
  });

  it('renders the scorecard and per-suite rows from the report', async () => {
    realGet.mockResolvedValue({
      data: {
        ok: true,
        passed: 6,
        total: 6,
        duration_ms: 1234,
        suites: { intent: { passed: 3, total: 3 }, auditor: { passed: 3, total: 3 } },
        detail: [{ line: '- [PASS] intent' }],
      },
    });
    renderWith();
    expect(await screen.findByText('6/6')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('intent')).toBeTruthy());
    expect(screen.getByText('auditor')).toBeTruthy();
    expect(screen.getByText('1.2s')).toBeTruthy();
    expect(screen.getByText('- [PASS] intent')).toBeTruthy();
  });

  it('marks a failing suite as FAIL', async () => {
    realGet.mockResolvedValue({
      data: {
        ok: false,
        passed: 2,
        total: 3,
        duration_ms: 500,
        suites: { intent: { passed: 2, total: 3 } },
      },
    });
    renderWith();
    expect(await screen.findByText('FAIL')).toBeTruthy();
  });
});