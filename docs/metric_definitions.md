# Metric definitions — v0.1

All metrics are evaluated for a specific release, period, filter set and metric-definition version. Report the currency as USD and interpret values as source-reported distribution transactions.

| Metric | Definition | Eligibility / caveat |
|---|---|---|
| reported_sales_usd | SUM(sales_dollars), signed | Source-reported value; suspect periods require warning/block policy |
| positive_sales_usd | SUM(sales_dollars WHERE sales_dollars > 0) | Not a claim of audited gross revenue |
| negative_adjustments_usd | SUM(sales_dollars WHERE sales_dollars < 0) | Signed; no automatic return classification |
| invoice_count | COUNT(DISTINCT source invoice_id) | Block cross-regime comparisons until semantics are resolved |
| active_purchasing_stores | Distinct store_no with a positive-value record in period | Does not establish physical store open/closed status |
| mom_growth | (current - prior) / prior | Require comparable eligible periods and prior > 0; otherwise null with reason |
| contribution_usd | Current group value minus prior group value | Include newly appearing/disappearing groups and Unknown |
| reported_volume_liters | SUM(source sales_liters) | Preserve source precision; gate suspect periods |
| calculated_volume_liters | SUM(sales_bottles * bottle_volume_ml / 1000) | Diagnostic; not an automatic replacement for reported volume |

## Reconciliation

`reported_sales_usd = positive_sales_usd + negative_adjustments_usd` for valid non-null monetary inputs. Missing values must not be silently treated as zero. Group totals including Unknown must reconcile to overall totals under identical filters. Store/category contributions must sum to overall change.

## Deferred metrics

YoY requires matching prior-year eligible coverage. Profit margin requires valid cost semantics and sufficient costs. Return rate requires adjustment classification. Average invoice value requires stable invoice semantics. Forecast accuracy requires out-of-time backtests and realistic data availability.

## Evidence contract

Every report stores release_id, snapshot references, metric_version, period, filters, query identifier/hash, computed result, units and eligibility. LLM text references this evidence; it cannot invent arithmetic or causality.
