import json
from datetime import datetime
from pathlib import Path

import pytest

from app.db import digest
from app.metrics import calculate


@pytest.fixture
def records():
    fixture = json.loads(Path("examples/fixtures/ledger.json").read_text())
    return [{**r, "content_hash": digest(r)} for r in fixture["records"]]


def compute(records, when="2026-09-07T09:00:00+03:00"):
    return {
        m.metric_id: m
        for m in calculate(records, "2026-09-07T09:00:00+03:00", datetime.fromisoformat(when))
    }


@pytest.mark.parametrize(
    "metric,value",
    [
        ("cash_balance", "2300000.00"),
        ("overdue_receivables", "450000.00"),
        ("forecast_profit", "360000.00"),
        ("forecast_margin", "20.00"),
        ("price_change", "14.00"),
    ],
)
def test_expected_numbers(records, metric, value):
    assert compute(records)[metric].value == value


def test_each_lineage_ref_resolves(records):
    ids = {r["id"]: r for r in records}
    for metric in compute(records).values():
        assert metric.input_refs
        for ref in metric.input_refs:
            assert ids[ref["record_id"]]["content_hash"] == ref["content_hash"]


def test_partial_payment_reduces_receivables(records):
    next(r for r in records if r["id"] == "invoice-01")["paid"] = "200000.00"
    assert compute(records)["overdue_receivables"].value == "270000.00"


def test_zero_denominators(records):
    for r in records:
        if r["type"] in {"contract", "price_old"}:
            r["amount"] = "0"
    result = compute(records)
    assert result["forecast_margin"].value is None
    assert result["price_change"].value is None


def test_missing_source_is_partial(records):
    records = [r for r in records if r["type"] != "forecast_cost"]
    assert compute(records)["forecast_profit"].value is None
    assert compute(records)["forecast_profit"].completeness == "partial"


@pytest.mark.parametrize(
    "field,value",
    [("currency", "USD"), ("unit", "tonne"), ("tax", "VAT excluded"), ("delivery", "delivered")],
)
def test_incomparable_prices(records, field, value):
    next(r for r in records if r["type"] == "price_new")[field] = value
    assert compute(records)["price_change"].value is None


def test_mixed_cash_currency_not_summed(records):
    records[0]["currency"] = "USD"
    assert compute(records)["cash_balance"].value is None


def test_stale_and_future_snapshots(records):
    assert compute(records, "2026-09-10T12:00:00+03:00")["cash_balance"].freshness == "stale"
    assert compute(records, "2026-09-05T12:00:00+03:00")["cash_balance"].freshness == "unknown"
