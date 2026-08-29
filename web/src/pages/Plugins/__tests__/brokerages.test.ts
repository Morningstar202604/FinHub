/**
 * The join between a shipped brokerage and the row it may or may not have yet.
 *
 * The registry itself is the backend's, so what is worth pinning here is the
 * one thing the page derives from it: a host match that decides whether a row
 * carries a vendor's constraints, including whether someone is told to go
 * install a desktop app. Being wrong costs a user a download they did not need
 * or a dead end they were not warned about, so it is pinned both ways.
 */
import { describe, expect, it } from 'vitest';

import { brokerageForUrl, type Brokerage } from '../brokerages';

const robinhood: Brokerage = {
  name: 'robinhood',
  label: 'Robinhood',
  url: 'https://agent.robinhood.com/mcp/trading',
  description: 'Robinhood brokerage account.',
  native_callback_only: true,
  exclusive_connection: false,
};

const ibkr: Brokerage = {
  name: 'ibkr',
  label: 'Interactive Brokers',
  url: 'https://api.ibkr.com/v1/api/mcp-public',
  description: 'Interactive Brokers account.',
  native_callback_only: false,
  exclusive_connection: true,
};

const all = [robinhood, ibkr];

describe('brokerageForUrl', () => {
  it.each([
    ['https://agent.robinhood.com/mcp/trading', 'robinhood'],
    // A row is the user's to edit once it exists, and a different path on the
    // same vendor host is still that vendor.
    ['https://agent.robinhood.com/mcp/other', 'robinhood'],
    ['https://AGENT.RobinHood.com/mcp/trading', 'robinhood'],
    ['https://api.ibkr.com/v1/api/mcp-public', 'ibkr'],
  ])('%s → %s', (url, name) => {
    expect(brokerageForUrl(url, all)?.name).toBe(name);
  });

  it.each([
    // A neighbouring host is a different server; claiming a vendor's
    // constraints for it would be a guess.
    ['https://robinhood.com/mcp'],
    ['https://agent.robinhood.com.example.test/mcp'],
    ['https://mcp.example.com/sse'],
    ['not a url'],
    [null],
    [undefined],
  ])('%s matches nothing', (url) => {
    expect(brokerageForUrl(url as string | null, all)).toBeNull();
  });

  it('matches nothing at all when the registry has not loaded', () => {
    expect(brokerageForUrl(robinhood.url, [])).toBeNull();
  });
});

describe('the quirks read off a match', () => {
  // Both quirks come from the same match, so a row at a vendor's host carries
  // both of that vendor's constraints or neither. Splitting the two joins is
  // how one of them ends up applying to a row the other skips.
  it('carries whatever the matched vendor carries, and nothing otherwise', () => {
    expect(brokerageForUrl(robinhood.url, all)?.native_callback_only).toBe(true);
    expect(brokerageForUrl(robinhood.url, all)?.exclusive_connection).toBe(false);
    expect(brokerageForUrl(ibkr.url, all)?.native_callback_only).toBe(false);
    expect(brokerageForUrl(ibkr.url, all)?.exclusive_connection).toBe(true);
    expect(brokerageForUrl('https://mcp.example.com/sse', all)).toBeNull();
  });
});
