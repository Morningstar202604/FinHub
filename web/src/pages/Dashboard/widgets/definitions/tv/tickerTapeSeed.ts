// Macro defaults. Plain US-listed ETFs always resolve on TV's free embed
// tier in every region — the licensed index feeds (`SP:SPX`, `NASDAQ:NDX`)
// fail unauthenticated, and CFDs (`FOREXCOM:*`) are blocked for US retail.
// SPY → S&P 500, QQQ → Nasdaq-100, DIA → Dow, IWM → Russell 2000, GLD →
// gold. Labels in TICKER_LABELS below remap to the names users recognize.
export const DEFAULT_TICKERS = [
  'AMEX:SPY',
  'NASDAQ:QQQ',
  'AMEX:DIA',
  'AMEX:IWM',
  'AMEX:GLD',
];

/**
 * Display labels for well-known tape symbols. Keeps the chip in settings
 * as the canonical `EXCHANGE:SYMBOL` form (what TV actually resolves)
 * while the tape itself shows the short name users recognize.
 * Misses fall back to the last colon-segment.
 */
const TICKER_LABELS: Record<string, string> = {
  'AMEX:SPY': 'SPX',
  'NASDAQ:QQQ': 'NDX',
  'AMEX:DIA': 'DJI',
  'AMEX:IWM': 'RUT',
  'AMEX:GLD': 'GOLD',
  'FOREXCOM:SPXUSD': 'SPX',
  'FOREXCOM:NSXUSD': 'NDX',
  'FOREXCOM:DJI': 'DJI',
};

export function titleFor(sym: string): string {
  return TICKER_LABELS[sym] ?? sym.split(':').pop() ?? sym;
}

/** Bare-ticker form ("AMEX:SPY" → "SPY", "NVDA" → "NVDA") for dedup. */
function bareTicker(sym: string): string {
  return (sym.split(':').pop() ?? sym).toUpperCase();
}

/**
 * Macro defaults + watchlist + portfolio, deduped by bare-ticker form so
 * a watchlist "SPY" collapses with the default "AMEX:SPY". First-write
 * wins → defaults stay in their fixed order at the head of the tape, then
 * personal symbols follow in watchlist-then-portfolio order.
 *
 * Exported for unit-testing — the live-seed dedup is the ONE thing every
 * tape user depends on and it's only otherwise exercised through React.
 */
export function buildSeedSymbols(watchlistSyms: string[], portfolioSyms: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const push = (sym: string) => {
    if (!sym) return;
    const key = bareTicker(sym);
    if (seen.has(key)) return;
    seen.add(key);
    out.push(sym);
  };
  for (const s of DEFAULT_TICKERS) push(s);
  for (const s of watchlistSyms) push(s);
  for (const s of portfolioSyms) push(s);
  return out;
}
