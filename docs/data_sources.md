# Data sources and attribution

## Source

Publisher: State of Iowa, Department of Revenue / Alcohol Operations Bureau.

- 2025: https://data.iowa.gov/catalog/dataset/1262
- 2026: https://data.iowa.gov/catalog/dataset/1263
- Catalog and license reference: https://catalog.data.gov/dataset/iowa-liquor-sales-2025
- Source license recorded during discovery: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/

Retain publisher attribution, source URL, download timestamp, applicable license and checksums with each snapshot. Verify terms when obtaining future exports. The repository MIT license does not replace dataset terms.

## Working input selection

| Year | Selected inputs | Excluded input | Reason |
|---|---|---|---|
| 2025 | Uploaded parts 1–4 | Uploaded part 5 | All 429,989 rows matched parts 3–4 including multiplicity |
| 2026 | All four members of the uploaded ZIP | None selected for exclusion | Initial working export |

Matching all observed rows is not proof of completeness against the originating system. Metadata and independent source totals should be reconciled before publication.

## Historical scope

2025–2026 are sufficient for initial pipeline implementation, but not automatically eligible for all year-over-year metrics. Schemas for 2020–2026 match in name/order/type; source semantics and precision do not necessarily match. Actual 2023–2024 records remain a later input for longer-history experiments.

## Packaging

Raw datasets are not included in this archive. `data/fixtures/transactions.csv` contains synthetic test records only. `configs/reference_inputs.json` records the locally examined export checksums; it is an inventory, not a source-issued completeness certificate.
