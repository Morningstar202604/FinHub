"""Tests for the finance ledger tools.

These run against a mocked DB pool (the repo's convention — see
test_active_task_discovery.py). The point of the suite is the *contract the
model sees*: a rejected entry must come back as a correctable message, not a
traceback, because a model that receives a bare exception retries the same
broken entry instead of fixing it.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ptc_agent.agent.tools.finance import (
    EntryLineInput,
    create_finance_tools,
)

DB_CONN_PATH = "src.server.database.pool.get_db_connection"
CHART_PATH = "src.server.database.ledger.load_chart"
LIST_ACC_PATH = "src.server.database.ledger.list_accounts"
INSERT_PATH = "src.server.database.ledger.insert_entry"
ENTRIES_PATH = "src.server.database.ledger.list_entries"
LIST_ENTRIES_PATH = "src.server.database.ledger.list_entries"


def _tools():
    return {t.name: t for t in create_finance_tools("u-1")}


def _line(code: str, direction: str, amount: str) -> dict:
    return {"account_code": code, "direction": direction, "amount": amount}


class TestToolRegistration:
    def test_all_expected_tools_are_exposed(self):
        assert set(_tools()) == {
            "post_journal_entry",
            "list_accounts",
            "add_account",
            "get_trial_balance",
            "list_journal_entries",
            "check_entry_balance",
        }

    def test_tools_bind_user_id_and_never_expose_it(self):
        """The model must not be able to choose an owner.

        A user_id parameter would let a prompt-injected instruction write to
        another user's ledger, so the binding is closure-captured and the
        schema must not surface it.
        """
        for name, tool in _tools().items():
            schema = tool.args_schema.model_json_schema() if tool.args_schema else {}
            assert "user_id" not in schema.get("properties", {}), name


class TestCheckEntryBalance:
    @pytest.mark.asyncio
    async def test_balanced_entry_reports_ok_with_totals(self):
        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()
        ):
            result = await _tools()["check_entry_balance"].ainvoke(
                {"lines": [
                    _line("1122", "debit", "11300.00"),
                    _line("6001", "credit", "10000.00"),
                    _line("2221001", "credit", "1300.00"),
                ]}
            )
        assert "✅" in result
        assert "11300.00" in result  # the amount must be shown back

    @pytest.mark.asyncio
    async def test_unbalanced_entry_is_rejected_with_the_difference(self):
        """The message must name the gap so the model can self-correct."""
        with patch(CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()):
            result = await _tools()["check_entry_balance"].ainvoke(
                {"lines": [
                    _line("1122", "debit", "11300.00"),
                    _line("6001", "credit", "10000.00"),
                ]}
            )
        assert "❌" in result
        assert "130000" in result  # 1300 元 in cents

    @pytest.mark.asyncio
    async def test_empty_lines_rejected_without_touching_db(self):
        with patch(CHART_PATH, new_callable=AsyncMock) as mock_chart:
            result = await _tools()["check_entry_balance"].ainvoke({"lines": []})
        assert "❌" in result
        mock_chart.assert_not_awaited()


class TestPostJournalEntry:
    @pytest.mark.asyncio
    async def test_valid_entry_reports_the_voucher_id(self):
        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()
        ), patch(
            INSERT_PATH,
            new_callable=AsyncMock,
            return_value="11111111-2222-3333-4444-555555555555",
        ):
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "2026-09-14",
                    "memo": "含税开票",
                    "lines": [
                        _line("1122", "debit", "11300.00"),
                        _line("6001", "credit", "10000.00"),
                        _line("2221001", "credit", "1300.00"),
                    ],
                }
            )
        assert "✅" in result
        assert "11111111" in result

    @pytest.mark.asyncio
    async def test_validation_failure_never_reaches_the_insert(self):
        """A rejection must short-circuit: no write is attempted."""
        from src.server.services.finance.ledger import default_chart

        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=default_chart()
        ), patch(INSERT_PATH, new_callable=AsyncMock) as mock_insert:
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "2026-09-14",
                    "memo": "不平",
                    "lines": [
                        _line("1122", "debit", "11300.00"),
                        _line("6001", "credit", "10000.00"),
                    ],
                }
            )
        assert "❌" in result
        assert "130000" in result  # names the gap
        mock_insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_validates_independently_of_the_write_path(self):
        """The tool must not delegate its correctness to insert_entry.

        Pinned as a separate case because the earlier version *did* delegate:
        it called insert_entry and reported success based on that call alone.
        With insert_entry stubbed here, the tool must still reject the
        unbalanced entry on its own — otherwise the tool's docstring ("拒绝不
        平衡的分录") describes a guarantee it does not itself provide.
        """
        from src.server.services.finance.ledger import default_chart

        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=default_chart()
        ), patch(
            INSERT_PATH,
            new_callable=AsyncMock,
            side_effect=AssertionError("insert must not be reached"),
        ):
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "2026-09-14",
                    "memo": "不平",
                    "lines": [
                        _line("1122", "debit", "11300.00"),
                        _line("6001", "credit", "10000.00"),
                    ],
                }
            )
        assert "❌" in result
        assert "✅" not in result

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_is_reported_distinctly(self):
        """A duplicate is not a validation error; retrying will not help."""
        from src.server.database.ledger import DuplicateEntryError

        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()
        ), patch(
            INSERT_PATH,
            new_callable=AsyncMock,
            side_effect=DuplicateEntryError("幂等键 'k1' 已存在"),
        ):
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "2026-09-14",
                    "memo": "重复",
                    "idempotency_key": "k1",
                    "lines": [
                        _line("1002", "debit", "100.00"),
                        _line("6001", "credit", "100.00"),
                    ],
                }
            )
        assert "⚠️" in result
        assert "❌" not in result  # distinguishable from a validation failure

    @pytest.mark.asyncio
    async def test_invalid_date_is_rejected_with_the_format_hint(self):
        with patch(CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()):
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "14/09/2026",
                    "memo": "日期错误",
                    "lines": [
                        _line("1002", "debit", "100.00"),
                        _line("6001", "credit", "100.00"),
                    ],
                }
            )
        assert "❌" in result
        assert "YYYY-MM-DD" in result

    @pytest.mark.asyncio
    async def test_unexpected_db_error_is_surfaced_not_swallowed(self):
        """An infrastructure failure must be visible, not silently 'ok'."""
        with patch(
            CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()
        ), patch(
            INSERT_PATH, new_callable=AsyncMock, side_effect=RuntimeError("db down")
        ):
            result = await _tools()["post_journal_entry"].ainvoke(
                {
                    "entry_date": "2026-09-14",
                    "memo": "db 挂了",
                    "lines": [
                        _line("1002", "debit", "100.00"),
                        _line("6001", "credit", "100.00"),
                    ],
                }
            )
        assert "❌" in result
        assert "db down" in result or "系统错误" in result


class TestAddAccount:
    @pytest.mark.asyncio
    async def test_invalid_category_rejected_before_db(self):
        with patch(
            "src.server.database.ledger.upsert_account", new_callable=AsyncMock
        ) as mock_upsert:
            result = await _tools()["add_account"].ainvoke(
                {
                    "code": "9999",
                    "name": "测试",
                    "category": "收入类",
                    "normal_balance": "credit",
                }
            )
        assert "❌" in result
        mock_upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_normal_balance_rejected(self):
        with patch(
            "src.server.database.ledger.upsert_account", new_callable=AsyncMock
        ) as mock_upsert:
            result = await _tools()["add_account"].ainvoke(
                {
                    "code": "9999",
                    "name": "测试",
                    "category": "资产",
                    "normal_balance": "both",
                }
            )
        assert "❌" in result
        mock_upsert.assert_not_awaited()


class TestTrialBalanceTool:
    @pytest.mark.asyncio
    async def test_empty_ledger_says_so(self):
        with patch(ENTRIES_PATH, new_callable=AsyncMock, return_value=[]), patch(
            CHART_PATH, new_callable=AsyncMock, return_value=MagicMock()
        ):
            result = await _tools()["get_trial_balance"].ainvoke({})
        assert "没有已入账" in result

    @pytest.mark.asyncio
    async def test_renders_rows_and_balance_verdict(self):
        """Feeds DB-shaped rows, as load_entries_as_objects receives them."""
        rows = [
            {"entry_id": "e1", "entry_date": date(2026, 9, 14), "memo": "开票",
             "source": "agent", "created_at": None,
             "account_code": "1122", "direction": "debit",
             "amount_minor": 1130000, "line_no": 0},
            {"entry_id": "e1", "entry_date": date(2026, 9, 14), "memo": "开票",
             "source": "agent", "created_at": None,
             "account_code": "6001", "direction": "credit",
             "amount_minor": 1000000, "line_no": 1},
            {"entry_id": "e1", "entry_date": date(2026, 9, 14), "memo": "开票",
             "source": "agent", "created_at": None,
             "account_code": "2221001", "direction": "credit",
             "amount_minor": 130000, "line_no": 2},
        ]

        from src.server.services.finance.ledger import default_chart

        with patch(LIST_ENTRIES_PATH, new_callable=AsyncMock, return_value=rows), patch(
            CHART_PATH, new_callable=AsyncMock, return_value=default_chart()
        ):
            result = await _tools()["get_trial_balance"].ainvoke({})
        assert "✅ 借贷平衡" in result
        assert "1122" in result
        assert "应收账款" in result


class TestListAccountsTool:
    @pytest.mark.asyncio
    async def test_groups_by_category(self):
        with patch(
            LIST_ACC_PATH,
            new_callable=AsyncMock,
            return_value=[
                {"code": "1122", "name": "应收账款", "category": "资产",
                 "normal_balance": "debit", "is_active": True, "is_custom": False},
                {"code": "6001", "name": "主营业务收入", "category": "收入",
                 "normal_balance": "credit", "is_active": True, "is_custom": False},
            ],
        ):
            result = await _tools()["list_accounts"].ainvoke({})
        assert "【资产】" in result
        assert "【收入】" in result

    @pytest.mark.asyncio
    async def test_db_failure_is_surfaced(self):
        with patch(LIST_ACC_PATH, new_callable=AsyncMock, side_effect=RuntimeError("x")):
            result = await _tools()["list_accounts"].ainvoke({})
        assert "❌" in result


class TestEntryLineInput:
    def test_amount_is_a_string_not_a_float(self):
        """Guards the JSON-decimal problem at the schema level.

        If this ever becomes ``float``, 0.1 + 0.2 style drift enters the
        ledger at the boundary and every downstream exactness argument is
        void.
        """
        schema = EntryLineInput.model_json_schema()
        assert schema["properties"]["amount"]["type"] == "string"

    def test_direction_is_constrained_to_the_two_sides(self):
        schema = EntryLineInput.model_json_schema()
        assert set(schema["properties"]["direction"]["enum"]) == {"debit", "credit"}
