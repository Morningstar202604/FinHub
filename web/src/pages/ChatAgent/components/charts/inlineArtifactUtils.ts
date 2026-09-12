// ─── Shared favicon helper ──────────────────────────────────────────

/** Build a direct-host favicon URL (https://<domain>/favicon.ico) for the
 * given domain. Returns '' if domain is empty or non-public. No third-party
 * favicon service is used, so it stays reachable from mainland China. */
export function faviconUrlForDomain(domain: string): string {
  if (!domain) return '';
  // Strip scheme + www, keep a bare hostname only (mirror <Favicon>).
  try {
    const host = new URL(domain.includes('://') ? domain : `https://${domain}`)
      .hostname.replace(/^www\./, '');
    if (!host.includes('.') || host.includes(':')) return '';
    return `https://${host}/favicon.ico`;
  } catch {
    return '';
  }
}

/** Favicon <img> with onError fallback to a monogram span. */
