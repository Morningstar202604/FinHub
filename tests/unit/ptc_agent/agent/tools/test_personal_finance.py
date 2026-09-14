"""Tests for the personal-finance tools.

Same stance as test_finance.py: the contract the *model* sees is the thing
under test. The load-bearing cases are the rejections — a tool that accepts an
unknown asset class, or reports a net worth it computed itself rather than from
recorded components, is how a plausible invented number becomes an
authoritative one.

The DB is mocked throughout (the repo's convention); the round-trip behaviour
against a real Postgres was verified separately during development.
"""

from datetime import date

import pytest

from ptc_agent.agent.tools.personal_finance import create_personal_finance_tools

SAVE_PATH = "src.server.database.personal_finance.save_snapshot"
LATEST_PATH = "src.server.database.personal_finance.get_latest_snapshot"
LIST_PATH = "src.server.database.personal_finance.list_snapshots"

USER = "00000000-0000-0000-0000-000000000001"


def _tools(user_id: str = USER):
    return {t.name: t for t in create_personal_finance_tools(user_id)}


def _bs_row(
    assets: list[dict],
    liabilities: list[dict] | None = None,
    *,
    as_of: str = "2026-09-14",
) -> dict:
    """Build a snapshot row in the shape list_snapshots returns."""
    items = [
        {
            "side": "asset",
            "key": a["key"],
            "label": a["label"],
            "amount_minor": a["amount_minor"],
            "liquid": a["liquid"],
        }
        for a in assets
    ] + [
        {
            "side": "liability",
            "key": li["key"],
            "label": li["label"],
            "amount_minor": li["amount_minor"],
            "monthly_payment_minor": li.get("monthly_payment_minor"),
        }
        for li in (liabilities or [])
    ]
    d = date.fromisoformat(as_of)
    return {
        "snapshot_id": "snap-1",
        "kind": "balance_sheet",
        "period_start": d,
        "period_end": d,
        "currency": "CNY",
        "note": "",
        "items": items,
        "created_at": None,
    }


class TestToolRegistration:
    def test_all_expected_tools_are_exposed(self):
        assert set(_tools()) == {
            "record_balance_sheet",
            "record_cash_flow",
            "get_net_worth",
            "get_cash_flow_analysis",
            "get_asset_classes",
            "list_financial_snapshots",
        }

    def test_tools_are_bound_to_the_user(self):
        """The owner id must come from construction, never from the model."""
        tools = _tools("11111111-1111-1111-1111-111111111111")
        for name in ("record_balance_sheet", "record_cash_flow", "get_net_worth"):
            schema = tools[name].args_schema.model_json_schema()
            props = schema.get("properties", {})
            assert "user_id" not in props, f"{name} leaks a user_id parameter"


class TestRecordBalanceSheet:
    @pytest.mark.asyncio
    async def test_records_and_reports_net_worth(self):
        captured = {}

        async def fake_save(user_id, kind, **kwargs):
            captured["user_id"] = user_id
            captured["kind"] = kind
            captured["items"] = kwargs["items"]
            return "snap-1"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(SAVE_PATH, fake_save)
            result = await _tools()["record_balance_sheet"].ainvoke(
                {
                    "as_of": "2026-09-14",
                    "assets": [
                        {
                            "key": "cash",
                            "label": "活期",
                            "amount": "85000.00",
                        },
                        {
                            "key": "property",
                            "label": "自住房",
                            "amount": "3500000.00",
                        },
                    ],
                    "liabilities": [
                        {
                            "key": "mortgage",
                            "label": "房贷",
                            "amount": "1800000.00",
                            "monthly_payment": "9800.00",
                        }
                    ],
                }
            )

        assert "✅" in result
        assert "3,585,000.00" in result  # 85,000 + 3,500,000
        assert "1,785,000.00" in result  # 3,585,000 − 1,800,000
        assert captured["kind"] == "balance_sheet"
        assert captured["user_id"] == USER

        # The house must not be counted as spendable; only 现金 is liquid.
        assert "85,000.00" in result

    @pytest.mark.asyncio
    async def test_liquid_flag_follows_the_class_catalogue_by_default(self):
        """现金 is liquid by default; 房产 is not. Neither is inferred from the
        label — the catalogue decides, and an explicit flag overrides it."""
        captured = {}

        async def fake_save(user_id, kind, **kwargs):
            captured["items"] = kwargs["items"]
            return "snap-1"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(SAVE_PATH, fake_save)
            await _tools()["record_balance_sheet"].ainvoke(
                {
                    "assets": [
                        {"key": "cash", "label": "活期", "amount": "1000"},
                        {"key": "property", "label": "自住房", "amount": "2000"},
                        {
                            "key": "property",
                            "label": "准备出售的投资房",
                            "amount": "3000",
                            "liquid": True,
                        },
                    ]
                }
            )

        by_label = {i["label"]: i["liquid"] for i in captured["items"]}
        assert by_label["活期"] is True
        assert by_label["自住房"] is False
        assert by_label["准备出售的投资房"] is True

    @pytest.mark.asyncio
    async def test_unknown_asset_class_is_rejected_with_the_valid_list(self):
        """Rejection must name the alternatives, or the model retries the same
        bad key instead of picking a real one."""
        result = await _tools()["record_balance_sheet"].ainvoke(
            {
                "assets": [
                    {"key": "bitcoin", "label": "BTC", "amount": "1000"},
                ]
            }
        )
        assert result.startswith("❌")
        assert "bitcoin" in result
        assert "cash" in result  # a genuinely valid key is suggested

    @pytest.mark.asyncio
    async def test_empty_sheet_is_rejected(self):
        result = await _tools()["record_balance_sheet"].ainvoke({})
        assert result.startswith("❌")

    @pytest.mark.asyncio
    async def test_negative_amount_is_rejected(self):
        """A liability recorded as a negative asset is the classic personal
        finance sign error — it must not silently produce the right net worth."""
        result = await _tools()["record_balance_sheet"].ainvoke(
            {
                "assets": [
                    {"key": "property", "label": "房", "amount": "-1800000"},
                ]
            }
        )
        assert result.startswith("❌")

    @pytest.mark.asyncio
    async def test_invalid_date_is_rejected_not_raised(self):
        result = await _tools()["record_balance_sheet"].ainvoke(
            {
                "as_of": "2026/09/14",
                "assets": [{"key": "cash", "label": "活期", "amount": "1"}],
            }
        )
        assert result.startswith("❌")
        assert "YYYY-MM-DD" in result


class TestRecordCashFlow:
    @pytest.mark.asyncio
    async def test_reports_savings_rate_excluding_investment_transfer(self):
        """储蓄投资 is the act of saving, not spending — it must not depress the
        savings rate, or a deliberate saver reports worse than someone who
        simply left the cash sitting there."""
        with pytest.MonkeyPatch.context() as mp:
            async def fake_save(user_id, kind, **kwargs):
                return "snap-1"

            mp.setattr(SAVE_PATH, fake_save)
            result = await _tools()["record_cash_flow"].ainvoke(
                {
                    "start_date": "2026-08-15",
                    "end_date": "2026-09-13",
                    "items": [
                        {"category": "收入", "label": "工资", "amount": "35000"},
                        {"category": "固定支出", "label": "房贷", "amount": "11000"},
                        {"category": "生活支出", "label": "餐饮", "amount": "6000"},
                        {"category": "可选支出", "label": "娱乐", "amount": "3000"},
                        {"category": "储蓄投资", "label": "定投", "amount": "5000"},
                    ],
                }
            )

        # (35000 − 11000 − 6000 − 3000) / 35000 = 42.86%, NOT 28.57%.
        assert "42.86%" in result
        assert "28.57%" not in result

    @pytest.mark.asyncio
    async def test_deficit_is_called_out(self):
        with pytest.MonkeyPatch.context() as mp:
            async def fake_save(user_id, kind, **kwargs):
                return "snap-1"

            mp.setattr(SAVE_PATH, fake_save)
            result = await _tools()["record_cash_flow"].ainvoke(
                {
                    "start_date": "2026-08-15",
                    "end_date": "2026-09-13",
                    "items": [
                        {"category": "收入", "label": "工资", "amount": "10000"},
                        {"category": "固定支出", "label": "房贷", "amount": "12000"},
                    ],
                }
            )
        assert "入不敷出" in result

    @pytest.mark.asyncio
    async def test_unknown_category_is_rejected(self):
        result = await _tools()["record_cash_flow"].ainvoke(
            {
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "items": [{"category": "投资", "label": "炒股", "amount": "100"}],
            }
        )
        assert result.startswith("❌")
        assert "可选支出" in result

    @pytest.mark.asyncio
    async def test_reversed_period_is_rejected(self):
        result = await _tools()["record_cash_flow"].ainvoke(
            {
                "start_date": "2026-09-30",
                "end_date": "2026-09-01",
                "items": [{"category": "收入", "label": "工资", "amount": "1"}],
            }
        )
        assert result.startswith("❌")
        assert "区间无效" in result

    @pytest.mark.asyncio
    async def test_empty_items_is_rejected(self):
        result = await _tools()["record_cash_flow"].ainvoke(
            {"start_date": "2026-08-01", "end_date": "2026-08-31"}
        )
        assert result.startswith("❌")


class TestGetNetWorth:
    @pytest.mark.asyncio
    async def test_without_a_record_it_asks_for_one_instead_of_guessing(self):
        """The whole reason this layer exists: no recorded data must produce
        "record it first", never an estimated figure."""
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return None

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_net_worth"].ainvoke({})

        assert "尚无资产负债表记录" in result
        assert "record_balance_sheet" in result

    @pytest.mark.asyncio
    async def test_computes_from_stored_components(self):
        row = _bs_row(
            [
                {
                    "key": "cash",
                    "label": "活期",
                    "amount_minor": 8_500_000,
                    "liquid": True,
                },
                {
                    "key": "property",
                    "label": "自住房",
                    "amount_minor": 350_000_000,
                    "liquid": False,
                },
            ],
            [
                {
                    "key": "mortgage",
                    "label": "房贷",
                    "amount_minor": 180_000_000,
                    "monthly_payment_minor": 980_000,
                }
            ],
        )
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return row

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_net_worth"].ainvoke({})

        assert "3,585,000.00" in result
        assert "1,785,000.00" in result
        assert "9,800.00" in result  # monthly debt service
        assert "不可动用" in result  # the house is flagged as such

    @pytest.mark.asyncio
    async def test_debt_to_asset_ratio_reports_correctly(self):
        row = _bs_row(
            [
                {
                    "key": "cash",
                    "label": "活期",
                    "amount_minor": 10_000_000,
                    "liquid": True,
                }
            ],
            [
                {
                    "key": "loan",
                    "label": "消费贷",
                    "amount_minor": 5_000_000,
                    "monthly_payment_minor": None,
                }
            ],
        )
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return row

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_net_worth"].ainvoke({})
        assert "50.00%" in result


class TestGetCashFlowAnalysis:
    def _flow_row(self):
        return {
            "snapshot_id": "s2",
            "kind": "cash_flow",
            "period_start": date(2026, 8, 15),
            "period_end": date(2026, 9, 13),  # 30 days
            "currency": "CNY",
            "note": "",
            "items": [
                {"category": "收入", "label": "工资", "amount_minor": 3_500_000},
                {"category": "固定支出", "label": "房贷", "amount_minor": 1_100_000},
                {"category": "生活支出", "label": "餐饮", "amount_minor": 600_000},
                {"category": "可选支出", "label": "娱乐", "amount_minor": 300_000},
                {"category": "储蓄投资", "label": "定投", "amount_minor": 500_000},
            ],
            "created_at": None,
        }

    @pytest.mark.asyncio
    async def test_emergency_fund_uses_liquid_assets_only(self):
        """A 3.5M house must not inflate the emergency-fund months — that is
        the reassuring-but-useless number this tool exists to avoid."""
        bs = _bs_row(
            [
                {
                    "key": "cash",
                    "label": "活期",
                    "amount_minor": 23_500_000,  # 235,000
                    "liquid": True,
                },
                {
                    "key": "property",
                    "label": "自住房",
                    "amount_minor": 350_000_000,  # 3,500,000 — not liquid
                    "liquid": False,
                },
            ]
        )
        flow = self._flow_row()
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return flow if kind == "cash_flow" else bs

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_cash_flow_analysis"].ainvoke({})

        # 235,000 / 17,000 = 13.8 months. Including the house would give ~219.6.
        assert "13.8" in result
        assert "219.6" not in result

    @pytest.mark.asyncio
    async def test_without_a_balance_sheet_it_says_so(self):
        flow = self._flow_row()
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return flow if kind == "cash_flow" else None

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_cash_flow_analysis"].ainvoke({})
        assert "尚无资产负债表记录" in result

    @pytest.mark.asyncio
    async def test_without_a_cash_flow_it_asks_for_one(self):
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return None

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_cash_flow_analysis"].ainvoke({})
        assert "尚无收支记录" in result
        assert "record_cash_flow" in result

    @pytest.mark.asyncio
    async def test_non_month_period_is_annualised_by_days(self):
        """A quarterly statement read as a month overstates essentials ~3x.
        The tool normalises by elapsed days, not by assuming 30."""
        quarter = {
            "snapshot_id": "s3",
            "kind": "cash_flow",
            "period_start": date(2026, 7, 1),
            "period_end": date(2026, 9, 30),  # 92 days
            "currency": "CNY",
            "note": "",
            "items": [
                {"category": "收入", "label": "工资", "amount_minor": 9_000_000},
                {"category": "固定支出", "label": "房贷", "amount_minor": 3_000_000},
                {"category": "生活支出", "label": "餐饮", "amount_minor": 3_000_000},
            ],
            "created_at": None,
        }
        with pytest.MonkeyPatch.context() as mp:
            async def fake_latest(user_id, kind):
                return quarter if kind == "cash_flow" else None

            mp.setattr(LATEST_PATH, fake_latest)
            result = await _tools()["get_cash_flow_analysis"].ainvoke({})

        # 60,000 over 92 days → 19,565.22/month. Anchor on the essential-spend
        # line specifically: the quarter's own 60,000 total legitimately appears
        # in the income/outflow lines above it.
        essential_line = next(
            line for line in result.splitlines() if "月度必要支出" in line
        )
        assert "19,565.22" in essential_line


class TestGetAssetClasses:
    @pytest.mark.asyncio
    async def test_lists_every_class_with_its_liquidity_default(self):
        result = await _tools()["get_asset_classes"].ainvoke({})
        for key in ("cash", "deposit", "investment", "property", "vehicle"):
            assert key in result
        assert "默认可动用" in result
        assert "默认不可动用" in result


class TestListFinancialSnapshots:
    @pytest.mark.asyncio
    async def test_rejects_an_unknown_kind(self):
        result = await _tools()["list_financial_snapshots"].ainvoke(
            {"kind": "portfolio"}
        )
        assert result.startswith("❌")

    @pytest.mark.asyncio
    async def test_summarises_both_kinds(self):
        bs = _bs_row(
            [
                {
                    "key": "cash",
                    "label": "活期",
                    "amount_minor": 10_000_000,
                    "liquid": True,
                }
            ]
        )
        flow = {
            "snapshot_id": "s4",
            "kind": "cash_flow",
            "period_start": date(2026, 8, 1),
            "period_end": date(2026, 8, 31),
            "currency": "CNY",
            "note": "8月",
            "items": [
                {"category": "收入", "label": "工资", "amount_minor": 3_500_000},
            ],
            "created_at": None,
        }
        with pytest.MonkeyPatch.context() as mp:
            async def fake_list(user_id, **kwargs):
                return [bs, flow]

            mp.setattr(LIST_PATH, fake_list)
            result = await _tools()["list_financial_snapshots"].ainvoke({})

        assert "资产负债表" in result
        assert "现金流量" in result
        assert "2026-08-01 ~ 2026-08-31" in result
        assert "8月" in result


class TestSaveFailureIsSurfaced:
    @pytest.mark.asyncio
    async def test_db_error_does_not_claim_success(self):
        """A failed write must never render as ✅ — that is how a model ends up
        telling a user their balance sheet was saved when it was not."""
        with pytest.MonkeyPatch.context() as mp:
            async def boom(user_id, kind, **kwargs):
                raise RuntimeError("connection reset")

            mp.setattr(SAVE_PATH, boom)
            result = await _tools()["record_balance_sheet"].ainvoke(
                {"assets": [{"key": "cash", "label": "活期", "amount": "1"}]}
            )
        assert result.startswith("❌")
        assert "✅" not in result
