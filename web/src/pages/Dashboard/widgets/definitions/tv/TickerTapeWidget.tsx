import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity } from 'lucide-react';
import { TradingViewEmbed } from '../../framework/TradingViewEmbed';
import { registerWidget } from '../../framework/WidgetRegistry';
import { TickerTapeConfigSchema } from '../../framework/configSchemas';
import { useDashboardContext } from '../../framework/useDashboardContext';
import { SymbolListField } from '../../framework/settings/SymbolListField';
import { EnumField } from '../../framework/settings/EnumField';
import { TradingViewSettingsFooter } from '../../framework/TradingViewSettingsFooter';
import { SettingsDoneButton } from '../../framework/settings/SettingsDoneButton';
import type { WidgetRenderProps, WidgetSettingsProps } from '../../types';
import { buildSeedSymbols, titleFor } from './tickerTapeSeed';

interface TickerTapeConfig {
  symbols: string[];
  displayMode: 'adaptive' | 'regular' | 'compact';
}

// Natural iframe heights for each displayMode (measured from TV's default
// `embed-widget-ticker-tape.js` renders). Paired with `fitToContent` so the
// RGL cell adapts to chrome between edit/view modes without clipping the
// marquee or leaving a band of padding.
const TICKER_CONTENT_HEIGHT: Record<TickerTapeConfig['displayMode'], number> = {
  adaptive: 76,
  regular: 76,
  compact: 46,
};

// Intentional iframe fallback: the WC `<tv-ticker-tape>` is a *static
// bordered grid* (verified at /widget-docs/widgets/tickers/ticker-tape/
// — even the `horizontal_no_chart` preset). The iframe `embed-widget-
// ticker-tape.js` is the classic continuous scrolling marquee, which is
// the UX users expect. Tracked in tvConfig.ts under "iframe-only widgets".
export function TickerTapeWidget({ instance }: WidgetRenderProps<TickerTapeConfig>) {
  const { symbols, displayMode } = instance.config;
  const { watchlist, portfolio } = useDashboardContext();
  // Reactive seed: when the user hasn't customized the chip list, the
  // tape stays in sync with their watchlist and portfolio. The moment
  // they edit chips in settings, the stored list takes over and the
  // tape stops reacting to watchlist/portfolio adds.
  const list = useMemo(() => {
    if (symbols?.length) return symbols;
    const w = watchlist.rows.map((r) => r.symbol).filter(Boolean);
    const p = portfolio.rows.map((r) => r.symbol).filter(Boolean);
    return buildSeedSymbols(w, p);
  }, [symbols, watchlist.rows, portfolio.rows]);
  return (
    <TradingViewEmbed
      card
      scriptKey="ticker-tape"
      contentHeight={TICKER_CONTENT_HEIGHT[displayMode] ?? TICKER_CONTENT_HEIGHT.adaptive}
      config={{
        symbols: list.map((s) => ({ proName: s, title: titleFor(s) })),
        showSymbolLogo: true,
        displayMode,
      }}
    />
  );
}

function TickerTapeSettings({ config, onChange, onClose }: WidgetSettingsProps<TickerTapeConfig>) {
  const { t } = useTranslation();
  const { watchlist, portfolio } = useDashboardContext();
  // Mirror the render-time live seed so the chip list shows what the tape
  // is actually rendering. Opening settings stays side-effect-free — the
  // displayed list only commits when the user adds or removes a chip
  // (their first edit captures the full effective list as the start state).
  const displayedSymbols = useMemo(() => {
    if (config.symbols?.length) return config.symbols;
    const w = watchlist.rows.map((r) => r.symbol).filter(Boolean);
    const p = portfolio.rows.map((r) => r.symbol).filter(Boolean);
    return buildSeedSymbols(w, p);
  }, [config.symbols, watchlist.rows, portfolio.rows]);
  return (
    <div className="space-y-4">
      <SymbolListField
        label={t('dashboard.widgets.tickerTape.symbols')}
        value={displayedSymbols}
        onChange={(next) => onChange({ symbols: next })}
        placeholder={t('dashboard.widgets.tickerTape.symbolsPlaceholder')}
        helper={t('dashboard.widgets.tickerTape.symbolsHelper')}
      />
      <EnumField
        label={t('dashboard.widgets.tickerTape.displayMode')}
        value={config.displayMode ?? 'adaptive'}
        onChange={(v) => onChange({ displayMode: v as TickerTapeConfig['displayMode'] })}
        options={[
          { value: 'adaptive', label: t('dashboard.widgets.tickerTape.displayMode_adaptive') },
          { value: 'regular', label: t('dashboard.widgets.tickerTape.displayMode_regular') },
          { value: 'compact', label: t('dashboard.widgets.tickerTape.displayMode_compact') },
        ]}
      />
      <TradingViewSettingsFooter />
      <SettingsDoneButton onClick={onClose} />
    </div>
  );
}

registerWidget<TickerTapeConfig>({
  type: 'tv.ticker-tape',
  titleKey: 'dashboard.widgets.tickerTape.title',
  descriptionKey: 'dashboard.widgets.tickerTape.description',
  category: 'markets',
  icon: Activity,
  component: TickerTapeWidget,
  settingsComponent: TickerTapeSettings,
  defaultConfig: { symbols: [], displayMode: 'adaptive' },
  configSchema: TickerTapeConfigSchema,
  // fitToContent: cell height tracks the embed's natural 76px iframe plus
  // chrome. View mode → ~6 rows (128px, card hugs the ticker). Edit mode →
  // ~9 rows (200px, includes 40px header + 24px body padding). maxSize.h
  // must clear the edit-mode measurement (~9 rows) otherwise the clamp
  // caps the fit and the iframe gets clipped. Width stays user-resizable.
  fitToContent: true,
  defaultSize: { w: 12, h: 6 },
  minSize: { w: 6, h: 3 },
  maxSize: { w: 12, h: 12 },
  source: 'tradingview',
  // Empty `symbols` triggers the render-time live seed (defaults +
  // watchlist + portfolio, deduped). The tape stays reactive to watchlist
  // and portfolio adds until the user explicitly customizes via settings.
  initConfig: () => ({ symbols: [], displayMode: 'adaptive' }),
});
