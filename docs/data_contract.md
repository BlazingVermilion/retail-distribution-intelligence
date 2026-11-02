# Data contract — v0.1

Status: proposed warehouse contract; the local inspector implements only the checks documented in its README.

## Grain and identity

RAW grain is one CSV record in one immutable snapshot. Use `(snapshot_id, source_file_id, source_row_number)` as the technical key. Row numbers count data records, starting at 1, not physical text lines. Embedded newlines are valid CSV. A content hash is not a transaction key: identical records can be legitimate occurrences.

A manifest snapshot ID hashes the source year plus the sorted set of file-byte SHA-256 hashes. Input order and renaming do not change this ID; repartitioning or line-ending changes do. This is byte-level identity, not semantic equivalence. Identical byte-content files are rejected within one input set. Partial overlap between different files requires a separate overlap review.

## Source schema

See `configs/source_schema.json`. Header names and order must match all 23 entries. Preserve original bytes and original values. Treat IDs as strings. No scientific-notation conversion of IDs and no leading-zero removal.

## Parsing

Proposed RAW storage keeps source cells as strings. STAGING converts dates to DATE, integer quantities to NUMBER(18,0), and money/volume to NUMBER(18,6). Overflow or precision beyond the selected scale must be observed before casting; do not silently round. The primitive inspector checks finite decimals, not warehouse precision/scale limits.

Missing cells remain missing. Missing dimensional attributes map to Unknown in analysis. Missing required keys/dates/amounts block publication; the current inspector records missing cells but does not yet implement this publication gate.

## Scope and completeness

Selected files must belong to one known source-year scope. Min/max dates and consecutive part names do not certify completeness. Compare expected file inventory, source metadata, row counts and period totals. Publication requires an explicit, auditable completeness decision.

## Revisions

For V1, stage complete candidate snapshots, validate, then publish a release mapping one accepted snapshot per source year. Never append overlapping versions or MERGE on invoice + item. Keep the previous release available. Do not treat absence in a partial export as a deletion.

## Record handling

Retain negative quantities/amounts and same-valued rows. Flag unexplained duplicates and price/volume differences. Never backfill missing historical prices with later prices. Keep reported and calculated amounts in separate columns.

## Schema drift

Unexpected headers fail the initial inspector. Future additive changes require a reviewed contract version. A matching schema still requires semantic checks for identifier patterns, null coverage and numeric precision by period.
