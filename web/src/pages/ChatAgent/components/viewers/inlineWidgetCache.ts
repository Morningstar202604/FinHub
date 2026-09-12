import { registerAuthReset } from '@/lib/authResets';

/**
 * Last reported height per widget content, so a revisited thread reserves the
 * real height immediately instead of the 150px guess — the first live report
 * then lands as a small correction rather than a layout jolt. Session-scoped.
 */
export const lastKnownHeights = new Map<string, number>();

/** The cache outlives unmounts by design; wiped on sign-out/account switch
 * (module singletons outlive React — web/AGENTS.md). Exported for tests. */
export function resetInlineWidgetHeightCache() {
  lastKnownHeights.clear();
}

registerAuthReset(resetInlineWidgetHeightCache);

export function widgetHeightKey(html: string, data?: Record<string, string>): string {
  let h = 5381;
  for (let i = 0; i < html.length; i++) h = ((h << 5) + h + html.charCodeAt(i)) | 0;
  let dataSig = '';
  if (data) {
    for (const k of Object.keys(data)) dataSig += `${k}:${data[k].length};`;
  }
  return `${h}|${html.length}|${dataSig}`;
}
