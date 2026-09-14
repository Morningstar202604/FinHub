import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Finance from '../Finance';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

/**
 * The API module is mocked (not `api/client`), so these tests exercise the
 * page's own logic — the has_data branches, the liquidity flag, the tab
 * switch — without asserting on axios shapes that the api module already owns.
 */
const getPersonalBalanceSheet = vi.fn();
const getPersonalCashFlow = vi.fn();
const getTrialBalance = vi.fn();

vi.mock('@/api/finance', () => ({
  getPersonalBalanceSheet: () => getPersonalBalanceSheet(),
  getPersonalCashFlow: () => getPersonalCashFlow(),
  getTrialBalance: () => getTrialBalance(),
}));

function renderWith() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Finance />
    </QueryClientProvider>,
  );
}

const EMPTY_SHEET = { has_data: false };
const EMPTY_FLOW = { has_data: false };

const SHEET = {
  has_data: true,
  as_of: '2026-09-14',
  currency: 'CNY',
  total_assets: 3585000,
  liquid_assets: 85000,
  total_liabilities: 1800000,
  net_worth: 1785000,
  debt_to_asset_ratio: 0.5021,
  assets: [
    { key: 'property', label: '自住房', amount: 3500000, liquid: false },
    { key: 'cash', label: '活期', amount: 85000, liquid: true },
  ],
  liabilities: [
    { key: 'mortgage', label: '房贷', amount: 1800000, monthly_payment: 9800 },
  ],
};

const FLOW = {
  has_data: true,
  start: '2026-08-15',
  end: '2026-09-13',
  days: 30,
  currency: 'CNY',
  income: 35000,
  total_outflow: 25000,
  net: 10000,
  savings_rate: 0.4286,
  is_deficit: false,
  monthly_essential: 17000,
  emergency_fund_months: 13.8,
};

describe('Finance page', () => {
  beforeEach(() => {
    getPersonalBalanceSheet.mockReset();
    getPersonalCashFlow.mockReset();
    getTrialBalance.mockReset();
  });

  it('defaults to the personal tab', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();
    expect(await screen.findByText('finance.title')).toBeTruthy();
    // The personal tab is selected on mount, so its data is what renders.
    expect(await screen.findByText('finance.personal.netWorth')).toBeTruthy();
    expect(getTrialBalance).not.toHaveBeenCalled();
  });

  it('shows an explicit empty state when nothing is recorded, never a zero', async () => {
    getPersonalBalanceSheet.mockResolvedValue(EMPTY_SHEET);
    getPersonalCashFlow.mockResolvedValue(EMPTY_FLOW);
    renderWith();

    expect(await screen.findByText('finance.personal.emptyTitle')).toBeTruthy();
    // The critical assertion: no metric card was rendered at all. A "¥0.00"
    // net worth would be indistinguishable from a real one.
    expect(screen.queryByText('finance.personal.netWorth')).toBeNull();
    expect(screen.queryByText('¥0.00')).toBeNull();
  });

  it('renders net worth and flags the illiquid asset', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();

    expect(await screen.findByText('finance.personal.netWorth')).toBeTruthy();
    expect(screen.getByText('¥1,785,000.00')).toBeTruthy();
    // The house must carry the illiquid tag so it cannot be mistaken for
    // spendable money.
    expect(screen.getByText('finance.personal.illiquidTag')).toBeTruthy();
    expect(screen.getByText('finance.personal.liquidTag')).toBeTruthy();
  });

  it('renders the savings rate and emergency-fund runway', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();

    await screen.findByText('finance.personal.savingsRate');
    expect(screen.getByText('42.86%')).toBeTruthy();
    expect(screen.getByText('13.8 finance.personal.months')).toBeTruthy();
  });

  it('labels the two outflow definitions so they do not read as bad arithmetic', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();

    await screen.findByText('finance.personal.savingsRate');
    // 收入 35,000, 总流出 25,000, 净结余 10,000, 储蓄率 42.86% — the rate
    // excludes 储蓄投资 while 净结余 includes it. Both are correct, and the
    // hints are the only thing stopping a user from reading the pair as a
    // subtraction that does not add up. If someone drops the hints, this
    // fails and points at the口径 doc comment in personal.py.
    expect(screen.getByText('finance.personal.netHint')).toBeTruthy();
    expect(screen.getByText('finance.personal.outflowHint')).toBeTruthy();
    expect(screen.getByText('¥25,000.00')).toBeTruthy();
    expect(screen.getByText('¥10,000.00')).toBeTruthy();
  });

  it('renders a deficit without hiding it', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue({
      ...FLOW,
      net: -2000,
      is_deficit: true,
      savings_rate: -0.0571,
    });
    renderWith();

    expect(await screen.findByText('finance.personal.deficit')).toBeTruthy();
  });

  it('shows only the cash-flow empty state when the balance sheet is missing', async () => {
    getPersonalBalanceSheet.mockResolvedValue(EMPTY_SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();

    expect(await screen.findByText('finance.personal.noSheetTitle')).toBeTruthy();
    // Cash-flow data is present, so its metrics render alongside.
    expect(screen.getByText('finance.personal.savingsRate')).toBeTruthy();
  });

  it('switches to the enterprise tab and renders the trial balance', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    getTrialBalance.mockResolvedValue({
      entry_count: 1,
      is_balanced: true,
      total_debit: 11300,
      total_credit: 11300,
      rows: [
        { account_code: '1122', account_name: '应收账款', debit: 11300, credit: 0 },
        { account_code: '6001', account_name: '主营业务收入', debit: 0, credit: 10000 },
      ],
    });
    renderWith();

    await screen.findByText('finance.personal.netWorth');
    fireEvent.click(screen.getByText('finance.tabEnterprise'));

    await waitFor(() => {
      expect(screen.getByText('finance.enterprise.trialBalance')).toBeTruthy();
    });
    expect(await screen.findByText('应收账款')).toBeTruthy();
    expect(screen.getByText('finance.enterprise.balanced')).toBeTruthy();
  });

  it('warns loudly when the trial balance does not balance', async () => {
    getPersonalBalanceSheet.mockResolvedValue(EMPTY_SHEET);
    getPersonalCashFlow.mockResolvedValue(EMPTY_FLOW);
    getTrialBalance.mockResolvedValue({
      entry_count: 1,
      is_balanced: false,
      total_debit: 10000,
      total_credit: 9000,
      rows: [],
    });
    renderWith();

    await screen.findByText('finance.personal.emptyTitle');
    fireEvent.click(screen.getByText('finance.tabEnterprise'));

    expect(
      await screen.findByText('finance.enterprise.unbalanced'),
    ).toBeTruthy();
  });

  it('states that the page is read-only', async () => {
    getPersonalBalanceSheet.mockResolvedValue(SHEET);
    getPersonalCashFlow.mockResolvedValue(FLOW);
    renderWith();
    expect(await screen.findByText('finance.readonlyNote')).toBeTruthy();
  });
});
