from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.contracts import MetricResult


def calculate(records: list[dict[str, Any]], as_of: str, now: datetime) -> list[MetricResult]:
    snapshot = datetime.fromisoformat(as_of)
    age = (now - snapshot).total_seconds()
    freshness: Literal["fresh", "stale", "unknown"] = (
        "stale" if age > 86400 else "unknown" if age < 0 else "fresh"
    )
    base_warnings = ["Synthetic snapshot; not live financial accounts."]
    if age < 0:
        base_warnings.append("Fixture snapshot is in the future relative to the runtime clock.")
    if age > 86400:
        base_warnings.append("Snapshot is stale; no remote synchronization is configured.")
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_type.setdefault(r["type"], []).append(r)

    def metric(
        metric_id: str,
        name: str,
        value: Decimal | None,
        unit: str,
        formula: str,
        inputs: list[dict[str, Any]],
        kind: Literal["observed", "calculated", "forecast"] = "calculated",
        warnings: list[str] | None = None,
    ) -> MetricResult:
        flags = warnings or []
        return MetricResult(
            metric_id=metric_id,
            name=name,
            value=str(value.quantize(Decimal("0.01"))) if value is not None else None,
            unit=unit,
            currency="RUB" if unit == "RUB" else None,
            formula_id=metric_id + "_v1",
            formula=formula,
            input_refs=[
                {"record_id": r["id"], "version": 1, "content_hash": r["content_hash"]}
                for r in inputs
            ],
            as_of=as_of,
            last_sync_at=as_of,
            completeness="partial" if flags else "complete",
            freshness=freshness,
            kind=kind,
            warnings=base_warnings + flags,
        )

    def compatible(inputs: list[dict[str, Any]], required: set[str]) -> list[str]:
        flags = []
        if not required <= {r["type"] for r in inputs}:
            flags.append("Missing required source records.")
        if any(r.get("currency") != "RUB" for r in inputs):
            flags.append("Mixed or unsupported currencies; conversion source required.")
        return flags

    cash = by_type.get("cash", [])
    cash_flags = compatible(cash, {"cash"})
    balance = sum(
        (
            Decimal(r["amount"]) * {"opening": 1, "in": 1, "out": -1, "internal": 0}[r["direction"]]
            for r in cash
        ),
        Decimal(0),
    )
    receivables = by_type.get("receivable", [])
    ar_flags = compatible(receivables, {"receivable"})
    overdue = sum(
        (
            max(Decimal(r["amount"]) - Decimal(r["paid"]), Decimal(0))
            for r in receivables
            if datetime.fromisoformat(r["due_at"]) < snapshot
        ),
        Decimal(0),
    )
    forecast = by_type.get("contract", []) + by_type.get("forecast_cost", [])
    forecast_flags = compatible(forecast, {"contract", "forecast_cost"})
    contract = sum((Decimal(r["amount"]) for r in forecast if r["type"] == "contract"), Decimal(0))
    cost = sum((Decimal(r["amount"]) for r in forecast if r["type"] == "forecast_cost"), Decimal(0))
    margin_flags = forecast_flags + (
        ["Zero contract value: margin is undefined."] if contract == 0 else []
    )
    prices = by_type.get("price_old", []) + by_type.get("price_new", [])
    price_flags = compatible(prices, {"price_old", "price_new"})
    delta = None
    if len(prices) == 2 and not price_flags:
        old, new = prices
        if any(old.get(k) != new.get(k) for k in ("unit", "delivery", "tax")):
            price_flags.append("Non-comparable unit, delivery or tax basis.")
        elif Decimal(old["amount"]) == 0:
            price_flags.append("Zero previous price: change is undefined.")
        else:
            delta = (Decimal(new["amount"]) / Decimal(old["amount"]) - 1) * 100
    else:
        price_flags.append("Exactly one old and one new quote are required.")
    return [
        metric(
            "cash_balance",
            "Cash balance / Денежный остаток",
            None if cash_flags else balance,
            "RUB",
            "opening + external inflows − external outflows; internal transfers excluded",
            cash,
            warnings=cash_flags,
        ),
        metric(
            "overdue_receivables",
            "Overdue receivables / Просроченная дебиторка",
            None if ar_flags else overdue,
            "RUB",
            "Σ max(amount − paid, 0) where due_at < snapshot as_of",
            receivables,
            warnings=ar_flags,
        ),
        metric(
            "forecast_profit",
            "Forecast profit / Прогнозная прибыль",
            None if forecast_flags else contract - cost,
            "RUB",
            "signed contract value − forecast costs",
            forecast,
            kind="forecast",
            warnings=forecast_flags,
        ),
        metric(
            "forecast_margin",
            "Forecast margin / Прогнозная маржа",
            None if margin_flags else (contract - cost) / contract * 100,
            "%",
            "(signed contract value − forecast costs) / signed contract value × 100",
            forecast,
            kind="forecast",
            warnings=margin_flags,
        ),
        metric(
            "price_change",
            "Price change / Рост цены",
            None if price_flags else delta,
            "%",
            "(new comparable unit price / previous unit price − 1) × 100",
            prices,
            warnings=price_flags,
        ),
    ]
