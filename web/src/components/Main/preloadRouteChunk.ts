// Chunk thunks shared by the lazy components and preloadRouteChunk — import()
// is deduped by the module system, so a preload and the lazy mount share one
// network fetch.
const routeChunks = {
  dashboard: () => import('../../pages/Dashboard/DashboardRouter'),
  chat: () => import('../../pages/ChatAgent/ChatAgent'),
  market: () => import('../../pages/MarketView/MarketView'),
  news: () => import('../../pages/Detail/NewsDetailPage'),
  automations: () => import('../../pages/Automations/Automations'),
  plugins: () => import('../../pages/Plugins/Plugins'),
  settings: () => import('../../pages/Settings/Settings'),
  evals: () => import('../../pages/Evals/Evals'),
  // Alias so preloading /connectors (the legacy path) warms the right chunk.
  connectors: () => import('../../pages/Plugins/Plugins'),
};

/** Start downloading the chunk for `pathname` without rendering it, so the
 * shell can warm the target route while the /users/me gate is still
 * resolving instead of serializing the two network legs. Unknown segments
 * warm the dashboard chunk (the catch-all redirect's target). */
export function preloadRouteChunk(pathname: string): void {
  const chunkFor: Record<string, () => Promise<unknown>> = routeChunks;
  const segment = pathname.split('/')[1] || 'dashboard';
  // Swallowed on purpose, but it must be caught: a deploy deletes the previous
  // build's chunks, so this rejects routinely for a stale tab, and an unhandled
  // rejection is noise that hides real ones. The failure still surfaces — Vite
  // fires vite:preloadError (index.html reports it), and React.lazy retries the
  // same import at mount, where StaleBuildBoundary catches it.
  void (chunkFor[segment] ?? routeChunks.dashboard)().catch(() => {});
}

export { routeChunks };
