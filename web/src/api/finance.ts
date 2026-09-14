/**
 * Finance endpoints (ledger + personal finance).
 *
 * Read-only: every function here is a GET. Writes intentionally go through the
 * agent, because the *validation* is the point — a POST that bypassed
 * `JournalEntry.validate_against` would be a hole straight through the
 * double-entry invariant the ledger exists to enforce.
 */
import { api } from '@/api/client';

export interface LedgerAccount {
  code: string;
  name: string;
  category: string;
  normal_balance: 'debit' | 'credit';
  is_custom: boolean;
  is_active: boolean;
}

export interface AccountsResponse {
  count: number;
  accounts: LedgerAccount[];
}

export interface JournalLine {
  account_code: string;
  direction: 'debit' | 'credit';
  amount: number;
}

export interface JournalEntry {
  entry_id: string;
  entry_date: string;
  memo: string;
  source: string;
  lines: JournalLine[];
}

export interface EntriesResponse {
  count: number;
  entries: JournalEntry[];
}

export interface TrialBalanceRow {
  account_code: string;
  account_name: string;
  debit: number;
  credit: number;
}

export interface TrialBalanceResponse {
  entry_count: number;
  is_balanced: boolean;
  total_debit: number;
  total_credit: number;
  rows: TrialBalanceRow[];
}

export interface PersonalAsset {
  key: string;
  label: string;
  amount: number;
  liquid: boolean;
}

export interface PersonalLiability {
  key: string;
  label: string;
  amount: number;
  monthly_payment: number | null;
}

export interface PersonalBalanceSheet {
  has_data: boolean;
  as_of?: string;
  currency?: string;
  total_assets?: number;
  liquid_assets?: number;
  total_liabilities?: number;
  net_worth?: number;
  debt_to_asset_ratio?: number | null;
  assets?: PersonalAsset[];
  liabilities?: PersonalLiability[];
}

export interface CashFlowItem {
  category: string;
  label: string;
  amount: number;
}

export interface PersonalCashFlow {
  has_data: boolean;
  start?: string;
  end?: string;
  days?: number;
  currency?: string;
  income?: number;
  fixed?: number;
  living?: number;
  discretionary?: number;
  savings?: number;
  debt_service?: number;
  total_outflow?: number;
  net?: number;
  savings_rate?: number | null;
  is_deficit?: boolean;
  monthly_essential?: number;
  emergency_fund_months?: number | null;
  items?: CashFlowItem[];
}

export interface SnapshotSummary {
  snapshot_id: string;
  kind: 'balance_sheet' | 'cash_flow';
  period_start: string;
  period_end: string;
  currency: string;
  note: string;
  net_worth?: number;
  total_assets?: number;
  total_liabilities?: number;
  income?: number;
  net?: number;
  savings_rate?: number | null;
}

export interface SnapshotsResponse {
  count: number;
  snapshots: SnapshotSummary[];
}

export async function getAccounts(category?: string): Promise<AccountsResponse> {
  const { data } = await api.get<AccountsResponse>('/api/v1/finance/accounts', {
    params: category ? { category } : undefined,
  });
  return data;
}

export async function getEntries(params?: {
  startDate?: string;
  endDate?: string;
  accountCode?: string;
  limit?: number;
}): Promise<EntriesResponse> {
  const { data } = await api.get<EntriesResponse>('/api/v1/finance/entries', {
    params: {
      start_date: params?.startDate,
      end_date: params?.endDate,
      account_code: params?.accountCode,
      limit: params?.limit,
    },
  });
  return data;
}

export async function getTrialBalance(params?: {
  startDate?: string;
  endDate?: string;
  currency?: string;
}): Promise<TrialBalanceResponse> {
  const { data } = await api.get<TrialBalanceResponse>('/api/v1/finance/trial-balance', {
    params: {
      start_date: params?.startDate,
      end_date: params?.endDate,
      currency: params?.currency,
    },
  });
  return data;
}

export async function getPersonalBalanceSheet(): Promise<PersonalBalanceSheet> {
  const { data } = await api.get<PersonalBalanceSheet>('/api/v1/finance/personal/balance-sheet');
  return data;
}

export async function getPersonalCashFlow(): Promise<PersonalCashFlow> {
  const { data } = await api.get<PersonalCashFlow>('/api/v1/finance/personal/cash-flow');
  return data;
}

export async function getSnapshots(kind?: 'balance_sheet' | 'cash_flow', limit = 50): Promise<SnapshotsResponse> {
  const { data } = await api.get<SnapshotsResponse>('/api/v1/finance/snapshots', {
    params: { kind, limit },
  });
  return data;
}
