# ADR-002 — Preserve reported values

Status: accepted for V1 design.

Context: absent prices, quantity-price differences and period-specific precision prevent a universal repair formula.

Decision: retain reported values, calculate diagnostics separately, and gate individual metrics. Missing inputs yield NOT_EVALUABLE, not PASS. Do not replace historical prices with current prices or call negative lines returns without evidence.

Consequences: some metrics remain unavailable. This is preferable to silently manufacturing precision or business meaning. Independent source verification can justify a later documented transformation.
