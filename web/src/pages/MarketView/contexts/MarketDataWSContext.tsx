import React, { createContext, useContext } from 'react';
import useMarketDataWS from '../hooks/useMarketDataWS';
import type { UseMarketDataWSReturn } from '../hooks/useMarketDataWS';

const MarketDataWSContext = createContext<UseMarketDataWSReturn | null>(null);

export function MarketDataWSProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const ws = useMarketDataWS();
  return (
    <MarketDataWSContext.Provider value={ws}>
      {children}
    </MarketDataWSContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useMarketDataWSContext(): UseMarketDataWSReturn {
  const ctx = useContext(MarketDataWSContext);
  if (!ctx) {
    throw new Error('useMarketDataWSContext must be used within <MarketDataWSProvider>');
  }
  return ctx;
}
