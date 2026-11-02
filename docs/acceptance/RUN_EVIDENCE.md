# Two-minute demo

1. Open the [sales overview](../images/sales-overview.png): September 2026 shows $35.76M, 2.56M net bottles and 1,990 active stores. [Growth analysis](../images/growth-analysis.png) compares the same calendar month; +1.72% is September YoY, not annual growth.
2. In [data quality](../images/data-quality.png), distinguish January's $961,296 signed difference from its $972,656 absolute difference. Disagreements of opposite signs can cancel in a signed sum. Neither amount proves a loss.
3. Read the [September brief](../evidence/brief.md). The October plan is a forecast, while September's dollars are reported observations. An earlier draft dropped the required NOT_EVALUABLE status for March; regression checks and source-rendered protected fields address that failure.
4. Inspect the [task instances](../images/airflow-run.png) and [run overview](../images/airflow-overview.png). Run manual__2026-11-02T01:28:57.825826+00:00 succeeded for all six tasks. The screenshot does not distinguish RENDERED from REUSED. A separate reporting receipt for manual__2026-11-02T00:36:42.136365+00:00 recorded RENDERED.
5. Open the [Snowflake query](../images/snowflake-query.png) and [result detail](../images/snowflake-result.png): 81 rows, 81 distinct months. The sync receipt for snapshot bae8dc30-62b6-4d3d-9368-f7d3b57f7163 recorded UNCHANGED and VERIFIED after comparing monthly keys, source counts, dollars and bottles. The screenshot alone proves the counts and range, not value parity.

Local publication evidence: 27 dbt data tests, 26 passing and one nonblocking quality observation returning 81 months. The separately counted hook was successful. The stress/failure-injection suite remains deferred.
