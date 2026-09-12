import { InlineStockPriceCard, InlineCompanyOverviewCard, InlineMarketIndicesCard, InlineSectorPerformanceCard, InlineMarketOverviewCard, InlineSecFilingCard, InlineStockScreenerCard, InlineWebSearchCard, InlineChartAnnotationCard } from './InlineArtifactCards';
import { InlineQuoteCard } from './InlineQuoteCard';
import { InlineAutomationCard } from './InlineAutomationCards';
import { InlinePreviewCard } from './InlinePreviewCard';
import type React from 'react';



/**
 * Maps an artifact type to its inline card component. Single source of truth
 * for both the activity timeline (ActivityBlock) and the message list
 * (MessageList) — a new inline card is registered here (plus its tool-name gate
 * in INLINE_ARTIFACT_TOOLS) rather than in each surface separately.
 */
export const INLINE_ARTIFACT_MAP: Record<
  string,
  React.ComponentType<{ artifact: Record<string, unknown>; onClick?: () => void }>
> = {
  stock_prices: InlineStockPriceCard,
  company_overview: InlineCompanyOverviewCard,
  quote: InlineQuoteCard,
  market_indices: InlineMarketIndicesCard,
  sector_performance: InlineSectorPerformanceCard,
  market_overview: InlineMarketOverviewCard,
  sec_filing: InlineSecFilingCard,
  stock_screener: InlineStockScreenerCard,
  automations: InlineAutomationCard,
  preview_url: InlinePreviewCard,
  web_search: InlineWebSearchCard,
  chart_annotation: InlineChartAnnotationCard,
};
