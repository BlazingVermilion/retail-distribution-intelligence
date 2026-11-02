# Business requirements

## Objective

Build a reproducible pipeline that supports monthly distribution performance review and prevents unsupported automated business statements.

## Intended users

Commercial analysts and distribution managers are design personas, not interviewed customers. Assumptions must be validated through usability review before claiming user adoption or time savings.

## Questions

1. How did reported purchasing value change between comparable periods?
2. Which stores and categories contributed most to the change?
3. Is the result affected by missing data, source revisions or precision differences?
4. Can a reviewer trace a report statement to its source snapshot and query result?

## Functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| FR-01 | Preserve immutable source snapshots | File checksums and source-row provenance |
| FR-02 | Repeat a load without multiplying records | Same snapshot loaded twice yields unchanged fact totals |
| FR-03 | Handle missing attributes without dropping transactions | Unknown-category totals reconcile |
| FR-04 | Publish only structurally validated releases | Failing candidate leaves current release unchanged |
| FR-05 | Apply metric-specific eligibility | A blocked metric is not used in AI conclusions |
| FR-06 | Support human report review | Durable approve/reject state and audit trail |
| FR-07 | Reproduce an earlier report | Snapshot, metric version and evidence references retained |

## Non-functional requirements

Use exact decimal arithmetic for money; retain leading-zero identifiers; version transformations; log failures without secrets. Measure runtime, costs and recovery behavior rather than assigning unmeasured performance claims.

## Initial scope

Monthly reported-value analysis, store/category contribution analysis, data-quality reporting and a reviewable AI narrative.

## Exclusions

Consumer-level retention, inventory replenishment quantities, causal attribution, audited net revenue/profit, real-time CDC and autonomous external notifications. Forecasting is a later experiment after historical coverage and release timing are understood.
