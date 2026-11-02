# ADR-001 — Snapshot loading before row-level upserts

Status: accepted for V1 design.

Context: invoice_id and invoice+item are not stable unique row keys across supplied exports. Part 5 of the supplied 2025 files overlaps fully with parts 3–4.

Decision: preserve immutable snapshots and technical source-row identity. Publish one validated snapshot per year in a versioned release. Exclude the redundant part 5 from the working input inventory, without modifying the original file.

Consequences: more retained storage, but auditable revisions and no speculative business-key deduplication. File-byte identity does not detect semantically identical re-exports; overlap investigation remains necessary.
