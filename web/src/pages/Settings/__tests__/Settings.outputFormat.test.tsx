import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Hoisted mutable state — vary preferences / mutation per test. Stable refs
// (rebuilt in beforeEach) keep Settings' prefs-sync effect from looping.
const h = vi.hoisted(() => ({
  platformMode: false,
  mutateAsync: vi.fn(async (_payload: unknown) => ({})),
  user: null as Record<string, unknown> | null,
  preferences: null as Record<string, unknown> | null,
  validModelNames: new Set<string>(),
  // The chat hand-off buttons await this POST before routing. Defaults to an
  // immediate resolve; the guard tests swap in a deferred so the in-flight
  // window is observable.
  getFlashWorkspace: vi.fn(async () => ({ workspace_id: 'ws-flash' })),
  toast: vi.fn(),
}));

vi.mock('@/config/hostMode', () => ({
  get isPlatformMode() {
    return h.platformMode;
  },
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

vi.mock('@/hooks/useUser', () => ({
  useUser: () => ({ user: h.user, isLoading: false }),
}));

vi.mock('@/hooks/usePreferences', () => ({
  usePreferences: () => ({ preferences: h.preferences, isLoading: false }),
}));

const mutationStub = { mutateAsync: h.mutateAsync };
vi.mock('@/hooks/useUpdatePreferences', () => ({
  useUpdatePreferences: () => mutationStub,
}));

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', preference: 'dark', setTheme: vi.fn() }),
}));

vi.mock('@/hooks/useAllModels', () => ({
  useAllModels: () => ({
    models: {},
    modelAccessMap: {},
    systemDefaults: { fallback_models: [] },
    validModelNames: h.validModelNames,
    compactionProfiles: null,
    searchProviders: null,
    isLoading: false,
  }),
}));

vi.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: h.toast }),
}));

vi.mock('@/hooks/useDebouncedSave', () => ({
  useDebouncedSave: (saveFn: () => Promise<void>) => ({
    trigger: () => { setTimeout(() => { void saveFn(); }, 0); },
    flush: () => { setTimeout(() => { void saveFn(); }, 0); },
    status: 'idle',
  }),
}));

vi.mock('@/components/model/ModelTierConfig', () => ({
  ModelTierConfig: () => <div data-testid="model-tier-config-stub" />,
}));

vi.mock('@/pages/Dashboard/utils/api', () => ({
  updateCurrentUser: vi.fn(async () => ({})),
  clearPreferences: vi.fn(async () => ({})),
  uploadAvatar: vi.fn(async () => ({ avatar_url: '' })),
  getUserApiKeys: vi.fn(async () => ({ providers: [] })),
  initiateCodexDevice: vi.fn(async () => ({})),
  pollCodexDevice: vi.fn(async () => ({})),
  getCodexOAuthStatus: vi.fn(async () => ({ connected: false })),
  disconnectCodexOAuth: vi.fn(async () => ({})),
  initiateClaudeOAuth: vi.fn(async () => ({})),
  submitClaudeCallback: vi.fn(async () => ({})),
  getClaudeOAuthStatus: vi.fn(async () => ({ connected: false })),
  disconnectClaudeOAuth: vi.fn(async () => ({})),
}));

vi.mock('@/pages/ChatAgent/utils/api', () => ({
  getFlashWorkspace: h.getFlashWorkspace,
}));

// Onboarding — Settings renders replay/reset buttons; no provider in this harness.
vi.mock('@/pages/Onboarding', () => ({
  useOnboarding: () => ({ replayGuides: vi.fn(), resetOnboarding: vi.fn() }),
}));

// Import after mocks are registered.
import Settings from '../Settings';

function renderPreferencesTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/settings?tab=preferences']}>
        <Settings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  h.platformMode = false;
  h.validModelNames = new Set<string>();
  h.mutateAsync.mockClear();
  h.mutateAsync.mockResolvedValue({});
  h.getFlashWorkspace.mockReset();
  h.getFlashWorkspace.mockResolvedValue({ workspace_id: 'ws-flash' });
  h.toast.mockClear();
});

/** Sentinel for "the profile was never completed" — the key is omitted entirely. */
const NO_ONBOARDING_KEY = Symbol('no-onboarding-key');

function setupAndRender(
  agentPreference: Record<string, unknown> = {},
  // The callout renders on `onboarding_completed !== true`, so a profile that
  // never finished onboarding has the key ABSENT. A `= undefined` default
  // cannot express that: JS applies the default to `undefined` too, so the
  // value silently became `true` and the callout never mounted. Hence the
  // sentinel rather than a plain optional flag.
  onboardingCompleted: boolean | typeof NO_ONBOARDING_KEY = true,
) {
  h.user = {
    id: 'u-1',
    email: 'tester@example.com',
    name: 'Tester',
    ...(onboardingCompleted === NO_ONBOARDING_KEY
      ? {}
      : { onboarding_completed: onboardingCompleted }),
  };
  h.preferences = { agent_preference: agentPreference };
  return renderPreferencesTab();
}

describe('Settings — Output format', () => {
  it('defaults to Default (Markdown) when output_format is absent', async () => {
    setupAndRender({});

    const defaultBtn = await screen.findByRole('button', { name: 'Default' });
    const htmlBtn = screen.getByRole('button', { name: 'HTML' });
    // The active segment uses the accent color; the inactive one uses tertiary.
    expect(defaultBtn).toHaveStyle({ color: 'var(--color-accent-primary)' });
    expect(htmlBtn).toHaveStyle({ color: 'var(--color-text-tertiary)' });
  });

  it('reflects the saved html value as the active segment', async () => {
    setupAndRender({ output_format: 'html' });

    const defaultBtn = await screen.findByRole('button', { name: 'Default' });
    const htmlBtn = screen.getByRole('button', { name: 'HTML' });
    expect(htmlBtn).toHaveStyle({ color: 'var(--color-accent-primary)' });
    expect(defaultBtn).toHaveStyle({ color: 'var(--color-text-tertiary)' });
  });

  it('selecting HTML saves output_format: "html" through updatePreferences', async () => {
    setupAndRender({});

    const htmlBtn = await screen.findByRole('button', { name: 'HTML' });
    fireEvent.click(htmlBtn);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference).toMatchObject({ output_format: 'html' });
  });

  it('selecting Default writes output_format: null to delete the key', async () => {
    setupAndRender({ output_format: 'html' });

    const defaultBtn = await screen.findByRole('button', { name: 'Default' });
    fireEvent.click(defaultBtn);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.output_format).toBeNull();
  });

  it('preserves other agent_preference keys when changing output format', async () => {
    setupAndRender({ tone: 'concise' });

    const htmlBtn = await screen.findByRole('button', { name: 'HTML' });
    fireEvent.click(htmlBtn);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference).toMatchObject({ tone: 'concise', output_format: 'html' });
  });

  it('does not duplicate output_format as a read-only row', async () => {
    setupAndRender({ output_format: 'html' });

    await screen.findByRole('button', { name: 'HTML' });
    // The generic key/value loop renders rows like "Output Format:"; the
    // dedicated control replaces it, so that raw row must not appear.
    expect(screen.queryByText('Output Format:')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Regression: the chat hand-off buttons must not fire a duplicate POST
//
// "Modify with Agent" and "Start Onboarding" both await getFlashWorkspace()
// — a network POST — before routing. Nothing on screen changes during that
// round-trip, so the click reads as inert and a second (or third) click used
// to fire another POST. The buttons share one in-flight flag because either
// is a valid exit from the panel.
// ---------------------------------------------------------------------------

/** A promise with its settle functions exposed, for asserting mid-flight state. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('Settings — chat hand-off guard', () => {
  function getModifyButton() {
    return screen.getByRole('button', { name: /Modify with Agent/ });
  }

  it('disables Modify with Agent while the workspace POST is in flight', async () => {
    const d = deferred<{ workspace_id: string }>();
    h.getFlashWorkspace.mockReturnValueOnce(d.promise);
    setupAndRender({});

    const modifyBtn = await screen.findByRole('button', { name: /Modify with Agent/ });
    expect(modifyBtn).toBeEnabled();

    fireEvent.click(modifyBtn);

    // In flight: still mounted (the POST has not settled) and visibly locked.
    await waitFor(() => expect(h.getFlashWorkspace).toHaveBeenCalledTimes(1));
    expect(getModifyButton()).toBeDisabled();
    expect(getModifyButton()).toHaveClass('disabled:opacity-60');

    // Settle so the component does not update after unmount.
    await act(async () => {
      d.resolve({ workspace_id: 'ws-flash' });
      await d.promise;
    });
  });

  it('three rapid clicks fire exactly one workspace POST', async () => {
    const d = deferred<{ workspace_id: string }>();
    h.getFlashWorkspace.mockReturnValueOnce(d.promise);
    setupAndRender({});

    const modifyBtn = await screen.findByRole('button', { name: /Modify with Agent/ });

    // Same tick, before React can commit the disabled state — the case a
    // `disabled` attribute alone cannot catch, because all three handlers run
    // against the stale render. The guard has to be a ref-fast early return.
    fireEvent.click(modifyBtn);
    fireEvent.click(modifyBtn);
    fireEvent.click(modifyBtn);

    await waitFor(() => expect(h.getFlashWorkspace).toHaveBeenCalledTimes(1));
    // Give any late duplicate a chance to land before asserting the total.
    await act(async () => {
      d.resolve({ workspace_id: 'ws-flash' });
      await d.promise;
    });
    expect(h.getFlashWorkspace).toHaveBeenCalledTimes(1);
  });

  it('Start Onboarding shares the lane: locked too, and no second POST', async () => {
    // User has not completed onboarding, so the callout carrying the second
    // exit button renders alongside "Modify with Agent".
    const d = deferred<{ workspace_id: string }>();
    h.getFlashWorkspace.mockReturnValueOnce(d.promise);
    setupAndRender({}, NO_ONBOARDING_KEY);

    const startBtn = await screen.findByRole('button', { name: /Start Onboarding/ });
    fireEvent.click(startBtn);

    await waitFor(() => expect(h.getFlashWorkspace).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: /Start Onboarding/ })).toBeDisabled();
    // The sibling is locked by the same flag — one exit is already underway,
    // and firing the other would open a second flash workspace nobody lands in.
    expect(getModifyButton()).toBeDisabled();

    await act(async () => {
      d.resolve({ workspace_id: 'ws-flash' });
      await d.promise;
    });
    expect(h.getFlashWorkspace).toHaveBeenCalledTimes(1);
  });

  it('a failed POST re-enables the button and surfaces the toast', async () => {
    const d = deferred<{ workspace_id: string }>();
    h.getFlashWorkspace.mockReturnValueOnce(d.promise);
    setupAndRender({});

    const modifyBtn = await screen.findByRole('button', { name: /Modify with Agent/ });
    fireEvent.click(modifyBtn);
    await waitFor(() => expect(getModifyButton()).toBeDisabled());

    await act(async () => {
      d.reject(new Error('network down'));
      await d.promise.catch(() => {});
    });

    // The failure path must unlock, or the panel is permanently dead.
    await waitFor(() => expect(getModifyButton()).toBeEnabled());
    expect(h.toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'destructive' }),
    );
  });
});
