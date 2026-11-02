# Data discovery — supplied exports

Recorded 2026-10-20. Findings describe supplied files, not independently certified source-system facts.

## 2026

- 1,814,856 rows across four CSV members; 23 columns; observed dates January 1–September 30.
- 94,439 distinct invoice identifiers; 2,219 stores; 4,630 item codes.
- Invoice ID is not unique by row; invoice + item also is not unique.
- 14 excess identical-value rows; retain pending explanation.
- 2,474 rows lack geographic/address fields; 26 lack category.
- 1,412 rows have negative sales value and quantity. Do not label all as returns without evidence.
- January: 120,224 money differences above USD 0.01; 120,240 volume differences above 0.001 liters. 182,993 of 182,995 rows have integer-valued cost, unit price, sales value and liters.
- February–September: 21,062 money differences above USD 0.01; no volume differences above 0.001 liters.
- Source sales-value sum before any adjustment: USD 301,459,397.84. This is not audited net revenue.

## 2025 working set

| Part | Rows | Observed date range |
|---|---:|---|
| 1 | 598,080 | Jan 1–Apr 3 |
| 2 | 775,752 | Apr 3–Jul 24 |
| 3 | 628,867 | Jul 24–Oct 27 |
| 4 | 487,921 | Oct 27–Dec 31 |

Total: 2,490,620 rows. No identical-value overlap was found between parts 1–4; seven excess identical-value rows occur within those files. Part 5 is a redundant export: all 429,989 records matched parts 3–4, including occurrence counts. Exclude the file from this working set; do not globally deduplicate genuine source rows.

- All 1,213,529 January–June rows lack `state_bottle_retail`; the earlier inspection also found missing cost fields. Price multiplication is NOT_EVALUABLE when inputs are absent.
- Long invoice identifiers occur before September; short identifiers occur from September 1. A line suffix is a hypothesis, not a confirmed parsing rule. Do not remove characters or compare distinct-ID counts as invoice growth.
- January–August volume differences do not exceed 0.01 liters; this is consistent with precision differences, not proof of corruption.
- November–December reported sales values and liters are integer-valued throughout the inspected files. Investigate export precision before interpreting trends.

## Confirmed observations vs hypotheses

Reduced precision, pricing adjustments and identifier-semantic changes are open explanations. The current JSON schemas contain names/types only. Do not infer documented business rules from column labels or overwrite source amounts using derived formulas.

## Required follow-up

Obtain an independent export for suspect periods; resolve invoice identifiers with publisher documentation; reconcile period completeness and totals; record publication availability dates for time-series evaluation. No external outreach has been performed.
