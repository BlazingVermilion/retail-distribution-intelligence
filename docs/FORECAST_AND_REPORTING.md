# Decision: classical statewide forecasting and evidence-based reporting

The planning target is monthly and calendar-year statewide wholesale net bottles. Seasonal naive is the primary plan; additive damped Holt-Winters is the comparison. ML and DL experiments remain historical research, outside the reporting path. Forecasts are deterministic given a snapshot, code and numerical environment. Neither method is promoted automatically.

Run from the repository root using the forecasting Python environment (NumPy and SciPy installed) and the existing Docker Compose PostgreSQL service:
~~~powershell
.\.venv-forecast\Scripts\python.exe scripts/monthly_brief.py --month 2026-09 --engine baseline
~~~
This package updates the existing step 13A monthly_brief.py. The default renderer needs no LLM. For the existing optional local Ollama setup, use --engine ollama. Its role is limited to choosing the opening KPI evidence ID. The forecast section, quality caveats and amounts are rendered by code in either mode.

One read-only SQL statement selects the dbt-validated publication, the requested month's KPI row, and ordered bottle history from that same snapshot through that same month. No export or training job is required. At least 36 consecutive complete numeric monthly observations are required for the outlook; completeness of the underlying extracts remains unverified. Calendar-year totals use only observations through the preceding December, if sufficient history exists. They are reconstructed with the current vintage, not attested as forecasts issued on that historical date.

Open the printed artifacts/ai_reporting/<month>/<run-id> directory. brief.md is the combined report, evidence.json identifies the source snapshot and observed KPIs, forecast.json records both 12-month paths for the rolling outlook and the two annual totals, and run.json records the reporting engine and render status. The bundled example/outlook.md is only the forecast subsection, generated from the uploaded Iowa store-week controls rather than a live publication. No Airflow schedule or Power BI dataset is modified by this package.
