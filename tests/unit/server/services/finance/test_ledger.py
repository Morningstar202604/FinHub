"""Tests for the ledger kernel.

The load-bearing tests here are the *rejections*. A ledger that accepts an
unbalanced entry is worse than no ledger, because it launders a hallucinated
journal entry into something that looks authoritative in a report. So the
negative cases carry as much weight as the arithmetic.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.server.services.finance.ledger import (
    CAS_DEFAULT_ACCOUNTS,
    Account,
    ChartOfAccounts,
    JournalEntry,
    LedgerError,
    currency_exponent,
    default_chart,
    from_cents,
    to_cents,
    trial_balance,
)


# ── money representation ──────────────────────────────────────────────────


class TestMoneyRepresentation:
    def test_float_is_converted_via_str_not_binary_value(self):
        """The reason we don't use Decimal(float) directly.

        Decimal(0.1) carries the binary expansion; Decimal("0.1") carries what
        the caller wrote. A ledger must do the latter.
        """
        assert to_cents(0.1, "CNY") == 10
        # Binary expansion would give 0.1000000000000000055511151231257827
        # -> 10 cents either way here, so prove it on a value where it differs.
        assert to_cents(1.005, "USD") == 101  # HALF_UP on the written value
        # Decimal(1.005) == 1.00499999999999989... which would floor to 100.
        assert Decimal(1.005) * 100 != Decimal("100.5")

    def test_sum_of_floats_is_exact_in_cents(self):
        """0.1 + 0.2 != 0.3 in float; in cents it must be exactly 0.30."""
        total = sum(to_cents(v, "CNY") for v in (0.1, 0.2))
        assert total == 30
        assert from_cents(total, "CNY") == Decimal("0.30")

    def test_jpy_has_no_minor_unit(self):
        """JPY: 1000 円 is 1000 minor units, not 100000.

        Getting this wrong scales every JPY amount by 100 — the classic
        currency-subunit bug.
        """
        assert currency_exponent("JPY") == 0
        assert to_cents(1000, "JPY") == 1000
        assert from_cents(1000, "JPY") == Decimal("1000")

    def test_kwd_has_three_minor_units(self):
        assert currency_exponent("KWD") == 3
        assert to_cents("1.234", "KWD") == 1234

    def test_unknown_currency_defaults_to_two(self):
        assert currency_exponent("XYZ") == 2
        assert to_cents("1.23", "XYZ") == 123

    def test_round_half_up_not_bankers(self):
        """Accountants round half away from zero; Python's default is banker's.

        round(2.5) == 2 in Python. For a ledger that is a silent 1-cent loss on
        every such line, and it compounds across a tax calculation.
        """
        assert to_cents("0.125", "USD") == 13  # not 12
        assert to_cents("0.135", "USD") == 14  # not 14-via-banker's-on-0.135

    def test_negative_amount_round_trips(self):
        assert from_cents(to_cents("-5.55", "CNY"), "CNY") == Decimal("-5.55")


# ── entry construction ────────────────────────────────────────────────────


def _entry(direction_pairs, memo="test"):
    entry = JournalEntry(entry_date=date(2026, 9, 14), memo=memo)
    for code, direction, amount in direction_pairs:
        entry.add(code, direction, to_cents(amount, "CNY"))
    return entry


class TestEntryValidation:
    def test_balanced_entry_passes(self):
        entry = _entry([
            ("1122", "debit", "1130"),
            ("6001", "credit", "1000"),
            ("2221001", "credit", "130"),
        ])
        entry.validate()  # no raise
        assert entry.imbalance_cents() == 0

    def test_unbalanced_entry_is_rejected_with_the_difference(self):
        entry = _entry([
            ("1122", "debit", "1130"),
            ("6001", "credit", "1000"),
        ])
        with pytest.raises(LedgerError) as exc:
            entry.validate()
        # The message must name the amount so the model can self-correct.
        assert "13000" in str(exc.value)
        assert "不平衡" in str(exc.value)

    def test_single_line_entry_is_rejected(self):
        entry = _entry([("1002", "debit", "100")])
        with pytest.raises(LedgerError, match="至少一借一贷"):
            entry.validate()

    def test_debits_only_is_rejected(self):
        entry = _entry([
            ("1002", "debit", "100"),
            ("1001", "debit", "100"),
        ])
        with pytest.raises(LedgerError, match="缺少贷方"):
            entry.validate()

    def test_credits_only_is_rejected(self):
        entry = _entry([
            ("6001", "credit", "100"),
            ("6051", "credit", "100"),
        ])
        with pytest.raises(LedgerError, match="缺少借方"):
            entry.validate()

    def test_empty_entry_is_rejected(self):
        entry = JournalEntry(entry_date=date(2026, 9, 14), memo="empty")
        with pytest.raises(LedgerError, match="分录为空"):
            entry.validate()

    def test_zero_amount_line_is_rejected(self):
        """A 0 amount is nearly always an upstream miscalculation."""
        with pytest.raises(LedgerError, match="金额为 0"):
            _entry([("1002", "debit", "0"), ("6001", "credit", "0")])

    def test_negative_amount_line_is_rejected(self):
        """Direction carries the sign; a negative magnitude is a caller bug."""
        with pytest.raises(LedgerError, match="金额为负"):
            _entry([("1002", "debit", "-100"), ("6001", "credit", "100")])

    def test_unknown_account_is_rejected_and_lists_valid_codes(self):
        entry = _entry([
            ("9999", "debit", "100"),
            ("6001", "credit", "100"),
        ])
        with pytest.raises(LedgerError) as exc:
            entry.validate_against(default_chart())
        assert "9999" in str(exc.value)
        assert "1001" in str(exc.value)  # offers real codes as a hint


# ── trial balance ─────────────────────────────────────────────────────────


class TestTrialBalance:
    def test_totals_are_equal_for_balanced_entries(self):
        entries = [
            _entry([("1002", "debit", "1000"), ("4001", "credit", "1000")]),
            _entry([("1122", "debit", "500"), ("6001", "credit", "500")]),
        ]
        tb = trial_balance(entries)
        assert tb.is_balanced
        assert tb.total_debit_cents == tb.total_credit_cents == 150000

    def test_rows_aggregate_by_account_across_entries(self):
        entries = [
            _entry([("1002", "debit", "100"), ("6001", "credit", "100")]),
            _entry([("1002", "debit", "250"), ("6001", "credit", "250")]),
        ]
        tb = trial_balance(entries)
        by_code = {r.account_code: r for r in tb.rows}
        assert by_code["1002"].debit_cents == to_cents("350")
        assert by_code["6001"].credit_cents == to_cents("350")

    def test_unknown_account_renders_as_placeholder_not_crash(self):
        """Trial balance of imported data may reference accounts we lack."""
        entry = _entry([("8888", "debit", "100"), ("6001", "credit", "100")])
        tb = trial_balance([entry])
        row = next(r for r in tb.rows if r.account_code == "8888")
        assert row.account_name == "(未知科目)"

    def test_empty_ledger_balances_trivially(self):
        tb = trial_balance([])
        assert tb.is_balanced
        assert tb.rows == []


# ── chart of accounts ─────────────────────────────────────────────────────


class TestChartOfAccounts:
    def test_default_chart_codes_are_unique(self):
        """A duplicate code would silently shadow an account on add()."""
        codes = [a.code for a in CAS_DEFAULT_ACCOUNTS]
        assert len(codes) == len(set(codes))

    def test_default_chart_has_both_balance_directions(self):
        assert default_chart().has("1122")
        assert default_chart().get("2221001").normal_balance == "credit"
        assert default_chart().get("1002").normal_balance == "debit"

    def test_accumulated_depreciation_is_a_credit_asset(self):
        """1602 is an asset contra-account carrying a credit balance.

        If it were marked debit, every trial balance with depreciation would
        look wrong to a normal-balance-aware reader.
        """
        acct = default_chart().get("1602")
        assert acct.category == "资产"
        assert acct.normal_balance == "credit"

    def test_custom_chart(self):
        chart = ChartOfAccounts([Account("X1", "自定科目", "资产", "debit")])
        assert chart.has("X1")
        assert not chart.has("1002")
        assert len(chart) == 1
