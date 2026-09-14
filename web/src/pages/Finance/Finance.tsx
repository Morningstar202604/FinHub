import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  RefreshCw,
  Scale,
  TrendingUp,
  User,
  Wallet,
} from 'lucide-react';
import {
  getPersonalBalanceSheet,
  getPersonalCashFlow,
  getTrialBalance,
  type PersonalBalanceSheet,
  type PersonalCashFlow,
  type TrialBalanceResponse,
} from '@/api/finance';
import './Finance.css';

/**
 * 财务部 — one page, two halves: 企业（记账凭证/试算平衡）与个人（净资产/收支）。
 *
 * Two deliberate choices worth stating, because both look like omissions:
 *
 * 1. It is read-only. Every figure here comes from the same service modules the
 *    agent tools use, so the page can never disagree with the agent. An edit
 *    form would need a write path, and the ledger's whole guarantee is that
 *    entries are validated by `JournalEntry.validate_against` before
 *    persistence — a form that POSTed directly would route around it.
 *    The empty states say "记一笔" and tell you to ask the agent.
 *
 * 2. ``has_data: false`` renders an explicit empty state, never a zero. Net
 *    worth of ¥0 and "you never told me your net worth" are very different
 *    things, and only one of them is safe to show silently.
 */

type TabKey = 'enterprise' | 'personal';

function money(value: number | null | undefined, currency = 'CNY'): string {
  if (value === null || value === undefined) return '—';
  const symbol = currency === 'CNY' ? '¥' : '';
  return `${symbol}${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(2)}%`;
}

/** Shared empty/first-use state. Wording tells the user *how* to get data. */
function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="finance-empty">
      <Wallet size={28} aria-hidden="true" />
      <p className="finance-empty-title">{title}</p>
      <p className="finance-empty-hint">{hint}</p>
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone = 'neutral',
  hint,
}: {
  label: string;
  value: string;
  tone?: 'neutral' | 'positive' | 'negative';
  hint?: string;
}) {
  return (
    <div className={`finance-metric finance-metric--${tone}`}>
      <span className="finance-metric-label">{label}</span>
      <span className="finance-metric-value">{value}</span>
      {hint ? <span className="finance-metric-hint">{hint}</span> : null}
    </div>
  );
}

function EnterpriseView() {
  const { t } = useTranslation();
  const { data, status, isFetching, refetch } = useQuery<TrialBalanceResponse>({
    queryKey: ['finance', 'trial-balance'],
    queryFn: () => getTrialBalance(),
    staleTime: 30_000,
  });

  if (status === 'pending') {
    return <div className="finance-loading">{t('finance.loading')}</div>;
  }
  if (status === 'error') {
    return (
      <EmptyState
        title={t('finance.enterprise.errorTitle')}
        hint={t('finance.enterprise.errorHint')}
      />
    );
  }

  const rows = data?.rows ?? [];

  return (
    <div className="finance-panel">
      <div className="finance-toolbar">
        <h2 className="finance-section-title">
          <Scale size={18} aria-hidden="true" />
          {t('finance.enterprise.trialBalance')}
        </h2>
        <button
          type="button"
          className="finance-refresh"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {t('finance.refresh')}
        </button>
      </div>

      <div className="finance-metrics">
        <MetricCard
          label={t('finance.enterprise.totalDebit')}
          value={money(data?.total_debit)}
        />
        <MetricCard
          label={t('finance.enterprise.totalCredit')}
          value={money(data?.total_credit)}
        />
        <MetricCard
          label={t('finance.enterprise.vouchers')}
          value={String(data?.entry_count ?? 0)}
        />
      </div>

      <div
        className={`finance-balance-badge ${
          data?.is_balanced ? 'is-ok' : 'is-bad'
        }`}
      >
        {data?.is_balanced ? (
          <>
            <CheckCircle2 size={16} aria-hidden="true" />
            {t('finance.enterprise.balanced')}
          </>
        ) : (
          <>
            <AlertTriangle size={16} aria-hidden="true" />
            {t('finance.enterprise.unbalanced')}
          </>
        )}
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title={t('finance.enterprise.emptyTitle')}
          hint={t('finance.enterprise.emptyHint')}
        />
      ) : (
        <div className="finance-table-wrap">
          <table className="finance-table">
            <thead>
              <tr>
                <th>{t('finance.enterprise.code')}</th>
                <th>{t('finance.enterprise.name')}</th>
                <th className="is-num">{t('finance.enterprise.debit')}</th>
                <th className="is-num">{t('finance.enterprise.credit')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.account_code}>
                  <td className="is-mono">{row.account_code}</td>
                  <td>{row.account_name}</td>
                  <td className="is-num">
                    {row.debit ? money(row.debit) : '—'}
                  </td>
                  <td className="is-num">
                    {row.credit ? money(row.credit) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}>{t('finance.enterprise.total')}</td>
                <td className="is-num">{money(data?.total_debit)}</td>
                <td className="is-num">{money(data?.total_credit)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

function PersonalView() {
  const { t } = useTranslation();
  const sheetQuery = useQuery<PersonalBalanceSheet>({
    queryKey: ['finance', 'personal', 'balance-sheet'],
    queryFn: () => getPersonalBalanceSheet(),
    staleTime: 30_000,
  });
  const flowQuery = useQuery<PersonalCashFlow>({
    queryKey: ['finance', 'personal', 'cash-flow'],
    queryFn: () => getPersonalCashFlow(),
    staleTime: 30_000,
  });

  if (sheetQuery.status === 'pending' || flowQuery.status === 'pending') {
    return <div className="finance-loading">{t('finance.loading')}</div>;
  }

  const sheet = sheetQuery.data;
  const flow = flowQuery.data;
  const hasSheet = Boolean(sheet?.has_data);
  const hasFlow = Boolean(flow?.has_data);

  if (!hasSheet && !hasFlow) {
    return (
      <EmptyState
        title={t('finance.personal.emptyTitle')}
        hint={t('finance.personal.emptyHint')}
      />
    );
  }

  const months = flow?.emergency_fund_months ?? null;
  const monthsTone =
    months === null ? 'neutral' : months < 3 ? 'negative' : 'positive';

  return (
    <div className="finance-panel">
      <div className="finance-toolbar">
        <h2 className="finance-section-title">
          <TrendingUp size={18} aria-hidden="true" />
          {t('finance.personal.title')}
        </h2>
        <button
          type="button"
          className="finance-refresh"
          onClick={() => {
            void sheetQuery.refetch();
            void flowQuery.refetch();
          }}
          disabled={sheetQuery.isFetching || flowQuery.isFetching}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {t('finance.refresh')}
        </button>
      </div>

      {hasSheet ? (
        <>
          <div className="finance-metrics">
            <MetricCard
              label={t('finance.personal.netWorth')}
              value={money(sheet?.net_worth, sheet?.currency)}
              tone={(sheet?.net_worth ?? 0) >= 0 ? 'positive' : 'negative'}
            />
            <MetricCard
              label={t('finance.personal.liquid')}
              value={money(sheet?.liquid_assets, sheet?.currency)}
              hint={t('finance.personal.liquidHint')}
            />
            <MetricCard
              label={t('finance.personal.totalAssets')}
              value={money(sheet?.total_assets, sheet?.currency)}
            />
            <MetricCard
              label={t('finance.personal.totalLiabilities')}
              value={money(sheet?.total_liabilities, sheet?.currency)}
            />
            <MetricCard
              label={t('finance.personal.debtRatio')}
              value={percent(sheet?.debt_to_asset_ratio)}
            />
          </div>

          <div className="finance-columns">
            <div>
              <h3 className="finance-subtitle">
                {t('finance.personal.assets')}
              </h3>
              <ul className="finance-list">
                {(sheet?.assets ?? []).map((a) => (
                  <li key={`${a.key}-${a.label}`}>
                    <span className="finance-list-label">
                      {a.label}
                      <span
                        className={`finance-chip ${
                          a.liquid ? 'is-liquid' : 'is-illiquid'
                        }`}
                      >
                        {a.liquid
                          ? t('finance.personal.liquidTag')
                          : t('finance.personal.illiquidTag')}
                      </span>
                    </span>
                    <span className="is-num">
                      {money(a.amount, sheet?.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="finance-subtitle">
                {t('finance.personal.liabilities')}
              </h3>
              <ul className="finance-list">
                {(sheet?.liabilities ?? []).map((li) => (
                  <li key={`${li.key}-${li.label}`}>
                    <span className="finance-list-label">
                      {li.label}
                      {li.monthly_payment ? (
                        <span className="finance-chip is-muted">
                          {t('finance.personal.monthly')}{' '}
                          {money(li.monthly_payment, sheet?.currency)}
                        </span>
                      ) : null}
                    </span>
                    <span className="is-num">
                      {money(li.amount, sheet?.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </>
      ) : (
        <EmptyState
          title={t('finance.personal.noSheetTitle')}
          hint={t('finance.personal.noSheetHint')}
        />
      )}

      {hasFlow ? (
        <>
          <h3 className="finance-subtitle">
            {t('finance.personal.cashFlow')}
            {flow?.start && flow?.end ? (
              <span className="finance-period">
                {flow.start} ~ {flow.end}
              </span>
            ) : null}
          </h3>
          <div className="finance-metrics">
            <MetricCard
              label={t('finance.personal.income')}
              value={money(flow?.income, flow?.currency)}
            />
            {/* 总流出 and 净结余 use two different outflow definitions on
                purpose, and sitting them side by side with no hint made them
                look like a broken subtraction: 净结余 excludes 储蓄投资 (a
                transfer is not spending) while 总流出 includes it (the cash
                really did leave the account). Both numbers are right; the
                hints are what make that legible, so they are not optional —
                a deficit message replaces the hint rather than stacking. */}
            <MetricCard
              label={t('finance.personal.outflow')}
              value={money(flow?.total_outflow, flow?.currency)}
              hint={t('finance.personal.outflowHint')}
            />
            <MetricCard
              label={t('finance.personal.net')}
              value={money(flow?.net, flow?.currency)}
              tone={flow?.is_deficit ? 'negative' : 'positive'}
              hint={
                flow?.is_deficit
                  ? t('finance.personal.deficit')
                  : t('finance.personal.netHint')
              }
            />
            <MetricCard
              label={t('finance.personal.savingsRate')}
              value={percent(flow?.savings_rate)}
              hint={t('finance.personal.savingsHint')}
            />
            <MetricCard
              label={t('finance.personal.runway')}
              value={months === null ? '—' : `${months} ${t('finance.personal.months')}`}
              tone={monthsTone as 'neutral' | 'positive' | 'negative'}
              hint={t('finance.personal.runwayHint')}
            />
          </div>
        </>
      ) : (
        <EmptyState
          title={t('finance.personal.noFlowTitle')}
          hint={t('finance.personal.noFlowHint')}
        />
      )}
    </div>
  );
}

export default function Finance() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>('personal');

  return (
    <div className="finance-page">
      <header className="finance-header">
        <h1 className="finance-title">{t('finance.title')}</h1>
        <p className="finance-subtitle-text">{t('finance.tagline')}</p>
      </header>

      <div className="finance-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'personal'}
          className={`finance-tab ${tab === 'personal' ? 'is-active' : ''}`}
          onClick={() => setTab('personal')}
        >
          <User size={15} aria-hidden="true" />
          {t('finance.tabPersonal')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'enterprise'}
          className={`finance-tab ${tab === 'enterprise' ? 'is-active' : ''}`}
          onClick={() => setTab('enterprise')}
        >
          <Building2 size={15} aria-hidden="true" />
          {t('finance.tabEnterprise')}
        </button>
      </div>

      <div className="finance-content">
        {tab === 'personal' ? <PersonalView /> : <EnterpriseView />}
      </div>

      <p className="finance-readonly-note">{t('finance.readonlyNote')}</p>
    </div>
  );
}
