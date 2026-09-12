export const INDEX_SYMBOLS: Array<{ symbol: string; name: string }> = [
  { symbol: 'SPX', name: 'S&P 500' },
  { symbol: 'DJI', name: 'Dow Jones Industrial Average' },
  { symbol: 'COMP', name: 'Nasdaq Composite' },
  { symbol: 'NDX', name: 'Nasdaq 100' },
  { symbol: 'RUT', name: 'Russell 2000' },
  { symbol: 'VIX', name: 'CBOE Volatility Index' },
];

const INDEX_SYMBOL_SET = new Set(INDEX_SYMBOLS.map((i) => i.symbol));

export function isIndexSymbol(symbol: string): boolean {
  return INDEX_SYMBOL_SET.has(symbol.toUpperCase());
}
