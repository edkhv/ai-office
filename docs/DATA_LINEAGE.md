# Data lineage

Fixture: `examples/fixtures/ledger.json`, `northline-v1`, synthetic=true. Snapshot as_of is 2026-09-07 09:00 Europe/Moscow (06:00 UTC); runtime uses the real clock. Before the fixture date freshness is unknown with a future-snapshot warning, after 24 hours it is stale. This avoids freezing runtime for a nicer demo.

| Metric | Formula | Expected | Source IDs |
|---|---|---|---|
| Cash balance | 2,000,000 + 1,200,000 − 900,000; own-account transfer excluded | 2,300,000 RUB | opening, receipt, payment, internal-transfer |
| Overdue receivables | sum max(amount − paid, 0), only due_at earlier than as_of | 450,000 RUB | invoice-01, invoice-02, invoice-future (included as checked non-overdue input) |
| Forecast profit | signed contract value − expected costs | 360,000 RUB | north-contract, north-costs |
| Forecast margin | forecast profit / signed contract value × 100 | 20% | north-contract, north-costs |
| Comparable price change | (114 / 100 − 1) × 100 | 14% | steel-old, steel-new |

All calculation operands are Decimal. Money is serialized as strings. Each MetricResult contains formula ID/version, kind, input IDs and hashes, source time, completeness, freshness and warnings. `/metrics/{id}/lineage` returns the same metric plus actual SQL ledger rows, not a hand-authored explanatory card. Unit tests exercise partial payments, missing required sources, mixed currencies, non-comparable tax/delivery/unit basis, zero denominators and stale/future snapshots.

`forecast` is distinct from observed revenue. A signed contract is not a receipt. Similarity scores are not evidence confidence. Traceability demonstrates where a result came from; it does not independently establish the truth or completeness of an external source. This alpha has no real accounting connector.
