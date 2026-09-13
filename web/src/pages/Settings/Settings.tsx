import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useScrollMemory } from '@/lib/scrollMemory';
import { useUser } from '@/hooks/useUser';
import { usePreferences } from '@/hooks/usePreferences';
import { useTranslation } from 'react-i18next';
import { UserRound, SlidersHorizontal, Cpu, FlaskConical, Bot, Settings as SettingsIcon } from 'lucide-react';
import { UserInfoTab } from './panels/UserInfoTab';
import { PreferencesTab } from './panels/PreferencesTab';
import { ModelTab } from './panels/ModelTab';
import { ExperimentsTab } from './panels/ExperimentsTab';
import { AgentTab } from './panels/AgentTab';
import './Settings.css';

/** Settings tabs — icon + label so the bar reads as a small command surface
 *  (Doubao/GPT convention) instead of a bare underline strip. `labelKey`
 *  overrides the default `settings.<key>` lookup where the key path is taken
 *  by a nested object (e.g. settings.agent.*). */
interface SettingsTabDef {
  key: string;
  icon: typeof SettingsIcon;
  labelKey?: string;
}

const SETTINGS_TABS: readonly SettingsTabDef[] = [
  { key: 'userInfo', icon: UserRound },
  { key: 'preferences', icon: SlidersHorizontal },
  { key: 'agent', icon: Bot, labelKey: 'agentTab' },
  { key: 'model', icon: Cpu },
  { key: 'experiments', icon: FlaskConical },
];

function Settings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { isLoading: isUserLoading } = useUser();
  const { isLoading: isPrefsLoading } = usePreferences();
  const { t } = useTranslation();

  const tabParam = searchParams.get('tab') || 'userInfo';
  const [activeTab, setActiveTab] = useState(tabParam);
  const pageRef = useRef<HTMLDivElement>(null);
  useScrollMemory(pageRef, 'page:settings');
  const isLoading = isUserLoading || isPrefsLoading;

  // Sync tab with URL search params
  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    setSearchParams({ tab }, { replace: true });
  };

  // Sync from URL on mount / back-forward navigation
  useEffect(() => {
    const urlTab = searchParams.get('tab');
    if (urlTab && urlTab !== activeTab) {
      setActiveTab(urlTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div className="settings-page">
      {/* Doubles as the window titlebar in the desktop shell; inert
          elsewhere. Above the scroll port rather than inside it, so it stays
          put once the page is scrolled. */}
      <div className="chrome-drag-strip" aria-hidden="true" />
      <div ref={pageRef} className="settings-scroll">
        <div className="settings-container">
          {/* Page header — icon tile + title + subtitle (Doubao-style) */}
          <div className="settings-header">
            <span className="settings-header-icon" aria-hidden="true">
              <SettingsIcon className="h-5 w-5" strokeWidth={2.2} />
            </span>
            <div className="flex flex-col gap-1 min-w-0">
              <h2 className="text-xl font-semibold title-font" style={{ color: 'var(--color-text-primary)' }}>
                {t('settings.title')}
              </h2>
              <p className="text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
                {t('settings.subtitle')}
              </p>
            </div>
          </div>

          {/* Pill-style tab bar — active tab wears the brand amber */}
          <div className="settings-tabs" role="tablist" aria-label={t('settings.title')}>
            {SETTINGS_TABS.map(({ key, icon: TabIcon, labelKey }) => {
              const active = activeTab === key;
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => handleTabChange(key)}
                  className="settings-tab"
                  data-active={active || undefined}
                >
                  <TabIcon className="settings-tab-icon" />
                  <span>{t(`settings.${labelKey ?? key}`)}</span>
                </button>
              );
            })}
          </div>

          <div className="settings-content">
            {isLoading && (
              <div className="flex items-center justify-center py-8">
                <p className="text-sm" style={{ color: 'var(--color-text-primary)', opacity: 0.7 }}>{t('common.loading')}</p>
              </div>
            )}

            {!isLoading && activeTab === 'userInfo' && <UserInfoTab />}

            {!isLoading && activeTab === 'preferences' && <PreferencesTab />}

            {!isLoading && activeTab === 'agent' && <AgentTab />}

            {!isLoading && activeTab === 'model' && <ModelTab />}

            {/* Text-heavy tab: cap the measure so descriptions stay readable
                instead of spanning the full settings container. */}
            {!isLoading && activeTab === 'experiments' && <ExperimentsTab />}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Settings;
