/**
 * The join between a catalog row and the brokerage it belongs to, and what
 * each vendor's quirks mean for the surfaces that draw them.
 *
 * The registry itself is the API layer's (`Brokerage`, `getBrokerages`) and the
 * hooks over it are `useMcpServers`', beside every other MCP query -- a
 * brokerage row is an ordinary catalog row and shares their invalidation
 * radius. What is left here is the part that is neither: which row is which
 * vendor, and whether this build can start a connect against one at all.
 */
import { canBeginMcpOAuth, isDesktopShell } from '@/lib/desktop';
import type { Brokerage } from '@/pages/ChatAgent/utils/api';

// Re-exported because this module is where the concept lives for every surface
// that draws one; the wire shape is declared with the call that fetches it.
export type { Brokerage };

/**
 * The brokerage a server address belongs to, matched on host.
 *
 * Host and not the full URL: a row is the user's to edit once it exists, and
 * moving to a sibling path on the same vendor host keeps every reason the
 * vendor quirks applied. A different host is a different server, and claiming
 * a vendor's constraints for it would be a guess.
 */
export function brokerageForUrl(
  url: string | null | undefined,
  brokerages: readonly Brokerage[],
): Brokerage | null {
  if (!url) return null;
  const host = hostOf(url);
  if (!host) return null;
  return brokerages.find((b) => hostOf(b.url) === host) ?? null;
}

function hostOf(url: string): string | null {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
}

/** Why a connect cannot start here, or null when the click is live. */
export type ConnectBlock = 'shell-outdated' | 'native-only' | 'unknown' | null;

/**
 * Whether this build can begin a connect against a vendor at all.
 *
 * One answer for every surface that asks. The two rows and the tab intro each
 * used to spell this out themselves, and the copy and the button drifted apart:
 * both said "desktop only" while only one refused the click, so the other led
 * straight into the dead end `connectReturn` exists to apologise for. A vendor
 * with no quirk, and every vendor at all once the shell is holding the
 * listener, answers null and behaves exactly as before.
 */
export function connectBlock(vendor: Brokerage | null | undefined): ConnectBlock {
  // Asked before the vendor, because it does not depend on one. In a shell with
  // no loopback listener NOTHING can connect: the consent screen opens in the
  // system browser and its reply comes home to a cookie jar that never saw the
  // flow. That is every row on the page, brokerage or not, so this is the first
  // and broadest answer rather than a special case inside the vendor's.
  if (isDesktopShell() && !canBeginMcpOAuth()) return 'shell-outdated';
  // `undefined` is the registry not answered yet, and it is not the same as
  // `null`, which is a row that resolved to no vendor. Reading the two alike is
  // how a backend too old to serve the registry -- or simply the moment before
  // the query settles -- turns every row into one with no constraints, and a
  // native-only vendor gets a live button into the dead end.
  if (vendor === undefined) return 'unknown';
  return vendor?.native_callback_only && !canBeginMcpOAuth() ? 'native-only' : null;
}
