/** Hostname suffixes that are never publicly routable. */
const NON_PUBLIC_SUFFIXES = ['.local', '.internal', '.lan', '.corp', '.home', '.test', '.localhost'];

/**
 * True only for clearly-public registrable domains. Anything that could be a
 * private/internal host (localhost, single-label names, IP literals, RFC1918 /
 * link-local ranges, internal TLDs) returns false so we never leak it to the
 * third-party favicon service. Accepts either a full URL or a bare hostname.
 */
export function isPublicHost(input: string): boolean {
  if (!input) return false;

  let host = input.trim().toLowerCase();
  try {
    host = new URL(input).hostname.toLowerCase();
  } catch {
    host = host.replace(/^\/\//, '').split('/')[0].split('?')[0].split('#')[0];
    if (!host.includes('[') && (host.match(/:/g) || []).length === 1) {
      host = host.split(':')[0];
    }
  }
  host = host.replace(/^\[|\]$/g, '').replace(/\.$/, '');

  if (!host) return false;
  if (host === 'localhost') return false;
  if (host.includes(':')) return false;
  if (!host.includes('.')) return false;
  if (NON_PUBLIC_SUFFIXES.some((suffix) => host.endsWith(suffix))) return false;

  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    const octets = host.split('.').map(Number);
    if (octets.some((o) => o > 255)) return false;
    const [a, b] = octets;
    if (a === 10) return false;
    if (a === 172 && b >= 16 && b <= 31) return false;
    if (a === 192 && b === 168) return false;
    if (a === 169 && b === 254) return false;
    if (a === 127) return false;
    return false;
  }

  return true;
}

/**
 * Direct-host favicon URL for a public registrable domain: the site's own
 * ``/favicon.ico`` (scheme https, www-prefix stripped). Returns '' when the
 * domain is empty or non-public.
 */
export function faviconUrlForHost(domain: string): string {
  if (!domain || !isPublicHost(domain)) return '';
  const host = domain.trim().toLowerCase().replace(/^www\./, '');
  return `https://${host}/favicon.ico`;
}
