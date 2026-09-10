import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AuditReportView from '../AuditReportView';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string; count?: number }) =>
      opts?.defaultValue ?? key,
  }),
}));

describe('AuditReportView (M4-2)', () => {
  it('renders nothing for an empty artifact', () => {
    const { container } = render(<AuditReportView artifact={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a passed banner when there are no findings', () => {
    render(<AuditReportView artifact={{ report_text: 'ok', findings: [] }} />);
    expect(screen.getByText('审校通过：未发现数值/引用/矛盾问题。')).toBeTruthy();
  });

  it('renders findings with their messages', () => {
    const findings = [
      { level: 'error', kind: 'noverify', message: '营收 9000 与数据源 9180 差 2.0%', evidence: 'source=fmp' },
      { level: 'warning', kind: 'conflict', message: '同一指标两处数值不一致' },
    ];
    render(<AuditReportView artifact={{ report_text: 'r', findings }} />);
    expect(screen.getByText('营收 9000 与数据源 9180 差 2.0%')).toBeTruthy();
    expect(screen.getByText('同一指标两处数值不一致')).toBeTruthy();
    expect(screen.getByText('source=fmp')).toBeTruthy();
  });

  it('rejects artifact types it cannot render', () => {
    const { container } = render(<AuditReportView artifact={{ type: 'stock_prices', data: [] } as unknown as Record<string, unknown>} />);
    expect(container.firstChild).toBeNull();
  });
});