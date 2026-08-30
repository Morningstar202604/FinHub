import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, RotateCcw } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { ToggleSwitch } from '@/components/ui/switch';
import { usePreferences } from '@/hooks/usePreferences';
import { useUpdatePreferences } from '@/hooks/useUpdatePreferences';
import { useDebouncedSave } from '@/hooks/useDebouncedSave';
import { useFeatures, useSetFeatureOverride } from '@/hooks/useFeatures';
import { useToast } from '@/components/ui/use-toast';
import { useTranslation } from 'react-i18next';
import type { Preferences } from './types';

const RESPONSE_STYLES = ['concise', 'balanced', 'detailed'] as const;
type ResponseStyle = (typeof RESPONSE_STYLES)[number];

/** Agent-behavior keys now surfaced in the dedicated Agent tab. PreferencesTab
 *  hides these from its raw summary so the two tabs don't double-report the
 *  same setting. Keep in sync with the backend AgentPreference model. */
export const AGENT_BEHAVIOR_KEYS = [
  'output_format',
  'output_style',
  'custom_instructions',
  'creativity',
  'deep_thinking',
] as const;

/** Feature-flag keys owned by the Agent tab (Doubao/GPT convention). These are
 *  opt_out toggles rendered here; Experiments tab filters them out. */
export const AGENT_MANAGED_FEATURE_KEYS = ['memory', 'web_search'] as const;
type AgentFeatureKey = (typeof AGENT_MANAGED_FEATURE_KEYS)[number];

function creativityTier(v: number): 'precise' | 'balanced' | 'creative' {
  if (v < 0.35) return 'precise';
  if (v > 0.65) return 'creative';
  return 'balanced';
}

/** Agent tab: behavior controls in the spirit of Doubao/GPT settings —
 *  custom instructions, response style, creativity, and deep thinking.
 *  Everything persists into `agent_preference` with debounced autosave. */
export function AgentTab() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { preferences: prefsData } = usePreferences();
  const updatePrefsMutation = useUpdatePreferences();
  const { data: featuresData } = useFeatures();
  const setFeatureOverrideMutation = useSetFeatureOverride();

  // Effective on/off for the agent-behavior feature toggles (memory, web_search).
  const featureEnabled = (key: AgentFeatureKey): boolean =>
    (featuresData ?? []).find((f) => f.key === key)?.enabled ?? false;

  const handleFeatureToggle = async (key: AgentFeatureKey, nextEnabled: boolean) => {
    try {
      await setFeatureOverrideMutation.mutateAsync({ key, enabled: nextEnabled });
    } catch {
      toast({
        variant: 'destructive',
        title: t('common.error'),
        description: t('settings.failedToSaveSettings'),
      });
    }
  };

  const agentPref = (prefsData as Preferences | null)?.agent_preference as
    | Record<string, unknown>
    | undefined;

  const [customInstructions, setCustomInstructions] = useState('');
  const [responseStyle, setResponseStyle] = useState<'' | ResponseStyle>('');
  // null = unset → JSONB merge deletes the key → model keeps its own default
  const [creativity, setCreativity] = useState<number | null>(null);
  const [deepThinking, setDeepThinking] = useState(false);

  // Sync local state when server preferences land / change.
  useEffect(() => {
    const raw = agentPref ?? {};
    setCustomInstructions(typeof raw.custom_instructions === 'string' ? raw.custom_instructions : '');
    const rawStyle = raw.output_style;
    setResponseStyle(RESPONSE_STYLES.includes(rawStyle as ResponseStyle) ? (rawStyle as ResponseStyle) : '');
    const rawCreativity = raw.creativity;
    setCreativity(
      typeof rawCreativity === 'number' && rawCreativity >= 0 && rawCreativity <= 1
        ? rawCreativity
        : null,
    );
    setDeepThinking(raw.deep_thinking === true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefsData]);

  const stateRef = useRef({ customInstructions, responseStyle, creativity, deepThinking });
  stateRef.current = { customInstructions, responseStyle, creativity, deepThinking };
  const dirtyRef = useRef(false);

  const saveAgentPrefs = useCallback(async () => {
    dirtyRef.current = false;
    const s = stateRef.current;
    const current = (prefsData as Preferences | null)?.agent_preference as
      | Record<string, unknown>
      | undefined;
    try {
      await updatePrefsMutation.mutateAsync({
        agent_preference: {
          ...(current ?? {}),
          custom_instructions: s.customInstructions.trim() ? s.customInstructions.trim() : null,
          output_style: s.responseStyle || null,
          creativity: s.creativity,
          deep_thinking: s.deepThinking,
        },
      });
    } catch {
      toast({
        variant: 'destructive',
        title: t('common.error'),
        description: t('settings.failedToSaveSettings'),
      });
    }
  }, [prefsData, updatePrefsMutation, toast, t]);

  const { trigger: triggerSaveRaw, flush: flushSave, status } = useDebouncedSave(saveAgentPrefs, 600);
  const triggerSave = useCallback(() => {
    dirtyRef.current = true;
    triggerSaveRaw();
  }, [triggerSaveRaw]);

  // Flush a pending edit on unmount (tab switch) so it isn't lost.
  useEffect(() => () => { if (dirtyRef.current) flushSave(); }, [flushSave]);

  const creativityPercent = creativity == null ? 50 : Math.round(creativity * 100);
  const creativityTierLabel = creativity == null
    ? t('settings.agent.creativityDefault')
    : t(`settings.agent.creativityTiers.${creativityTier(creativity)}`);

  return (
    <div className="space-y-5 max-w-2xl">
      <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
        {t('settings.agent.intro')}
      </p>

      {/* Custom instructions */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
          {t('settings.agent.customInstructions')}
        </label>
        <p className="text-xs mt-1 mb-2 leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
          {t('settings.agent.customInstructionsDesc')}
        </p>
        <Textarea
          value={customInstructions}
          onChange={(e) => { setCustomInstructions(e.target.value); triggerSave(); }}
          placeholder={t('settings.agent.customInstructionsPlaceholder')}
          rows={4}
        />
      </section>

      {/* Response style */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
          {t('settings.agent.responseStyle')}
        </label>
        <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
          {t('settings.agent.responseStyleDesc')}
        </p>
        <div
          className="mt-3 inline-flex rounded-lg overflow-hidden clips-focus-ring"
          style={{ border: '1px solid var(--color-border-muted)' }}
        >
          {RESPONSE_STYLES.map((style) => {
            const active = responseStyle === style;
            return (
              <button
                key={style}
                type="button"
                onClick={() => { setResponseStyle(active ? '' : style); triggerSave(); }}
                aria-pressed={active}
                className="px-3 py-1.5 text-[0.8125rem] font-medium transition-colors"
                style={{
                  backgroundColor: active ? 'var(--color-accent-soft)' : 'transparent',
                  color: active ? 'var(--color-accent-primary)' : 'var(--color-text-tertiary)',
                }}
              >
                {t(`settings.agent.responseStyleOptions.${style}.label`)}
              </button>
            );
          })}
        </div>
        <p className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>
          {responseStyle
            ? t(`settings.agent.responseStyleOptions.${responseStyle}.description`)
            : t('settings.agent.responseStyleDefault')}
        </p>
      </section>

      {/* Creativity */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {t('settings.agent.creativity')}
            </label>
            <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('settings.agent.creativityDesc')}
            </p>
          </div>
          <span
            className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-md"
            style={{ backgroundColor: 'var(--color-bg-elevated)', color: 'var(--color-accent-primary)' }}
          >
            {creativityTierLabel}
            {creativity != null && <span style={{ opacity: 0.6 }}>{' · '}{creativityPercent}%</span>}
          </span>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={creativity == null ? 0.5 : creativity}
            onChange={(e) => { setCreativity(Number(e.target.value)); triggerSave(); }}
            aria-label={t('settings.agent.creativity')}
            className="min-w-0"
            style={{ accentColor: 'var(--color-accent-primary)', flex: 1 }}
          />
          {creativity != null && (
            <button
              type="button"
              onClick={() => { setCreativity(null); triggerSave(); }}
              className="shrink-0 inline-flex items-center gap-1 text-xs font-medium transition-opacity hover:opacity-80"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              <RotateCcw className="h-3 w-3" />
              {t('settings.agent.creativityReset')}
            </button>
          )}
        </div>
      </section>

      {/* Deep thinking */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {t('settings.agent.deepThinking')}
            </label>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {t('settings.agent.deepThinkingDesc')}
            </p>
          </div>
          <ToggleSwitch
            checked={deepThinking}
            onChange={() => { setDeepThinking((v) => !v); triggerSave(); }}
            className="mt-0.5"
            ariaLabel={t('settings.agent.deepThinking')}
          />
        </div>
      </section>

      {/* Memory (agent-behavior feature toggle) */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {t('settings.agent.memory')}
            </label>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {t('settings.agent.memoryDesc')}
            </p>
          </div>
          <ToggleSwitch
            checked={featureEnabled('memory')}
            onChange={() => handleFeatureToggle('memory', !featureEnabled('memory'))}
            className="mt-0.5"
            ariaLabel={t('settings.agent.memory')}
          />
        </div>
      </section>

      {/* Web search (agent-behavior feature toggle) */}
      <section
        className="p-4 rounded-lg"
        style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <label className="block text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {t('settings.agent.webSearch')}
            </label>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {t('settings.agent.webSearchDesc')}
            </p>
          </div>
          <ToggleSwitch
            checked={featureEnabled('web_search')}
            onChange={() => handleFeatureToggle('web_search', !featureEnabled('web_search'))}
            className="mt-0.5"
            ariaLabel={t('settings.agent.webSearch')}
          />
        </div>
      </section>

      {/* Save status */}
      {status !== 'idle' && (
        <p
          className="text-xs"
          style={{ color: status === 'error' ? 'var(--color-loss)' : 'var(--color-text-tertiary)' }}
        >
          {status === 'saving' && t('settings.agent.saving')}
          {status === 'saved' && (
            <span className="inline-flex items-center gap-1">
              <Check className="h-3 w-3" /> {t('settings.agent.saved')}
            </span>
          )}
          {status === 'error' && t('settings.failedToSaveSettings')}
        </p>
      )}
    </div>
  );
}
