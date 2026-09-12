export interface InsightTopic {
  text: string;
  trend: 'up' | 'down' | 'neutral';
}

export interface Insight {
  market_insight_id: string;
  type: string;
  headline: string;
  summary: string;
  completed_at?: string;
  topics?: InsightTopic[];
  [key: string]: unknown;
}

// Module-level cache (survives navigation, clears on page refresh)
export let insightsCache: Insight[] | null = null;

export function setInsightsCache(value: Insight[] | null): void {
  insightsCache = value;
}

/**
 * Read the latest insight brief data from the module cache. Used by the
 * InsightBriefWidget's `useWidgetContextExport` snapshot serializer so the
 * agent gets the actual headline + summary + topics, not just the widget label.
 * Returns null if the brief hasn't loaded yet.
 */
export function getCachedInsights(): Insight[] | null {
  return insightsCache;
}
