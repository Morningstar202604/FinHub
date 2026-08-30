import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  features: [] as Array<{
    key: string;
    label: string;
    description: string;
    enabled: boolean;
    gate: string;
    tradeoffs?: string | null;
  }>,
  setFeatureOverride: vi.fn(
    async (_payload: { key: string; enabled: boolean | null }) => [],
  ),
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

vi.mock('@/hooks/useFeatures', () => ({
  useFeatures: () => ({ data: h.features, isLoading: false }),
  useSetFeatureOverride: () => ({ mutateAsync: h.setFeatureOverride }),
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
  useToast: () => ({ toast: vi.fn() }),
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
  getFlashWorkspace: vi.fn(async () => ({ workspace_id: 'ws-flash' })),
}));

// Onboarding — Settings renders replay/reset buttons; no provider in this harness.
vi.mock('@/pages/Onboarding', () => ({
  useOnboarding: () => ({ replayGuides: vi.fn(), resetOnboarding: vi.fn() }),
}));

// Import after mocks are registered.
import Settings from '../Settings';

function renderAgentTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/settings?tab=agent']}>
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
  h.setFeatureOverride.mockClear();
  h.setFeatureOverride.mockResolvedValue([]);
  // opt_out defaults: memory and web search are ON until the user opts out.
  h.features = [
    { key: 'memory', label: 'Memory', description: '', enabled: true, gate: 'opt_out' },
    { key: 'web_search', label: 'Web search', description: '', enabled: true, gate: 'opt_out' },
  ];
});

function setupAndRender(agentPreference: Record<string, unknown> = {}) {
  h.user = {
    id: 'u-1',
    email: 'tester@example.com',
    name: 'Tester',
    onboarding_completed: true,
  };
  h.preferences = { agent_preference: agentPreference };
  return renderAgentTab();
}

describe('Settings — Agent tab', () => {
  it('renders with defaults when no agent_preference is saved', async () => {
    setupAndRender({});

    const textarea = await screen.findByPlaceholderText(/name|直呼|名前/);
    expect(textarea).toHaveValue('');

    // Creativity defaults to the system-default state, not a number.
    expect(screen.getByText('System default')).toBeInTheDocument();

    // No response style is active.
    const concise = screen.getByRole('button', { name: 'Concise' });
    const detailed = screen.getByRole('button', { name: 'Detailed' });
    expect(concise).toHaveStyle({ color: 'var(--color-text-tertiary)' });
    expect(detailed).toHaveStyle({ color: 'var(--color-text-tertiary)' });

    // Deep thinking starts off.
    expect(screen.getByRole('switch', { name: 'Deep Thinking' })).toHaveAttribute('aria-checked', 'false');
  });

  it('loads saved values from agent_preference', async () => {
    setupAndRender({
      custom_instructions: 'Always use tables.',
      output_style: 'detailed',
      creativity: 0.8,
      deep_thinking: true,
    });

    const textarea = await screen.findByPlaceholderText(/name|直呼|名前/);
    expect(textarea).toHaveValue('Always use tables.');

    expect(screen.getByRole('button', { name: 'Detailed' })).toHaveStyle({
      color: 'var(--color-accent-primary)',
    });

    // 0.8 → "Creative · 80%"
    expect(screen.getByText('Creative')).toBeInTheDocument();
    expect(screen.getByText(/80%/)).toBeInTheDocument();

    expect(screen.getByRole('switch', { name: 'Deep Thinking' })).toHaveAttribute('aria-checked', 'true');
  });

  it('typing custom instructions saves them through updatePreferences', async () => {
    setupAndRender({});

    const textarea = await screen.findByPlaceholderText(/name|直呼|名前/);
    fireEvent.change(textarea, { target: { value: 'Always cite sources.' } });

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.custom_instructions).toBe('Always cite sources.');
  });

  it('clearing custom instructions writes null to delete the key', async () => {
    setupAndRender({ custom_instructions: 'Keep it short.' });

    const textarea = await screen.findByPlaceholderText(/name|直呼|名前/);
    expect(textarea).toHaveValue('Keep it short.');
    fireEvent.change(textarea, { target: { value: '   ' } });

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.custom_instructions).toBeNull();
  });

  it('selecting a response style saves output_style', async () => {
    setupAndRender({});

    const concise = await screen.findByRole('button', { name: 'Concise' });
    fireEvent.click(concise);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.output_style).toBe('concise');
  });

  it('clicking the active style again resets output_style to null', async () => {
    setupAndRender({ output_style: 'detailed' });

    const detailed = await screen.findByRole('button', { name: 'Detailed' });
    fireEvent.click(detailed);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.output_style).toBeNull();
  });

  it('moving the creativity slider saves a 0..1 value', async () => {
    setupAndRender({});

    const slider = await screen.findByRole('slider', { name: 'Creativity' });
    fireEvent.change(slider, { target: { value: '0.2' } });

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.creativity).toBe(0.2);
  });

  it('resetting creativity returns the stored value to null', async () => {
    setupAndRender({ creativity: 0.8 });

    const slider = await screen.findByRole('slider', { name: 'Creativity' });
    expect(slider).toHaveValue('0.8');
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.creativity).toBeNull();
  });

  it('toggling deep thinking saves deep_thinking: true', async () => {
    setupAndRender({});

    const toggle = await screen.findByRole('switch', { name: 'Deep Thinking' });
    fireEvent.click(toggle);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference.deep_thinking).toBe(true);
  });

  it('preserves unrelated agent_preference keys on save', async () => {
    setupAndRender({ output_format: 'html', custom: 'kept' });

    const toggle = await screen.findByRole('switch', { name: 'Deep Thinking' });
    fireEvent.click(toggle);

    await waitFor(() => expect(h.mutateAsync).toHaveBeenCalled());
    const payload = h.mutateAsync.mock.calls.at(-1)![0] as {
      agent_preference: Record<string, unknown>;
    };
    expect(payload.agent_preference).toMatchObject({ output_format: 'html', custom: 'kept' });
  });

  it('renders memory and web search toggles on by default (opt_out)', async () => {
    setupAndRender({});

    const memory = await screen.findByRole('switch', { name: 'Memory' });
    const webSearch = screen.findByRole('switch', { name: 'Web Search' });
    expect(memory).toHaveAttribute('aria-checked', 'true');
    expect(await webSearch).toHaveAttribute('aria-checked', 'true');
  });

  it('turning off memory writes an override through setFeatureOverride', async () => {
    setupAndRender({});

    const memory = await screen.findByRole('switch', { name: 'Memory' });
    fireEvent.click(memory);

    await waitFor(() => expect(h.setFeatureOverride).toHaveBeenCalled());
    expect(h.setFeatureOverride.mock.calls.at(-1)![0]).toEqual({ key: 'memory', enabled: false });
  });

  it('renders memory/web search as off when the user overrode them off', async () => {
    h.features = [
      { key: 'memory', label: 'Memory', description: '', enabled: false, gate: 'opt_out' },
      { key: 'web_search', label: 'Web Search', description: '', enabled: true, gate: 'opt_out' },
    ];
    setupAndRender({});

    const memory = await screen.findByRole('switch', { name: 'Memory' });
    const webSearch = screen.findByRole('switch', { name: 'Web Search' });
    expect(memory).toHaveAttribute('aria-checked', 'false');
    expect(await webSearch).toHaveAttribute('aria-checked', 'true');
  });
});
