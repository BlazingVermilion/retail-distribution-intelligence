# Quality and publication policy

## Statuses

- PASS: implemented check ran and passed its defined scope.
- WARN: usable only with specified caveats.
- BLOCKED: affected metric/publication must not be used.
- NOT_EVALUABLE: necessary inputs or business rules are unavailable.

PASS does not certify all business semantics. Distinguish a technical release gate from metric eligibility.

## Technical blockers

Corrupt/missing selected files; malformed required fields; unknown schema; unexplained loss/duplication introduced by transformations; join fanout; unreconciled totals; incomplete candidate scope. Leave current release unchanged on failure.

## Metric-level observations

Missing category/address: use Unknown and warn. Negative amounts: preserve and investigate classification. Identical source rows: retain and flag. Missing price: multiplication check is NOT_EVALUABLE. Source precision changes: gate affected metrics/periods, without fabricating corrected values.

## Diagnostic comparisons

Money: absolute difference between reported value and quantity times reported unit price. USD 0.01 is an initial diagnostic threshold, not a documented business tolerance.

Volume: compare reported liters to quantity times milliliters / 1000. Earlier 2025 records show differences within 0.01 liters; later 2026 records often preserve more precision. Report magnitude and period-specific precision; do not apply a universal 0.001-liter hard-failure rule.

## Reconciliation boundaries

Reconcile valid parsed amounts with source decimals, account for unparseable/missing rows, and compare totals after joins and aggregations. No missing numeric cell should silently become zero.

## Open source issues

Resolve early-2025 missing prices, the September 2025 identifier transition, November 2025–January 2026 precision patterns, and later price differences. An independent export and source documentation are needed before causal explanations or blanket corrections.
