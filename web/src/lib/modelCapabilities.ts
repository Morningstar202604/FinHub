// Xhigh effort was introduced in Opus 4.7. Opus 4.6 and earlier don't support it.
// Pattern covers opus-4-7/8/9, opus-4-10+, and any opus-5+ without manual updates.
const XHIGH_PATTERN = /opus-(?:4-(?:[7-9]|\d{2,})|[5-9])/i;

export function supportsXhighEffort(model: string | null | undefined): boolean {
  return !!model && XHIGH_PATTERN.test(model);
}
